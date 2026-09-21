"""Engine adapters. Every adapter implements:

    ask(state_text, instructions, criteria) -> {"choice": str, "probabilities": {opt: float},
                                                "confidence": float|None, "latency_ms": int,
                                                "raw": anything}

Adapters must return probabilities that sum to ~1 across EXACTLY the criteria
keys; the runner normalizes defensively and logs contract violations.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request

TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"


class JevAPI:
    """TypeSafe Jev cloud API (the real System One model)."""

    name = "jev"
    title = "Jev"
    role = "TYPE SAFE · API"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.environ["TYPESAFE_API_KEY"]
        self.model = model or os.environ.get("TYPESAFE_MODEL", "jev-latest")
        self.calls = 0

    def ask(self, state_text, instructions, criteria):
        body = {
            "model": self.model,
            "state": state_text,
            "questions": {
                "q": {"type": "choice", "instructions": instructions, "criteria": criteria}
            },
        }
        req = urllib.request.Request(
            TYPESAFE_URL,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        latency = int((time.perf_counter() - t0) * 1000)
        self.calls += 1
        ans = payload["answers"]["q"]
        return {
            "choice": ans["choice"],
            "probabilities": ans["probabilities"],
            "confidence": ans.get("confidence"),
            "latency_ms": latency,
            "raw": {"model": payload.get("model"), "usage": payload.get("usage")},
        }


class NanoJevLocal:
    """NanoJev root checkpoint, bf16, loaded in its own venv via subprocess."""

    name = "nanojev"
    title = "NanoJev"
    role = "0.6B · LOCAL"

    def __init__(self):
        self._proc = None
        self.calls = 0

    def _start(self):
        if self._proc is not None:
            return
        script = r"F:\Space\PRO\test\jev-arena\runner\nanojev_worker.py"
        python = r"F:\Space\PRO\test\nanojev\.venv\Scripts\python.exe"
        ckpt = r"F:\Space\PRO\test\nanojev\checkpoints\NanoJev"
        import subprocess
        self._proc = subprocess.Popen(
            [python, script, ckpt, "1024"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", bufsize=1,
        )
        hello = self._proc.stdout.readline()
        if not hello.startswith("READY"):
            raise RuntimeError(f"nanojev worker failed: {hello[:400]}")

    def ask(self, state_text, instructions, criteria):
        self._start()
        req = {"state": state_text, "instructions": instructions, "criteria": criteria}
        self._proc.stdin.write(json.dumps(req) + "\n")
        self._proc.stdin.flush()
        line = self._proc.stdout.readline()
        if not line:
            raise RuntimeError("nanojev worker died")
        payload = json.loads(line)
        self.calls += 1
        return payload

    def close(self):
        if self._proc is not None:
            try:
                self._proc.stdin.close()
            except Exception:
                pass
            self._proc.terminate()
            self._proc = None


class LayaLocal:
    """laya (ModernBERT-421M) loaded in jevshoot's .venv-laya via subprocess."""

    name = "laya"
    title = "Laya"
    role = "421M · LOCAL"

    def __init__(self):
        self._proc = None
        self.calls = 0

    def _start(self):
        if self._proc is not None:
            return
        script = r"F:\Space\PRO\test\jev-arena\runner\laya_worker.py"
        python = r"F:\Space\PRO\test\jevshoot\.venv-laya\Scripts\python.exe"
        import subprocess
        env = dict(os.environ)
        env.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        env.setdefault("HF_HUB_OFFLINE", "1")
        self._proc = subprocess.Popen(
            [python, script],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", bufsize=1, env=env,
        )
        hello = self._proc.stdout.readline()
        if not hello.startswith("READY"):
            raise RuntimeError(f"laya worker failed: {hello[:400]}")

    def ask(self, state_text, instructions, criteria):
        self._start()
        req = {"state": state_text, "instructions": instructions, "criteria": criteria}
        self._proc.stdin.write(json.dumps(req) + "\n")
        self._proc.stdin.flush()
        line = self._proc.stdout.readline()
        if not line:
            raise RuntimeError("laya worker died")
        payload = json.loads(line)
        self.calls += 1
        return payload

    def close(self):
        if self._proc is not None:
            try:
                self._proc.stdin.close()
            except Exception:
                pass
            self._proc.terminate()
            self._proc = None


def normalize(answer: dict, criteria: dict) -> dict:
    """Defensive normalization to the TypeSafe contract. Returns a new dict."""
    probs = answer.get("probabilities") or {}
    keys = list(criteria.keys())
    # keep only known options, coerce to float, clamp to [0,1]
    cleaned = {}
    for k in keys:
        v = probs.get(k, 0.0)
        try:
            v = float(v)
        except (TypeError, ValueError):
            v = 0.0
        cleaned[k] = max(0.0, min(1.0, v))
    total = sum(cleaned.values())
    if total <= 0:
        # degenerate: uniform
        cleaned = {k: 1.0 / len(keys) for k in keys}
    else:
        cleaned = {k: v / total for k, v in cleaned.items()}
    choice = answer.get("choice")
    if choice not in cleaned:
        choice = max(cleaned, key=cleaned.get)
    # argmax consistency (contract requires choice == argmax)
    top = max(cleaned, key=cleaned.get)
    if cleaned[choice] < cleaned[top]:
        choice = top
    out = dict(answer)
    out["probabilities"] = {k: round(v, 4) for k, v in cleaned.items()}
    out["choice"] = choice
    out["normalized"] = True
    return out
