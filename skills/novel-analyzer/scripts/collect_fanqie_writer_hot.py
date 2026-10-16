#!/usr/bin/env python3
"""One-time Fanqie writer login and read-only Hot Stories snapshot.

The browser is visible so the workspace owner can complete sign-in. The
authenticated Playwright storage state is written outside the skill source by
default and must never be committed or attached to an issue.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.sync_api import Page
else:
    Page = Any


WRITER_URL = "https://fanqienovel.com/main/writer/inspiration"
USER_INFO_URL = "https://fanqienovel.com/api/user/info/v2"
HOT_STORIES_PATH = "/api/author/short_article/douyin_hot_list/v0/"
HOT_TYPES = {
    0: "all",
    1: "dark_horse_increase",
    2: "classic_hot",
}


def default_state_path() -> Path:
    user_profile = Path(os.environ.get("USERPROFILE", Path.home()))
    return user_profile / ".rank2story" / "private" / "fanqie-writer-state.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def fetch_json(page: Page, url: str) -> dict[str, Any]:
    result = page.evaluate(
        """async (url) => {
          const response = await fetch(url, {
            method: "GET",
            credentials: "include",
            headers: { "accept": "application/json, text/plain, */*" }
          });
          const text = await response.text();
          let body;
          try { body = JSON.parse(text); }
          catch { body = { parse_error: true, text: text.slice(0, 2000) }; }
          return {
            http_status: response.status,
            content_type: response.headers.get("content-type"),
            body
          };
        }""",
        url,
    )
    return result


def login_ok(page: Page) -> bool:
    try:
        result = fetch_json(page, USER_INFO_URL)
    except Exception:
        return False
    body = result.get("body")
    return isinstance(body, dict) and body.get("code") == 0


def wait_for_login(page: Page, timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if page.is_closed():
            raise RuntimeError("Browser window was closed before login completed.")
        if login_ok(page):
            return
        page.wait_for_timeout(2000)
    raise TimeoutError(f"Login did not complete within {timeout_seconds} seconds.")


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
            book_id = str(item.get("book_id") or "")
            identity = book_id or json.dumps(item, ensure_ascii=False, sort_keys=True)
            entry = merged.setdefault(
                identity,
                {
                    "book_id": book_id or None,
                    "book_name": item.get("book_name"),
                    "author": item.get("author"),
                    "content": item.get("content"),
                    "category": item.get("category"),
                    "word_number": item.get("word_number"),
                    "thumb_url": item.get("thumb_url"),
                    "video_url": item.get("video_url"),
                    "hot_types": [],
                },
            )
            if type_name not in entry["hot_types"]:
                entry["hot_types"].append(type_name)
    return list(merged.values())


def collect(page: Page, output_dir: Path) -> dict[str, Any]:
    raw_by_type: dict[str, dict[str, Any]] = {}
    statuses: dict[str, dict[str, Any]] = {}

    for hot_type, type_name in HOT_TYPES.items():
        url = f"https://fanqienovel.com{HOT_STORIES_PATH}?type={hot_type}"
        response = fetch_json(page, url)
        raw_by_type[type_name] = response
        body = response.get("body")
        data = body.get("data") if isinstance(body, dict) else None
        items = data.get("item_list") if isinstance(data, dict) else None
        statuses[type_name] = {
            "http_status": response.get("http_status"),
            "api_code": body.get("code") if isinstance(body, dict) else None,
            "message": body.get("message") if isinstance(body, dict) else None,
            "item_count": len(items) if isinstance(items, list) else 0,
            "total_count": data.get("total_count") if isinstance(data, dict) else None,
        }
        write_json(output_dir / f"{type_name}.json", response)

    normalized = normalize_items(raw_by_type)
    write_json(output_dir / "normalized.json", normalized)
    manifest = {
        "source": "fanqie_writer_hot_stories",
        "surface": "writer_web",
        "url": WRITER_URL,
        "captured_at": utc_now(),
        "authentication": "local_playwright_storage_state",
        "statuses": statuses,
        "unique_item_count": len(normalized),
        "raw_files": [f"{name}.json" for name in HOT_TYPES.values()],
        "normalized_file": "normalized.json",
    }
    write_json(output_dir / "manifest.json", manifest)
    return manifest


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit("Playwright is required to run this collector; install playwright in your project's Python environment.") from exc
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, default=default_state_path())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--login-timeout", type=int, default=900)
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    args.state.parent.mkdir(parents=True, exist_ok=True)
    state_arg = str(args.state) if args.state.exists() else None

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False, channel="chrome")
        context = browser.new_context(storage_state=state_arg)
        page = context.new_page()
        page.goto(WRITER_URL, wait_until="domcontentloaded", timeout=60_000)

        try:
            wait_for_login(page, args.login_timeout)
            context.storage_state(path=str(args.state))
            manifest = collect(page, args.output)
            print(json.dumps(manifest, ensure_ascii=False, indent=2))
        finally:
            browser.close()

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"fanqie collector failed: {exc}", file=sys.stderr)
        raise
