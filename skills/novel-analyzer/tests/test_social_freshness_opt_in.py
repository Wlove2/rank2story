"""Offline tests for opt-in, frozen social evidence age windows."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import scan_start
import social_evidence
import validate_source_coverage


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = json.loads((ROOT / "references" / "source-registry.json").read_text(encoding="utf-8"))
SOURCE_ID = "xiaohongshu_novel_demand_shared"


def make_note(index: int, day: str) -> dict:
    return {
        "source_url": f"https://example.invalid/note/{index}",
        "author": f"author-{index}",
        "published_at": day,
        "engagement": {"likes": 1},
        "full_text": "Complete, independently reviewed synthetic note",
        "content_complete": True,
        "images_total": 1,
        "images_read": 1,
        "primary_signal_type": "reader_demand_or_book_shortage",
    }


class SocialFreshnessTests(unittest.TestCase):
    def test_default_unchanged_and_opt_in_excludes_old_and_future(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "social.json"
            source.write_text(json.dumps({"entries": [
                make_note(1, "2026-10-08T12:00:00+08:00"),
                make_note(2, "2025-01-01"),
                make_note(3, "2026-10-17"),
                make_note(4, "not-a-date"),
            ]}), encoding="utf-8")
            normal = social_evidence.audit_social_files(SOURCE_ID, [source])
            recent = social_evidence.audit_social_files(
                SOURCE_ID, [source], max_age_days=30, as_of_date="2026-10-16")
            self.assertEqual(normal["signal_eligible_entries"], 4)
            self.assertEqual(recent["signal_eligible_entries"], 1)
            self.assertEqual(recent["invalid_entry_reasons"]["SOCIAL_ENTRY_OUTSIDE_FRESHNESS_WINDOW"], 3)
            self.assertFalse(normal["social_freshness_checked"])
            self.assertTrue(recent["social_freshness_checked"])

    def test_negative_window_rejected_before_scan_directory_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "SOCIAL_FRESHNESS_POLICY_INVALID"):
                scan_start.start_scan("short_production", REGISTRY, output_root=Path(tmp),
                                      max_social_age_days=-1)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_scan_start_freezes_age_policy_and_date(self):
        response = {"status": "ready", "failures": [],
                    "checks": {"source_contracts": [], "manual_capture_sources": []}}
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(scan_start.preflight, "run_preflight", return_value=response):
                result = scan_start.start_scan(
                    "short_production", REGISTRY, output_root=Path(tmp),
                    now=datetime(2026, 10, 16, 7, tzinfo=timezone.utc),
                    skip_network=True, launch_browser=False, max_social_age_days=30)
            frozen = json.loads(Path(result["run_manifest"]).read_text(encoding="utf-8"))
            self.assertEqual(frozen["social_freshness"],
                             {"max_age_days": 30, "as_of_date": "2026-10-16"})
            self.assertEqual(result["social_freshness"], frozen["social_freshness"])

    def test_coverage_reads_frozen_window_and_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "social.json"
            raw.write_text(json.dumps({"entries": [
                make_note(1, "2026-10-08"), make_note(2, "2025-01-01"),
                make_note(3, "2026-10-09"), make_note(4, "2026-10-07"),
            ], "discovery": {"discovered_unique_entries": 20, "screened_entries": 10}}),
                encoding="utf-8")
            reg = {"coverage_profiles": {"freshness_test": {"required_source_ids": [SOURCE_ID]}},
                   "sources": [{"id": SOURCE_ID, "signal_requires_complete_content": True,
                                "coverage": {"min_signal_eligible_entries": 4}}]}
            manifest = {"run_id": "test-run", "sources": [{
                "source_id": SOURCE_ID, "status": "success", "signal_eligible_entries": 4,
                "artifacts": [{"path": str(raw)}],
            }]}
            base = {"run_root": tmp}
            fake_audit = {"failures": [], "artifact_integrity": "passed"}
            with patch.object(validate_source_coverage.GUARD, "audit_manifest", return_value=fake_audit):
                default = validate_source_coverage.validate(
                    "freshness_test", manifest, reg, run_manifest=base)
                restricted = validate_source_coverage.validate(
                    "freshness_test", manifest, reg, run_manifest={
                        **base, "social_freshness": {"max_age_days": 30, "as_of_date": "2026-10-16"}})
            self.assertEqual(default["formal_candidate_generation"], "allowed")
            self.assertEqual(restricted["formal_candidate_generation"], "blocked")
            self.assertIn("SOCIAL_COMPLETE_CONTENT_COUNT_MISMATCH",
                          [item["reason"] for item in restricted["failures"]])
            self.assertIn("COMPLETE_SIGNAL_ENTRY_SHORTFALL",
                          [item["reason"] for item in restricted["failures"]])


if __name__ == "__main__":
    unittest.main()
