from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


FREEZE = load("freeze_evidence_packet")
VALIDATOR = load("validate_deliberation")


class CurrentAttemptBindingTest(unittest.TestCase):
    def test_expired_dispatch_callbacks_cannot_validate_retry_attempt(self) -> None:
        packet = FREEZE.freeze(
            {"lane": "short", "sources": []},
            {"formal_candidate_generation": "allowed"},
            [{"id": "e1", "source_id": "fanqie_short"}],
            {},
        )
        bundle = {
            "stage": "candidate_draft",
            "lane": "short",
            "generation_run_id": "gen-1",
            "evidence_packet_hash": packet["evidence_packet_hash"],
            "candidates": [{
                "candidate_id": "c1",
                "cited_evidence_ids": ["e1"],
                "source_utilization": {"fanqie_official": {"share": 0.4, "evidence_ids": ["e1"]}},
            }],
        }
        reviews = [
            {
                "reviewer_kind": kind,
                "delegation_id": "deleg-expired",
                "task_index": index,
                "reviewer_run_id": f"deleg-expired:{index}",
                "independent_context": True,
                "evidence_packet_hash": packet["evidence_packet_hash"],
                "reviewed_candidate_ids": ["c1"],
                "status": "passed",
                "findings": [],
            }
            for index, kind in enumerate(("market_coverage", "originality_craft"))
        ]
        result = VALIDATOR.validate(
            packet,
            bundle,
            reviews,
            "short",
            expected_delegation_id="deleg-current",
        )
        reasons = {item["reason"] for item in result["failures"]}
        self.assertIn("DELEGATION_NOT_CURRENT_RECOVERY_ATTEMPT", reasons)


if __name__ == "__main__":
    unittest.main()
