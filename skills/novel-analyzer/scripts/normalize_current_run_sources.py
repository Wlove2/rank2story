#!/usr/bin/env python3
"""Normalize the registered long-form collectors directly from one current run."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SOCIAL_PATH = Path(__file__).with_name("social_evidence.py")
SOCIAL_SPEC = importlib.util.spec_from_file_location("social_evidence_for_current_normalizer", SOCIAL_PATH)
if SOCIAL_SPEC is None or SOCIAL_SPEC.loader is None:
    raise RuntimeError(f"cannot load {SOCIAL_PATH}")
SOCIAL = importlib.util.module_from_spec(SOCIAL_SPEC)
sys.modules[SOCIAL_SPEC.name] = SOCIAL
SOCIAL_SPEC.loader.exec_module(SOCIAL)


GROUPS = {
    "fanqie": ("fanqie_public_web_ranks", "fanqie_reader_novel_rank_center"),
    "qimao": ("qimao_public_web_ranks", "qimao_reader_rank_center"),
    "zongheng": ("zongheng_public_rank_snapshot",),
    "jjwxc": ("jjwxc_quarter_rank_snapshot",),
    "qidian": ("qidian_paid_trend_target",),
    "xiaohongshu": ("xiaohongshu_novel_demand_shared",),
    "bilibili": ("bilibili_novel_demand_shared",),
}
SOCIAL_SOURCE_IDS = {
    "xiaohongshu": "xiaohongshu_novel_demand_shared",
    "bilibili": "bilibili_novel_demand_shared",
}

REGISTRY_PATH = Path(__file__).resolve().parents[1] / "references" / "source-registry.json"


def social_coverage(source_id: str) -> dict[str, Any]:
    registry = load_json(REGISTRY_PATH)
    return next(row["coverage"] for row in registry["sources"] if row["id"] == source_id)

ID_KEYS = ("book_id", "bookId", "bookid", "novel_id", "story_id", "id")
TITLE_KEYS = ("title", "book_name", "bookName", "novel_name")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def first(row: dict[str, Any], keys: Iterable[str]) -> Any:
    return next((row.get(key) for key in keys if row.get(key) not in (None, "")), None)


def book_records(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, list):
        for item in value:
            yield from book_records(item)
        return
    if not isinstance(value, dict):
        return
    title = first(value, TITLE_KEYS)
    item_id = first(value, ID_KEYS)
    book_shape = any(value.get(key) not in (None, "") for key in (
        "author", "author_name", "rank", "position", "intro", "description",
        "word_count", "word_number", "book_url", "book_id", "bookId", "novel_id",
    ))
    if title and book_shape and (item_id is not None or value.get("url") or value.get("book_url")):
        yield value
    for child in value.values():
        if isinstance(child, (dict, list)):
            yield from book_records(child)


def candidate_files(source_dir: Path) -> list[Path]:
    files = sorted(path for path in source_dir.rglob("*.json") if path.is_file() and path.stat().st_size > 0)
    normalized_02 = [path for path in files if "normalized_02" in path.name]
    if normalized_02:
        return normalized_02
    normalized = [path for path in files if "normalized" in path.name and "manifest" not in path.name]
    return normalized or [path for path in files if "manifest" not in path.name and "summary" not in path.name and "state" not in path.name]


def normalize_source(platform: str, source_id: str, source_dir: Path, run_id: str) -> tuple[list[dict[str, Any]], list[str]]:
    rows: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for path in candidate_files(source_dir):
        try:
            payload = load_json(path)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path.name}: {exc}")
            continue
        for record in book_records(payload):
            item_id = str(first(record, ID_KEYS) or first(record, ("url", "book_url", "source_url")))
            title = str(first(record, TITLE_KEYS))
            key = f"{source_id}:{item_id}"
            rows.setdefault(key, {
                "evidence_id": key,
                "manifest_id": f"{run_id}:{source_id}",
                "source_item_id": item_id,
                "platform": platform,
                "source_product": source_id,
                "source_file": str(path.resolve()),
                "title": title,
                "author": first(record, ("author", "author_name", "authorName")),
                "gender": first(record, ("gender", "channel", "category_type")),
                "rank_type": first(record, ("rank_type", "rank_name", "algorithm", "list_id")),
                "category": first(record, ("category", "category_name", "genre", "tag")),
                "rank": first(record, ("rank", "position", "index", "rank_no")),
                "intro": first(record, ("intro", "description", "summary", "book_abstract")),
                "current": True,
            })
    return list(rows.values()), errors


def build(run_manifest: dict[str, Any], acquisition: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    run_id = str(run_manifest.get("run_id") or acquisition.get("run_id") or "unknown")
    acquired = {row.get("source_id"): row for row in acquisition.get("sources", []) if isinstance(row, dict)}
    source_dirs = run_manifest.get("paths", {}).get("source_dirs", {})
    all_entries: list[dict[str, Any]] = []
    source_rows = []
    gate_reasons = []
    for platform, source_ids in GROUPS.items():
        missing = [source_id for source_id in source_ids if acquired.get(source_id, {}).get("status") != "success"]
        errors: list[str] = []
        entries: list[dict[str, Any]] = []
        social_audit: dict[str, Any] | None = None
        if platform in SOCIAL_SOURCE_IDS:
            source_id = SOCIAL_SOURCE_IDS[platform]
            source_dir = Path(str(source_dirs.get(source_id) or ""))
            coverage = social_coverage(source_id)
            social_audit = SOCIAL.audit_social_files(
                source_id, source_dir.rglob("*.json") if source_dir.is_dir() else [],
                max_entries_per_account=int(coverage.get("max_signal_entries_per_account", 2)),
            )
            entries = social_audit["eligible_entries"]
            errors.extend(f"{key}: {count}" for key, count in social_audit["invalid_entry_reasons"].items())
        else:
            for source_id in source_ids:
                source_dir = Path(str(source_dirs.get(source_id) or ""))
                normalized, parse_errors = normalize_source(platform, source_id, source_dir, run_id)
                entries.extend(normalized)
                errors.extend(parse_errors)
        social_complete = True
        if social_audit is not None:
            counts = social_audit.get("primary_signal_type_counts", {})
            social_complete = (
                social_audit.get("discovered_unique_entries", 0)
                >= int(coverage.get("min_discovered_unique_entries", 0))
                and social_audit.get("screened_entries", 0)
                >= int(coverage.get("min_screened_entries", 0))
                and social_audit.get("signal_eligible_entries", 0)
                >= int(coverage.get("min_signal_eligible_entries", 0))
                and social_audit.get("unique_accounts", 0)
                >= int(coverage.get("min_unique_accounts", 0))
                and social_audit.get("max_entries_per_account", 0)
                <= int(coverage.get("max_signal_entries_per_account", 999999))
                and all(
                    counts.get(kind, 0) >= minimum
                    for kind, minimum in coverage.get("required_primary_signal_type_counts", {}).items()
                )
            )
        status = "success" if not missing and entries and social_complete else "degraded"
        if status != "success":
            gate_reasons.append(f"{platform}:{'missing_or_degraded_acquisition' if missing else 'no_normalized_entries'}")
        source_rows.append({
            "platform": platform,
            "source_ids": list(source_ids),
            "status": status,
            "valid_entries": len(entries),
            "signal_eligible_entries": len(entries),
            "errors": errors,
        })
        all_entries.extend(entries)
    data = {"schema_version": 3, "lane": "long", "run_id": run_id, "entries": all_entries}
    manifest = {
        "schema_version": 3,
        "lane": "long",
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "formal_candidate_generation": "allowed" if not gate_reasons else "not_run",
        "formal_gate_reasons": gate_reasons,
        "sources": source_rows,
    }
    return data, manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-manifest", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    run_manifest = load_json(args.run_manifest)
    manifest_path = args.manifest or Path(run_manifest["paths"]["files"]["acquisition_manifest"])
    data, manifest = build(run_manifest, load_json(manifest_path))
    args.output.mkdir(parents=True, exist_ok=True)
    data_path = args.output / f"long_source_data_{args.date}.json"
    manifest_path_out = args.output / f"long_source_manifest_{args.date}.json"
    manifest["normalized_data_file"] = str(data_path.resolve())
    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_path_out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "data": str(data_path), "manifest": str(manifest_path_out),
        "formal_candidate_generation": manifest["formal_candidate_generation"],
        "counts": {row["platform"]: row["valid_entries"] for row in manifest["sources"]},
    }, ensure_ascii=False, indent=2))
    return 0 if manifest["formal_candidate_generation"] == "allowed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
