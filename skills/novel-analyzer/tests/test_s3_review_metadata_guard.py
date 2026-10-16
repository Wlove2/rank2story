"""Regression for opt-in S3 metadata compatibility without touching frozen core."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import candidate_workflow as frozen_workflow
import review_envelope_compat as compat


class ReviewEnvelopeTests(unittest.TestCase):
    IDS = {f"{branch}-C{number:02d}" for branch in "ABC" for number in (1, 2, 3)}

    def original(self):
        return {"candidates": {
            cid: {"layers": {"causal": {"status": "passed"}}, "closest_work": cid}
            for cid in self.IDS
        }}

    def test_only_known_nested_scalar_status_is_normalized(self):
        raw = self.original()
        raw["candidates"]["status"] = "passed"
        raw["__meta__"] = {"schema_version": 3}
        before = copy.deepcopy(raw)
        cleaned, audit = compat.normalize_nested_review_status(raw, self.IDS)
        self.assertEqual(raw, before, "original model response must not be modified")
        self.assertEqual(set(cleaned["candidates"]), self.IDS)
        self.assertEqual(cleaned["__meta__"], before["__meta__"])
        self.assertEqual(audit["removed_metadata_path"], "candidates.status")
        self.assertFalse(audit["review_body_changed"])
        self.assertTrue(audit["requires_original_validator"])
        for cid in self.IDS:
            self.assertEqual(cleaned["candidates"][cid], raw["candidates"][cid])

    def test_missing_and_extra_candidate_records_cannot_be_hidden(self):
        missing = self.original()
        missing["candidates"].pop("C-C03")
        missing["candidates"]["status"] = "passed"
        cleaned, audit = compat.normalize_nested_review_status(missing, self.IDS)
        self.assertIsNone(audit)
        self.assertEqual(cleaned, missing)
        extra = self.original()
        extra["candidates"].update({"status": "passed", "D-C99": {"invented": True}})
        cleaned, audit = compat.normalize_nested_review_status(extra, self.IDS)
        self.assertIsNone(audit)
        self.assertEqual(cleaned, extra)

    def test_status_must_be_allowlisted_scalar(self):
        for bad in ({"status": "passed"}, ["passed"], 1, "unknown", None, True):
            with self.subTest(bad=bad):
                raw = self.original()
                raw["candidates"]["status"] = bad
                cleaned, audit = compat.normalize_nested_review_status(raw, self.IDS)
                self.assertIsNone(audit)
                self.assertIn("status", cleaned["candidates"])

    def test_original_core_remains_strict_unmodified(self):
        raw = self.original()
        raw["candidates"]["status"] = "passed"
        unchanged = frozen_workflow.auto_fix_review(
            copy.deepcopy(raw), self.IDS, {"portfolio_track": "general"}, "long")
        self.assertIn("status", unchanged["candidates"])
        cleaned, _ = compat.normalize_nested_review_status(raw, self.IDS)
        self.assertEqual(set(cleaned["candidates"]), self.IDS)
        self.assertNotIn("status", cleaned["candidates"])

    def test_already_valid_review_passes_through(self):
        raw = self.original()
        cleaned, audit = compat.normalize_nested_review_status(raw, self.IDS)
        self.assertIsNone(audit)
        self.assertEqual(cleaned, raw)
        self.assertIsNot(cleaned, raw)


if __name__ == "__main__":
    unittest.main()
