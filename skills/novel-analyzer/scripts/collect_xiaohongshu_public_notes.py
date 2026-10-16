#!/usr/bin/env python3
"""Conservative public Xiaohongshu note collector using the user's OpenCLI browser.

Search metadata is never treated as full text. Signed URLs are transient argv
only; serialized files contain canonical URLs without tokens or session data.
Image/video notes remain incomplete until ALL media has been substantively read.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from xiaohongshu_local_vision import read_public_gallery

SOURCE_ID = "xiaohongshu_novel_demand_shared"
DEFAULT_QUERIES = (
    "2026 网文 阅读 书荒",
    "2026 小说 避雷",
    "网文 榜单 推荐 2026",
    "网络小说 题材 趋势",
)
# The JS reads public DOM only. It does not access cookies, storage or hidden APIs.
NOTE_DOM_JS = """JSON.stringify((()=>{const n=document.querySelector('#noteContainer');const c=n?.querySelector('.note-content');const title=c?.querySelector('.title')?.innerText||document.title;const desc=c?.querySelector('.desc')?.innerText||'';const slides=[...(n?.querySelectorAll('.swiper-wrapper .swiper-slide:not(.swiper-slide-duplicate)')||[])];const videos=n?.querySelectorAll('video')?.length||0;return{url:location.origin+location.pathname,title,description:desc,note_present:!!n,images_total:slides.length,videos,description_length:desc.trim().length}})())"""


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), "", ""))


def opencli_argv() -> list[str]:
    executable = shutil.which("opencli")
    if not executable:
        raise RuntimeError("OPENCLI_NOT_INSTALLED")
    path = Path(executable)
    if os.name == "nt" and path.suffix.lower() in {".cmd", ".bat"}:
        # Never pass signed query strings through cmd.exe (ampersands & etc.).
        wrapper = path.read_text(encoding="utf-8", errors="replace")
        match = re.search(r'"([^"]+node\.exe)"\s+"([^"]+\.js)"', wrapper, re.I)
        if not match:
            raise RuntimeError("OPENCLI_WINDOWS_WRAPPER_UNSAFE_OR_UNKNOWN")
        return list(match.groups())
    return [executable]


def run_cli(prefix: list[str], args: list[str], timeout: int) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            [*prefix, *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            encoding="utf-8", errors="replace", timeout=timeout, check=False,
            shell=False,
        )
        return completed.returncode, completed.stdout
    except (subprocess.TimeoutExpired, OSError):
        return 124, ""


def numeric_likes(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    text = str(value or "").strip().replace(",", "")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([万千]?)", text)
    if not m:
        return None
    mult = {"": 1, "千": 1000, "万": 10000}[m.group(2)]
    return int(float(m.group(1)) * mult)


def classify(text: str) -> str | None:
    labels = (
        ("negative_or_avoidance", ("避雷", "劝退", "弃文", "不推荐", "避坑")),
        ("reader_demand_or_book_shortage", ("书荒", "求文", "求推荐", "求书")),
        ("curator_roundup", ("书单", "合集", "盘点", "推荐小说", "推文")),
        ("current_hotspot_or_rank_scan", ("榜单", "排名", "排行榜", "热门", "热度")),
    )
    for label, keys in labels:
        if any(k in text for k in keys):
            return label
    return None


def normalize_note(search: dict, page: dict) -> dict:
    url = canonical_url(str(page.get("url") or search.get("url") or ""))
    if urlsplit(url).hostname != "www.xiaohongshu.com":
        raise ValueError("NOTE_URL_NOT_XHS")
    desc = str(page.get("description") or "").strip()
    title = str(page.get("title") or search.get("title") or "").strip()
    author = str(search.get("author") or "").strip()
    published_at = str(search.get("published_at") or "").strip()
    images_total = int(page.get("images_total") or 0)
    videos = int(page.get("videos") or 0)
    image_reads = [
        image for image in page.get("vision_images") or []
        if isinstance(image, dict)
        and image.get("reading_status") == "machine_read_unreviewed"
        and isinstance(image.get("index"), int)
        and image.get("text")
    ]
    images_read = len({image["index"] for image in image_reads})
    media_transcript = "\n".join(
        f"[图片 {image['index'] + 1} / 本机视觉提取（未人工校对）] {image['text']}"
        for image in image_reads
    )
    likes = numeric_likes(search.get("likes"))
    signal = classify(title + "\n" + desc)
    # Media may be text embedded in images. DOM loads do NOT prove OCR/reading.
    # Never attest unprocessed image/video posts as complete.
    complete = (
        bool(page.get("note_present"))
        and len(desc) >= 100 and bool(author) and bool(published_at)
        and likes is not None and bool(signal)
        and images_read == images_total and videos == 0
    )
    entry = {
        "source_id": SOURCE_ID, "source_url": url, "url": url, "title": title,
        "author": author, "published_at": published_at,
        "engagement": {"likes": likes} if likes is not None else {},
        "full_text": (desc + "\n" + media_transcript).strip(),
        "content_complete": complete,
        "images_total": images_total, "images_read": images_read,
        "media_vision_records": image_reads,
        "media_reading_method": "local_vision_model_unreviewed" if image_reads else "none",
        "videos_total": videos,
        "primary_signal_type": signal, "signal_eligible": bool(complete),
        "source_relation": "independent",
        "incomplete_reason": (
            None if complete else
            "images_or_video_not_fully_read" if images_read < images_total or videos else
            "missing_public_text_author_timestamp_engagement_or_signal"
        ),
    }
    return entry


def collect(output: Path, queries: list[str], *, limit: int, max_notes: int, timeout: int, vision_model: str | None = None, vision_max_images: int | None = None) -> dict:
    prefix = opencli_argv()
    output.mkdir(parents=True, exist_ok=True)
    session = f"xhs-public-scan-{os.getpid()}"
    seen: dict[str, dict] = {}
    search_errors: list[str] = []
    for query in queries:
        code, response = run_cli(
            prefix, ["xiaohongshu", "search", query, "--limit", str(limit), "-f", "json"],
            timeout,
        )
        if code:
            search_errors.append("search_failed")
            continue
        try:
            rows = json.loads(response)
        except json.JSONDecodeError:
            search_errors.append("search_invalid_json")
            continue
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            url = str(row.get("url") or "")
            if "xsec_token=" not in url:
                continue
            key = canonical_url(url)
            if urlsplit(key).hostname == "www.xiaohongshu.com":
                seen.setdefault(key, row)
    captures = []
    try:
        for key, search in list(seen.items())[:max_notes]:
            # Never include signed URLs in logs, files, error text, or exceptions.
            code, _ = run_cli(prefix, ["browser", session, "open", str(search["url"])], timeout)
            if code:
                captures.append({
                    "source_url": key, "content_complete": False,
                    "incomplete_reason": "browser_open_failed",
                })
                continue
            code, response = run_cli(
                prefix, ["browser", session, "eval", NOTE_DOM_JS], timeout
            )
            if code:
                captures.append({
                    "source_url": key, "content_complete": False,
                    "incomplete_reason": "browser_dom_eval_failed",
                })
                continue
            try:
                note = json.loads(response)
                if vision_model and int(note.get("images_total") or 0) > 0:
                    note["vision_images"] = read_public_gallery(
                        prefix, session, run_cli, int(note["images_total"]),
                        model=vision_model, max_images=vision_max_images
                    )
                captures.append(normalize_note(search, note))
            except (ValueError, TypeError, json.JSONDecodeError):
                captures.append({
                    "source_url": key, "content_complete": False,
                    "incomplete_reason": "invalid_note_dom",
                })
    finally:
        run_cli(prefix, ["browser", session, "close"], min(timeout, 14))
    result = {
        "source_id": SOURCE_ID,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "discovery": {
            "discovered_unique_entries": len(seen),
            "screened_entries": len(captures),
        },
        "entries": captures,
        "limitations": [
            "No signed URLs or account tokens serialized",
            "Image/video notes remain incomplete until their media content is actually read",
            "Source completeness and profile quota must be independently audited",
        ],
        "search_error_kinds": search_errors,
    }
    (output / "public_notes.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--query", action="append", dest="queries")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--max-notes", type=int, default=6)
    parser.add_argument("--timeout", type=int, default=40)
    parser.add_argument("--vision-model", help="opt-in local Ollama multimodal model ID")
    parser.add_argument("--vision-max-images", type=int, help="diagnostic cap; capped notes stay incomplete")
    args = parser.parse_args()
    if not (1 <= args.limit <= 30 and 1 <= args.max_notes <= 60 and 8 <= args.timeout <= 180):
        parser.error("invalid live-capture bounds")
    if args.vision_max_images is not None and not 1 <= args.vision_max_images <= 40:
        parser.error("invalid live-capture bounds")
    result = collect(
        args.output, args.queries or list(DEFAULT_QUERIES),
        limit=args.limit, max_notes=args.max_notes, timeout=args.timeout,
        vision_model=args.vision_model, vision_max_images=args.vision_max_images,
    )
    print(json.dumps({
        "source_id": SOURCE_ID,
        "discovered": result["discovery"]["discovered_unique_entries"],
        "screened": result["discovery"]["screened_entries"],
        "full_content_eligible": sum(
            item.get("signal_eligible") is True for item in result["entries"]
        ),
        "output": str(args.output / "public_notes.json"),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
