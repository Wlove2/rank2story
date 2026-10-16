#!/usr/bin/env python3
"""Validate and pool a fresh 16-concept short-form production batch."""

from __future__ import annotations

import argparse
import importlib.util
import json
from collections import Counter
import re
from urllib.parse import urlsplit
from pathlib import Path
import sys
from typing import Any


POOLER_PATH = Path(__file__).with_name("short_candidate_pool.py")
POOLER_SPEC = importlib.util.spec_from_file_location("short_candidate_pool_production", POOLER_PATH)
if POOLER_SPEC is None or POOLER_SPEC.loader is None:
    raise RuntimeError(f"cannot load {POOLER_PATH}")
pooler = importlib.util.module_from_spec(POOLER_SPEC)
sys.modules[POOLER_SPEC.name] = pooler
POOLER_SPEC.loader.exec_module(pooler)

FREEZER_PATH = Path(__file__).with_name("freeze_evidence_packet.py")
FREEZER_SPEC = importlib.util.spec_from_file_location("freeze_evidence_packet_short", FREEZER_PATH)
if FREEZER_SPEC is None or FREEZER_SPEC.loader is None:
    raise RuntimeError(f"cannot load {FREEZER_PATH}")
freezer = importlib.util.module_from_spec(FREEZER_SPEC)
sys.modules[FREEZER_SPEC.name] = freezer
FREEZER_SPEC.loader.exec_module(freezer)


FIXTURE_TITLES = {
    "遗物整理师收到一张活人清单", "我把全家福挂进了失物招领处", "婚礼司仪念错了第三份遗嘱",
    "社区食堂只收旧欠条", "她在族谱背面开了一间工厂", "凌晨两点，停尸房来了一份外卖",
    "我替失忆的妈妈参加离婚调解", "返城表上，姐姐替我签了放弃", "老宅拆迁前，奶奶改了门牌号",
    "全网等我认错时，我关掉了提词器", "华妃重生后改写甄嬛传", "她赢了以后所有人都后悔",
    "真相公开后婚礼取消", "我替现实领导改了审判书", "停电那天所有人都忘了我",
    "他认错以后故事结束了",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_candidates(candidates: Any) -> list[dict[str, Any]]:
    if not isinstance(candidates, list) or not all(isinstance(item, dict) for item in candidates):
        raise ValueError("raw input must be candidates[] or a JSON list")
    if len(candidates) != 16:
        raise ValueError(f"production short batch must contain exactly 16 raw candidates, got {len(candidates)}")
    fixture_hits = sorted({item.get("title") for item in candidates} & FIXTURE_TITLES)
    if fixture_hits:
        raise ValueError(f"REGRESSION_FIXTURE_IN_PRODUCTION: {fixture_hits}")
    return candidates


def load_candidates(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path)
    candidates = payload.get("candidates") if isinstance(payload, dict) else payload
    return validate_candidates(candidates)


def validate_score_audit(candidates: list[dict[str, Any]]) -> None:
    vectors = []
    for item in candidates:
        scores = item.get("scores")
        rationales = item.get("score_rationales")
        if not isinstance(scores, dict) or not isinstance(rationales, dict):
            raise ValueError(f"{item.get('title')}: scores and score_rationales are required")
        missing = [name for name in pooler.WEIGHTS if not nonempty(rationales.get(name))]
        if missing:
            raise ValueError(f"{item.get('title')}: missing score rationales: {missing}")
        vectors.append(tuple(scores.get(name) for name in pooler.WEIGHTS))
    if len(set(vectors)) == 1:
        raise ValueError("UNIFORM_BATCH_SCORES: all 16 candidates use the same score vector")
def evidence_index(value: Any) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    if isinstance(value, dict):
        evidence_id = value.get("evidence_id")
        if nonempty(evidence_id):
            result[str(evidence_id)] = value
        for child in value.values():
            result.update(evidence_index(child))
    elif isinstance(value, list):
        for child in value:
            result.update(evidence_index(child))
    return result


def validate_frozen_evidence(candidates: list[dict[str, Any]], packet: dict[str, Any]) -> None:
    frozen = evidence_index(packet.get("evidence"))
    for candidate in candidates:
        title = candidate.get("title")
        for evidence in candidate.get("market_evidence") or []:
            if not isinstance(evidence, dict) or evidence.get("kind") not in pooler.DEMAND_SIGNAL_KINDS:
                continue
            required = ("evidence_id", "source_item_id", "manifest_id")
            missing = [key for key in required if not nonempty(evidence.get(key))]
            if missing:
                raise ValueError(f"{title}: scan-derived evidence lacks frozen identifiers: {missing}")
            source = frozen.get(str(evidence["evidence_id"]))
            if source is None:
                raise ValueError(f"{title}: FROZEN_EVIDENCE_UNKNOWN: {evidence['evidence_id']}")
            for key in ("source_item_id", "manifest_id"):
                if str(source.get(key) or "") != str(evidence.get(key) or ""):
                    raise ValueError(f"{title}: FROZEN_EVIDENCE_IDENTITY_MISMATCH: {evidence['evidence_id']} {key}")


def direct_result_url(value: str) -> bool:
    try:
        host = (urlsplit(value).hostname or "").casefold()
    except ValueError:
        return False
    search_hosts = ("bing.com", "google.com", "baidu.com", "so.com", "sogou.com")
    return bool(host) and not any(host == item or host.endswith("." + item) for item in search_hosts)


def suspicious_mojibake(value: str) -> bool:
    markers = ("鐨", "鍙", "涓", "绔", "濂", "浠", "锛", "銆")
    return "�" in value or sum(value.count(marker) for marker in markers) >= 3




def verification_for(title: str, records: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    record = records.get(title)
    if not isinstance(record, dict):
        raise ValueError(f"{title}: verification record missing")
    checks = record.get("records")
    if not isinstance(checks, list):
        raise ValueError(f"{title}: verification records[] missing")
    by_check = {item.get("check"): item for item in checks if isinstance(item, dict)}
    for check in ("title_search", "concept_search"):
        item = by_check.get(check, {})
        urls = item.get("reviewed_urls")
        query = item.get("query")
        if not (
            item.get("status") in {"passed", "failed"}
            and nonempty(item.get("provider"))
            and nonempty(item.get("checked_at"))
            and nonempty(query)
            and not suspicious_mojibake(str(query))
            and nonempty(item.get("result_summary"))
            and isinstance(urls, list)
            and any(nonempty(url) and direct_result_url(str(url)) for url in urls)
        ):
            raise ValueError(
                f"{title}: {check} lacks auditable query/result summary/direct reviewed result URL"
            )
    statuses = {
        key: record.get(key, "not_run")
        for key in ("title_status", "concept_status", "ip_status", "safety_status")
    }
    return statuses, checks


def render(items: list[dict[str, Any]], status: str) -> str:
    lines = [f"# short {status} production", ""]
    for item in items:
        if item.get("status") == status:
            lines.extend([
                f"## {item['id']} 《{item['title']}》", "",
                f"- 分数：{item['score']}；判定：{', '.join(item['gate_reasons']) or '通过'}", "",
            ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--evidence-packet", type=Path, required=True)
    parser.add_argument("--verification", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    try:
        packet = load_json(args.evidence_packet)
        packet_hash = freezer.validate_packet(packet, "short")
        candidates = load_candidates(args.raw)
        for item in candidates:
            item["evidence_packet_hash"] = packet_hash
        validate_score_audit(candidates)
        validate_frozen_evidence(candidates, packet)
        verification = load_json(args.verification)
        records = verification.get("titles", {}) if isinstance(verification, dict) else {}
        for item in candidates:
            statuses, checks = verification_for(item.get("title", ""), records)
            item["verification"] = statuses
            item["verification_records"] = checks
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc), "formal_candidate_generation": "not_run"}, ensure_ascii=False, indent=2))
        return 2
    pool = pooler.empty_pool()
    pooler.ingest(pool, candidates)
    args.outdir.mkdir(parents=True, exist_ok=True)
    save_json(args.outdir / "short_raw_production.json", candidates)
    pooler.save_pool(args.outdir / "short_candidate_pool_v3.json", pool)
    for status in ("ready", "provisional", "rejected"):
        (args.outdir / f"short_{status}_v3.md").write_text(render(pool["candidates"], status), encoding="utf-8")
    summary = pooler.summarize(pool)
    summary["evidence_packet_hash"] = packet_hash
    summary["score_distribution"] = dict(Counter(item.get("score") for item in pool["candidates"]))
    save_json(args.outdir / "short_v3_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["counts"]["ready"] >= summary["ready_floor"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
