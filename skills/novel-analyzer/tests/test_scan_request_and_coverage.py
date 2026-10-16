import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(name):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


RESOLVE = load("resolve_scan_request")
COVERAGE = load("validate_source_coverage")


class NaturalLanguageRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads((ROOT / "references" / "source-registry.json").read_text(encoding="utf-8"))

    def test_short_scan_needs_no_internal_phrase_or_flag(self):
        result = RESOLVE.resolve("短篇扫榜", self.registry)
        self.assertEqual(result["profile_id"], "short_production")
        self.assertFalse(result["fixture_inputs_allowed"])
        self.assertFalse(result["user_needs_internal_flags"])
        self.assertEqual(result["analysis_sampling"]["base_top_n_per_list"], 6)
        self.assertEqual(result["analysis_sampling"]["adaptive_max_top_n_per_list"], 10)

    def test_long_scan_routes_independently(self):
        result = RESOLVE.resolve("扫长篇榜准备开书", self.registry)
        self.assertEqual(result["profile_id"], "comprehensive_long_production")

    def test_bare_scan_only_asks_for_lane(self):
        with self.assertRaisesRegex(ValueError, "lane is ambiguous"):
            RESOLVE.resolve("扫榜", self.registry)


class CoverageGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads((ROOT / "references" / "source-registry.json").read_text(encoding="utf-8"))

    def test_narrow_fanqie_rank_card_cannot_satisfy_rank_center(self):
        manifest = {"sources": [{"source_id": "fanqie_reader_bookmall_tab_103", "status": "success", "acquired_list_ids": ["完本榜", "推荐榜", "番茄榜", "黑马榜"]}]}
        result = COVERAGE.validate("short_production", manifest, self.registry)
        self.assertEqual(result["formal_candidate_generation"], "blocked")
        self.assertTrue(any(item["source_id"] == "fanqie_reader_short_rank_center" for item in result["failures"]))

    def test_missing_one_named_rank_blocks_even_when_other_sources_succeed(self):
        profile = self.registry["coverage_profiles"]["comprehensive_long_production"]
        sources = []
        definitions = {item["id"]: item for item in self.registry["sources"]}
        for source_id in profile["required_source_ids"] + profile.get("candidate_context_source_ids", []):
            definition = definitions[source_id]
            lists = list(definition.get("coverage", {}).get("required_list_ids", []))
            row = {"source_id": source_id, "status": "success", "acquired_list_ids": lists, "category_taxonomy_complete": True, "signal_eligible_entries": 8}
            if definition.get("signal_requires_complete_content"):
                row.update({
                    "discovered_unique_entries": 30,
                    "screened_entries": 15,
                    "unique_accounts": 5,
                    "max_entries_per_account": 2,
                    "primary_signal_type_counts": {"current_hotspot_or_rank_scan": 2, "curator_roundup": 2, "reader_demand_or_book_shortage": 2, "negative_or_avoidance": 1},
                })
            sources.append(row)
        target = next(item for item in sources if item["source_id"] == "fanqie_reader_novel_rank_center")
        target["acquired_list_ids"].remove("阅读榜")
        result = COVERAGE.validate("comprehensive_long_production", {"sources": sources}, self.registry)
        self.assertEqual(result["formal_candidate_generation"], "blocked")
        failure = next(item for item in result["failures"] if item["source_id"] == "fanqie_reader_novel_rank_center")
        self.assertIn("阅读榜", failure["missing_list_ids"])

    def test_owner_reduced_xhs_quota_still_enforces_content_and_diversity(self):
        profile = self.registry["coverage_profiles"]["short_production"]
        definitions = {item["id"]: item for item in self.registry["sources"]}
        sources = []
        for source_id in profile["required_source_ids"] + profile.get("candidate_context_source_ids", []):
            definition = definitions[source_id]
            row = {
                "source_id": source_id,
                "status": "success",
                "acquired_list_ids": definition.get("coverage", {}).get("required_list_ids", []),
                "category_taxonomy_complete": True,
                "signal_eligible_entries": 8,
            }
            if definition.get("signal_requires_complete_content"):
                row.update({
                    "discovered_unique_entries": 30,
                    "screened_entries": 15,
                    "unique_accounts": 5,
                    "max_entries_per_account": 2,
                    "primary_signal_type_counts": {"current_hotspot_or_rank_scan": 2, "curator_roundup": 2, "reader_demand_or_book_shortage": 2, "negative_or_avoidance": 1},
                })
            sources.append(row)
        xhs = next(item for item in sources if item["source_id"] == "xiaohongshu_novel_demand_shared")
        xhs["signal_eligible_entries"] = 3
        result = COVERAGE.validate("short_production", {"sources": sources}, self.registry)
        failure = next(item for item in result["failures"] if item["source_id"] == xhs["source_id"])
        self.assertEqual(failure["reason"], "COMPLETE_SIGNAL_ENTRY_SHORTFALL")
        self.assertEqual((failure["observed"], failure["required"]), (3, 4))

        xhs["signal_eligible_entries"] = 4
        xhs["unique_accounts"] = 2
        result = COVERAGE.validate("short_production", {"sources": sources}, self.registry)
        self.assertTrue(any(item["reason"] == "UNIQUE_ACCOUNT_SHORTFALL" for item in result["failures"] if item["source_id"] == xhs["source_id"]))


if __name__ == "__main__":
    unittest.main()
