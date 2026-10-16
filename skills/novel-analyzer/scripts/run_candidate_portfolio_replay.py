#!/usr/bin/env python3
"""Replay v2 structural/Pareto selection against historical frozen packets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import candidate_portfolio as portfolio


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        value = payload.get("candidates")
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []


def objective(candidate: dict[str, Any], lane: str) -> dict[str, float]:
    supplied = candidate.get("portfolio_objectives")
    if isinstance(supplied, dict) and all(key in supplied for key in portfolio.OBJECTIVES):
        return supplied
    scores = candidate.get("scores") if isinstance(candidate.get("scores"), dict) else {}
    if lane == "long":
        return {
            "commercial_certainty": float(scores.get("market_evidence", 1)),
            "structural_novelty": float(scores.get("differentiation", 1)),
            "emotional_impact": float(scores.get("reader_promise", 1)),
            "producibility": 6 - float(scores.get("production_cost", 5)),
            "originality_risk": 6 - float(scores.get("differentiation", 1)),
        }
    return {
        "commercial_certainty": (float(scores.get("desire_strength", 1)) + float(scores.get("platform_fit", 1))) / 2,
        "structural_novelty": float(scores.get("payoff_density", 1)),
        "emotional_impact": float(scores.get("emotional_compensation", 1)),
        "producibility": 6 - float(scores.get("revision_cost", 5)),
        "originality_risk": float((candidate.get("risks") or {}).get("originality_risk", 3)),
    }


def packet_summary(packet: dict[str, Any], lane: str) -> dict[str, Any]:
    packet_hash = portfolio.validate_packet(packet, lane)
    source_to_cohort, cohorts = portfolio.cohort_index(packet)
    counts = {cohort: 0 for cohort in cohorts}
    unknown = 0
    for item in portfolio.evidence_index(packet).values():
        source_id = str(item.get("source_id") or item.get("manifest_id") or "")
        cohort = portfolio.cohort_for_source(source_to_cohort, source_id)
        if cohort:
            counts[cohort] += 1
        else:
            unknown += 1
    evidence_count = len(portfolio.evidence_index(packet))
    return {
        "packet_hash": packet_hash,
        "evidence_count": evidence_count,
        "cohort_counts": counts,
        "missing_cohorts": sorted(cohort for cohort, count in counts.items() if count == 0),
        "unknown_cohort_evidence": unknown,
        "atom_input_viability": "audit_possible" if evidence_count else "blocked_no_frozen_evidence",
    }


def replay_candidates(payload: Any, lane: str) -> dict[str, Any]:
    candidates = []
    for index, source in enumerate(rows(payload), 1):
        candidate = dict(source)
        candidate["candidate_id"] = str(candidate.get("candidate_id") or candidate.get("id") or f"{lane}-{index}")
        candidate["structural_fingerprint"] = candidate.get("structural_fingerprint") or portfolio.derive_structural_fingerprint(candidate, lane)
        candidate["portfolio_objectives"] = objective(candidate, lane)
        candidates.append(candidate)
    if not candidates:
        return {"candidate_count": 0, "error": "NO_HISTORICAL_CANDIDATES"}
    old_top = sorted(
        candidates,
        key=lambda item: (-float(item.get("score") or 0), item["candidate_id"]),
    )[:5]
    representatives, audit = portfolio.cluster_candidates(
        candidates, lane, f"historical-{lane}", portfolio.canonical_hash([item["candidate_id"] for item in candidates])
    )
    frontier = portfolio.pareto_frontier(representatives)
    selected = portfolio.cap_frontier(frontier, 6)
    return {
        "candidate_count": len(candidates),
        "old_weighted_top_ids": [item["candidate_id"] for item in old_top],
        "cluster_count": len(audit["clusters"]),
        "multi_member_clusters": [item for item in audit["clusters"] if len(item["members"]) > 1],
        "representative_ids": audit["representative_ids"],
        "pareto_frontier_ids": [item["candidate_id"] for item in frontier],
        "display_ids": [item["candidate_id"] for item in selected],
        "formal_card_count_gate": "passed" if 4 <= len(frontier) else "blocked",
        "cluster_audit_hash": audit["output_hash"],
    }


def historical_atom_replay(packet: dict[str, Any]) -> dict[str, Any]:
    definitions = [
        ("desire", "fanqie-writer-7655527399517342744", ["fanqie-writer-7655527399517342744", "fanqie-writer-7652712017999957054"], "Current official all/dark-horse items combine family-relationship tags with visible reversal and sit in the 10k-30k capacity band.", "Readers are rewarding compressed family pressure that converts into a concrete, publicly legible change."),
        ("anxiety", "fanqie-writer-7652712017999957054", ["fanqie-writer-7652712017999957054"], "A current official item centers sustained family evaluation and threatened belonging rather than an external monster or system.", "Ordinary family measurement can supply durable pressure when the protagonist must choose whether to keep competing for affection."),
        ("identity_fantasy", "fanqie-writer-7654184661840579646", ["fanqie-writer-7654184661840579646"], "A current official sample establishes agency through repeated concrete enforcement actions and a socially costly personality edge.", "A rule-enforcing identity fantasy can feel fresh when the trait creates both competence and relational cost."),
        ("conflict_mechanism", "fanqie-writer-7655527399517342744", ["fanqie-writer-7655527399517342744", "fanqie-writer-7654184661840579646"], "Two current official items turn private relationship conflict into an observable public consequence through evidence-bearing action.", "The reusable mechanism is private pressure -> deliberate evidence action -> public reaction, not the original characters or setting."),
        ("payoff_mode", "fanqie-writer-7654184661840579646", ["fanqie-writer-7654184661840579646"], "The sample's return is carried by things characters visibly do and by multiple social reactions, not by an explanatory monologue.", "Candidate payoffs should be staged as observable actions with a reaction chain and a new cost."),
        ("opening_form", "fanqie-writer-7654395348340706328", ["fanqie-writer-7654395348340706328"], "A current official 10k-30k item opens inside an irreversible relationship decision rather than with background exposition.", "The first 300 characters should bind pressure to a choice whose social consequences cannot be reset."),
        ("anti_signal", "qimao-story-1720237", ["qimao-story-1720237"], "The current official story recommendation surface ranks a media-derivative category first.", "Popularity of a derivative category is an IP warning, not permission to reuse protected characters or recognizable expression."),
        ("activity_constraint", "qimao-story-12026448", ["qimao-story-12026448", "qimao-story-1963125"], "The official story surface proves short-lane placement for current urban and modern-romance items but publishes no word count in these records.", "Treat official story placement as lane evidence while keeping capacity verification separate; do not invent a word-count pass."),
    ]
    evidence = portfolio.evidence_index(packet)
    source_to_cohort, _ = portfolio.cohort_index(packet)
    atoms = []
    for index, (atom_type, evidence_id, supporting, observation, inference) in enumerate(definitions, 1):
        row = evidence[evidence_id]
        source_id = str(row.get("source_id") or row.get("manifest_id"))
        atoms.append({
            "atom_id": f"replay-short-{index:02d}", "lane": "short", "atom_type": atom_type,
            "evidence_id": evidence_id, "source_item_id": str(row.get("source_item_id") or ""),
            "source_id": source_id, "source_cohort": portfolio.cohort_for_source(source_to_cohort, source_id) or "",
            "platform": str(row.get("platform") or source_id), "observation": observation,
            "inference": inference, "confidence": 0.75, "freshness": "historical_current_run",
            "claim_key": f"replay-claim-{index:02d}", "stance": "support",
            "supporting_evidence_ids": supporting, "counter_evidence_ids": [],
            "contradicting_atom_ids": [], "generation_safe": True,
        })
    bundle = portfolio.seal({
        "stage": "evidence_atoms", "schema_version": portfolio.SCHEMA_VERSION,
        "lane": "short", "run_id": "historical-short-replay",
        "input_hash": packet["evidence_packet_hash"],
        "evidence_packet_hash": packet["evidence_packet_hash"],
        "recovery_status": "atoms_ready", "atoms": atoms,
    })
    failures, audit = portfolio.atom_failures(packet, bundle, "short")
    return {"bundle": bundle, "audit": audit, "status": "passed" if not failures else "blocked"}

def calibration() -> dict[str, Any]:
    fields = portfolio.FINGERPRINT_CORE + portfolio.FINGERPRINT_EXTRAS["short"]
    base = {key: f"shared-{key}" for key in fields}
    reskin = dict(base)
    reskin["audience_desire"] = "new profession fantasy"
    reskin["opening_form"] = "new era and named setting"
    different = dict(base)
    for key in portfolio.CAUSAL_DIMENSIONS:
        different[key] = f"different-causal-{key}"
    merge = portfolio.fingerprint_similarity(base, reskin, "short")
    separate = portfolio.fingerprint_similarity(base, different, "short")
    return {
        "reskin_should_merge": merge,
        "causal_change_should_separate": separate,
        "status": "passed" if merge["merge"] and not separate["merge"] else "failed",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--short-packet", type=Path, required=True)
    parser.add_argument("--short-candidates", type=Path, required=True)
    parser.add_argument("--long-packet", type=Path, required=True)
    parser.add_argument("--long-candidates", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = {
        "schema_version": 1,
        "stage": "historical_candidate_portfolio_replay",
        "short": {
            "packet": packet_summary(load(args.short_packet), "short"),
            "atom_replay": historical_atom_replay(load(args.short_packet)),
            "selection": replay_candidates(load(args.short_candidates), "short"),
        },
        "long": {
            "packet": packet_summary(load(args.long_packet), "long"),
            "selection": replay_candidates(load(args.long_candidates), "long"),
        },
        "calibration": calibration(),
    }
    result["status"] = "passed" if result["calibration"]["status"] == "passed" else "failed"
    result["output_hash"] = portfolio.canonical_hash(result)
    portfolio.save_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
