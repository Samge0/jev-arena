"""laya worker: line protocol. stdin JSON -> stdout JSON, one per line.

Body: {"state": str, "instructions": str, "criteria": {opt: desc}}
Reply: same shape as nanojev worker.
"""
import json
import sys
import time

import laya

agent = laya.load("convaiinnovations/laya")
print("READY", flush=True)

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    req = json.loads(line)
    t0 = time.perf_counter()
    try:
        result = agent.predict(req["state"], {"q": {"type": "choice",
                                                    "instructions": req["instructions"],
                                                    "criteria": req["criteria"]}})
        latency = int((time.perf_counter() - t0) * 1000)
        ans = result["answers"]["q"]
        out = {
            "choice": ans["choice"],
            "probabilities": ans["probabilities"],
            "confidence": ans.get("confidence"),
            "latency_ms": latency,
            "raw": {"backend": "laya-modernbert-421m"},
        }
    except Exception as e:
        out = {"choice": None, "probabilities": {}, "confidence": None,
               "latency_ms": int((time.perf_counter() - t0) * 1000),
               "raw": {"error": f"{type(e).__name__}: {e}"}}
    print(json.dumps(out), flush=True)
