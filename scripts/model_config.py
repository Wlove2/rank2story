"""Read optional project-local model settings without disclosing credentials.

Priority: inherited process environment > untracked project-root .env file.
No shell interpolation, subprocess, external dependencies, or secret logging.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEYS = ("MODEL_BASE_URL", "MODEL_ID", "MODEL_API_KEY")

def load_settings(path: Path | None = None, *, environ: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if environ is None else environ)
    local = ROOT / ".env" if path is None else path
    if local.is_file():
        for line_number, line in enumerate(local.read_text(encoding="utf-8-sig").splitlines(), 1):
            text = line.strip()
            if not text or text.startswith("#"):
                continue
            if "=" not in text:
                raise ValueError(f"MODEL_ENV_INVALID_LINE:{line_number}")
            key, value = text.split("=", 1)
            key = key.strip()
            if key not in KEYS:
                raise ValueError(f"MODEL_ENV_UNKNOWN_KEY:{line_number}")
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            if not value or value in {"your-model-id", "https://your-endpoint.example/v1"}:
                continue
            env.setdefault(key, value)
    return env

def model_args(argv: list[str], env: dict[str, str]) -> list[str]:
    """Supply missing flags for one execute command, never pass the key as argv."""
    rest = list(argv)
    flags = {arg.split("=", 1)[0] for arg in rest if arg.startswith("--")}
    if "--base-url" not in flags:
        base = env.get("MODEL_BASE_URL", "").strip()
        if not base:
            raise ValueError("MODEL_BASE_URL_MISSING: configure .env or --base-url")
        rest.extend(["--base-url", base])
    if "--model" not in flags:
        model = env.get("MODEL_ID", "").strip()
        if not model:
            raise ValueError("MODEL_ID_MISSING: configure .env or --model")
        rest.extend(["--model", model])
    if "--api-key-env" not in flags and env.get("MODEL_API_KEY", ""):
        rest.extend(["--api-key-env", "MODEL_API_KEY"])
    return rest
