#!/usr/bin/env python3
"""Normalize Fanqie/Qimao reader snapshots for long_source_refresh."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fanqie", type=Path, required=True)
    parser.add_argument("--qimao", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fanqie_raw = read(args.fanqie)
    qimao_raw = read(args.qimao)
    fanqie = [{
        **item,
        "title": item.get("book_name"),
        "rank": item.get("position"),
        "rank_type": item.get("source_cell_name"),
        "word_count": item.get("word_number"),
    } for item in fanqie_raw if isinstance(item, dict) and item.get("book_name")]
    qimao = [{
        **item,
        "rank": item.get("position"),
        "metric": item.get("subtitle"),
    } for item in qimao_raw.get("items", []) if isinstance(item, dict) and item.get("title")]
    now = datetime.now(timezone.utc).isoformat()
    write(args.output / "fanqie_reader_long.json", {"retrieved_at": now, "entries": fanqie})
    write(args.output / "qimao_reader_long.json", {"retrieved_at": now, "entries": qimao})
    print(json.dumps({"fanqie_entries": len(fanqie), "qimao_entries": len(qimao)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
