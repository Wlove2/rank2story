import importlib.util
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs


ROOT = Path(__file__).resolve().parents[1]


def load(name):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


FANQIE = load("collect_fanqie_reader_ranks")
QIMAO = load("collect_qimao_reader_ranks")
PAID = load("collect_paid_platform_ranks")


class QimaoStoryCollectorTests(unittest.TestCase):
    def test_query_has_independent_signature(self):
        query = QIMAO.signed_query({
            "rank_type": "story_trend_list",
            "category_id": "758",
            "category_type": "2",
            "cache_ver": "",
            "refresh_page": "2",
        })
        values = parse_qs(query, keep_blank_values=True)
        self.assertEqual(values["rank_type"], ["story_trend_list"])
        self.assertEqual(values["category_id"], ["758"])
        self.assertEqual(values["sign"], ["54b9527ac16c97d20be932280dfd96ae"])

    def test_story_matrix_expands_rank_and_category_taxonomies(self):
        seed = {"data": {
            "rank_list": [
                {"type": "story_rec_list", "cache_ver": "0"},
                {"type": "story_trend_list", "cache_ver": "0"},
            ],
            "category_list": [
                {"category_id": "0", "category_type": "0"},
                {"category_id": "758", "category_type": "2"},
            ],
            "refresh_page": "2",
        }}
        matrix = QIMAO.story_matrix(seed)
        self.assertEqual(len(matrix), 4)
        self.assertIn({
            "rank_type": "story_trend_list",
            "category_id": "758",
            "category_type": "2",
            "cache_ver": "0",
            "refresh_page": "2",
        }, matrix)

    def test_incomplete_taxonomy_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "taxonomy incomplete"):
            QIMAO.story_matrix({"data": {
                "rank_list": [{"type": "story_rec_list"}],
                "category_list": [{"category_id": "0", "category_type": "0"}],
            }})


class ReaderRankCenterCollectorTests(unittest.TestCase):
    def test_fanqie_contract_has_11_long_algorithms_and_independent_short(self):
        self.assertEqual(len(FANQIE.LONG_RANKS), 11)
        self.assertEqual(FANQIE.SHORT_RANKS, {"601": "番茄短篇榜"})
        self.assertNotEqual(
            FANQIE.rank_params({}, "601", "short")["algo_type"],
            FANQIE.rank_params({}, "101", "long")["algo_type"],
        )

    def test_fanqie_short_normalization_keeps_official_lane_and_capacity(self):
        payload = {"data": {"book_data": [
            {"book_id": "0", "book_name": "很短", "word_number": 6000},
            {"book_id": "1", "book_name": "短", "word_number": 12000},
            {"book_id": "2", "book_name": "长", "word_number": 120000},
        ]}}
        rank = FANQIE.normalize_rank(payload, "601", "番茄短篇榜", "short")
        self.assertEqual([item["target_short_fit"] for item in rank["items"]], [True, True, True])
        self.assertEqual([item["target_capacity_fit"] for item in rank["items"]], [True, True, False])

    def test_qimao_current_official_taxonomy_is_29_not_fake_30(self):
        self.assertEqual(sum(map(len, QIMAO.EXPECTED_LONG_TAXONOMY.values())), 29)
        self.assertEqual(len(QIMAO.EXPECTED_LONG_TAXONOMY["3"]), 5)
        self.assertNotIn("recommend_list", QIMAO.EXPECTED_LONG_TAXONOMY["3"])

    def test_registry_names_can_be_emitted_without_placeholder_aliases(self):
        names = [
            f"{QIMAO.TAB_NAMES[tab]}/{name}"
            for tab, ranks in QIMAO.EXPECTED_LONG_TAXONOMY.items()
            for name in ranks.values()
        ]
        self.assertEqual(len(names), 29)
        self.assertIn("男生/角色榜", names)
        self.assertNotIn("图书/推荐榜", names)

    def test_qimao_character_rank_is_preserved_as_character_records(self):
        payload = {"data": {
            "rank_type": "character_list", "category_id": "0", "category_type": "0",
            "character_list": [{"id": "book-1", "character_id": "role-1", "nickname": "甲"}],
        }}
        rank = QIMAO.normalize_long(payload, tab_type="1", rank_name="角色榜")
        self.assertEqual(rank["record_kind"], "character")
        self.assertEqual(QIMAO.record_ids(rank), ["role-1"])


class PaidPlatformCollectorTests(unittest.TestCase):
    def test_zongheng_missing_modules_fails_closed(self):
        raw = b"<html><body><section class='zh-modules-rank'></section></body></html>"
        with self.assertRaisesRegex(ValueError, "expected 6 rank modules"):
            PAID.parse_zongheng(raw, "2026-07-20T00:00:00Z")

    def test_qidian_cli_sets_native_output_utf8_before_json_parse(self):
        script = (ROOT / "scripts" / "collect_qidian_browser_ranks.ps1").read_text(encoding="utf-8")
        self.assertIn("[Console]::OutputEncoding = $utf8", script)
        self.assertIn("$OutputEncoding = $utf8", script)
        self.assertIn("chcp.com", script)
        self.assertLess(script.index("[Console]::OutputEncoding"), script.index("$raw = $rawText | ConvertFrom-Json"))

    def test_qidian_unloaded_page_retries_without_relaxing_contract(self):
        script = (ROOT / "scripts" / "collect_qidian_browser_ranks.ps1").read_text(encoding="utf-8")
        self.assertIn("for ($attempt = 1; $attempt -le 2; $attempt++)", script)
        self.assertIn("if ($raw.url.StartsWith($spec.Url) -and $raw.items.Count -ge 20)", script)
        self.assertIn("Qidian page contract failed", script)
        self.assertIn("throw \"Qidian page contract failed", script)

    def test_qidian_script_fixes_urls_selectors_and_minimum(self):
        text = (ROOT / "scripts" / "collect_qidian_browser_ranks.ps1").read_text(encoding="utf-8")
        for path in ("yuepiao", "hotsales", "readindex", "recom", "signNewBkAll"):
            self.assertIn(f"https://www.qidian.com/rank/{path}/", text)
        self.assertIn(".book-img-text li", text)
        self.assertIn("$raw.items.Count -lt 20", text)
        self.assertIn("opencli_chrome_bridge_fixed_urls_and_dom_contract", text)


if __name__ == "__main__":
    unittest.main()
