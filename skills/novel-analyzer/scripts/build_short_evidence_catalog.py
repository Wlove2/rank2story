#!/usr/bin/env python3
"""Merge current Fanqie and Qimao short-story observations into one catalog."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def category_names(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    names = []
    for item in value:
        if isinstance(item, dict) and str(item.get("name") or "").strip():
            names.append(str(item["name"]).strip())
        elif isinstance(item, str) and item.strip():
            names.append(item.strip())
    return list(dict.fromkeys(names))


def capacity_band(words: int | None) -> str:
    if not words:
        return "unknown"
    if words < 10_000:
        return "under_10k"
    if words < 30_000:
        return "10k_30k"
    if words <= 80_000:
        return "30k_80k"
    return "over_80k"


def channel_from_source(tab_name: Any, channel_field: Any = None) -> tuple[str, str]:
    """Derive audience channel ONLY from source-provided gender signals.

    带性别的就写性别；没有性别信号的（综合榜/作家榜/小红书/B站）一律 neutral，不猜词表。
    """
    raw = str(channel_field if channel_field is not None else tab_name or "").strip()
    low = raw.casefold()
    if raw in {"男生", "男频"} or low.startswith("male"):
        return "male", "source_channel"
    if raw in {"女生", "女频"} or low.startswith("female"):
        return "female", "source_channel"
    return "neutral", "neutral"


def fanqie_items(payload: Any, manifest_id: str) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        raise ValueError("Fanqie writer normalized payload must be a list")
    items = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        book_id = str(row.get("book_id") or "")
        words = int(row.get("word_number") or 0)
        if not book_id:
            continue
        items.append({
            "evidence_id": f"fanqie-writer-{book_id}",
            "manifest_id": manifest_id,
            "source_id": "fanqie_writer_hot_stories",
            "list_id": "writer_hot_stories/" + str((row.get("hot_types") or ["all"])[0]),
            "platform": "番茄",
            "surface": "writer_hot_stories",
            "kind": "short_rank",
            "source_item_id": book_id,
            "source": row.get("video_url") or "https://fanqienovel.com/main/writer/inspiration",
            "title": row.get("book_name"),
            "author": row.get("author"),
            "categories": category_names(row.get("category")),
            "rank_labels": list(row.get("hot_types") or []),
            "position": None,
            "word_count": words or None,
            "platform_format": "official_short",
            "lane_classification": "short",
            "classification_basis": "official_platform_surface",
            "capacity_band": capacity_band(words or None),
            "rank_status": "complete",
            "sample_status": "partial_200_char_excerpt",
            "excerpt": row.get("content"),
            "current": True,
            "evidence_state": "current_run",
            "channel": "neutral",
            "channel_basis": "neutral",
        })
    return items


def qimao_items(payload: dict[str, Any], manifest_id: str) -> list[dict[str, Any]]:
    rows = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError("Qimao story normalized payload must contain items[]")
    channel, channel_basis = channel_from_source(
        payload.get("tab_name"), payload.get("channel")
    )
    items = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        book_id = str(row.get("book_id") or "")
        if not book_id:
            continue
        subtitle = str(row.get("subtitle") or "")
        category = subtitle.split("・", 1)[1].strip() if "・" in subtitle else ""
        items.append({
            "evidence_id": f"qimao-story-{book_id}",
            "manifest_id": manifest_id,
            "source_id": "qimao_reader_story_rank_center",
            "list_id": "reader_story_leader_board/" + str(payload.get("rank_type") or "unknown"),
            "platform": "七猫",
            "surface": "reader_story_leader_board",
            "kind": "short_rank",
            "source_item_id": book_id,
            "source": "https://api-bc.wtzw.com/api/v1/story/leader-board",
            "title": row.get("title"),
            "author": row.get("author"),
            "categories": [category] if category else [],
            "rank_labels": [payload.get("rank_type") or row.get("rank_type")],
            "position": row.get("position"),
            "word_count": None,
            "platform_format": "official_short",
            "lane_classification": "short",
            "classification_basis": "official_platform_surface",
            "capacity_band": "unknown",
            "rank_status": "complete",
            "sample_status": "metadata_blurb_only",
            "excerpt": row.get("intro"),
            "current": True,
            "evidence_state": "current_run",
            "channel": channel,
            "channel_basis": channel_basis,
        })
    return items


def fanqie_reader_items(payload: Any, manifest_id: str) -> list[dict[str, Any]]:
    """Fanqie reader short rank (601 番茄短篇榜) rows; no gender signal -> neutral."""
    rows = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("Fanqie reader normalized payload must contain items[]")
    items = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        book_id = str(row.get("book_id") or "")
        if not book_id:
            continue
        words = int(row.get("word_count") or row.get("word_number") or 0)
        items.append({
            "evidence_id": f"fanqie-reader-{book_id}",
            "manifest_id": manifest_id,
            "source_id": "fanqie_reader_short_rank_center",
            "list_id": "reader_app_short_rank/" + str(payload.get("name") or "short") if isinstance(payload, dict) else "reader_app_short_rank/short",
            "platform": "番茄",
            "surface": "reader_app_short_rank",
            "kind": "short_rank",
            "source_item_id": book_id,
            "source": "https://api5-normal.fqnovel.com/reading/bookapi/bookmall/cell/change/v1/?algo_type=601&genre_tab=7",
            "title": row.get("title") or row.get("book_name"),
            "author": row.get("author"),
            "categories": [str(row.get("category"))] if row.get("category") else [],
            "rank_labels": ["番茄短篇榜"],
            "position": row.get("position"),
            "word_count": words or None,
            "platform_format": "official_short",
            "lane_classification": "short",
            "classification_basis": "official_platform_surface",
            "capacity_band": capacity_band(words or None),
            "rank_status": "complete",
            "sample_status": "metadata_blurb_only",
            "excerpt": row.get("excerpt") or row.get("intro") or row.get("content"),
            "current": True,
            "evidence_state": "current_run",
            "channel": "neutral",
            "channel_basis": "neutral",
        })
    return items


def social_items(entries: Any, source_id: str, platform_label: str, manifest_id: str) -> list[dict[str, Any]]:
    """Audited complete social demand entries; no gender signal -> neutral."""
    rows = entries.get("entries") if isinstance(entries, dict) else entries
    if not isinstance(rows, list):
        raise ValueError(f"{source_id} social payload must contain entries[]")
    items = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item_id = str(row.get("source_item_id") or row.get("note_id") or row.get("bvid") or "")
        if not item_id:
            continue
        prefix = "xhs-note" if source_id == "xiaohongshu_novel_demand_shared" else "bili-sub"
        kind = "social_post"
        surface = "original_note" if source_id == "xiaohongshu_novel_demand_shared" else "original_video"
        text = str(row.get("full_text") or row.get("content") or row.get("transcript") or "")
        items.append({
            "evidence_id": f"{prefix}-{item_id}",
            "manifest_id": manifest_id,
            "source_id": source_id,
            "platform": platform_label,
            "surface": surface,
            "kind": kind,
            "source_item_id": item_id,
            "source": row.get("source") or row.get("url"),
            "title": row.get("title"),
            "author": row.get("author"),
            "categories": [],
            "rank_labels": [],
            "position": None,
            "word_count": None,
            "platform_format": "social_demand_signal",
            "lane_classification": "short",
            "classification_basis": "social_demand_signal",
            "capacity_band": "unknown",
            "rank_status": "complete",
            "sample_status": "complete_content",
            "excerpt": text,
            "current": True,
            "evidence_state": "current_run",
            "channel": "neutral",
            "channel_basis": "neutral",
        })
    return items


def build_catalog(
    fanqie: Any,
    qimao: dict[str, Any],
    fanqie_manifest_id: str = "fanqie-writer-hot-current",
    qimao_manifest_id: str = "qimao-reader-story-current",
    fanqie_reader: Any = None,
    fanqie_reader_manifest_id: str = "fanqie-reader-short-current",
    xhs: Any = None,
    xhs_manifest_id: str = "xhs-current",
    bili: Any = None,
    bili_manifest_id: str = "bili-current",
) -> dict[str, Any]:
    items = fanqie_items(fanqie, fanqie_manifest_id)
    items.extend(qimao_items(qimao, qimao_manifest_id))
    if fanqie_reader is not None:
        items.extend(fanqie_reader_items(fanqie_reader, fanqie_reader_manifest_id))
    if xhs is not None:
        items.extend(social_items(xhs, "xiaohongshu_novel_demand_shared", "小红书", xhs_manifest_id))
    if bili is not None:
        items.extend(social_items(bili, "bilibili_novel_demand_shared", "B站", bili_manifest_id))
    # Deduplicate by evidence_id (first occurrence wins) so the frozen packet stays
    # lean: repeats across lists/rounds must not inflate the prompt for S1 atoms.
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in items:
        key = str(item.get("evidence_id") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    items = deduped
    capacity_counts = Counter(item["capacity_band"] for item in items)
    platform_counts = Counter(item["platform"] for item in items)
    channel_counts = Counter(item.get("channel") or "neutral" for item in items)
    return {
        "schema_version": 2,
        "generated_at": utc_now(),
        "lane": "short",
        "items": items,
        "stats": {
            "item_count": len(items),
            "unique_evidence_count": len({item["evidence_id"] for item in items}),
            "platform_counts": dict(platform_counts),
            "official_short_count": sum(item["platform_format"] == "official_short" for item in items),
            "capacity_band_counts": dict(capacity_counts),
            "channel_counts": dict(channel_counts),
            "unknown_word_count": capacity_counts.get("unknown", 0),
        },
        "rules": {
            "rank_record_and_sample_text_are_separate": True,
            "official_short_surface_is_authoritative": True,
            "word_count_is_descriptive_not_a_lane_gate": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fanqie-writer", type=Path, required=True)
    parser.add_argument("--qimao-story", type=Path, required=True)
    parser.add_argument("--fanqie-reader", type=Path)
    parser.add_argument("--xhs", type=Path)
    parser.add_argument("--bili", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fanqie-manifest-id", default="fanqie-writer-hot-current")
    parser.add_argument("--qimao-manifest-id", default="qimao-reader-story-current")
    args = parser.parse_args()
    catalog = build_catalog(
        load_json(args.fanqie_writer),
        load_json(args.qimao_story),
        fanqie_manifest_id=args.fanqie_manifest_id,
        qimao_manifest_id=args.qimao_manifest_id,
        fanqie_reader=load_json(args.fanqie_reader) if args.fanqie_reader else None,
        xhs=load_json(args.xhs) if args.xhs else None,
        bili=load_json(args.bili) if args.bili else None,
    )
    write_json(args.output, catalog)
    print(json.dumps(catalog["stats"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
