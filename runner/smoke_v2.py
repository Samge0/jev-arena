"""One-step smoke for tetris v2 combined action space (17 options)."""
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "runner"))

from dotenv import load_dotenv
load_dotenv(os.path.join(BASE, ".env"))

from engines import JevAPI, NanoJevLocal, LayaLocal, normalize  # noqa: E402
from games.tetris_v2 import TetrisV2  # noqa: E402

env = TetrisV2(seed=2026)
env.legal_actions()  # populate placements cache
desc = env.action_descriptions()
print("options:", len(desc), flush=True)
instr = ("Pick the best (orientation, column) placement for the current piece. "
         "Answer with exactly one option id like r0c4.")

for cls in (JevAPI, NanoJevLocal, LayaLocal):
    eng = cls()
    try:
        ans = normalize(eng.ask(env.state_for_model(), instr, desc), desc)
        top3 = sorted(ans["probabilities"].items(), key=lambda kv: -kv[1])[:3]
        print(f"{eng.name:8s} choice={ans['choice']:6s} conf={ans.get('confidence')} top3={top3}", flush=True)
    except Exception as e:
        print(f"{eng.name:8s} ERROR {type(e).__name__}: {str(e)[:200]}", flush=True)
    finally:
        if hasattr(eng, "close"):
            eng.close()
print("SMOKE DONE")
