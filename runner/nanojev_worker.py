"""NanoJev worker: line protocol. stdin JSON -> stdout JSON, one per line.

Body: {"state": str, "instructions": str, "criteria": {opt: desc}}
Reply: {"choice": str, "probabilities": {...}, "confidence": null,
        "latency_ms": int, "raw": {...}}
"""
import json
import sys
import time

ckpt = sys.argv[1]
sys.path.insert(0, r"F:\Space\PRO\test\nanojev\NanoJev\scripts")

from predict_toy_decisions import DecisionPredictor  # noqa: E402

engine = DecisionPredictor(ckpt, precision="bf16")
print("READY", flush=True)

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    req = json.loads(line)
    body = {
        "states": [{
            "id": "q",
            "state": req["state"],
            "questions": {"q": {"type": "choice", "instructions": req["instructions"],
                                 "criteria": req["criteria"]}},
        }]
    }
    t0 = time.perf_counter()
    try:
        result = engine.predict(body)
        latency = int((time.perf_counter() - t0) * 1000)
        ans = result["states"][0]["answers"]["q"]
        out = {
            "choice": ans["choice"],
            "probabilities": ans["probabilities"],
            "confidence": ans.get("confidence"),
            "latency_ms": latency,
            "raw": {"backend": "nanojev-decision-predictor", "precision": "bf16"},
        }
    except Exception as e:  # keep the worker alive on per-question errors
        out = {"choice": None, "probabilities": {}, "confidence": None,
               "latency_ms": int((time.perf_counter() - t0) * 1000),
               "raw": {"error": f"{type(e).__name__}: {e}"}}
    print(json.dumps(out), flush=True)
