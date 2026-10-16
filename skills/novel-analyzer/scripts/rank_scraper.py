#!/usr/bin/env python3
"""Normalize paid-platform rank snapshots and summary-only social snapshots."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


SOURCE_URL_RE = re.compile(r"来源：\s*\S+\s+(https?://\S+)")
SNAPSHOT_DATE_RE = re.compile(r"时间：\s*(20\d{2}-\d{2}-\d{2})")
ZONGHENG_SECTIONS = {
    "月票榜": ("monthly_ticket", "monthly_tickets"),
    "点击榜": ("click", "clicks"),
    "推荐榜": ("recommendation", "recommendations"),
    "新书榜/人气榜": ("new_popularity", "popularity"),
}


def snapshot_metadata(text: str) -> dict[str, str | None]:
    url_match = SOURCE_URL_RE.search(text)
    date_match = SNAPSHOT_DATE_RE.search(text)
    return {
        "source_url": url_match.group(1) if url_match else None,
        "snapshot_date": date_match.group(1) if date_match else None,
    }


def _metric(value: str) -> int:
    return int(value.replace(",", ""))


def parse_zongheng_snapshot(text: str) -> list[dict[str, Any]]:
    """Parse the real 20260709 plain-text Zongheng snapshot without losing metrics."""
    metadata = snapshot_metadata(text)
    current: tuple[str, str] | None = None
    section_rank = 0
    results: list[dict[str, Any]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            label = re.sub(r"\s+TOP\d+$", "", line[3:].strip())
            current = ZONGHENG_SECTIONS.get(label)
            section_rank = 0
            continue
        if current is None:
            continue
        numbered = re.match(r"^(\d+)\s+(.+?)\s+([\d,]+)$", line)
        bulleted = re.match(r"^-\s+(.+?)\s+([\d,]+)(?:\s+人气)?$", line)
        if numbered:
            rank = int(numbered.group(1))
            title = numbered.group(2).strip()
            value = _metric(numbered.group(3))
        elif bulleted and current[0] == "new_popularity":
            section_rank += 1
            rank = section_rank
            title = bulleted.group(1).strip()
            value = _metric(bulleted.group(2))
        else:
            continue
        results.append({
            "platform": "zongheng",
            "gender": "mixed",
            "rank_type": current[0],
            "category": None,
            "rank": rank,
            "title": title,
            "author": None,
            "metric": value,
            "metric_type": current[1],
            "word_count": None,
            "url": metadata["source_url"],
            "snapshot_date": metadata["snapshot_date"],
            "evidence_layer": "paid_platform_corroboration",
            "signals": {},
        })
    return results


def parse_jjwxc_snapshot(text: str) -> list[dict[str, Any]]:
    """Parse the real 20260709 plain-text JJWXC quarterly TOP10 snapshot."""
    metadata = snapshot_metadata(text)
    results: list[dict[str, Any]] = []
    pattern = re.compile(
        r"^(\d+)\s+(.+?)《(.+?)》\s+(.+?)\s+(\d+)字\s+([\d,]+)积分$"
    )
    for raw_line in text.splitlines():
        match = pattern.match(raw_line.strip())
        if not match:
            continue
        results.append({
            "platform": "jjwxc",
            "gender": "female",
            "rank_type": "quarter",
            "category": match.group(4).strip(),
            "rank": int(match.group(1)),
            "title": match.group(3).strip(),
            "author": match.group(2).strip(),
            "metric": _metric(match.group(6)),
            "metric_type": "points",
            "word_count": int(match.group(5)),
            "url": metadata["source_url"],
            "snapshot_date": metadata["snapshot_date"],
            "evidence_layer": "paid_platform_corroboration",
            "signals": {},
        })
    return results


def parse_social_summary(text: str, platform: str) -> dict[str, Any]:
    """Record summary-level evidence without upgrading it to original content."""
    metadata = snapshot_metadata(text)
    section: str | None = None
    queries: list[str] = []
    summaries: list[str] = []
    signals: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("来源："):
            section = "queries"
        elif line.startswith("## 搜索摘要"):
            section = "summaries"
        elif line.startswith("## 有效信号"):
            section = "signals"
        elif line.startswith("## ") or line.startswith("时间："):
            section = None
        elif line.startswith("- "):
            value = line[2:].strip()
            if section == "queries":
                queries.append(value)
            elif section == "summaries":
                summaries.append(value)
            elif section == "signals":
                signals.append(value)
    return {
        "platform": platform,
        "snapshot_date": metadata["snapshot_date"],
        "acquisition_mode": "automated_public_search_summary",
        "evidence_layer": "social_demand_signal",
        "rank_completeness": "not_applicable",
        "sample_completeness": "metadata_only",
        "full_text_completeness": "not_acquired",
        "metadata_completeness": "search_summary_without_original_content",
        "queries": queries,
        "summary_items": summaries,
        "claimed_signals": signals,
        "eligible_signal_entries": 0,
        "limitations": [
            "summary only; not original post/video evidence",
            "strong signal requires original URL, publication time, engagement and complete post content or transcript",
        ],
    }


# Backward-compatible names used by older callers.
parse_zongheng = parse_zongheng_snapshot
parse_zongheng_v2 = parse_zongheng_snapshot
parse_jjwxc = parse_jjwxc_snapshot


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--platform", choices=("zongheng", "jjwxc", "xiaohongshu", "bilibili"), required=True)
    args = parser.parse_args()
    text = args.path.read_text(encoding="utf-8")
    if args.platform == "zongheng":
        payload: Any = {"entries": parse_zongheng_snapshot(text)}
    elif args.platform == "jjwxc":
        payload = {"entries": parse_jjwxc_snapshot(text)}
    else:
        payload = parse_social_summary(text, args.platform)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
