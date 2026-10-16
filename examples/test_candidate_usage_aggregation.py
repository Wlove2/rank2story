"""Offline aggregation handles valid and missing provider usage without falsifying totals."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("local_candidate_usage", ROOT / "scripts/candidate_usage.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class CandidateUsageTests(unittest.TestCase):
    def test_count_only_valid_usage_and_group_retries(self):
        with tempfile.TemporaryDirectory() as td:
            raw = Path(td) / "raw"
            raw.mkdir()
            rows = [
                {"role": "story_creator", "raw_response": json.dumps({"usage": {"prompt_tokens": 75, "completion_tokens": 25, "total_tokens": 100}})},
                {"role": "story_editor", "raw_response": {"usage": {"prompt_tokens": 40, "completion_tokens": 10, "total_tokens": 50}}},
                {"role": "story_editor", "raw_response": {"choices": []}},
                {"role": "market_coverage", "raw_response": {"usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 2}}},
            ]
            for index, row in enumerate(rows):
                (raw / f"attempt-{index}.txt.response.json").write_text(
                    json.dumps(row), encoding="utf-8"
                )
            summary = module.summarize(Path(td))
            self.assertEqual(summary["response_count"], 4)
            self.assertEqual(summary["measured_calls"], 2)
            self.assertEqual(summary["missing_usage_calls"], 2)
            self.assertFalse(summary["usage_complete"])
            self.assertEqual(summary["totals"], {"prompt_tokens": 115, "completion_tokens": 35, "total_tokens": 150})
            self.assertEqual([s["stage"] for s in summary["stages"]], ["story_creation", "story_quality_review"])

    def test_no_receipts_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError, "RUN_RAW_DIRECTORY_NOT_FOUND"):
                module.summarize(Path(td))
            (Path(td) / "raw").mkdir()
            with self.assertRaisesRegex(ValueError, "RUN_MODEL_RESPONSE_RECORDS_MISSING"):
                module.summarize(Path(td))


if __name__ == "__main__":
    unittest.main()
