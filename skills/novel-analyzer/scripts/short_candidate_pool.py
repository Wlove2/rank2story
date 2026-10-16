#!/usr/bin/env python3
"""Deterministic state, gate, score, and replenishment helper for short candidates."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any


PORTFOLIO_PATH = Path(__file__).with_name("candidate_portfolio.py")
PORTFOLIO_SPEC = importlib.util.spec_from_file_location("candidate_portfolio_short", PORTFOLIO_PATH)
if PORTFOLIO_SPEC is None or PORTFOLIO_SPEC.loader is None:
    raise RuntimeError(f"cannot load {PORTFOLIO_PATH}")
portfolio = importlib.util.module_from_spec(PORTFOLIO_SPEC)
sys.modules[PORTFOLIO_SPEC.name] = portfolio
PORTFOLIO_SPEC.loader.exec_module(portfolio)

STATUSES = {"raw", "provisional", "rejected", "ready", "selected", "written", "submitted", "accepted", "failed"}
ALLOWED_TRANSITIONS = {
    "raw": {"provisional", "rejected", "ready"},
    "provisional": {"raw", "rejected", "ready"},
    "rejected": {"raw", "provisional"},
    "ready": {"selected", "provisional", "rejected"},
    "selected": {"written"},
    "written": {"submitted"},
    "submitted": {"accepted", "failed"},
    "failed": {"ready"},
    "accepted": set(),
}
DIRECTION_SIGNAL_KINDS = {"official_activity", "editorial_direction"}
DEMAND_SIGNAL_KINDS = {
    "short_rank", "short_sample", "submission_feedback",
    "social_post", "video_transcript",
}
BACKGROUND_SIGNAL_KINDS = {"long_rank_background"}
RULE_SIGNAL_KINDS = {"official_rule"}
SHORT_SIGNAL_KINDS = DIRECTION_SIGNAL_KINDS | DEMAND_SIGNAL_KINDS
EVIDENCE_GATE_REASONS = {
    "MISSING_CURRENT_SHORT_DIRECTION",
    "MISSING_INDEPENDENT_DEMAND",
    "MISSING_EVIDENCE_DIVERSITY",
}
GENERIC_SCAFFOLD_PHRASES = {
    "异常规则与人物关系同时落地",
    "主角必须在当晚拿到可验证的结果",
    "失败会失去最重要的关系或生存机会",
    "对手控制信息并迫使主角做不可逆选择",
    "主角以行动完成核心承诺并改变公开结果",
    "人物关系和生存状态进入新的稳定态",
    "前300字建立限时问题",
}
WEIGHTS = {
    "core_promise": 10, "desire_strength": 10, "closure": 15,
    "aftermath": 12, "platform_fit": 12, "hook_300": 8,
    "scene_capacity": 8, "payoff_density": 7, "reaction_chain": 5,
    "emotional_compensation": 5, "micro_hooks": 3, "revision_cost": 5,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def empty_pool() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "updated_at": now_iso(),
        "config": {
            "raw_batch_size": 16,
            "ready_target": 10,
            "ready_floor": 8,
            "ready_score": 70,
            "structural_cluster_policy": dict(portfolio.CLUSTER_POLICY),
        },
        "candidates": [],
    }


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_pool(path: Path) -> dict[str, Any]:
    if not path.exists():
        return empty_pool()
    pool = load_json(path)
    if not isinstance(pool, dict) or not isinstance(pool.get("candidates"), list):
        raise ValueError("pool must be an object containing candidates[]")
    return pool


def save_pool(path: Path, pool: dict[str, Any]) -> None:
    pool["updated_at"] = now_iso()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(pool, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def score_value(scores: dict[str, Any], name: str) -> float:
    value = scores.get(name)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not 1 <= value <= 5:
        raise ValueError(f"score {name} must be between 1 and 5")
    return float(value)


def craft_list(concept: dict[str, Any], name: str) -> list[str]:
    craft = concept.get("craft") if isinstance(concept.get("craft"), dict) else {}
    values = craft.get(name)
    if not isinstance(values, list):
        return []
    return list(dict.fromkeys(value.strip() for value in values if nonempty(value)))


def score_caps(concept: dict[str, Any]) -> dict[str, int]:
    caps = {name: 5 for name in WEIGHTS}
    actions = craft_list(concept, "observable_payoff_actions")
    reactions = craft_list(concept, "reaction_parties")
    hooks = craft_list(concept, "micro_hook_questions")
    anchors = craft_list(concept, "concrete_anchors")
    craft = concept.get("craft") if isinstance(concept.get("craft"), dict) else {}
    aftermath = concept.get("aftermath") if isinstance(concept.get("aftermath"), dict) else {}
    aftermath_keys = ("opponent_reaction", "relationship_or_cost", "protagonist_choice", "next_state")
    aftermath_count = sum(nonempty(aftermath.get(key)) for key in aftermath_keys)
    caps["payoff_density"] = 2 if len(actions) < 2 else 3 if len(actions) < 3 else 5
    caps["reaction_chain"] = 2 if len(reactions) < 2 else 4 if len(reactions) < 3 else 5
    caps["aftermath"] = min(5, 1 + aftermath_count)
    caps["hook_300"] = 5 if nonempty(craft.get("opening_action")) else 2
    caps["desire_strength"] = 5 if nonempty(craft.get("irreversible_choice")) else 2
    caps["core_promise"] = 5 if len(anchors) >= 3 else 2
    caps["micro_hooks"] = 2 if len(hooks) < 2 else 4 if len(hooks) < 3 else 5
    return caps


def effective_scores(concept: dict[str, Any]) -> tuple[dict[str, float], dict[str, int]]:
    scores = concept.get("scores")
    if not isinstance(scores, dict):
        raise ValueError("scores must be an object")
    caps = score_caps(concept)
    effective = {
        name: min(score_value(scores, name), float(caps[name]))
        for name in WEIGHTS
    }
    return effective, caps


def total_score(concept: dict[str, Any]) -> float:
    effective, _ = effective_scores(concept)
    total = 0.0
    for name, weight in WEIGHTS.items():
        value = effective[name]
        normalized = (6 - value) / 5 if name == "revision_cost" else value / 5
        total += normalized * weight
    return round(total, 1)


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def usable_evidence(item: Any) -> bool:
    base = (
        isinstance(item, dict)
        and item.get("kind") in SHORT_SIGNAL_KINDS
        and nonempty(item.get("source"))
        and nonempty(item.get("manifest_id"))
        and item.get("current") is True
        and item.get("content_status") == "complete"
    )
    if not base:
        return False
    if item.get("kind") in {"short_rank", "short_sample"}:
        return nonempty(item.get("evidence_id")) and nonempty(item.get("source_item_id"))
    return True


def evidence_gate_reasons(concept: dict[str, Any]) -> list[str]:
    evidence = concept.get("market_evidence")
    usable = [item for item in evidence or [] if usable_evidence(item)]
    directions = [item for item in usable if item.get("kind") in DIRECTION_SIGNAL_KINDS]
    demand = [item for item in usable if item.get("kind") in DEMAND_SIGNAL_KINDS]
    reasons: list[str] = []
    if not directions:
        reasons.append("MISSING_CURRENT_SHORT_DIRECTION")
    if not demand:
        reasons.append("MISSING_INDEPENDENT_DEMAND")
    if directions and demand:
        sources = {item.get("source") for item in directions + demand}
        if len(sources) < 2:
            reasons.append("MISSING_EVIDENCE_DIVERSITY")
    return reasons


def all_candidate_text(concept: dict[str, Any]) -> str:
    parts = [
        concept.get("title"), concept.get("premise"), concept.get("promise_300"),
        concept.get("setup"), concept.get("risk"), concept.get("obstacle"), concept.get("payoff"),
    ]
    aftermath = concept.get("aftermath")
    if isinstance(aftermath, dict):
        parts.extend(aftermath.values())
    parts.extend(concept.get("scene_chain") or [])
    return "\n".join(str(part) for part in parts if nonempty(part))


def scaffold_similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_fp = left.get("structural_fingerprint") or portfolio.derive_structural_fingerprint(left, "short")
    right_fp = right.get("structural_fingerprint") or portfolio.derive_structural_fingerprint(right, "short")
    return portfolio.fingerprint_similarity(left_fp, right_fp, "short")["overall"]


def craft_audit(concept: dict[str, Any], others: list[dict[str, Any]], threshold: float | None = None) -> dict[str, Any]:
    comparisons = [
        (portfolio.fingerprint_similarity(
            concept.get("structural_fingerprint") or portfolio.derive_structural_fingerprint(concept, "short"),
            other.get("structural_fingerprint") or portfolio.derive_structural_fingerprint(other, "short"),
            "short",
        ), other.get("title"))
        for other in others
        if other is not concept and other.get("title") != concept.get("title")
    ]
    result, closest = max(comparisons, default=({"overall": 0.0, "merge": False, "reason": "no neighbor"}, None), key=lambda item: item[0]["overall"])
    phrase_hits = sorted(phrase for phrase in GENERIC_SCAFFOLD_PHRASES if phrase in all_candidate_text(concept))
    return {
        "generic_phrase_hits": phrase_hits,
        "max_structural_similarity": result["overall"],
        "closest_title": closest,
        "duplicate_scaffold": result["merge"],
        "cluster_reason": result["reason"],
        "cluster_policy": portfolio.CLUSTER_POLICY,
    }

def craft_gate_reasons(concept: dict[str, Any]) -> list[str]:
    craft = concept.get("craft") if isinstance(concept.get("craft"), dict) else {}
    reasons = []
    if len(craft_list(concept, "concrete_anchors")) < 3:
        reasons.append("MISSING_CONCRETE_ANCHORS")
    if not nonempty(craft.get("irreversible_choice")):
        reasons.append("MISSING_IRREVERSIBLE_CHOICE")
    if len(craft_list(concept, "observable_payoff_actions")) < 2:
        reasons.append("EXPLANATION_ONLY_PAYOFF")
    if len(craft_list(concept, "reaction_parties")) < 2:
        reasons.append("THIN_REACTION_CHAIN")
    audit = concept.get("craft_audit") if isinstance(concept.get("craft_audit"), dict) else {}
    if len(audit.get("generic_phrase_hits") or []) >= 2:
        reasons.append("GENERIC_AI_SCAFFOLD")
    if audit.get("duplicate_scaffold") is True:
        reasons.append("DUPLICATE_CONCEPT_SCAFFOLD")
    return reasons


def gate_reasons(concept: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    risks = concept.get("risks") if isinstance(concept.get("risks"), dict) else {}
    scores = concept.get("scores") if isinstance(concept.get("scores"), dict) else {}
    verification = concept.get("verification") if isinstance(concept.get("verification"), dict) else {}
    verification_fields = {"title_status", "concept_status", "ip_status", "safety_status"}
    if any(verification.get(field) not in {"passed", "failed", "not_run"} for field in verification_fields):
        reasons.append("VERIFICATION_NOT_RUN")
    elif any(verification.get(field) == "not_run" for field in verification_fields):
        reasons.append("VERIFICATION_NOT_RUN")
    if verification.get("title_status") == "failed":
        reasons.append("TITLE_COLLISION")
    if verification.get("concept_status") == "failed":
        reasons.append("CONCEPT_COLLISION")
    if verification.get("ip_status") == "failed":
        reasons.append("UNAUTHORIZED_IP")
    if verification.get("safety_status") == "failed":
        reasons.append("HIGH_SENSITIVE_RISK")
    if risks.get("direct_ip") is True:
        reasons.append("DIRECT_IP")
    if risks.get("unauthorized_ip") is True:
        reasons.append("UNAUTHORIZED_IP")
    if isinstance(risks.get("sensitive_risk"), (int, float)) and risks["sensitive_risk"] >= 4:
        reasons.append("HIGH_SENSITIVE_RISK")
    if risks.get("hotspot_stacking") is True:
        reasons.append("HOTSPOT_STACKING")

    reasons.extend(craft_gate_reasons(concept))
    reasons.extend(evidence_gate_reasons(concept))
    if scores.get("core_promise", 0) < 3 or scores.get("hook_300", 0) < 3 or not nonempty(concept.get("promise_300")):
        reasons.append("WEAK_PROMISE")
    if scores.get("closure", 0) < 3 or not nonempty(concept.get("payoff")):
        reasons.append("WEAK_CLOSURE")
    scenes = concept.get("scene_chain")
    if scores.get("scene_capacity", 0) < 3 or not isinstance(scenes, list) or len(scenes) < 5:
        reasons.append("WEAK_SCENE_CAPACITY")
    aftermath = concept.get("aftermath")
    aftermath_keys = {"opponent_reaction", "relationship_or_cost", "protagonist_choice", "next_state"}
    if (
        scores.get("aftermath", 0) < 3
        or not isinstance(aftermath, dict)
        or any(not nonempty(aftermath.get(key)) for key in aftermath_keys)
    ):
        reasons.append("MISSING_AFTERMATH")
    return list(dict.fromkeys(reasons))


def evaluated_status(reasons: list[str], score: float, ready_score: float) -> tuple[str, list[str]]:
    final_reasons = list(reasons)
    if not final_reasons and score < ready_score:
        final_reasons.append("LOW_TOTAL_SCORE")
    if not final_reasons:
        return "ready", final_reasons
    if set(final_reasons).issubset(EVIDENCE_GATE_REASONS):
        return "provisional", final_reasons
    return "rejected", final_reasons


def next_id(pool: dict[str, Any]) -> str:
    used = {item.get("id") for item in pool["candidates"]}
    number = 1
    while f"S-{number:04d}" in used:
        number += 1
    return f"S-{number:04d}"


def prepare_portfolio_fields(candidate: dict[str, Any]) -> None:
    candidate.setdefault("structural_fingerprint", portfolio.derive_structural_fingerprint(candidate, "short"))
    scores = candidate.get("scores", {})
    candidate.setdefault("portfolio_objectives", {
        "commercial_certainty": round((float(scores.get("desire_strength", 1)) + float(scores.get("platform_fit", 1))) / 2, 2),
        "structural_novelty": float(scores.get("payoff_density", 1)),
        "emotional_impact": float(scores.get("emotional_compensation", 1)),
        "producibility": 6 - float(scores.get("revision_cost", 5)),
        "originality_risk": float((candidate.get("risks") or {}).get("originality_risk", 3)),
    })


def ingest(pool: dict[str, Any], concepts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    added = []
    ready_score = float(pool.get("config", {}).get("ready_score", 70))
    prepared = [dict(concept) if isinstance(concept, dict) else concept for concept in concepts]
    for concept in prepared:
        if not isinstance(concept, dict) or not nonempty(concept.get("title")):
            raise ValueError("each concept must be an object with a non-empty title")
        candidate = dict(concept)
        candidate["craft_audit"] = craft_audit(concept, [])
        candidate["id"] = candidate.get("id") or next_id(pool)
        candidate["status"] = "raw"
        candidate["created_at"] = now_iso()
        candidate["history"] = [{"from": None, "to": "raw", "at": now_iso(), "reason": "ingested"}]
        candidate["submission_feedback"] = list(candidate.get("submission_feedback") or [])
        effective, caps = effective_scores(candidate)
        candidate["score_audit"] = {
            "declared": dict(candidate["scores"]),
            "effective": effective,
            "caps": caps,
        }
        candidate["score"] = total_score(candidate)
        new_status, reasons = evaluated_status(gate_reasons(candidate), candidate["score"], ready_score)
        candidate["gate_reasons"] = reasons
        candidate["history"].append({
            "from": "raw", "to": new_status, "at": now_iso(),
            "reason": ",".join(reasons) or "hard gates passed",
        })
        candidate["status"] = new_status
        prepare_portfolio_fields(candidate)
        pool["candidates"].append(candidate)
        added.append(candidate)

    clusterable = [item for item in pool["candidates"] if item.get("status") in {"ready", "provisional"}]
    if len(clusterable) > 1:
        for candidate in clusterable:
            prepare_portfolio_fields(candidate)
        representatives, audit = portfolio.cluster_candidates(
            clusterable, "short", "short-pool-batch", portfolio.canonical_hash([item["id"] for item in clusterable])
        )
        representative_ids = {item["id"] for item in representatives}
        cluster_by_member = {
            member: cluster for cluster in audit["clusters"] for member in cluster["members"]
        }
        for candidate in clusterable:
            cluster = cluster_by_member[candidate["id"]]
            candidate["craft_audit"].update({
                "cluster_audit_hash": audit["output_hash"],
                "cluster_id": cluster["cluster_id"],
                "cluster_representative_id": cluster["representative_id"],
                "duplicate_scaffold": candidate["id"] not in representative_ids,
                "cluster_reason": cluster["reason"],
            })
            if candidate["id"] not in representative_ids:
                old_status = candidate["status"]
                candidate["status"] = "rejected"
                candidate["gate_reasons"] = list(dict.fromkeys([*candidate.get("gate_reasons", []), "DUPLICATE_CONCEPT_SCAFFOLD"]))
                candidate["history"].append({
                    "from": old_status, "to": "rejected", "at": now_iso(),
                    "reason": "DUPLICATE_CONCEPT_SCAFFOLD: non-representative structural cluster member",
                })
    pool["updated_at"] = now_iso()
    return added

def revalidate(pool: dict[str, Any]) -> list[dict[str, Any]]:
    ready_score = float(pool.get("config", {}).get("ready_score", 70))
    original = {item.get("id"): item.get("status") for item in pool["candidates"]}
    active = []
    for candidate in pool["candidates"]:
        if candidate.get("status") not in {"raw", "provisional", "rejected", "ready"}:
            continue
        candidate["craft_audit"] = craft_audit(candidate, [])
        effective, caps = effective_scores(candidate)
        candidate["score_audit"] = {"declared": dict(candidate["scores"]), "effective": effective, "caps": caps}
        candidate["score"] = total_score(candidate)
        destination, reasons = evaluated_status(gate_reasons(candidate), candidate["score"], ready_score)
        candidate["gate_reasons"] = [reason for reason in reasons if reason != "DUPLICATE_CONCEPT_SCAFFOLD"]
        candidate["status"] = destination
        prepare_portfolio_fields(candidate)
        if destination in {"ready", "provisional"}:
            active.append(candidate)
    if len(active) > 1:
        representatives, audit = portfolio.cluster_candidates(
            active, "short", "short-pool-revalidation", portfolio.canonical_hash([item["id"] for item in active])
        )
        representative_ids = {item["id"] for item in representatives}
        cluster_by_member = {member: cluster for cluster in audit["clusters"] for member in cluster["members"]}
        for candidate in active:
            cluster = cluster_by_member[candidate["id"]]
            candidate["craft_audit"].update({
                "cluster_audit_hash": audit["output_hash"],
                "cluster_id": cluster["cluster_id"],
                "cluster_representative_id": cluster["representative_id"],
                "duplicate_scaffold": candidate["id"] not in representative_ids,
                "cluster_reason": cluster["reason"],
            })
            if candidate["id"] not in representative_ids:
                candidate["status"] = "rejected"
                candidate["gate_reasons"] = list(dict.fromkeys([*candidate["gate_reasons"], "DUPLICATE_CONCEPT_SCAFFOLD"]))
    changed = []
    for candidate in pool["candidates"]:
        before, after = original.get(candidate.get("id")), candidate.get("status")
        if before != after:
            candidate.setdefault("history", []).append({
                "from": before, "to": after, "at": now_iso(),
                "reason": "revalidated:" + (",".join(candidate.get("gate_reasons", [])) or "hard gates passed"),
            })
            changed.append(candidate)
    pool["updated_at"] = now_iso()
    return changed

def transition(pool: dict[str, Any], candidate_id: str, destination: str, reason: str, platform: str | None) -> dict[str, Any]:
    if destination not in STATUSES:
        raise ValueError(f"unknown status: {destination}")
    candidate = next((item for item in pool["candidates"] if item.get("id") == candidate_id), None)
    if candidate is None:
        raise ValueError(f"candidate not found: {candidate_id}")
    current = candidate.get("status")
    if destination not in ALLOWED_TRANSITIONS.get(current, set()):
        raise ValueError(f"invalid transition: {current} -> {destination}")
    if destination in {"rejected", "failed"} and not reason.strip():
        raise ValueError(f"reason is required for {destination}")
    event = {"from": current, "to": destination, "at": now_iso(), "reason": reason.strip(), "platform": platform}
    candidate.setdefault("history", []).append(event)
    candidate["status"] = destination
    if destination in {"submitted", "accepted", "failed"}:
        candidate.setdefault("submission_feedback", []).append({
            "status": destination, "at": event["at"], "platform": platform, "reason": reason.strip(),
        })
    return candidate


def ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def summarize(pool: dict[str, Any]) -> dict[str, Any]:
    counts = Counter(item.get("status") for item in pool["candidates"])
    reason_counts = Counter(reason for item in pool["candidates"] for reason in item.get("gate_reasons", []))
    config = pool.get("config", {})
    ready = counts.get("ready", 0)
    floor = int(config.get("ready_floor", 8))
    target = int(config.get("ready_target", 10))
    progressed = sum(counts.get(s, 0) for s in {"selected", "written", "submitted", "accepted", "failed"})
    selectable = progressed + ready
    return {
        "counts": {status: counts.get(status, 0) for status in sorted(STATUSES)},
        "ready_floor": floor,
        "ready_target": target,
        "replenish_needed": ready < floor,
        "replenish_gap": max(0, target - ready) if ready < floor else 0,
        "observed_adoption_rate": ratio(progressed, selectable) if progressed else None,
        "gate_reason_counts": dict(reason_counts),
    }


def parse_concepts(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path)
    if isinstance(payload, dict):
        payload = payload.get("candidates")
    if not isinstance(payload, list):
        raise ValueError("concepts file must be a list or an object containing candidates[]")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    ingest_parser = sub.add_parser("ingest")
    ingest_parser.add_argument("--pool", type=Path, required=True)
    ingest_parser.add_argument("--concepts", type=Path, required=True)
    transition_parser = sub.add_parser("transition")
    transition_parser.add_argument("--pool", type=Path, required=True)
    transition_parser.add_argument("--id", required=True)
    transition_parser.add_argument("--to", required=True)
    transition_parser.add_argument("--reason", default="")
    transition_parser.add_argument("--platform")
    revalidate_parser = sub.add_parser("revalidate")
    revalidate_parser.add_argument("--pool", type=Path, required=True)
    summary_parser = sub.add_parser("summary")
    summary_parser.add_argument("--pool", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        pool = load_pool(args.pool)
        if args.command == "ingest":
            added = ingest(pool, parse_concepts(args.concepts))
            save_pool(args.pool, pool)
            result = {
                "added": len(added),
                "ready": sum(x["status"] == "ready" for x in added),
                "rejected": sum(x["status"] == "rejected" for x in added),
                "summary": summarize(pool),
            }
        elif args.command == "transition":
            candidate = transition(pool, args.id, args.to, args.reason, args.platform)
            save_pool(args.pool, pool)
            result = {"candidate": candidate, "summary": summarize(pool)}
        elif args.command == "revalidate":
            changed = revalidate(pool)
            save_pool(args.pool, pool)
            result = {
                "changed": len(changed),
                "changed_ids": [item.get("id") for item in changed],
                "summary": summarize(pool),
            }
        else:
            result = summarize(pool)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())



