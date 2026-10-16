#!/usr/bin/env python3
"""Build an auditable analysis sample without truncating acquisition data."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def item_key(item: dict[str, Any]) -> str:
    value = item.get("book_id") or item.get("source_item_id")
    if value:
        return str(value)
    return "|".join(str(item.get(name) or "").strip().lower() for name in ("title", "author"))


def build_sample(
    rows: list[dict[str, Any]], base_n: int = 6, max_n: int = 10, small_max: int = 25
) -> dict[str, Any]:
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("rows must be a list of objects")
    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if not row.get("source_id") or not row.get("list_id") or not item_key(row):
            raise ValueError("each row needs source_id, list_id and a work id or title+author")
        by_source[str(row["source_id"])].append(row)

    selected_rows: list[dict[str, Any]] = []
    source_reports = []
    for source_id, source_rows in sorted(by_source.items()):
        unique_count = len({item_key(row) for row in source_rows})
        if unique_count <= small_max:
            chosen = [(row, "all_unique_small_complete_source") for row in source_rows]
            mode = "all_unique"
        else:
            lists: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in source_rows:
                lists[str(row["list_id"])].append(row)
            chosen = []
            prior_keys: set[str] = set()
            for list_id in sorted(lists):
                ranked = sorted(lists[list_id], key=lambda row: (int(row.get("position") or 10**9), item_key(row)))
                base = ranked[:base_n]
                duplicate_count = sum(item_key(row) in prior_keys for row in base)
                expand = bool(base) and duplicate_count * 2 >= len(base)
                limit = max_n if expand else base_n
                for row in ranked[:limit]:
                    reason = "adaptive_overlap_expansion" if expand and int(row.get("position") or 0) > base_n else "base_top_n"
                    chosen.append((row, reason))
                prior_keys.update(item_key(row) for row in ranked[:limit])
            mode = "adaptive_rank"

        work_map: dict[str, dict[str, Any]] = {}
        for row, reason in chosen:
            key = item_key(row)
            if key not in work_map:
                work_map[key] = {
                    "source_id": source_id,
                    "work_key": key,
                    "title": row.get("title"),
                    "author": row.get("author"),
                    "selection_reasons": [],
                    "appearances": [],
                }
            work = work_map[key]
            if reason not in work["selection_reasons"]:
                work["selection_reasons"].append(reason)
            work["appearances"].append({"list_id": row["list_id"], "position": row.get("position")})
        selected_rows.extend(work_map.values())
        source_reports.append({
            "source_id": source_id,
            "raw_rank_slots": len(source_rows),
            "raw_unique_works": unique_count,
            "selected_unique_works": len(work_map),
            "sampling_mode": mode,
        })
    return {
        "sampling_policy": {"base_top_n": base_n, "adaptive_max_top_n": max_n, "small_complete_source_max_unique": small_max},
        "source_reports": source_reports,
        "selected_works": selected_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-n", type=int, default=6)
    parser.add_argument("--max-n", type=int, default=10)
    parser.add_argument("--small-max", type=int, default=25)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    rows = payload.get("items") if isinstance(payload, dict) else payload
    result = build_sample(rows, args.base_n, args.max_n, args.small_max)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["source_reports"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
