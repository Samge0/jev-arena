"""laya worker v2: single- AND multi-question line protocol.

Requests:
  {"state", "instructions", "criteria"}                 -> legacy single choice
  {"mode": "multi", "state", "questions": {qid: q}}    -> fan-out (choice only)
"""
import json
import os
import sys
import time

import laya

agent = laya.load(os.environ.get("LAYA_MODEL_ID", "convaiinnovations/laya"))
print("READY", flush=True)


def ask_one(state, instructions, criteria):
    result = agent.predict(state, {"q": {"type": "choice", "instructions": instructions,
                                         "criteria": criteria}})
    return result["answers"]["q"]


for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    req = json.loads(line)
    t0 = time.perf_counter()
    try:
        if req.get("mode") == "multi":
            answers = {}
            for qid, q in req["questions"].items():
                if q.get("type") != "choice":
                    continue
                ans = ask_one(req["state"], q["instructions"], q["criteria"])
                answers[qid] = {"choice": ans.get("choice"),
                                "probabilities": ans.get("probabilities"),
                                "confidence": ans.get("confidence"),
                                "latency_ms": int((time.perf_counter() - t0) * 1000),
                                "raw": {"backend": "laya"}}
            print(json.dumps({"answers": answers, "usage": None}), flush=True)
        else:
            ans = ask_one(req["state"], req["instructions"], req["criteria"])
            print(json.dumps({"choice": ans["choice"], "probabilities": ans["probabilities"],
                              "confidence": ans.get("confidence"),
                              "latency_ms": int((time.perf_counter() - t0) * 1000),
                              "raw": {"backend": "laya-modernbert-421m"}}), flush=True)
    except Exception as e:
        out = {"answers": {}, "error": f"{type(e).__name__}: {e}"} if req.get("mode") == "multi" else \
              {"choice": None, "probabilities": {}, "confidence": None,
               "latency_ms": int((time.perf_counter() - t0) * 1000),
               "raw": {"error": f"{type(e).__name__}: {e}"}}
        print(json.dumps(out), flush=True)
