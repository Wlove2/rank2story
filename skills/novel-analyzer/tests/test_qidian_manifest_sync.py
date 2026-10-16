"""Qidian list presence must be proven by current official capture and raw hashes."""
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location(
    "qidian_sync_fixture", SCRIPTS / "sync_acquisition_manifest.py"
)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class QidianCaptureManifestTests(unittest.TestCase):
    URL = "https://www.qidian.com/rank/signNewBkAll/"

    def with_fixture(self, root: Path, *, repeat_id=False, hash_valid=True, url=None):
        items = [{
            "position": i + 1,
            "title": f"真实待测名称{i}",
            "url": f"https://www.qidian.com/book/{1049003034 + (0 if repeat_id else i)}/",
        } for i in range(20)]
        payload = {"url": url or self.URL, "items": items}
        path = root / "raw_new_book_01.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        capture = {
            "list_id": "new_book", "raw_file": path.name,
            "raw_sha256": digest if hash_valid else "0" * 64,
            "final_url": url or self.URL,
            "item_count": 20,
        }
        (root / "manifest.json").write_text(json.dumps({
            "required_list_ids": [
                "monthly_ticket", "hot_sales", "read_index",
                "recommendation", "new_book",
            ],
            "captures": [capture],
        }), encoding="utf8")
        return capture

    def test_valid_actual_collector_schema_detects_newbook(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.with_fixture(root)
            self.assertEqual(module.qidian_lists(root), ["new_book"])

    def test_invalid_sha_and_wrong_official_url_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.with_fixture(root, hash_valid=False)
            self.assertEqual(module.qidian_lists(root), [])
            self.with_fixture(root, url="https://www.qidian.com/rank/")
            self.assertEqual(module.qidian_lists(root), [])

    def test_repeated_books_cannot_fake_twenty_unique_rankings(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.with_fixture(root, repeat_id=True)
            self.assertEqual(module.qidian_lists(root), [])

    def test_no_manifest_does_not_accept_raw_filename_only(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.with_fixture(root)
            (root / "manifest.json").unlink()
            self.assertEqual(module.qidian_lists(root), [])

    def test_changed_raw_file_fails_sha_verification(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.with_fixture(root)
            with (root / "raw_new_book_01.json").open("a", encoding="utf8") as f:
                f.write(" ")
            self.assertEqual(module.qidian_lists(root), [])


if __name__ == "__main__":
    unittest.main()
