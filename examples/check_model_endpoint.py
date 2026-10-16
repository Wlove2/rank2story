#!/usr/bin/env python3
"""Minimal OpenAI-compatible chat readiness check, with no secret or output logging.

Accepts either a user-managed direct endpoint or a localhost gateway.
Only a nonempty assistant content confirms generation readiness; HTTP 200
alone, model catalog listings, or reasoning-only truncation do not.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit


def check_endpoint(
    *, base_url: str, model: str, api_key: str = "", timeout: int = 90,
    max_tokens: int = 1024, bypass_proxy: bool = False,
    opener=None,
) -> dict:
    url = base_url.rstrip("/")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("MODEL_BASE_URL_INVALID")
    if not url.endswith("/chat/completions"):
        url += "/chat/completions"
    if not model.strip():
        raise ValueError("MODEL_NAME_MISSING")
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": "Return a short, nonempty assistant response."},
            {"role": "user", "content": "Reply with the word READY only."},
        ],
        "max_tokens": max_tokens,
        "stream": False,
    }, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    if opener is None:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}) if bypass_proxy else urllib.request.ProxyHandler()
        )
    started = time.monotonic()
    try:
        with opener.open(request, timeout=timeout) as response:
            data = json.load(response)
            choices = data.get("choices") or []
            first = choices[0] if choices else {}
            message = first.get("message") or {}
            content = message.get("content")
            if isinstance(content, list):
                content = "".join(
                    str(part.get("text", "")) if isinstance(part, dict) else str(part)
                    for part in content
                )
            content = content if isinstance(content, str) else ""
            reasoning = message.get("reasoning_content") or ""
            result = {
                "ready": bool(content.strip()),
                "http_status": response.status,
                "model_returned": str(data.get("model") or ""),
                "content_chars": len(content.strip()),
                "reasoning_chars": len(reasoning) if isinstance(reasoning, str) else 0,
                "finish_reason": first.get("finish_reason"),
            }
    except urllib.error.HTTPError as exc:
        result = {"ready": False, "http_status": exc.code, "error": "HTTP_ERROR"}
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {"ready": False, "http_status": None, "error": type(exc).__name__}
    result["elapsed_seconds"] = round(time.monotonic() - started, 2)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--api-key-env", default="")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--bypass-proxy", action="store_true")
    args = parser.parse_args(argv)
    if args.timeout < 1 or args.max_tokens < 1:
        parser.error("timeout and max-tokens must be positive")
    if args.api_key_env and not os.environ.get(args.api_key_env):
        print(json.dumps({"ready": False, "error": "MODEL_API_KEY_ENV_MISSING"}))
        return 2
    result = check_endpoint(
        base_url=args.base_url, model=args.model,
        api_key=os.environ.get(args.api_key_env, "") if args.api_key_env else "",
        timeout=args.timeout, max_tokens=args.max_tokens,
        bypass_proxy=args.bypass_proxy,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
