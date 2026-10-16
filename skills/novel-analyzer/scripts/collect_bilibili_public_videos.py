#!/usr/bin/env python3
"""Read-only Bilibili public-search → video-page → official caption-track collector.

This does not bypass logged-in/private resources. Empty, partial, unsupported
or nonexistent captions remain incomplete and cannot count as market evidence.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from collect_xiaohongshu_public_notes import opencli_argv, run_cli, classify

SOURCE_ID = "bilibili_novel_demand_shared"
DEFAULT_QUERIES = (
    "网文 2026 推荐",
    "网络小说 2026 榜单",
    "小说 书荒 推荐 2026",
    "2026 网文 避雷",
)
VIDEO_PATTERN = re.compile(r"(BV[A-Za-z0-9]{10})")

SEARCH_DOM_JS = """JSON.stringify({
url:location.origin+location.pathname,
videos:[...document.querySelectorAll('.bili-video-card a[href]')]
.filter(a=>a.href.includes('/video/BV')&&!a.href.includes('cm.bilibili.com'))
.map(a=>({url:a.href,title:a.getAttribute('title')||a.textContent.trim()})).slice(0,80)
})"""
# Subtitles are pulled only from player-advertised public, provider-owned URLs.
# Video identifiers and metadata come from the real opened page, not a model.
VIDEO_DOM_JS = """(async()=>{const d=window.__INITIAL_STATE__?.videoData;
if(!d)return JSON.stringify({error:'NO_PUBLIC_VIDEO_DATA'});
const out={url:location.origin+location.pathname,bvid:d.bvid,title:d.title,
author:d.owner?.name||'',author_id:d.owner?.mid||null,pubdate:d.pubdate,
duration:d.duration,engagement:{views:d.stat?.view,likes:d.stat?.like,
comments:d.stat?.reply,shares:d.stat?.share,favorites:d.stat?.favorite},
subtitles:[]};
const resp=await fetch('https://api.bilibili.com/x/player/v2?aid='+d.aid+'&cid='+d.cid,
{credentials:'include'});const meta=await resp.json();
out.player_status=resp.status;out.player_code=meta.code;out.subtitle_advertised=(meta.data?.subtitle?.subtitles||[]).length;out.caption_errors=[];
for(const track of (meta.data?.subtitle?.subtitles||[]).slice(0,5)){
try{let u=track.subtitle_url;if(u.startsWith('//'))u='https:'+u;
const host=new URL(u).hostname;
if(!['hdslb.com','bilibili.com'].some(d=>host===d||host.endsWith('.'+d)))continue;
const response=await fetch(u,{credentials:'omit'});
if(!response.ok)continue;const body=await response.json();
const rows=(body.body||[]).filter(x=>typeof x.content==='string'
&&Number.isFinite(x.from)&&Number.isFinite(x.to));
if(!rows.length)continue;
out.subtitles.push({lang:track.lan||'',track_id:track.id,
segments:rows.length,first_start:Math.min(...rows.map(x=>x.from)),
last_end:Math.max(...rows.map(x=>x.to)),content:rows.map(x=>x.content).join('\\n')});
}catch(e){out.caption_errors.push(e?.name||'caption_fetch_error')}}
return JSON.stringify(out)})()"""


def normalize_video(item: dict) -> dict:
    bvid = str(item.get("bvid") or "")
    if not VIDEO_PATTERN.fullmatch(bvid):
        raise ValueError("INVALID_BVID")
    url = f"https://www.bilibili.com/video/{bvid}"
    title = str(item.get("title") or "").strip()
    author = str(item.get("author") or "").strip()
    duration = float(item.get("duration") or 0)
    tracks = [
        x for x in item.get("subtitles") or []
        if isinstance(x, dict) and isinstance(x.get("content"), str)
    ]
    # Choose the widest time-span caption track, not a single short teaser.
    best = max(
        tracks,
        key=lambda x: (float(x.get("last_end") or 0), len(x["content"])),
        default={},
    )
    content = str(best.get("content") or "").strip()
    first = float(best.get("first_start") or 0)
    last = float(best.get("last_end") or 0)
    coverage = last / duration if duration > 0 else 0
    signal = classify(title + "\n" + content[:1600])
    pubdate = item.get("pubdate")
    try:
        published_at = datetime.fromtimestamp(
            int(pubdate), tz=timezone.utc
        ).isoformat()
    except (ValueError, TypeError, OverflowError, OSError):
        published_at = ""
    engagement = {
        name: value
        for name, value in (item.get("engagement") or {}).items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }
    complete = (
        len(content) >= 200 and duration > 0
        and 0 <= first <= 45 and 0.92 <= coverage <= 1.05
        and bool(title) and bool(author) and bool(published_at)
        and bool(engagement) and signal is not None
        and item.get("player_code") == 0
    )
    return {
        "source_id": SOURCE_ID, "source_url": url, "url": url, "bvid": bvid,
        "title": title, "author": author, "author_id": item.get("author_id"),
        "published_at": published_at, "engagement": engagement,
        "full_text": content, "content_complete": complete,
        "subtitle_lang": best.get("lang"), "subtitle_segments": best.get("segments"),
        "subtitle_first_second": first, "subtitle_last_second": last,
        "video_duration_seconds": duration,
        "subtitle_end_coverage_ratio": round(coverage, 4),
        "primary_signal_type": signal, "signal_eligible": bool(complete),
        "source_relation": "independent",
        "incomplete_reason": None if complete else "missing_or_partial_usable_public_caption",
    }


def interleave_queries(groups: list[list[str]], limit: int) -> list[str]:
    """Prevent one large query's ranking from consuming every capture slot."""
    ordered: list[str] = []
    seen: set[str] = set()
    for position in range(max(map(len, groups), default=0)):
        for group in groups:
            if position < len(group) and group[position] not in seen:
                seen.add(group[position])
                ordered.append(group[position])
                if len(ordered) >= limit:
                    return ordered
    return ordered


def previously_screened(output: Path) -> tuple[list[dict], int]:
    """Resume only real saved records, never invent discovered IDs."""
    path = output / "public_videos.json"
    if not path.is_file():
        return [], 0
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("source_id") != SOURCE_ID:
        raise ValueError("BILIBILI_RESUME_SOURCE_MISMATCH")
    records = []
    seen = set()
    for record in payload.get("entries") or []:
        match = VIDEO_PATTERN.search(str(record.get("source_url") or ""))
        if match and match.group(1) not in seen:
            seen.add(match.group(1))
            records.append(record)
    lower_bound = int((payload.get("discovery") or {}).get("discovered_unique_entries") or 0)
    return records, lower_bound


def collect(output: Path, queries: list[str], *, max_notes: int, timeout: int, resume: bool = False) -> dict:
    prefix = opencli_argv()
    output.mkdir(parents=True, exist_ok=True)
    session = f"bili-public-scan-{int(time.time())}"
    previous, previous_discovery = previously_screened(output) if resume else ([], 0)
    previously_seen = {
        match.group(1)
        for row in previous
        if (match := VIDEO_PATTERN.search(str(row.get("source_url") or "")))
    }
    discovered: dict[str, dict] = {}
    query_groups: list[list[str]] = []
    errors: list[str] = []
    captures: list[dict] = []
    try:
        for query in queries:
            url = "https://search.bilibili.com/all?keyword=" + quote(query)
            status, _ = run_cli(prefix, ["browser", session, "open", url], timeout)
            if status:
                errors.append("search_page_unavailable")
                continue
            status, raw = run_cli(
                prefix, ["browser", session, "eval", SEARCH_DOM_JS], timeout
            )
            if status:
                errors.append("search_dom_unavailable")
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                errors.append("search_json_unparseable")
                continue
            if data.get("url") != "https://search.bilibili.com/all":
                errors.append("search_redirected")
                continue
            group: list[str] = []
            for item in data.get("videos") or []:
                match = VIDEO_PATTERN.search(str(item.get("url") or ""))
                if match:
                    discovered.setdefault(match.group(1), item)
                    if match.group(1) not in group:
                        group.append(match.group(1))
            query_groups.append(group)
        pending = [
            bvid for bvid in interleave_queries(query_groups, len(discovered))
            if bvid not in previously_seen
        ]
        for bvid in pending[:max_notes]:
            url = f"https://www.bilibili.com/video/{bvid}/"
            status, _ = run_cli(prefix, ["browser", session, "open", url], timeout)
            if status:
                captures.append({"source_url": url, "content_complete": False,
                    "incomplete_reason": "public_video_page_unavailable"})
                continue
            status, raw = run_cli(
                prefix, ["browser", session, "eval", VIDEO_DOM_JS], timeout
            )
            if status:
                captures.append({"source_url": url, "content_complete": False,
                    "incomplete_reason": "public_video_metadata_or_caption_unavailable"})
                continue
            try:
                page = json.loads(raw)
                if str(page.get("bvid")) != bvid:
                    raise ValueError("REDIRECTED_BVID")
                captures.append(normalize_video(page))
            except (ValueError, TypeError, json.JSONDecodeError):
                captures.append({"source_url": url, "content_complete": False,
                    "incomplete_reason": "public_video_response_invalid"})
    finally:
        run_cli(prefix, ["browser", session, "close"], min(timeout, 14))
    # Every entry came from a real observed video URL.
    captures = previous + captures
    payload = {
        "source_id": SOURCE_ID,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "discovery": {
            "discovered_unique_entries": max(len(discovered), previous_discovery),
            "screened_entries": len(captures),
        },
        "entries": captures,
        "search_error_kinds": errors,
        "limitations": [
            "Public browser/player/subtitle endpoints only; no auth bypass",
            "Tracks that do not cover >=92% of video duration are incomplete",
            "Official source quotas must be independently audited",
        ],
    }
    (output / "public_videos.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return payload


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--query", action="append", dest="queries")
    p.add_argument("--max-notes", type=int, default=5)
    p.add_argument("--timeout", type=int, default=45)
    p.add_argument("--resume", action="store_true", help="continue real video capture without recounting")
    args = p.parse_args()
    if not (1 <= args.max_notes <= 60 and 10 <= args.timeout <= 180):
        p.error("invalid capture bounds")
    result = collect(args.output, args.queries or list(DEFAULT_QUERIES),
        max_notes=args.max_notes, timeout=args.timeout, resume=args.resume)
    print(json.dumps({
        "source_id": SOURCE_ID,
        "discovered": result["discovery"]["discovered_unique_entries"],
        "screened": result["discovery"]["screened_entries"],
        "complete_eligible": sum(x.get("signal_eligible") is True for x in result["entries"]),
        "output": str(args.output / "public_videos.json")
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
