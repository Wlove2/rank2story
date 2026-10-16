#!/usr/bin/env python3
"""Hard-gate and score an 8–12 concept long-form batch; never invent verification."""

from __future__ import annotations

import argparse
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import sys


FREEZER_PATH = Path(__file__).with_name("freeze_evidence_packet.py")
FREEZER_SPEC = importlib.util.spec_from_file_location("freeze_evidence_packet_long", FREEZER_PATH)
if FREEZER_SPEC is None or FREEZER_SPEC.loader is None:
    raise RuntimeError(f"cannot load {FREEZER_PATH}")
freezer = importlib.util.module_from_spec(FREEZER_SPEC)
sys.modules[FREEZER_SPEC.name] = freezer
FREEZER_SPEC.loader.exec_module(freezer)

PORTFOLIO_PATH = Path(__file__).with_name("candidate_portfolio.py")
PORTFOLIO_SPEC = importlib.util.spec_from_file_location("candidate_portfolio_long", PORTFOLIO_PATH)
if PORTFOLIO_SPEC is None or PORTFOLIO_SPEC.loader is None:
    raise RuntimeError(f"cannot load {PORTFOLIO_PATH}")
portfolio = importlib.util.module_from_spec(PORTFOLIO_SPEC)
sys.modules[PORTFOLIO_SPEC.name] = portfolio
PORTFOLIO_SPEC.loader.exec_module(portfolio)


WEIGHTS = {
    "market_evidence": 20,
    "long_run_capacity": 20,
    "differentiation": 18,
    "reader_promise": 12,
    "platform_fit": 10,
    "relationship_engine": 8,
    "stage_closure": 7,
    "production_cost": 5,
}
VERIFICATION_FIELDS = {"title_search", "concept_search", "ip_check", "real_person_check", "safety_check"}
REQUIRED_TEXT = {
    "target_reader", "target_platform", "composite_genre", "one_line_promise",
    "core_desire", "main_conflict", "mechanism", "mechanism_limit",
    "relationship_engine", "world_expansion", "stage_closures",
    "closest_samples", "essential_difference", "production_cost", "failure_risks",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def total_score(candidate: dict[str, Any]) -> float:
    scores = candidate.get("scores")
    if not isinstance(scores, dict):
        raise ValueError(f"{candidate.get('id', candidate.get('title'))}: scores must be an object")
    total = 0.0
    for name, weight in WEIGHTS.items():
        value = scores.get(name)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not 1 <= value <= 5:
            raise ValueError(f"{candidate.get('id', candidate.get('title'))}: score {name} must be 1..5")
        normalized = (6 - value) / 5 if name == "production_cost" else value / 5
        total += normalized * weight
    return round(total, 1)


def verification_summary(candidate: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    verification = candidate.get("verification") if isinstance(candidate.get("verification"), dict) else {}
    reasons = []
    normalized = {}
    for field in sorted(VERIFICATION_FIELDS):
        item = verification.get(field)
        if isinstance(item, dict):
            status = item.get("status")
            normalized[field] = item
        else:
            status = item
            normalized[field] = {"status": status or "not_run"}
        if status == "failed":
            reasons.append(f"{field.upper()}_FAILED")
        elif status != "passed":
            reasons.append(f"{field.upper()}_NOT_RUN")
        if field in {"title_search", "concept_search"} and status == "passed":
            reviewed = item.get("reviewed_urls") if isinstance(item, dict) else None
            if not (
                isinstance(item, dict)
                and nonempty(item.get("provider"))
                and nonempty(item.get("checked_at"))
                and isinstance(reviewed, list)
                and any(nonempty(url) for url in reviewed)
            ):
                reasons.append(f"{field.upper()}_AUDIT_MISSING")
    return reasons, normalized


def hard_gate_reasons(candidate: dict[str, Any]) -> list[str]:
    reasons = []
    if not nonempty(candidate.get("title")):
        reasons.append("MISSING_TITLE")
    reasons.extend(f"MISSING_{field.upper()}" for field in sorted(REQUIRED_TEXT) if not nonempty(candidate.get(field)))
    rationales = candidate.get("score_rationales")
    if not isinstance(rationales, dict):
        reasons.append("MISSING_SCORE_RATIONALES")
    else:
        reasons.extend(
            f"MISSING_SCORE_RATIONALE:{name}"
            for name in WEIGHTS
            if not nonempty(rationales.get(name))
        )
    stages = candidate.get("long_run_stages")
    if not isinstance(stages, dict) or any(not nonempty(stages.get(key)) for key in ("300k", "800k", "1500k")):
        reasons.append("NO_THREE_STAGE_LONG_RUN")
    evidence = candidate.get("market_evidence") if isinstance(candidate.get("market_evidence"), list) else []
    platforms = {item.get("platform") for item in evidence if isinstance(item, dict) and item.get("platform")}
    samples = {item.get("title") for item in evidence if isinstance(item, dict) and item.get("title")}
    if len(platforms) < 2 or len(samples) < 2:
        reasons.append("SINGLE_BOOK_OR_PLATFORM_EVIDENCE")
    if any(isinstance(item, dict) and item.get("current") is not True for item in evidence):
        reasons.append("STALE_MARKET_EVIDENCE")
    risks = candidate.get("risks") if isinstance(candidate.get("risks"), dict) else {}
    if risks.get("direct_ip") or risks.get("unauthorized_derivative"):
        reasons.append("DIRECT_OR_UNAUTHORIZED_IP")
    if risks.get("real_person"):
        reasons.append("REAL_PERSON_RISK")
    if isinstance(risks.get("sensitive_level"), (int, float)) and risks["sensitive_level"] >= 4:
        reasons.append("HIGH_SENSITIVE_RISK")
    if risks.get("surface_reskin"):
        reasons.append("SURFACE_RESKIN")
    if risks.get("short_twist_only"):
        reasons.append("SHORT_TWIST_ONLY")
    if risks.get("oversaturated") and not nonempty(candidate.get("saturation_difference")):
        reasons.append("OVERSATURATED_WITHOUT_DIFFERENCE")
    verification_reasons, _ = verification_summary(candidate)
    reasons.extend(verification_reasons)
    return list(dict.fromkeys(reasons))


def portfolio_fields(candidate: dict[str, Any]) -> None:
    candidate.setdefault("structural_fingerprint", portfolio.derive_structural_fingerprint(candidate, "long"))
    scores = candidate.get("scores", {})
    candidate.setdefault("portfolio_objectives", {
        "commercial_certainty": scores.get("market_evidence", 1),
        "structural_novelty": scores.get("differentiation", 1),
        "emotional_impact": scores.get("reader_promise", 1),
        "producibility": 6 - scores.get("production_cost", 5),
        "originality_risk": 6 - scores.get("differentiation", 1),
    })


def evaluate(raw: list[dict[str, Any]], formal_allowed: bool, batch_reasons: list[str] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    evaluated = []
    rejected = []
    eligible = []
    for index, concept in enumerate(raw, 1):
        candidate = dict(concept)
        candidate["id"] = candidate.get("id") or f"L-{index:04d}"
        reasons = list(batch_reasons or []) if formal_allowed else ["CURRENT_SOURCE_GATE_NOT_ALLOWED", *(batch_reasons or [])]
        try:
            score = total_score(candidate)
        except ValueError as exc:
            score = None
            reasons.append(f"INVALID_SCORE:{exc}")
        reasons.extend(hard_gate_reasons(candidate))
        candidate["score"] = score
        candidate["gate_reasons"] = list(dict.fromkeys(reasons))
        candidate["decision"] = "market_eligible" if not reasons else "rejected"
        evaluated.append(candidate)
        if reasons:
            rejected.append(candidate)
        else:
            portfolio_fields(candidate)
            eligible.append(candidate)
    if not eligible:
        return evaluated, rejected, []
    representatives, cluster_audit = portfolio.cluster_candidates(
        eligible, "long", "long-market-batch", portfolio.canonical_hash([item["id"] for item in eligible])
    )
    representative_ids = {item["id"] for item in representatives}
    for candidate in eligible:
        candidate["cluster_audit_hash"] = cluster_audit["output_hash"]
        if candidate["id"] not in representative_ids:
            candidate["gate_reasons"].append("DUPLICATE_CONCEPT_SCAFFOLD")
            candidate["decision"] = "rejected"
            rejected.append(candidate)
    frontier = portfolio.pareto_frontier(representatives)
    selected = portfolio.cap_frontier(frontier, 6)
    for candidate in selected:
        candidate["decision"] = "pareto_market_candidate"
    return evaluated, rejected, selected


def batch_score_reasons(candidates: list[dict[str, Any]]) -> list[str]:
    vectors = []
    for candidate in candidates:
        scores = candidate.get("scores")
        if isinstance(scores, dict):
            vectors.append(tuple(scores.get(name) for name in WEIGHTS))
    if len(vectors) > 1 and len(set(vectors)) == 1:
        return ["UNIFORM_BATCH_SCORES"]
    return []


def render_rejected(rejected: list[dict[str, Any]], date_key: str) -> str:
    lines = [f"# 长篇 raw 淘汰清单 {date_key}", ""]
    if not rejected:
        lines.append("本批没有硬门淘汰。")
    for item in rejected:
        lines.extend([
            f"## {item['id']}｜{item.get('title', '未命名')}", "",
            f"- 原始承诺：{item.get('one_line_promise', '')}",
            f"- 淘汰原因：{', '.join(item['gate_reasons'])}",
            f"- 预计成本/风险：{item.get('production_cost', '')} / {item.get('failure_risks', '')}", "",
        ])
    return "\n".join(lines)


def render_candidates(selected: list[dict[str, Any]], date_key: str, formal_allowed: bool) -> str:
    lines = [f"# 长篇最终候选 {date_key}", "", f"- 正式数据门：`{'allowed' if formal_allowed else 'not_run'}`", ""]
    if not selected:
        lines.append("没有候选通过全部数据、原创、安全和长线承载硬门；本轮不输出伪实时候选。")
    for rank, item in enumerate(selected, 1):
        lines.extend([
            f"## {rank}. {item.get('title')}（{item['score']}）", "",
            f"- 读者/平台：{item.get('target_reader')} / {item.get('target_platform')}",
            f"- 承诺：{item.get('one_line_promise')}",
            f"- 欲望与冲突：{item.get('core_desire')} / {item.get('main_conflict')}",
            f"- 机制及限制：{item.get('mechanism')} / {item.get('mechanism_limit')}",
            f"- 30/80/150 万字：{item.get('long_run_stages', {}).get('300k')}；{item.get('long_run_stages', {}).get('800k')}；{item.get('long_run_stages', {}).get('1500k')}",
            f"- 最相似样本与本质差异：{item.get('closest_samples')} / {item.get('essential_difference')}",
            f"- 关系发动机：{item.get('relationship_engine')}；阶段闭环：{item.get('stage_closures')}",
            f"- 制作成本/失败风险：{item.get('production_cost')} / {item.get('failure_risks')}",
            "- route: `await_user_selection` (resume to `novel-init` only after explicit choice)", "",
        ])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--evidence-packet", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--historical-regression", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    payload = load_json(args.raw)
    raw = payload.get("candidates", []) if isinstance(payload, dict) else payload
    if not isinstance(raw, list) or not 8 <= len(raw) <= 12:
        print(json.dumps({"error": "raw batch must contain 8..12 candidates"}, ensure_ascii=False))
        return 2
    manifest = load_json(args.manifest)
    packet_hash = freezer.validate_packet(load_json(args.evidence_packet), "long")
    for item in raw:
        item["evidence_packet_hash"] = packet_hash
    formal_allowed = manifest.get("formal_candidate_generation") == "allowed" or args.historical_regression
    batch_reasons = [] if args.historical_regression else batch_score_reasons(raw)
    evaluated, rejected, selected = evaluate(raw, formal_allowed, batch_reasons)
    args.output.mkdir(parents=True, exist_ok=True)
    save_json(args.output / f"long_raw_{args.date}.json", {
        "schema_version": 1, "date": args.date, "generated_at": datetime.now(timezone.utc).isoformat(),
        "formal_allowed": formal_allowed, "candidates": evaluated,
    })
    (args.output / f"long_rejected_{args.date}.md").write_text(render_rejected(rejected, args.date), encoding="utf-8")
    (args.output / f"long_candidates_{args.date}.md").write_text(render_candidates(selected, args.date, formal_allowed), encoding="utf-8")
    save_json(args.output / f"long_verification_{args.date}.json", {
        "schema_version": 1, "date": args.date,
        "candidates": [{"id": item["id"], "title": item.get("title"), "verification": verification_summary(item)[1], "gate_reasons": item["gate_reasons"]} for item in evaluated],
    })
    result = {"raw": len(evaluated), "rejected": len(rejected), "eligible": len(evaluated) - len(rejected), "pareto_final": len(selected), "formal_allowed": formal_allowed, "status": "awaiting_user_choice" if 4 <= len(selected) <= 6 else "blocked"}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if 4 <= len(selected) <= 6 else 2


if __name__ == "__main__":
    raise SystemExit(main())
