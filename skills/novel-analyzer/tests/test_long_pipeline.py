import importlib.util
import sys
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).parents[1]
FIXTURES = Path(__file__).parent / "fixtures"


def load_module(name):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


SOURCE = load_module("long_source_refresh")
MARKET = load_module("long_market_scan")
CANDIDATE = load_module("long_candidate_batch")
FANQIE = load_module("fanqie_refresh")


def verification(status="passed"):
    result = {field: {"status": status} for field in CANDIDATE.VERIFICATION_FIELDS}
    for field in ("title_search", "concept_search"):
        result[field].update({
            "provider": "test-search", "checked_at": "2026-07-18T00:00:00Z",
            "reviewed_urls": ["https://example.test/result"],
        })
    return result


def valid_candidate(number=1):
    candidate = {field: f"{field}-{number}" for field in CANDIDATE.REQUIRED_TEXT}
    candidate.update({
        "id": f"L-{number:04d}", "title": f"原创候选{number}",
        "long_run_stages": {"300k": "城内闭环", "800k": "区域联盟", "1500k": "世界秩序"},
        "market_evidence": [
            {"platform": "fanqie", "title": "样本甲", "current": True},
            {"platform": "qimao", "title": "样本乙", "current": True},
        ],
        "verification": verification(),
        "risks": {"direct_ip": False, "sensitive_level": 1},
        "scores": {field: 4 for field in CANDIDATE.WEIGHTS},
        "score_rationales": {field: f"fixture rationale {field}" for field in CANDIDATE.WEIGHTS},
    })
    return candidate


class FanqieCollectorTests(unittest.TestCase):
    def test_default_and_regression_limits(self):
        self.assertEqual(FANQIE.load_config(None, False)["books_per_category"], 10)
        self.assertEqual(FANQIE.load_config(None, True)["books_per_category"], 6)

    def test_state_without_matching_result_is_not_skipped(self):
        completed, rows = FANQIE.reconcile_resume({"completed": ["都市"]}, {"categories": []})
        self.assertEqual(completed, set())
        self.assertEqual(rows, [])

    def test_empty_category_is_not_success(self):
        self.assertEqual(FANQIE.category_record("空榜", [])["status"], "empty")


class SourceAdapterTests(unittest.TestCase):
    def test_qimao_requires_every_gender_rank_channel(self):
        summary, normalized = SOURCE.inspect_qimao(FIXTURES / "qimao_full.json", date(2026, 7, 16))
        self.assertEqual(summary["status"], "success")
        self.assertEqual(len(normalized), 10)
        summary, _ = SOURCE.inspect_qimao(FIXTURES / "qimao_missing.json", date(2026, 7, 16))
        self.assertEqual(summary["status"], "degraded")
        self.assertEqual(len(summary["missing_channels"]), 1)

    def test_seven_day_fanqie_snapshot_is_historical_not_current(self):
        summary, _ = SOURCE.inspect_fanqie(FIXTURES / "fanqie", date(2026, 7, 16))
        self.assertEqual(summary["status"], "stale")
        self.assertEqual(summary["age_days"], 7)
        self.assertEqual(summary["current_tier"], "historical_only")
        self.assertEqual(summary["max_age_days"], 0)


class MarketTests(unittest.TestCase):
    def test_single_batch_never_claims_rising(self):
        matrix = MARKET.build_matrix([("20260716", [{
            "platform": "fanqie", "gender": "male", "rank_type": "new_ranks",
            "category": "都市", "rank": 1, "title": "开局觉醒系统", "source_file": "fixture.json",
        }])])
        self.assertTrue(matrix["signals"])
        self.assertTrue(all(item["trend"] == "insufficient_history" for item in matrix["signals"]))

    def test_rank_percentile_is_cohort_local(self):
        rows = MARKET.normalized_entries([
            {"platform": "fanqie", "gender": "male", "rank_type": "new", "category": "都市", "rank": 1},
            {"platform": "fanqie", "gender": "male", "rank_type": "new", "category": "都市", "rank": 2},
        ])
        self.assertEqual([row["platform_percentile"] for row in rows], [1.0, 0.0])

    def test_zongheng_and_jjwxc_are_paid_cohorts(self):
        rows = MARKET.normalized_entries([
            {"platform": "zongheng", "rank_type": "monthly_ticket", "rank": 1},
            {"platform": "jjwxc", "rank_type": "quarter", "rank": 1},
        ])
        self.assertTrue(all(row["cohort"]["commercial_model"] == "paid" for row in rows))


class CandidateTests(unittest.TestCase):
    def test_valid_batch_uses_structural_clusters_and_pareto_cap(self):
        candidates = []
        tradeoffs = ([5, 1, 1, 5, 5], [4, 2, 2, 4, 4], [3, 3, 3, 3, 3], [2, 4, 4, 2, 2], [1, 5, 5, 1, 1])
        seeds = ["inheritance", "memory", "courtroom", "epidemic", "artfraud", "deepsea", "eldercare", "satellite"]
        for index, seed in enumerate(seeds, 1):
            candidate = valid_candidate(index)
            candidate["structural_fingerprint"] = {
                key: f"{seed}-{position}"
                for position, key in enumerate(CANDIDATE.portfolio.FINGERPRINT_CORE + CANDIDATE.portfolio.FINGERPRINT_EXTRAS["long"])
            }
            candidate["portfolio_objectives"] = dict(zip(CANDIDATE.portfolio.OBJECTIVES, tradeoffs[(index - 1) % len(tradeoffs)]))
            candidates.append(candidate)
        evaluated, rejected, selected = CANDIDATE.evaluate(candidates, True)
        self.assertEqual(len(evaluated), 8)
        self.assertEqual(rejected, [])
        self.assertEqual(len(selected), 6)
        self.assertTrue(all(item["decision"] == "pareto_market_candidate" for item in selected))

    def test_not_run_verification_is_hard_rejection(self):
        candidate = valid_candidate()
        candidate["verification"]["concept_search"] = {"status": "not_run"}
        _, rejected, selected = CANDIDATE.evaluate([candidate], True)
        self.assertEqual(selected, [])
        self.assertIn("CONCEPT_SEARCH_NOT_RUN", rejected[0]["gate_reasons"])

    def test_single_platform_and_short_twist_are_rejected(self):
        candidate = valid_candidate()
        candidate["market_evidence"] = candidate["market_evidence"][:1]
        candidate["risks"]["short_twist_only"] = True
        _, rejected, _ = CANDIDATE.evaluate([candidate], True)
        self.assertIn("SINGLE_BOOK_OR_PLATFORM_EVIDENCE", rejected[0]["gate_reasons"])
        self.assertIn("SHORT_TWIST_ONLY", rejected[0]["gate_reasons"])

    def test_current_source_gate_rejects_everything(self):
        _, rejected, selected = CANDIDATE.evaluate([valid_candidate()], False)
        self.assertEqual(selected, [])
        self.assertIn("CURRENT_SOURCE_GATE_NOT_ALLOWED", rejected[0]["gate_reasons"])


if __name__ == "__main__":
    unittest.main()
