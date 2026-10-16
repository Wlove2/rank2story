#!/usr/bin/env python3
"""Deterministically audit complete social evidence saved by registered workflows."""

from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit


SIGNAL_TYPES = {
    "current_hotspot_or_rank_scan",
    "curator_roundup",
    "reader_demand_or_book_shortage",
    "negative_or_avoidance",
    "creator_market_analysis",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_url(value: str) -> str:
    parts = urlsplit(value.strip())
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), "", ""))


def payload_entries(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("entries", "items", "notes", "videos", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    if any(key in payload for key in ("source_url", "url", "full_text", "content", "transcript")):
        return [payload]
    return []


def discovery_counts(payload: Any) -> tuple[int, int]:
    if not isinstance(payload, dict):
        return 0, 0
    discovery = payload.get("discovery") if isinstance(payload.get("discovery"), dict) else payload
    discovered = int(discovery.get("discovered_unique_entries") or 0)
    screened = int(discovery.get("screened_entries") or 0)
    return discovered, screened


def numeric_engagement(item: dict[str, Any]) -> dict[str, int | float]:
    engagement = item.get("engagement")
    if isinstance(engagement, dict):
        return {
            str(key): value
            for key, value in engagement.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }
    aliases = ("likes", "collects", "comments", "shares", "views", "score")
    return {
        key: item[key]
        for key in aliases
        if isinstance(item.get(key), (int, float)) and not isinstance(item.get(key), bool)
    }


def complete_entry(item: dict[str, Any], source_id: str) -> tuple[dict[str, Any] | None, str | None]:
    url = str(item.get("source_url") or item.get("url") or "").strip()
    author = str(item.get("author") or "").strip()
    published_at = str(item.get("published_at") or "").strip()
    signal_type = item.get("primary_signal_type") or item.get("signal_type")
    content = item.get("full_text") or item.get("content") or item.get("transcript")
    content = str(content or "").strip()
    engagement = numeric_engagement(item)
    if not url or not author or not published_at:
        return None, "missing URL, author, or published_at"
    if signal_type not in SIGNAL_TYPES:
        return None, "missing or invalid primary_signal_type"
    if not engagement:
        return None, "missing numeric engagement"
    if item.get("content_complete") is not True:
        return None, "content_complete is not true"
    if not content:
        return None, "full content/transcript missing"
    if source_id == "bilibili_novel_demand_shared" and len(content) < 200:
        return None, "transcript is only an excerpt"
    if source_id == "xiaohongshu_novel_demand_shared":
        images_total = item.get("images_total")
        images_read = item.get("images_read")
        if not isinstance(images_total, int) or not isinstance(images_read, int) or images_read != images_total:
            return None, "image completeness is not attested"
    relation = item.get("source_relation") or "independent"
    signal_eligible = item.get("signal_eligible", True) is True
    if relation == "official_rank_repost" and item.get("original_analysis") is not True:
        signal_eligible = False
    key = canonical_url(url)
    return {
        "evidence_id": str(item.get("evidence_id") or f"{source_id}:{key}"),
        "manifest_id": str(item.get("manifest_id") or source_id),
        "source_item_id": str(item.get("source_item_id") or item.get("note_id") or item.get("bvid") or key),
        "source_id": source_id,
        "kind": "social_post",
        "source": url,
        "url": url,
        "title": item.get("title"),
        "author": author,
        "author_id": item.get("author_id"),
        "published_at": published_at,
        "engagement": engagement,
        "full_text": content,
        "content_complete": True,
        "content_status": "complete",
        "primary_signal_type": signal_type,
        "source_relation": relation,
        "signal_eligible": signal_eligible,
        "current": True,
    }, None


def social_age_days(published_at: str, as_of_date: date) -> int | None:
    """Measure the source's age in UTC calendar days; unknown dates fail closed."""
    try:
        published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        if published.tzinfo is not None:
            published = published.astimezone(timezone.utc)
        return (as_of_date - published.date()).days
    except (ValueError, OverflowError):
        return None


def audit_social_files(
    source_id: str, paths: Iterable[Path], *, max_entries_per_account: int | None = None,
    max_age_days: int | None = None, as_of_date: str | None = None,
) -> dict[str, Any]:
    if max_age_days is not None:
        if type(max_age_days) is not int or max_age_days < 0 or not as_of_date:
            raise ValueError("SOCIAL_FRESHNESS_POLICY_INVALID")
        try:
            reference_day = date.fromisoformat(as_of_date)
        except ValueError as exc:
            raise ValueError("SOCIAL_FRESHNESS_POLICY_INVALID") from exc
    else:
        reference_day = None
    discovered = screened = 0
    candidates: list[dict[str, Any]] = []
    parse_errors: list[str] = []
    for path in paths:
        if path.suffix.lower() != ".json" or not path.is_file():
            continue
        try:
            payload = load_json(path)
        except (OSError, json.JSONDecodeError) as exc:
            parse_errors.append(f"{path.name}: {exc}")
            continue
        found, selected = discovery_counts(payload)
        discovered = max(discovered, found)
        screened = max(screened, selected)
        candidates.extend(payload_entries(payload))

    # Multiple real batches may overlap. Count a screened URL only once,
    # rather than inflating screen counts by adding file-level metadata.
    unique_screened_urls = {
        canonical_url(str(item.get("source_url") or item.get("url") or ""))
        for item in candidates
        if str(item.get("source_url") or item.get("url") or "").startswith("https://")
    }
    screened = max(screened, len(unique_screened_urls))
    valid_by_url: dict[str, dict[str, Any]] = {}
    invalid_reasons: Counter[str] = Counter()
    for item in candidates:
        normalized, reason = complete_entry(item, source_id)
        if normalized is None:
            if reason:
                invalid_reasons[reason] += 1
            continue
        if normalized["signal_eligible"] and reference_day is not None:
            age_days = social_age_days(normalized["published_at"], reference_day)
            if age_days is None or age_days < 0 or age_days > max_age_days:
                invalid_reasons["SOCIAL_ENTRY_OUTSIDE_FRESHNESS_WINDOW"] += 1
                continue
        valid_by_url.setdefault(canonical_url(normalized["url"]), normalized)
    complete = list(valid_by_url.values())
    eligible = []
    account_counts: Counter[str] = Counter()
    over_account_cap = 0
    for item in complete:
        if not item["signal_eligible"]:
            continue
        account = str(item.get("author_id") or item["author"]).casefold()
        if max_entries_per_account is not None and account_counts[account] >= max_entries_per_account:
            over_account_cap += 1
            # Retain complete source provenance, but do not double-count this
            # author's third+ submission toward a diversified market sample.
            item["signal_eligible"] = False
            continue
        account_counts[account] += 1
        eligible.append(item)
    accounts = Counter(str(item.get("author_id") or item["author"]).casefold() for item in eligible)
    types = Counter(item["primary_signal_type"] for item in eligible)
    return {
        "discovered_unique_entries": discovered,
        "screened_entries": screened,
        "complete_content_entries": len(complete),
        "signal_eligible_entries": len(eligible),
        "unique_accounts": len(accounts),
        "max_entries_per_account": max(accounts.values(), default=0),
        "excluded_over_account_cap": over_account_cap,
        "primary_signal_type_counts": dict(types),
        "eligible_entries": eligible,
        "invalid_entry_reasons": dict(invalid_reasons),
        "parse_errors": parse_errors,
        "social_freshness_checked": reference_day is not None,
    }
