import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SourceRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads(
            (ROOT / "references" / "source-registry.json").read_text(encoding="utf-8")
        )
        cls.sources = {source["id"]: source for source in cls.registry["sources"]}

    def test_acquired_cross_platform_sources_are_not_fallbacks(self):
        expected = {
            "zongheng_public_rank_snapshot",
            "jjwxc_quarter_rank_snapshot",
            "xiaohongshu_novel_demand_shared",
            "bilibili_novel_demand_shared",
            "qidian_paid_trend_target",
        }
        self.assertTrue(expected.issubset(self.sources))
        self.assertEqual(self.registry["fallbacks"], [])
        self.assertEqual(
            self.sources["qidian_paid_trend_target"]["accepted_baseline"]["status"],
            "acquired",
        )

    def test_reader_baselines_keep_slots_separate_from_unique_books(self):
        fanqie = self.sources["fanqie_reader_bookmall_tab_103"]["accepted_baseline"]
        qimao = self.sources["qimao_reader_default_hot_card"]["accepted_baseline"]
        self.assertEqual(fanqie["rank_slots"], 40)
        self.assertEqual(fanqie["unique_books"], 34)
        self.assertEqual(qimao["items"], 8)

    def test_full_app_rank_centers_are_separate_from_diagnostic_cards(self):
        self.assertEqual(len(self.sources["fanqie_reader_novel_rank_center"]["coverage"]["required_list_ids"]), 11)
        self.assertEqual(len(self.sources["qimao_reader_rank_center"]["coverage"]["required_list_ids"]), 29)
        self.assertEqual(self.sources["fanqie_reader_bookmall_tab_103"]["role"], "diagnostic_only")
        self.assertEqual(self.sources["qimao_reader_default_hot_card"]["role"], "diagnostic_only")

    def test_summary_sources_cannot_claim_original_content(self):
        for source_id in (
            "xiaohongshu_novel_demand_shared",
            "bilibili_novel_demand_shared",
        ):
            baseline = self.sources[source_id]["accepted_baseline"]
            self.assertEqual(baseline["sample"], "metadata_only")
            self.assertEqual(baseline["signal_eligible_entries"], 0)

    def test_comprehensive_profiles_name_every_required_source(self):
        profiles = self.registry["coverage_profiles"]
        self.assertEqual(len(profiles["short_production"]["required_source_ids"]), 5)
        self.assertEqual(len(profiles["short_production"]["candidate_context_source_ids"]), 3)
        self.assertEqual(len(profiles["comprehensive_long_production"]["required_source_ids"]), 9)
        self.assertEqual(len(profiles["comprehensive_long_production"]["candidate_context_source_ids"]), 3)

    def test_every_required_source_has_a_machine_collection_contract(self):
        for profile in self.registry["coverage_profiles"].values():
            for source_id in profile["required_source_ids"]:
                contract = self.sources[source_id].get("collection_contract")
                self.assertIsInstance(contract, dict, source_id)
                self.assertIn(contract.get("status"), {"verified_executable", "partial_only", "unresolved"})
                self.assertIn(contract.get("coverage_capability"), {"complete", "partial", "none"})

    def test_verified_reader_rank_centers_are_in_production(self):
        fanqie_short = self.sources["fanqie_reader_short_rank_center"]["collection_contract"]
        qimao_short = self.sources["qimao_reader_story_rank_center"]["collection_contract"]
        fanqie_long = self.sources["fanqie_reader_novel_rank_center"]["collection_contract"]
        qimao_long = self.sources["qimao_reader_rank_center"]["collection_contract"]
        self.assertEqual(fanqie_short["status"], "verified_executable")
        self.assertEqual(fanqie_short["verification"]["algorithm"], "601")
        self.assertEqual(fanqie_long["verification"]["algorithm_count"], 11)
        self.assertEqual(qimao_long["verification"]["current_named_list_count"], 29)
        self.assertEqual(qimao_long["verification"]["category_expansion_list_count"], 74)
        self.assertEqual(qimao_short["status"], "verified_executable")
        self.assertEqual(qimao_short["coverage_capability"], "complete")
        self.assertEqual(qimao_short["verification"]["acquired_matrix_list_count"], 26)
        self.assertTrue(qimao_short["verification"]["exact_ordered_ids"])

    def test_lane_partition_is_explicit_and_unknown_social_is_not_scored(self):
        policy = self.registry["lane_classification_policy"]
        self.assertIn("fanqie_writer_hot_stories", policy["official_short_surfaces"])
        self.assertIn("fanqie_reader_novel_rank_center", policy["official_long_surfaces"])
        self.assertIn("fanqie_writer_activities", policy["shared_context_surfaces"])
        self.assertEqual(
            set(policy["shared_social_surfaces"]),
            {"xiaohongshu_novel_demand_shared", "bilibili_novel_demand_shared"},
        )
        for source_id in policy["shared_social_surfaces"]:
            self.assertEqual(set(self.sources[source_id]["lanes"]), {"short", "long"})
            self.assertEqual(self.sources[source_id]["lane_scope"], "both")
            coverage = self.sources[source_id]["coverage"]
            self.assertEqual(coverage["min_signal_eligible_entries"], 4 if source_id == "xiaohongshu_novel_demand_shared" else 5)
            self.assertEqual(coverage["min_discovered_unique_entries"], 12 if source_id == "xiaohongshu_novel_demand_shared" else 20)
            self.assertEqual(coverage["min_screened_entries"], 6 if source_id == "xiaohongshu_novel_demand_shared" else 10)
            self.assertEqual(coverage["min_unique_accounts"], 3 if source_id == "xiaohongshu_novel_demand_shared" else 3)
            self.assertEqual(coverage["max_signal_entries_per_account"], 2)
        self.assertTrue(policy["social_both_scoring_eligible"])
        self.assertFalse(policy["unknown_scoring_eligible"])

    def test_source_mix_caps_are_explicit_and_sum_to_one(self):
        mixes = self.registry["source_mix_policy"]
        for lane in ("long", "short"):
            caps = [item["cap"] for item in mixes[lane].values() if isinstance(item, dict) and "cap" in item]
            self.assertAlmostEqual(sum(caps), 1.0)
        self.assertEqual(mixes["long"]["fanqie_official"]["cap"], 0.40)
        self.assertEqual(mixes["long"]["qimao_official"]["cap"], 0.20)
        self.assertEqual(mixes["long"]["xiaohongshu_demand"]["cap"], 0.10)
        self.assertEqual(mixes["short"]["xiaohongshu_demand"]["cap"], 0.15)


if __name__ == "__main__":
    unittest.main()
