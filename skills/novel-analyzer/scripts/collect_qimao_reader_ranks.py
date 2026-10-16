#!/usr/bin/env python3
"""Collect the official Qimao reader App story and full current rank centers."""

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

API_HOST = "https://api-bc.wtzw.com"
STORY_PATH = "/api/v1/story/leader-board"
LONG_PATH = "/api/v1/leader-board"
APP_VERSION = "82000"
APPLICATION_ID = "com.kmxs.reader"
# Protocol constant embedded in compatible official clients; not a user secret.
SIGNING_SALT = "d3dGiJc651gSQ8w1"

EXPECTED_LONG_TAXONOMY = {
    "1": {
        "must_read_list": "必读榜", "hot_list": "大热榜", "craft_list": "匠心榜",
        "new_list": "新书榜", "end_list": "完结榜", "up_list": "飙升榜",
        "good_comment_list": "好评榜", "hot_search_list": "热搜榜",
        "reward_value_list": "礼物榜", "character_list": "角色榜",
        "ticket_list": "投票榜", "reward_user_list": "粉丝榜",
    },
    "2": {
        "must_read_list": "必读榜", "hot_list": "大热榜", "craft_list": "匠心榜",
        "new_list": "新书榜", "end_list": "完结榜", "up_list": "飙升榜",
        "good_comment_list": "好评榜", "hot_search_list": "热搜榜",
        "reward_value_list": "礼物榜", "character_list": "角色榜",
        "ticket_list": "投票榜", "reward_user_list": "粉丝榜",
    },
    "3": {
        "hot_list": "大热榜", "film_list": "影视榜", "good_comment_list": "好评榜",
        "hot_search_list": "热搜榜", "ticket_list": "投票榜",
    },
}
TAB_NAMES = {"1": "男生", "2": "女生", "3": "图书"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def sign_mapping(values: dict[str, Any]) -> str:
    canonical = "".join(f"{key}={values[key]}" for key in sorted(values))
    return hashlib.md5((canonical + SIGNING_SALT).encode("utf-8")).hexdigest()


def signed_headers() -> dict[str, str]:
    headers = {
        "app-version": APP_VERSION, "platform": "android", "reg": "0",
        "AUTHORIZATION": "", "application-id": APPLICATION_ID, "net-env": "1",
        "channel": "unknown", "qm-params": "",
    }
    headers["sign"] = sign_mapping(headers)
    headers.update({"Accept": "application/json", "User-Agent": f"{APPLICATION_ID}/{APP_VERSION} (Android)"})
    return headers


def signed_query(params: dict[str, Any] | None = None) -> str:
    values = {str(key): str(value) for key, value in (params or {}).items() if value is not None}
    if not values:
        return ""
    values["sign"] = sign_mapping(values)
    return urllib.parse.urlencode(values)


def fetch(path: str, timeout_seconds: int = 30, *, params: dict[str, Any] | None = None, retries: int = 3) -> tuple[dict[str, Any], dict[str, Any]]:
    captured_at = utc_now()
    query = signed_query(params)
    url = API_HOST + path + (f"?{query}" if query else "")
    request = urllib.request.Request(url, headers=signed_headers())
    last_err = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                raw = response.read()
                payload = json.loads(raw.decode("utf-8"))
                transport = {
                    "captured_at": captured_at, "http_status": response.status,
                    "response_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                    "content_type": response.headers.get("Content-Type"), "url": url,
                }
            if not isinstance(payload.get("data"), dict):
                raise ValueError(f"{path} did not return a data object")
            return payload, transport
        except (urllib.error.URLError, TimeoutError, ConnectionResetError) as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            continue
    raise last_err


def story_request_params(data: dict[str, Any], *, rank_type: str, category_id: str, category_type: str, cache_ver: str = "") -> dict[str, Any]:
    return {
        "rank_type": rank_type, "category_id": category_id, "category_type": category_type,
        "cache_ver": cache_ver or str(data.get("cache_ver") or ""),
        "refresh_page": str(data.get("refresh_page") or "1"),
    }


def story_matrix(seed: dict[str, Any]) -> list[dict[str, str]]:
    data = seed["data"]
    ranks = [item for item in data.get("rank_list", []) if isinstance(item, dict)]
    categories = [item for item in data.get("category_list", []) if isinstance(item, dict)]
    rank_types = {str(item.get("type") or "") for item in ranks}
    if not {"story_rec_list", "story_trend_list"}.issubset(rank_types):
        raise ValueError(f"story rank taxonomy incomplete: {sorted(rank_types)}")
    if not categories or any(not str(item.get("category_id") or "") for item in categories):
        raise ValueError("story category taxonomy missing category ids")
    return [
        story_request_params(
            data, rank_type=str(rank["type"]), category_id=str(category["category_id"]),
            category_type=str(category.get("category_type") or ""), cache_ver=str(rank.get("cache_ver") or ""),
        )
        for rank in ranks for category in categories if rank.get("type")
    ]


def normalize_book(book: dict[str, Any], *, lane: str, rank_type: str, position: int) -> dict[str, Any]:
    return {
        "source": "qimao_reader_app_api", "lane": lane, "rank_type": rank_type,
        "position": int(book.get("order") or position), "book_id": str(book.get("id") or ""),
        "title": book.get("title"), "author": book.get("author"),
        "subtitle": book.get("sub_title"), "intro": book.get("intro"),
        "reader_type": str(book.get("reader_type") or ""), "image_link": book.get("image_link"),
        "book_tags": book.get("book_tag_list") or [], "word_count": None,
        "target_short_fit": None if lane == "short" else False,
        "length_verification": "platform_story_surface_word_count_unavailable" if lane == "short" else "not_applicable",
    }


def normalize_story(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload["data"]
    rank_type = str(data.get("rank_type") or "story_rec_list")
    books = [normalize_book(book, lane="short", rank_type=rank_type, position=i) for i, book in enumerate(data.get("books", []), 1) if isinstance(book, dict)]
    return {
        "source": "qimao_reader_story_leader_board", "surface": "reader_app_api", "lane": "short",
        "rank_type": rank_type, "cache_ver": str(data.get("cache_ver") or ""),
        "refresh_page": data.get("refresh_page"), "categories": data.get("category_list") or [],
        "available_rank_tabs": data.get("rank_list") or [], "items": books,
        "stats": {"item_count": len(books), "unique_book_count": len({item['book_id'] for item in books if item['book_id']})},
    }


def long_params(tab_type: str, rank_type: str, category_id: str = "0", category_type: str = "0") -> dict[str, str]:
    return {
        "rank_type": rank_type, "category_id": category_id, "tab_type": tab_type,
        "category_type": category_type, "read_preference": "", "from": "",
        "new_user": "0", "refresh_state": "0", "book_privacy": "0",
    }


def discover_long_taxonomy(timeout: int) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    ranks_by_tab: dict[str, list[dict[str, Any]]] = {}
    categories_by_tab: dict[str, list[dict[str, Any]]] = {}
    seeds: list[dict[str, Any]] = []
    for tab_type, expected in EXPECTED_LONG_TAXONOMY.items():
        raw, transport = fetch(LONG_PATH, timeout, params=long_params(tab_type, "hot_list"))
        data = raw["data"]
        ranks = [item for item in data.get("rank_list", []) if isinstance(item, dict)]
        categories = [item for item in data.get("category_list", []) if isinstance(item, dict)]
        actual = {str(item.get("type") or ""): str(item.get("title") or "") for item in ranks if item.get("type")}
        if actual != expected:
            raise ValueError(f"Qimao tab {tab_type} taxonomy drift: expected={expected}, actual={actual}")
        if not categories or str(categories[0].get("category_id")) != "0":
            raise ValueError(f"Qimao tab {tab_type} missing all-category entry")
        ranks_by_tab[tab_type] = ranks
        categories_by_tab[tab_type] = categories
        seeds.append({"tab_type": tab_type, "transport": transport, "raw": raw})
    return ranks_by_tab, categories_by_tab, seeds


def normalize_long(payload: dict[str, Any], *, tab_type: str, rank_name: str) -> dict[str, Any]:
    data = payload["data"]
    rank_type = str(data.get("rank_type") or "")
    if rank_type == "character_list":
        records = [item for item in data.get("character_list", []) if isinstance(item, dict)]
        items: list[dict[str, Any]] = []
        record_kind = "character"
    else:
        records = [item for item in data.get("books", []) if isinstance(item, dict)]
        items = [normalize_book(book, lane="long", rank_type=rank_type, position=i) for i, book in enumerate(records, 1)]
        record_kind = "book"
    if not records:
        raise ValueError(f"Qimao {TAB_NAMES[tab_type]}/{rank_name} returned no records")
    return {
        "source": "qimao_reader_rank_center", "surface": "reader_app_api", "lane": "long",
        "tab_type": tab_type, "tab_name": TAB_NAMES[tab_type], "rank_type": rank_type,
        "rank_name": rank_name, "category_type": str(data.get("category_type") or ""),
        "category_id": str(data.get("category_id") or ""), "cache_ver": str(data.get("cache_ver") or ""),
        "record_kind": record_kind, "items": items, "records": records,
        "stats": {"record_count": len(records), "book_count": len(items), "unique_book_count": len({item['book_id'] for item in items if item['book_id']})},
    }


def record_ids(snapshot: dict[str, Any]) -> list[str]:
    if snapshot.get("record_kind") == "character":
        return [str(item.get("character_id") or item.get("id") or "") for item in snapshot["records"]]
    return [item["book_id"] for item in snapshot.get("items", [])]


def compare_runs(runs: list[dict[str, dict[str, Any]]]) -> dict[str, Any]:
    pairs = []
    for index, (left, right) in enumerate(zip(runs, runs[1:]), 1):
        pairs.append({
            "pair": index,
            "lists": [{
                "list_id": list_id, "left_count": len(record_ids(left[list_id])),
                "right_count": len(record_ids(right[list_id])),
                "overlap_count": len(set(record_ids(left[list_id])) & set(record_ids(right[list_id]))),
                "exact_ordered_ids": record_ids(left[list_id]) == record_ids(right[list_id]),
            } for list_id in sorted(left)],
        })
    return {"repeat_count": len(runs), "pairs": pairs}


def collect(output_dir: Path, *, repeat: int = 2, timeout_seconds: int = 30, delay_seconds: float = 1.0) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    captures: list[dict[str, Any]] = []
    story_runs: list[dict[str, dict[str, Any]]] = []
    long_runs: list[dict[str, dict[str, Any]]] = []
    category_runs: list[dict[str, dict[str, Any]]] = []
    required_story_ids: list[str] = []
    required_long_ids = sorted(f"{tab}/{rank}" for tab, ranks in EXPECTED_LONG_TAXONOMY.items() for rank in ranks)
    category_taxonomy: dict[str, list[dict[str, Any]]] = {}

    for repeat_index in range(1, repeat + 1):
        story_seed, story_seed_transport = fetch(STORY_PATH, timeout_seconds)
        matrix = story_matrix(story_seed)
        if not required_story_ids:
            required_story_ids = sorted(f"{item['rank_type']}/{item['category_id']}" for item in matrix)
        write_json(output_dir / f"story_taxonomy_raw_{repeat_index:02d}.json", story_seed)
        story_run: dict[str, dict[str, Any]] = {}
        story_transports: list[dict[str, Any]] = []
        for params in matrix:
            raw, transport = fetch(STORY_PATH, timeout_seconds, params=params)
            data = raw["data"]
            if str(data.get("rank_type")) != params["rank_type"] or str(data.get("category_id")) != params["category_id"]:
                raise ValueError(f"story endpoint ignored signed query {params}")
            normalized = normalize_story(raw)
            list_id = f"{params['rank_type']}/{params['category_id']}"
            normalized.update({"list_id": list_id, "category_id": params["category_id"], "category_type": params["category_type"], "captured_at": transport["captured_at"]})
            safe_id = list_id.replace("/", "__")
            write_json(output_dir / f"story_{safe_id}_raw_{repeat_index:02d}.json", raw)
            write_json(output_dir / f"story_{safe_id}_normalized_{repeat_index:02d}.json", normalized)
            story_run[list_id] = normalized
            story_transports.append({"list_id": list_id, **transport, **normalized["stats"]})
        if sorted(story_run) != required_story_ids:
            raise ValueError("Qimao story matrix capture incomplete")

        ranks_by_tab, categories_by_tab, seeds = discover_long_taxonomy(timeout_seconds)
        category_taxonomy = categories_by_tab
        for seed in seeds:
            write_json(output_dir / f"long_taxonomy_tab_{seed['tab_type']}_raw_{repeat_index:02d}.json", seed["raw"])
        long_run: dict[str, dict[str, Any]] = {}
        long_transports: list[dict[str, Any]] = []
        for tab_type, ranks in ranks_by_tab.items():
            for rank in ranks:
                rank_type = str(rank["type"])
                rank_name = str(rank["title"])
                raw, transport = fetch(LONG_PATH, timeout_seconds, params=long_params(tab_type, rank_type))
                data = raw["data"]
                if str(data.get("rank_type")) != rank_type or str(data.get("category_id")) != "0" or str(data.get("category_type")) != "0":
                    raise ValueError(f"rank center ignored query for {tab_type}/{rank_type}")
                normalized = normalize_long(raw, tab_type=tab_type, rank_name=rank_name)
                list_id = f"{tab_type}/{rank_type}"
                normalized.update({"list_id": list_id, "captured_at": transport["captured_at"]})
                write_json(output_dir / f"long_{tab_type}_{rank_type}_raw_{repeat_index:02d}.json", raw)
                write_json(output_dir / f"long_{tab_type}_{rank_type}_normalized_{repeat_index:02d}.json", normalized)
                long_run[list_id] = normalized
                long_transports.append({"list_id": list_id, "name": rank_name, **transport, **normalized["stats"]})
        if sorted(long_run) != required_long_ids:
            raise ValueError("Qimao current rank-center capture incomplete")

        category_run: dict[str, dict[str, Any]] = {}
        category_transports: list[dict[str, Any]] = []
        for tab_type, categories in categories_by_tab.items():
            expansion_ranks = ("hot_list", "up_list") if tab_type in {"1", "2"} else ("hot_list", "ticket_list")
            for category in categories:
                category_id = str(category.get("category_id") or "")
                category_type = str(category.get("category_type") or "")
                if not category_id or category_id == "0":
                    continue
                for rank_type in expansion_ranks:
                    rank_name = EXPECTED_LONG_TAXONOMY[tab_type][rank_type]
                    raw, transport = fetch(LONG_PATH, timeout_seconds, params=long_params(tab_type, rank_type, category_id, category_type))
                    data = raw["data"]
                    if str(data.get("rank_type")) != rank_type or str(data.get("category_id")) != category_id or str(data.get("category_type")) != category_type:
                        raise ValueError(f"rank center ignored category query for {tab_type}/{category_id}/{rank_type}")
                    normalized = normalize_long(raw, tab_type=tab_type, rank_name=rank_name)
                    list_id = f"{tab_type}/{category_id}/{rank_type}"
                    normalized.update({"list_id": list_id, "category_name": category.get("title"), "captured_at": transport["captured_at"]})
                    write_json(output_dir / f"category_{tab_type}_{category_id}_{rank_type}_raw_{repeat_index:02d}.json", raw)
                    write_json(output_dir / f"category_{tab_type}_{category_id}_{rank_type}_normalized_{repeat_index:02d}.json", normalized)
                    category_run[list_id] = normalized
                    category_transports.append({"list_id": list_id, "category_name": category.get("title"), **transport, **normalized["stats"]})
        expected_category_count = sum((len(items) - 1) * 2 for items in categories_by_tab.values())
        if len(category_run) != expected_category_count:
            raise ValueError(f"Qimao category expansion incomplete: expected={expected_category_count}, actual={len(category_run)}")
        captures.append({"index": repeat_index, "story_seed": story_seed_transport, "story_lists": story_transports, "long_lists": long_transports, "category_lists": category_transports})
        story_runs.append(story_run)
        long_runs.append(long_run)
        category_runs.append(category_run)
        if repeat_index < repeat:
            time.sleep(delay_seconds)

    write_json(output_dir / "reproducibility.json", {"story": compare_runs(story_runs), "long": compare_runs(long_runs), "category_expansion": compare_runs(category_runs)})
    acquired_long_names = [
        f"{TAB_NAMES[tab]}/{name}"
        for tab, ranks in EXPECTED_LONG_TAXONOMY.items()
        for name in ranks.values()
    ]
    acquired_story_names = ["story_rec_list/all", "story_trend_list/all"]
    manifest = {
        "source": "qimao_reader_app_api", "official_host": API_HOST,
        "app_version": APP_VERSION, "application_id": APPLICATION_ID,
        "captured_at": utc_now(), "repeat_count": repeat, "authentication": "none_observed",
        "story_evidence_class": "verified_complete_official_story_rank_matrix",
        "long_evidence_class": "verified_complete_current_official_rank_center",
        "rank_endpoint": LONG_PATH, "required_story_list_ids": required_story_ids,
        "required_long_list_ids": required_long_ids, "current_official_list_count": len(required_long_ids),
        "acquired_long_list_ids": acquired_long_names,
        "acquired_story_list_ids": acquired_story_names,
        "category_taxonomy_complete": True,
        "source_results": {
            "qimao_reader_rank_center": {"status": "success", "acquired_list_ids": acquired_long_names, "category_taxonomy_complete": True},
            "qimao_reader_story_rank_center": {"status": "success", "acquired_list_ids": acquired_story_names, "category_taxonomy_complete": True},
        },
        "current_official_counts_by_tab": {tab: len(ranks) for tab, ranks in EXPECTED_LONG_TAXONOMY.items()},
        "category_expansion_list_count": len(category_runs[0]),
        "category_expansion_policy": "every non-all category: hot + up (male/female), hot + ticket (books)",
        "nominal_legacy_contract_count": 30,
        "removed_or_unadvertised_legacy_lists": ["图书/推荐榜"],
        "category_taxonomy": category_taxonomy, "captures": captures,
        "reproducibility_file": "reproducibility.json",
        "limitations": [
            "The current official API advertises 29 lists (12+12+5), not the legacy 30 (12+12+6).",
            "Unknown tab-3 recommendation aliases are normalized by the server to hot_list and must never be counted as a separate list.",
            "All current rank tabs are captured at the all-category level and every non-all category is expanded with two independent demand/trend lists.",
            "The story endpoint does not expose word count; verify target length before candidate generation.",
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
