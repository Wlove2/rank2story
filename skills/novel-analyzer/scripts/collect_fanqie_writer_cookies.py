#!/usr/bin/env python3
"""番茄作家端热门故事采集（cookies 直连 fallback）

当 playwright 登录超时（cookies 过期）时，用已有的 storage_state.json
cookies 直接 urllib 请求 API，无需打开浏览器登录。

保留脚本以便未来 playwright 登录失败时无需重写。
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


USER_INFO_URL = "https://fanqienovel.com/api/user/info/v2"
HOT_STORIES_PATH = "/api/author/short_article/douyin_hot_list/v0/"
HOT_TYPES = {0: "all", 1: "dark_horse_increase", 2: "classic_hot"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_cookies(state_path: Path) -> tuple[dict[str, str], str]:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    cookies = {c["name"]: c["value"] for c in state.get("cookies", [])}
    cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
    return cookies, cookie_str


def check_login(cookie_str: str) -> dict[str, Any]:
    req = urllib.request.Request(USER_INFO_URL, headers={
        "accept": "application/json, text/plain, */*",
        "cookie": cookie_str,
        "referer": "https://fanqienovel.com/main/writer/inspiration",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = json.loads(r.read().decode())
            return {"http_status": r.status, "code": body.get("code"), "logged_in": body.get("code") == 0}
    except Exception as e:
        return {"http_status": 0, "logged_in": False, "error": str(e)}


def normalize_items(raw_by_type: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for type_name, response in raw_by_type.items():
        body = response.get("body")
        data = body.get("data") if isinstance(body, dict) else None
        item_list = data.get("item_list") if isinstance(data, dict) else None
        if not isinstance(item_list, list):
            continue
        for item in item_list:
            if not isinstance(item, dict):
                continue
            bid = str(item.get("book_id") or "")
            identity = bid or json.dumps(item, ensure_ascii=False, sort_keys=True)
            entry = merged.setdefault(identity, {
                "book_id": bid or None,
                "book_name": item.get("book_name"),
                "author": item.get("author"),
                "content": item.get("content"),
                "category": item.get("category"),
                "word_number": item.get("word_number"),
                "thumb_url": item.get("thumb_url"),
                "video_url": item.get("video_url"),
                "hot_types": [],
            })
            if type_name not in entry["hot_types"]:
                entry["hot_types"].append(type_name)
    return list(merged.values())


def fetch_hot_list(cookies: dict[str, str], cookie_str: str, hot_type: int) -> dict[str, Any]:
    url = f"https://fanqienovel.com{HOT_STORIES_PATH}?{urllib.parse.urlencode({'type': hot_type})}"
    req = urllib.request.Request(url, headers={
        "accept": "application/json, text/plain, */*",
        "cookie": cookie_str,
        "referer": "https://fanqienovel.com/main/writer/inspiration",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return {"http_status": r.status, "body": json.loads(r.read().decode())}


def collect(state: Path, output: Path, *, authenticate_first: bool = True) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    cookies, cookie_str = load_cookies(state)

    login_check = check_login(cookie_str)
    if authenticate_first and not login_check.get("logged_in"):
        return {
            "source": "fanqie_writer_hot_stories",
            "status": "cookies_expired",
            "login_check": login_check,
            "recommendation": "Run scripts/collect_fanqie_writer_hot.py to refresh login state.",
        }

    raw_by_type: dict[str, dict[str, Any]] = {}
    statuses: dict[str, dict[str, Any]] = {}

    for hot_type, type_name in HOT_TYPES.items():
        result = fetch_hot_list(cookies, cookie_str, hot_type)
        raw_by_type[type_name] = result
        body = result["body"]
        data = body.get("data") if isinstance(body, dict) else None
        items = data.get("item_list") if isinstance(data, dict) else None
        statuses[type_name] = {
            "http_status": result["http_status"],
            "api_code": body.get("code") if isinstance(body, dict) else None,
            "message": body.get("message") if isinstance(body, dict) else None,
            "item_count": len(items) if isinstance(items, list) else 0,
        }
        write_json(output / f"{type_name}.json", body)

    normalized = normalize_items(raw_by_type)
    write_json(output / "normalized.json", normalized)

    manifest = {
        "source": "fanqie_writer_hot_stories",
        "surface": "writer_web",
        "url": "https://fanqienovel.com/main/writer/inspiration",
        "captured_at": utc_now(),
        "authentication": "cookies_from_storage_state_json",
        "login_check": login_check,
        "statuses": statuses,
        "unique_item_count": len(normalized),
        "raw_files": [f"{n}.json" for n in HOT_TYPES.values()],
        "normalized_file": "normalized.json",
    }
    write_json(output / "manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="番茄作家端热门故事 cookies fallback 采集")
    parser.add_argument("--state", type=Path, default=Path.home() / ".rank2story" / "private" / "fanqie-writer-state.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--skip-auth-check", action="store_true")
    args = parser.parse_args()
    if not args.state.exists():
        print(f"state file not found: {args.state}", file=sys.stderr)
        return 1
    manifest = collect(args.state, args.output, authenticate_first=not args.skip_auth_check)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    if manifest.get("status") == "cookies_expired":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
