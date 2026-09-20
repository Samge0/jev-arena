"""Smoke test for the v3 protocol: fan-out multi-question on one state per
game, all three engines, checking contract shapes for choice AND noul."""
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "runner"))

from dotenv import load_dotenv
load_dotenv(os.path.join(BASE, ".env"))

from engines_multi import JevAPIMulti, NanoJevMulti, LayaMulti  # noqa: E402
from games.game1024 import Game1024  # noqa: E402
from games.tetris_v2 import TetrisV2  # noqa: E402
import protocol_v3  # noqa: E402

# --- tetris
env = TetrisV2(seed=2026)
env.legal_actions()
qs = protocol_v3.tetris_questions_v3(env)
state = protocol_v3.tetris_state_v3(env)
print("TETRIS options:", len(qs["action"]["criteria"]), "questions:", list(qs))
print(state.splitlines()[-3], "| holes line:", [l for l in state.splitlines() if "holes" in l][0][:80])

for cls in (JevAPIMulti, NanoJevMulti, LayaMulti):
    eng = cls()
    try:
        answers, usage = eng.ask_multi(state, qs)
        act = answers.get("action", {})
        noul = answers.get("hole_free_exists", {})
        print(f"{eng.name:8s} action={act.get('choice'):6s} conf={act.get('confidence')} "
              f"noul(hole_free)={noul.get('noul')} qids={sorted(answers)}")
    except Exception as e:
        print(f"{eng.name:8s} ERROR {type(e).__name__}: {str(e)[:180]}")
    finally:
        if hasattr(eng, "close"):
            eng.close()

# --- 1024
env2 = Game1024(seed=2026)
env2.grid = [[2, 2, 4, 0], [0, 0, 2, 2], [4, 0, 4, 0], [2, 2, 0, 0]]
qs2 = protocol_v3.game1024_questions_v3(env2)
state2 = protocol_v3.game1024_state_v3(env2)
print("\n1024 state:\n" + state2)
for cls in (JevAPIMulti, NanoJevMulti, LayaMulti):
    eng = cls()
    try:
        answers, usage = eng.ask_multi(state2, qs2)
        act = answers.get("action", {})
        noul = answers.get("stuck_risk", {})
        print(f"{eng.name:8s} action={act.get('choice'):6s} conf={act.get('confidence')} "
              f"noul(stuck)={noul.get('noul')}")
    except Exception as e:
        print(f"{eng.name:8s} ERROR {type(e).__name__}: {str(e)[:180]}")
    finally:
        if hasattr(eng, "close"):
            eng.close()
print("V3 SMOKE DONE")
