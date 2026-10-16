from __future__ import annotations

import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def load(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


FREEZE = load("freeze_evidence_packet")
PORTFOLIO = load("candidate_portfolio")


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


class CandidatePortfolioTests(unittest.TestCase):
    def setUp(self) -> None:
        evidence = [
            {
                "evidence_id": f"ev-{index}",
                "source_item_id": f"item-{index}",
                "source_id": source_id,
            }
            for index, (source_id, _, _) in enumerate(SOURCES, 1)
        ]
        self.packet = FREEZE.freeze(
            {"lane": "short", "sources": []},
            {"formal_candidate_generation": "allowed", "lane": "short"},
            evidence,
            {"selected_works": []},
        )
        atom_types = [
            "desire", "anxiety", "identity_fantasy", "conflict_mechanism",
            "payoff_mode", "opening_form", "activity_constraint", "anti_signal",
        ]
        atoms = []
        for index, ((source_id, cohort, platform), atom_type) in enumerate(zip(SOURCES, atom_types), 1):
            atoms.append({
                "atom_id": f"atom-{index}",
                "lane": "short",
                "atom_type": atom_type,
                "evidence_id": f"ev-{index}",
                "source_item_id": f"item-{index}",
                "source_id": source_id,
                "source_cohort": cohort,
                "platform": platform,
                "observation": f"Observed current signal {index} without copying a title.",
                "inference": f"Abstract reader implication {index}.",
                "confidence": 0.75,
                "freshness": "current_run",
                "claim_key": f"claim-{index}",
                "stance": "support",
                "supporting_evidence_ids": [f"ev-{index}"],
                "counter_evidence_ids": [],
                "contradicting_atom_ids": [],
                "generation_safe": True,
            })
        self.atoms = PORTFOLIO.seal({
            "stage": "evidence_atoms",
            "schema_version": PORTFOLIO.SCHEMA_VERSION,
            "lane": "short",
            "run_id": "run-1",
            "input_hash": self.packet["evidence_packet_hash"],
            "evidence_packet_hash": self.packet["evidence_packet_hash"],
            "recovery_status": "atoms_ready",
            "atoms": atoms,
        })
        self.profile = PORTFOLIO.make_profile("short", "general", "fanqie", "female")
        self.contexts = PORTFOLIO.build_contexts(self.packet, self.atoms, self.profile, "short", "run-1")

    def fingerprint(self, seed: str) -> dict[str, str]:
        mechanisms = {
            "reskin": "记忆质押交易",
            "same-cause": "记忆抵押换取生存资源",
            "alpha": "真假千金身份交换",
            "beta": "婚姻契约债务清算",
            "gamma": "直播公开审判",
            "theta": "任务系统规则反噬",
            "delta": "重生时间循环",
            "epsilon": "能力拍卖交易市场",
            "zeta": "末世生存资源交换",
            "shape": "公开审判证据账本",
            "semantic": "身份契约交易",
        }
        mechanism = mechanisms.get(seed, f"机制-{seed}")
        result = {
            "audience_desire": f"desire-{seed}",
            "protagonist_lack": f"lack-{seed}",
            "agency": f"主角主动启动{mechanism}",
            "core_mechanism": mechanism,
            "mechanism_cost": f"{mechanism}每次使用都会增加代价",
            "opponent_interest": f"对手试图垄断{mechanism}",
            "escalation": f"{mechanism}从私人冲突升级为公开规则",
            "payoff_mode": f"通过{mechanism}兑现因果回报",
            "reaction_chain": f"reaction-{seed}",
            "ending_reward": f"主角承担{mechanism}最终代价后完成闭环",
            "opening_form": f"opening-{seed}",
            "short_closure": f"closure-{seed}",
        }
        return result

    def candidate(self, candidate_id: str, branch_id: str, seed: str, objectives: list[int]) -> dict:
        atom_ids = self.contexts["contexts"][branch_id]["input_atom_ids"][:2]
        closest = f"audited-work-{candidate_id}"
        difference = f"material-causal-difference-{candidate_id}"
        kernel_id = f"{candidate_id}-K"
        story = f"完整故事正文 {candidate_id}：人物依照已知利益作出选择，机制前后一致，转折由行动导致，结局完成中心冲突。"
        story_hash = PORTFOLIO.canonical_hash(story)
        review = PORTFOLIO.seal({
            "stage": "story_review", "schema_version": PORTFOLIO.SCHEMA_VERSION,
            "lane": "short", "run_id": "run-1", "candidate_id": candidate_id,
            "kernel_id": kernel_id, "story_hash": story_hash, "status": "passed",
            "review_text": "通过", "reviewer_does_not_complete_story": True,
        })
        return {
            "candidate_id": candidate_id,
            "kernel_id": kernel_id,
            "generator_branch": branch_id,
            "story_proposal": story,
            "story_review": review,
            "story_trace": {
                "candidate_id": candidate_id, "kernel_id": kernel_id,
                "story_hash": story_hash, "review_hash": review["output_hash"],
                "mapping_input_hash": PORTFOLIO.canonical_hash({
                    "candidate_id": candidate_id, "kernel_id": kernel_id,
                    "story_hash": story_hash, "review_hash": review["output_hash"],
                }),
            },
            "cited_atom_ids": atom_ids,
            "structural_fingerprint": self.fingerprint(seed),
            "portfolio_objectives": dict(zip(PORTFOLIO.OBJECTIVES, objectives)),
            "candidate_card": {
                "one_line_concept": f"\u5973\u4e3b\u5728\u516c\u5f00\u5ba1\u5224\u4e2d\u7528\u4e00\u4efd\u65e7\u8d26\u672c\u53cd\u8f6c\u547d\u8fd0\u5e76\u627f\u62c5\u771f\u5b9e\u4ee3\u4ef7-{candidate_id}",
                "target_reader": "female readers seeking a causal commercial hook",
                "target_platform": "fanqie",
                "audience_channel": "female",
                "portfolio_track": "general",
                "target_profile_hash": self.profile["output_hash"],
                "opening_300_beats": ["visible pressure arrives", "protagonist chooses a costly response", "irreversible action changes the relationship"],
                "reward_cycle": ["pressure exposes the lack", "protagonist makes a choice", "action cannot be reversed", "visible result changes power", "other people react materially", "new cost creates the next desire"],
                "three_payoffs": ["first promise pays through action", "relationship debt becomes visible", "ending resolves the central causal question"],
                "short_closure": "the main conflict closes and the surviving relationship cost is shown",
                "closest_work": closest,
                "causal_difference": difference,
                "evidence_atom_ids": atom_ids,
                "risks": "the mechanism may become repetitive unless each scene changes the relationship cost",
                "activity_route": "not_applicable",
            },
        }

    def branch(self, branch_id: str, candidates: list[dict]) -> dict:
        context = self.contexts["contexts"][branch_id]
        return PORTFOLIO.seal({
            "stage": "divergent_generation",
            "schema_version": PORTFOLIO.SCHEMA_VERSION,
            "lane": "short",
            "run_id": "run-1",
            "branch_id": branch_id,
            "generator_role": PORTFOLIO.BRANCH_ROLES[branch_id],
            "context_hash": context["output_hash"],
            "input_atom_ids": context["input_atom_ids"],
            "sampling_config": context["sampling_config"],
            "independent_context": True,
            "visible_branch_ids": [branch_id],
            "evidence_packet_hash": self.packet["evidence_packet_hash"],
            "target_profile_hash": self.profile["output_hash"],
            "recovery_status": "branch_complete",
            "candidates": candidates,
        })

    def valid_artifacts(self):
        candidates = [
            self.candidate("A-low", "A", "reskin", [2, 1, 1, 2, 5]),
            self.candidate("A-1", "A", "reskin", [5, 2, 2, 5, 3]),
            self.candidate("A-2", "A", "alpha", [4, 3, 3, 4, 2]),
            self.candidate("B-1", "B", "beta", [3, 5, 2, 3, 1]),
            self.candidate("B-2", "B", "gamma", [2, 4, 5, 2, 2]),
            self.candidate("B-3", "B", "theta", [4, 4, 2, 2, 3]),
            self.candidate("C-1", "C", "delta", [3, 2, 5, 4, 3]),
            self.candidate("C-2", "C", "epsilon", [2, 3, 4, 5, 1]),
            self.candidate("C-3", "C", "zeta", [4, 2, 4, 3, 2]),
        ]
        branches = [
            self.branch("A", candidates[:3]),
            self.branch("B", candidates[3:6]),
            self.branch("C", candidates[6:]),
        ]
        representatives, cluster_audit = PORTFOLIO.cluster_candidates(
            candidates, "short", "run-1", PORTFOLIO.canonical_hash([branch["output_hash"] for branch in branches])
        )
        ids = {item["candidate_id"] for item in representatives}
        market_records = {}
        originality_records = {}
        for candidate in representatives:
            candidate_id = candidate["candidate_id"]
            market_records[candidate_id] = {
                "status": "passed",
                "checks": {
                    "entry_promise": True,
                    "reward_cycle": True,
                    "platform_fit": True,
                    "activity_fit": True,
                    "short_closure": True,
                },
                "entry_promise": "the first scene states a concrete pressure and an irreversible choice",
                "reward_cycle": ["pressure exposes the lack", "protagonist makes a choice", "action cannot be reversed", "visible result changes power", "other people react materially", "new cost creates the next desire"],
                "platform_fit": "the concept is calibrated for the selected Fanqie female profile only",
                "channel_fit": "the central desire and relationship feedback fit the selected female channel",
                "channel_verdict": "fit",
                "protagonist_perspective": "female",
                "activity_fit": "not_applicable",
                "causal_consistency": "the premise, three payoffs, and closure preserve one causal answer",
                "contradictions": [],
                "complexity_budget": {"mechanism_count": 2, "assessment": "two interacting mechanisms fit a short narrative without label stacking"},
                "calibrated_objectives": dict(candidate["portfolio_objectives"]),
                "objective_rationales": {
                    objective: f"independent market rationale for {objective} on {candidate_id}"
                    for objective in PORTFOLIO.OBJECTIVES
                },
            }
            originality_records[candidate_id] = {
                "layers": {
                    name: {"status": "passed", "high_recognition_collision": False}
                    for name in ("expression", "semantic", "structural", "causal")
                },
                "closest_work": f"audited-work-{candidate_id}",
                "causal_difference": f"material-causal-difference-{candidate_id}",
                "closest_work_reference": {
                    "identifier": f"frozen-corpus-item-{candidate_id}",
                    "evidence_id": "ev-1",
                },
                "evidence_methods": ["local_history", "direct_result_urls", "structural_fingerprint"],
                "calibrated_originality_risk": candidate["portfolio_objectives"]["originality_risk"],
                "originality_risk_rationale": f"four-layer independent risk rationale for {candidate_id}",
            }
        market = PORTFOLIO.seal({
            "stage": "market_editor_review",
            "schema_version": PORTFOLIO.SCHEMA_VERSION,
            "lane": "short",
            "run_id": "run-1",
            "input_hash": cluster_audit["output_hash"],
            "evidence_packet_hash": self.packet["evidence_packet_hash"],
            "target_profile_hash": self.profile["output_hash"],
            "reviewer_receipt": {
                "reviewer_kind": "market_coverage",
                "delegation_id": "deleg_bbbbbbbb",
                "task_index": 0,
                "reviewer_run_id": "deleg_bbbbbbbb:0",
                "reviewer_agent_id": "market-reviewer-agent",
                "delegated_task_id": "market-review-task",
                "independent_context": True,
                "evidence_packet_hash": self.packet["evidence_packet_hash"],
                "reviewed_candidate_ids": sorted(ids),
                "status": "passed",
                "findings": [],
            },
            "candidates": market_records,
        })
        originality = PORTFOLIO.seal({
            "stage": "originality_redteam",
            "schema_version": PORTFOLIO.SCHEMA_VERSION,
            "lane": "short",
            "run_id": "run-1",
            "input_hash": cluster_audit["output_hash"],
            "evidence_packet_hash": self.packet["evidence_packet_hash"],
            "target_profile_hash": self.profile["output_hash"],
            "reviewer_receipt": {
                "reviewer_kind": "originality_craft",
                "delegation_id": "deleg_bbbbbbbb",
                "task_index": 1,
                "reviewer_run_id": "deleg_bbbbbbbb:1",
                "reviewer_agent_id": "originality-reviewer-agent",
                "delegated_task_id": "originality-review-task",
                "independent_context": True,
                "evidence_packet_hash": self.packet["evidence_packet_hash"],
                "reviewed_candidate_ids": sorted(ids),
                "status": "passed",
                "findings": [],
            },
            "candidates": originality_records,
        })
        self.assertNotIn("A-low", ids)
        self.assertIn("A-1", ids)
        provenance = PORTFOLIO.make_delegation_provenance(
            "run-1", "deleg_aaaaaaaa", "deleg_bbbbbbbb",
            branches, market, originality,
        )
        return branches, market, originality, provenance

    def test_atoms_are_auditable_and_keep_missing_cohort_share_unallocated(self):
        failures, audit = PORTFOLIO.atom_failures(self.packet, self.atoms, "short")
        self.assertEqual(failures, [])
        self.assertEqual(audit["status"], "passed")
        self.assertTrue(audit["missing_cohorts_are_not_redistributed"])
        self.assertEqual(sum(row["atom_count"] for row in audit["cohort_distribution"].values()), 8)
        self.assertEqual(audit["allocated_influence"], 1.0)

        missing_social = dict(self.atoms)
        missing_social["atoms"] = [
            dict(atom) for atom in self.atoms["atoms"]
            if atom["source_cohort"] not in {"xiaohongshu_demand", "bilibili_demand"}
        ]
        missing_social = PORTFOLIO.seal(missing_social)
        failures, missing_audit = PORTFOLIO.atom_failures(self.packet, missing_social, "short")
        self.assertEqual(failures, [])
        self.assertEqual(missing_audit["allocated_influence"], 0.7)
        self.assertEqual(missing_audit["unallocated_influence"], 0.3)
        self.assertEqual(missing_audit["cohort_distribution"]["xiaohongshu_demand"]["allocated_influence"], 0)
        self.assertEqual(missing_audit["cohort_distribution"]["bilibili_demand"]["allocated_influence"], 0)
        for context in self.contexts["contexts"].values():
            self.assertIn("cohort_influence_weight", context["atoms"][0])

    def test_atom_fact_inference_and_frozen_reference_fail_closed(self):
        broken = dict(self.atoms)
        broken["atoms"] = [dict(item) for item in self.atoms["atoms"]]
        broken["atoms"][0]["inference"] = broken["atoms"][0]["observation"]
        broken["atoms"][1]["evidence_id"] = "unknown"
        broken["atoms"][2]["observation"] = "desire"
        broken = PORTFOLIO.seal(broken)
        failures, _ = PORTFOLIO.atom_failures(self.packet, broken, "short")
        reasons = {item["reason"] for item in failures}
        self.assertIn("FACT_INFERENCE_NOT_SEPARATED", reasons)
        self.assertIn("ATOM_EVIDENCE_UNKNOWN", reasons)
        self.assertIn("ATOM_CONTENT_LOW_INFORMATION", reasons)

    def test_three_contexts_are_isolated_and_vs_has_deterministic_fallback(self):
        contexts = PORTFOLIO.build_contexts(
            self.packet, self.atoms, self.profile, "short", "run-1",
            requested_sampling="verbalized_sampling", vs_outcome="invalid", vs_gain=0.5,
        )
        ordered = {
            tuple(atom["atom_id"] for atom in item["atoms"])
            for item in contexts["contexts"].values()
        }
        self.assertEqual(len(ordered), 3)
        for branch_id, context in contexts["contexts"].items():
            self.assertEqual(context["visible_branch_ids"], [branch_id])
            self.assertEqual(context["sampling_config"]["effective"], "standard_stratified")
            self.assertEqual(context["sampling_config"]["fallback_reason"], "VS_INVALID")

    def test_structural_calibration_merges_reskin_but_separates_new_causality(self):
        base = self.fingerprint("same-cause")
        reskin = dict(base)
        reskin["opening_form"] = "spaceship profession and imperial era names"
        reskin["audience_desire"] = "different surface occupation fantasy"
        merged = PORTFOLIO.fingerprint_similarity(base, reskin, "short")
        self.assertTrue(merged["merge"])

        different = dict(base)
        for key in PORTFOLIO.CAUSAL_DIMENSIONS:
            different[key] = f"new-causal-path-{key}"
        separated = PORTFOLIO.fingerprint_similarity(base, different, "short")
        self.assertFalse(separated["merge"])

    def test_full_pipeline_returns_pareto_cards_and_pauses_for_user(self):
        branches, market, originality, provenance = self.valid_artifacts()
        result = PORTFOLIO.assemble_portfolio(
            self.packet, self.atoms, self.contexts, branches, market, originality,
            self.profile, "short", "run-1", provenance,
        )
        self.assertEqual(result["status"], "awaiting_user_choice")
        self.assertEqual(result["route"], "await_user_selection")
        self.assertEqual(result["resume_route"], "short-story-writer")
        self.assertFalse(result["auto_route_before_user_selection"])
        self.assertGreaterEqual(len(result["candidate_cards"]), 4)
        self.assertLessEqual(len(result["candidate_cards"]), 6)
        self.assertNotIn("A-low", result["pareto_frontier_ids"])
        self.assertTrue(
            {card["candidate_id"] for card in result["candidate_cards"]}
            <= set(result["pareto_frontier_ids"])
        )
        self.assertEqual(result["generated_count"], 9)
        self.assertEqual(result["selected_for_delivery_count"], len(result["candidate_cards"]))
        self.assertEqual(result["usable_candidate_count"], len(result["candidate_cards"]))

    def test_originality_reviewer_may_correct_generator_hypothesis(self):
        branches, market, originality, _ = self.valid_artifacts()
        candidate_id = sorted(originality["candidates"])[0]
        originality["candidates"][candidate_id]["closest_work"] = "审计后确认的更接近作品"
        originality["candidates"][candidate_id]["causal_difference"] = "审计后确认的候选专属因果差异"
        originality["candidates"][candidate_id]["closest_work_reference"] = {
            "identifier": "packet-evidence-one", "evidence_id": "ev-1",
        }
        originality = PORTFOLIO.seal(originality)
        provenance = PORTFOLIO.make_delegation_provenance(
            "run-1", "deleg_aaaaaaaa", "deleg_bbbbbbbb",
            branches, market, originality,
        )
        result = PORTFOLIO.assemble_portfolio(
            self.packet, self.atoms, self.contexts, branches, market, originality,
            self.profile, "short", "run-1", provenance,
        )
        self.assertEqual(result["status"], "awaiting_user_choice")
        card = next(row for row in result["candidate_cards"] if row["candidate_id"] == candidate_id)
        self.assertEqual(card["closest_work"], "审计后确认的更接近作品")
        self.assertEqual(card["causal_difference"], "审计后确认的候选专属因果差异")
        self.assertNotEqual(
            card["originality_audit"]["generator_hypothesis"]["closest_work"],
            card["originality_audit"]["reviewer_finding"]["closest_work"],
        )

    def test_originality_reference_must_resolve_to_frozen_packet(self):
        branches, market, originality, _ = self.valid_artifacts()
        candidate_id = sorted(originality["candidates"])[0]
        originality["candidates"][candidate_id]["closest_work_reference"] = {
            "identifier": "invented", "evidence_id": "not-in-packet",
        }
        originality = PORTFOLIO.seal(originality)
        provenance = PORTFOLIO.make_delegation_provenance(
            "run-1", "deleg_aaaaaaaa", "deleg_bbbbbbbb",
            branches, market, originality,
        )
        result = PORTFOLIO.assemble_portfolio(
            self.packet, self.atoms, self.contexts, branches, market, originality,
            self.profile, "short", "run-1", provenance,
        )
        self.assertIn(
            "CLOSEST_WORK_REFERENCE_INVALID",
            {row["reason"] for row in result["failures"]},
        )

    def test_mechanism_signature_normalizes_paraphrases(self):
        left = {"structural_fingerprint": self.fingerprint("same-cause")}
        right_fingerprint = self.fingerprint("same-cause")
        right_fingerprint["core_mechanism"] = "把个人回忆拿去抵押，换取末世里的生存物资"
        right_fingerprint["mechanism_cost"] = "每次质押记忆都会永久遗忘一段亲情"
        right = {"structural_fingerprint": right_fingerprint}
        different = {"structural_fingerprint": self.fingerprint("gamma")}
        self.assertEqual(PORTFOLIO.mechanism_signature(left), PORTFOLIO.mechanism_signature(right))
        self.assertNotEqual(PORTFOLIO.mechanism_signature(left), PORTFOLIO.mechanism_signature(different))

    def test_individual_vetoes_do_not_fail_the_batch_or_force_all_branches(self):
        branches, market, originality, _ = self.valid_artifacts()
        vetoed = {
            candidate_id for candidate_id in market["candidates"]
            if candidate_id.startswith("C-")
        }
        for candidate_id in vetoed:
            market["candidates"][candidate_id]["status"] = "rejected"
        market = PORTFOLIO.seal(market)
        provenance = PORTFOLIO.make_delegation_provenance(
            "run-1", "deleg_aaaaaaaa", "deleg_bbbbbbbb",
            branches, market, originality,
        )
        result = PORTFOLIO.assemble_portfolio(
            self.packet, self.atoms, self.contexts, branches, market, originality,
            self.profile, "short", "run-1", provenance,
        )
        self.assertEqual(result["status"], "awaiting_user_choice")
        self.assertTrue(vetoed.issubset(set(result["vetoed_candidate_ids"])))
        self.assertTrue(all(card["generator_branch"] in {"A", "B"} for card in result["candidate_cards"]))
        self.assertGreaterEqual(len({card["mechanism_signature"] for card in result["candidate_cards"]}), 3)

    def test_market_status_variants_do_not_veto_candidates(self):
        """Status wording is model-surface drift: 通过/ok/yes/approved must not veto.

        The S4 market veto must reject on explicit rejection markers only, so
        any pass variant (pass/passed/acceptable/通过/ok/yes/approved) keeps the
        candidate in the pool. Regression for the "pass vs passed 无用卡住" class.
        """
        for variant in ("通过", "ok", "yes", "approved", "Pass", "PASSED", "acceptable"):
            branches, market, originality, _ = self.valid_artifacts()
            for record in market["candidates"].values():
                record["status"] = variant
            market = PORTFOLIO.seal(market)
            provenance = PORTFOLIO.make_delegation_provenance(
                "run-1", "deleg_aaaaaaaa", "deleg_bbbbbbbb",
                branches, market, originality,
            )
            result = PORTFOLIO.assemble_portfolio(
                self.packet, self.atoms, self.contexts, branches, market, originality,
                self.profile, "short", "run-1", provenance,
            )
            self.assertEqual(
                result["status"], "awaiting_user_choice",
                f"market status {variant!r} must not fail the batch",
            )
            self.assertEqual(
                set(result["vetoed_candidate_ids"]), set(),
                f"market status {variant!r} must not veto any candidate",
            )

    def test_market_status_explicit_reject_still_vetoes(self):
        """Explicit rejection markers must still veto even without failing checks."""
        branches, market, originality, _ = self.valid_artifacts()
        target = "C-1"
        market["candidates"][target]["status"] = "rejected"
        del market["candidates"][target]["checks"]  # no failing checks dict at all
        market = PORTFOLIO.seal(market)
        provenance = PORTFOLIO.make_delegation_provenance(
            "run-1", "deleg_aaaaaaaa", "deleg_bbbbbbbb",
            branches, market, originality,
        )
        result = PORTFOLIO.assemble_portfolio(
            self.packet, self.atoms, self.contexts, branches, market, originality,
            self.profile, "short", "run-1", provenance,
        )
        self.assertIn(target, set(result["vetoed_candidate_ids"]))

    def test_same_sealed_inputs_resume_idempotently_at_user_pause(self):
        branches, market, originality, provenance = self.valid_artifacts()
        first = PORTFOLIO.assemble_portfolio(
            self.packet, self.atoms, self.contexts, branches, market, originality,
            self.profile, "short", "run-1", provenance,
        )
        second = PORTFOLIO.assemble_portfolio(
            self.packet, self.atoms, self.contexts, branches, market, originality,
            self.profile, "short", "run-1", provenance,
        )
        self.assertEqual(first, second)
        self.assertEqual(first["recovery_status"], "idempotent_pause_checkpoint")
    def test_missing_generation_branch_blocks_formal_cards(self):
        branches, market, originality, provenance = self.valid_artifacts()
        result = PORTFOLIO.assemble_portfolio(
            self.packet, self.atoms, self.contexts, branches[:2], market, originality,
            self.profile, "short", "run-1", provenance,
        )
        self.assertEqual(result["status"], "candidate_generation_failed")
        self.assertTrue(result["diagnostic_only"])
        self.assertTrue(any(item["reason"] == "THREE_GENERATION_BRANCHES_REQUIRED" for item in result["failures"]))

    def test_originality_runs_only_on_cluster_representatives_and_rejects_ai_style_proxy(self):
        branches, market, originality, provenance = self.valid_artifacts()
        originality["candidates"]["A-low"] = originality["candidates"]["A-1"]
        result = PORTFOLIO.assemble_portfolio(
            self.packet, self.atoms, self.contexts, branches, market, originality,
            self.profile, "short", "run-1", provenance,
        )
        self.assertTrue(any(item["reason"] == "ORIGINALITY_REDTEAM_CANDIDATE_SET_MISMATCH" for item in result["failures"]))

        originality.pop("candidates")
        _, _, clean_originality, _ = self.valid_artifacts()
        clean_originality["candidates"]["A-1"]["evidence_methods"].append("perplexity")
        result = PORTFOLIO.assemble_portfolio(
            self.packet, self.atoms, self.contexts, branches, market, clean_originality,
            self.profile, "short", "run-1",
            PORTFOLIO.make_delegation_provenance(
                "run-1", "deleg_aaaaaaaa", "deleg_bbbbbbbb",
                branches, market, clean_originality,
            ),
        )
        self.assertTrue(any(item["reason"] == "AI_STYLE_METRIC_USED_AS_ORIGINALITY_EVIDENCE" for item in result["failures"]))

    def test_profile_separates_general_and_activity_tracks(self):
        activity = {
            "activity_id": "fanqie-event-2026-07",
            "name": "current verified Fanqie event",
            "platform": "fanqie",
            "source_url": "https://fanqienovel.com/writer/zone/solicit-activity",
            "rule_hash": "a" * 64,
            "retrieved_at": "2026-07-21T10:00:00+08:00",
            "submission_window_status": "open",
            "rule_evidence_ids": ["event-rule-evidence-1"],
            "requirements": ["use one of the published activity genres"],
            "allowed_lanes": ["short"],
            "allowed_channels": ["female"],
        }
        activity_profile = PORTFOLIO.make_profile("short", "activity", "fanqie", "female", activity=activity)
        self.assertEqual(activity_profile["portfolio_track"], "activity")
        self.assertEqual(PORTFOLIO.profile_failures(activity_profile), [])
        with self.assertRaisesRegex(ValueError, "GENERAL_PROFILE_MUST_NOT_EMBED_ACTIVITY"):
            PORTFOLIO.make_profile("short", "general", "fanqie", "female", activity=activity)
        with self.assertRaisesRegex(ValueError, "PROFILE_PLATFORM_NOT_PRIMARY"):
            PORTFOLIO.make_profile("short", "general", "qidian", "female")

    def test_story_contract_rejects_tampered_story_after_review(self):
        candidate = self.candidate("A-9", "A", "shape", [3, 3, 3, 3, 3])
        self.assertEqual(PORTFOLIO.story_contract_failures(candidate), [])
        candidate["story_proposal"] += "未经编辑复核的新结局"
        reasons = {row["reason"] for row in PORTFOLIO.story_contract_failures(candidate)}
        self.assertIn("STORY_REVIEW_HASH_MISMATCH", reasons)
        self.assertIn("STORY_TRACE_MISMATCH", reasons)

    def test_candidate_card_rejects_platform_channel_placeholders_and_activity_mixing(self):
        candidate = self.candidate("A-9", "A", "shape", [3, 3, 3, 3, 3])
        card = candidate["candidate_card"]
        card["target_platform"] = "qimao"
        card["audience_channel"] = "male"
        card["opening_300_beats"] = ["beat1", "beat2", "beat3"]
        card["activity_route"] = {"activity_id": "unrequested"}
        reasons = PORTFOLIO.candidate_card_shape_failures(candidate, "short", self.profile)
        self.assertIn("CARD_TARGET_PLATFORM_MISMATCH", reasons)
        self.assertIn("CARD_AUDIENCE_CHANNEL_MISMATCH", reasons)
        self.assertIn("CARD_OPENING_300_INVALID", reasons)
        self.assertIn("GENERAL_CARD_ACTIVITY_ROUTE_INVALID", reasons)
        candidate["candidate_card"] = None
        self.assertEqual(
            PORTFOLIO.candidate_card_shape_failures(candidate, "short", self.profile),
            ["CANDIDATE_CARD_MISSING"],
        )

    def test_long_card_requires_substantive_three_stage_engine(self):
        profile = PORTFOLIO.make_profile("long", "general", "qimao", "male")
        candidate = self.candidate("A-8", "A", "long-shape", [3, 3, 3, 3, 3])
        card = candidate["candidate_card"]
        card.update({
            "target_platform": "qimao",
            "audience_channel": "male",
            "target_profile_hash": profile["output_hash"],
            "short_closure": None,
            "long_run_stages": {
                "300k": {"goal": "step1"},
                "800k": {"goal": "step2"},
                "1500k": {"goal": "step3"},
            },
        })
        reasons = PORTFOLIO.candidate_card_shape_failures(candidate, "long", profile)
        self.assertTrue(any(reason.startswith("CARD_LONG_STAGE_NOT_SUBSTANTIVE") for reason in reasons))

    def test_raw_book_title_text_is_rejected_and_context_is_capped(self):
        broken = dict(self.atoms)
        broken["atoms"] = [dict(item) for item in self.atoms["atoms"]]
        broken["atoms"][0]["observation"] = "\u300aCopied Book Title\u300b is currently visible in the rank."
        broken = PORTFOLIO.seal(broken)
        failures, _ = PORTFOLIO.atom_failures(self.packet, broken, "short")
        self.assertIn("RAW_TITLE_TEXT_LEAKED_TO_ATOM", {item["reason"] for item in failures})
        self.assertTrue(all(len(context["atoms"]) <= 60 for context in self.contexts["contexts"].values()))

    def test_manual_reviewer_receipt_is_not_valid_provenance(self):
        branches, market, originality, provenance = self.valid_artifacts()
        market["reviewer_receipt"]["delegation_id"] = "manual_fix"
        market["reviewer_receipt"]["reviewer_run_id"] = "manual_fix:0"
        market = PORTFOLIO.seal(market)
        result = PORTFOLIO.assemble_portfolio(
            self.packet, self.atoms, self.contexts, branches, market, originality,
            self.profile, "short", "run-1", provenance,
        )
        self.assertIn("REVIEWER_RECEIPT_INVALID", {item["reason"] for item in result["failures"]})

    def test_final_pareto_scores_are_independent_reviewer_scores(self):
        branches, market, originality, provenance = self.valid_artifacts()
        result = PORTFOLIO.assemble_portfolio(
            self.packet, self.atoms, self.contexts, branches, market, originality,
            self.profile, "short", "run-1", provenance,
        )
        for card in result["candidate_cards"]:
            candidate_id = card["candidate_id"]
            expected = dict(market["candidates"][candidate_id]["calibrated_objectives"])
            expected["originality_risk"] = originality["candidates"][candidate_id]["calibrated_originality_risk"]
            self.assertEqual(card["pareto_objectives"], expected)

    def test_audience_description_and_platform_alias_are_not_deliverable_concepts(self):
        candidate = self.candidate("A-7", "A", "semantic", [3, 3, 3, 3, 3])
        candidate["candidate_card"]["one_line_concept"] = "Readers seeking fast rewards prefer strong protagonists"
        candidate["candidate_card"]["target_platform"] = "\u756a\u8304"
        reasons = PORTFOLIO.candidate_card_shape_failures(candidate, "short", self.profile)
        self.assertIn("CARD_ONE_LINE_CONCEPT_IS_AUDIENCE_DESCRIPTION", reasons)
        self.assertIn("CARD_ONE_LINE_CONCEPT_LANGUAGE_INVALID", reasons)
        self.assertIn("CARD_TARGET_PLATFORM_MISMATCH", reasons)

    def test_placeholders_and_truncated_concepts_fail_closed(self):
        candidate = self.candidate('A-6', 'A', 'semantic-hardening', [3, 3, 3, 3, 3])
        card = candidate['candidate_card']
        card['closest_work'] = ''.join(map(chr, PORTFOLIO.LOW_INFORMATION_CODEPOINTS[0]))
        card['causal_difference'] = ''.join(map(chr, PORTFOLIO.LOW_INFORMATION_CODEPOINTS[2]))
        card['one_line_concept'] += ''.join(map(chr, PORTFOLIO.TRUNCATED_END_CODEPOINTS[2]))
        reasons = PORTFOLIO.candidate_card_shape_failures(candidate, 'short', self.profile)
        self.assertIn('CARD_CLOSEST_WORK_PLACEHOLDER', reasons)
        self.assertIn('CARD_CAUSAL_DIFFERENCE_PLACEHOLDER', reasons)
        self.assertIn('CARD_ONE_LINE_CONCEPT_TRUNCATED', reasons)

    def test_uniform_market_scores_fail_closed(self):
        branches, market, originality, _ = self.valid_artifacts()
        for record in market["candidates"].values():
            record["calibrated_objectives"] = dict(zip(PORTFOLIO.OBJECTIVES, [3, 3, 3, 3, 3]))
        market = PORTFOLIO.seal(market)
        provenance = PORTFOLIO.make_delegation_provenance(
            "run-1", "deleg_aaaaaaaa", "deleg_bbbbbbbb", branches, market, originality,
        )
        result = PORTFOLIO.assemble_portfolio(
            self.packet, self.atoms, self.contexts, branches, market, originality,
            self.profile, "short", "run-1", provenance,
        )
        self.assertIn("MARKET_SCORE_VECTORS_UNIFORM", {item["reason"] for item in result["failures"]})

    def test_majority_reused_market_score_vector_fails_closed(self):
        branches, market, originality, _ = self.valid_artifacts()
        candidate_ids = list(market['candidates'])
        repeated = dict(zip(PORTFOLIO.OBJECTIVES, [3, 3, 3, 3, 3]))
        for candidate_id in candidate_ids[: len(candidate_ids) // 2 + 1]:
            market['candidates'][candidate_id]['calibrated_objectives'] = repeated
        market = PORTFOLIO.seal(market)
        provenance = PORTFOLIO.make_delegation_provenance(
            'run-1', 'deleg_aaaaaaaa', 'deleg_bbbbbbbb', branches, market, originality,
        )
        result = PORTFOLIO.assemble_portfolio(
            self.packet, self.atoms, self.contexts, branches, market, originality,
            self.profile, 'short', 'run-1', provenance,
        )
        self.assertIn('MARKET_SCORE_VECTOR_OVERUSED', {item['reason'] for item in result['failures']})

    def test_runtime_reviewer_id_must_match_provenance(self):
        branches, market, originality, _ = self.valid_artifacts()
        provenance = PORTFOLIO.make_delegation_provenance(
            "run-1", "deleg_aaaaaaaa", "deleg_cccccccc", branches, market, originality,
        )
        result = PORTFOLIO.assemble_portfolio(
            self.packet, self.atoms, self.contexts, branches, market, originality,
            self.profile, "short", "run-1", provenance,
        )
        self.assertIn("REVIEWER_RUNTIME_DELEGATION_ID_MISMATCH", {item["reason"] for item in result["failures"]})

    def test_delivery_requires_profile_directory_and_exact_sealed_cards(self):
        branches, market, originality, provenance = self.valid_artifacts()
        gate = PORTFOLIO.assemble_portfolio(
            self.packet, self.atoms, self.contexts, branches, market, originality,
            self.profile, "short", "run-1", provenance,
        )
        cards = PORTFOLIO.make_cards_bundle(gate)
        good_dir = Path("candidate_runs") / self.profile["profile_slug"]
        self.assertEqual(PORTFOLIO.delivery_failures(gate, cards, self.profile, good_dir), [])
        altered = dict(cards)
        altered["cards"] = altered["cards"][:-1]
        altered = PORTFOLIO.seal(altered)
        reasons = {item["reason"] for item in PORTFOLIO.delivery_failures(gate, altered, self.profile, good_dir)}
        self.assertIn("CANDIDATE_CARDS_GATE_MISMATCH", reasons)
        reasons = {item["reason"] for item in PORTFOLIO.delivery_failures(gate, cards, self.profile, Path("candidate_runs") / "short")}
        self.assertIn("PROFILE_OUTPUT_DIR_NOT_ISOLATED", reasons)


class ValidatorToleranceTests(unittest.TestCase):
    """Tests for the 4.4.0-rc1 validator fault-tolerance paths."""

    def setUp(self) -> None:
        self.candidate_ids = {"A-C01", "B-C01"}
        self.profile = {"output_hash": "test-hash", "portfolio_track": "general", "activity": {}, "audience_channel": "female"}
        self.registry = {"evidence_ids": {"ev-1", "ev-2"}, "urls": {"https://example.com/work"}}

    def _market_record(self, **overrides):
        record = {
            "status": "passed",
            "checks": {"entry_promise": True, "reward_cycle": True, "platform_fit": True, "activity_fit": True, "short_closure": True},
            "entry_promise": "读者入场钩子描述",
            "reward_cycle": ["持续压迫感", "艰难选择", "不可逆行动", "可见结果", "世界反应", "新代价"],
            "platform_fit": "番茄平台适配分析",
            "channel_fit": "女频频道适配分析",
            "channel_verdict": "fit",
            "protagonist_perspective": "female",
            "activity_fit": "not_applicable",
            "causal_consistency": "因果一致性分析通过",
            "contradictions": [],
            "calibrated_objectives": {"commercial_certainty": 4, "structural_novelty": 3, "emotional_impact": 4, "producibility": 3, "originality_risk": 2},
            "objective_rationales": {"commercial_certainty": "商业确定性理由", "structural_novelty": "结构新意理由", "emotional_impact": "情感冲击理由", "producibility": "可制作性理由", "originality_risk": "原创风险理由"},
            "complexity_budget": {"mechanism_count": 2, "assessment": "机制复杂度评估说明"},
        }
        record.update(overrides)
        return record

    def _originality_record(self, **overrides):
        record = {
            "layers": {
                "expression": {"status": "passed", "high_recognition_collision": False, "closest_match": "无", "evidence": "表达层证据"},
                "semantic": {"status": "passed", "high_recognition_collision": False, "closest_match": "无", "evidence": "语义层证据"},
                "structural": {"status": "passed", "high_recognition_collision": False, "closest_match": "无", "evidence": "结构层证据"},
                "causal": {"status": "passed", "high_recognition_collision": False, "closest_match": "无", "evidence": "因果层证据"},
            },
            "closest_work": "最近作品名称描述",
            "causal_difference": "因果差异实质性描述",
            "closest_work_reference": {"identifier": "证据引用", "evidence_id": "ev-1"},
            "evidence_methods": ["structural_comparison"],
            "calibrated_originality_risk": 3,
            "originality_risk_rationale": "原创风险评估理由",
        }
        record.update(overrides)
        return record

    def _run_market(self, records):
        audit = {"candidates": records, "stage": "market_editor_review", "schema_version": PORTFOLIO.SCHEMA_VERSION,
                 "lane": "short", "run_id": "r", "input_hash": "h", "evidence_packet_hash": "p",
                 "target_profile_hash": "test-hash", "reviewer_receipt": {
                     "reviewer_kind": "market_coverage", "independent_context": True,
                     "evidence_packet_hash": "p", "reviewed_candidate_ids": sorted(self.candidate_ids),
                     "status": "passed", "findings": [], "reviewer_agent_id": "agent",
                     "delegated_task_id": "task", "job_id": "job-1", "session_id": "sess-1",
                     "attempt": 1, "reviewer_run_id": "sess-1",
                 }}
        audit = PORTFOLIO.seal(audit)
        return PORTFOLIO.validate_market_audit(
            audit, self.candidate_ids, "short", "r", "h", "p", self.profile, allow_rejections=True,
        )

    def _run_originality(self, records):
        audit = {"candidates": records, "stage": "originality_redteam", "schema_version": PORTFOLIO.SCHEMA_VERSION,
                 "lane": "short", "run_id": "r", "input_hash": "h", "evidence_packet_hash": "p",
                 "target_profile_hash": "test-hash", "reviewer_receipt": {
                     "reviewer_kind": "originality_craft", "independent_context": True,
                     "evidence_packet_hash": "p", "reviewed_candidate_ids": sorted(self.candidate_ids),
                     "status": "passed", "findings": [], "reviewer_agent_id": "agent",
                     "delegated_task_id": "task", "job_id": "job-1", "session_id": "sess-1",
                     "attempt": 1, "reviewer_run_id": "sess-1",
                 }}
        audit = PORTFOLIO.seal(audit)
        return PORTFOLIO.validate_originality_audit(
            audit, self.candidate_ids, "short", "r", "h", "p", self.profile,
            self.registry, allow_rejections=True,
        )

    def test_nested_score_rationale_objectives_accepted(self):
        nested = {obj: {"score": 4, "rationale": f"嵌套理由-{obj}"} for obj in PORTFOLIO.OBJECTIVES}
        records = {cid: self._market_record(calibrated_objectives=nested, objective_rationales="invalid") for cid in self.candidate_ids}
        failures = self._run_market(records)
        reasons = {f["reason"] for f in failures}
        self.assertNotIn("MARKET_CALIBRATED_OBJECTIVE_INVALID", reasons)
        self.assertNotIn("MARKET_OBJECTIVE_RATIONALE_MISSING", reasons)

    def test_string_mechanism_count_coerced(self):
        records = {cid: self._market_record(complexity_budget={"mechanism_count": "2", "assessment": "机制复杂度评估"}) for cid in self.candidate_ids}
        failures = self._run_market(records)
        self.assertNotIn("SHORT_COMPLEXITY_BUDGET_INVALID", {f["reason"] for f in failures})

    def test_reward_cycle_four_items_accepted(self):
        records = {cid: self._market_record(reward_cycle=["压力积累", "选择困境", "不可逆行动", "可见结果"]) for cid in self.candidate_ids}
        failures = self._run_market(records)
        self.assertNotIn("READING_RETURN_CYCLE_INVALID", {f["reason"] for f in failures})

    def test_channel_verdict_missing_is_invalid(self):
        record = self._market_record()
        del record["channel_verdict"]
        records = {cid: dict(record) for cid in self.candidate_ids}
        reasons = {f["reason"] for f in self._run_market(records)}
        self.assertIn("MARKET_CHANNEL_VERDICT_INVALID", reasons)

    def test_channel_mismatch_must_reject_record(self):
        records = {cid: self._market_record(channel_verdict="mismatch") for cid in self.candidate_ids}
        reasons = {f["reason"] for f in self._run_market(records)}
        self.assertIn("CHANNEL_MISMATCH_NOT_REJECTED", reasons)
        rejected = {cid: self._market_record(channel_verdict="mismatch", status="rejected") for cid in self.candidate_ids}
        reasons = {f["reason"] for f in self._run_market(rejected)}
        self.assertNotIn("CHANNEL_MISMATCH_NOT_REJECTED", reasons)

    def test_opposite_perspective_cannot_claim_fit(self):
        records = {cid: self._market_record(protagonist_perspective="male") for cid in self.candidate_ids}
        reasons = {f["reason"] for f in self._run_market(records)}
        self.assertIn("CHANNEL_VERDICT_CONTRADICTS_PERSPECTIVE", reasons)
        records = {cid: self._market_record(protagonist_perspective="male", channel_verdict="partial") for cid in self.candidate_ids}
        reasons = {f["reason"] for f in self._run_market(records)}
        self.assertNotIn("CHANNEL_VERDICT_CONTRADICTS_PERSPECTIVE", reasons)

    def test_reward_cycle_string_still_fails(self):
        records = {cid: self._market_record(reward_cycle="单个字符串不是列表") for cid in self.candidate_ids}
        failures = self._run_market(records)
        self.assertIn("READING_RETURN_CYCLE_INVALID", {f["reason"] for f in failures})

    def test_status_pass_variant_accepted(self):
        records = {cid: self._market_record(status="pass") for cid in self.candidate_ids}
        failures = self._run_market(records)
        self.assertNotIn("MARKET_EDITOR_REJECTED", {f["reason"] for f in failures})

    def test_layers_any_order_accepted(self):
        layers = self._originality_record()["layers"]
        reordered = {"causal": layers["causal"], "expression": layers["expression"], "structural": layers["structural"], "semantic": layers["semantic"]}
        records = {cid: self._originality_record(layers=reordered) for cid in self.candidate_ids}
        failures = self._run_originality(records)
        self.assertNotIn("ORIGINALITY_LAYER_ORDER_INVALID", {f["reason"] for f in failures})

    def test_layers_missing_key_still_fails(self):
        layers = self._originality_record()["layers"]
        del layers["causal"]
        records = {cid: self._originality_record(layers=layers) for cid in self.candidate_ids}
        failures = self._run_originality(records)
        self.assertIn("ORIGINALITY_LAYER_ORDER_INVALID", {f["reason"] for f in failures})

    def test_bare_string_reference_accepted_when_in_registry(self):
        records = {cid: self._originality_record(closest_work_reference="ev-1") for cid in self.candidate_ids}
        failures = self._run_originality(records)
        self.assertNotIn("CLOSEST_WORK_REFERENCE_INVALID", {f["reason"] for f in failures})

    def test_bare_string_reference_rejected_when_not_in_registry(self):
        records = {cid: self._originality_record(closest_work_reference="not-in-registry") for cid in self.candidate_ids}
        failures = self._run_originality(records)
        self.assertIn("CLOSEST_WORK_REFERENCE_INVALID", {f["reason"] for f in failures})

    def test_string_risk_calibration_coerced(self):
        records = {cid: self._originality_record(calibrated_originality_risk="3") for cid in self.candidate_ids}
        failures = self._run_originality(records)
        self.assertNotIn("ORIGINALITY_RISK_CALIBRATION_INVALID", {f["reason"] for f in failures})

    def test_layer_status_pass_variant_accepted(self):
        layers = self._originality_record()["layers"]
        for name in layers:
            layers[name]["status"] = "pass"
        records = {cid: self._originality_record(layers=layers) for cid in self.candidate_ids}
        failures = self._run_originality(records)
        self.assertNotIn("ORIGINALITY_REDTEAM_REJECTED", {f["reason"] for f in failures})

    def test_rejected_candidate_with_contradictions_passes_when_allowed(self):
        rejected = self._market_record(
            status="rejected",
            contradictions=["因果链断裂：主角动机与结局矛盾"],
            entry_promise="",
            reward_cycle=[],
            platform_fit="",
            channel_fit="",
            causal_consistency="",
            calibrated_objectives=None,
            objective_rationales=None,
            complexity_budget=None,
        )
        records = {cid: rejected for cid in self.candidate_ids}
        failures = self._run_market(records)
        self.assertEqual(failures, [])

    def test_rejected_candidate_fails_when_rejections_not_allowed(self):
        rejected = self._market_record(
            status="rejected",
            contradictions=["因果链断裂"],
        )
        records = {cid: rejected for cid in self.candidate_ids}
        audit = {"candidates": records, "stage": "market_editor_review", "schema_version": PORTFOLIO.SCHEMA_VERSION,
                 "lane": "short", "run_id": "r", "input_hash": "h", "evidence_packet_hash": "p",
                 "target_profile_hash": "test-hash", "reviewer_receipt": {
                     "reviewer_kind": "market_coverage", "independent_context": True,
                     "evidence_packet_hash": "p", "reviewed_candidate_ids": sorted(self.candidate_ids),
                     "status": "passed", "findings": [], "reviewer_agent_id": "agent",
                     "delegated_task_id": "task", "job_id": "job-1", "session_id": "sess-1",
                     "attempt": 1, "reviewer_run_id": "sess-1",
                 }}
        audit = PORTFOLIO.seal(audit)
        failures = PORTFOLIO.validate_market_audit(
            audit, self.candidate_ids, "short", "r", "h", "p", self.profile, allow_rejections=False,
        )
        reasons = {f["reason"] for f in failures}
        self.assertIn("MARKET_EDITOR_REJECTED", reasons)
        self.assertIn("MARKET_CAUSAL_CONTRADICTION_PRESENT", reasons)


class RecoveryFailureInjectionTests(unittest.TestCase):
    """Tests for save_state PermissionError retry logic."""

    def test_save_state_retries_on_permission_error(self):
        import tempfile as tmp_mod
        from unittest.mock import patch
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        import candidate_workflow as workflow

        with tmp_mod.TemporaryDirectory() as td:
            target = Path(td) / "state.json"
            call_count = {"n": 0}
            original_replace = os.replace

            def flaky_replace(src, dst):
                call_count["n"] += 1
                if call_count["n"] <= 2:
                    raise PermissionError("WinError 5: Access is denied")
                return original_replace(src, dst)

            with patch("os.replace", side_effect=flaky_replace):
                workflow.save_state(target, {"status": "ok", "attempt": 1})

            self.assertEqual(call_count["n"], 3)
            with open(target, encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data["status"], "ok")

    def test_save_state_raises_after_three_failures(self):
        import tempfile as tmp_mod
        from unittest.mock import patch
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        import candidate_workflow as workflow

        with tmp_mod.TemporaryDirectory() as td:
            target = Path(td) / "state.json"

            def always_fail(src, dst):
                raise PermissionError("WinError 5: Access is denied")

            with patch("os.replace", side_effect=always_fail):
                with self.assertRaises(PermissionError):
                    workflow.save_state(target, {"status": "fail"})


if __name__ == "__main__":
    unittest.main()
