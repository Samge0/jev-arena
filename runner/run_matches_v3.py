"""V3 match recorder: best-practice protocol (fan-out + composite scoring).

Per step (all engines, same request bytes):
  1. one ask_multi call: action choice (strategy-hierarchy instructions) + noul
  2. code-side composite scoring (argmax unless razor-thin margin AND the noul
     gate fires, then deterministic re-rank from placement facts)
  3. single legal action -> executed by code, no model call (forced move)
Schema: jev-arena-v3.
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

from engines_multi import JevAPIMulti, NanoJevMulti, LayaMulti  # noqa: E402
from games.game1024 import Game1024  # noqa: E402
from games.tetris_v2 import TetrisV2  # noqa: E402
import protocol_v3  # noqa: E402

GAMES = {
    "tetris": lambda seed: TetrisV2(seed=seed),
    "1024": lambda seed: Game1024(seed=seed),
}
SEEDS = [2026, 901]
ENGINE_CLASSES = [JevAPIMulti, NanoJevMulti, LayaMulti]
STEP_BUDGET = {"tetris": 80, "1024": 240}
MAX_CONSECUTIVE_ERRORS = 5
INVERSE = {"up": "down", "down": "up", "left": "right", "right": "left"}


def render_state(env, game):
    return protocol_v3.tetris_state_v3(env) if game == "tetris" else protocol_v3.game1024_state_v3(env)


def build_questions(env, game):
    return protocol_v3.tetris_questions_v3(env) if game == "tetris" else protocol_v3.game1024_questions_v3(env)


def compose(action_ans, noul_ans, legal, desc, game):
    if game == "tetris":
        return protocol_v3.compose_tetris(action_ans, noul_ans, legal, desc)
    return protocol_v3.compose_1024(action_ans, noul_ans, legal, desc)


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
    forced_moves = 0
    reranks = 0
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

        # best practice: single legal action -> code executes, no model call
        if len(legal) == 1:
            choice = legal[0]
            forced_moves += 1
            frame_extra = {"probabilities": {choice: 1.0}, "confidence": 1.0,
                           "decision_source": "forced", "violation": False,
                           "latency_ms": 0, "noul": None}
        else:
            state_text = render_state(env, game_name)
            questions = build_questions(env, game_name)
            noul_qid = "hole_free_exists" if game_name == "tetris" else "stuck_risk"
            try:
                answers, usage = engine.ask_multi(state_text, questions)
                consecutive_errors = 0
            except Exception as e:
                answers, usage = {}, None
                consecutive_errors += 1
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    env.alive = False
                    env.outcome = "engine_failure"
                    frames.append({"frame": step + 1, "grid": [row[:] for row in env.grid],
                                   "metrics": dict(env.metrics()) if game_name == "tetris" else {"score": env.score, "max_tile": env.max_tile},
                                   "event": "engine_failure", "error": f"{type(e).__name__}: {e}"})
                    break
            action_ans = answers.get("action", {})
            noul_ans = answers.get(noul_qid)
            if action_ans.get("probabilities"):
                action_ans = {"choice": action_ans.get("choice"),
                              "probabilities": action_ans.get("probabilities"),
                              "confidence": action_ans.get("confidence")}
            raw_answers.append({"action": action_ans, "noul": noul_ans, "usage": usage})
            latencies.append(action_ans.get("latency_ms") or
                             next(iter([a.get("latency_ms") for a in answers.values()]), 0) or 0)

            choice, comp = compose(action_ans, noul_ans, legal, desc, game_name)
            if action_ans.get("choice") not in legal:
                violations += 1
            if comp.get("rule") == "rerank":
                reranks += 1
            frame_extra = {
                "probabilities": action_ans.get("probabilities") or {choice: 1.0},
                "confidence": action_ans.get("confidence"),
                "decision_source": comp.get("rule", "argmax"),
                "violation": action_ans.get("choice") not in legal if action_ans.get("choice") else False,
                "latency_ms": action_ans.get("latency_ms"),
                "noul": (noul_ans or {}).get("noul"),
            }

        env.step(choice)
        step += 1

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
            "current_piece": getattr(env, "current", None),
            **frame_extra,
        })

    summary = env.summary()
    summary.update({
        "violations": violations,
        "avg_latency_ms": int(sum(latencies) / len(latencies)) if latencies else 0,
        "frames_recorded": len(frames) - 1,
        "forced_moves": forced_moves,
        "reranks": reranks,
    })
    if game_name == "1024":
        total_moves = sum(direction_usage.values()) or 1
        summary["oscillation_rate"] = round(oscillations / total_moves, 3)
        summary["repeat_rate"] = round(repeats / total_moves, 3)
        summary["direction_usage"] = direction_usage
    else:
        summary["orientation_usage"] = orientation_usage
        summary["orientations_used"] = len(orientation_usage)
    return {"game": game_name, "seed": seed, "frames": frames, "summary": summary,
            "raw_answers": raw_answers}


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
                    if prev.get("schema") == "jev-arena-v3":
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
                print(f"{eng.name:8s} {json.dumps(s)} wall={wall}s", flush=True)
                examples.append({"id": f"{game_name}:seed{seed}:{eng.name}", "game": game_name,
                                 "seed": seed, "engine": eng.name, **run})
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
    out = {"schema": "jev-arena-v3", "protocol": "fanout+composite",
           "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
           "step_budget": STEP_BUDGET, "seeds": SEEDS,
           "examples": examples, "tallies": tallies}
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    slim = {k: v for k, v in out.items() if k != "examples"}
    slim["examples"] = []
    for ex in out["examples"]:
        frames = []
        for fr in ex["frames"]:
            f2 = {k: v for k, v in fr.items()
                  if k not in ("error", "decision_source", "latency_ms", "current_piece")}
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
