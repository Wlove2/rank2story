#!/usr/bin/env python3
"""Fail closed when a production manifest lacks registered source coverage."""

from __future__ import annotations

import argparse
from datetime import date
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "references" / "source-registry.json"
PASS_STATUSES = {"success", "complete"}

GUARD_PATH = Path(__file__).with_name("scan_run_guard.py")
GUARD_SPEC = importlib.util.spec_from_file_location("scan_run_guard", GUARD_PATH)
if GUARD_SPEC is None or GUARD_SPEC.loader is None:
    raise RuntimeError(f"cannot load {GUARD_PATH}")
GUARD = importlib.util.module_from_spec(GUARD_SPEC)
sys.modules[GUARD_SPEC.name] = GUARD
GUARD_SPEC.loader.exec_module(GUARD)

SOCIAL_PATH = Path(__file__).with_name("social_evidence.py")
SOCIAL_SPEC = importlib.util.spec_from_file_location("social_evidence_for_coverage", SOCIAL_PATH)
if SOCIAL_SPEC is None or SOCIAL_SPEC.loader is None:
    raise RuntimeError(f"cannot load {SOCIAL_PATH}")
SOCIAL = importlib.util.module_from_spec(SOCIAL_SPEC)
sys.modules[SOCIAL_SPEC.name] = SOCIAL
SOCIAL_SPEC.loader.exec_module(SOCIAL)


def validate(
    profile_id: str,
    manifest: dict[str, Any],
    registry: dict[str, Any],
    *,
    stage: str = "scan",
    run_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile = registry["coverage_profiles"][profile_id]
    sources = {item.get("source_id"): item for item in manifest.get("sources", [])}
    required = list(profile["required_source_ids"])
    if stage == "candidate":
        required += profile.get("candidate_context_source_ids", [])
    registry_sources = {item["id"]: item for item in registry["sources"]}
    failures: list[dict[str, Any]] = []
    freshness = run_manifest.get("social_freshness") if run_manifest is not None else None
    if freshness is not None:
        try:
            if not isinstance(freshness, dict) or type(freshness.get("max_age_days")) is not int or freshness["max_age_days"] < 0:
                raise ValueError("invalid age")
            date.fromisoformat(str(freshness["as_of_date"]))
        except (ValueError, KeyError, TypeError):
            failures.append({"reason": "SOCIAL_FRESHNESS_POLICY_INVALID"})
            freshness = None
    for source_id in required:
        observed = sources.get(source_id)
        definition = registry_sources[source_id]
        if observed is None:
            failures.append({"source_id": source_id, "reason": "SOURCE_NOT_RUN"})
            continue
        observed = dict(observed)
        if observed.get("status") not in PASS_STATUSES:
            failures.append({"source_id": source_id, "reason": "SOURCE_NOT_SUCCESS", "status": observed.get("status")})
            continue
        coverage = definition.get("coverage", {})
        expected_lists = coverage.get("required_list_ids", [])
        acquired_lists = set(observed.get("acquired_list_ids", []))
        missing_lists = [item for item in expected_lists if item not in acquired_lists]
        if missing_lists:
            failures.append({"source_id": source_id, "reason": "REQUIRED_LISTS_MISSING", "missing_list_ids": missing_lists})
        if coverage.get("category_taxonomy_required") and not observed.get("category_taxonomy_complete"):
            failures.append({"source_id": source_id, "reason": "CATEGORY_TAXONOMY_INCOMPLETE"})
        if definition.get("signal_requires_complete_content"):
            if run_manifest is not None:
                run_root = Path(str(run_manifest.get("run_root") or ""))
                raw_paths = []
                for artifact in observed.get("artifacts", []):
                    if not isinstance(artifact, dict) or not artifact.get("path"):
                        continue
                    path = Path(str(artifact["path"]))
                    raw_paths.append(path if path.is_absolute() else run_root / path)
                audited = SOCIAL.audit_social_files(
                    source_id, raw_paths,
                    max_entries_per_account=int(coverage.get("max_signal_entries_per_account", 999999)),
                    max_age_days=freshness["max_age_days"] if freshness is not None else None,
                    as_of_date=freshness["as_of_date"] if freshness is not None else None,
                )
                claimed = int(observed.get("signal_eligible_entries") or 0)
                derived = int(audited.get("signal_eligible_entries") or 0)
                if claimed != derived:
                    failures.append({"source_id": source_id, "reason": "SOCIAL_COMPLETE_CONTENT_COUNT_MISMATCH",
                                     "claimed": claimed, "derived": derived,
                                     "invalid_entry_reasons": audited.get("invalid_entry_reasons", {})})
                observed.update({key: value for key, value in audited.items() if key != "eligible_entries"})
            minimum = int(coverage.get("min_signal_eligible_entries", 1))
            observed_count = int(observed.get("signal_eligible_entries") or 0)
            if observed_count < minimum:
                failures.append({
                    "source_id": source_id,
                    "reason": "COMPLETE_SIGNAL_ENTRY_SHORTFALL",
                    "observed": observed_count,
                    "required": minimum,
                })
            count_checks = (
                ("discovered_unique_entries", "min_discovered_unique_entries", "DISCOVERY_POOL_SHORTFALL"),
                ("screened_entries", "min_screened_entries", "SCREENING_POOL_SHORTFALL"),
                ("unique_accounts", "min_unique_accounts", "UNIQUE_ACCOUNT_SHORTFALL"),
            )
            for observed_key, required_key, reason in count_checks:
                if required_key not in coverage:
                    continue
                observed_value = int(observed.get(observed_key) or 0)
                required_value = int(coverage[required_key])
                if observed_value < required_value:
                    failures.append({
                        "source_id": source_id,
                        "reason": reason,
                        "observed": observed_value,
                        "required": required_value,
                    })
            maximum = coverage.get("max_signal_entries_per_account")
            observed_maximum = int(observed.get("max_entries_per_account") or 0)
            if maximum is not None and observed_maximum > int(maximum):
                failures.append({
                    "source_id": source_id,
                    "reason": "ACCOUNT_CONCENTRATION_EXCEEDED",
                    "observed": observed_maximum,
                    "maximum": int(maximum),
                })
            observed_types = observed.get("primary_signal_type_counts") or {}
            for signal_type, required_count in coverage.get("required_primary_signal_type_counts", {}).items():
                observed_type_count = int(observed_types.get(signal_type) or 0)
                if observed_type_count < int(required_count):
                    failures.append({
                        "source_id": source_id,
                        "reason": "SIGNAL_TYPE_QUOTA_SHORTFALL",
                        "signal_type": signal_type,
                        "observed": observed_type_count,
                        "required": int(required_count),
                    })
    artifact_audit = None
    if run_manifest is not None:
        artifact_audit = GUARD.audit_manifest(run_manifest, manifest)
        failures.extend(artifact_audit["failures"])
    return {
        "profile_id": profile_id,
        "stage": stage,
        "run_id": manifest.get("run_id"),
        "formal_candidate_generation": "allowed" if not failures else "blocked",
        "failures": failures,
        "artifact_audit": artifact_audit,
        "social_freshness": freshness,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--run-manifest", type=Path, required=True)
    parser.add_argument("--stage", choices=("scan", "candidate"), default="scan")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    run_manifest = json.loads(args.run_manifest.read_text(encoding="utf-8"))
    result = validate(args.profile, manifest, registry, stage=args.stage, run_manifest=run_manifest)
    report_key = "scan_coverage_report" if args.stage == "scan" else "candidate_coverage_report"
    output = args.output or Path(run_manifest["paths"]["files"][report_key])
    output.parent.mkdir(parents=True, exist_ok=True)
    result["report"] = str(output.resolve())
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["formal_candidate_generation"] == "allowed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
