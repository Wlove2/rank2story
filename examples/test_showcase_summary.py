"""Test the privacy-safe, aggregate-only historical results showcased in README."""
from __future__ import annotations
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SUMMARY=ROOT/"examples"/"showcase"/"results-summary.json"
DOC=ROOT/"docs"/"RESULTS.md"
README=ROOT/"README.md"

class ShowcaseSummaryTests(unittest.TestCase):
    def setUp(self):
        self.data=json.loads(SUMMARY.read_text(encoding="utf-8"))

    def test_real_scan_groups_sum_exactly_to_verified_totals(self):
        scan=self.data["scan"]
        self.assertEqual(scan["date"],"2026-10-09")
        self.assertEqual((scan["source_coverage"]["required"],scan["source_coverage"]["passed"]),(9,9))
        self.assertEqual(scan["story_atoms_accepted"],70)
        groups=scan["rank_groups"]
        self.assertEqual({(g["audience"],g["chart"]) for g in groups},{("female","new"),("female","read"),("male","new"),("male","read")})
        self.assertTrue(all(g["status"]=="success" for g in groups))
        self.assertEqual(sum(g["categories"] for g in groups),scan["categories_total"])
        self.assertEqual(sum(g["records"] for g in groups),scan["records_total"])
        self.assertEqual((scan["categories_total"],scan["records_total"]),(74,740))
        self.assertTrue(scan["historical_font_decoder_required"])

    def test_original_success_is_not_claimed_by_new_default(self):
        original=self.data["historical_candidate"]
        self.assertEqual(original["control_policy"],"quality_strict")
        self.assertEqual((original["kernels_generated"],original["passed_review"],original["final_delivery"]),(9,5,5))
        self.assertEqual(original["formal_verify"],"passed")
        self.assertTrue(original["curated_real_cards_in_review_repo"])
        self.assertEqual(original["curated_cards_count"],5)
        self.assertNotEqual(original["date"],self.data["scan"]["date"])
        self.assertIn("separate historical runs",self.data["caution"])
        self.assertIn("4.4.2 has no full-model delivery pass",self.data["caution"])

    def test_real_scan_preview_has_74_categories_and_222_verified_metadata_rows(self):
        data=json.loads((ROOT/"examples/showcase/verified_scan_book_preview_20261009.json").read_text(encoding="utf-8"))
        self.assertEqual((data["full_categories"],data["full_records"]),(74,740))
        self.assertEqual(len(data["groups"]),4)
        cats=[cat for group in data["groups"] for cat in group["categories"]]
        self.assertEqual(len(cats),74)
        books=[book for cat in cats for book in cat["preview"]]
        self.assertEqual(len(books),222)
        self.assertTrue(all(cat["collected"]==10 for cat in cats))
        self.assertTrue(all(b["title"] and b["official_page"].startswith("https://fanqienovel.com/page/") for b in books))
        self.assertFalse(any("intro" in b or "cover" in b or "cookie" in b for b in books))
        self.assertIn("222", (ROOT/"docs/SCAN_SHOWCASE_20261009.md").read_text(encoding="utf-8"))

    def test_five_actual_cards_include_creative_detail_not_placeholder(self):
        obj=json.loads((ROOT/"examples/showcase/verified_candidate_cards_20260905.json").read_text(encoding="utf-8"))
        self.assertEqual(obj["source_run_id"],"cand-20260905-132200-11f9484c")
        self.assertEqual((obj["generated"],obj["passed_review"],obj["delivered"]),(9,5,5))
        self.assertEqual(len(obj["cards"]),5)
        self.assertEqual([c["candidate_id"] for c in obj["cards"]],["A-C02","B-C01","B-C03","C-C02","C-C03"])
        for c in obj["cards"]:
            self.assertEqual(len(c["opening_300_beats"]),5)
            self.assertEqual(len(c["reward_cycle"]),6)
            self.assertEqual(len(c["three_payoffs"]),3)
            self.assertTrue(c["one_line_concept"] and c["short_closure"] and c["risks"])
            self.assertNotIn("evidence_atom_ids",c)
        self.assertIn("A-C02", (ROOT/"docs/CANDIDATE_SHOWCASE_20260905.md").read_text(encoding="utf-8"))

    def test_no_unreviewed_private_source_fields_in_public_summary(self):
        banned=("cookie","access_token","secret","authorization","signed_url","base_url","book_title","author_name","raw_text","prompt","original_work")
        raw=SUMMARY.read_text(encoding="utf-8").lower()
        for key in banned:
            with self.subTest(key=key):
                self.assertNotIn('"'+key+'"',raw)

    def test_readme_links_documented_results(self):
        readme=README.read_text(encoding="utf-8")
        result=DOC.read_text(encoding="utf-8")
        for s in ("docs/RESULTS.md","docs/MULTIPLATFORM_SHOWCASE_20261009.md","docs/CANDIDATE_SHOWCASE_20260905.md","74/74","740","abc_branch_one","quality_strict"):
            self.assertIn(s,readme)
        for s in ("190","180","9/9","5","verify"):
            self.assertIn(s,result)

if __name__=="__main__":
    unittest.main()
