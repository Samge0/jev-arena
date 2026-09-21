"""Multi-question engine adapters (best-practice fan-out) - v3+ link.

ask_multi(state, questions) -> ({qid: answer}, usage)

- JevAPIMulti: one POST <TYPESAFE_URL> with ALL questions (native fan-out,
  zero latency cost per extra question, per official Parallel-Questions cookbook).
- NanoJev/Laya workers: extended line protocol {"mode": "multi", ...}; their
  predictors already accept multi-question bodies.

All external coupling (API key/URL, foreign-repo venvs, checkpoints, model
ids, HF mirror) lives in config.py / .env - nothing machine-specific here.
Single-question ask() is kept for compatibility (smoke probes).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root -> config.py
import config  # noqa: E402


class JevAPIMulti:
    """TypeSafe Jev cloud API (the real System One model)."""

    name = "jev"

    def __init__(self):
        self.api_key = config.typesafe_api_key()
        self.model = config.TYPESAFE_MODEL
        self.calls = 0

    def ask_multi(self, state_text, questions):
        body = {"model": self.model, "state": state_text, "questions": questions}
        req = self._request(body)
        t0 = time.perf_counter()
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
        return urllib.request.Request(
            config.TYPESAFE_URL,
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


class NanoJevMulti(_WorkerMultiMixin):
    """NanoJev root checkpoint, bf16, loaded in its own venv via subprocess."""

    name = "nanojev"

    def __init__(self):
        self._proc = None
        self.calls = 0

    def _start(self):
        if self._proc is not None:
            return
        script = Path(__file__).resolve().with_name("nanojev_worker.py")
        env = dict(os.environ)
        env["NANOJEV_SCRIPTS"] = str(config.nanojev_scripts())
        self._proc = subprocess.Popen(
            [str(config.nanojev_python()), str(script), str(config.nanojev_ckpt()),
             str(config.NANOJEV_MAX_LENGTH)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", bufsize=1, env=env,
        )
        hello = self._proc.stdout.readline()
        if not hello.startswith("READY"):
            raise RuntimeError(f"nanojev worker failed: {hello[:400]}")

    def close(self):
        if self._proc is not None:
            try:
                self._proc.stdin.close()
            except Exception:
                pass
            self._proc.terminate()
            self._proc = None


class LayaMulti(_WorkerMultiMixin):
    """laya (ModernBERT-421M) loaded in jevshoot's .venv-laya via subprocess."""

    name = "laya"

    def __init__(self):
        self._proc = None
        self.calls = 0

    def _start(self):
        if self._proc is not None:
            return
        script = Path(__file__).resolve().with_name("laya_worker.py")
        env = dict(os.environ)
        env.setdefault("HF_ENDPOINT", config.HF_ENDPOINT)
        env.setdefault("HF_HUB_OFFLINE", config.HF_HUB_OFFLINE)
        env["LAYA_MODEL_ID"] = config.LAYA_MODEL_ID
        self._proc = subprocess.Popen(
            [str(config.laya_python()), str(script)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", bufsize=1, env=env,
        )
        hello = self._proc.stdout.readline()
        if not hello.startswith("READY"):
            raise RuntimeError(f"laya worker failed: {hello[:400]}")

    def close(self):
        if self._proc is not None:
            try:
                self._proc.stdin.close()
            except Exception:
                pass
            self._proc.terminate()
            self._proc = None
