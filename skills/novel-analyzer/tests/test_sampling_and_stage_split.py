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


SAMPLE = load("build_analysis_sample")
FREEZE = load("freeze_evidence_packet")


class SamplingTests(unittest.TestCase):
    def test_small_complete_official_source_uses_all_unique_works(self):
        rows = []
        for list_id in ("all", "dark", "classic"):
            for pos in range(1, 21):
                rows.append({"source_id": "fanqie_writer", "list_id": list_id, "position": pos, "book_id": str(pos), "title": f"书{pos}"})
        result = SAMPLE.build_sample(rows)
        self.assertEqual(len(result["selected_works"]), 20)
        self.assertEqual(result["source_reports"][0]["sampling_mode"], "all_unique")

    def test_high_overlap_rank_expands_from_six_to_ten_for_new_works(self):
        rows = []
        for pos in range(1, 31):
            rows.append({"source_id": "large", "list_id": "a", "position": pos, "book_id": f"a{pos}", "title": f"A{pos}"})
        for pos in range(1, 7):
            rows.append({"source_id": "large", "list_id": "b", "position": pos, "book_id": f"a{pos}", "title": f"A{pos}"})
        for pos in range(7, 31):
            rows.append({"source_id": "large", "list_id": "b", "position": pos, "book_id": f"b{pos}", "title": f"B{pos}"})
        result = SAMPLE.build_sample(rows)
        selected = result["selected_works"]
        self.assertEqual(len(selected), 10)
        self.assertTrue(any("adaptive_overlap_expansion" in item["selection_reasons"] for item in selected))


class StageSplitTests(unittest.TestCase):
    def test_incomplete_acquisition_cannot_freeze(self):
        with self.assertRaisesRegex(ValueError, "COVERAGE_GATE_BLOCKED"):
            FREEZE.freeze({"lane": "short"}, {"formal_candidate_generation": "blocked"}, [], {})

    def test_frozen_packet_hash_detects_mutation_and_lane_mix(self):
        packet = FREEZE.freeze({"lane": "short", "sources": []}, {"formal_candidate_generation": "allowed"}, [{"id": "e1"}], {})
        self.assertAlmostEqual(sum(item["cap"] for item in packet["source_mix_policy"].values() if isinstance(item, dict) and "cap" in item), 1.0)
        self.assertEqual(packet["source_mix_policy"]["xiaohongshu_demand"]["cap"], 0.15)
        FREEZE.validate_packet(packet, "short")
        with self.assertRaisesRegex(ValueError, "lane mismatch"):
            FREEZE.validate_packet(packet, "long")
        packet["evidence"].append({"id": "late"})
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            FREEZE.validate_packet(packet, "short")


if __name__ == "__main__":
    unittest.main()
