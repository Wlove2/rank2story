import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "build_short_evidence_catalog.py"
SPEC = importlib.util.spec_from_file_location("build_short_evidence_catalog", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ShortEvidenceCatalogTests(unittest.TestCase):
    def test_length_and_completeness_contracts_are_distinct(self):
        fanqie = [
            {"book_id": "a", "book_name": "常规短篇", "word_number": 10000, "content": "摘要"},
            {"book_id": "b", "book_name": "官方较短短篇", "word_number": 9999, "content": "摘要"},
        ]
        qimao = {"rank_type": "story_rec_list", "items": [{"book_id": "c", "title": "平台短故事", "intro": "简介"}]}
        catalog = MODULE.build_catalog(fanqie, qimao, "fq-scan", "qm-scan")
        by_id = {item["source_item_id"]: item for item in catalog["items"]}
        self.assertEqual(by_id["a"]["platform_format"], "official_short")
        self.assertEqual(by_id["b"]["lane_classification"], "short")
        self.assertEqual(by_id["b"]["capacity_band"], "under_10k")
        self.assertEqual(by_id["c"]["capacity_band"], "unknown")
        self.assertEqual(catalog["stats"]["official_short_count"], 3)
        self.assertEqual(by_id["a"]["rank_status"], "complete")
        self.assertEqual(by_id["a"]["sample_status"], "partial_200_char_excerpt")
        self.assertEqual(by_id["c"]["sample_status"], "metadata_blurb_only")
        self.assertEqual(by_id["a"]["manifest_id"], "fq-scan")
        self.assertEqual(by_id["c"]["manifest_id"], "qm-scan")

    def test_reader_short_items_carry_source_id_and_list_id(self):
        """Every item must carry a source_id that maps into source_mix_policy cohorts.

        Regression for WOR-124: the 60 fanqie reader short items were emitted without
        source_id/list_id, so candidate S1 atoms referencing them failed
        ATOM_SOURCE_COHORT_MISMATCH on every gap-fill round.
        """
        fanqie = [
            {"book_id": "w1", "book_name": "作者榜书", "word_number": 10000, "content": "摘要", "hot_types": ["all"]},
        ]
        reader = {
            "name": "番茄短篇榜",
            "items": [
                {"position": 1, "book_id": "r1", "title": "读者榜书", "author": "作者", "category": "都市", "word_count": 12000},
            ],
        }
        qimao = {"rank_type": "story_rec_list", "items": [{"book_id": "q1", "title": "七猫书", "intro": "简介"}]}
        catalog = MODULE.build_catalog(
            fanqie,
            qimao,
            fanqie_manifest_id="fanqie-writer-hot-current",
            qimao_manifest_id="qimao-reader-story-current",
            fanqie_reader=reader,
            fanqie_reader_manifest_id="fanqie-reader-short-current",
        )
        expected = {
            "fanqie-writer-w1": ("fanqie_writer_hot_stories", "writer_hot_stories/all"),
            "fanqie-reader-r1": ("fanqie_reader_short_rank_center", "reader_app_short_rank/番茄短篇榜"),
            "qimao-story-q1": ("qimao_reader_story_rank_center", "reader_story_leader_board/story_rec_list"),
        }
        by_evidence = {item["evidence_id"]: item for item in catalog["items"]}
        self.assertEqual(len(catalog["items"]), 3)
        for evidence_id, (source_id, list_id) in expected.items():
            self.assertEqual(by_evidence[evidence_id]["source_id"], source_id, evidence_id)
            self.assertEqual(by_evidence[evidence_id]["list_id"], list_id, evidence_id)
            # source_id must be a registered cohort source
            self.assertIn(source_id, {
                "fanqie_writer_hot_stories",
                "fanqie_reader_short_rank_center",
                "qimao_reader_story_rank_center",
                "xiaohongshu_novel_demand_shared",
                "bilibili_novel_demand_shared",
            })


if __name__ == "__main__":
    unittest.main()
