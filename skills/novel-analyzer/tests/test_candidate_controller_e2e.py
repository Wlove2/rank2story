from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import candidate_portfolio as portfolio
import candidate_workflow as workflow
import freeze_evidence_packet as freezer


SOURCES = [
    ("fanqie_writer_hot_stories", "fanqie_official_short", "fanqie"),
    ("fanqie_reader_short_rank_center", "fanqie_official_short", "fanqie"),
    ("qimao_reader_story_rank_center", "qimao_official_story", "qimao"),
    ("xiaohongshu_novel_demand_shared", "xiaohongshu_demand", "xiaohongshu"),
    ("bilibili_novel_demand_shared", "bilibili_demand", "bilibili"),
    ("qimao_reader_story_rank_center", "qimao_official_story", "qimao"),
    ("fanqie_writer_hot_stories", "fanqie_official_short", "fanqie"),
    ("xiaohongshu_novel_demand_shared", "xiaohongshu_demand", "xiaohongshu"),
]

LONG_SOURCES = [
    ("fanqie_public_web_ranks", "fanqie_official", "fanqie"),
    ("fanqie_reader_novel_rank_center", "fanqie_official", "fanqie"),
    ("qimao_public_web_ranks", "qimao_official", "qimao"),
    ("zongheng_public_rank_snapshot", "paid_platform_corroboration", "zongheng"),
    ("jjwxc_quarter_rank_snapshot", "paid_platform_corroboration", "jjwxc"),
    ("qidian_paid_trend_target", "paid_platform_corroboration", "qidian"),
    ("xiaohongshu_novel_demand_shared", "xiaohongshu_demand", "xiaohongshu"),
    ("bilibili_novel_demand_shared", "bilibili_demand", "bilibili"),
]

CLOSEST_WORKS = {
    "A-1": "《记忆大师》", "A-2": "《交换人生》", "A-3": "《消失的她》",
    "B-1": "《全民目击》", "B-2": "电视剧《开端》（2022）", "B-3": "《想见你》",
    "C-1": "《斗破苍穹》", "C-2": "《人民的名义》", "C-3": "《末日乐园》",
}
CLOSEST_WORKS.update({
    f"{branch}-C{index:02d}": CLOSEST_WORKS[f"{branch}-{index}"]
    for branch in "ABC" for index in range(1, 4)
})


class CandidateControllerEndToEndTests(unittest.TestCase):
    def packet(self, lane: str = "short") -> dict:
        sources = SOURCES if lane == "short" else LONG_SOURCES
        evidence = [
            {"evidence_id": f"ev-{index}", "source_item_id": f"item-{index}", "source_id": source_id}
            for index, (source_id, _, _) in enumerate(sources, 1)
        ]
        evidence.extend(
            {
                "evidence_id": f"work-ref-{candidate_id}",
                "source_item_id": f"closest-work-{candidate_id}",
                "source_id": "frozen_closest_work_registry",
                "work_identifier": title,
            }
            for candidate_id, title in CLOSEST_WORKS.items()
        )
        return freezer.freeze(
            {"lane": lane, "sources": []},
            {"formal_candidate_generation": "allowed", "lane": lane},
            evidence, {"selected_works": []},
        )

    def atoms(self, lane: str = "short") -> list[dict]:
        sources = SOURCES if lane == "short" else LONG_SOURCES
        atom_types = [
            "desire", "anxiety", "identity_fantasy", "conflict_mechanism",
            "payoff_mode", "opening_form", "activity_constraint", "anti_signal",
        ]
        return [
            {
                "atom_id": f"atom-{index}", "lane": lane, "atom_type": atom_type,
                "evidence_id": f"ev-{index}", "source_item_id": f"item-{index}",
                "source_id": source_id, "source_cohort": cohort, "platform": platform,
                "observation": f"Current evidence {index} shows a concrete reader or market behavior.",
                "inference": f"Story mechanism {index} can answer that signal with a specific causal payoff.",
                "confidence": 0.8, "freshness": "current_run", "claim_key": f"claim-{index}",
                "stance": "support", "supporting_evidence_ids": [f"ev-{index}"],
                "counter_evidence_ids": [], "contradicting_atom_ids": [], "generation_safe": True,
            }
            for index, ((source_id, cohort, platform), atom_type) in enumerate(zip(sources, atom_types), 1)
        ]

    def fingerprint(self, seed: str) -> dict[str, str]:
        fields = (
            "audience_desire", "protagonist_lack", "agency", "core_mechanism",
            "mechanism_cost", "opponent_interest", "escalation", "payoff_mode",
            "reaction_chain", "ending_reward", "opening_form", "short_closure",
        )
        mechanisms = {
            "A-1": "记忆质押交易", "A-2": "身份交换契约", "A-3": "婚姻债务清算",
            "B-1": "直播公开审判", "B-2": "任务系统规则", "B-3": "重生时间循环",
            "C-1": "能力拍卖市场", "C-2": "证据账本审计", "C-3": "末世生存资源交换",
        }
        mechanism = mechanisms[seed]
        result = {
            field: hashlib.sha256(f"{seed}:{field}".encode()).hexdigest()[:24]
            for field in fields
        }
        for field in portfolio.CAUSAL_DIMENSIONS:
            result[field] = f"{mechanism}的候选专属{field}"
        return result

    def candidate(
        self, profile: dict, context: dict, candidate_id: str, branch: str, seed: str, index: int,
    ) -> dict:
        atom_ids = context["input_atom_ids"][:2]
        candidate = {
            "kernel_id": f"{branch}-K{index}", "candidate_id": candidate_id,
            "generator_branch": branch, "cited_atom_ids": atom_ids,
            "structural_fingerprint": self.fingerprint(seed),
            "candidate_card": {
                "one_line_concept": f"{'女主' if profile['audience_channel'] == 'female' else '男主'}在公开追责中用旧账本反转权力并承担无法撤销的代价-{candidate_id}",
                "target_reader": f"{profile['audience_channel']} readers seeking a strong causal commercial hook",
                "target_platform": profile["target_platform"], "audience_channel": profile["audience_channel"],
                "portfolio_track": "general", "target_profile_hash": profile["output_hash"],
                "opening_300_beats": [
                    "visible pressure reaches the protagonist",
                    "she chooses a costly response",
                    "the irreversible action changes the relationship",
                ],
                "reward_cycle": [
                    "pressure exposes the lack", "the protagonist makes a choice",
                    "the action cannot be reversed", "the result changes power",
                    "other people react materially", "a new cost creates the next desire",
                ],
                "three_payoffs": [
                    "the opening promise pays through action",
                    "the relationship debt becomes visible",
                    "the ending resolves the central causal question",
                ],
                "short_closure": "the main conflict closes and the remaining relationship cost is shown",
                "closest_work": CLOSEST_WORKS[candidate_id],
                "causal_difference": f"material-causal-difference-{candidate_id}",
                "evidence_atom_ids": atom_ids,
                "risks": "the mechanism can repeat unless each scene changes the relationship cost",
                "activity_route": "not_applicable",
            },
        }
        if profile["lane"] == "long":
            candidate["structural_fingerprint"].update({
                "relationship_engine": f"{seed}关系债务随每次选择累积",
                "world_expansion": f"{seed}机制从家族扩展到行业规则",
                "stage_engine": f"{seed}按三阶段改变权力和代价",
            })
            candidate["candidate_card"]["long_run_stages"] = {
                stage: {
                    "goal": f"{stage}阶段完成候选{seed}的明确目标",
                    "relationship_change": f"{stage}阶段核心关系产生不可逆变化",
                    "world_expansion": f"{stage}阶段规则扩展到新的社会层级",
                    "irreversible_change": f"{stage}阶段主角付出无法撤销的实际代价",
                    "stage_payoff": f"{stage}阶段兑现此前建立的读者承诺",
                }
                for stage in ("300k", "800k", "1500k")
            }
        return candidate

    def write_raw(self, action: dict, payload) -> Path:
        path = Path(action["raw_output"])
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(payload, str):
            path.write_text(payload, encoding="utf-8")
        else:
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def run_case(self, lane: str, platform_name: str, channel: str) -> dict:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            packet_path = root / "packet.json"
            packet_path.write_text(json.dumps(self.packet(lane), ensure_ascii=False), encoding="utf-8")
            result = workflow.init_run(root, packet_path, lane, platform_name, channel)
            atom_action = result["actions"][0]
            result = workflow.ingest_job(
                Path(result["claim"]), atom_action["job_id"], "deleg_e2e:atoms",
                self.write_raw(atom_action, self.atoms(lane)),
            )
            claim_path = Path(result["claim"])
            _, profile, _, output_dir, _ = workflow.validate_claim(claim_path)
            contexts = workflow.load_json(output_dir / "generation_contexts.json")["contexts"]
            for action in list(result["actions"]):
                branch = action["role"][-1]
                kernels = [
                    {
                        "kernel_id": f"{branch}-K{index}",
                        "mechanism_signature": f"{branch} mechanism {index} with unique cost",
                        "hook": f"visible opening pressure {branch} {index}",
                        "protagonist_situation": f"specific protagonist situation {branch} {index}",
                        "protagonist_desire": f"specific protagonist desire {branch} {index}",
                        "core_mechanism": f"choice and irreversible cost mechanism {branch} {index}",
                        "primary_resistance": f"specific opposing interest {branch} {index}",
                        "reader_payoff": f"specific repeatable payoff {branch} {index}",
                        "cited_atom_ids": contexts[branch]["input_atom_ids"][:2],
                    }
                    for index in range(1, 4)
                ]
                result = workflow.ingest_job(
                    claim_path, action["job_id"], f"deleg_e2e:{branch}",
                    self.write_raw(action, {"branch_id": branch, "concept_kernels": kernels}),
                )

            seen_story_actions = 0
            while {row["role"] for row in result["actions"]} != {"market_coverage", "originality_craft"}:
                actions = list(result["actions"])
                self.assertTrue(actions, result)
                self.assertLessEqual(len(actions), 3)
                for action in actions:
                    role = action["role"]
                    if role == "story_creator":
                        seen_story_actions += 1
                        payload = (
                            f"故事 {action['candidate_id']}：主角面对明确压力，因自身利益作出不可撤销的选择。"
                            "这个选择改变关系并触发阻力；机制保持一致，转折由前一步行动导致，"
                            "结局用人物行动完成本篇中心冲突，没有依赖临时出现的新设定。"
                        )
                    elif role == "story_editor":
                        payload = "通过"
                    elif role == "candidate_mapper":
                        branch = action["branch_id"]
                        index = int(action["candidate_id"].split("C")[-1])
                        payload = {"candidate": self.candidate(
                            profile, contexts[branch], action["candidate_id"],
                            branch, f"{branch}-{index}", index,
                        )}
                    else:
                        self.fail(f"unexpected story-first action: {role}")
                    result = workflow.ingest_job(
                        claim_path, action["job_id"], f"deleg_e2e:{role}:{action.get('candidate_id', '')}",
                        self.write_raw(action, payload),
                    )
            self.assertEqual(seen_story_actions, 9)
            self.assertEqual(
                {row["role"] for row in result["actions"]},
                {"market_coverage", "originality_craft"},
                result,
            )
            clustered = workflow.load_json(Path(workflow.load_json(output_dir / "controller_state.json")["artifacts"]["clustered"]))
            representatives = clustered["representatives"]
            objectives = [
                [5, 2, 3, 5, 3], [4, 3, 4, 4, 2], [3, 5, 3, 3, 1],
                [4, 4, 5, 2, 3], [2, 5, 4, 5, 2], [5, 3, 2, 4, 1],
                [3, 4, 5, 3, 2], [4, 2, 4, 5, 3], [5, 4, 3, 2, 2],
            ]
            market_records = {}
            originality_records = {}
            for index, candidate in enumerate(representatives):
                candidate_id = candidate["candidate_id"]
                vector = objectives[index % len(objectives)]
                checks = {
                    "entry_promise": True, "reward_cycle": True, "platform_fit": True,
                    "activity_fit": True,
                }
                if lane == "short":
                    checks["short_closure"] = True
                else:
                    checks["three_stage_engine"] = True
                market_record = {
                    "status": "passed",
                    "checks": checks,
                    "entry_promise": "the first scene states pressure and an irreversible choice",
                    "reward_cycle": [
                        "pressure exposes the lack", "the protagonist makes a choice",
                        "the action cannot be reversed", "the result changes power",
                        "other people react materially", "a new cost creates the next desire",
                    ],
                    "platform_fit": f"the concept fits the selected {platform_name} profile",
                    "channel_fit": f"the desire and relationship feedback fit the {channel} channel",
                    "channel_verdict": "fit",
                    "protagonist_perspective": channel,
                    "activity_fit": "not_applicable",
                    "causal_consistency": "the premise, payoffs, and ending preserve one causal answer",
                    "contradictions": [],
                    "calibrated_objectives": dict(zip(portfolio.OBJECTIVES, vector)),
                    "objective_rationales": {
                        key: f"candidate-specific rationale for {key} on {candidate_id}"
                        for key in portfolio.OBJECTIVES
                    },
                }
                if lane == "short":
                    market_record["complexity_budget"] = {
                        "mechanism_count": 2,
                        "assessment": "two mechanisms fit the short form",
                    }
                else:
                    market_record["three_stage_engine"] = {
                        stage: {
                            "goal": f"candidate {candidate_id} pursues a distinct institutional goal at {stage}",
                            "irreversible_change": f"candidate {candidate_id} loses a concrete alliance at {stage}",
                            "relationship_change": f"candidate {candidate_id} turns a creditor into an opponent at {stage}",
                            "stage_payoff": f"candidate {candidate_id} cashes the promised audit reversal at {stage}",
                            "world_expansion": f"candidate {candidate_id} expands from a family debt to an industry rule at {stage}",
                        }
                        for stage in ("300k", "800k", "1500k")
                    }
                market_records[candidate_id] = market_record
                originality_records[candidate_id] = {
                    "layers": {
                        name: {"status": "passed", "high_recognition_collision": False}
                        for name in ("expression", "semantic", "structural", "causal")
                    },
                    "closest_work": CLOSEST_WORKS[candidate_id],
                    "causal_difference": f"material-causal-difference-{candidate_id}",
                    "closest_work_reference": {
                        "identifier": CLOSEST_WORKS[candidate_id],
                        "evidence_id": f"work-ref-{candidate_id}",
                    },
                    "evidence_methods": ["local_history", "direct_result_urls", "structural_fingerprint"],
                    "calibrated_originality_risk": vector[-1],
                    "originality_risk_rationale": f"four-layer independent rationale for {candidate_id}",
                }
            for action in list(result["actions"]):
                payload = {"candidates": market_records if action["role"] == "market_coverage" else originality_records}
                result = workflow.ingest_job(
                    claim_path, action["job_id"], f"deleg_e2e:{action['role']}",
                    self.write_raw(action, payload),
                )
            self.assertEqual(result["status"], "awaiting_user_choice", result)
            self.assertGreaterEqual(result["candidate_count"], 4)
            verified = workflow.verify_delivery(claim_path)
            self.assertEqual(verified["status"], "passed")
            self.assertEqual(verified["generated_count"], 9)
            self.assertGreaterEqual(verified["passed_review_count"], 4)
            self.assertEqual(verified["selected_for_delivery_count"], result["candidate_count"])
            self.assertEqual(verified["usable_candidate_count"], result["candidate_count"])
            return verified

    def test_pairwise_short_long_platform_channel_matrix(self):
        cases = (
            ("short", "fanqie", "female"),
            ("short", "qimao", "male"),
            ("long", "fanqie", "male"),
            ("long", "qimao", "female"),
        )
        for lane, platform_name, channel in cases:
            with self.subTest(lane=lane, platform=platform_name, channel=channel):
                verified = self.run_case(lane, platform_name, channel)
                self.assertEqual(verified["status"], "passed")


if __name__ == "__main__":
    unittest.main()
