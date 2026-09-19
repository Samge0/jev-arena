"""Play full games for every (game, seed) with all three engines and record
replay JSON for the web viewer + a tallies summary.

Protocol per step (identical across engines — fair comparison):
  1. render state_for_model()
  2. ask the single choice question with action descriptions
  3. normalize answer, take argmax; if the choice is not a legal action
     (contract violation), fall back to engine argmax over legal actions and
     record violation=true; if nothing is legal, play random legal action and
     record fallback="random".
  4. step the environment; record frame.

Output: web/arena_results.json  {"schema": "jev-arena-v1", "examples": [...], "tallies": {...}}
"""
from __future__ import annotations

import json
import os
import random
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "runner"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(BASE, ".env"))

from engines import JevAPI, NanoJevLocal, LayaLocal, normalize  # noqa: E402
from games.game1024 import Game1024  # noqa: E402
from games.tetris import Tetris  # noqa: E402

GAMES = {
    "tetris": lambda seed: Tetris(seed=seed),
    "1024": lambda seed: Game1024(seed=seed),
}
SEEDS = [2026, 901]
ENGINE_CLASSES = [JevAPI, NanoJevLocal, LayaLocal]
STEP_BUDGET = {"tetris": 80, "1024": 240}
MAX_CONSECUTIVE_ERRORS = 5
DECISION_TIMEOUTS = {}


def play_one(engine, game_name, seed):
    env = GAMES[game_name](seed)
    frames = [{
        "frame": 0,
        "grid": [row[:] for row in env.grid],
        "metrics": dict(env.metrics()) if game_name == "tetris" else {"score": 0, "max_tile": 2},
        "event": "initial",
    }]
    violations = 0
    latencies = []
    raw_answers = []
    consecutive_errors = 0
    step = 0
    while env.alive and step < STEP_BUDGET[game_name]:
        legal = env.legal_actions()
        if not legal:
            break
        desc = env.action_descriptions()
        state_text = env.state_for_model()
        instr = ("Which action is the best next move? Answer with exactly one option id. "
                 if game_name == "tetris" else
                 "Which slide direction is the best next move? Answer with exactly one option id.")
        try:
            ans = engine.ask(state_text, instr, desc)
            consecutive_errors = 0
        except Exception as e:
            # network/worker failure: fall back to random, log it
            ans = {"choice": None, "probabilities": {}, "confidence": None,
                   "latency_ms": None, "raw": {"error": f"{type(e).__name__}: {e}"}}
            consecutive_errors += 1
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                frames.append({
                    "frame": step + 1, "grid": [row[:] for row in env.grid],
                    "metrics": dict(env.metrics()) if game_name == "tetris" else {"score": env.score, "max_tile": env.max_tile},
                    "event": "engine_failure", "error": ans["raw"]["error"],
                })
                env.alive = False
                env.outcome = "engine_failure"
                break
        ans = normalize(ans, desc)
        latencies.append(ans.get("latency_ms") or 0)
        raw_answers.append(ans)

        choice = ans["choice"]
        violation = choice not in legal
        fallback = None
        if violation:
            violations += 1
            legal_probs = {k: ans["probabilities"].get(k, 0.0) for k in legal}
            if max(legal_probs.values()) > 0:
                choice = max(legal_probs, key=legal_probs.get)
                fallback = "legal_argmax"
            else:
                choice = random.Random(seed * 1000 + step).choice(legal)
                fallback = "random"
        env.step(choice)
        step += 1

        if game_name == "tetris":
            metrics = dict(env.metrics())
        else:
            metrics = {"score": env.score, "max_tile": env.max_tile}
        frames.append({
            "frame": step,
            "grid": [row[:] for row in env.grid],
            "metrics": metrics,
            "action": choice,
            "probabilities": ans["probabilities"],
            "confidence": ans.get("confidence"),
            "chosen_prob": ans["probabilities"].get(choice, 0.0),
            "violation": violation,
            "fallback": fallback,
            "error": (ans.get("raw") or {}).get("error"),
            "latency_ms": ans.get("latency_ms"),
            "current_piece": getattr(env, "current", None),
            "collision": violation,
            "forced": False,
            "decision_source": fallback or "model",
        })

    summary = env.summary()
    summary.update({
        "violations": violations,
        "avg_latency_ms": int(sum(latencies) / len(latencies)) if latencies else 0,
        "frames_recorded": len(frames) - 1,
    })
    return {
        "game": game_name,
        "seed": seed,
        "frames": frames,
        "summary": summary,
        "raw_answers": raw_answers,
    }


def main():
    engines = [cls() for cls in ENGINE_CLASSES]
    examples = []
    dest = os.path.join(BASE, "web", "arena_results.json")
    t_all = time.perf_counter()
    for game_name in GAMES:
        for seed in SEEDS:
            # resume: skip (game, seed, engine) combos already recorded
            done = set()
            if os.path.exists(dest):
                try:
                    with open(dest, encoding="utf-8") as f:
                        prev = json.load(f)
                    done = {(e["game"], e["seed"], e["engine"]) for e in prev.get("examples", [])}
                    examples = [e for e in prev.get("examples", [])]
                except Exception:
                    done = set()
                    examples = []
            print(f"\n=== {game_name} seed={seed} ===", flush=True)
            for eng in engines:
                if (game_name, seed, eng.name) in done:
                    print(f"{eng.name:8s} already recorded, skip", flush=True)
                    continue
                t0 = time.perf_counter()
                run = play_one(eng, game_name, seed)
                wall = int(time.perf_counter() - t0)
                s = run["summary"]
                print(f"{eng.name:8s} {json.dumps({k: s[k] for k in s if k not in ()})} wall={wall}s", flush=True)
                examples.append({
                    "id": f"{game_name}:seed{seed}:{eng.name}",
                    "game": game_name,
                    "seed": seed,
                    "engine": eng.name,
                    **run,
                })
                _save(dest, examples, engines, t_all)
    for eng in engines:
        if hasattr(eng, "close"):
            eng.close()

    _save(dest, examples, engines, t_all)
    print(f"\nWROTE {dest} ({os.path.getsize(dest)/1024:.0f} KB) in {int(time.perf_counter()-t_all)}s")


def _save(dest, examples, engines, t_all):
    # tallies: per game, rank engines
    tallies = {}
    for game_name in GAMES:
        rows = []
        for eng in engines:
            runs = [e for e in examples if e["game"] == game_name and e["engine"] == eng.name]
            agg = {
                "engine": eng.name,
                "runs": len(runs),
            }
            keys = list(runs[0]["summary"].keys()) if runs else []
            for k in keys:
                vals = [r["summary"].get(k) for r in runs]
                if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
                    agg[k] = round(sum(vals) / len(vals), 1)
                else:
                    agg[k] = vals[0]
            rows.append(agg)
        tallies[game_name] = rows

    out = {
        "schema": "jev-arena-v1",
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "step_budget": STEP_BUDGET,
        "seeds": SEEDS,
        "examples": examples,
        "tallies": tallies,
    }
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    return out


if __name__ == "__main__":
    main()
