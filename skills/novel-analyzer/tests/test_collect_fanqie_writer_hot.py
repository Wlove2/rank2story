import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "collect_fanqie_writer_hot.py"
SPEC = importlib.util.spec_from_file_location("collect_fanqie_writer_hot", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def response(items):
    return {"body": {"code": 0, "data": {"item_list": items}}}


class FanqieWriterHotTests(unittest.TestCase):
    def test_normalize_items_deduplicates_and_preserves_hot_types(self):
        raw = {
            "all": response([{"book_id": "1", "book_name": "A", "author": "作者", "content": "摘要", "word_number": 10000}]),
            "classic_hot": response([{"book_id": "1", "book_name": "A", "author": "作者", "content": "摘要", "word_number": 10000}]),
        }
        result = MODULE.normalize_items(raw)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["book_id"], "1")
        self.assertEqual(result[0]["hot_types"], ["all", "classic_hot"])

    def test_normalize_items_skips_invalid_item_lists(self):
        result = MODULE.normalize_items({
            "all": {"body": {"code": 1}},
            "classic_hot": {"body": {"code": 0, "data": {"item_list": [None]}}},
        })
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
