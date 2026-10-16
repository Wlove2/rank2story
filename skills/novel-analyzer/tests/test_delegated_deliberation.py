import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def load(name):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


FREEZE = load("freeze_evidence_packet")
DELIBERATION = load("validate_deliberation")


class DelegatedDeliberationTests(unittest.TestCase):
    def setUp(self):
        self.packet = FREEZE.freeze(
            {"lane": "short", "sources": []},
            {"formal_candidate_generation": "allowed"},
            [{"id": "e1", "source_id": "fanqie_writer_hot_stories"}],
            {},
        )
        self.bundle = {
            "stage": "candidate_draft",
            "lane": "short",
            "generation_run_id": "generator-parent-1",
            "evidence_packet_hash": self.packet["evidence_packet_hash"],
            "candidates": [{
                "candidate_id": "c1",
                "cited_evidence_ids": ["e1"],
                "source_utilization": {"fanqie_official_short": {"share": 0.40, "evidence_ids": ["e1"]}},
            }],
        }

    def review(self, kind, task_index, status="passed", delegation_id="deleg-1"):
        return {
            "reviewer_kind": kind,
            "delegation_id": delegation_id,
            "task_index": task_index,
            "reviewer_run_id": f"{delegation_id}:{task_index}",
            "independent_context": True,
            "evidence_packet_hash": self.packet["evidence_packet_hash"],
            "reviewed_candidate_ids": ["c1"],
            "status": status,
            "findings": [],
        }

    def test_two_distinct_reviews_allow_final_candidates(self):
        reviews = [
            self.review("market_coverage", 0),
            self.review("originality_craft", 1),
        ]
        result = DELIBERATION.validate(self.packet, self.bundle, reviews, "short")
        self.assertEqual(result["formal_candidate_generation"], "allowed")

    def test_missing_reviewer_blocks_solo_fallback(self):
        result = DELIBERATION.validate(
            self.packet,
            self.bundle,
            [self.review("market_coverage", 0)],
            "short",
        )
        self.assertEqual(result["formal_candidate_generation"], "blocked")
        self.assertTrue(any(item["reason"] == "REQUIRED_REVIEWER_MISSING" for item in result["failures"]))

    def test_same_delegate_run_cannot_pose_as_two_reviewers(self):
        reviews = [
            self.review("market_coverage", 0),
            self.review("originality_craft", 0),
        ]
        result = DELIBERATION.validate(self.packet, self.bundle, reviews, "short")
        self.assertEqual(result["formal_candidate_generation"], "blocked")
        self.assertTrue(any(item["reason"] == "REVIEWER_RUN_ID_INVALID_OR_DUPLICATE" for item in result["failures"]))

    def test_rejection_or_packet_mismatch_blocks(self):
        reviews = [
            self.review("market_coverage", 0, status="failed"),
            self.review("originality_craft", 1),
        ]
        reviews[1]["evidence_packet_hash"] = "wrong"
        result = DELIBERATION.validate(self.packet, self.bundle, reviews, "short")
        reasons = {item["reason"] for item in result["failures"]}
        self.assertIn("REVIEWER_REJECTED", reasons)
        self.assertIn("REVIEW_PACKET_HASH_MISMATCH", reasons)

    def test_source_mix_cap_and_cohort_are_deterministic_gates(self):
        reviews = [self.review("market_coverage", 0), self.review("originality_craft", 1)]
        self.bundle["candidates"][0]["source_utilization"]["fanqie_official_short"]["share"] = 0.41
        result = DELIBERATION.validate(self.packet, self.bundle, reviews, "short")
        self.assertTrue(any(item["reason"] == "SOURCE_UTILIZATION_CAP_EXCEEDED" for item in result["failures"]))

        self.bundle["candidates"][0]["source_utilization"] = {"xiaohongshu_demand": {"share": 0.10, "evidence_ids": ["e1"]}}
        result = DELIBERATION.validate(self.packet, self.bundle, reviews, "short")
        self.assertTrue(any(item["reason"] == "SOURCE_UTILIZATION_EVIDENCE_WRONG_COHORT" for item in result["failures"]))


if __name__ == "__main__":
    unittest.main()
