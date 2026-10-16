"""Owner-approved social sampling quotas are source-specific."""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
spec = importlib.util.spec_from_file_location("normalize_owner_social_policy", SCRIPTS / "normalize_current_run_sources.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class OwnerSourcePolicyTests(unittest.TestCase):
    def test_xhs_and_bilibili_have_distinct_sampling(self):
        xhs = module.social_coverage("xiaohongshu_novel_demand_shared")
        bili = module.social_coverage("bilibili_novel_demand_shared")
        self.assertEqual((xhs["min_discovered_unique_entries"], xhs["min_screened_entries"],
                          xhs["min_signal_eligible_entries"], xhs["min_unique_accounts"]), (12, 6, 4, 3))
        self.assertEqual((bili["min_discovered_unique_entries"], bili["min_screened_entries"],
                          bili["min_signal_eligible_entries"], bili["min_unique_accounts"]), (20, 10, 5, 3))
        self.assertEqual(xhs["max_signal_entries_per_account"], 2)
        self.assertEqual(bili["max_signal_entries_per_account"], 2)
        self.assertEqual(bili["required_primary_signal_type_counts"], {
            "current_hotspot_or_rank_scan": 1,
            "curator_roundup": 1,
            "reader_demand_or_book_shortage": 1,
            "negative_or_avoidance": 1,
        })

    def test_all_image_completeness_still_required_for_xhs(self):
        import importlib.util
        s=importlib.util.spec_from_file_location("social_owner_policy_test",SCRIPTS/"social_evidence.py")
        social=importlib.util.module_from_spec(s)
        sys.modules[s.name]=social
        s.loader.exec_module(social)
        note={
            "url":"https://www.xiaohongshu.com/explore/123",
            "author":"one_public_author",
            "published_at":"2026-10-09",
            "primary_signal_type":"reader_demand_or_book_shortage",
            "engagement":{"likes":10},
            "full_text":"全部截图实质内容"+"abc"*80,
            "content_complete":True,
            "images_total":9,
            "images_read":8,
        }
        self.assertIsNone(social.complete_entry(note,"xiaohongshu_novel_demand_shared")[0])
        note["images_read"]=9
        self.assertIsNotNone(social.complete_entry(note,"xiaohongshu_novel_demand_shared")[0])


if __name__ == "__main__":
    unittest.main()
