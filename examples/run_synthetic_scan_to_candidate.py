"""Offline synthetic scan-to-story-first integration demo.

Exercises real source-attestation, coverage and freeze CLI plus the unmodified
candidate controller with synthetic evidence and deterministic mocked jobs.
No network access, browser login, copyrighted book text or LLM API required.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "novel-analyzer" / "tests"))

from test_scan_to_candidate_handoff import ScanToCandidateHandoffTests


def main() -> int:
    verifier = ScanToCandidateHandoffTests()
    results = [verifier.verify_handoff(lane) for lane in ("short", "long")]
    print(json.dumps({
        "demo": "synthetic_run_artifacts_to_frozen_packet_to_story_first_candidate",
        "synthetic_data_only": True,
        "actual_platform_collection_verified": False,
        "results": results,
        "overall": "passed",
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
