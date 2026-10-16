#!/usr/bin/env python3
"""Build within-platform normalized signals from registered long-form data."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TITLE_TEMPLATES = [
    (re.compile(r"^(重生|穿越|开局|全民|末世|高武|让你|我在|绑定|觉醒)"), "prefix:{0}"),
    (re.compile(r"(系统|签到|模拟器|词条|面板|天赋|空间)"), "mechanism:{0}"),
    (re.compile(r"[:：]"), "colon-promise"),
]
PAID_PLATFORMS = {"qidian", "zongheng", "jjwxc"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def percentile(rank: int, size: int) -> float:
    return 1.0 if size <= 1 else round(1 - (rank - 1) / (size - 1), 4)


def normalized_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for item in entries:
        key = (item.get("platform"), item.get("gender"), item.get("rank_type"), item.get("category"))
        groups[key].append(item)
    output = []
    for group in groups.values():
        ranked = sorted(group, key=lambda item: item.get("rank") if isinstance(item.get("rank"), int) else 10**9)
        for index, item in enumerate(ranked, 1):
            row = dict(item)
            row["platform_percentile"] = percentile(index, len(ranked))
            row["cohort_size"] = len(ranked)
            row["cohort"] = {
                "platform": item.get("platform"), "gender": item.get("gender"),
                "rank_type": item.get("rank_type"), "category": item.get("category"),
                "commercial_model": "paid" if item.get("platform") in PAID_PLATFORMS else "free_or_mixed",
            }
            output.append(row)
    return output


def inferred_signals(item: dict[str, Any]) -> list[tuple[str, str]]:
    result = []
    explicit = item.get("signals") if isinstance(item.get("signals"), dict) else {}
    aliases = {
        "genre": "genre", "subgenre": "subgenre", "profession": "protagonist_profession",
        "protagonist_profession": "protagonist_profession", "mechanism": "mechanism",
        "conflict": "core_conflict", "core_conflict": "core_conflict", "title_template": "title_template",
    }
    for source_key, kind in aliases.items():
        value = explicit.get(source_key)
        values = value if isinstance(value, list) else [value]
        result.extend((kind, str(entry).strip()) for entry in values if entry)
    if item.get("category"):
        result.append(("genre", str(item["category"]).strip()))
    title = str(item.get("title") or "")
    for pattern, template in TITLE_TEMPLATES:
        match = pattern.search(title)
        if match:
            value = template.format(match.group(1) if match.groups() else match.group(0))
            result.append(("title_template", value))
    return list(dict.fromkeys(result))


def trend_label(dates: list[str], counts: list[int]) -> str:
    if len(dates) < 2:
        return "insufficient_history"
    if len(dates) >= 3 and all(left < right for left, right in zip(counts[-3:], counts[-2:])):
        return "rising_3_batches"
    if len(dates) >= 2 and counts[-2] < counts[-1]:
        return "rising_2_batches"
    if len(dates) >= 2 and counts[-2] > counts[-1]:
        return "falling"
    return "flat"


def build_matrix(batches: list[tuple[str, list[dict[str, Any]]]]) -> dict[str, Any]:
    occurrence: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    batch_counts: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    normalized_latest = []
    for date_key, entries in batches:
        normalized = normalized_entries(entries)
        if date_key == batches[-1][0]:
            normalized_latest = normalized
        for item in normalized:
            for kind, value in inferred_signals(item):
                evidence = {
                    "title": item.get("title"), "platform": item.get("platform"),
                    "gender": item.get("gender"), "rank_type": item.get("rank_type"),
                    "date": date_key, "source_file": item.get("source_file"),
                    "url": item.get("url"), "platform_percentile": item.get("platform_percentile"),
                }
                occurrence[(kind, value)].append(evidence)
                batch_counts[(kind, value)][date_key] += 1
    signals = []
    latest_date = batches[-1][0]
    latest_total = max(1, len(normalized_latest))
    for (kind, value), evidence in occurrence.items():
        current = [item for item in evidence if item["date"] == latest_date]
        if not current:
            continue
        platforms = sorted({item.get("platform") for item in current if item.get("platform")})
        rank_types = {item.get("rank_type") for item in current}
        dates = sorted(batch_counts[(kind, value)])
        counts = [batch_counts[(kind, value)][key] for key in dates]
        share = len(current) / latest_total
        title_concentration = len({item.get("title") for item in current}) / max(1, len(current))
        saturated = share >= 0.08 and (kind == "title_template" or title_concentration < 0.6)
        signals.append({
            "kind": kind, "value": value, "current_occurrences": len(current),
            "platforms": platforms, "multi_platform": len(platforms) >= 2,
            "supply_and_consumption_validated": bool(rank_types & {"new", "new_ranks"}) and bool(rank_types & {"hot", "read_ranks", "favorites"}),
            "trend": trend_label(dates, counts), "batch_counts": dict(batch_counts[(kind, value)]),
            "saturation": "oversaturated" if saturated else "observed",
            "confidence": "high" if len(platforms) >= 2 and len(current) >= 3 else "medium" if len(current) >= 2 else "sample_only",
            "evidence": current,
        })
    signals.sort(key=lambda item: (item["confidence"] != "high", -item["current_occurrences"], item["kind"], item["value"]))
    return {
        "schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
        "latest_date": latest_date, "batch_count": len(batches),
        "normalization": "within platform/gender/rank/category percentile only; raw metrics are never compared across platforms",
        "signals": signals, "normalized_entries": normalized_latest,
    }


def render_report(matrix: dict[str, Any], manifest: dict[str, Any]) -> str:
    lines = [
        f"# 长篇市场信号报告 {matrix['latest_date']}", "",
        f"- 正式候选门：`{manifest.get('formal_candidate_generation', 'not_run')}`",
        f"- 已登记批次：{matrix['batch_count']}",
        f"- 当前有效作品条目：{len(matrix['normalized_entries'])}",
        "- 标准化：仅在平台/性别/榜型/分类内部计算排名分位；不跨平台比较热度、在读、月票或积分。", "",
        "## 信号", "",
    ]
    if not matrix["signals"]:
        lines.append("没有足够的登记数据形成信号；本轮不得生成伪实时候选。")
    for item in matrix["signals"]:
        lines.extend([
            f"### {item['kind']} / {item['value']}", "",
            f"- 当前出现 {item['current_occurrences']} 次；平台：{', '.join(item['platforms']) or 'unknown'}；置信度：`{item['confidence']}`。",
            f"- 趋势：`{item['trend']}`；供给与消费双验证：`{str(item['supply_and_consumption_validated']).lower()}`；饱和：`{item['saturation']}`。",
        ])
        for evidence in item["evidence"][:8]:
            lines.append(f"- 证据：{evidence.get('title')}｜{evidence.get('platform')}/{evidence.get('rank_type')}｜{evidence.get('date')}｜{evidence.get('url') or evidence.get('source_file')}")
        lines.append("")
    lines.extend(["## 限制", "", "- 单日只能标 observed/sample，不能写成上升趋势；只有连续 2–3 批数据才允许 rising。", "- 高频且标题模板集中只标过饱和，不能直接升级为候选方向。", ""])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--date", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    manifest = load_json(args.manifest)
    current_path = Path(manifest["normalized_data_file"])
    current = load_json(current_path)
    batches = [(args.date, current.get("entries", []))]
    matrix = build_matrix(batches)
    matrix_path = args.output / f"long_signal_matrix_{args.date}.json"
    report_path = args.output / f"long_market_report_{args.date}.md"
    save_json(matrix_path, matrix)
    report_path.write_text(render_report(matrix, manifest), encoding="utf-8")
    print(json.dumps({"matrix": str(matrix_path), "report": str(report_path), "signals": len(matrix["signals"])}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
