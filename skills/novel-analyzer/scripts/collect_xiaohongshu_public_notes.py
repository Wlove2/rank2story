#!/usr/bin/env python3
"""Conservative public Xiaohongshu note collector using the user's OpenCLI browser.

Search metadata is never treated as full text. Signed URLs are transient argv
only; serialized files contain canonical URLs without tokens or session data.
Image/video notes remain incomplete until ALL media has been substantively read.
"""
from __future__ import annotations

import argparse
import json
import hashlib
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from xiaohongshu_local_vision import read_public_gallery, stage_public_gallery

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


def resolve_windows_opencli_shim(path: Path) -> list[str]:
    """Resolve known Node.js .cmd shims without passing signed URLs through cmd.exe."""
    wrapper = path.read_text(encoding="utf-8", errors="replace")
    direct = re.search(r'"([^"]+node\.exe)"\s+"([^"]+\.js)"', wrapper, re.I)
    if direct:
        return list(direct.groups())

    # npm's cmd-shim uses %_prog% and a %dp0%-relative JavaScript entrypoint.
    npm = re.search(
        r'"%_prog%"\s+"%(?:~)?dp0%[\\/]+([^"]+\.js)"\s+%\*',
        wrapper, re.I,
    )
    if npm:
        script = (path.parent / npm.group(1).replace("\\", "/")).resolve()
        nearby_node = path.parent / "node.exe"
        node = (str(nearby_node) if nearby_node.is_file()
                else shutil.which("node.exe") or shutil.which("node"))
        if node and script.is_file():
            return [node, str(script)]
    raise RuntimeError("OPENCLI_WINDOWS_WRAPPER_UNSAFE_OR_UNKNOWN")


def opencli_argv() -> list[str]:
    executable = shutil.which("opencli")
    if not executable:
        raise RuntimeError("OPENCLI_NOT_INSTALLED")
    path = Path(executable)
    if os.name == "nt" and path.suffix.lower() in {".cmd", ".bat"}:
        return resolve_windows_opencli_shim(path)
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



def save_json(path: Path, data: dict) -> None:
    """Atomic, incremental checkpoint (also usable on Windows)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        for attempt in range(5):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.2 * (attempt + 1))
    finally:
        tmp.unlink(missing_ok=True)


def import_agent_vision(output: Path) -> dict:
    """Check Agent descriptions against saved image bytes before counting reads."""
    data_file, queue_file = output / "public_notes.json", output / "agent_vision_queue.json"
    if not data_file.is_file() or not queue_file.is_file():
        raise ValueError("AGENT_VISION_SCAN_AND_QUEUE_REQUIRED")
    data = json.loads(data_file.read_text(encoding="utf-8"))
    queue = json.loads(queue_file.read_text(encoding="utf-8"))
    if data.get("source_id") != SOURCE_ID or queue.get("source_id") != SOURCE_ID:
        raise ValueError("AGENT_VISION_SOURCE_MISMATCH")
    by_source: dict[str, list[dict]] = {}
    for item in queue.get("images", []):
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        source = str(item.get("source_url") or "")
        index = item.get("index")
        digest = str(item.get("image_sha256") or "")
        path = str(item.get("image_path") or "")
        if (canonical_url(source) != source or urlsplit(source).hostname != "www.xiaohongshu.com"
                or type(index) is not int or index < 0
                or not re.fullmatch("[0-9a-f]{64}", digest)
                or not re.fullmatch(r"media/" + digest + r"\.(jpg|png|webp)", path)
                or len(text) < 15):
            raise ValueError("AGENT_VISION_INVALID_READ_RECORD")
        image_file = (output / path).resolve()
        if not image_file.is_relative_to(output.resolve()) or not image_file.is_file():
            raise ValueError("AGENT_VISION_IMAGE_MISSING")
        if hashlib.sha256(image_file.read_bytes()).hexdigest() != digest:
            raise ValueError("AGENT_VISION_IMAGE_HASH_MISMATCH")
        by_source.setdefault(source, []).append({
            "index": index, "image_sha256": digest, "model": "agent_native_vision",
            "text": text, "reading_status": "agent_read_unreviewed",
        })
    sources = {entry.get("source_url") for entry in data.get("entries", [])}
    if not set(by_source).issubset(sources):
        raise ValueError("AGENT_VISION_SOURCE_NOT_CAPTURED")
    queued_sources = {str(item.get("source_url") or "") for item in queue.get("images", [])}
    for entry in data.get("entries", []):
        total = entry.get("images_total")
        if entry.get("source_url") not in queued_sources or type(total) is not int or total < 1:
            continue
        reads = by_source.get(entry.get("source_url"), [])
        indexes = [row["index"] for row in reads]
        if len(set(indexes)) != len(indexes) or any(i >= total for i in indexes):
            raise ValueError("AGENT_VISION_DUPLICATE_OR_OUT_OF_RANGE")
        entry["media_vision_records"] = sorted(reads, key=lambda r: r["index"])
        entry["images_read"] = len(reads)
        entry["media_reading_method"] = "agent_native_vision_unreviewed" if reads else "none"
        original_text = str(entry.get("full_text") or "").split("\n[图片 ", 1)[0].strip()
        transcript = "\n".join(
            f"[图片 {r['index'] + 1} / Agent 实际读取（未人工校对）] {r['text']}"
            for r in entry["media_vision_records"]
        )
        entry["full_text"] = (original_text + "\n" + transcript).strip()
        complete = (
            len(reads) == total and len(original_text) >= 100
            and bool(entry.get("title")) and bool(entry.get("author"))
            and bool(entry.get("published_at")) and bool(entry.get("engagement"))
            and bool(entry.get("primary_signal_type")) and entry.get("videos_total") == 0
        )
        entry["content_complete"] = complete
        entry["signal_eligible"] = complete
        entry["incomplete_reason"] = None if complete else "images_or_video_not_fully_read"
    save_json(data_file, data)
    return data


def collect(output: Path, queries: list[str], *, limit: int, max_notes: int, timeout: int, vision_model: str | None = None, vision_max_images: int | None = None, resume: bool = False, agent_vision: bool = False, max_gallery_images: int | None = None) -> dict:
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
    output_file = output / "public_notes.json"
    queue_file = output / "agent_vision_queue.json"
    previous = (
        json.loads(output_file.read_text(encoding="utf-8"))
        if resume and output_file.is_file() else None
    )
    if previous and previous.get("source_id") != SOURCE_ID:
        raise ValueError("XHS_RESUME_SOURCE_MISMATCH")
    captures = list(previous.get("entries", [])) if previous else []
    processed = {
        urlsplit(str(item.get("source_url") or "")).path.rsplit("/", 1)[-1]
        for item in captures if item.get("source_url")
    }
    queue = (
        json.loads(queue_file.read_text(encoding="utf-8"))
        if resume and queue_file.is_file() else {"source_id": SOURCE_ID, "images": []}
    )
    discovered = max(len(seen), int((previous or {}).get("discovery", {}).get("discovered_unique_entries") or 0))
    screened_before = int((previous or {}).get("discovery", {}).get("screened_entries") or 0)
    newly_screened = 0

    def checkpoint() -> dict:
        result = {
            "source_id": SOURCE_ID,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "discovery": {
                "discovered_unique_entries": discovered,
                "screened_entries": max(screened_before + newly_screened, len(processed)),
            },
            "entries": captures,
            "limitations": [
                "No signed URLs or account tokens serialized",
                "All images must actually be read before counting a complete post",
                "Source coverage must pass the official auditor",
            ],
            "search_error_kinds": search_errors,
        }
        save_json(output_file, result)
        if agent_vision:
            save_json(queue_file, queue)
        return result

    # Reader requests first, then other market signals; stop after max_notes
    # newly screened notes rather than spending the budget on old records.
    ordered = sorted(seen.items(), key=lambda pair: (
        0 if any(word in str(pair[1].get("title") or "")
                 for word in ("书荒", "求文", "求书", "求推荐", "求推")) else 1
    ))
    result = None
    try:
        for key, search in ordered:
            if urlsplit(key).path.rsplit("/", 1)[-1] in processed or newly_screened >= max_notes:
                continue
            newly_screened += 1
            processed.add(urlsplit(key).path.rsplit("/", 1)[-1])
            code, _ = run_cli(prefix, ["browser", session, "open", str(search["url"])], timeout)
            if code:
                captures.append({
                    "source_url": key, "content_complete": False,
                    "incomplete_reason": "browser_open_failed",
                })
                result = checkpoint()
                continue
            code, response = run_cli(prefix, ["browser", session, "eval", NOTE_DOM_JS], timeout)
            if code:
                captures.append({
                    "source_url": key, "content_complete": False,
                    "incomplete_reason": "browser_dom_eval_failed",
                })
                result = checkpoint()
                continue
            try:
                note = json.loads(response)
                count = int(note.get("images_total") or 0)
                description = str(note.get("description") or "").strip()
                heading = str(note.get("title") or search.get("title") or "")
                suitable = (
                    bool(note.get("note_present")) and len(description) >= 100
                    and bool(search.get("author")) and bool(search.get("published_at"))
                    and numeric_likes(search.get("likes")) is not None
                    and classify(heading + "\n" + description) is not None
                    and int(note.get("videos") or 0) == 0
                    and (max_gallery_images is None or count <= max_gallery_images)
                )
                if not suitable:
                    captures.append({
                        "source_url": key, "content_complete": False,
                        "incomplete_reason": "unsuitable_text_or_gallery",
                    })
                else:
                    pending = []
                    if agent_vision and count:
                        pending = stage_public_gallery(prefix, session, run_cli, count, output / "media")
                    elif vision_model and count:
                        note["vision_images"] = read_public_gallery(
                            prefix, session, run_cli, count,
                            model=vision_model, max_images=vision_max_images
                        )
                    entry = normalize_note(search, note)
                    for image in pending:
                        image["source_url"] = entry["source_url"]
                    queue["images"].extend(pending)
                    captures.append(entry)
            except (ValueError, TypeError, json.JSONDecodeError):
                captures.append({
                    "source_url": key, "content_complete": False,
                    "incomplete_reason": "invalid_note_dom",
                })
            result = checkpoint()
    finally:
        run_cli(prefix, ["browser", session, "close"], min(timeout, 14))
        result = checkpoint()
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
    parser.add_argument("--resume", action="store_true", help="continue a saved scan without recounting URLs")
    parser.add_argument("--agent-vision", action="store_true", help="save images for Agent-native visual reading")
    parser.add_argument("--apply-agent-vision", action="store_true", help="validate Agent image reading records against saved SHA-256")
    parser.add_argument("--max-gallery-images", type=int, help="skip larger galleries as incomplete")
    args = parser.parse_args()
    if not (1 <= args.limit <= 30 and 1 <= args.max_notes <= 60 and 8 <= args.timeout <= 180):
        parser.error("invalid live-capture bounds")
    if args.vision_max_images is not None and not 1 <= args.vision_max_images <= 40:
        parser.error("invalid live-capture bounds")
    if args.max_gallery_images is not None and not 1 <= args.max_gallery_images <= 40:
        parser.error("invalid gallery bound")
    if args.agent_vision and args.vision_model:
        parser.error("choose Agent-native vision or Ollama, not both")
    if args.apply_agent_vision:
        result = import_agent_vision(args.output)
    else:
        result = collect(
            args.output, args.queries or list(DEFAULT_QUERIES),
            limit=args.limit, max_notes=args.max_notes, timeout=args.timeout,
            vision_model=args.vision_model, vision_max_images=args.vision_max_images,
            resume=args.resume, agent_vision=args.agent_vision,
            max_gallery_images=args.max_gallery_images,
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
