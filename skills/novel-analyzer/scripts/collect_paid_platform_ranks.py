#!/usr/bin/env python3
"""Collect current public Zongheng and JJWXC paid-platform rank pages."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lxml import html

SPECS = {
    "zongheng": {"url": "https://www.zongheng.com/rank", "encoding": "utf-8"},
    "jjwxc": {"url": "https://www.jjwxc.net/topten.php?orderstr=4", "encoding": "gb18030"},
}
ZONGHENG_LISTS = [
    ("monthly_ticket", "月票榜"),
    ("one_day_sales", "24小时畅销榜"),
    ("new_book_male", "新书榜-男频"),
    ("new_book_female", "新书榜-女频"),
    ("click", "点击榜"),
    ("recommendation", "推荐榜"),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fetch_bytes(url: str, timeout: int) -> tuple[bytes, dict[str, Any]]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/138 Safari/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept-Encoding": "identity",
        },
    )
    captured_at = utc_now()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
        transport = {
            "captured_at": captured_at,
            "http_status": int(response.status),
            "final_url": response.geturl(),
            "content_type": response.headers.get("Content-Type"),
            "response_bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    if transport["http_status"] != 200 or len(raw) < 10000:
        raise ValueError(f"rank page transport invalid: {transport}")
    return raw, transport


def class_nodes(node: Any, name: str) -> list[Any]:
    return node.xpath(f".//*[contains(concat(' ', normalize-space(@class), ' '), ' {name} ')]")


def first_text(node: Any, xpath: str) -> str | None:
    values = node.xpath(xpath)
    for value in values:
        text = str(value).strip()
        if text:
            return text
    return None


def absolute(base: str, value: str | None) -> str | None:
    return urllib.parse.urljoin(base, value) if value else None


def parse_zongheng(raw: bytes, captured_at: str) -> dict[str, Any]:
    document = html.fromstring(raw.decode("utf-8", "strict"))
    modules = class_nodes(document, "zh-modules-rank")
    if len(modules) != len(ZONGHENG_LISTS):
        raise ValueError(f"Zongheng overview expected 6 rank modules, got {len(modules)}")
    lists: list[dict[str, Any]] = []
    for module, (list_id, label) in zip(modules, ZONGHENG_LISTS):
        items: list[dict[str, Any]] = []
        for position, book in enumerate(class_nodes(module, "zh-modules-rank-book"), 1):
            title = first_text(book, ".//*[contains(concat(' ', normalize-space(@class), ' '), ' book-rank--title-text ')]//a/@title")
            href = first_text(book, ".//*[contains(concat(' ', normalize-space(@class), ' '), ' book-rank--title-text ')]//a/@href")
            if not title or not href:
                continue
            items.append({
                "platform": "zongheng",
                "source_id": "zongheng_public_rank_snapshot",
                "list_id": list_id,
                "list_label": label,
                "position": position,
                "book_id": str(book.get("data-id") or ""),
                "title": title,
                "author": first_text(book, ".//*[contains(concat(' ', normalize-space(@class), ' '), ' auther ')]/text()"),
                "metric_text": first_text(book, ".//*[contains(concat(' ', normalize-space(@class), ' '), ' rank-content-default__rank-text ')]/text()"),
                "url": absolute(SPECS["zongheng"]["url"], href),
                "captured_at": captured_at,
            })
        if len(items) < 7:
            raise ValueError(f"Zongheng list {list_id} too short: {len(items)}")
        lists.append({"list_id": list_id, "list_label": label, "items": items})
    return {
        "source": "zongheng_public_rank_snapshot",
        "captured_at": captured_at,
        "required_list_ids": [item[0] for item in ZONGHENG_LISTS],
        "lists": lists,
        "stats": {
            "list_count": len(lists),
            "rank_slots": sum(len(item["items"]) for item in lists),
            "unique_book_count": len({book["book_id"] or book["url"] for item in lists for book in item["items"]}),
        },
    }


def parse_jjwxc(raw: bytes, captured_at: str) -> dict[str, Any]:
    document = html.fromstring(raw.decode("gb18030", "replace"))
    rows = document.xpath("//tr[.//a[contains(@href, 'onebook.php')]]")
    items: list[dict[str, Any]] = []
    for row in rows:
        cells = row.xpath("./td")
        if len(cells) < 8:
            continue
        values = [" ".join(part.strip() for part in cell.xpath(".//text()") if part.strip()) for cell in cells]
        href = first_text(cells[2], ".//a[contains(@href, 'onebook.php')]/@href")
        try:
            position = int(values[0])
            word_count = int(values[5].replace(",", ""))
            points = int(values[6].replace(",", ""))
        except ValueError:
            continue
        items.append({
            "platform": "jjwxc",
            "source_id": "jjwxc_quarter_rank_snapshot",
            "list_id": "quarter_points",
            "position": position,
            "title": values[2],
            "author": values[1],
            "category": values[3],
            "status": values[4],
            "word_count": word_count,
            "points": points,
            "last_updated": values[7],
            "url": absolute(SPECS["jjwxc"]["url"], href),
            "captured_at": captured_at,
        })
    if len(items) < 100 or [item["position"] for item in items] != list(range(1, len(items) + 1)):
        raise ValueError(f"JJWXC quarterly rank incomplete or unordered: {len(items)}")
    return {
        "source": "jjwxc_quarter_rank_snapshot",
        "captured_at": captured_at,
        "required_list_ids": ["quarter_points"],
        "lists": [{"list_id": "quarter_points", "list_label": "季度排行榜", "items": items}],
        "stats": {"list_count": 1, "rank_slots": len(items), "unique_book_count": len({item["url"] for item in items})},
    }


def ordered_ids(snapshot: dict[str, Any]) -> list[str]:
    return [f'{rank["list_id"]}:{item["url"]}' for rank in snapshot["lists"] for item in rank["items"]]


def collect(platform: str, output: Path, *, repeat: int, timeout: int, delay: float) -> dict[str, Any]:
    spec = SPECS[platform]
    output.mkdir(parents=True, exist_ok=True)
    captures: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    parser = parse_zongheng if platform == "zongheng" else parse_jjwxc
    for index in range(1, repeat + 1):
        raw, transport = fetch_bytes(spec["url"], timeout)
        raw_path = output / f"raw_{index:02d}.html"
        raw_path.write_bytes(raw)
        normalized = parser(raw, transport["captured_at"])
        write_json(output / f"normalized_{index:02d}.json", normalized)
        captures.append({**transport, **normalized["stats"], "raw_file": raw_path.name})
        snapshots.append(normalized)
        if index < repeat:
            time.sleep(delay)
    pairs = []
    for pair, (left, right) in enumerate(zip(snapshots, snapshots[1:]), 1):
        left_ids, right_ids = ordered_ids(left), ordered_ids(right)
        pairs.append({"pair": pair, "left_count": len(left_ids), "right_count": len(right_ids), "overlap_count": len(set(left_ids) & set(right_ids)), "exact_ordered_ids": left_ids == right_ids})
    write_json(output / "reproducibility.json", {"repeat_count": repeat, "pairs": pairs})
    manifest = {
        "source": snapshots[-1]["source"],
        "official_url": spec["url"],
        "captured_at": utc_now(),
        "repeat_count": repeat,
        "required_list_ids": snapshots[-1]["required_list_ids"],
        "captures": captures,
        "reproducibility_file": "reproducibility.json",
        "evidence_class": "verified_current_public_rank",
    }
    write_json(output / "manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=tuple(SPECS), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeat", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat must be at least 1")
    print(json.dumps(collect(args.platform, args.output, repeat=args.repeat, timeout=args.timeout, delay=args.delay), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())