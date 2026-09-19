"""Smoke test: all three engines answer one snake-safety question."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engines import JevAPI, NanoJevLocal, LayaLocal, normalize  # noqa: E402

CRIT = {"up": "(5,4) empty", "down": "(5,6) body",
        "left": "(4,5) empty", "right": "(6,5) empty"}
STATE = "Snake 12x12. Head at (5,5). Body occupies (5,6) and (5,7). Food at (8,5)."
INSTR = "Which direction is immediately safe for the snake head?"

from dotenv import load_dotenv  # noqa: E402

load_dotenv(r"F:\Space\PRO\test\jev-arena\.env")

for cls in (JevAPI, NanoJevLocal, LayaLocal):
    eng = cls()
    try:
        ans = eng.ask(STATE, INSTR, CRIT)
        ans = normalize(ans, CRIT)
        print(f"{eng.name:8s} choice={ans['choice']:6s} probs={ans['probabilities']} "
              f"conf={ans.get('confidence')} lat={ans['latency_ms']}ms")
    finally:
        if hasattr(eng, "close"):
            eng.close()
print("SMOKE OK")
