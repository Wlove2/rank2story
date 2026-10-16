from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


FREEZE = load("freeze_evidence_packet")
RECOVERY = load("deliberation_recovery")


class DeliberationRecoveryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        packet = FREEZE.freeze(
            {"lane": "short", "sources": []},
            {"formal_candidate_generation": "allowed"},
            [{"id": "e1"}],
            {},
        )
        self.packet = self.root / "packet.json"
        self.packet.write_text(json.dumps(packet), encoding="utf-8")
        self.candidates = self.root / "candidates.json"
        self.candidates.write_text(json.dumps({
            "stage": "candidate_draft",
            "lane": "short",
            "generation_run_id": "gen-1",
            "evidence_packet_hash": packet["evidence_packet_hash"],
            "candidates": [{"candidate_id": "c1"}],
        }), encoding="utf-8")
        self.start = datetime(2026, 7, 19, 0, 0, tzinfo=timezone.utc)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def review(self, kind: str, delegation_id: str, task_index: int) -> dict:
        return {
            "reviewer_kind": kind,
            "delegation_id": delegation_id,
            "task_index": task_index,
        }

    def test_timeout_retries_once_on_same_frozen_inputs(self) -> None:
        state = RECOVERY.create_state(
            self.packet, self.candidates, "short", timeout_minutes=30, max_retries=1, now=self.start
        )
        RECOVERY.mark_dispatched(state, "deleg-1", now=self.start)
        pending = RECOVERY.status(state, [], now=self.start + timedelta(minutes=29))
        self.assertEqual(pending["status"], "pending")
        retry = RECOVERY.status(state, [], now=self.start + timedelta(minutes=31))
        self.assertEqual(retry["status"], "retry_required")
        RECOVERY.mark_dispatched(state, "deleg-2", now=self.start + timedelta(minutes=31))

        stale = [
            self.review("market_coverage", "deleg-1", 0),
            self.review("originality_craft", "deleg-1", 1),
        ]
        self.assertEqual(
            RECOVERY.status(state, stale, now=self.start + timedelta(minutes=32))["status"],
            "pending",
        )
        current = [
            self.review("market_coverage", "deleg-2", 0),
            self.review("originality_craft", "deleg-2", 1),
        ]
        ready = RECOVERY.status(state, current, now=self.start + timedelta(minutes=32))
        self.assertEqual(ready["status"], "ready_for_validation")
        self.assertEqual(ready["delegation_id"], "deleg-2")

    def test_second_timeout_fails_closed(self) -> None:
        state = RECOVERY.create_state(
            self.packet, self.candidates, "short", timeout_minutes=30, max_retries=1, now=self.start
        )
        RECOVERY.mark_dispatched(state, "deleg-1", now=self.start)
        RECOVERY.status(state, [], now=self.start + timedelta(minutes=31))
        RECOVERY.mark_dispatched(state, "deleg-2", now=self.start + timedelta(minutes=31))
        result = RECOVERY.status(state, [], now=self.start + timedelta(minutes=62))
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "DELIBERATION_CALLBACK_TIMEOUT_EXHAUSTED")

    def test_v2_cluster_checkpoint_resumes_at_portfolio_assemble(self) -> None:
        packet = json.loads(self.packet.read_text(encoding="utf-8"))
        clustered = self.root / "clustered.json"
        clustered.write_text(json.dumps({
            "stage": "clustered_representatives",
            "status": "representatives_ready",
            "schema_version": 2,
            "lane": "short",
            "run_id": "run-v2",
            "evidence_packet_hash": packet["evidence_packet_hash"],
            "representatives": [{"candidate_id": "c1"}],
        }), encoding="utf-8")
        state = RECOVERY.create_state(self.packet, clustered, "short", now=self.start)
        self.assertEqual(state["candidate_stage"], "clustered_representatives")
        RECOVERY.mark_dispatched(state, "review-v2", now=self.start)
        result = RECOVERY.status(state, [
            self.review("market_coverage", "review-v2", 0),
            self.review("originality_craft", "review-v2", 1),
        ], now=self.start + timedelta(minutes=1))
        self.assertEqual(result["status"], "ready_for_validation")
        self.assertEqual(result["next_action"], "run_candidate_portfolio_assemble")
    def test_frozen_input_mutation_is_detected(self) -> None:
        state = RECOVERY.create_state(self.packet, self.candidates, "short", now=self.start)
        self.candidates.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "RECOVERY_CANDIDATES_FILE_MUTATED"):
            RECOVERY.mark_dispatched(state, "deleg-1", now=self.start)


if __name__ == "__main__":
    unittest.main()
