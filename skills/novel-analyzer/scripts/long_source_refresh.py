#!/usr/bin/env python3
"""Normalize registered long-form sources under the canonical long-lane freshness policy."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


FANQIE_RANKS = {"female/new_ranks", "male/new_ranks", "female/read_ranks", "male/read_ranks"}
QIMAO_RANKS = {f"{gender}/{rank}" for gender in ("male", "female") for rank in ("hot", "new", "finished", "favorites", "updates")}
QIMAO_URL = "https://www.qimao.com/paihang/"
PRIMARY_MAX_DAYS = 0
RANK_SCRAPER_PATH = Path(__file__).with_name("rank_scraper.py")
RANK_SPEC = importlib.util.spec_from_file_location("novel_rank_scraper", RANK_SCRAPER_PATH)
if RANK_SPEC is None or RANK_SPEC.loader is None:
    raise RuntimeError(f"cannot load {RANK_SCRAPER_PATH}")
RANK_SCRAPER = importlib.util.module_from_spec(RANK_SPEC)
sys.modules[RANK_SPEC.name] = RANK_SCRAPER
RANK_SPEC.loader.exec_module(RANK_SCRAPER)

REGISTERED_PRODUCTION_SOURCES = {
    "fanqie_reader": "direct_reader_side",
    "qimao_reader": "direct_reader_side",
    "zongheng": "paid_platform_corroboration",
    "jjwxc": "paid_platform_corroboration",
    "xiaohongshu": "social_demand_signal",
    "bilibili": "social_demand_signal",
    "qidian": "paid_trend_target",
}
# Compatibility alias for callers/tests that imported the old name. These sources
# are no longer "optional" in a comprehensive production scan.
REGISTERED_OPTIONAL_SOURCES = REGISTERED_PRODUCTION_SOURCES
REQUIRED_LONG_SOURCES = ("fanqie", "qimao", *REGISTERED_PRODUCTION_SOURCES.keys())
PAID_MARKDOWN_PLATFORMS = {"zongheng", "jjwxc"}
SOCIAL_PLATFORMS = {"xiaohongshu", "bilibili"}
SOCIAL_SIGNAL_TYPES = {
    "current_hotspot_or_rank_scan",
    "curator_roundup",
    "reader_demand_or_book_shortage",
    "negative_or_avoidance",
    "creator_market_analysis",
}
SOCIAL_REQUIRED_TYPE_COUNTS = {
    "current_hotspot_or_rank_scan": 2,
    "curator_roundup": 2,
    "reader_demand_or_book_shortage": 2,
    "negative_or_avoidance": 1,
}
SOCIAL_MIN_DISCOVERED = 30
SOCIAL_MIN_SCREENED = 15
SOCIAL_MIN_ELIGIBLE = 8
SOCIAL_MIN_UNIQUE_ACCOUNTS = 5
SOCIAL_MAX_PER_ACCOUNT = 2


def social_requirements(platform: str) -> dict[str, Any]:
    """Registered source-specific targets; Bilibili retains existing strict quotas."""
    if platform not in SOCIAL_PLATFORMS:
        raise ValueError("NOT_SOCIAL_PLATFORM")
    registry = load_json(
        Path(__file__).resolve().parents[1] / "references" / "source-registry.json"
    )
    source_id = {
        "xiaohongshu": "xiaohongshu_novel_demand_shared",
        "bilibili": "bilibili_novel_demand_shared",
    }[platform]
    return next(row["coverage"] for row in registry["sources"] if row["id"] == source_id)


def tier(age_days: int) -> str:
    if age_days == 0:
        return "current_run"
    if age_days > 0:
        return "historical_only"
    return "invalid_future_date"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_day(value: str) -> date:
    value = value.replace("-", "")
    return datetime.strptime(value, "%Y%m%d").date()


def newest_fanqie_dir(root: Path, target: date) -> Path | None:
    choices = []
    if not root.exists():
        return None
    for item in root.iterdir():
        if item.is_dir() and len(item.name) == 8 and item.name.isdigit():
            try:
                day = parse_day(item.name)
            except ValueError:
                continue
            if day <= target:
                choices.append((day, item))
    return max(choices, default=(None, None))[1]


def inspect_fanqie(root: Path, target: date) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    folder = newest_fanqie_dir(root, target)
    started = utc_now()
    if folder is None:
        summary = {"platform": "fanqie", "status": "not_run", "role": "formal_long_rank_gate", "acquisition_mode": "automated_public_with_local_decoder", "rank_completeness": "not_run", "sample_completeness": "not_run", "full_text_completeness": "not_acquired", "metadata_completeness": "not_run", "ranks": [], "errors": ["no dated data directory"], "started_at": started, "finished_at": utc_now()}
        return summary, []
    age_days = (target - parse_day(folder.name)).days
    rank_rows = []
    normalized = []
    for rank in sorted(FANQIE_RANKS):
        gender, rank_type = rank.split("/")
        path = folder / f"fanqie_{gender}_{rank_type}_{folder.name}.json"
        if not path.exists():
            rank_rows.append({"channel": rank, "status": "missing", "valid_entries": 0, "path": str(path.resolve())})
            continue
        try:
            payload = load_json(path)
            categories = payload.get("categories", []) if isinstance(payload, dict) else []
            empty = []
            parse_errors = []
            valid = 0
            for category in categories:
                books = category.get("books", []) if isinstance(category, dict) else []
                status = category.get("status") if isinstance(category, dict) else None
                if status and status not in {"success", "empty"}:
                    parse_errors.append({"category": category.get("name"), "status": status, "error": category.get("error")})
                if not books:
                    empty.append(category.get("name", "unknown"))
                for position, book in enumerate(books, 1):
                    if isinstance(book, dict) and book.get("title"):
                        valid += 1
                        normalized.append({
                            "platform": "fanqie", "gender": gender, "rank_type": rank_type,
                            "category": category.get("name"), "rank": position,
                            "title": book.get("title"), "author": book.get("author"),
                            "metric": book.get("reads"), "word_count": book.get("word_count"),
                            "status": book.get("status"), "updated_at": book.get("updated_at"),
                            "url": book.get("url"), "source_file": str(path.resolve()),
                            "signals": book.get("signals", {}),
                        })
            row_status = "success" if categories and valid and not empty and not parse_errors else "degraded"
            rank_rows.append({
                "channel": rank, "status": row_status, "category_count": len(categories),
                "valid_entries": valid, "empty_categories": empty, "parse_errors": parse_errors,
                "path": str(path.resolve()),
            })
        except (OSError, json.JSONDecodeError, AttributeError) as exc:
            rank_rows.append({"channel": rank, "status": "parse_error", "valid_entries": 0, "path": str(path.resolve()), "error": str(exc)})
    complete = {row["channel"] for row in rank_rows if row.get("status") == "success"}
    status = "success" if complete == FANQIE_RANKS and age_days <= PRIMARY_MAX_DAYS else "stale" if age_days > PRIMARY_MAX_DAYS else "degraded"
    return {
        "platform": "fanqie", "status": status, "snapshot_date": folder.name,
        "role": "formal_long_rank_gate", "acquisition_mode": "automated_public_with_local_decoder",
        "rank_completeness": "complete" if status == "success" else "partial",
        "sample_completeness": "metadata_only", "full_text_completeness": "not_acquired", "metadata_completeness": "partial",
        "age_days": age_days, "max_age_days": PRIMARY_MAX_DAYS, "current_tier": tier(age_days), "ranks": rank_rows,
        "valid_entries": len(normalized), "started_at": started, "finished_at": utc_now(),
        "errors": [row for row in rank_rows if row.get("status") != "success"],
    }, normalized


def inspect_qimao(path: Path | None, target: date) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    started = utc_now()
    if path is None or not path.exists():
        return {
            "platform": "qimao", "status": "not_run", "source_url": QIMAO_URL,
            "role": "formal_long_rank_gate", "acquisition_mode": "automated_public",
            "rank_completeness": "not_run", "sample_completeness": "not_run", "full_text_completeness": "not_acquired", "metadata_completeness": "not_run",
            "channels": [], "missing_channels": sorted(QIMAO_RANKS), "empty_channels": [],
            "parse_errors": ["structured qimao input not supplied"], "valid_entries": 0,
            "started_at": started, "finished_at": utc_now(),
        }, []
    try:
        payload = load_json(path)
        entries = payload.get("entries", []) if isinstance(payload, dict) else payload
        retrieved = payload.get("retrieved_at") if isinstance(payload, dict) else None
        retrieved_day = parse_day((retrieved or target.isoformat())[:10])
        age_days = (target - retrieved_day).days
        if not isinstance(entries, list):
            raise ValueError("qimao input must contain entries[]")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "platform": "qimao", "status": "parse_error", "source_url": QIMAO_URL,
            "role": "formal_long_rank_gate", "acquisition_mode": "automated_public",
            "rank_completeness": "not_acquired", "sample_completeness": "not_acquired", "full_text_completeness": "not_acquired", "metadata_completeness": "not_acquired",
            "channels": [], "missing_channels": sorted(QIMAO_RANKS), "empty_channels": [],
            "parse_errors": [str(exc)], "valid_entries": 0, "started_at": started, "finished_at": utc_now(),
        }, []
    grouped: dict[str, list[dict[str, Any]]] = {key: [] for key in QIMAO_RANKS}
    errors = []
    normalized = []
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append("non-object entry")
            continue
        channel = f"{entry.get('gender')}/{entry.get('rank_type')}"
        if channel not in grouped:
            errors.append(f"unknown channel:{channel}")
            continue
        if not entry.get("title") or not isinstance(entry.get("rank"), int):
            errors.append(f"invalid entry:{channel}:{entry.get('title')}")
            continue
        item = {
            "platform": "qimao", "gender": entry.get("gender"), "rank_type": entry.get("rank_type"),
            "rank": entry.get("rank"), "title": entry.get("title"), "author": entry.get("author"),
            "metric": entry.get("heat"), "word_count": entry.get("word_count"),
            "category": entry.get("category"), "status": entry.get("status"),
            "updated_at": entry.get("updated_at"), "url": entry.get("url"),
            "source_file": str(path.resolve()), "signals": entry.get("signals", {}),
        }
        grouped[channel].append(item)
        normalized.append(item)
    channels = [{"channel": key, "valid_entries": len(value), "status": "success" if value else "empty"} for key, value in sorted(grouped.items())]
    missing = sorted(QIMAO_RANKS - {key for key, value in grouped.items() if value})
    status = "success" if not missing and not errors and age_days <= PRIMARY_MAX_DAYS else "stale" if age_days > PRIMARY_MAX_DAYS else "degraded"
    return {
        "platform": "qimao", "status": status, "source_url": QIMAO_URL,
        "role": "formal_long_rank_gate", "acquisition_mode": "automated_public",
        "rank_completeness": "complete" if status == "success" else "partial",
        "sample_completeness": "metadata_only", "full_text_completeness": "not_acquired", "metadata_completeness": "partial",
        "snapshot_date": retrieved_day.isoformat(), "age_days": age_days, "max_age_days": PRIMARY_MAX_DAYS, "current_tier": tier(age_days),
        "channels": channels, "missing_channels": missing,
        "empty_channels": [item["channel"] for item in channels if item["status"] == "empty"],
        "parse_errors": errors, "valid_entries": len(normalized),
        "started_at": started, "finished_at": utc_now(), "source_file": str(path.resolve()),
    }, normalized


def snapshot_timing(snapshot_date: str | None, target: date) -> dict[str, Any]:
    if not snapshot_date:
        return {"snapshot_date": None, "age_days": None, "max_age_days": PRIMARY_MAX_DAYS, "current_tier": "unknown"}
    source_day = parse_day(snapshot_date[:10])
    age_days = (target - source_day).days
    return {
        "snapshot_date": source_day.isoformat(),
        "age_days": age_days,
        "max_age_days": PRIMARY_MAX_DAYS,
        "current_tier": tier(age_days),
    }


def inspect_paid_markdown(platform: str, path: Path, target: date) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    started = utc_now()
    text = path.read_text(encoding="utf-8")
    if platform == "zongheng":
        normalized = RANK_SCRAPER.parse_zongheng_snapshot(text)
    else:
        normalized = RANK_SCRAPER.parse_jjwxc_snapshot(text)
    metadata = RANK_SCRAPER.snapshot_metadata(text)
    timing = snapshot_timing(metadata.get("snapshot_date"), target)
    for item in normalized:
        item["source_file"] = str(path.resolve())
    if not normalized:
        status = "degraded"
    elif isinstance(timing["age_days"], int) and timing["age_days"] > PRIMARY_MAX_DAYS:
        status = "stale"
    else:
        status = "success"
    return {
        "platform": platform,
        "status": status,
        "role": "paid_platform_corroboration",
        "acquisition_mode": "automated_public",
        "source_url": metadata.get("source_url"),
        "source_file": str(path.resolve()),
        **timing,
        "rank_completeness": "complete_for_recorded_snapshot" if normalized else "not_acquired",
        "sample_completeness": "metadata_only",
        "full_text_completeness": "not_acquired",
        "metadata_completeness": "title_rank_metric" if platform == "zongheng" else "title_author_category_word_count_points",
        "valid_entries": len(normalized),
        "signal_eligible_entries": len(normalized),
        "errors": [] if normalized else ["no paid-platform rank entries parsed"],
        "started_at": started,
        "finished_at": utc_now(),
    }, normalized


def canonical_social_key(url: str) -> str:
    return url.split("?", 1)[0].rstrip("/").casefold()


def social_original_entry(item: dict[str, Any], platform: str, path: Path, position: int) -> dict[str, Any] | None:
    source_url = item.get("source_url") or item.get("url")
    published_at = item.get("published_at")
    engagement = item.get("engagement")
    content = item.get("full_text") or item.get("content") or item.get("transcript")
    content_complete = item.get("content_complete") is True or item.get("full_text_completeness") == "complete"
    images_total = item.get("images_total")
    images_read = item.get("images_read")
    author = str(item.get("author") or "").strip()
    primary_signal_type = item.get("primary_signal_type")
    source_relation = item.get("source_relation") or "independent"
    if images_total is not None and images_read != images_total:
        content_complete = False
    if (
        not source_url
        or not published_at
        or not isinstance(engagement, dict)
        or not engagement
        or not content
        or not content_complete
        or not author
        or primary_signal_type not in SOCIAL_SIGNAL_TYPES
    ):
        return None
    numeric_engagement = [value for value in engagement.values() if isinstance(value, (int, float)) and not isinstance(value, bool)]
    if not numeric_engagement:
        return None
    signal_eligible = item.get("signal_eligible", True) is True
    if source_relation == "official_rank_repost" and item.get("original_analysis") is not True:
        signal_eligible = False
    canonical_key = canonical_social_key(str(source_url))
    return {
        "evidence_id": item.get("evidence_id") or f"{platform}:{canonical_key}",
        "platform": platform,
        "gender": item.get("gender") or "mixed",
        "rank_type": "social_demand",
        "category": item.get("category"),
        "rank": item.get("rank") if isinstance(item.get("rank"), int) else position,
        "title": item.get("title") or str(content)[:40],
        "author": author,
        "author_id": item.get("author_id"),
        "metric": sum(numeric_engagement),
        "metric_type": "engagement_total",
        "word_count": None,
        "url": source_url,
        "published_at": published_at,
        "content_evidence": content,
        "engagement": engagement,
        "evidence_layer": "social_demand_signal",
        "primary_signal_type": primary_signal_type,
        "source_relation": source_relation,
        "signal_eligible": signal_eligible,
        "heat_increment": 1 if signal_eligible else 0,
        "source_file": str(path.resolve()),
        "signals": item.get("signals", {}),
    }


def inspect_social(platform: str, path: Path, target: date) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    started = utc_now()
    if path.suffix.lower() == ".md":
        text = path.read_text(encoding="utf-8")
        detail = RANK_SCRAPER.parse_social_summary(text, platform)
        timing = snapshot_timing(detail.get("snapshot_date"), target)
        return {
            "platform": platform,
            "status": "degraded",
            "role": "social_demand_signal",
            "acquisition_mode": "automated_public_search_summary",
            "source_file": str(path.resolve()),
            **timing,
            "rank_completeness": "not_applicable",
            "sample_completeness": "metadata_only",
            "full_text_completeness": "not_acquired",
            "metadata_completeness": "search_summary_without_original_content",
            "valid_entries": len(detail["summary_items"]),
            "signal_eligible_entries": 0,
            "queries": detail["queries"],
            "limitations": detail["limitations"],
            "errors": ["summary-only evidence excluded from the signal matrix"],
            "started_at": started,
            "finished_at": utc_now(),
        }, []
    payload = load_json(path)
    raw_entries = payload.get("entries", []) if isinstance(payload, dict) else payload
    if not isinstance(raw_entries, list):
        raise ValueError("social original input must contain entries[]")
    discovery = payload.get("discovery", {}) if isinstance(payload, dict) else {}
    discovered_unique = int(discovery.get("discovered_unique_entries") or 0)
    screened_entries = int(discovery.get("screened_entries") or 0)
    complete_rows = []
    seen_evidence_ids = set()
    duplicate_count = 0
    for position, item in enumerate(raw_entries, 1):
        row = social_original_entry(item, platform, path, position) if isinstance(item, dict) else None
        if row is None:
            continue
        if row["evidence_id"] in seen_evidence_ids:
            duplicate_count += 1
            continue
        seen_evidence_ids.add(row["evidence_id"])
        complete_rows.append(row)
    invalid_count = len(raw_entries) - len(complete_rows) - duplicate_count
    normalized = [row for row in complete_rows if row["signal_eligible"]]
    author_counts = Counter((row.get("author_id") or row["author"]).casefold() for row in normalized)
    signal_type_counts = Counter(row["primary_signal_type"] for row in normalized)
    max_entries_per_account = max(author_counts.values(), default=0)
    context_only_count = len(complete_rows) - len(normalized)
    errors = []
    if invalid_count:
        errors.append(f"{invalid_count} entries missing original URL/time/engagement/complete content/author/signal type")
    if duplicate_count:
        errors.append(f"{duplicate_count} duplicate canonical evidence entries removed")
    return {
        "platform": platform,
        "status": "success" if complete_rows and invalid_count == 0 else "degraded",
        "role": "social_demand_signal",
        "acquisition_mode": "authenticated_reproducible_or_manual" if platform == "xiaohongshu" else "automated_public_or_authenticated_reproducible",
        "source_file": str(path.resolve()),
        "rank_completeness": "not_applicable",
        "sample_completeness": "complete" if complete_rows and invalid_count == 0 else "partial",
        "full_text_completeness": "complete" if complete_rows and invalid_count == 0 else "partial",
        "metadata_completeness": "original_url_time_engagement_content",
        "valid_entries": len(raw_entries),
        "discovered_unique_entries": discovered_unique,
        "screened_entries": screened_entries,
        "complete_content_entries": len(complete_rows),
        "signal_eligible_entries": len(normalized),
        "unique_accounts": len(author_counts),
        "max_entries_per_account": max_entries_per_account,
        "primary_signal_type_counts": dict(signal_type_counts),
        "context_only_rank_reposts": context_only_count,
        "duplicate_evidence_entries": duplicate_count,
        "errors": errors,
        "started_at": started,
        "finished_at": utc_now(),
    }, normalized


def inspect_optional(spec: str, target: date) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if "=" not in spec:
        raise ValueError("--source must be PLATFORM=PATH")
    platform, raw_path = spec.split("=", 1)
    path = Path(raw_path)
    started = utc_now()
    if not path.exists():
        return {"platform": platform, "status": "not_run", "role": REGISTERED_OPTIONAL_SOURCES.get(platform, "registered_optional"), "source_file": str(path), "rank_completeness": "not_run", "sample_completeness": "not_run", "full_text_completeness": "not_acquired", "metadata_completeness": "not_run", "valid_entries": 0, "signal_eligible_entries": 0, "errors": ["missing file"], "started_at": started, "finished_at": utc_now()}, []
    try:
        if platform in PAID_MARKDOWN_PLATFORMS and path.suffix.lower() == ".md":
            return inspect_paid_markdown(platform, path, target)
        if platform in SOCIAL_PLATFORMS:
            return inspect_social(platform, path, target)
        payload = load_json(path)
        entries = payload.get("entries", []) if isinstance(payload, dict) else payload
        if not isinstance(entries, list):
            raise ValueError("entries must be a list")
        normalized = [dict(item, platform=platform, source_file=str(path.resolve())) for item in entries if isinstance(item, dict) and item.get("title")]
        return {"platform": platform, "status": "success" if normalized else "degraded", "role": REGISTERED_OPTIONAL_SOURCES.get(platform, "registered_optional"), "acquisition_mode": "automated_public", "source_file": str(path.resolve()), "rank_completeness": "complete_for_returned_list" if normalized else "not_acquired", "sample_completeness": "metadata_only", "full_text_completeness": "not_acquired", "metadata_completeness": "partial", "valid_entries": len(normalized), "signal_eligible_entries": len(normalized), "errors": [] if normalized else ["no valid entries"], "started_at": started, "finished_at": utc_now()}, normalized
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"platform": platform, "status": "parse_error", "role": REGISTERED_OPTIONAL_SOURCES.get(platform, "registered_optional"), "source_file": str(path.resolve()), "rank_completeness": "not_acquired", "sample_completeness": "not_acquired", "full_text_completeness": "not_acquired", "metadata_completeness": "not_acquired", "valid_entries": 0, "signal_eligible_entries": 0, "errors": [str(exc)], "started_at": started, "finished_at": utc_now()}, []


def missing_registered_source(platform: str) -> dict[str, Any]:
    return {
        "platform": platform,
        "status": "not_acquired" if platform == "qidian" else "not_run",
        "role": REGISTERED_PRODUCTION_SOURCES[platform],
        "rank_completeness": "not_acquired" if platform == "qidian" else "not_run",
        "sample_completeness": "not_acquired" if platform == "qidian" else "not_run",
        "full_text_completeness": "not_acquired" if platform == "qidian" else "not_run",
        "metadata_completeness": "not_acquired" if platform == "qidian" else "not_run",
        "valid_entries": 0,
        "signal_eligible_entries": 0,
        "errors": ["no independent structured current artifact"] if platform == "qidian" else ["registered source input not supplied"],
        "started_at": utc_now(),
        "finished_at": utc_now(),
    }


def source_gate_reasons(sources: list[dict[str, Any]]) -> list[str]:
    by_platform = {item.get("platform"): item for item in sources}
    reasons = []
    for platform in REQUIRED_LONG_SOURCES:
        item = by_platform.get(platform, {})
        status = item.get("status", "missing")
        if status != "success":
            reasons.append(f"{platform}:{status}")
            continue
        if platform in SOCIAL_PLATFORMS:
            required = social_requirements(platform)
            for field, limit, reason in (
                ("discovered_unique_entries", "min_discovered_unique_entries", "discovery_shortfall"),
                ("screened_entries", "min_screened_entries", "screening_shortfall"),
                ("signal_eligible_entries", "min_signal_eligible_entries", "complete_signal_shortfall"),
                ("unique_accounts", "min_unique_accounts", "account_diversity_shortfall"),
            ):
                if int(item.get(field) or 0) < int(required.get(limit, 0)):
                    reasons.append(f"{platform}:{reason}")
            if int(item.get("max_entries_per_account") or 0) > int(required.get("max_signal_entries_per_account", 999999)):
                reasons.append(f"{platform}:account_concentration_exceeded")
            observed_types = item.get("primary_signal_type_counts") or {}
            for signal_type, minimum in required.get("required_primary_signal_type_counts", {}).items():
                if int(observed_types.get(signal_type) or 0) < minimum:
                    reasons.append(f"{platform}:signal_type_shortfall:{signal_type}")
        elif platform not in {"fanqie", "qimao"} and int(item.get("valid_entries") or 0) < 1:
            reasons.append(f"{platform}:no_valid_entries")
    return reasons


def build_manifest(target: date, sources: list[dict[str, Any]], data_file: Path) -> dict[str, Any]:
    reasons = source_gate_reasons(sources)
    formal_ready = not reasons
    status_by_platform = {item.get("platform"): item.get("status") for item in sources}
    return {
        "schema_version": 2, "lane": "long", "date": target.isoformat(),
        "generated_at": utc_now(), "formal_candidate_generation": "allowed" if formal_ready else "not_run",
        "formal_gate_reasons": reasons,
        "coverage": {
            "profile": "comprehensive_production",
            "required_sources": list(REQUIRED_LONG_SOURCES),
            "successful_sources": [name for name in REQUIRED_LONG_SOURCES if status_by_platform.get(name) == "success"],
            "missing_or_degraded_sources": reasons,
        },
        "normalized_data_file": str(data_file.resolve()), "sources": sources,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="YYYYMMDD")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fanqie-data-root", type=Path, required=True)
    parser.add_argument("--qimao-json", type=Path, required=True)
    parser.add_argument("--source", action="append", default=[], help="Additional PLATFORM=PATH input; paid-platform/social markdown and normalized JSON are supported")
    parser.add_argument("--run-fanqie", action="store_true")
    parser.add_argument("--fanqie-config", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    target = parse_day(args.date)
    args.output.mkdir(parents=True, exist_ok=True)
    if args.run_fanqie:
        cmd = [sys.executable, str(Path(__file__).with_name("fanqie_refresh.py")), "--output-root", str(args.fanqie_data_root), "--date", args.date]
        if args.fanqie_config:
            cmd.extend(["--config", str(args.fanqie_config)])
        subprocess.run(cmd, check=False)
    fanqie_summary, fanqie_data = inspect_fanqie(args.fanqie_data_root, target)
    qimao_summary, qimao_data = inspect_qimao(args.qimao_json, target)
    sources = [fanqie_summary, qimao_summary]
    normalized = fanqie_data + qimao_data
    for spec in args.source:
        summary, data = inspect_optional(spec, target)
        sources.append(summary)
        normalized.extend(data)
    present = {item["platform"] for item in sources}
    for platform in REGISTERED_OPTIONAL_SOURCES:
        if platform not in present:
            sources.append(missing_registered_source(platform))
    data_file = args.output / f"long_source_data_{args.date}.json"
    save_json(data_file, {"schema_version": 1, "date": target.isoformat(), "entries": normalized})
    manifest = build_manifest(target, sources, data_file)
    manifest_path = args.output / f"long_source_manifest_{args.date}.json"
    save_json(manifest_path, manifest)
    collection = {
        "schema_version": 1, "date": target.isoformat(), "started_at": min((item.get("started_at", utc_now()) for item in sources), default=utc_now()),
        "finished_at": utc_now(), "platform_status": {item["platform"]: item["status"] for item in sources},
        "valid_entries": len(normalized), "errors": {item["platform"]: item.get("errors") or item.get("parse_errors") for item in sources if item.get("status") != "success"},
        "formal_candidate_generation": manifest["formal_candidate_generation"],
    }
    save_json(args.output / f"collection_summary_{args.date}.json", collection)
    print(json.dumps({"manifest": str(manifest_path), "collection": collection}, ensure_ascii=False, indent=2))
    return 0 if manifest["formal_candidate_generation"] == "allowed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
