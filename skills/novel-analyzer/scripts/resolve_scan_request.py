#!/usr/bin/env python3
"""Resolve a natural-language scan request to a production coverage profile."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "references" / "source-registry.json"
SHORT_MARKERS = ("短篇", "短故事", "故事投稿", "短篇投稿")
LONG_MARKERS = ("长篇", "长篇开书", "连载开书")


def resolve(text: str, registry: dict) -> dict:
    normalized = "".join(text.split()).lower()
    short = any(marker in normalized for marker in SHORT_MARKERS)
    long = any(marker in normalized for marker in LONG_MARKERS)
    if short and long:
        raise ValueError("request mentions both long and short lanes")
    if not short and not long:
        raise ValueError("lane is ambiguous; ask only whether the user wants long or short")
    profile_id = "short_production" if short else "comprehensive_long_production"
    profile = registry["coverage_profiles"][profile_id]
    return {
        "lane": "short" if short else "long",
        "profile_id": profile_id,
        "production_mode": True,
        "fixture_inputs_allowed": False,
        "user_needs_internal_flags": False,
        "analysis_sampling": {
            "base_top_n_per_list": registry["sampling_policy"]["base_top_n_per_list"],
            "adaptive_max_top_n_per_list": registry["sampling_policy"]["adaptive_max_top_n_per_list"],
            "small_complete_source_max_unique": registry["sampling_policy"]["small_complete_source_max_unique"],
        },
        "required_source_ids": profile["required_source_ids"],
        "candidate_context_source_ids": profile.get("candidate_context_source_ids", []),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("request")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    args = parser.parse_args()
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    print(json.dumps(resolve(args.request, registry), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
