#!/usr/bin/env python3
"""Fail closed unless two independent reviewers approve one frozen draft."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from freeze_evidence_packet import validate_packet


REVIEWER_KINDS = {"market_coverage", "originality_craft"}


def evidence_index(evidence: Any) -> dict[str, dict[str, Any]]:
    if isinstance(evidence, dict):
        rows = evidence.get("entries") or evidence.get("evidence") or []
    else:
        rows = evidence
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("evidence_id") or row.get("id")): row
        for row in rows
        if isinstance(row, dict) and (row.get("evidence_id") or row.get("id"))
    }


def validate_source_utilization(
    packet: dict[str, Any],
    candidate: dict[str, Any],
    candidate_id: str,
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    policy = packet.get("source_mix_policy")
    utilization = candidate.get("source_utilization")
    if not isinstance(policy, dict) or not isinstance(utilization, dict) or not utilization:
        return [{"reason": "CANDIDATE_SOURCE_UTILIZATION_MISSING", "candidate_id": candidate_id}]
    known_cohorts = {
        name: value for name, value in policy.items()
        if isinstance(value, dict) and "cap" in value and "source_ids" in value
    }
    index = evidence_index(packet.get("evidence"))
    cited = {str(item) for item in candidate.get("cited_evidence_ids", [])}
    utilized_evidence: set[str] = set()
    total_share = 0.0
    for cohort, record in utilization.items():
        definition = known_cohorts.get(cohort)
        if definition is None:
            failures.append({"reason": "SOURCE_UTILIZATION_COHORT_UNKNOWN", "candidate_id": candidate_id, "cohort": cohort})
            continue
        if not isinstance(record, dict) or not isinstance(record.get("share"), (int, float)):
            failures.append({"reason": "SOURCE_UTILIZATION_SHARE_INVALID", "candidate_id": candidate_id, "cohort": cohort})
            continue
        share = float(record["share"])
        cap = float(definition["cap"])
        if share < 0 or share > cap + 1e-9:
            failures.append({"reason": "SOURCE_UTILIZATION_CAP_EXCEEDED", "candidate_id": candidate_id, "cohort": cohort, "observed": share, "cap": cap})
        total_share += max(0.0, share)
        evidence_ids = {str(item) for item in record.get("evidence_ids", [])}
        utilized_evidence.update(evidence_ids)
        allowed_sources = set(definition["source_ids"])
        for evidence_id in evidence_ids:
            evidence = index.get(evidence_id)
            if evidence is None:
                failures.append({"reason": "SOURCE_UTILIZATION_EVIDENCE_UNKNOWN", "candidate_id": candidate_id, "evidence_id": evidence_id})
                continue
            if evidence.get("source_id") not in allowed_sources:
                failures.append({"reason": "SOURCE_UTILIZATION_EVIDENCE_WRONG_COHORT", "candidate_id": candidate_id, "evidence_id": evidence_id, "cohort": cohort})
    if total_share > 1.0 + 1e-9:
        failures.append({"reason": "SOURCE_UTILIZATION_TOTAL_EXCEEDED", "candidate_id": candidate_id, "observed": total_share})
    if utilized_evidence != cited:
        failures.append({"reason": "SOURCE_UTILIZATION_EVIDENCE_SET_MISMATCH", "candidate_id": candidate_id, "cited": sorted(cited), "utilized": sorted(utilized_evidence)})
    return failures


def validate(
    packet: dict[str, Any],
    bundle: dict[str, Any],
    reviews: list[dict[str, Any]],
    lane: str,
    expected_delegation_id: str | None = None,
) -> dict[str, Any]:
    packet_hash = validate_packet(packet, lane)
    failures: list[dict[str, Any]] = []
    if bundle.get("stage") != "candidate_draft":
        failures.append({"reason": "CANDIDATE_BUNDLE_NOT_DRAFT"})
    if bundle.get("lane") != lane:
        failures.append({"reason": "CANDIDATE_LANE_MISMATCH"})
    if bundle.get("evidence_packet_hash") != packet_hash:
        failures.append({"reason": "CANDIDATE_PACKET_HASH_MISMATCH"})
    if not bundle.get("generation_run_id"):
        failures.append({"reason": "GENERATION_RUN_ID_MISSING"})

    candidate_ids: set[str] = set()
    for candidate in bundle.get("candidates", []):
        candidate_id = str(candidate.get("candidate_id") or candidate.get("id") or "")
        if not candidate_id or candidate_id in candidate_ids:
            failures.append({"reason": "CANDIDATE_ID_INVALID", "candidate_id": candidate_id})
            continue
        candidate_ids.add(candidate_id)
        if not candidate.get("cited_evidence_ids"):
            failures.append({"reason": "CANDIDATE_EVIDENCE_MISSING", "candidate_id": candidate_id})
        failures.extend(validate_source_utilization(packet, candidate, candidate_id))
    if not candidate_ids:
        failures.append({"reason": "NO_CANDIDATES"})

    by_kind: dict[str, dict[str, Any]] = {}
    run_ids: set[str] = set()
    delegation_ids: set[str] = set()
    task_indexes: set[int] = set()
    for review in reviews:
        kind = review.get("reviewer_kind")
        if kind not in REVIEWER_KINDS or kind in by_kind:
            failures.append({"reason": "REVIEWER_KIND_INVALID_OR_DUPLICATE", "reviewer_kind": kind})
            continue
        by_kind[kind] = review
        delegation_id = str(review.get("delegation_id") or "")
        task_index = review.get("task_index")
        expected_run_id = f"{delegation_id}:{task_index}"
        run_id = str(review.get("reviewer_run_id") or "")
        if (
            not delegation_id
            or not isinstance(task_index, int)
            or run_id != expected_run_id
            or run_id in run_ids
        ):
            failures.append({"reason": "REVIEWER_RUN_ID_INVALID_OR_DUPLICATE", "reviewer_kind": kind})
        delegation_ids.add(delegation_id)
        if isinstance(task_index, int):
            task_indexes.add(task_index)
        run_ids.add(run_id)
        if review.get("independent_context") is not True:
            failures.append({"reason": "REVIEW_NOT_INDEPENDENT", "reviewer_kind": kind})
        if review.get("evidence_packet_hash") != packet_hash:
            failures.append({"reason": "REVIEW_PACKET_HASH_MISMATCH", "reviewer_kind": kind})
        if review.get("status") not in {"passed", "failed"}:
            failures.append({"reason": "REVIEW_STATUS_INVALID", "reviewer_kind": kind})
        reviewed_ids = {str(item) for item in review.get("reviewed_candidate_ids", [])}
        if reviewed_ids != candidate_ids:
            failures.append({"reason": "REVIEW_CANDIDATE_SET_MISMATCH", "reviewer_kind": kind})
        if not isinstance(review.get("findings"), list):
            failures.append({"reason": "REVIEW_FINDINGS_MISSING", "reviewer_kind": kind})

    missing = sorted(REVIEWER_KINDS - set(by_kind))
    if missing:
        failures.append({"reason": "REQUIRED_REVIEWER_MISSING", "reviewer_kinds": missing})
    if len(delegation_ids) != 1 or task_indexes != {0, 1}:
        failures.append({"reason": "DELEGATION_BATCH_IDENTITY_INVALID"})
    if expected_delegation_id and delegation_ids != {expected_delegation_id}:
        failures.append({
            "reason": "DELEGATION_NOT_CURRENT_RECOVERY_ATTEMPT",
            "expected_delegation_id": expected_delegation_id,
            "observed_delegation_ids": sorted(delegation_ids),
        })
    rejected = sorted(kind for kind, review in by_kind.items() if review.get("status") == "failed")
    if rejected:
        failures.append({"reason": "REVIEWER_REJECTED", "reviewer_kinds": rejected})
    return {
        "lane": lane,
        "evidence_packet_hash": packet_hash,
        "formal_candidate_generation": "allowed" if not failures else "blocked",
        "failures": failures,
        "reviewer_kinds": sorted(by_kind),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--review", type=Path, action="append", required=True)
    parser.add_argument("--lane", choices=["short", "long"], required=True)
    parser.add_argument("--recovery-state", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    load = lambda path: json.loads(path.read_text(encoding="utf-8"))
    expected_delegation_id = None
    if args.recovery_state:
        recovery = load(args.recovery_state)
        if recovery.get("status") != "ready_for_validation":
            raise ValueError("recovery state is not ready_for_validation")
        expected_delegation_id = recovery.get("current_delegation_id")
        if not expected_delegation_id:
            raise ValueError("recovery state lacks current_delegation_id")
    result = validate(
        load(args.packet),
        load(args.candidates),
        [load(path) for path in args.review],
        args.lane,
        expected_delegation_id,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["formal_candidate_generation"] == "allowed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
