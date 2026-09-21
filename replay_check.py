"""Replay-consistency check (mirrors the NanoJev author's CPU replay checks):
for every recorded run, re-execute the recorded action sequence on a fresh
deterministic engine and verify every frame's grid + metrics match the
recording byte-for-byte. Also validates schema invariants.

Exit 0 = all runs consistent.
"""
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from games.game1024 import Game1024
from games.tetris_v2 import TetrisV2

GAMES = {"tetris": TetrisV2, "1024": Game1024}


def grid_sig(grid):
    return [list(row) for row in grid]


def check_run(ex):
    problems = []
    env = GAMES[ex["game"]](seed=ex["seed"])
    frames = ex["frames"]
    # frame 0 must equal the initial state
    if grid_sig(frames[0]["grid"]) != grid_sig(env.grid):
        problems.append("frame0 grid mismatch (initial state)")
    for i, fr in enumerate(frames[1:], start=1):
        action = fr.get("action")
        if action is None:
            if fr.get("event") == "engine_failure":
                break
            problems.append(f"frame{i} has no action")
            break
        if action not in env.legal_actions() and not fr.get("violation", False):
            # recorded action must be legal at replay time unless flagged
            problems.append(f"frame{i} action {action} illegal at replay")
        env.step(action)
        if grid_sig(fr["grid"]) != grid_sig(env.grid):
            problems.append(f"frame{i} grid mismatch after stepping {action}")
            break
        # metrics consistency
        m = fr.get("metrics") or {}
        if ex["game"] == "tetris":
            if m.get("score") != env.score or m.get("lines") != env.lines:
                problems.append(f"frame{i} metrics mismatch")
                break
        else:
            if m.get("score") != env.score or m.get("max_tile") != env.max_tile:
                problems.append(f"frame{i} metrics mismatch (1024)")
                break
        # probability invariants on decision frames
        probs = fr.get("probabilities") or {}
        if probs:
            total = sum(probs.values())
            if not 0.98 <= total <= 1.02:
                problems.append(f"frame{i} probabilities sum {total:.3f}")
            # argmax consistency: raw argmax, the chosen action, or a documented
            # composite re-rank (decision_source='rerank' / violation flag) are all legal
            if (fr.get("action") and probs.get(action, 0) < max(probs.values()) - 1e-6
                    and fr.get("decision_source") not in ("rerank",)
                    and not fr.get("violation")):
                problems.append(f"frame{i} action is not argmax of recorded probs (src={fr.get('decision_source')})")
    # summary consistency
    s = ex["summary"]
    if s.get("frames_recorded") != len(frames) - 1:
        problems.append("summary.frames_recorded mismatch")
    if ex["game"] == "tetris":
        if s.get("score") != env.score:
            problems.append(f"summary score {s.get('score')} != replayed {env.score}")
        if s.get("lines") != env.lines:
            problems.append(f"summary lines {s.get('lines')} != replayed {env.lines}")
    else:
        if s.get("score") != env.score:
            problems.append(f"summary score {s.get('score')} != replayed {env.score}")
    return problems


def main():
    path = os.path.join(BASE, "web", "arena_results.json")
    data = json.load(open(path, encoding="utf-8"))
    ok = True
    for ex in data["examples"]:
        problems = check_run(ex)
        status = "OK " if not problems else "FAIL"
        print(f"{status} {ex['id']}  frames={len(ex['frames'])}")
        for p in problems:
            print(f"     - {p}")
            ok = False
    # schema invariants
    n_expected = len(data["seeds"]) * len(GAMES) * 3
    if len(data["examples"]) != n_expected:
        print(f"WARN expected {n_expected} runs, found {len(data['examples'])}")
    print("\nREPLAY CHECK:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
