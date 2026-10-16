import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(name):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


SHORT = load("short_candidate_batch")
LONG = load("long_candidate_batch")


class ProductionBatchContractTests(unittest.TestCase):
    def test_short_fixture_titles_are_forbidden_in_production(self):
        candidates = [{"title": f"fresh-{i}"} for i in range(16)]
        candidates[0]["title"] = "遗物整理师收到一张活人清单"
        with self.assertRaisesRegex(ValueError, "REGRESSION_FIXTURE_IN_PRODUCTION"):
            SHORT.validate_candidates(candidates)

    def test_short_uniform_score_vectors_are_forbidden(self):
        candidates = [
            {
                "title": f"fresh-{i}",
                "scores": {name: 4 for name in SHORT.pooler.WEIGHTS},
                "score_rationales": {name: "evidence" for name in SHORT.pooler.WEIGHTS},
            }
            for i in range(16)
        ]
        with self.assertRaisesRegex(ValueError, "UNIFORM_BATCH_SCORES"):
            SHORT.validate_score_audit(candidates)

    def test_long_uniform_score_vectors_mark_batch_invalid(self):
        candidates = [{"scores": {name: 4 for name in LONG.WEIGHTS}} for _ in range(8)]
        self.assertEqual(LONG.batch_score_reasons(candidates), ["UNIFORM_BATCH_SCORES"])

    def test_candidate_batches_reject_unfrozen_or_wrong_lane_packets(self):
        with self.assertRaisesRegex(ValueError, "stage=evidence_frozen"):
            SHORT.freezer.validate_packet({"stage": "acquire"}, "short")
        packet = SHORT.freezer.freeze({"lane": "short"}, {"formal_candidate_generation": "allowed"}, [], {})
        with self.assertRaisesRegex(ValueError, "lane mismatch"):
            LONG.freezer.validate_packet(packet, "long")


if __name__ == "__main__":
    unittest.main()
