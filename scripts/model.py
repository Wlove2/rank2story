#!/usr/bin/env python3
"""Safe project-local model configuration status and optional readiness test."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from model_config import load_settings, ROOT

def main(argv=None):
    parser = argparse.ArgumentParser(description="Check project-local .env model configuration")
    parser.add_argument("command", choices=["status", "check"])
    args = parser.parse_args(argv)
    try:
        env = load_settings()
    except (OSError, UnicodeError, ValueError) as exc:
        print(json.dumps({"ready": False, "error": str(exc).split(":")[0]}))
        return 2
    summary = {
        "model_endpoint_configured": bool(env.get("MODEL_BASE_URL")),
        "model_id_configured": bool(env.get("MODEL_ID")),
        "key_configured": bool(env.get("MODEL_API_KEY")),
        "config_file_present": (ROOT / ".env").is_file(),
    }
    if args.command == "status":
        print(json.dumps(summary))
        return 0
    if not summary["model_endpoint_configured"] or not summary["model_id_configured"]:
        print(json.dumps({"ready": False, "error": "MODEL_CONFIG_INCOMPLETE"}))
        return 2
    sys.path.insert(0, str(ROOT / "examples"))
    from check_model_endpoint import check_endpoint
    result = check_endpoint(base_url=env["MODEL_BASE_URL"], model=env["MODEL_ID"],
                            api_key=env.get("MODEL_API_KEY", ""))
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ready") else 2

if __name__ == "__main__":
    raise SystemExit(main())
