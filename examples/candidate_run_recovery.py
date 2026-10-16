#!/usr/bin/env python3
"""Operator-safe candidate inspection and deliberate re-run from frozen evidence.

This does not rewrite a terminal run, silently retry, or call a model.
"resume" remains the existing candidate.py execute command for paused claims.
"restart --create" explicitly creates a fresh claim with validated S1 atoms.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from pathlib import Path
import sys
from typing import Any

REPO = Path(__file__).resolve().parents[1]
DEFAULT_SCRIPTS = REPO / "skills" / "novel-analyzer" / "scripts"
TECHNICAL_FAILURE_CODES = {
    "LLM_CALL_FUSE_REACHED", "EXECUTOR_NO_ACTIONS_FOR_NONTERMINAL_RUN",
    "BUNDLE_SNAPSHOT_CHANGED_DURING_RUN", "OUTPUT_WHITELIST_VIOLATION",
    "MODEL_HTTP_ERROR", "EVIDENCE_PACKET_HASH_MISMATCH",
}
CONTENT_FAILURE_CODES = {
    "GENERATOR_CANDIDATES_MISSING", "GENERATOR_CANDIDATE_COUNT_INSUFFICIENT",
    "BRANCH_REPRESENTATIVE_DIVERSITY_INSUFFICIENT",
    "FINAL_BRANCH_COVERAGE_INSUFFICIENT",
    "FINAL_STRATEGY_DIVERSITY_INSUFFICIENT",
    "FINAL_MECHANISM_DIVERSITY_INSUFFICIENT",
    "QUALIFIED_CANDIDATES_INSUFFICIENT",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def engine(scripts: Path) -> tuple[Any, Any]:
    """Load only the explicitly chosen controller. Never substitute parent state."""
    scripts = scripts.resolve()
    if not (scripts / "candidate_workflow.py").is_file():
        raise ValueError("CONTROLLER_SCRIPTS_MISSING")
    if not (scripts / "candidate_portfolio.py").is_file():
        raise ValueError("CONTROLLER_PORTFOLIO_MISSING")
    names = ("candidate_workflow", "candidate_portfolio")
    previous = {name: sys.modules.pop(name, None) for name in names}
    sys.path.insert(0, str(scripts))
    try:
        portfolio = importlib.import_module("candidate_portfolio")
        workflow = importlib.import_module("candidate_workflow")
        if Path(workflow.__file__).resolve() != (scripts / "candidate_workflow.py"):
            raise ValueError("MISMATCHED_LOADED_CONTROLLER")
        if Path(portfolio.__file__).resolve() != (scripts / "candidate_portfolio.py"):
            raise ValueError("MISMATCHED_LOADED_PORTFOLIO")
        return workflow, portfolio
    finally:
        sys.path.pop(0)
        for name in names:
            sys.modules.pop(name, None)
            if previous[name] is not None:
                sys.modules[name] = previous[name]


def classify(status: str, failures: list[dict[str, Any]]) -> str:
    if status == "awaiting_user_choice":
        return "candidate_ready_requires_verify"
    if status in {"running", "paused"}:
        return "in_progress_or_interrupted"
    if status != "candidate_generation_failed":
        return "unknown_state"
    codes = {str(row.get("reason") or "") for row in failures}
    if codes and codes <= CONTENT_FAILURE_CODES:
        return "candidate_quality_or_coverage_not_met"
    if codes & TECHNICAL_FAILURE_CODES:
        return "possible_technical_failure"
    return "needs_engineering_triage"


def inspect_claim(claim_file: Path, scripts: Path) -> tuple[dict[str, Any], Any, Any]:
    workflow, portfolio = engine(scripts)
    claim_file = claim_file.resolve()
    claim, profile, packet, out, statepath = workflow.validate_claim(claim_file)
    state = workflow.load_json(statepath)
    atom = out / "evidence_atoms.json"
    evidence_reusable = False
    atom_hash = None
    if atom.is_file():
        try:
            workflow.validate_pool_atom_bundle(packet, workflow.load_json(atom), claim["lane"])
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            pass
        else:
            evidence_reusable = True
            atom_hash = sha(atom)
    result = {
        "run_id": claim["run_id"],
        "claim": str(claim_file),
        "status": state["status"],
        "stage": state["stage"],
        "candidate_delivery": (
            "ready_unverified" if state["status"] == "awaiting_user_choice"
            else "not_delivered"
        ),
        "execution_outcome_class": classify(state["status"], state.get("failures") or []),
        "engineering_acceptance": "requires_separate_recovery_and_integrity_tests",
        "failures": state.get("failures") or [],
        "calls_started": (state.get("call_budget") or {}).get("calls_started", 0),
        "accepted_receipts": len(state.get("receipts") or []),
        "lease": state.get("executor_lease") or {},
        "reusable_verified_atoms": evidence_reusable,
        "atom_sha256": atom_hash,
        "claim_sha256": sha(claim_file),
        "state_sha256": sha(statepath),
        "evidence_packet_hash": claim["evidence_packet_hash"],
        "bundle_hash": claim["bundle_hash"],
        "next_action": (
            "verify_then_user_choice" if state["status"] == "awaiting_user_choice" else
            "inspect_active_lease_do_not_duplicate" if state["status"] == "running" else
            "execute_same_claim_to_resume" if state["status"] == "paused" else
            "create_new_claim_only_with_explicit_restart" if state["status"] == "candidate_generation_failed" else
            "manual_inspection"
        ),
    }
    return result, workflow, portfolio


def restart_from_claim(
    claim_file: Path,
    *,
    read_scripts: Path = DEFAULT_SCRIPTS,
    new_scripts: Path,
    base_root: Path,
    create: bool = False,
) -> dict[str, Any]:
    parent, old_engine, _ = inspect_claim(claim_file, read_scripts)
    if parent["status"] != "candidate_generation_failed":
        raise ValueError("RESTART_REQUIRES_TERMINAL_FAILED_CLAIM")
    if not parent["reusable_verified_atoms"]:
        raise ValueError("RESTART_REQUIRES_VALIDATED_ATOM_BUNDLE")
    chosen_workflow, chosen_portfolio = engine(new_scripts)
    old_claim, old_profile, packet, old_dir, old_state = old_engine.validate_claim(claim_file)
    old_atom_path = old_dir / "evidence_atoms.json"
    chosen_workflow.validate_pool_atom_bundle(
        packet, chosen_workflow.load_json(old_atom_path), old_claim["lane"],
    )
    new_profile = chosen_portfolio.make_profile(
        old_claim["lane"], "general", old_profile["target_platform"],
        old_profile["audience_channel"],
    )
    if new_profile["output_hash"] != old_claim["target_profile_hash"]:
        raise ValueError("TARGET_PROFILE_NOT_REPRODUCIBLE")
    original_claim_sha = sha(claim_file.resolve())
    original_state_sha = sha(old_state)
    selected_controller_sha = sha(new_scripts.resolve() / "candidate_workflow.py")
    report = {
        "action": "create_new_claim_from_validated_atoms",
        "mode": "create" if create else "dry_run",
        "parent_claim": str(claim_file.resolve()),
        "parent_claim_sha256": original_claim_sha,
        "parent_terminal_state_sha256": original_state_sha,
        "parent_business_failures": parent["failures"],
        "new_base_root": str(base_root.resolve()),
        "selected_controller_script": str((new_scripts / "candidate_workflow.py").resolve()),
        "selected_controller_sha256": selected_controller_sha,
        "evidence_packet_hash": old_claim["evidence_packet_hash"],
        "reused_atom_sha256": parent["atom_sha256"],
        "historical_calls_replayed": 0,
        "model_calls_started_by_this_command": 0,
        "historical_receipts_claimed_by_new_run": 0,
        "automatic_execution": False,
    }
    if not create:
        return report

    # The operator explicitly chose the output base and versioned source. The
    # existing sealed engine creates a UNIQUE new claim. No old terminal writes.
    base_root = base_root.resolve()
    base_root.mkdir(parents=True, exist_ok=True)
    new_state = chosen_workflow.init_run(
        base_root,
        old_dir / "evidence_packet.json",
        old_claim["lane"],
        old_profile["target_platform"],
        old_profile["audience_channel"],
        old_claim["execution_profile"],
        atom_bundle_path=old_atom_path,
    )
    if new_state["stage"] != "S2_KERNELS" or new_state["status"] != "paused":
        raise ValueError("NEW_CLAIM_NOT_PAUSED_AT_S2")
    fresh_claim = Path(new_state["claim"])
    if fresh_claim.resolve() == claim_file.resolve():
        raise ValueError("RESTART_REUSED_PARENT_CLAIM")
    child, _, _, _, statepath = chosen_workflow.validate_claim(fresh_claim)
    if child["evidence_packet_hash"] != old_claim["evidence_packet_hash"]:
        raise ValueError("CHILD_PACKET_HASH_CHANGED")
    if sha(old_state) != original_state_sha or sha(claim_file) != original_claim_sha:
        raise ValueError("PARENT_CHANGED_DURING_RESTART")
    report["new_claim"] = str(fresh_claim)
    report["new_claim_sha256"] = sha(fresh_claim)
    report["new_bundle_hash"] = child["bundle_hash"]
    report["new_run_id"] = child["run_id"]
    report["new_status"] = new_state["status"]
    report["new_stage"] = new_state["stage"]
    report["new_calls_started"] = new_state["call_budget"]["calls_started"]
    report["new_accepted_controller_receipts"] = 0
    lineage_dir = base_root / "candidate_restarts"
    lineage_dir.mkdir(exist_ok=True)
    lineage_file = lineage_dir / f"{child['run_id']}.json"
    with lineage_file.open("x", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")
    report["lineage_file"] = str(lineage_file)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect or explicitly restart a candidate run, without model calls")
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--claim", required=True, type=Path)
    inspect.add_argument("--read-scripts", type=Path, default=DEFAULT_SCRIPTS)
    restart = sub.add_parser("restart")
    restart.add_argument("--claim", required=True, type=Path)
    restart.add_argument("--read-scripts", type=Path, default=DEFAULT_SCRIPTS)
    restart.add_argument("--new-scripts", required=True, type=Path)
    restart.add_argument("--base-root", required=True, type=Path)
    restart.add_argument("--create", action="store_true", help="Explicit opt-in; absent means dry-run only")
    args = parser.parse_args()
    try:
        if args.command == "inspect":
            result, _, _ = inspect_claim(args.claim, args.read_scripts)
        else:
            result = restart_from_claim(
                args.claim, read_scripts=args.read_scripts,
                new_scripts=args.new_scripts, base_root=args.base_root,
                create=args.create,
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "blocked", "reason": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
