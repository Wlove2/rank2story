import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(name):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


RANK = load("rank_scraper")
SOURCE = load("long_source_refresh")


class PaidPlatformAdapterTests(unittest.TestCase):
    def test_zongheng_plain_text_keeps_rank_type_and_metric(self):
        text = """来源：web_extract https://www.zongheng.com/rank.html
时间：2026-07-09
## 月票榜 TOP10
1 齐天 12580
2 江山绝色榜 6292
## 新书榜/人气榜
- 无敌圣体 18474 人气
"""
        rows = RANK.parse_zongheng_snapshot(text)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["rank_type"], "monthly_ticket")
        self.assertEqual(rows[0]["metric"], 12580)
        self.assertEqual(rows[-1]["metric_type"], "popularity")

    def test_jjwxc_plain_text_keeps_author_words_and_points(self):
        text = """来源：web_extract https://www.jjwxc.net/topten.php?orderstr=4
时间：2026-07-09
## 季度榜 TOP10
1 姑娘别哭《天阶夜色》 原创-言情-近代现代-爱情 382520字 5,774,497,280积分
"""
        row = RANK.parse_jjwxc_snapshot(text)[0]
        self.assertEqual(row["title"], "天阶夜色")
        self.assertEqual(row["author"], "姑娘别哭")
        self.assertEqual(row["word_count"], 382520)
        self.assertEqual(row["metric"], 5774497280)

    def test_paid_rows_are_signal_eligible_shape(self):
        text = """来源：web_extract https://www.zongheng.com/rank.html
时间：2026-07-09
## 点击榜 TOP10
1 无敌天命 212381
"""
        row = RANK.parse_zongheng_snapshot(text)[0]
        self.assertEqual(row["evidence_layer"], "paid_platform_corroboration")
        self.assertEqual(row["rank_type"], "click")


class SocialAdapterTests(unittest.TestCase):
    def test_summary_is_manifest_only(self):
        text = """来源：web_search 检索词：
- 网文 2026
时间：2026-07-09
## 搜索摘要
- 一个摘要
## 有效信号
- 一个未经原帖核实的判断
"""
        summary = RANK.parse_social_summary(text, "xiaohongshu")
        self.assertEqual(summary["sample_completeness"], "metadata_only")
        self.assertEqual(summary["eligible_signal_entries"], 0)

    def test_complete_original_can_enter_social_signal(self):
        item = {
            "title": "完整原帖",
            "author": "账号甲",
            "source_url": "https://example.test/post/1",
            "published_at": "2026-07-16T00:00:00+08:00",
            "engagement": {"likes": 10, "comments": 2, "collects": 3},
            "full_text": "caption 与全部图片文字",
            "content_complete": True,
            "images_total": 3,
            "images_read": 3,
            "signals": {"genre": "悬疑"},
            "primary_signal_type": "reader_demand_or_book_shortage",
            "source_relation": "independent",
        }
        row = SOURCE.social_original_entry(item, "xiaohongshu", Path("xhs.json"), 1)
        self.assertIsNotNone(row)
        self.assertEqual(row["metric"], 15)

    def test_incomplete_original_is_excluded(self):
        item = {
            "title": "只读首图",
            "author": "账号乙",
            "source_url": "https://example.test/post/2",
            "published_at": "2026-07-16T00:00:00+08:00",
            "engagement": {"likes": 10},
            "full_text": "不完整",
            "content_complete": True,
            "images_total": 3,
            "images_read": 1,
            "primary_signal_type": "curator_roundup",
        }
        row = SOURCE.social_original_entry(item, "xiaohongshu", Path("xhs.json"), 1)
        self.assertIsNone(row)

    def test_official_rank_repost_is_context_only(self):
        item = {
            "title": "原榜单转载",
            "author": "账号丙",
            "source_url": "https://example.test/post/3",
            "published_at": "2026-07-16T00:00:00+08:00",
            "engagement": {"likes": 10},
            "full_text": "完整转载内容",
            "content_complete": True,
            "primary_signal_type": "current_hotspot_or_rank_scan",
            "source_relation": "official_rank_repost",
        }
        row = SOURCE.social_original_entry(item, "xiaohongshu", Path("xhs.json"), 1)
        self.assertIsNotNone(row)
        self.assertFalse(row["signal_eligible"])
        self.assertEqual(row["heat_increment"], 0)

    def test_social_batch_records_discovery_types_and_account_diversity(self):
        types = [
            "current_hotspot_or_rank_scan", "current_hotspot_or_rank_scan",
            "curator_roundup", "curator_roundup",
            "reader_demand_or_book_shortage", "reader_demand_or_book_shortage",
            "negative_or_avoidance", "creator_market_analysis",
        ]
        entries = []
        for index, signal_type in enumerate(types):
            entries.append({
                "title": f"内容{index}", "author": f"账号{index % 5}",
                "source_url": f"https://example.test/post/{index}",
                "published_at": "2026-07-16T00:00:00+08:00",
                "engagement": {"likes": index + 1}, "full_text": "完整内容",
                "content_complete": True, "primary_signal_type": signal_type,
                "source_relation": "independent",
            })
        payload = {"discovery": {"discovered_unique_entries": 30, "screened_entries": 15}, "entries": entries}
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            path = Path(tmp) / "xhs.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            summary, normalized = SOURCE.inspect_social("xiaohongshu", path, date(2026, 7, 19))
        self.assertEqual(len(normalized), 8)
        self.assertEqual(summary["unique_accounts"], 5)
        self.assertEqual(summary["max_entries_per_account"], 2)
        self.assertEqual(summary["primary_signal_type_counts"]["curator_roundup"], 2)

    def test_all_registered_long_sources_get_manifest_records(self):
        qidian = SOURCE.missing_registered_source("qidian")
        self.assertEqual(qidian["status"], "not_acquired")
        self.assertEqual(qidian["signal_eligible_entries"], 0)

    def test_comprehensive_gate_rejects_any_missing_registered_source(self):
        sources = []
        for name in SOURCE.REQUIRED_LONG_SOURCES:
            row = {"platform": name, "status": "success", "valid_entries": 1, "signal_eligible_entries": 1}
            if name in SOURCE.SOCIAL_PLATFORMS:
                row.update({
                    "discovered_unique_entries": 30, "screened_entries": 15,
                    "signal_eligible_entries": 8, "unique_accounts": 5,
                    "max_entries_per_account": 2,
                    "primary_signal_type_counts": {"current_hotspot_or_rank_scan": 2, "curator_roundup": 2, "reader_demand_or_book_shortage": 2, "negative_or_avoidance": 1},
                })
            sources.append(row)
        self.assertEqual(SOURCE.source_gate_reasons(sources), [])
        sources[-1] = SOURCE.missing_registered_source("qidian")
        self.assertIn("qidian:not_acquired", SOURCE.source_gate_reasons(sources))


if __name__ == "__main__":
    unittest.main()
