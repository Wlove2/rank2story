#!/usr/bin/env python3
"""Rebuild acquisition source records from current-run collector artifacts."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "references" / "source-registry.json"
SOCIAL_IDS = {"xiaohongshu_novel_demand_shared", "bilibili_novel_demand_shared"}

SOCIAL_PATH = Path(__file__).with_name("social_evidence.py")
SOCIAL_SPEC = importlib.util.spec_from_file_location("social_evidence_for_manifest_sync", SOCIAL_PATH)
if SOCIAL_SPEC is None or SOCIAL_SPEC.loader is None:
    raise RuntimeError(f"cannot load {SOCIAL_PATH}")
SOCIAL = importlib.util.module_from_spec(SOCIAL_SPEC)
sys.modules[SOCIAL_SPEC.name] = SOCIAL
SOCIAL_SPEC.loader.exec_module(SOCIAL)

def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def iso_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def artifacts(run_root: Path, source_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(item for item in source_dir.rglob("*") if item.is_file() and item.stat().st_size > 0):
        rows.append({
            "path": path.resolve().relative_to(run_root.resolve()).as_posix(),
            "artifact_type": "raw_response",
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "file_mtime": iso_mtime(path),
        })
    return rows


def collector_manifest(source_dir: Path) -> dict[str, Any]:
    path = source_dir / "manifest.json"
    return load_json(path) if path.is_file() else {}


def qidian_lists(source_dir: Path) -> list[str]:
    """Trust only actual registered ranking captures with valid raw-file hashes.

    The collector writes raw_<list_id>_<repeat>.json and captures[].list_id;
    filename-prefix probing previously failed even when all five lists existed.
    """
    expected_urls = {
        "monthly_ticket": "https://www.qidian.com/rank/yuepiao/",
        "hot_sales": "https://www.qidian.com/rank/hotsales/",
        "read_index": "https://www.qidian.com/rank/readindex/",
        "recommendation": "https://www.qidian.com/rank/recom/",
        "new_book": "https://www.qidian.com/rank/signNewBkAll/",
    }
    manifest = collector_manifest(source_dir)
    allowed = set(manifest.get("required_list_ids") or [])
    valid: set[str] = set()
    for capture in manifest.get("captures") or []:
        if not isinstance(capture, dict):
            continue
        kind = str(capture.get("list_id") or "")
        filename = str(capture.get("raw_file") or "")
        if kind not in expected_urls or kind not in allowed:
            continue
        if (
            capture.get("final_url") != expected_urls[kind]
            or not filename.startswith(f"raw_{kind}_")
            or Path(filename).name != filename
            or not filename.endswith(".json")
        ):
            continue
        path = source_dir / filename
        if not path.is_file() or sha256_file(path) != capture.get("raw_sha256"):
            continue
        try:
            raw = load_json(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        entries = raw.get("items") if isinstance(raw, dict) else None
        if (
            raw.get("url") != expected_urls[kind]
            or not isinstance(entries, list)
            or len(entries) < 20
            or not str(capture.get("item_count") or "").isdigit()
            or int(capture.get("item_count")) != len(entries)
        ):
            continue
        if not all(
            isinstance(item, dict)
            and bool(str(item.get("title") or "").strip())
            and str(item.get("url") or "").startswith("https://www.qidian.com/book/")
            for item in entries
        ):
            continue
        if len({item["url"] for item in entries}) < 20:
            continue
        valid.add(kind)
    return [key for key in expected_urls if key in valid]


def public_fanqie(source_dir: Path) -> dict[str, Any]:
    summaries = list(source_dir.glob("*/collection_summary.json")) + list(source_dir.glob("collection_summary.json"))
    if not summaries:
        return {}
    summary = load_json(max(summaries, key=lambda path: path.stat().st_mtime))
    ranks = [row for row in summary.get("ranks", []) if isinstance(row, dict)]
    list_ids = [f"{row.get('gender')}/{row.get('rank_type')}" for row in ranks if row.get("status") == "success"]
    category_count = sum(int(row.get("valid_category_count") or 0) for row in ranks)
    return {
        "acquired_list_ids": list_ids,
        "category_taxonomy_complete": summary.get("status") == "success" and category_count == 74 and not summary.get("empty_categories"),
        "signal_eligible_entries": int(summary.get("valid_book_count") or 0),
    }


def public_qimao(source_dir: Path) -> dict[str, Any]:
    manifest = collector_manifest(source_dir)
    channels = [row for row in manifest.get("channels", []) if isinstance(row, dict) and row.get("status") == "success"]
    return {
        "acquired_list_ids": [str(row["channel"]) for row in channels],
        "signal_eligible_entries": sum(int(row.get("valid_entries") or 0) for row in channels),
    }


def manifest_lists(source_id: str, source_dir: Path) -> dict[str, Any]:
    manifest = collector_manifest(source_dir)
    result = manifest.get("source_results", {}).get(source_id, {}) if isinstance(manifest.get("source_results"), dict) else {}
    list_ids = result.get("acquired_list_ids") or manifest.get("required_list_ids") or []
    values: dict[str, Any] = {"acquired_list_ids": list(list_ids)}
    taxonomy = result.get("category_taxonomy_complete", manifest.get("category_taxonomy_complete"))
    if taxonomy is not None:
        values["category_taxonomy_complete"] = taxonomy is True
    captures = manifest.get("captures") if isinstance(manifest.get("captures"), list) else []
    if captures:
        values["signal_eligible_entries"] = max(int(row.get("rank_slots") or 0) for row in captures if isinstance(row, dict))
    return values


def writer_hot(source_dir: Path) -> dict[str, Any]:
    manifest = collector_manifest(source_dir)
    acquired = manifest.get("acquired_list_ids") or [
        name for name in ("all", "dark_horse_increase", "classic_hot") if (source_dir / f"{name}.json").is_file()
    ]
    normalized = source_dir / "normalized.json"
    payload = load_json(normalized) if normalized.is_file() else []
    entries = payload if isinstance(payload, list) else payload.get("items", []) if isinstance(payload, dict) else []
    unique = {str(row.get("book_id")) for row in entries if isinstance(row, dict) and row.get("book_id")}
    return {"acquired_list_ids": list(acquired), "signal_eligible_entries": len(unique)}


def derive(source_id: str, source_dir: Path, definition: dict[str, Any]) -> dict[str, Any]:
    files = [item for item in source_dir.rglob("*") if item.is_file() and item.stat().st_size > 0] if source_dir.is_dir() else []
    if not files:
        return {"status": "not_run", "artifacts": []}
    if source_id == "fanqie_public_web_ranks":
        values = public_fanqie(source_dir)
    elif source_id == "qimao_public_web_ranks":
        values = public_qimao(source_dir)
    elif source_id == "fanqie_writer_hot_stories":
        values = writer_hot(source_dir)
    elif source_id == "qidian_paid_trend_target":
        values = {"acquired_list_ids": qidian_lists(source_dir)}
        values["signal_eligible_entries"] = sum(
            len(load_json(path).get("items", [])) for path in source_dir.glob("*.json") if isinstance(load_json(path), dict)
        )
    elif source_id in SOCIAL_IDS:
        values = SOCIAL.audit_social_files(
            source_id, files,
            max_entries_per_account=int(definition.get("coverage", {}).get("max_signal_entries_per_account", 999999)),
        )
        values.pop("eligible_entries", None)
    else:
        values = manifest_lists(source_id, source_dir)

    coverage = definition.get("coverage", {})
    expected = set(coverage.get("required_list_ids", []))
    observed = set(values.get("acquired_list_ids", []))
    complete = expected.issubset(observed)
    if coverage.get("category_taxonomy_required"):
        complete = complete and values.get("category_taxonomy_complete") is True
    if source_id in SOCIAL_IDS:
        complete = complete and int(values.get("signal_eligible_entries") or 0) >= int(coverage.get("min_signal_eligible_entries", 1))
        complete = complete and int(values.get("discovered_unique_entries") or 0) >= int(coverage.get("min_discovered_unique_entries", 0))
        complete = complete and int(values.get("screened_entries") or 0) >= int(coverage.get("min_screened_entries", 0))
        complete = complete and int(values.get("unique_accounts") or 0) >= int(coverage.get("min_unique_accounts", 0))
        complete = complete and int(values.get("max_entries_per_account") or 0) <= int(coverage.get("max_signal_entries_per_account", 999999))
        for signal_type, minimum in coverage.get("required_primary_signal_type_counts", {}).items():
            complete = complete and int(values.get("primary_signal_type_counts", {}).get(signal_type) or 0) >= int(minimum)
    values["status"] = "success" if complete else "degraded"
    values["captured_at"] = min(iso_mtime(path) for path in files)
    return values


def sync(run_manifest: dict[str, Any], manifest: dict[str, Any], registry: dict[str, Any], only: set[str] | None = None) -> dict[str, Any]:
    definitions = {row["id"]: row for row in registry["sources"]}
    run_root = Path(run_manifest["run_root"])
    sources = []
    for source in manifest.get("sources", []):
        source_id = source["source_id"]
        if only and source_id not in only:
            sources.append(source)
            continue
        source_dir = Path(run_manifest["paths"]["source_dirs"][source_id])
        updated = dict(source)
        updated.update(derive(source_id, source_dir, definitions[source_id]))
        updated["artifacts"] = artifacts(run_root, source_dir) if source_dir.is_dir() else []
        sources.append(updated)
    result = dict(manifest)
    result["sources"] = sources
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-manifest", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--source-id", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run_manifest = load_json(args.run_manifest)
    manifest_path = args.manifest or Path(run_manifest["paths"]["files"]["acquisition_manifest"])
    output = args.output or manifest_path
    result = sync(run_manifest, load_json(manifest_path), load_json(args.registry), set(args.source_id) or None)
    summary = {row["source_id"]: row.get("status") for row in result["sources"]}
    if not args.dry_run:
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": None if args.dry_run else str(output.resolve()), "sources": summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
