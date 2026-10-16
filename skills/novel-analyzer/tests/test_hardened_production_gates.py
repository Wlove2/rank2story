import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(name):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"hardened_{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SOCIAL = load("social_evidence")
COVERAGE = load("validate_source_coverage")
SHORT = load("short_candidate_batch")


def valid_social(source_id="xiaohongshu_novel_demand_shared"):
    item = {
        "source_url": "https://example.test/note/1",
        "author": "reader-1",
        "published_at": "2026-07-20T10:00:00Z",
        "primary_signal_type": "reader_demand_or_book_shortage",
        "engagement": {"likes": 3},
        "content_complete": True,
        "full_text": "完整正文" * 100,
    }
    if source_id.startswith("xiaohongshu"):
        item.update({"images_total": 2, "images_read": 2})
    return item


class SocialEvidenceTests(unittest.TestCase):
    def test_empty_note_and_video_excerpt_are_not_complete(self):
        note = valid_social()
        note["full_text"] = ""
        note["content_complete"] = False
        video = valid_social("bilibili_novel_demand_shared")
        video["full_text"] = "只有摘录"
        with tempfile.TemporaryDirectory() as directory:
            note_path = Path(directory) / "note.json"
            video_path = Path(directory) / "video.json"
            note_path.write_text(json.dumps([note], ensure_ascii=False), encoding="utf-8")
            video_path.write_text(json.dumps([video], ensure_ascii=False), encoding="utf-8")
            self.assertEqual(SOCIAL.audit_social_files("xiaohongshu_novel_demand_shared", [note_path])["signal_eligible_entries"], 0)
            self.assertEqual(SOCIAL.audit_social_files("bilibili_novel_demand_shared", [video_path])["signal_eligible_entries"], 0)

    def test_complete_social_entry_is_normalized_with_stable_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "note.json"
            path.write_text(json.dumps([valid_social()], ensure_ascii=False), encoding="utf-8")
            result = SOCIAL.audit_social_files("xiaohongshu_novel_demand_shared", [path])
            self.assertEqual(result["signal_eligible_entries"], 1)
            self.assertTrue(result["eligible_entries"][0]["evidence_id"])


class RecomputedCoverageTests(unittest.TestCase):
    def test_manifest_claim_cannot_replace_complete_social_content(self):
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory)
            raw_dir = run_root / "raw" / "social"
            raw_dir.mkdir(parents=True)
            raw = raw_dir / "notes.json"
            raw.write_text(json.dumps([{"source_url": "https://example.test/empty", "content": ""}]), encoding="utf-8")
            stat = raw.stat()
            mtime = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
            run_manifest = {
                "run_id": "test-run",
                "run_root": str(run_root),
                "started_at": "2026-07-20T00:00:00Z",
                "paths": {"source_dirs": {"social": str(raw_dir)}},
            }
            artifact = {
                "path": "raw/social/notes.json",
                "artifact_type": "raw_response",
                "bytes": stat.st_size,
                "sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
                "file_mtime": mtime,
            }
            manifest = {"run_id": "test-run", "sources": [{
                "source_id": "social", "run_id": "test-run", "output_dir": str(raw_dir),
                "status": "success", "captured_at": mtime, "signal_eligible_entries": 8,
                "discovered_unique_entries": 30, "screened_entries": 15, "unique_accounts": 5,
                "max_entries_per_account": 2, "primary_signal_type_counts": {"reader_demand_or_book_shortage": 8},
                "artifacts": [artifact],
            }]}
            registry = {
                "coverage_profiles": {"test": {"required_source_ids": ["social"]}},
                "sources": [{"id": "social", "signal_requires_complete_content": True,
                             "coverage": {"min_signal_eligible_entries": 1}}],
            }
            result = COVERAGE.validate("test", manifest, registry, run_manifest=run_manifest)
            reasons = {failure["reason"] for failure in result["failures"]}
            self.assertIn("SOCIAL_COMPLETE_CONTENT_COUNT_MISMATCH", reasons)
            self.assertIn("COMPLETE_SIGNAL_ENTRY_SHORTFALL", reasons)


class CandidateEvidenceTests(unittest.TestCase):
    def test_unknown_scan_evidence_is_rejected(self):
        packet = {"evidence": {"items": [{"evidence_id": "known", "source_item_id": "1", "manifest_id": "m"}]}}
        candidate = {"title": "新题", "market_evidence": [{
            "kind": "short_rank", "evidence_id": "invented", "source_item_id": "2", "manifest_id": "m"
        }]}
        with self.assertRaisesRegex(ValueError, "FROZEN_EVIDENCE_UNKNOWN"):
            SHORT.validate_frozen_evidence([candidate], packet)

    def test_search_page_or_incomplete_verification_is_rejected(self):
        records = {"新题": {"records": [
            {"check": "title_search", "status": "passed", "provider": "bing", "checked_at": "now",
             "query": "新题", "result_summary": "未发现", "reviewed_urls": ["https://www.bing.com/search?q=x"]},
            {"check": "concept_search", "status": "passed", "provider": "bing", "checked_at": "now",
             "query": "新题 概念", "result_summary": "未发现", "reviewed_urls": ["https://example.test/result"]},
        ]}}
        with self.assertRaisesRegex(ValueError, "direct reviewed result URL"):
            SHORT.verification_for("新题", records)


if __name__ == "__main__":
    unittest.main()
