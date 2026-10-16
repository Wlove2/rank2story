"""Offline safety checks for operator-driven candidate continuation/restart."""
from __future__ import annotations
from pathlib import Path
from unittest import mock
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from examples import candidate_run_recovery as R


class CandidateRunRecoveryTests(unittest.TestCase):
    def test_candidate_quality_rejection_is_not_auto_labeled_system_failure(self):
        self.assertEqual(
            R.classify("candidate_generation_failed", [
                {"reason": "GENERATOR_CANDIDATES_MISSING", "branch_id": "A"},
                {"reason": "FINAL_BRANCH_COVERAGE_INSUFFICIENT", "missing": ["B"]},
            ]), "candidate_quality_or_coverage_not_met",
        )

    def test_unknown_rejection_needs_triage(self):
        self.assertEqual(
            R.classify("candidate_generation_failed", [{"reason": "SOME_NEW_UNCLASSIFIED_ERROR"}]),
            "needs_engineering_triage",
        )

    def test_known_technical_problem_needs_separate_verification(self):
        self.assertEqual(
            R.classify("candidate_generation_failed", [{"reason": "OUTPUT_WHITELIST_VIOLATION"}]),
            "possible_technical_failure",
        )

    def test_paused_and_running_are_not_treated_as_terminal(self):
        self.assertEqual(R.classify("paused", []), "in_progress_or_interrupted")
        self.assertEqual(R.classify("running", []), "in_progress_or_interrupted")
        self.assertEqual(R.classify("awaiting_user_choice", []), "candidate_ready_requires_verify")

    def test_restart_rejects_active_or_paused_parent_before_writing(self):
        for status in ("running", "paused", "awaiting_user_choice"):
            with self.subTest(status=status), mock.patch.object(
                R, "inspect_claim", return_value=(
                    {"status": status, "reusable_verified_atoms": True}, object(), object(),
                ),
            ):
                with self.assertRaisesRegex(ValueError, "RESTART_REQUIRES_TERMINAL_FAILED_CLAIM"):
                    R.restart_from_claim(
                        Path("hypothetical-parent.json"),
                        new_scripts=Path("hypothetical-controller"), base_root=Path("hypothetical-root"),
                        create=True,
                    )

    def test_restart_rejects_missing_or_invalid_evidence_atoms(self):
        with mock.patch.object(R, "inspect_claim", return_value=(
            {"status": "candidate_generation_failed", "reusable_verified_atoms": False},
            object(), object(),
        )):
            with self.assertRaisesRegex(ValueError, "RESTART_REQUIRES_VALIDATED_ATOM_BUNDLE"):
                R.restart_from_claim(
                    Path("hypothetical-parent.json"),
                    new_scripts=Path("hypothetical-controller"), base_root=Path("hypothetical-root"),
                )

    def test_engine_loader_supports_separately_selected_version_without_global_import_leak(self):
        one, _ = R.engine(R.DEFAULT_SCRIPTS)
        other, _ = R.engine(R.DEFAULT_SCRIPTS)
        self.assertEqual(Path(one.__file__).resolve(), (R.DEFAULT_SCRIPTS / "candidate_workflow.py").resolve())
        self.assertEqual(Path(other.__file__).resolve(), Path(one.__file__).resolve())


if __name__ == "__main__":
    unittest.main()
