"""V2 match recorder: full games for every (game, seed) with all three engines.

Changes vs v1 (see web/arena_results_v1.json):
  - Tetris uses TetrisV2: (orientation, column) combined action space
  - schema jev-arena-v2; per-run extra stats:
      oscillation_rate : fraction of 1024 moves that are the inverse of the
                         previous move (up<->down, left<->right)
      direction_usage  : {dir: count} for 1024
      orientation_usage: {orientation: count} for tetris
      repeats          : consecutive identical moves (1024)
Output: web/arena_results.json (v2) + slim
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
from games.tetris_v2 import TetrisV2  # noqa: E402

GAMES = {
    "tetris": lambda seed: TetrisV2(seed=seed),
    "1024": lambda seed: Game1024(seed=seed),
}
SEEDS = [2026, 901]
ENGINE_CLASSES = [JevAPI, NanoJevLocal, LayaLocal]
STEP_BUDGET = {"tetris": 80, "1024": 240}
MAX_CONSECUTIVE_ERRORS = 5
INVERSE = {"up": "down", "down": "up", "left": "right", "right": "left"}


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
    prev_action = None
    oscillations = 0
    repeats = 0
    direction_usage = {}
    orientation_usage = {}
    step = 0
    while env.alive and step < STEP_BUDGET[game_name]:
        legal = env.legal_actions()
        if not legal:
            break
        desc = env.action_descriptions()
        state_text = env.state_for_model()
        if game_name == "tetris":
            instr = ("Pick the best (orientation, column) placement for the current piece. "
                     "Answer with exactly one option id like r0c4.")
        else:
            instr = "Which slide direction is the best next move? Answer with exactly one option id."
        try:
            ans = engine.ask(state_text, instr, desc)
            consecutive_errors = 0
        except Exception as e:
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

        # behavior stats
        if game_name == "1024":
            direction_usage[choice] = direction_usage.get(choice, 0) + 1
            if prev_action is not None:
                if choice == INVERSE.get(prev_action):
                    oscillations += 1
                elif choice == prev_action:
                    repeats += 1
        else:
            oi = int(choice[1:].split("c")[0])
            orientation_usage[str(oi)] = orientation_usage.get(str(oi), 0) + 1
        prev_action = choice

        metrics = dict(env.metrics()) if game_name == "tetris" else {"score": env.score, "max_tile": env.max_tile}
        frames.append({
            "frame": step,
            "grid": [row[:] for row in env.grid],
            "metrics": metrics,
            "action": choice,
            "probabilities": ans["probabilities"],
            "confidence": ans.get("confidence"),
            "violation": violation,
            "latency_ms": ans.get("latency_ms"),
            "current_piece": getattr(env, "current", None),
            "violation_flag": violation,
            "decision_source": fallback or "model",
        })

    summary = env.summary()
    summary.update({
        "violations": violations,
        "avg_latency_ms": int(sum(latencies) / len(latencies)) if latencies else 0,
        "frames_recorded": len(frames) - 1,
    })
    if game_name == "1024":
        total_moves = sum(direction_usage.values()) or 1
        summary["oscillation_rate"] = round(oscillations / total_moves, 3)
        summary["repeat_rate"] = round(repeats / total_moves, 3)
        summary["direction_usage"] = direction_usage
    else:
        summary["orientation_usage"] = orientation_usage
        summary["orientations_used"] = len(orientation_usage)
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
            done = set()
            if os.path.exists(dest):
                try:
                    with open(dest, encoding="utf-8") as f:
                        prev = json.load(f)
                    if prev.get("schema") == "jev-arena-v2":
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
                print(f"{eng.name:8s} {json.dumps({k: s[k] for k in s})} wall={wall}s", flush=True)
                examples.append({
                    "id": f"{game_name}:seed{seed}:{eng.name}",
                    "game": game_name,
                    "seed": seed,
                    "engine": eng.name,
                    **run,
                })
                _save(dest, examples, engines)
    for eng in engines:
        if hasattr(eng, "close"):
            eng.close()
    _save(dest, examples, engines)
    print(f"\nWROTE {dest} ({os.path.getsize(dest)/1024:.0f} KB) in {int(time.perf_counter()-t_all)}s")


def _save(dest, examples, engines):
    tallies = {}
    for game_name in GAMES:
        rows = []
        for eng in engines:
            runs = [e for e in examples if e["game"] == game_name and e["engine"] == eng.name]
            agg = {"engine": eng.name, "runs": len(runs)}
            keys = list(runs[0]["summary"].keys()) if runs else []
            for k in keys:
                vals = [r["summary"].get(k) for r in runs]
                if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
                    agg[k] = round(sum(vals) / len(vals), 2)
                elif k in ("direction_usage", "orientation_usage"):
                    merged = {}
                    for v in vals:
                        for kk, vv in (v or {}).items():
                            merged[kk] = merged.get(kk, 0) + vv
                    agg[k] = merged
                else:
                    agg[k] = vals[0]
            rows.append(agg)
        tallies[game_name] = rows

    out = {
        "schema": "jev-arena-v2",
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "step_budget": STEP_BUDGET,
        "seeds": SEEDS,
        "examples": examples,
        "tallies": tallies,
    }
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    # slim
    slim = {k: v for k, v in out.items() if k != "examples"}
    slim["examples"] = []
    for ex in out["examples"]:
        frames = []
        for fr in ex["frames"]:
            f2 = {k: v for k, v in fr.items()
                  if k not in ("error", "decision_source", "latency_ms", "current_piece", "violation_flag")}
            if "grid" in f2:
                f2["grid"] = [",".join(str(v) for v in row) for row in f2["grid"]]
            frames.append(f2)
        slim["examples"].append({"id": ex["id"], "game": ex["game"], "seed": ex["seed"],
                                 "engine": ex["engine"], "summary": ex["summary"], "frames": frames})
    with open(dest.replace("arena_results", "arena_slim"), "w", encoding="utf-8") as f:
        json.dump(slim, f, ensure_ascii=False)
    return out


if __name__ == "__main__":
    main()
