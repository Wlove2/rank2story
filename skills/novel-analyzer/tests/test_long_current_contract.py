import importlib.util
import tempfile
import sys
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).parents[1]


def load(name):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CURRENT = load("long_source_refresh")
QIMAO_WEB = load("collect_qimao_web_ranks")


class FreshnessContractTests(unittest.TestCase):
    def test_current_run_is_not_a_fourteen_day_reuse_window(self):
        self.assertEqual(CURRENT.tier(0), "current_run")
        self.assertEqual(CURRENT.tier(1), "historical_only")
        self.assertEqual(CURRENT.tier(14), "historical_only")

    def test_qimao_snapshot_must_belong_to_current_run(self):
        fixture = ROOT / "tests" / "fixtures" / "qimao_full.json"
        summary, entries = CURRENT.inspect_qimao(fixture, date(2026, 7, 16))
        self.assertEqual(summary["status"], "success")
        self.assertEqual(summary["current_tier"], "current_run")
        self.assertEqual(summary["max_age_days"], 0)
        self.assertEqual(len(entries), 10)
        stale, _ = CURRENT.inspect_qimao(fixture, date(2026, 7, 17))
        self.assertEqual(stale["status"], "stale")


class QimaoWebParserTests(unittest.TestCase):
    def test_parses_rank_item(self):
        sample = """
        <ul class="rank-list"><li class="rank-list-item">
          <a href="https://www.qimao.com/shuku/123/"><span class="rank-number first">1</span></a>
          <a class="s-book-title">测试书</a>
          <span class="s-book-info"><a>作者甲</a><a>都市</a><a>职业</a><em>连载中</em><em>88万字</em></span>
          <span class="s-book-update"><em>2026-07-17 01:02:03</em></span>
          <em class="rank-num">9.8</em><em class="rank-unit">万</em>
        </li></ul>
        """
        rows = QIMAO_WEB.parse_page(
            sample,
            gender="male",
            rank_type="hot",
            source_url="https://www.qimao.com/paihang/boy/hot/date/",
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "测试书")
        self.assertEqual(rows[0]["rank"], 1)
        self.assertEqual(rows[0]["author"], "作者甲")
        self.assertEqual(rows[0]["heat"], "9.8万")


    def test_parses_current_generic_links_and_embedded_state(self):
        quote = chr(34)
        generic = f'<section><span class={quote}rank-current{quote}>1</span><a href={quote}/shuku/456/{quote}>Book Alpha</a></section>'
        rows = QIMAO_WEB.parse_page(generic, gender='male', rank_type='hot', source_url='https://www.qimao.com/rank')
        self.assertEqual(rows[0]['book_id'], '456')
        self.assertEqual(rows[0]['title'], 'Book Alpha')
        embedded = f'<script>{{book_id:{quote}789{quote},title:{quote}Book Beta{quote},author:{quote}Author B{quote}}}</script>'
        rows = QIMAO_WEB.parse_page(embedded, gender='female', rank_type='new', source_url='https://www.qimao.com/rank')
        self.assertEqual(rows[0]['book_id'], '789')
        self.assertEqual(rows[0]['author'], 'Author B')

    def test_browser_snapshots_require_all_ten_channels(self):
        quote = chr(34)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            snapshots = root / 'snapshots'
            output = root / 'output'
            snapshots.mkdir()
            index = 0
            for gender in ('male', 'female'):
                for rank_type in QIMAO_WEB.CHANNELS:
                    index += 1
                    body = f'<a href={quote}/shuku/{index}/{quote}>Book {index}</a>'
                    (snapshots / f'{gender}_{rank_type}.html').write_text(body, encoding='utf-8')
            manifest = QIMAO_WEB.collect_snapshots(output, snapshots)
            self.assertEqual(manifest['status'], 'success')
            self.assertEqual(manifest['successful_channel_count'], 10)
            (snapshots / 'female_updates.html').unlink()
            blocked = QIMAO_WEB.collect_snapshots(root / 'blocked', snapshots)
            self.assertEqual(blocked['status'], 'degraded')


if __name__ == "__main__":
    unittest.main()
