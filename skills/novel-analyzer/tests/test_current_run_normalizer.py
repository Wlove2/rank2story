import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "normalize_current_run_sources.py"
SPEC = importlib.util.spec_from_file_location("normalize_current_run_sources_test", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class CurrentRunNormalizerTests(unittest.TestCase):
    def test_url_only_paid_platform_rows_are_normalized(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            (source / "normalized_02.json").write_text(json.dumps({"lists": [{"items": [{
                "title": "原创书名", "author": "作者", "position": 1,
                "url": "https://example.test/book/42", "category": "现实",
            }]}]}, ensure_ascii=False), encoding="utf-8")
            entries, errors = MODULE.normalize_source("jjwxc", "jjwxc_quarter_rank_snapshot", source, "run-1")
            self.assertEqual(errors, [])
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["source_item_id"], "https://example.test/book/42")
            self.assertEqual(entries[0]["manifest_id"], "run-1:jjwxc_quarter_rank_snapshot")

    def test_social_quality_cannot_pass_on_one_complete_post(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_dirs = {}
            acquisition_sources = []
            for source_ids in MODULE.GROUPS.values():
                for source_id in source_ids:
                    source_dir = root / source_id
                    source_dir.mkdir()
                    source_dirs[source_id] = str(source_dir)
                    acquisition_sources.append({"source_id": source_id, "status": "success"})
                    if source_id not in MODULE.SOCIAL_SOURCE_IDS.values():
                        (source_dir / "normalized.json").write_text(json.dumps({"items": [{
                            "book_id": source_id, "title": "书", "author": "作者", "position": 1,
                        }]}), encoding="utf-8")
            xhs = root / "xiaohongshu_novel_demand_shared" / "note.json"
            xhs.write_text(json.dumps({"items": [{
                "source_url": "https://example.test/note/1", "author": "a",
                "published_at": "2026-07-20T10:00:00Z", "primary_signal_type": "curator_roundup",
                "engagement": {"likes": 1}, "content_complete": True, "full_text": "全文",
                "images_total": 1, "images_read": 1,
            }]}), encoding="utf-8")
            data, manifest = MODULE.build(
                {"run_id": "run-1", "paths": {"source_dirs": source_dirs}},
                {"run_id": "run-1", "sources": acquisition_sources},
            )
            self.assertTrue(data["entries"])
            self.assertEqual(manifest["formal_candidate_generation"], "not_run")
            xhs_row = next(row for row in manifest["sources"] if row["platform"] == "xiaohongshu")
            self.assertEqual(xhs_row["status"], "degraded")


if __name__ == "__main__":
    unittest.main()
