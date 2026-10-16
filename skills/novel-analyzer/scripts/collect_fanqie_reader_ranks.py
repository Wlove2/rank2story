#!/usr/bin/env python3
"""Collect the official Fanqie reader App 11-rank center and short rank."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

API_HOST = "https://api5-normal.fqnovel.com"
TAB_PATH = "/reading/bookapi/bookmall/tab/v1/"
RANK_PATH = "/reading/bookapi/bookmall/cell/change/v1/"
APP_VERSION_CODE = "72732"
APP_VERSION_NAME = "7.2.8.7"
USER_AGENT = "com.dragon.read/72732 (Linux; U; Android 13)"

# Names and algorithm ids are independently verified against the current Lynx
# common-rank-list-v1 template.  Discovery below must confirm every one before
# collection starts; a stale or partial App payload therefore fails closed.
LONG_RANKS = {
    "100": "完本榜",
    "101": "推荐榜",
    "102": "黑马榜",
    "108": "新书榜",
    "109": "追更榜",
    "111": "阅读榜",
    "188": "礼物榜",
    "200": "巅峰榜",
    "205": "作者榜",
    "207": "书友榜",
    "208": "书荒榜",
}
SHORT_RANKS = {"601": "番茄短篇榜"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def common_params() -> dict[str, str]:
    return {
        "aid": "1967",
        "iid": "1",
        "app_name": "novelapp",
        "version_code": APP_VERSION_CODE,
        "update_version_code": APP_VERSION_CODE,
        "version_name": APP_VERSION_NAME,
        "device_platform": "android",
    }


def fetch(path: str, params: dict[str, Any], timeout: int) -> tuple[dict[str, Any], dict[str, Any]]:
    query = urllib.parse.urlencode({k: str(v) for k, v in params.items() if v is not None})
    url = API_HOST + path + "?" + query
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    captured_at = utc_now()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
        payload = json.loads(raw.decode("utf-8"))
        transport = {
            "captured_at": captured_at,
            "http_status": response.status,
            "response_bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "content_type": response.headers.get("Content-Type"),
            "url": url,
        }
    if str(payload.get("code")) not in {"0", "None"}:
        raise ValueError(f"Fanqie API failed: code={payload.get('code')} message={payload.get('message')}")
    return payload, transport


def walk_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from walk_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_strings(child)


def discover_protocol(timeout: int) -> tuple[dict[str, Any], dict[str, str], dict[str, Any]]:
    """Discover the current rank deep-link instead of trusting a stale cell id."""
    payload, transport = fetch(TAB_PATH, {**common_params(), "tab_type": "1"}, timeout)
    candidates = [text for text in walk_strings(payload) if "common-rank-list-v1" in text]
    if not candidates:
        raise ValueError("current tab 25 contains no common-rank-list-v1 deep-link")
    decoded = candidates[0]
    for _ in range(4):
        next_value = urllib.parse.unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    parsed = urllib.parse.urlparse(decoded)
    query = {key: values[-1] for key, values in urllib.parse.parse_qs(parsed.query).items()}
    discovered = set(filter(None, query.get("main_algo_type", query.get("algo_type", "")).split(",")))
    missing = sorted(set(LONG_RANKS) - discovered)
    if missing:
        raise ValueError(f"current Fanqie App rank protocol is incomplete; missing algorithms={missing}")
    return payload, query, transport


def rank_params(discovered: dict[str, str], algorithm: str, lane: str) -> dict[str, str]:
    params = common_params()
    for key in (
        "cell_id", "bookstore_id", "cell_gender", "gender_list_type",
        "genre_tab", "tab_type", "rank_list_id", "rank_list_type",
    ):
        if discovered.get(key):
            params[key] = discovered[key]
    params.update({
        "algo_type": algorithm,
        "genre_tab": "7" if lane == "short" else discovered.get("genre_tab", "0"),
        "gender_list_type": discovered.get("gender_list_type", discovered.get("cell_gender", "2")),
        "list_type": "daily",
        "client_req_type": "1",
        "genre_type": "0",
        "rank_sub_info_id": "7" if lane == "short" else discovered.get("genre_tab", "0"),
        "rank_sub_info_type": "0",
        "rank_list_style_type": "1",
        "web_page_key": "common-rank-list-v1",
        "web_page_version_code": "1",
        "support_gender_list": "true",
        "change_type": "1",
        "offset": "0",
        "limit": "12",
        "book_type": "0",
    })
    if algorithm == "200":
        params.update({"rank_list_sub_tab_type_list": "1,2", "specific_sub_tab_type": "1"})
    return params


def safe_id(value: Any) -> str:
    return "" if value is None else str(value)


def looks_like_book(value: dict[str, Any]) -> bool:
    return bool(value.get("book_id") and (value.get("book_name") or value.get("title")))


def collect_objects(value: Any, predicate: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if predicate(value):
            found.append(value)
        else:
            for child in value.values():
                found.extend(collect_objects(child, predicate))
    elif isinstance(value, list):
        for child in value:
            found.extend(collect_objects(child, predicate))
    return found


def normalize_rank(payload: dict[str, Any], algorithm: str, name: str, lane: str) -> dict[str, Any]:
    books = collect_objects(payload.get("data"), looks_like_book)
    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    for book in books:
        book_id = safe_id(book.get("book_id"))
        if not book_id or book_id in seen:
            continue
        seen.add(book_id)
        word_count = int(book.get("word_number") or book.get("word_count") or 0)
        items.append({
            "position": len(items) + 1,
            "book_id": book_id,
            "title": book.get("book_name") or book.get("title"),
            "author": book.get("author"),
        "category": book.get("category") or book.get("genre"),
        "word_count": word_count or None,
        "official_short_surface": lane == "short",
        "target_short_fit": True if lane == "short" else False,
        "target_capacity_fit": word_count <= 80_000 if lane == "short" and word_count else None,
        })
    topics = collect_objects(
        payload.get("data"),
        lambda obj: bool(obj.get("topic_id") and (obj.get("topic_desc") or obj.get("topic_name") or obj.get("topic_title") or obj.get("hot_book_ids"))),
    )
    authors = collect_objects(
        payload.get("data"),
        lambda obj: bool((obj.get("author_id") or obj.get("user_id") or obj.get("AuthorId")) and not obj.get("book_id")),
    )
    if algorithm == "205" and not authors:
        raise ValueError("Fanqie author rank returned no author records")
    if algorithm == "208" and not topics:
        raise ValueError("Fanqie book-shortage rank returned no topic records")
    if algorithm not in {"205", "208"} and not items:
        raise ValueError(f"Fanqie {name} ({algorithm}) returned no books")
    records = items if items else topics if topics else authors
    return {
        "source": "fanqie_reader_rank_center",
        "lane": lane,
        "algorithm": algorithm,
        "name": name,
        "record_kind": "book" if items else "topic" if topics else "author",
        "items": items,
        "records": records,
        "stats": {"record_count": len(records), "book_count": len(items), "unique_book_count": len(seen)},
    }


def ordered_ids(snapshot: dict[str, Any]) -> list[str]:
    if snapshot["record_kind"] == "book":
        return [item["book_id"] for item in snapshot["items"]]
    key = "topic_id" if snapshot["record_kind"] == "topic" else "author_id"
    return [safe_id(item.get(key) or item.get("user_id") or item.get("AuthorId")) for item in snapshot["records"]]


def collect(output_dir: Path, *, repeat: int = 2, timeout_seconds: int = 30, delay_seconds: float = 1.0) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    all_runs: list[dict[str, dict[str, Any]]] = []
    captures: list[dict[str, Any]] = []
    for repeat_index in range(1, repeat + 1):
        discovery_raw, discovered, discovery_transport = discover_protocol(timeout_seconds)
        write_json(output_dir / f"protocol_discovery_raw_{repeat_index:02d}.json", discovery_raw)
        run: dict[str, dict[str, Any]] = {}
        run_transport: list[dict[str, Any]] = []
        ranks = [(algo, name, "long") for algo, name in LONG_RANKS.items()] + [("601", SHORT_RANKS["601"], "short")]
        for algorithm, name, lane in ranks:
            raw, transport = fetch(RANK_PATH, rank_params(discovered, algorithm, lane), timeout_seconds)
            normalized = normalize_rank(raw, algorithm, name, lane)
            normalized["captured_at"] = transport["captured_at"]
            write_json(output_dir / f"{lane}_{algorithm}_raw_{repeat_index:02d}.json", raw)
            write_json(output_dir / f"{lane}_{algorithm}_normalized_{repeat_index:02d}.json", normalized)
            run[algorithm] = normalized
            run_transport.append({"algorithm": algorithm, "name": name, **transport, **normalized["stats"]})
        if set(run) != set(LONG_RANKS) | set(SHORT_RANKS):
            raise ValueError("Fanqie rank capture did not cover the required 11+1 algorithms")
        all_runs.append(run)
        captures.append({"index": repeat_index, "protocol_discovery": discovery_transport, "lists": run_transport})
        if repeat_index < repeat:
            time.sleep(delay_seconds)

    comparisons = []
    for index, (left, right) in enumerate(zip(all_runs, all_runs[1:]), 1):
        comparisons.append({
            "pair": index,
            "lists": [{
                "algorithm": algorithm,
                "name": left[algorithm]["name"],
                "left_count": len(ordered_ids(left[algorithm])),
                "right_count": len(ordered_ids(right[algorithm])),
                "overlap_count": len(set(ordered_ids(left[algorithm])) & set(ordered_ids(right[algorithm]))),
                "exact_ordered_ids": ordered_ids(left[algorithm]) == ordered_ids(right[algorithm]),
            } for algorithm in sorted(left)],
        })
    write_json(output_dir / "reproducibility.json", {"repeat_count": repeat, "pairs": comparisons})
    manifest = {
        "source": "fanqie_reader_rank_center",
        "official_host": API_HOST,
        "protocol_discovery": "current bookmall tab 1 common-rank-list-v1 deep-link",
        "rank_endpoint": RANK_PATH,
        "captured_at": utc_now(),
        "repeat_count": repeat,
        "long_evidence_class": "verified_complete_official_11_rank_center",
        "short_evidence_class": "verified_official_independent_short_rank",
        "long_algorithms": LONG_RANKS,
        "short_algorithms": SHORT_RANKS,
        "acquired_long_list_ids": list(LONG_RANKS.values()),
        "acquired_short_list_ids": list(SHORT_RANKS.values()),
        "source_results": {
            "fanqie_reader_novel_rank_center": {"status": "success", "acquired_list_ids": list(LONG_RANKS.values())},
            "fanqie_reader_short_rank_center": {"status": "success", "acquired_list_ids": list(SHORT_RANKS.values())},
        },
        "captures": captures,
        "reproducibility_file": "reproducibility.json",
        "limitations": [
            "The App protocol and all 11 expected algorithms are rediscovered and validated on every repeat.",
            "The independent official short rank remains short-lane evidence regardless of word count; word count is a capacity annotation, not a lower admission gate.",
            "Author and book-shortage ranks contain author/topic records rather than ordinary book rows and are preserved without fabrication.",
        ],
    }
    write_json(output_dir / "manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeat", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args()
    if args.repeat < 2:
        parser.error("--repeat must be at least 2 for production evidence")
    print(json.dumps(collect(args.output, repeat=args.repeat, timeout_seconds=args.timeout, delay_seconds=args.delay), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
