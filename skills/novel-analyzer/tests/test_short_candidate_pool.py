import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "short_candidate_pool.py"
SPEC = importlib.util.spec_from_file_location("short_candidate_pool", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def valid_concept(title="原创概念"):
    return {
        "title": title,
        "audience_bucket": "general",
        "genre_bucket": "现实反转",
        "emotion_bucket": "治愈",
        "platform_targets": ["番茄短故事"],
        "premise": "主角在一次公开选择中完成反转并承担结果",
        "promise_300": "开篇即给出必须在今晚完成的选择",
        "desire": "保住家人的信任",
        "setup": "旧误会被公开",
        "risk": "家庭关系破裂",
        "obstacle": "证据被对手控制",
        "payoff": "主角用现场行动揭示真相",
        "aftermath": {
            "opponent_reaction": "对手当场失去支持",
            "relationship_or_cost": "家人道歉但信任需重建",
            "protagonist_choice": "主角拒绝轻易和解",
            "next_state": "主角获得新的独立生活",
        },
        "scene_chain": ["开场", "升级", "受阻", "兑现", "后效"],
        "craft": {
            "concrete_anchors": ["离婚协议第七页", "走廊摄像头", "带裂纹的录音笔"],
            "opening_action": "主角当众撕下协议第七页并要求核对时间戳",
            "irreversible_choice": "主角把唯一原件交给第三方公证，放弃私下和解",
            "antagonist_self_interest": "对手必须销毁证据才能保住职位和财产",
            "observable_payoff_actions": ["公证员投屏时间戳", "对手被迫交出门禁记录"],
            "reaction_parties": ["家人撤回指控", "同事公开改口"],
            "micro_hook_questions": ["第七页是谁替换的？", "录音笔为什么有裂纹？"],
            "rough_edge": "主角赢下证据却仍拒绝马上原谅家人",
        },
        "market_evidence": [
            {
                "kind": "official_activity",
                "manifest_id": "direction-1",
                "source": "https://example.test/activity",
                "date": "2026-07-16",
                "current": True,
                "content_status": "complete",
            },
            {
                "kind": "social_post",
                "manifest_id": "demand-1",
                "source": "https://example.test/reader-demand",
                "date": "2026-07-16",
                "current": True,
                "content_status": "complete",
            },
        ],
        "verification": {"title_status": "passed", "concept_status": "passed", "ip_status": "passed", "safety_status": "passed"},
        "scores": {name: 4 for name in MODULE.WEIGHTS},
        "risks": {"direct_ip": False, "unauthorized_ip": False, "sensitive_risk": 1, "hotspot_stacking": False},
    }


class CandidatePoolTests(unittest.TestCase):
    def test_valid_concept_enters_ready(self):
        pool = MODULE.empty_pool()
        [candidate] = MODULE.ingest(pool, [valid_concept()])
        self.assertEqual(candidate["status"], "ready")
        self.assertGreaterEqual(candidate["score"], 70)

    def test_activity_only_is_provisional(self):
        pool = MODULE.empty_pool()
        concept = valid_concept("只有活动页")
        concept["market_evidence"] = concept["market_evidence"][:1]
        [candidate] = MODULE.ingest(pool, [concept])
        self.assertEqual(candidate["status"], "provisional")
        self.assertIn("MISSING_INDEPENDENT_DEMAND", candidate["gate_reasons"])

    def test_background_and_rules_do_not_count_as_market_ready(self):
        pool = MODULE.empty_pool()
        concept = valid_concept("只有背景榜和规则")
        concept["market_evidence"] = [
            {
                "kind": "long_rank_background",
                "source": "https://example.test/long-rank",
                "date": "2026-07-16",
                "current": True,
                "content_status": "complete",
            },
            {
                "kind": "official_rule",
                "source": "https://example.test/rule",
                "date": "2026-07-16",
                "current": True,
                "content_status": "complete",
            },
        ]
        [candidate] = MODULE.ingest(pool, [concept])
        self.assertEqual(candidate["status"], "provisional")
        self.assertIn("MISSING_CURRENT_SHORT_DIRECTION", candidate["gate_reasons"])
        self.assertIn("MISSING_INDEPENDENT_DEMAND", candidate["gate_reasons"])

    def test_direction_and_demand_must_be_independent_sources(self):
        pool = MODULE.empty_pool()
        concept = valid_concept("同一来源重复记账")
        concept["market_evidence"][1]["source"] = concept["market_evidence"][0]["source"]
        [candidate] = MODULE.ingest(pool, [concept])
        self.assertEqual(candidate["status"], "provisional")
        self.assertIn("MISSING_EVIDENCE_DIVERSITY", candidate["gate_reasons"])

    def test_revalidate_downgrades_ready_when_demand_disappears(self):
        pool = MODULE.empty_pool()
        MODULE.ingest(pool, [valid_concept()])
        pool["candidates"][0]["market_evidence"] = pool["candidates"][0]["market_evidence"][:1]
        changed = MODULE.revalidate(pool)
        self.assertEqual([item["id"] for item in changed], ["S-0001"])
        self.assertEqual(pool["candidates"][0]["status"], "provisional")

    def test_direct_known_ip_is_rejected(self):
        pool = MODULE.empty_pool()
        concept = valid_concept("我的室友是张起灵")
        concept["risks"]["direct_ip"] = True
        [candidate] = MODULE.ingest(pool, [concept])
        self.assertEqual(candidate["status"], "rejected")
        self.assertIn("DIRECT_IP", candidate["gate_reasons"])

    def test_weak_closure_and_aftermath_are_rejected(self):
        pool = MODULE.empty_pool()
        concept = valid_concept("只有热点没有结局")
        concept["scores"]["closure"] = 2
        concept["aftermath"]["next_state"] = ""
        [candidate] = MODULE.ingest(pool, [concept])
        self.assertIn("WEAK_CLOSURE", candidate["gate_reasons"])
        self.assertIn("MISSING_AFTERMATH", candidate["gate_reasons"])

    def test_unverified_candidate_cannot_enter_ready(self):
        pool = MODULE.empty_pool()
        concept = valid_concept("尚未查重")
        concept["verification"]["title_status"] = "not_run"
        [candidate] = MODULE.ingest(pool, [concept])
        self.assertEqual(candidate["status"], "rejected")
        self.assertIn("VERIFICATION_NOT_RUN", candidate["gate_reasons"])

    def test_ready_can_be_rejected_after_late_collision(self):
        pool = MODULE.empty_pool()
        MODULE.ingest(pool, [valid_concept()])
        candidate = MODULE.transition(pool, "S-0001", "rejected", "late title collision", None)
        self.assertEqual(candidate["status"], "rejected")

    def test_inventory_replenishes_after_selection(self):
        pool = MODULE.empty_pool()
        concepts = []
        seeds = ["inheritance", "memory", "courtroom", "epidemic", "artfraud", "deepsea", "eldercare", "satellite"]
        for i, seed in enumerate(seeds):
            concept = valid_concept(f"candidate-{i}")
            concept["structural_fingerprint"] = {
                key: f"{seed}-{position}"
                for position, key in enumerate(MODULE.portfolio.FINGERPRINT_CORE + MODULE.portfolio.FINGERPRINT_EXTRAS["short"])
            }
            concepts.append(concept)
        MODULE.ingest(pool, concepts)
        self.assertFalse(MODULE.summarize(pool)["replenish_needed"])
        MODULE.transition(pool, "S-0001", "selected", "用户选择", None)
        summary = MODULE.summarize(pool)
        self.assertTrue(summary["replenish_needed"])
        self.assertEqual(summary["replenish_gap"], 3)

    def test_failed_requires_reason(self):
        pool = MODULE.empty_pool()
        MODULE.ingest(pool, [valid_concept()])
        MODULE.transition(pool, "S-0001", "selected", "用户选择", None)
        MODULE.transition(pool, "S-0001", "written", "已成稿", None)
        MODULE.transition(pool, "S-0001", "submitted", "投稿", "番茄")
        with self.assertRaisesRegex(ValueError, "reason is required"):
            MODULE.transition(pool, "S-0001", "failed", "", "番茄")

    def test_official_platform_short_without_word_count_is_valid_demand(self):
        pool = MODULE.empty_pool()
        concept = valid_concept("七猫官方故事无需字数门")
        concept["market_evidence"][1] = {
            "kind": "short_rank", "manifest_id": "qimao-story",
            "evidence_id": "qimao-1", "source_item_id": "1",
            "source": "https://example.test/qimao", "date": "2026-07-16",
            "current": True, "content_status": "complete",
            "platform_format": "official_short",
            "lane_classification": "short",
            "classification_basis": "official_platform_surface",
        }
        [candidate] = MODULE.ingest(pool, [concept])
        self.assertEqual(candidate["status"], "ready")
        self.assertNotIn("MISSING_VERIFIED_TARGET_REFERENCE", candidate["gate_reasons"])

    def test_missing_craft_anchors_is_rejected_and_score_is_capped(self):
        pool = MODULE.empty_pool()
        concept = valid_concept("没有具体锚点")
        concept["craft"]["concrete_anchors"] = []
        [candidate] = MODULE.ingest(pool, [concept])
        self.assertEqual(candidate["status"], "rejected")
        self.assertIn("MISSING_CONCRETE_ANCHORS", candidate["gate_reasons"])
        self.assertEqual(candidate["score_audit"]["caps"]["core_promise"], 2)

    def test_generic_ai_scaffold_is_rejected(self):
        pool = MODULE.empty_pool()
        concept = valid_concept("通用骨架")
        concept["payoff"] = "主角以行动完成核心承诺并改变公开结果"
        concept["scene_chain"][0] = "异常规则与人物关系同时落地"
        [candidate] = MODULE.ingest(pool, [concept])
        self.assertEqual(candidate["status"], "rejected")
        self.assertIn("GENERIC_AI_SCAFFOLD", candidate["gate_reasons"])

    def test_intra_batch_duplicate_scaffold_rejects_later_candidate(self):
        pool = MODULE.empty_pool()
        first = valid_concept("骨架甲")
        second = valid_concept("骨架乙")
        added = MODULE.ingest(pool, [first, second])
        self.assertEqual(added[0]["status"], "ready")
        self.assertEqual(added[1]["status"], "rejected")
        self.assertIn("DUPLICATE_CONCEPT_SCAFFOLD", added[1]["gate_reasons"])


if __name__ == "__main__":
    unittest.main()
