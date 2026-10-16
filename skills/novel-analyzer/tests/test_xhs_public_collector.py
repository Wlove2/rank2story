"""No-network tests for conservative public Xiaohongshu collector."""
import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
path = SCRIPTS / "collect_xiaohongshu_public_notes.py"
spec = importlib.util.spec_from_file_location("xhs_public_collector_under_test", path)
collector = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = collector
spec.loader.exec_module(collector)


class PublicXhsCollectorTests(unittest.TestCase):
    def test_signed_link_is_stripped(self):
        url = "https://www.xiaohongshu.com/search_result/123?xsec_token=SECRET&xsec_source=pc"
        self.assertEqual(
            collector.canonical_url(url),
            "https://www.xiaohongshu.com/search_result/123",
        )

    def test_signal_classification_must_be_grounded(self):
        self.assertEqual(collector.classify("求推文，书荒"), "reader_demand_or_book_shortage")
        self.assertEqual(collector.classify("小说避雷：勿入"), "negative_or_avoidance")
        self.assertEqual(collector.classify("新书书单合集"), "curator_roundup")
        self.assertIsNone(collector.classify("生活和记录"))

    def test_numeric_likes(self):
        self.assertEqual(collector.numeric_likes("1.2万"), 12000)
        self.assertEqual(collector.numeric_likes("985"), 985)
        self.assertIsNone(collector.numeric_likes("未知"))
        self.assertIsNone(collector.numeric_likes(-3))

    def test_genuine_text_only_note_can_be_complete(self):
        search = {
            "url": "https://www.xiaohongshu.com/search_result/abc?xsec_token=PRIVATE",
            "title": "2026年书荒，求推荐",
            "author": "可核验用户",
            "published_at": "2026-10-09",
            "likes": "100",
        }
        note = {
            "url": "https://www.xiaohongshu.com/explore/abc",
            "title": search["title"],
            "description": "求推荐一本有具体生存代价的都市悬疑小说，最好第一章就有职业伦理抉择。" * 4,
            "note_present": True,
            "images_total": 0,
            "videos": 0,
        }
        result = collector.normalize_note(search, note)
        self.assertTrue(result["content_complete"])
        self.assertTrue(result["signal_eligible"])
        self.assertNotIn("PRIVATE", str(result))
        self.assertEqual(result["images_total"], 0)
        self.assertEqual(result["engagement"]["likes"], 100)

    def test_gallery_and_video_are_never_declared_complete_from_dom_alone(self):
        search = {
            "url": "https://www.xiaohongshu.com/search_result/abc?xsec_token=PRIVATE",
            "author": "作者",
            "published_at": "2026-10-09",
            "likes": 123,
        }
        note = {
            "url": "https://www.xiaohongshu.com/explore/abc",
            "title": "2026小说书单",
            "description": "非常详细的内容和读后感" * 14,
            "note_present": True,
            "images_total": 9,
            "videos": 0,
        }
        result = collector.normalize_note(search, note)
        self.assertFalse(result["content_complete"])
        self.assertEqual(result["images_read"], 0)
        self.assertEqual(result["incomplete_reason"], "images_or_video_not_fully_read")
        note["images_total"] = 0
        note["videos"] = 1
        self.assertFalse(collector.normalize_note(search, note)["content_complete"])

    def test_gallery_all_images_need_actual_local_vision_results(self):
        search = {
            "url": "https://www.xiaohongshu.com/search_result/abc?xsec_token=TRANSIENT",
            "title": "书荒求推荐的小说合集",
            "author": "网友乙",
            "published_at": "2026-10-09",
            "likes": "12",
        }
        note = {
            "url": "https://www.xiaohongshu.com/explore/abc",
            "title": search["title"],
            "description": "针对真实网文小说的推荐合集，给出清楚的情节、角色及阅读取舍。" * 6,
            "note_present": True, "images_total": 2, "videos": 0,
            "vision_images": [{
                "index": 0, "text": "识别图片第1张上的推荐书单以及情节说明。",
                "image_sha256": "a" * 64, "model": "qwen2.5vl:7b",
                "reading_status": "machine_read_unreviewed",
            }],
        }
        partial = collector.normalize_note(search, note)
        self.assertEqual(partial["images_read"], 1)
        self.assertFalse(partial["signal_eligible"])
        note["vision_images"].append({
            "index": 1, "text": "识别图片第2张上的书单作者与特点。",
            "image_sha256": "b" * 64, "model": "qwen2.5vl:7b",
            "reading_status": "machine_read_unreviewed",
        })
        complete = collector.normalize_note(search, note)
        self.assertTrue(complete["content_complete"])
        self.assertEqual(complete["images_read"], 2)
        self.assertIn(note["vision_images"][0]["text"], complete["full_text"])
        self.assertNotIn("TRANSIENT", str(complete))

    def test_vision_cdn_restricts_untrusted_urls(self):
        from xiaohongshu_local_vision import sanitize_public_cdn
        with self.assertRaises(ValueError):
            sanitize_public_cdn("https://attacker.example/pic.jpg")
        with self.assertRaises(ValueError):
            sanitize_public_cdn("http://sns-webpic-qc.xhscdn.com/x")
        self.assertEqual(
            sanitize_public_cdn("https://sns-webpic-qc.xhscdn.com/x"),
            "https://sns-webpic-qc.xhscdn.com/x",
        )

    def test_untrusted_domains_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "NOTE_URL_NOT_XHS"):
            collector.normalize_note(
                {"url": "https://other.example/post/1"},
                {"url": "https://other.example/post/1"},
            )


if __name__ == "__main__":
    unittest.main()
