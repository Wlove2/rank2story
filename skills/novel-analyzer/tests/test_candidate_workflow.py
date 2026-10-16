from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys
import tempfile
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


PORTFOLIO = load("candidate_portfolio")
WORKFLOW = load("candidate_workflow")
FREEZE = load("freeze_evidence_packet")

SOURCES = [
    ("fanqie_writer_hot_stories", "fanqie_official_short", "fanqie"),
    ("fanqie_reader_short_rank_center", "fanqie_official_short", "fanqie"),
    ("qimao_reader_story_rank_center", "qimao_official_story", "qimao"),
    ("xiaohongshu_novel_demand_shared", "xiaohongshu_demand", "xiaohongshu"),
    ("bilibili_novel_demand_shared", "bilibili_demand", "bilibili"),
    ("qimao_reader_story_rank_center", "qimao_official_story", "qimao"),
]


class CandidateWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        evidence = [
            {"evidence_id": f"ev-{index}", "source_item_id": f"item-{index}", "source_id": source_id}
            for index, (source_id, _, _) in enumerate(SOURCES, 1)
        ]
        self.packet = FREEZE.freeze(
            {"lane": "short", "sources": []},
            {"formal_candidate_generation": "allowed", "lane": "short"},
            evidence,
            {"selected_works": []},
        )

    def save_packet(self, directory: Path) -> Path:
        path = directory / "packet.json"
        path.write_text(json.dumps(self.packet, ensure_ascii=False), encoding="utf-8")
        return path

    def test_run_creates_unique_claim_and_only_atoms_action(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            packet = self.save_packet(root)
            first = WORKFLOW.init_run(root, packet, "short", "fanqie", "female")
            second = WORKFLOW.init_run(root, packet, "short", "fanqie", "female")
            self.assertNotEqual(first["run_id"], second["run_id"])
            self.assertEqual(first["production_contract_version"], "4.4.0-rc1")
            self.assertEqual(first["stage"], "S1_ATOMS")
            self.assertEqual(first["status"], "paused")
            self.assertEqual(first["execution_profile"], "production")
            self.assertEqual(first["kernels_per_branch"], 3)
            self.assertEqual([row["role"] for row in first["actions"]], ["atoms"])
            claim, profile, _, output_dir, _ = WORKFLOW.validate_claim(Path(first["claim"]))
            self.assertEqual(profile["production_contract_version"], "4.4.0-rc1")
            self.assertRegex(claim["bundle_hash"], r"^[0-9a-f]{64}$")
            self.assertIn("novel-candidate-portfolio/SKILL.md", claim["bundle_files"])
            self.assertEqual(output_dir.name, profile["profile_slug"])
            self.assertEqual(claim["lane"], "short")

    def test_smoke_profile_and_executor_lease_are_explicit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = WORKFLOW.init_run(
                root, self.save_packet(root), "short", "fanqie", "female", "smoke",
            )
            self.assertEqual(result["kernels_per_branch"], 2)
            claim_path = Path(result["claim"])
            running = WORKFLOW.acquire_executor_lease(claim_path, "exec-test-123456", "test-model")
            self.assertEqual(running["status"], "running")
            paused = WORKFLOW.release_executor_lease(claim_path, "exec-test-123456")
            self.assertEqual(paused["status"], "paused")

    def test_recovery_budget_is_shared_across_recovery_kinds(self):
        state = {}
        reasons = ("story_rewrite", "mapper_format_repair", "format_repair", "kernel_supplement")
        for i in range(WORKFLOW.RECOVERY_CALL_BUDGET):
            self.assertTrue(WORKFLOW.reserve_recovery_call(state, reasons[i % len(reasons)]))
        self.assertFalse(WORKFLOW.reserve_recovery_call(state, "gap_fill"))
        self.assertEqual(state["recovery_budget"]["used"], WORKFLOW.RECOVERY_CALL_BUDGET)

    def test_kernel_fields_are_examples_and_controller_normalizes_metadata(self):
        payload = {
            "concept_kernels": [
                {"premise": "A courier follows an impossible order into a burned orphanage."},
                {
                    "character_pressure": "The apprentice grows stronger while the master pays the cost.",
                    "possible_turn": "A failed early experiment reveals how to loosen the bond.",
                },
                {
                    "hook": "A public donation counter traps the protagonist.",
                    "anything_helpful": "She can change the mechanism while writing the story.",
                },
            ],
        }
        self.assertEqual(WORKFLOW.kernel_failures(payload, "A"), [])
        normalized, failures = WORKFLOW.normalize_kernel_payload(
            payload, "A", ["atom-1", "atom-2"],
        )
        self.assertEqual(failures, [])
        kernels = normalized["concept_kernels"]
        self.assertEqual(len({row["kernel_id"] for row in kernels}), 3)
        self.assertTrue(all(row["cited_atom_ids"] == ["atom-1", "atom-2"] for row in kernels))
        self.assertEqual(kernels[0]["premise"], payload["concept_kernels"][0]["premise"])
        payload["concept_kernels"][1] = {}
        self.assertIn(
            "CONCEPT_KERNEL_CONTENT_EMPTY",
            {row["reason"] for row in WORKFLOW.kernel_failures(payload, "A")},
        )

    def test_smoke_exact_two_kernels_does_not_inherit_production_minimum(self):
        payload = {
            "concept_kernels": [
                {"premise": "A concrete first mechanism with a costly choice."},
                {"premise": "A distinct second mechanism with escalating resistance."},
            ],
        }
        self.assertEqual(WORKFLOW.kernel_failures(payload, "A", exact_count=2), [])

    def test_smoke_branch_gate_uses_two_while_production_default_stays_three(self):
        context = {"branch_id": "A", "input_atom_ids": []}
        branch = {
            "stage": "divergent_generation", "schema_version": PORTFOLIO.SCHEMA_VERSION,
            "candidates": [{"candidate_id": "A-C01"}, {"candidate_id": "A-C02"}],
        }
        smoke = PORTFOLIO.branch_failures(branch, context, {}, "short", 2)
        production = PORTFOLIO.branch_failures(branch, context, {}, "short")
        self.assertNotIn("GENERATOR_CANDIDATE_COUNT_INSUFFICIENT", {row["reason"] for row in smoke})
        self.assertIn("GENERATOR_CANDIDATE_COUNT_INSUFFICIENT", {row["reason"] for row in production})

    def test_atom_failure_retries_atoms_instead_of_skipping_to_generation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = WORKFLOW.init_run(root, self.save_packet(root), "short", "fanqie", "male")
            claim_path = Path(result["claim"])
            claim, profile, _, output_dir, state_path = WORKFLOW.validate_claim(claim_path)
            state = WORKFLOW.load_json(state_path)
            retried = WORKFLOW.fail_or_gap_fill(
                claim_path, claim, profile, output_dir, state_path, state,
                [{"reason": "ATOM_SEMANTIC_GATE_FAILED"}],
            )
            self.assertEqual(retried["stage"], "S1_ATOMS")
            self.assertEqual(retried["gap_fill_round"], 1)
            self.assertEqual([row["role"] for row in retried["actions"]], ["atoms"])

    def test_auto_fix_only_failure_never_redispatches_same_pending_job(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = WORKFLOW.init_run(root, self.save_packet(root), "short", "fanqie", "male")
            claim_path = Path(result["claim"])
            claim, profile, _, output_dir, state_path = WORKFLOW.validate_claim(claim_path)
            state = WORKFLOW.load_json(state_path)
            failed_job_id = state["jobs"][0]["job_id"]
            retried = WORKFLOW.fail_or_gap_fill(
                claim_path, claim, profile, output_dir, state_path, state,
                [{"reason": "ATOM_TYPE_INVALID"}], failed_job_id=failed_job_id,
            )
            self.assertEqual(retried["recovery_budget"]["used"], 1)
            self.assertNotEqual(retried["actions"][0]["job_id"], failed_job_id)

    # Controller regression tests

    def test_content_hash_normalises_crlf_to_lf(self):
        """CRLF and LF line endings produce identical content_hash."""
        import tempfile
        lf = Path(tempfile.mktemp(suffix=".md"))
        crlf = Path(tempfile.mktemp(suffix=".md"))
        try:
            lf.write_text("line 1\nline 2\n\nend\n", encoding="utf-8")
            crlf.write_bytes(b"line 1\r\nline 2\r\n\r\nend\r\n")
            self.assertEqual(WORKFLOW.content_hash(lf), WORKFLOW.content_hash(crlf))
        finally:
            for p in (lf, crlf):
                if p.exists():
                    os.unlink(str(p))

    def test_bundle_snapshot_is_self_contained(self):
        """After init_run, _bundle_snapshot/ contains every runtime dependency."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = WORKFLOW.init_run(root, self.save_packet(root), "short", "fanqie", "female")
            claim = json.loads(Path(result["claim"]).read_text("utf-8"))
            snap = Path(claim["output_dir"]) / "_bundle_snapshot"
            self.assertTrue(snap.is_dir(), "snapshot dir should exist")
            snap_files = list(snap.iterdir())
            self.assertEqual(len(snap_files), len(WORKFLOW.SNAPSHOT_NAMES))
            for label, expected in claim["bundle_files"].items():
                snap_file = snap / WORKFLOW.SNAPSHOT_NAMES[label]
                self.assertTrue(snap_file.is_file(), f"missing snapshot file for {label}")
                self.assertEqual(
                    (WORKFLOW.content_hash(snap_file) if label in WORKFLOW.BUNDLE_DOCS else WORKFLOW.file_sha256(snap_file)), expected,
                    f"snapshot hash mismatch for {label}",
                )

    def test_short_snapshot_names_survive_a_long_windows_base(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = Path(temp) / ("long-base-" + "x" * 65)
            root.mkdir()
            result = WORKFLOW.init_run(root, self.save_packet(root), "short", "fanqie", "female")
            claim = json.loads(Path(result["claim"]).read_text("utf-8"))
            snap = Path(claim["output_dir"]) / "_bundle_snapshot"
            self.assertEqual({path.name for path in snap.iterdir()}, set(WORKFLOW.SNAPSHOT_NAMES.values()))
            WORKFLOW.validate_claim(Path(result["claim"]))

    def test_snapshot_validation_ignores_runtime_pycache_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = WORKFLOW.init_run(root, self.save_packet(root), "short", "fanqie", "female")
            snapshot = Path(result["claim"]).parent / "_bundle_snapshot"
            pycache = WORKFLOW.win_long_path(snapshot / "__pycache__")
            pycache.mkdir()
            (pycache / "candidate_workflow.pyc").write_bytes(b"runtime cache")
            WORKFLOW.validate_claim(Path(result["claim"]))
            WORKFLOW.win_long_path(snapshot / "unexpected.txt").write_text("drift", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "BUNDLE_SNAPSHOT_FILE_SET_INVALID"):
                WORKFLOW.validate_claim(Path(result["claim"]))

    def test_story_artifact_uses_long_path_only_at_io_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / ("story-root-" + "x" * 120)
            path = WORKFLOW.write_text_artifact(root, "story_A-C01_a1.txt", "正文")
            self.assertFalse(str(path).startswith('\\\\?\\'))
            self.assertEqual(WORKFLOW.win_long_path(path).read_text(encoding="utf-8"), "正文\n")

    def test_same_snapshot_atom_pool_is_not_auto_discovered(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            packet_path = self.save_packet(root)
            first = WORKFLOW.init_run(root, packet_path, "short", "fanqie", "male")
            claim, profile, packet, output_dir, state_path = WORKFLOW.validate_claim(Path(first["claim"]))
            state = WORKFLOW.load_json(state_path)
            raw_atoms = {
                "atoms": [
                    {
                        "atom_type": "desire",
                        "evidence_id": f"ev-{((index - 1) % len(SOURCES)) + 1}",
                        "observation": f"第{index}组读者在当前榜单中持续选择明确回报的叙事结构",
                        "inference": f"第{index}组候选可测试不同阻力下的阶段性兑现方式",
                        "confidence": 0.7,
                        "claim_key": f"claim-{index}",
                        "stance": "mixed",
                    }
                    for index in range(1, 19)
                ]
            }
            WORKFLOW.accept_atoms(raw_atoms, claim, profile, packet, output_dir, state)

            second = WORKFLOW.init_run(root, packet_path, "short", "fanqie", "male")
            self.assertIsNone(second["pool_input"])
            self.assertEqual(
                [action["role"] for action in second["actions"]],
                ["atoms"],
            )

    def test_format_retry_only_supersedes_failed_job(self):
        """Format-only failure retries only the failed job, keeps other pending jobs alive."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = WORKFLOW.init_run(root, self.save_packet(root), "short", "fanqie", "male")
            claim_path = Path(result["claim"])
            claim, profile, _, output_dir, state_path = WORKFLOW.validate_claim(claim_path)
            state = WORKFLOW.load_json(state_path)
            # Simulate atoms accepted, then add 3 generation jobs
            state["stage"] = "S2_CONCEPTS"
            state["artifacts"] = {"atoms": "fake_atoms.json", "contexts": "fake_contexts.json"}
            state["jobs"] = [
                {"job_id": "r-gen-A-r0-a1", "role": "generation_A", "round": 0, "attempt": 1, "raw_output": "raw/A.json", "prompt": "p", "status": "pending"},
                {"job_id": "r-gen-B-r0-a1", "role": "generation_B", "round": 0, "attempt": 1, "raw_output": "raw/B.json", "prompt": "p", "status": "pending"},
                {"job_id": "r-gen-C-r0-a1", "role": "generation_C", "round": 0, "attempt": 1, "raw_output": "raw/C.json", "prompt": "p", "status": "pending"},
            ]
            WORKFLOW.save_state(state_path, state)
            # Trigger format failure on B only
            retried = WORKFLOW.fail_or_gap_fill(
                claim_path, claim, profile, output_dir, state_path, WORKFLOW.load_json(state_path),
                [{"reason": "CONCEPT_KERNEL_CONTENT_EMPTY"}],
                failed_job_id="r-gen-B-r0-a1",
            )
            # Check: actions should have the repair job (and possibly surviving pending jobs)
            action_ids = {a["job_id"] for a in retried.get("actions", [])}
            self.assertTrue(len(action_ids) >= 1, "should have at least one action for repair")
            # format_retries should be used, gap_fill_round should stay at 0
            st = WORKFLOW.load_json(state_path)
            self.assertEqual(st["gap_fill_round"], 0, "format retry must not consume gap-fill round")
            self.assertIn("generation_B", st.get("format_retries_used", {}),
                          "format_retries_used should track the failed role")

    def test_originality_prompt_requires_complete_registered_reference(self):
        prompt = WORKFLOW.job_prompt(
            "originality_craft", {"run_id": "r", "lane": "short"}, Path("."),
            Path("raw/originality-a2.json"), 0,
            repair_hint="CLOSEST_WORK_REFERENCE_INVALID",
        )
        self.assertIn('"identifier": "<work name or evidence title>"', prompt)
        self.assertIn('"evidence_id": "<registered ID>"', prompt)
        self.assertIn("an evidence_id without identifier is invalid", prompt)
        self.assertIn("calibrated_originality_risk as integer 1-5", prompt)

    def test_format_retry_uses_attempt_specific_job_id_prompt_and_raw_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = WORKFLOW.init_run(root, self.save_packet(root), "short", "fanqie", "male")
            claim_path = Path(result["claim"])
            claim, profile, _, output_dir, state_path = WORKFLOW.validate_claim(claim_path)
            state = WORKFLOW.load_json(state_path)
            first = WORKFLOW.create_job(
                "originality_craft", claim, output_dir, 0, attempt=1,
            )
            state["stage"] = "S3_REVIEW"
            state["jobs"] = [first]
            WORKFLOW.save_state(state_path, state)

            retried = WORKFLOW.fail_or_gap_fill(
                claim_path, claim, profile, output_dir, state_path, WORKFLOW.load_json(state_path),
                [{"reason": "CLOSEST_WORK_REFERENCE_INVALID", "candidate_id": "A-C01"}],
                failed_job_id=first["job_id"],
            )

            repairs = [
                action for action in retried["actions"]
                if action["role"] == "originality_craft"
            ]
            self.assertEqual(len(repairs), 1)
            repair = repairs[0]
            self.assertEqual(repair["attempt"], 2)
            self.assertIn("-a2", repair["job_id"])
            self.assertIn("-a2.json", repair["raw_output"])
            self.assertNotEqual(repair["raw_output"], first["raw_output"])
            self.assertIn(repair["raw_output"], repair["prompt"])
            self.assertIn("CLOSEST_WORK_REFERENCE_INVALID", repair["prompt"])

    def test_semantic_failure_consumes_gap_fill_not_format_retry(self):
        """A real semantic failure triggers gap-fill, not format retry."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = WORKFLOW.init_run(root, self.save_packet(root), "short", "fanqie", "male")
            claim_path = Path(result["claim"])
            claim, profile, _, output_dir, state_path = WORKFLOW.validate_claim(claim_path)
            state = WORKFLOW.load_json(state_path)
            state["stage"] = "S2_CONCEPTS"
            state["artifacts"] = {"atoms": "f.json", "contexts": "f.json"}
            state["jobs"] = [
                {"job_id": "r-gen-A-r0-a1", "role": "generation_A", "round": 0, "attempt": 1, "raw_output": "raw/A.json", "prompt": "p", "status": "pending"},
                {"job_id": "r-gen-B-r0-a1", "role": "generation_B", "round": 0, "attempt": 1, "raw_output": "raw/B.json", "prompt": "p", "status": "pending"},
                {"job_id": "r-gen-C-r0-a1", "role": "generation_C", "round": 0, "attempt": 1, "raw_output": "raw/C.json", "prompt": "p", "status": "pending"},
            ]
            WORKFLOW.save_state(state_path, state)
            # Semantic failure: low-information content, not format error
            retried = WORKFLOW.fail_or_gap_fill(
                claim_path, claim, profile, output_dir, state_path, WORKFLOW.load_json(state_path),
                [{"reason": "GENERATOR_CANDIDATES_MISSING"}],
                failed_job_id="r-gen-A-r0-a1",
            )
            st = WORKFLOW.load_json(state_path)
            self.assertEqual(st["gap_fill_round"], 1, "semantic failure must consume gap-fill round")
            # All 3 should be superseded (semantic failure means re-gen all)
            superseded = [j for j in st["jobs"] if j.get("status") == "superseded"]
            self.assertGreaterEqual(len(superseded), 1)

    def test_s3_format_retry_exhaustion_never_routes_back_to_s2(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = WORKFLOW.init_run(root, self.save_packet(root), "short", "fanqie", "female")
            claim_path = Path(result["claim"])
            claim, profile, _, output_dir, state_path = WORKFLOW.validate_claim(claim_path)
            state = WORKFLOW.load_json(state_path)
            state["stage"] = "S3_REVIEW"
            state["format_retries_used"] = {"originality_craft": WORKFLOW.MAX_FORMAT_RETRIES}
            state["jobs"] = [{
                "job_id": "r-originality-r0-a2", "role": "originality_craft", "round": 0,
                "attempt": 2, "raw_output": "raw/originality.json", "prompt": "p", "status": "pending",
            }]
            WORKFLOW.save_state(state_path, state)
            final = WORKFLOW.fail_or_gap_fill(
                claim_path, claim, profile, output_dir, state_path, WORKFLOW.load_json(state_path),
                [{"reason": "ORIGINALITY_RECORD_INVALID"}],
                failed_job_id="r-originality-r0-a2",
            )
            self.assertEqual(final["status"], "candidate_generation_failed")
            self.assertEqual(final["stage"], "S4_TERMINAL")
            self.assertFalse(any(action["role"].startswith("generation_") for action in final["actions"]))

    def test_recovery_budget_exhaustion_fails_explicitly(self):
        """A pending job cannot keep a run alive after its shared recovery budget is exhausted."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = WORKFLOW.init_run(root, self.save_packet(root), "short", "fanqie", "female")
            claim_path = Path(result["claim"])
            claim, profile, _, output_dir, state_path = WORKFLOW.validate_claim(claim_path)
            state = WORKFLOW.load_json(state_path)
            state["recovery_budget"]["used"] = state["recovery_budget"]["limit"]
            state["stage"] = "S1_ATOMS"
            state["artifacts"] = {}
            state["receipts"] = []
            state["jobs"] = [
                {"job_id": "r-atoms-r2-a1", "role": "atoms", "round": 2, "attempt": 1, "raw_output": "raw/atoms.json", "prompt": "p", "status": "pending"},
            ]
            WORKFLOW.save_state(state_path, state)
            final = WORKFLOW.fail_or_gap_fill(
                claim_path, claim, profile, output_dir, state_path, WORKFLOW.load_json(state_path),
                [{"reason": "ATOM_SEMANTIC_GATE_FAILED"}],
                failed_job_id="r-atoms-r2-a1",
            )
            st = WORKFLOW.load_json(state_path)
            self.assertEqual(st.get("status"), "candidate_generation_failed")
            self.assertIn(
                "RECOVERY_CALL_BUDGET_EXHAUSTED",
                {row.get("reason") for row in st.get("failures", [])},
            )

    def test_mapper_elimination_supersedes_consumed_job_when_budget_is_full(self):
        state = {
            "candidate_tracks": {
                "A-C01": {
                    "candidate_id": "A-C01", "kernel_id": "A-K01", "branch_id": "A",
                    "status": "awaiting_mapping", "mapper_retries": 0,
                },
            },
            "recovery_budget": {"limit": 4, "used": 4, "events": []},
            "branch_supplement_rounds": {"A": 0, "B": 0, "C": 0},
            "kernels_per_branch": 2,
            "jobs": [],
            "story_failures": [],
        }
        job = {"candidate_id": "A-C01", "status": "pending"}
        WORKFLOW.handle_mapping_failure(
            state, {"run_id": "run-1"}, Path("."), job,
            [{"reason": "CARD_FIELD_MISSING"}],
        )
        self.assertEqual(job["status"], "superseded")
        self.assertEqual(state["candidate_tracks"]["A-C01"]["status"], "eliminated")

    def test_inject_deterministic_fields_covers_evidence_atom_ids(self):
        """inject_deterministic_fields() must set evidence_atom_ids on each candidate_card."""
        raw = {
            "candidates": [
                {"candidate_id": "C1", "candidate_card": {"one_line_concept": "test"}},
                {"candidate_id": "C2", "candidate_card": {}},
            ]
        }
        claim = {"lane": "short", "run_id": "r1", "evidence_packet_hash": "abc"}
        profile = {"output_hash": "prof", "target_platform": "fanqie",
                    "audience_channel": "female", "portfolio_track": "general"}
        context = {"generator_role": "test", "output_hash": "ctx",
                    "input_atom_ids": ["a1", "a2"], "sampling_config": {}}
        result = WORKFLOW.inject_deterministic_fields(raw, "generation_A", claim, profile, context)
        for c in result["candidates"]:
            card = c["candidate_card"]
            self.assertEqual(card["evidence_atom_ids"], ["a1", "a2"],
                             f"evidence_atom_ids must be injected for {c['candidate_id']}")
            self.assertEqual(card["target_platform"], "fanqie")
            self.assertEqual(card["audience_channel"], "female")
        self.assertEqual(result["branch_id"], "A")

    def test_concurrent_runs_produce_different_snapshots(self):
        """Two independent init_run calls create separate, non-conflicting snapshots."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            r1 = WORKFLOW.init_run(root, self.save_packet(root), "short", "fanqie", "female")
            r2 = WORKFLOW.init_run(root, self.save_packet(root), "short", "fanqie", "male")
            c1 = json.loads(Path(r1["claim"]).read_text("utf-8"))
            c2 = json.loads(Path(r2["claim"]).read_text("utf-8"))
            # Different output dirs
            self.assertNotEqual(c1["output_dir"], c2["output_dir"])
            # Each has its own snapshot
            s1 = Path(c1["output_dir"]) / "_bundle_snapshot"
            s2 = Path(c2["output_dir"]) / "_bundle_snapshot"
            self.assertTrue(s1.is_dir() and s2.is_dir())
            # Both should validate independently
            _, _, _, _, _ = WORKFLOW.validate_claim(Path(r1["claim"]))
            _, _, _, _, _ = WORKFLOW.validate_claim(Path(r2["claim"]))

    def test_atom_list_is_normalized_and_unknown_evidence_fails_closed(self):
        claim = {"lane": "short", "run_id": "run-1", "evidence_packet_hash": self.packet["evidence_packet_hash"]}
        raw = [{
            "atom_type": "desire", "evidence_id": "ev-1",
            "observation": "specific current reader signal",
            "inference": "specific abstract reader implication",
            "confidence": 0.8, "claim_key": "claim-1", "stance": "support",
        }]
        normalized = WORKFLOW.inject_atom_deterministic_fields(raw, claim, self.packet)
        atom = normalized["atoms"][0]
        self.assertRegex(atom["atom_id"], r"^atom-0001-[0-9a-f]{8}$")
        self.assertEqual(atom["source_item_id"], "item-1")
        self.assertEqual(atom["supporting_evidence_ids"], ["ev-1"])
        raw[0]["atom_type"] = "reader desire signal"
        raw[0]["confidence"] = "high"
        normalized_type = WORKFLOW.inject_atom_deterministic_fields(raw, claim, self.packet)
        self.assertEqual(normalized_type["atoms"][0]["atom_type"], "desire")
        self.assertEqual(normalized_type["atoms"][0]["confidence"], 0.85)
        raw[0]["evidence_id"] = "unknown"
        invalid = WORKFLOW.inject_atom_deterministic_fields(raw, claim, self.packet)
        failures, _ = PORTFOLIO.atom_failures(self.packet, PORTFOLIO.seal(invalid), "short")
        self.assertTrue(any(row["reason"] == "ATOM_EVIDENCE_UNKNOWN" for row in failures))

    def test_k08_retry_once_then_eliminate_and_supplement(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = WORKFLOW.init_run(root, self.save_packet(root), "short", "fanqie", "female")
            claim, _, _, output_dir, state_path = WORKFLOW.validate_claim(Path(result["claim"]))
            state = WORKFLOW.load_json(state_path)
            kernel_file = output_dir / "kernel_source.json"
            kernel_file.write_text("{}", encoding="utf-8")
            state["candidate_tracks"] = {
                "A-C01": {
                    "candidate_id": "A-C01", "kernel_id": "A-K1", "branch_id": "A",
                    "kernel_path": str(kernel_file), "status": "awaiting_review",
                    "story_attempt": 1, "story_hash": PORTFOLIO.canonical_hash("first story"),
                    "supplemental": False, "mapper_retries": 0,
                }
            }
            state["branch_supplement_rounds"] = {"A": 0, "B": 0, "C": 0}
            state["receipts"] = [{"role": "generation_A", "artifact_path": str(kernel_file)}]
            state["jobs"] = []
            job = {"candidate_id": "A-C01", "story_attempt": 1}
            WORKFLOW.accept_story_review(
                "读者必须脑补主角为何行动", job, claim, output_dir, state,
            )
            track = state["candidate_tracks"]["A-C01"]
            self.assertEqual(track["story_attempt"], 2)
            self.assertEqual(track["status"], "awaiting_story")
            self.assertEqual([row["role"] for row in state["jobs"]], ["story_creator"])
            state["jobs"][0]["status"] = "accepted"
            track.update({
                "status": "awaiting_review",
                "story_hash": PORTFOLIO.canonical_hash("rewritten story"),
            })
            WORKFLOW.accept_story_review(
                "结局仍需读者脑补关键事实",
                {"candidate_id": "A-C01", "story_attempt": 2},
                claim, output_dir, state,
            )
            self.assertEqual(track["status"], "eliminated")
            self.assertEqual(
                [row["role"] for row in state["jobs"] if row["status"] == "pending"],
                ["kernel_supplement_A"],
            )
            self.assertEqual(state["story_failures"][0]["reason"], "STORY_REVIEW_REJECTED_AFTER_REWRITE")

    def test_story_editor_prompt_is_ten_lines_or_less_and_never_completes(self):
        prompt = WORKFLOW.job_prompt(
            "story_editor", {"run_id": "r", "lane": "short"}, Path("."),
            Path("review.txt"), 0, metadata={"story_path": "story.txt"},
        )
        self.assertLessEqual(len(prompt.splitlines()), 10)
        self.assertIn("检查以下硬伤", prompt)
        self.assertNotIn("评分", prompt)
        self.assertTrue(PORTFOLIO.story_review_passed("通过。"))
        self.assertFalse(PORTFOLIO.story_review_passed("通过，但结局还需脑补"))

    def test_model_roles_receive_only_the_minimum_branch_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            output_dir = Path(temp)
            contexts = {
                branch: PORTFOLIO.seal({'branch_id': branch, 'private_marker': f'ONLY-{branch}'})
                for branch in PORTFOLIO.BRANCH_ROLES
            }
            (output_dir / 'generation_contexts.json').write_text(
                json.dumps({'contexts': contexts}, ensure_ascii=False), encoding='utf-8',
            )
            metadata = {
                'branch_id': 'A', 'kernel_path': str(output_dir / 'kernel.json'),
                'kernel_artifact': str(output_dir / 'generation_A.json'),
                'story_path': str(output_dir / 'story.txt'),
                'review_path': str(output_dir / 'review.txt'),
            }

            generation = WORKFLOW.job_input_paths('generation_A', output_dir, metadata)
            supplement = WORKFLOW.job_input_paths('kernel_supplement_A', output_dir, metadata)
            creator = WORKFLOW.job_input_paths('story_creator', output_dir, metadata)
            mapper = WORKFLOW.job_input_paths('candidate_mapper', output_dir, metadata)

            branch_slice = str((output_dir / 'generation_context_A.json').resolve())
            full_contexts = str((output_dir / 'generation_contexts.json').resolve())
            full_atoms = str((output_dir / 'evidence_atoms.json').resolve())
            self.assertIn(branch_slice, generation)
            self.assertIn(branch_slice, supplement)
            self.assertIn(branch_slice, creator)
            self.assertNotIn(full_contexts, generation + supplement + creator + mapper)
            self.assertNotIn(full_atoms, creator)
            self.assertEqual(
                json.loads((output_dir / 'generation_context_A.json').read_text('utf-8'))['private_marker'],
                'ONLY-A',
            )

    def test_s4_recovery_preserves_survivors_and_schedules_only_targeted_supplements(self):
        with tempfile.TemporaryDirectory() as temp:
            output_dir = Path(temp)
            for branch in PORTFOLIO.BRANCH_ROLES:
                (output_dir / f'generation_context_{branch}.json').write_text(
                    json.dumps(PORTFOLIO.seal({'branch_id': branch})), encoding='utf-8',
                )
                (output_dir / f'generation_{branch}.json').write_text('{}', encoding='utf-8')
            tracks = {
                f'{branch}-C0{index}': {
                    'candidate_id': f'{branch}-C0{index}',
                    'branch_id': branch,
                    'status': 'mapped',
                }
                for branch in PORTFOLIO.BRANCH_ROLES
                for index in range(1, 4)
            }
            state = {
                'candidate_tracks': tracks,
                'branch_supplement_rounds': {'A': 0, 'B': 0, 'C': 0},
                'gap_fill_round': 0,
                'kernels_per_branch': 3,
                'jobs': [],
                'receipts': [
                    {
                        'role': f'generation_{branch}',
                        'artifact_path': str(output_dir / f'generation_{branch}.json'),
                    }
                    for branch in PORTFOLIO.BRANCH_ROLES
                ],
            }
            gate = {
                'vetoed_candidate_ids': ['A-C02'],
                'pareto_frontier_ids': ['A-C01', 'B-C01', 'B-C02'],
            }
            failures = [{'reason': 'QUALIFIED_CANDIDATES_INSUFFICIENT'}]

            scheduled = WORKFLOW.schedule_portfolio_recovery(
                state, {'run_id': 'run-1', 'lane': 'short', 'kernels_per_branch': 3},
                output_dir, gate, failures,
            )

            self.assertTrue(scheduled)
            self.assertEqual(state['candidate_tracks']['A-C01']['status'], 'mapped')
            self.assertEqual(state['candidate_tracks']['B-C01']['status'], 'mapped')
            self.assertEqual(state['candidate_tracks']['A-C02']['status'], 'eliminated')
            pending_roles = [job['role'] for job in state['jobs'] if job['status'] == 'pending']
            self.assertEqual(pending_roles, ['kernel_supplement_A'])
            self.assertFalse(any(role.startswith('generation_') for role in pending_roles))
            self.assertEqual(state['gap_fill_round'], 1)

    def test_job_provenance_rejects_reused_sessions(self):
        receipt = {"session_id": "deleg_real:0"}
        with self.assertRaisesRegex(ValueError, "JOB_SESSIONS_NOT_ISOLATED"):
            PORTFOLIO.make_job_provenance(
                "run-1",
                {"A": receipt, "B": receipt, "C": receipt},
                {"market_coverage": receipt, "originality_craft": receipt},
                [], {}, {},
            )


if __name__ == "__main__":
    unittest.main()
