#!/usr/bin/env python3
"""Date-safe entry point around the reusable long market scan core."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any


CORE_PATH = Path(__file__).with_name("long_market_scan_core.py")
SPEC = importlib.util.spec_from_file_location("long_market_scan_core", CORE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load {CORE_PATH}")
CORE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CORE
SPEC.loader.exec_module(CORE)


def source_date(item: dict[str, Any], fallback: str) -> str:
    explicit = item.get("snapshot_date") or item.get("retrieved_at") or item.get("date")
    if explicit:
        return str(explicit).replace("-", "")[:8]
    match = re.search(r"(?<!\d)(20\d{6})(?!\d)", str(item.get("source_file") or ""))
    return match.group(1) if match else fallback


def stamp_entries(entries: list[dict[str, Any]], fallback: str) -> list[dict[str, Any]]:
    output = []
    for item in entries:
        if isinstance(item, dict):
            row = dict(item)
            row["source_date"] = source_date(row, fallback)
            output.append(row)
    return output


def correct_matrix_dates(matrix: dict[str, Any]) -> None:
    for item in matrix.get("normalized_entries", []):
        item["source_date"] = source_date(item, matrix.get("latest_date", "unknown"))
    for signal in matrix.get("signals", []):
        for evidence in signal.get("evidence", []):
            evidence["date"] = source_date(evidence, evidence.get("date", "unknown"))
    matrix["source_dates"] = sorted({item.get("source_date") for item in matrix.get("normalized_entries", []) if item.get("source_date")})


def render_report(matrix: dict[str, Any], manifest: dict[str, Any]) -> str:
    report = CORE.render_report(matrix, manifest)
    source_dates = ", ".join(matrix.get("source_dates", [])) or "unknown"
    warning = (
        f"- 实际来源日期：{source_dates}；报告日期不是证据日期。\n"
        f"- 数据门原因：{', '.join(manifest.get('formal_gate_reasons', [])) or 'none'}。\n"
    )
    marker = f"- 正式候选门：`{manifest.get('formal_candidate_generation', 'not_run')}`\n"
    return report.replace(marker, marker + warning, 1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--date", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    manifest = CORE.load_json(args.manifest)
    current_path = Path(manifest["normalized_data_file"])
    current = CORE.load_json(current_path)
    batches = [(args.date, stamp_entries(current.get("entries", []), args.date))]
    matrix = CORE.build_matrix(batches)
    correct_matrix_dates(matrix)
    matrix_path = args.output / f"long_signal_matrix_{args.date}.json"
    report_path = args.output / f"long_market_report_{args.date}.md"
    CORE.save_json(matrix_path, matrix)
    report_path.write_text(render_report(matrix, manifest), encoding="utf-8")
    print(json.dumps({"matrix": str(matrix_path), "report": str(report_path), "signals": len(matrix["signals"]), "source_dates": matrix["source_dates"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
