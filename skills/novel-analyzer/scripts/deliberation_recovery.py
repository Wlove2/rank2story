#!/usr/bin/env python3
"""Persist and recover the two-reviewer deliberation dispatch contract.

This script does not pretend to be a background scheduler.  It gives the
interactive caller a durable receipt: on every callback or resumed turn
it can determine whether to keep waiting, re-dispatch once against the same
frozen inputs, validate the current callbacks, or fail closed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from freeze_evidence_packet import validate_packet


SCHEMA_VERSION = 1
REVIEWER_KINDS = {"market_coverage", "originality_craft"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def sha_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def create_state(
    packet_path: Path,
    candidates_path: Path,
    lane: str,
    *,
    timeout_minutes: int = 30,
    max_retries: int = 1,
    now: datetime | None = None,
) -> dict[str, Any]:
    if timeout_minutes < 1:
        raise ValueError("timeout_minutes must be >= 1")
    if max_retries < 0:
        raise ValueError("max_retries must be >= 0")
    packet_hash = validate_packet(load_json(packet_path), lane)
    candidates = load_json(candidates_path)
    stage = candidates.get("stage")
    if stage not in {"candidate_draft", "clustered_representatives"} or candidates.get("lane") != lane:
        raise ValueError("candidate artifact stage/lane mismatch")
    if stage == "clustered_representatives" and candidates.get("status") != "representatives_ready":
        raise ValueError("clustered representative artifact is not ready")
    if candidates.get("evidence_packet_hash") != packet_hash:
        raise ValueError("candidate artifact packet hash mismatch")
    timestamp = now or utc_now()
    return {
        "schema_version": SCHEMA_VERSION,
        "lane": lane,
        "packet_path": str(packet_path.resolve()),
        "packet_file_sha256": sha_file(packet_path),
        "evidence_packet_hash": packet_hash,
        "candidates_path": str(candidates_path.resolve()),
        "candidates_file_sha256": sha_file(candidates_path),
        "generation_run_id": candidates.get("generation_run_id") or candidates.get("run_id"),
        "candidate_stage": stage,
        "timeout_minutes": timeout_minutes,
        "max_retries": max_retries,
        "status": "dispatch_required",
        "created_at": iso(timestamp),
        "attempts": [],
    }


def assert_bindings(state: dict[str, Any]) -> None:
    if state.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported recovery state schema")
    packet_path = Path(state["packet_path"])
    candidates_path = Path(state["candidates_path"])
    if sha_file(packet_path) != state.get("packet_file_sha256"):
        raise ValueError("RECOVERY_PACKET_FILE_MUTATED")
    if sha_file(candidates_path) != state.get("candidates_file_sha256"):
        raise ValueError("RECOVERY_CANDIDATES_FILE_MUTATED")
    if validate_packet(load_json(packet_path), state.get("lane")) != state.get("evidence_packet_hash"):
        raise ValueError("RECOVERY_PACKET_BINDING_INVALID")


def mark_dispatched(
    state: dict[str, Any],
    delegation_id: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    assert_bindings(state)
    if not delegation_id.strip():
        raise ValueError("delegation_id is required")
    attempts = state.setdefault("attempts", [])
    allowed_attempts = 1 + int(state.get("max_retries", 1))
    if len(attempts) >= allowed_attempts:
        raise ValueError("DELIBERATION_RETRY_LIMIT_EXHAUSTED")
    if attempts and state.get("status") != "retry_required":
        raise ValueError("current attempt is not eligible for redispatch")
    if any(item.get("delegation_id") == delegation_id for item in attempts):
        raise ValueError("delegation_id must be unique per attempt")
    timestamp = now or utc_now()
    attempt = {
        "attempt": len(attempts) + 1,
        "delegation_id": delegation_id,
        "dispatched_at": iso(timestamp),
        "deadline_at": iso(timestamp + timedelta(minutes=int(state["timeout_minutes"]))),
    }
    attempts.append(attempt)
    state["status"] = "pending"
    state["current_delegation_id"] = delegation_id
    return state


def review_map(review_payloads: list[dict[str, Any]], delegation_id: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for review in review_payloads:
        if review.get("delegation_id") != delegation_id:
            continue
        kind = review.get("reviewer_kind")
        if kind in REVIEWER_KINDS and kind not in result:
            result[kind] = review
    return result


def status(
    state: dict[str, Any],
    review_payloads: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    assert_bindings(state)
    timestamp = now or utc_now()
    current_id = state.get("current_delegation_id")
    if not current_id:
        state["status"] = "dispatch_required"
        return {"status": "dispatch_required", "next_action": "dispatch_two_reviewers", "state": state}
    current = state["attempts"][-1]
    current_reviews = review_map(review_payloads, current_id)
    if set(current_reviews) == REVIEWER_KINDS:
        state["status"] = "ready_for_validation"
        return {
            "status": "ready_for_validation",
            "delegation_id": current_id,
            "reviewer_kinds": sorted(current_reviews),
            "next_action": "run_candidate_portfolio_assemble" if state.get("candidate_stage") == "clustered_representatives" else "run_validate_deliberation",
            "state": state,
        }
    missing = sorted(REVIEWER_KINDS - set(current_reviews))
    if timestamp < parse_time(current["deadline_at"]):
        state["status"] = "pending"
        return {
            "status": "pending",
            "delegation_id": current_id,
            "missing_reviewer_kinds": missing,
            "deadline_at": current["deadline_at"],
            "next_action": "wait_for_current_callbacks",
            "state": state,
        }
    retries_used = len(state["attempts"]) - 1
    if retries_used < int(state.get("max_retries", 1)):
        state["status"] = "retry_required"
        current["timed_out_at"] = iso(timestamp)
        current["missing_reviewer_kinds"] = missing
        return {
            "status": "retry_required",
            "expired_delegation_id": current_id,
            "missing_reviewer_kinds": missing,
            "next_action": "redispatch_same_frozen_inputs_once",
            "state": state,
        }
    state["status"] = "blocked"
    current["timed_out_at"] = iso(timestamp)
    current["missing_reviewer_kinds"] = missing
    return {
        "status": "blocked",
        "delegation_id": current_id,
        "missing_reviewer_kinds": missing,
        "reason": "DELIBERATION_CALLBACK_TIMEOUT_EXHAUSTED",
        "next_action": "deliver_diagnostic_only",
        "state": state,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init")
    init.add_argument("--packet", type=Path, required=True)
    init.add_argument("--candidates", type=Path, required=True)
    init.add_argument("--lane", choices=("short", "long"), required=True)
    init.add_argument("--state", type=Path, required=True)
    init.add_argument("--timeout-minutes", type=int, default=30)
    init.add_argument("--max-retries", type=int, default=1)

    dispatched = sub.add_parser("mark-dispatched")
    dispatched.add_argument("--state", type=Path, required=True)
    dispatched.add_argument("--delegation-id", required=True)

    check = sub.add_parser("status")
    check.add_argument("--state", type=Path, required=True)
    check.add_argument("--review", type=Path, action="append", default=[])

    args = parser.parse_args()
    if args.command == "init":
        state = create_state(
            args.packet,
            args.candidates,
            args.lane,
            timeout_minutes=args.timeout_minutes,
            max_retries=args.max_retries,
        )
        atomic_json(args.state, state)
        result = {"status": state["status"], "state": str(args.state.resolve())}
    elif args.command == "mark-dispatched":
        state = mark_dispatched(load_json(args.state), args.delegation_id)
        atomic_json(args.state, state)
        result = {"status": state["status"], "delegation_id": state["current_delegation_id"]}
    else:
        state = load_json(args.state)
        reviews = [load_json(path) for path in args.review]
        result = status(state, reviews)
        atomic_json(args.state, result.pop("state"))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"dispatch_required", "pending", "ready_for_validation", "retry_required"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
