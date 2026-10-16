#!/usr/bin/env python3
"""Collect Qimao's ten public Web long-form rank channels."""

from __future__ import annotations

import argparse
import html
import hashlib
import json
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


BASE_URL = "https://www.qimao.com/paihang"
CHANNELS = {
    "hot": "hot",
    "new": "new",
    "finished": "over",
    "favorites": "collect",
    "updates": "update",
}
ITEM_RE = re.compile(r'<li class="rank-list-item".*?</li>', re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
BOOK_LINK_RE = re.compile(
    rf'<a[^>]+href={chr(34)}(?:https://www\.qimao\.com)?/shuku/(\d+)/?{chr(34)}[^>]*>(.*?)</a>',
    re.DOTALL | re.IGNORECASE,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean(fragment: str | None) -> str | None:
    if fragment is None:
        return None
    text = html.unescape(TAG_RE.sub(" ", fragment))
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def one(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, re.DOTALL)
    return clean(match.group(1)) if match else None


def parse_embedded_books(text: str, *, gender: str, rank_type: str, source_url: str) -> list[dict[str, Any]]:
    positions = [match.start() for match in re.finditer(r'\{book_id\s*:', text)]
    entries = []
    quote = chr(34)
    for index, start in enumerate(positions):
        end = positions[index + 1] if index + 1 < len(positions) else min(len(text), start + 12000)
        fragment = text[start:end]
        book_id = one(r'book_id\s*:\s*[^0-9]*(\d+)', fragment)
        title = one(fr'title\s*:\s*{quote}([^{quote}]+)', fragment)
        if not book_id or not title:
            continue
        entries.append({
            'gender': gender, 'rank_type': rank_type, 'rank': len(entries) + 1,
            'title': title, 'author': one(fr'author\s*:\s*{quote}([^{quote}]*)', fragment),
            'book_id': book_id, 'url': f'https://www.qimao.com/shuku/{book_id}/', 'source_url': source_url,
        })
    return entries


def parse_generic_book_links(text: str, *, gender: str, rank_type: str, source_url: str) -> list[dict[str, Any]]:
    entries = []
    seen = set()
    quote = chr(34)
    for match in BOOK_LINK_RE.finditer(text):
        book_id, raw_title = match.groups()
        title = clean(raw_title)
        if not title or book_id in seen or len(title) > 100:
            continue
        seen.add(book_id)
        fragment = text[max(0, match.start() - 1200): min(len(text), match.end() + 2500)]
        rank = one(fr'class={quote}[^{quote}]*rank[^{quote}]*{quote}[^>]*>\s*(\d+)', fragment)
        entries.append({
            'gender': gender, 'rank_type': rank_type,
            'rank': int(rank) if rank and rank.isdigit() else len(entries) + 1,
            'title': title, 'author': None, 'category': None, 'status': None,
            'word_count': None, 'heat': None, 'updated_at': None,
            'book_id': book_id, 'url': f'https://www.qimao.com/shuku/{book_id}/', 'source_url': source_url,
        })
    return entries


def fetch(url: str, timeout: int) -> tuple[str, dict[str, Any]]:
    captured_at = utc_now()
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": "Mozilla/5.0 AppleWebKit/537.36 Chrome/124 Safari/537.36",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace"), {
            "captured_at": captured_at,
            "http_status": response.status,
            "response_bytes": len(raw),
            "content_type": response.headers.get("Content-Type"),
        }


def parse_page(text: str, *, gender: str, rank_type: str, source_url: str) -> list[dict[str, Any]]:
    entries = []
    for item in ITEM_RE.findall(text):
        rank_text = one(r'class="rank-number[^"]*"[^>]*>(.*?)</span>', item)
        title = one(r'class="s-book-title"[^>]*>(.*?)</a>', item)
        book_match = re.search(r'href="https://www\.qimao\.com/shuku/(\d+)/"', item)
        info_match = re.search(r'<span class="s-book-info[^"]*"[^>]*>(.*?)</span>', item, re.DOTALL)
        info = info_match.group(1) if info_match else ""
        links = [clean(value) for value in re.findall(r"<a[^>]*>(.*?)</a>", info, re.DOTALL)]
        ems = [clean(value) for value in re.findall(r"<em[^>]*>(.*?)</em>", info, re.DOTALL)]
        ems = [value for value in ems if value]
        metric_num = one(r'class="rank-num"[^>]*>(.*?)</em>', item)
        metric_unit = one(r'class="rank-unit"[^>]*>(.*?)</em>', item)
        updated_at = one(r'class="s-book-update"[^>]*>.*?<em[^>]*>(.*?)</em>', item)
        if not title or not rank_text or not rank_text.isdigit():
            continue
        word_text = next((value for value in reversed(ems) if "字" in value), None)
        entries.append({
            "gender": gender,
            "rank_type": rank_type,
            "rank": int(rank_text),
            "title": title,
            "author": links[0] if links else None,
            "category": " / ".join(value for value in links[1:3] if value) or None,
            "status": next((value for value in ems if value in {"连载中", "已完结"}), None),
            "word_count": word_text,
            "heat": f"{metric_num or ''}{metric_unit or ''}".strip() or None,
            "updated_at": updated_at,
            "book_id": book_match.group(1) if book_match else None,
            "url": f"https://www.qimao.com/shuku/{book_match.group(1)}/" if book_match else None,
            "source_url": source_url,
        })
    if entries:
        return entries
    embedded = parse_embedded_books(text, gender=gender, rank_type=rank_type, source_url=source_url)
    if embedded:
        return embedded
    return parse_generic_book_links(text, gender=gender, rank_type=rank_type, source_url=source_url)


def fetch_and_parse_with_retries(
    *,
    gender: str,
    rank_type: str,
    source_url: str,
    timeout: int,
    attempts: int,
    retry_backoff: float,
    fetcher: Callable[[str, int], tuple[str, dict[str, Any]]] = fetch,
    sleeper: Callable[[float], None] = time.sleep,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    if retry_backoff < 0:
        raise ValueError("retry_backoff must be >= 0")
    errors = []
    for attempt in range(1, attempts + 1):
        try:
            page, transport = fetcher(source_url, timeout)
            parsed = parse_page(page, gender=gender, rank_type=rank_type, source_url=source_url)
            if not parsed:
                raise ValueError("no rank items parsed")
            transport = dict(transport)
            transport["attempt_count"] = attempt
            transport["retry_errors"] = errors
            return parsed, transport
        except Exception as exc:
            errors.append({"attempt": attempt, "error": f"{type(exc).__name__}: {exc}"})
            if attempt < attempts and retry_backoff:
                sleeper(retry_backoff * attempt)
    raise RuntimeError(json.dumps({"source_url": source_url, "attempts": errors}, ensure_ascii=False))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def collect_snapshots(output: Path, snapshot_dir: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    started_at = utc_now()
    entries = []
    channels = []
    for gender, gender_slug in (('male', 'boy'), ('female', 'girl')):
        for rank_type, rank_slug in CHANNELS.items():
            source_url = f'{BASE_URL}/{gender_slug}/{rank_slug}/date/'
            snapshot = snapshot_dir / f'{gender}_{rank_type}.html'
            if not snapshot.is_file() or snapshot.stat().st_size <= 0:
                channels.append({
                    'channel': f'{gender}/{rank_type}', 'status': 'failed', 'valid_entries': 0,
                    'source_url': source_url, 'error': 'CURRENT_RUN_BROWSER_SNAPSHOT_MISSING',
                })
                continue
            raw = snapshot.read_bytes()
            page = raw.decode('utf-8', errors='replace')
            parsed = parse_page(page, gender=gender, rank_type=rank_type, source_url=source_url)
            entries.extend(parsed)
            channels.append({
                'channel': f'{gender}/{rank_type}', 'status': 'success' if parsed else 'failed',
                'valid_entries': len(parsed), 'source_url': source_url,
                'snapshot_path': str(snapshot.resolve()), 'snapshot_bytes': len(raw),
                'snapshot_sha256': hashlib.sha256(raw).hexdigest(), 'captured_at': utc_now(),
            })
    successful = [item for item in channels if item['status'] == 'success']
    write_json(output / 'qimao_web_ranks.json', {
        'source': 'qimao_public_web_ranks', 'surface': 'public_web_browser_snapshot',
        'retrieved_at': utc_now(), 'entries': entries, 'channels': channels,
    })
    manifest = {
        'source': 'qimao_public_web_ranks', 'started_at': started_at, 'finished_at': utc_now(),
        'status': 'success' if len(successful) == 10 else 'degraded',
        'channel_count': len(channels), 'successful_channel_count': len(successful),
        'valid_entries': len(entries), 'data_file': 'qimao_web_ranks.json', 'channels': channels,
    }
    write_json(output / 'manifest.json', manifest)
    return manifest


def collect(
    output: Path,
    *,
    timeout: int = 30,
    delay: float = 0.2,
    attempts: int = 3,
    retry_backoff: float = 1.0,
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    started_at = utc_now()
    entries, channels = [], []
    for gender, gender_slug in (("male", "boy"), ("female", "girl")):
        for rank_type, rank_slug in CHANNELS.items():
            url = f"{BASE_URL}/{gender_slug}/{rank_slug}/date/"
            try:
                parsed, transport = fetch_and_parse_with_retries(
                    gender=gender,
                    rank_type=rank_type,
                    source_url=url,
                    timeout=timeout,
                    attempts=attempts,
                    retry_backoff=retry_backoff,
                )
                entries.extend(parsed)
                channels.append({
                    "channel": f"{gender}/{rank_type}",
                    "status": "success" if parsed else "empty",
                    "valid_entries": len(parsed),
                    "source_url": url,
                    **transport,
                })
            except Exception as exc:
                channels.append({
                    "channel": f"{gender}/{rank_type}",
                    "status": "failed",
                    "valid_entries": 0,
                    "source_url": url,
                    "error": f"{type(exc).__name__}: {exc}",
                    "captured_at": utc_now(),
                })
            if delay:
                time.sleep(delay)
    successful = [item for item in channels if item["status"] == "success"]
    write_json(output / "qimao_web_ranks.json", {
        "source": "qimao_public_web_ranks",
        "surface": "public_web",
        "retrieved_at": utc_now(),
        "entries": entries,
        "channels": channels,
    })
    manifest = {
        "source": "qimao_public_web_ranks",
        "started_at": started_at,
        "finished_at": utc_now(),
        "status": "success" if len(successful) == 10 else "degraded",
        "channel_count": len(channels),
        "successful_channel_count": len(successful),
        "valid_entries": len(entries),
        "data_file": "qimao_web_ranks.json",
        "channels": channels,
    }
    write_json(output / "manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--delay", type=float, default=0.2)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--retry-backoff", type=float, default=1.0)
    parser.add_argument('--snapshot-dir', type=Path)
    args = parser.parse_args()
    if args.snapshot_dir:
        manifest = collect_snapshots(args.output, args.snapshot_dir)
    else:
        manifest = collect(
            args.output,
            timeout=args.timeout,
            delay=args.delay,
            attempts=args.attempts,
            retry_backoff=args.retry_backoff,
        )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if manifest["status"] == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
