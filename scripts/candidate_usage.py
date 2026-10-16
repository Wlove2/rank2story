#!/usr/bin/env python3
"""Offline token accounting from local candidate executor response receipts.

No network requests, no model calls, no raw prompts or endpoint metadata emitted.
"""
from __future__ import annotations
import argparse
import json
from collections import defaultdict
from pathlib import Path

TOKEN_FIELDS = ("prompt_tokens", "completion_tokens", "total_tokens")
ROLE_GROUPS = {
    "atoms": "evidence_atoms",
    "story_creator": "story_creation",
    "story_editor": "story_quality_review",
    "candidate_mapper": "candidate_mapping",
    "market_coverage": "market_review",
    "originality_craft": "originality_review",
}


def stage_name(role: str) -> str:
    if role.startswith("generation_") or role.startswith("kernel_supplement_"):
        return "branch_generation"
    return ROLE_GROUPS.get(role, "other")


def read_usage(path: Path) -> tuple[str, dict[str, int] | None]:
    envelope = json.loads(path.read_text(encoding="utf-8"))
    role = str(envelope.get("role") or "")
    response = envelope.get("raw_response")
    if isinstance(response, str):
        try:
            response = json.loads(response)
        except ValueError:
            response = {}
    usage = response.get("usage") if isinstance(response, dict) else None
    if not isinstance(usage, dict):
        return role, None
    fields = {key: usage.get(key) for key in TOKEN_FIELDS}
    if not all(type(value) is int and value >= 0 for value in fields.values()):
        return role, None
    if fields["prompt_tokens"] + fields["completion_tokens"] != fields["total_tokens"]:
        return role, None
    return role, fields


def summarize(run_dir: Path) -> dict:
    raw = run_dir / "raw"
    if not raw.is_dir():
        raise ValueError("RUN_RAW_DIRECTORY_NOT_FOUND")
    totals = {name: 0 for name in TOKEN_FIELDS}
    stages: dict[str, dict] = defaultdict(
        lambda: {"calls": 0, **{name: 0 for name in TOKEN_FIELDS}}
    )
    files = sorted(raw.glob("*.response.json"))
    if not files:
        raise ValueError("RUN_MODEL_RESPONSE_RECORDS_MISSING")
    missing = 0
    for path in files:
        role, usage = read_usage(path)
        if usage is None:
            missing += 1
            continue
        stage = stages[stage_name(role)]
        stage["calls"] += 1
        for key, value in usage.items():
            stage[key] += value
            totals[key] += value
    return {
        "response_count": len(files),
        "measured_calls": len(files) - missing,
        "missing_usage_calls": missing,
        "usage_complete": missing == 0,
        "totals": totals,
        "stages": [{"stage": key, **stages[key]} for key in sorted(stages)],
        "note": "Only stored provider usage counts, including stored retries; missing usage is unknown, never counted as zero.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect local candidate model-token usage (offline)")
    parser.add_argument("--run-dir", type=Path, required=True, help="Candidate output directory containing raw/*.response.json")
    args = parser.parse_args()
    print(json.dumps(summarize(args.run_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
