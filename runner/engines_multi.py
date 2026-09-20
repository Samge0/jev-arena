"""Multi-question adapters (best-practice fan-out).

ask_multi(state, questions) -> {qid: {choice, probabilities, confidence, ...}}

- JevAPI.ask_multi: one POST /v1/systemone with ALL questions (native fan-out,
  zero latency cost per extra question, per official Parallel-Questions cookbook).
- NanoJev/Laya workers: extended line protocol {"mode": "multi", ...}; their
  predictors already accept multi-question bodies.

Single-question ask() is kept for compatibility (v1/v2 protocol).
"""
from __future__ import annotations

import json
import time

from engines import JevAPI as _JevAPIBase, NanoJevLocal as _NanoBase, LayaLocal as _LayaBase, normalize


class JevAPIMulti(_JevAPIBase):
    name = "jev"

    def ask_multi(self, state_text, questions):
        body = {"model": self.model, "state": state_text, "questions": questions}
        req = self._request(body)
        t0 = time.perf_counter()
        import urllib.request
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        latency = int((time.perf_counter() - t0) * 1000)
        self.calls += 1
        out = {}
        for qid, ans in payload["answers"].items():
            out[qid] = {
                "choice": ans.get("choice"),
                "probabilities": ans.get("probabilities"),
                "score": ans.get("score"),
                "noul": ans.get("noul"),
                "confidence": ans.get("confidence"),
                "latency_ms": latency,
                "raw": {"model": payload.get("model"), "qid": qid},
            }
        return out, payload.get("usage")

    def _request(self, body):
        import urllib.request
        return urllib.request.Request(
            "https://api.typesafe.ai/v1/systemone",
            data=json.dumps(body).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST")


class _WorkerMultiMixin:
    def ask_multi(self, state_text, questions):
        self._start()
        req = {"mode": "multi", "state": state_text, "questions": questions}
        self._proc.stdin.write(json.dumps(req) + "\n")
        self._proc.stdin.flush()
        line = self._proc.stdout.readline()
        if not line:
            raise RuntimeError(f"{self.name} worker died")
        payload = json.loads(line)
        self.calls += 1
        return payload.get("answers", {}), payload.get("usage")

    def ask(self, state_text, instructions, criteria):
        """Route single-question ask through the multi protocol."""
        answers, usage = self.ask_multi(
            state_text, {"q": {"type": "choice", "instructions": instructions, "criteria": criteria}})
        ans = answers.get("q") or {}
        return {
            "choice": ans.get("choice"),
            "probabilities": ans.get("probabilities") or {},
            "confidence": ans.get("confidence"),
            "latency_ms": ans.get("latency_ms"),
            "raw": ans.get("raw"),
        }


class NanoJevMulti(_WorkerMultiMixin, _NanoBase):
    name = "nanojev"


class LayaMulti(_WorkerMultiMixin, _LayaBase):
    name = "laya"
