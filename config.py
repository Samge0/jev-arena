"""Central configuration for jev-arena (single source of truth).

Loads .env from the repo root at import time. Machine-specific external
dependencies (foreign repo locations) have NO defaults and are validated
lazily by the getters below, so scripts that don't need an engine
(replay_check, verify_site) can still import this module.

Required in .env (see .env.example):
  TYPESAFE_API_KEY   cloud engine auth
  NANOJEV_HOME       clone of NanoJev (provides .venv, checkpoints/, NanoJev/scripts)
  JEVSHOOT_HOME      repo containing .venv-laya (laya package installed)

Optional (defaults): TYPESAFE_MODEL, TYPESAFE_URL, NANOJEV_CKPT,
NANOJEV_SCRIPTS, NANOJEV_MAX_LENGTH, LAYA_MODEL_ID, ARENA_PORT, HF_ENDPOINT,
HF_HUB_OFFLINE.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")

_WIN = os.name == "nt"


def _require(var: str, why: str) -> str:
    val = os.environ.get(var, "").strip()
    if not val:
        raise RuntimeError(
            f"Config error: {var} is not set ({why}).\n"
            f"Add it to {BASE / '.env'} - copy .env.example to get started."
        )
    return val


def _py(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if _WIN else "bin/python")


# --- cloud engine: TypeSafe Jev -------------------------------------------------
TYPESAFE_MODEL = os.environ.get("TYPESAFE_MODEL", "jev-latest")
TYPESAFE_URL = os.environ.get("TYPESAFE_URL", "https://api.typesafe.ai/v1/systemone")


def typesafe_api_key() -> str:
    return _require("TYPESAFE_API_KEY", "Bearer key for the Jev cloud API")


# --- local engine: nanojev repo (REQUIRED, no default) ---------------------------
def nanojev_home() -> Path:
    return Path(_require(
        "NANOJEV_HOME",
        "local clone of https://github.com/TianyuCodings/NanoJev with .venv "
        "created and checkpoints/NanoJev present"))


def nanojev_python() -> Path:
    py = _py(nanojev_home() / ".venv")
    if not py.exists():
        raise RuntimeError(
            f"Config error: {py} does not exist - create the nanojev venv, "
            f"or point NANOJEV_HOME at the right repo.")
    return py


def nanojev_ckpt() -> Path:
    home = nanojev_home()
    ckpt = Path(os.environ.get("NANOJEV_CKPT", home / "checkpoints" / "NanoJev"))
    if not ckpt.is_dir():
        raise RuntimeError(
            f"Config error: nanojev checkpoint dir {ckpt} does not exist - "
            f"download it or set NANOJEV_CKPT.")
    return ckpt


def nanojev_scripts() -> Path:
    home = nanojev_home()
    scripts = Path(os.environ.get("NANOJEV_SCRIPTS", home / "NanoJev" / "scripts"))
    if not scripts.is_dir():
        raise RuntimeError(
            f"Config error: nanojev scripts dir {scripts} does not exist - "
            f"set NANOJEV_SCRIPTS to the NanoJev/scripts directory.")
    return scripts


NANOJEV_MAX_LENGTH = int(os.environ.get("NANOJEV_MAX_LENGTH", "1024"))


# --- local engine: laya venv (REQUIRED, no default) ------------------------------
def laya_python() -> Path:
    home = Path(_require(
        "JEVSHOOT_HOME",
        "repo containing .venv-laya with the laya package installed"))
    py = _py(home / ".venv-laya")
    if not py.exists():
        raise RuntimeError(
            f"Config error: {py} does not exist - create .venv-laya, "
            f"or point JEVSHOOT_HOME at the right repo.")
    return py


LAYA_MODEL_ID = os.environ.get("LAYA_MODEL_ID", "convaiinnovations/laya")


# --- replay site / tooling ---------------------------------------------------------
ARENA_PORT = int(os.environ.get("ARENA_PORT", "8775"))
ARENA_URL = os.environ.get("ARENA_URL", f"http://127.0.0.1:{ARENA_PORT}/")

HF_ENDPOINT = os.environ.get("HF_ENDPOINT", "https://hf-mirror.com")
HF_HUB_OFFLINE = os.environ.get("HF_HUB_OFFLINE", "1")

# --- internal output dirs (derived by design, not configurable) --------------------
WEB_DIR = BASE / "web"
SHOTS = BASE / "shots"
DOCS_MEDIA = BASE / "docs-media"
