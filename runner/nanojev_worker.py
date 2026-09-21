"""NanoJev worker v2: single- AND multi-question line protocol.

Requests:
  {"state", "instructions", "criteria"}                 -> legacy single choice
  {"mode": "multi", "state", "questions": {qid: q}}    -> fan-out (choice only)
Replies: single -> flat answer; multi -> {"answers": {qid: answer}, "usage": null}
"""
import json
import os
import sys
import time

ckpt = sys.argv[1]
# max_length 1024: the backbone config allows 40960 positions; the training
# default 512 refuses (not truncates) overflowing candidate paths. Game states
# with 17-34 enriched options need ~550-700 tokens.
max_len = int(sys.argv[2]) if len(sys.argv) > 2 else 1024
_scripts = os.environ.get("NANOJEV_SCRIPTS")
if not _scripts:
    raise SystemExit("NANOJEV_SCRIPTS env var not set - start me via runner/engines_multi.py")
sys.path.insert(0, _scripts)

from predict_toy_decisions import DecisionPredictor  # noqa: E402

engine = DecisionPredictor(ckpt, precision="bf16", max_length=max_len)
print("READY", flush=True)


def predict_choice(state, instructions, criteria):
    body = {"states": [{"id": "q", "state": state,
                        "questions": {"q": {"type": "choice", "instructions": instructions,
                                            "criteria": criteria}}}]}
    result = engine.predict(body)
    ans = result["states"][0]["answers"]["q"]
    return ans


for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    req = json.loads(line)
    t0 = time.perf_counter()
    try:
        if req.get("mode") == "multi":
            questions = {qid: q for qid, q in req["questions"].items() if q.get("type") == "choice"}
            body = {"states": [{"id": qid, "state": req["state"], "questions": {qid: q}}
                               for qid, q in questions.items()]}
            result = engine.predict(body)
            answers = {}
            for st in result["states"]:
                qid = st["id"]
                ans = st["answers"][qid]
                answers[qid] = {"choice": ans.get("choice"),
                                "probabilities": ans.get("probabilities"),
                                "confidence": ans.get("confidence"),
                                "latency_ms": int((time.perf_counter() - t0) * 1000),
                                "raw": {"backend": "nanojev"}}
            print(json.dumps({"answers": answers, "usage": None}), flush=True)
        else:
            ans = predict_choice(req["state"], req["instructions"], req["criteria"])
            print(json.dumps({"choice": ans["choice"], "probabilities": ans["probabilities"],
                              "confidence": ans.get("confidence"),
                              "latency_ms": int((time.perf_counter() - t0) * 1000),
                              "raw": {"backend": "nanojev-decision-predictor", "precision": "bf16"}}), flush=True)
    except Exception as e:
        out = {"answers": {}, "error": f"{type(e).__name__}: {e}"} if req.get("mode") == "multi" else \
              {"choice": None, "probabilities": {}, "confidence": None,
               "latency_ms": int((time.perf_counter() - t0) * 1000),
               "raw": {"error": f"{type(e).__name__}: {e}"}}
        print(json.dumps(out), flush=True)
