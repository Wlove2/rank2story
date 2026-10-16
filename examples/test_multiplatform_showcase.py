"""Tests for historically verified seven-platform public metadata showcase.
No network, model, or private source path required.
"""
from __future__ import annotations
import json
import pathlib
import re
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
PREVIEW=ROOT/"examples/showcase/verified_multiplatform_preview_20261009.json"
SHOWCASE=ROOT/"docs/MULTIPLATFORM_SHOWCASE_20261009.md"

class MultiPlatformShowcaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=json.loads(PREVIEW.read_text(encoding="utf-8"))
        cls.doc=SHOWCASE.read_text(encoding="utf-8")

    def test_success_sources_and_seven_distinct_platforms(self):
        d=self.data
        self.assertEqual(d["date"],"2026-10-09")
        self.assertEqual((d["platform_count"],d["success_source_count"],d["optional_not_run"]),(7,9,3))
        self.assertEqual(set(d["platforms"]),{"fanqie","qimao","zongheng","jjwxc","qidian","xiaohongshu","bilibili"})
        self.assertEqual(len(d["source_manifest_sha256"]),64)

    def test_ranked_platform_units_not_conflated(self):
        p=self.data["platforms"]
        self.assertEqual((p["fanqie"]["web_categories"],p["fanqie"]["web_slots"]),(74,740))
        self.assertEqual((p["qimao"]["web_charts"],p["qimao"]["web_slots"]),(10,200))
        self.assertEqual(len(p["qimao"]["charts"]),10)
        self.assertTrue(all(x["slots"]==20 and len(x["top"])==3 for x in p["qimao"]["charts"]))
        for platform,exp in {"zongheng":(6,58,33),"jjwxc":(1,200,200),"qidian":(5,100,54)}.items():
            val=p[platform]
            self.assertEqual((val["chart_count"],val["rank_slots"],val["unique_books"]),exp)
            self.assertEqual(sum(x["slots"] for x in val["charts"]),exp[1])
        self.assertEqual(len(p["jjwxc"]["charts"][0]["top"]),12)

    def test_conflicting_qimao_female_update_ranks_not_published_as_verified(self):
        chart = next(x for x in self.data["platforms"]["qimao"]["charts"] if x["id"] == "female/updates")
        self.assertEqual(chart["rank_status"], "unverified_conflicting_historical_fields")
        self.assertTrue(all(row["rank"] is None and row["heat"] is None for row in chart["top"]))
        self.assertIn("女频·更新（名次未核）", self.doc)

    def test_social_qualification_caps_and_distinct_links(self):
        p=self.data["platforms"]
        x=p["xiaohongshu"];b=p["bilibili"]
        self.assertEqual((x["discovered_unique"],x["screened"],x["qualified"],x["unique_accounts"]),(26,27,4,4))
        self.assertEqual((b["discovered_unique"],b["screened"],b["qualified"],b["unique_accounts"]),(139,57,10,8))
        self.assertEqual(len(x["examples"]),4)
        self.assertEqual(len(b["examples"]),10)
        self.assertEqual(len({z["url"] for z in x["examples"]}),4)
        self.assertEqual(len({z["url"] for z in b["examples"]}),10)
        self.assertTrue(all(x["images_read"]==x["image_count"] for x in p["xiaohongshu"]["examples"]))
        self.assertEqual(b["types"],{
          "reader_demand_or_book_shortage":4,
          "negative_or_avoidance":1,
          "curator_roundup":2,
          "current_hotspot_or_rank_scan":3
        })

    def test_no_private_payload_in_public_data(self):
        raw=PREVIEW.read_text(encoding="utf-8").lower()
        for banned in ['"full_text"','"intro"','"subtitle_segments"','"cookie"','"signed_url"','"image_link"','"auth_token"','"author_id"']:
            self.assertNotIn(banned,raw)
        self.assertNotIn('d:\\',raw)
        self.assertNotIn('c:\\',raw)
        self.assertIn("七猫小说",self.doc)
        self.assertIn("晋江文学城",self.doc)
        self.assertIn("起点中文网",self.doc)
        self.assertIn("Bilibili",self.doc)

    def test_markdown_targets_exist_and_readme_highlights_all_seven(self):
        for name in ["README.md","docs/RESULTS.md","docs/MULTIPLATFORM_SHOWCASE_20261009.md"]:
            file=ROOT/name
            s=file.read_text(encoding="utf-8")
            for url in re.findall(r"\[[^\]\n]+\]\(([^)]+)\)",s):
                if url.startswith(("http:","https:","#")):
                    continue
                self.assertTrue((file.parent/url.split("#")[0]).exists(),(name,url))
        readme=(ROOT/"README.md").read_text(encoding="utf-8")
        for platform in ("番茄小说","七猫小说","纵横中文网","晋江文学城","起点中文网","小红书","Bilibili"):
            self.assertIn(platform,readme)
        self.assertIn("docs/MULTIPLATFORM_SHOWCASE_20261009.md",readme)

if __name__=="__main__":
    unittest.main()
