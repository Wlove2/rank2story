#!/usr/bin/env python3
"""Resumable, fail-closed controller for candidate portfolio production."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import candidate_portfolio as portfolio

CONTRACT_VERSION = "4.4.0-rc1"
MAX_FORMAT_RETRIES = 1
MAX_STORY_REWRITES = 1
MAX_KERNEL_SUPPLEMENT_ROUNDS = 2
MAX_CANDIDATE_CONCURRENCY = 3
# 2026-09-02：用户确认候选用免费模型（调用成本无关），大步放宽预算/熔断门限。
# 历史参考：8/04 production 实跑 81 calls / recovery 16/16 / 运行时 live fuse 曾为 120。
# 2026-09-02（用户二次指示）：RECOVERY_CALL_BUDGET 提到 64 以上 → 定为 128。
RECOVERY_CALL_BUDGET = 128
CALL_WARNING_THRESHOLD = 400
CALL_FUSE_THRESHOLD = 512
EXECUTOR_LEASE_SECONDS = 120
EXECUTION_PROFILES = {
    "smoke": {"kernels_per_branch": 2, "expected_base_calls": 24},
    "production": {"kernels_per_branch": 3, "expected_base_calls": 33},
}
TERMINAL = {"awaiting_user_choice", "candidate_generation_failed"}
ROLE_TO_STAGE = {
    "atoms": "S1_ATOMS",
    "generation_A": "S2_KERNELS",
    "generation_B": "S2_KERNELS",
    "generation_C": "S2_KERNELS",
    "market_coverage": "S3_REVIEW",
    "originality_craft": "S3_REVIEW",
}
BUNDLE_SCRIPTS = [
    "novel-analyzer/scripts/candidate_workflow.py",
    "novel-analyzer/scripts/candidate_portfolio.py",
    "novel-analyzer/scripts/freeze_evidence_packet.py",
    "novel-analyzer/scripts/candidate_executor.py",
    "novel-candidate-portfolio/scripts/candidate.py",
]
BUNDLE_DOCS = [
    "novel-analyzer/SKILL.md",
    "novel-candidate-portfolio/SKILL.md",
    "novel-analyzer/references/generation-artifact-schema.md",
]
SNAPSHOT_NAMES = {
    "novel-analyzer/scripts/candidate_workflow.py": "candidate_workflow.py",
    "novel-analyzer/scripts/candidate_portfolio.py": "candidate_portfolio.py",
    "novel-analyzer/scripts/freeze_evidence_packet.py": "freeze_evidence_packet.py",
    "novel-analyzer/scripts/candidate_executor.py": "candidate_executor.py",
    "novel-candidate-portfolio/scripts/candidate.py": "candidate.py",
    "novel-analyzer/SKILL.md": "analyzer.md",
    "novel-candidate-portfolio/SKILL.md": "portfolio.md",
    "novel-analyzer/references/generation-artifact-schema.md": "schema.md",
}


def bundle_fingerprint() -> dict[str, Any]:
    analyzer_root = Path(__file__).resolve().parents[1]
    script_paths = {
        "novel-analyzer/scripts/candidate_workflow.py": Path(__file__).resolve(),
        "novel-analyzer/scripts/candidate_portfolio.py": Path(portfolio.__file__).resolve(),
        "novel-analyzer/scripts/freeze_evidence_packet.py": Path(portfolio.__file__).resolve().with_name("freeze_evidence_packet.py"),
        "novel-analyzer/scripts/candidate_executor.py": Path(__file__).resolve().with_name("candidate_executor.py"),
        "novel-candidate-portfolio/scripts/candidate.py": analyzer_root.parent / "novel-candidate-portfolio" / "scripts" / "candidate.py",
    }
    doc_paths = {
        "novel-analyzer/SKILL.md": analyzer_root / "SKILL.md",
        "novel-candidate-portfolio/SKILL.md": analyzer_root.parent / "novel-candidate-portfolio" / "SKILL.md",
        "novel-analyzer/references/generation-artifact-schema.md": analyzer_root / "references" / "generation-artifact-schema.md",
    }
    missing = sorted(label for label, path in {**script_paths, **doc_paths}.items() if not path.is_file())
    if missing:
        raise ValueError(f"BUNDLE_FILES_MISSING:{missing}")
    script_hashes = {label: file_sha256(path) for label, path in script_paths.items()}
    doc_hashes = {label: content_hash(path) for label, path in doc_paths.items()}
    bundle_files = {**script_hashes, **doc_hashes}
    return {"bundle_hash": portfolio.canonical_hash(bundle_files), "bundle_files": bundle_files}


def content_hash(path: Path) -> str:
    """Normalise line-endings to LF before hashing so CRLF drift is harmless."""
    text = win_long_path(path).read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_path(path: Path) -> Path:
    """Return a normal absolute path suitable for prompts, state, and receipts."""
    text = os.path.abspath(str(path))
    if os.name != "nt":
        return Path(text)
    prefix = '\\\\?\\'
    unc_prefix = prefix + 'UNC\\'
    if text.startswith(unc_prefix):
        return Path('\\\\' + text[len(unc_prefix):])
    if text.startswith(prefix):
        return Path(text[4:])
    return Path(text)


def win_long_path(path: Path) -> Path:
    """Return a Windows extended path for filesystem calls only."""
    canonical = canonical_path(path)
    if os.name != "nt":
        return canonical
    text = str(canonical)
    if text.startswith('\\\\'):
        return Path('\\\\?\\UNC\\' + text[2:])
    return Path('\\\\?\\' + text)


def snapshot_bundle(output_dir: Path) -> dict[str, str]:
    """Copy every bundle file into the run directory so concurrent runs are isolated."""
    snap_dir = win_long_path(output_dir / "_bundle_snapshot")
    snap_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, str] = {}
    analyzer_root = Path(__file__).resolve().parents[1]
    paths = {
        "novel-analyzer/scripts/candidate_workflow.py": Path(__file__).resolve(),
        "novel-analyzer/scripts/candidate_portfolio.py": Path(portfolio.__file__).resolve(),
        "novel-analyzer/scripts/freeze_evidence_packet.py": Path(portfolio.__file__).resolve().with_name("freeze_evidence_packet.py"),
        "novel-analyzer/scripts/candidate_executor.py": Path(__file__).resolve().with_name("candidate_executor.py"),
        "novel-candidate-portfolio/scripts/candidate.py": analyzer_root.parent / "novel-candidate-portfolio" / "scripts" / "candidate.py",
        "novel-analyzer/SKILL.md": analyzer_root / "SKILL.md",
        "novel-candidate-portfolio/SKILL.md": analyzer_root.parent / "novel-candidate-portfolio" / "SKILL.md",
        "novel-analyzer/references/generation-artifact-schema.md": analyzer_root / "references" / "generation-artifact-schema.md",
    }
    for label, src in paths.items():
        dst = snap_dir / SNAPSHOT_NAMES[label]
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
        manifest[label] = content_hash(dst) if label in BUNDLE_DOCS else file_sha256(dst)
    return manifest


def snapshot_manifest(output_dir: Path) -> dict[str, str]:
    snap_dir = win_long_path(output_dir / "_bundle_snapshot")
    expected_names = {SNAPSHOT_NAMES[label]: label for label in BUNDLE_SCRIPTS + BUNDLE_DOCS}
    if not snap_dir.is_dir():
        raise ValueError("BUNDLE_SNAPSHOT_MISSING")
    observed_names = {
        path.relative_to(snap_dir).as_posix()
        for path in snap_dir.rglob("*") if path.is_file() and "__pycache__" not in path.parts
    }
    if observed_names != set(expected_names):
        raise ValueError("BUNDLE_SNAPSHOT_FILE_SET_INVALID")
    return {
        label: content_hash(snap_dir / name) if label in BUNDLE_DOCS else file_sha256(snap_dir / name)
        for name, label in expected_names.items()
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def lease_is_valid(state: dict[str, Any]) -> bool:
    lease = state.get("executor_lease")
    if not isinstance(lease, dict) or lease.get("status") != "active":
        return False
    try:
        heartbeat = datetime.fromisoformat(str(lease["heartbeat_at"]))
    except (KeyError, TypeError, ValueError):
        return False
    return datetime.now(timezone.utc) - heartbeat <= timedelta(seconds=EXECUTOR_LEASE_SECONDS)


def reserve_recovery_call(state: dict[str, Any], reason: str, **metadata: Any) -> bool:
    budget = state.setdefault("recovery_budget", {
        "limit": RECOVERY_CALL_BUDGET, "used": 0, "events": [],
    })
    if int(budget.get("used", 0)) >= int(budget.get("limit", RECOVERY_CALL_BUDGET)):
        return False
    budget["used"] = int(budget.get("used", 0)) + 1
    budget.setdefault("events", []).append({"at": utc_now(), "reason": reason, **metadata})
    return True


def acquire_executor_lease(claim_path: Path, executor_id: str, model: str) -> dict[str, Any]:
    _, _, _, output_dir, state_path = validate_claim(claim_path)
    state = load_json(state_path)
    if state["status"] in TERMINAL:
        return public_state(claim_path, state)
    if lease_is_valid(state):
        raise ValueError("EXECUTOR_LEASE_ALREADY_HELD")
    now = utc_now()
    state["executor_lease"] = {
        "executor_id": executor_id, "model": model, "status": "active",
        "acquired_at": now, "heartbeat_at": now,
    }
    state["status"] = "running"
    state["updated_at"] = now
    save_state(state_path, state)
    append_manifest(output_dir, {"event": "executor_lease_acquired", "executor_id": executor_id, "model": model})
    return public_state(claim_path, state)


def heartbeat_executor(claim_path: Path, executor_id: str) -> None:
    _, _, _, _, state_path = validate_claim(claim_path)
    state = load_json(state_path)
    lease = state.get("executor_lease") or {}
    if lease.get("executor_id") != executor_id or lease.get("status") != "active":
        raise ValueError("EXECUTOR_LEASE_NOT_HELD")
    lease["heartbeat_at"] = utc_now()
    state["updated_at"] = utc_now()
    save_state(state_path, state)


def release_executor_lease(claim_path: Path, executor_id: str, *, error: str | None = None) -> dict[str, Any]:
    _, _, _, output_dir, state_path = validate_claim(claim_path)
    state = load_json(state_path)
    lease = state.get("executor_lease") or {}
    if lease.get("executor_id") == executor_id:
        lease["status"] = "failed" if error else "released"
        lease["released_at"] = utc_now()
        if error:
            lease["error"] = error
    if state["status"] not in TERMINAL:
        state["status"] = "paused"
    state["updated_at"] = utc_now()
    save_state(state_path, state)
    append_manifest(output_dir, {"event": "executor_lease_released", "executor_id": executor_id, "error": error})
    return public_state(claim_path, state)


def record_executor_call(claim_path: Path, executor_id: str, action: dict[str, Any], session_id: str) -> None:
    _, _, _, output_dir, state_path = validate_claim(claim_path)
    state = load_json(state_path)
    lease = state.get("executor_lease") or {}
    if lease.get("executor_id") != executor_id or not lease_is_valid(state):
        raise ValueError("EXECUTOR_LEASE_NOT_HELD")
    metrics = state.setdefault("call_budget", {})
    started = int(metrics.get("calls_started", 0))
    if started >= int(metrics.get("hard_fuse", CALL_FUSE_THRESHOLD)):
        raise ValueError("LLM_CALL_FUSE_REACHED")
    metrics["calls_started"] = started + 1
    metrics.setdefault("calls", []).append({
        "at": utc_now(), "job_id": action["job_id"], "role": action["role"],
        "session_id": session_id,
    })
    if metrics["calls_started"] >= int(metrics.get("warning_threshold", CALL_WARNING_THRESHOLD)):
        metrics["warning"] = "LLM_CALL_SOFT_BUDGET_EXCEEDED"
    lease["heartbeat_at"] = utc_now()
    state["updated_at"] = utc_now()
    save_state(state_path, state)
    append_manifest(output_dir, {
        "event": "llm_call_started", "job_id": action["job_id"], "role": action["role"],
        "session_id": session_id, "call_number": metrics["calls_started"],
    })


def abort_for_executor(claim_path: Path, reason: str) -> dict[str, Any]:
    claim, profile, _, output_dir, state_path = validate_claim(claim_path)
    state = load_json(state_path)
    if state["status"] in TERMINAL:
        return public_state(claim_path, state)
    state = finalize_failure(
        claim, profile, output_dir, state_path, state,
        [{"reason": reason, "calls_started": state.get("call_budget", {}).get("calls_started", 0)}],
    )
    return public_state(claim_path, state)


COMPACT_LIMITS: dict[str, dict[str, int]] = {
    "short": {"max_items": 150, "max_chars": 200_000},
    "long": {"max_items": 300, "max_chars": 350_000},
}


def compact_evidence_view(packet: dict[str, Any], lane: str, *, max_items: int | None = None, max_chars: int | None = None, seed: str = "") -> dict[str, Any]:
    """Deterministically round-robin evidence across cohorts/platforms; never take the first N."""
    limits = COMPACT_LIMITS.get(lane, COMPACT_LIMITS["short"])
    if max_items is None:
        max_items = limits["max_items"]
    if max_chars is None:
        max_chars = limits["max_chars"]
    packet_hash = portfolio.validate_packet(packet, lane)
    source_to_cohort, _ = portfolio.cohort_index(packet)
    unique: dict[str, dict[str, Any]] = {}
    for item in portfolio.recursive_evidence(packet):
        evidence_id = str(item.get("evidence_id") or "")
        if evidence_id:
            unique.setdefault(evidence_id, item)

    def compact(value: Any) -> Any:
        if isinstance(value, str):
            return value[:1200]
        if isinstance(value, list):
            return [compact(row) for row in value[:20]]
        if isinstance(value, dict):
            return {str(key): compact(row) for key, row in sorted(value.items())}
        return value

    def sort_key(evidence_id: str) -> str:
        if seed:
            return hashlib.sha256(f"{evidence_id}:{seed}".encode()).hexdigest()
        return evidence_id

    buckets: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for evidence_id, item in sorted(unique.items(), key=lambda kv: sort_key(kv[0])):
        source_id = str(item.get("source_id") or item.get("manifest_id") or "")
        platform_name = platform_for_source(item, source_id)
        cohort = portfolio.cohort_for_source(source_to_cohort, source_id) or "unassigned"
        stance = str(item.get("stance") or "unlabeled")
        buckets.setdefault((cohort, platform_name, stance), []).append(compact(item))
    selected: list[dict[str, Any]] = []
    total_chars = 0
    while buckets and len(selected) < max_items:
        progressed = False
        for key in sorted(list(buckets)):
            rows = buckets[key]
            if not rows:
                buckets.pop(key, None)
                continue
            row = rows.pop(0)
            encoded = json.dumps(row, ensure_ascii=False, sort_keys=True)
            if total_chars + len(encoded) > max_chars:
                buckets.clear()
                break
            selected.append(row)
            total_chars += len(encoded)
            progressed = True
            if len(selected) >= max_items:
                break
        if not progressed:
            break
    return portfolio.seal({
        "stage": "compact_evidence_view", "schema_version": portfolio.SCHEMA_VERSION,
        "lane": lane, "evidence_packet_hash": packet_hash,
        "selection_policy": "deterministic_round_robin_by_cohort_platform_stance",
        "seed": seed, "max_items": max_items, "max_chars": max_chars, "selected_count": len(selected),
        "evidence": selected,
    })


def build_review_evidence_slice(
    packet: dict[str, Any], atom_bundle: dict[str, Any], clustered: dict[str, Any],
    lane: str, output_dir: Path,
) -> Path:
    """Build a compact evidence slice for S3 reviewers (~13K tokens vs ~350K full packet)."""
    packet_hash = portfolio.validate_packet(packet, lane)
    registry = portfolio.evidence_reference_registry(packet)
    evidence = portfolio.evidence_index(packet)
    representative_ids = set(clustered.get("representative_ids") or [])
    cited_atom_ids: set[str] = set()
    for candidate in clustered.get("representatives") or []:
        if str(candidate.get("candidate_id") or candidate.get("id")) in representative_ids:
            cited_atom_ids.update(map(str, candidate.get("cited_atom_ids") or []))
    atoms = atom_bundle.get("atoms") if isinstance(atom_bundle.get("atoms"), list) else []
    cited_atoms = [a for a in atoms if isinstance(a, dict) and str(a.get("atom_id") or "") in cited_atom_ids]
    cited_evidence_ids: set[str] = set()
    for atom in cited_atoms:
        eid = str(atom.get("evidence_id") or "")
        if eid:
            cited_evidence_ids.add(eid)
        for sid in atom.get("supporting_evidence_ids") or []:
            if str(sid):
                cited_evidence_ids.add(str(sid))
    referenced_evidence = {
        eid: {k: v for k, v in evidence[eid].items() if k in (
            "evidence_id", "source_id", "source_item_id", "platform", "url", "direct_url", "source_url",
        )}
        for eid in sorted(cited_evidence_ids) if eid in evidence
    }
    slice_payload = portfolio.seal({
        "stage": "review_evidence_slice", "schema_version": portfolio.SCHEMA_VERSION,
        "lane": lane, "evidence_packet_hash": packet_hash,
        "evidence_ids": sorted(registry["evidence_ids"]),
        "registered_urls": sorted(registry["urls"]),
        "referenced_evidence": referenced_evidence,
        "cited_atoms": cited_atoms,
    })
    return Path(write_artifact(output_dir, "review_evidence_slice.json", slice_payload))


def load_json(path: Path) -> Any:
    return json.loads(win_long_path(path).read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with win_long_path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_exclusive(path: Path, payload: Any) -> None:
    filesystem_path = win_long_path(path)
    filesystem_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with filesystem_path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    except FileExistsError:
        with filesystem_path.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")


def save_state(path: Path, payload: dict[str, Any]) -> None:
    filesystem_path = win_long_path(path)
    filesystem_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".state-", suffix=".json", dir=str(filesystem_path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        for attempt in range(3):
            try:
                os.replace(temporary, str(filesystem_path))
                break
            except PermissionError:
                if attempt == 2:
                    raise
                import time
                time.sleep(0.1 * (attempt + 1))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def append_manifest(output_dir: Path, event: dict[str, Any]) -> None:
    with win_long_path(output_dir / "controller_manifest.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps({"at": utc_now(), **event}, ensure_ascii=False, sort_keys=True) + "\n")


def validate_claim(claim_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], Path, Path]:
    claim_path = claim_path.resolve()
    claim = load_json(claim_path)
    output_dir = Path(str(claim.get("output_dir") or "")).resolve()
    state_path = output_dir / "controller_state.json"
    if (
        claim.get("stage") != "candidate_run_claim"
        or claim.get("production_contract_version") != CONTRACT_VERSION
        or not portfolio.verify_seal(claim)
        or claim_path != output_dir / "candidate_run_claim.json"
        or not win_long_path(state_path).is_file()
    ):
        raise ValueError("CANDIDATE_RUN_CLAIM_INVALID")
    expected_bundle = snapshot_manifest(output_dir)
    if (
        claim.get("bundle_files") != expected_bundle
        or claim.get("bundle_hash") != portfolio.canonical_hash(expected_bundle)
    ):
        raise ValueError("BUNDLE_SNAPSHOT_CHANGED_DURING_RUN")
    profile = load_json(output_dir / "target_profile.json")
    packet = load_json(output_dir / "evidence_packet.json")
    if profile.get("output_hash") != claim.get("target_profile_hash"):
        raise ValueError("CLAIM_PROFILE_HASH_MISMATCH")
    if portfolio.validate_packet(packet, claim["lane"]) != claim.get("evidence_packet_hash"):
        raise ValueError("CLAIM_PACKET_HASH_MISMATCH")
    return claim, profile, packet, output_dir, state_path



def role_stage(role: str) -> str:
    if role in ROLE_TO_STAGE:
        return ROLE_TO_STAGE[role]
    if role.startswith("kernel_supplement_"):
        return "S2_KERNELS"
    if role == "story_creator":
        return "S2_STORY"
    if role == "story_editor":
        return "S2_EDIT"
    if role == "candidate_mapper":
        return "S2_MAP"
    raise ValueError(f"JOB_ROLE_INVALID:{role}")


def job_prompt(
    role: str, claim: dict[str, Any], output_dir: Path, raw_path: Path, round_no: int,
    *, repair_hint: str = "", metadata: dict[str, Any] | None = None,
) -> str:
    metadata = metadata or {}
    contract_doc = output_dir / "_bundle_snapshot" / "schema.md"
    common = (
        f"Candidate contract {CONTRACT_VERSION}; run_id={claim['run_id']}; lane={claim['lane']}. "
        f"Read the exact role schema in the frozen run bundle at {contract_doc}. "
        f"Write exactly one UTF-8 JSON object to {raw_path}. Do not edit any other file. "
        "Never use placeholders, schema labels as content, invented evidence IDs, or parent-artifact edits."
    )
    if role == "atoms":
        atom_target = "40～60" if claim.get("lane") == "short" else "60～90"
        base = common + (
            f" Read {output_dir / 'evidence_compact_view.json'} and {output_dir / 'target_profile.json'}. "
            "你的任务是从扫榜证据中提炼可重新组合的故事力量/元素（story atoms），供 A/B/C 分支自由组合创意。"
            "故事元素是：欲望、焦虑、身份幻想、冲突机制、回报模式、开篇形式、活动约束、反信号。"
            "运营收入、平台流量衰减、渠道不确定性只能作为市场背景理解，不能作为生成原子。"
            "Never quote, reproduce, or closely paraphrase any title, work name, book name, author name, "
            "or raw ranking row in observation or inference; describe only the underlying audience behavior, "
            "desire, mechanism, resistance, or reward that can be recombined into new stories. "
            "CRITICAL HARD RULES: (1) observation and inference MUST be written in Chinese (CJK); "
            "do NOT write observation or inference in English or any other language. "
            "(2) observation and inference MUST NOT contain any Chinese book-title "
            "brackets 《》 or any quoted/paraphrased work title, author name, or ranking row text; "
            "describe only abstract audience behavior, desire, mechanism, resistance, or reward. "
            "(3) evidence_id MUST be copied VERBATIM from the evidence list in evidence_compact_view.json; "
            "never construct, rewrite, concatenate, or invent evidence IDs, URLs, or manifest-derived IDs. "
            "Legal evidence_id values look like 'fanqie-reader-short-<digits>', 'qimao-story-<digits>', "
            "'bili-sub-<digits>', 'xhs-note-<digits>', 'fanqie-writer-<digits>'. NEVER use a source_id, "
            "manifest_id, URL, or any 'source_id:https://...' style value as an evidence_id; the evidence_id "
            "field of each record in evidence_compact_view.json is the ONLY legal value. " 
            "(4) observation MUST state only facts present in the cited evidence (what the source shows or "
            "what the story does); inference MUST be the interpretation (reader desire, mechanism, payoff logic). "
            "Never write the interpretation into observation, and never assert an interpretation the evidence does not support. "
            "Example — observation: '榜单条目多为身份互换、主角地位被顶替的设定'; "
            "inference: '读者对身份被剥夺有强烈不适，适合放大为拉扯钩子'. "
            "(5) do not use ASCII apostrophes or quote marks inside string values; write Chinese text with "
            "full-width punctuation only."
            f"目标产出 {atom_target} 个互不重复、确有证据支撑的元素。必须覆盖所有证据来源（番茄、七猫、社交平台），"
            "不能静默遗漏整个 cohort；无有效故事元素的证据可以不用，但必须实际阅读。"
            "Use a numeric confidence from 0 through 1. Return either atoms[] directly or an object containing atoms[]. "
            "Each atom contains only atom_type, "
            "evidence_id, observation, inference, confidence, claim_key, stance, plus optional "
            "counter_evidence_ids and contradicting_atom_ids. "
            f"atom_type 必须是以下之一：{', '.join(sorted(portfolio.ATOM_TYPES))}。不要使用其他类型。 "
            "The controller injects every deterministic source, "
            "cohort, platform, freshness, ID, hash, lane, and supporting-evidence field."
        )
        if repair_hint:
            base += (
                f" PREVIOUS ATTEMPT FAILED validation with these codes: {repair_hint}. "
                "Fix ONLY the flagged issues. In particular: if RAW_TITLE_TEXT_LEAKED_TO_ATOM was flagged, "
                "rewrite every observation/inference to remove ALL 《》 book-title brackets and any quoted or "
                "paraphrased work title/author/ranking text. If ATOM_EVIDENCE_UNKNOWN or "
                "ATOM_SOURCE_COHORT_MISMATCH or ATOM_RELATED_EVIDENCE_UNKNOWN was flagged, replace every "
                "evidence_id with an ID copied VERBATIM from the evidence list in evidence_compact_view.json "
                "— legal values look like 'fanqie-reader-short-<digits>', 'qimao-story-<digits>', "
                "'bili-sub-<digits>', 'xhs-note-<digits>', 'fanqie-writer-<digits>'; NEVER use source_id, "
                "manifest_id, URLs, or 'source_id:https://...' values."
            )
        return base
    if role.startswith("generation_"):
        branch = role[-1]
        context_path = output_dir / f'generation_context_{branch}.json'
        kernel_count = int(claim["kernels_per_branch"])
        return common + (
            f' Read only the sealed branch context at {context_path}. '
            f"Isolated strategy={branch}; gap-fill round={round_no}. Return branch_id and exactly {kernel_count} concept_kernels; "
            "do not write stories, candidate cards, fingerprints, scores, audits, or proofs. A kernel is a compact "
            "natural-language idea seed, not a fixed field schema. Hook, situation, desire, mechanism, resistance, "
            "payoff, evidence hints, and any other useful details are examples only; omit or add fields freely. "
            "The controller normalizes kernel IDs and branch evidence references. Differences should be causal, not cosmetic."
        )
    if role.startswith("kernel_supplement_"):
        branch = role[-1]
        context_path = output_dir / f'generation_context_{branch}.json'
        return common + (
            f' Read only {context_path} and the prior '
            f"kernel artifact at {metadata['kernel_artifact']}. Return exactly one new object as concept_kernel; "
            "write a compact natural-language idea seed using whichever fields help, with no fixed schema and no story "
            "or candidate card. The controller normalizes its ID and branch evidence references."
        )
    if role == "story_creator":
        feedback = str(metadata.get("feedback") or "").strip()
        context_path = output_dir / f'generation_context_{metadata["branch_id"]}.json'
        return "\n".join([
            "你是故事提案作者。暂时不要填候选卡、评分或解释新意。",
            f"只读取 kernel：{metadata['kernel_path']}；目标读者：{output_dir / 'target_profile.json'}；相关证据原子：{output_dir / 'evidence_atoms.json'}。",
            "把这个创意写成约 300—600 字的完整故事提案：从开端讲到结局，证明它能讲通。允许为讲通而调整 kernel。",
            "提案不是正文：不需要完整文风、场景细节或对话，但必须有清晰的因果链——谁、想要什么、遇到什么阻力、怎么行动、结局如何。",
            "人物按当时信息和利益行动，机制前后一致，关键转折由前一步导致，结局由前文行动挣得；讲不通就主动改机制。",
            "短篇必须闭合中心冲突；长篇必须讲清首阶段闭环并发动长期矛盾。不要用结尾一句新设定补洞。",
            f"上次编辑意见：{feedback}" if feedback else "这是第一次创作，没有上次编辑意见。",
            f"只把故事提案写入 {raw_path}，不加标题、列表、注释或 JSON。",
        ]) + (
            f'\nAUTHORITATIVE INPUT SCOPE: only {metadata["kernel_path"]} and {context_path}; '
            'ignore any broader legacy path named above.'
        )
    if role == "story_editor":
        return "\n".join([
            "你是独立故事编辑，只读取指定故事提案，不看商业目标、其他评价或答案。",
            f"故事提案：{metadata['story_path']}",
            "检查以下硬伤：前后矛盾（前文说不知道X，后文却利用X行动）、因果倒置（结果出现在原因之前）、机制自相矛盾（规则同时允许和禁止同一行为）。",
            "检查机械降神：如果决定胜负的能力、证据或信息直到需要解题时才第一次出现，前文完全没有建立它存在、主角为何能收到或使用它，就属于核心因果断裂，必须拒绝。系统、超能力、神秘播报都可以写，但必须在危机之前自然建立其存在和基本规则。",
            "不拒绝：叙事留白、未交代的次要因果、读者可以合理推断的环节、时间线压缩、能力来源的技术原理未详细解释。",
            "不需要解释系统宇宙观或所有细节，读者能理解主角为什么能获得并使用关键能力即可。",
            "若不存在上述硬伤，只输出\u201c通过\u201d。",
            "若存在，引用具体矛盾位置并说明前后如何冲突；只写硬伤，不做其他分析或输出 JSON。",
            f"把结果写入 {raw_path}。",
        ])
    if role == "candidate_mapper":
        lane_rule = (
            " The candidate_card MUST include a substantive 'short_closure' field (2-4 sentences describing "
            "how the short story ends and closes its emotional loop)."
            if claim.get("lane") == "short"
            else " The candidate_card MUST include a substantive 'long_run_stages' object (long-lane "
            "requirement) with EXACT keys '300k', '800k', '1500k' — each a dict containing exactly "
            "'goal', 'relationship_change', 'world_expansion', 'irreversible_change', 'stage_payoff' "
            "(all substantive Chinese strings describing the opening arc, the middle escalation, and the "
            "long-run payoff engine). The field must be exactly 'long_run_stages' with keys 300k/800k/1500k; "
            "do not omit it."
        )
        base = common + (
            f" Read the passed story at {metadata['story_path']}, its review at {metadata['review_path']}, "
            f"kernel at {metadata['kernel_path']}, and target_profile.json. Return one candidate object containing only structural_fingerprint and the "
            "existing full candidate_card contract. Map facts already present in the story; do not add a new cause, "
            "motivation, mechanism rule, ending condition, score, or audit. "
            "CRITICAL LANGUAGE RULE: ALL text fields in candidate_card (one_line_concept, target_reader, "
            "opening_300_beats, reward_cycle, three_payoffs, closest_work, causal_difference, risks) "
            "MUST be written in Chinese (中文). Never output English sentences in any card field."
            + lane_rule
        )
        if repair_hint:
            base += (
                f" PREVIOUS ATTEMPT FAILED validation with these codes: {repair_hint}. "
                "Fix ONLY the flagged issues while preserving all other content. "
                "If CARD_ONE_LINE_CONCEPT_LANGUAGE_INVALID: rewrite one_line_concept in natural Chinese. "
                "If CARD_CLOSEST_WORK_PLACEHOLDER or CARD_CAUSAL_DIFFERENCE_PLACEHOLDER: write substantive Chinese content."
                " If CARD_SHORT_CLOSURE_INVALID: add a substantive 'short_closure' field in Chinese."
                " If CARD_LONG_RUN_STAGES_INVALID or LONG_THREE_STAGE_REVIEW_MISSING or LONG_THREE_STAGE_REVIEW_NOT_SUBSTANTIVE: "
                "add a substantive 'long_run_stages' object with EXACT keys '300k', '800k', '1500k', each containing 'goal', "
                "'relationship_change', 'world_expansion', 'irreversible_change', 'stage_payoff' in Chinese."
            )
        return base
    if role == "market_coverage":
        base = common + (
            f" Independently review every item in {output_dir / f'clustered_representatives_r{round_no}.json'}. Return candidates keyed "
            "by candidate_id using the S3 market review schema. Reject any weak entry promise, reward cycle, platform/"
            "channel fit, causality, short closure/complexity, or long three-stage engine. "
            "编辑原则：逻辑讲得通不等于值得看。若主角不是读者想跟随的对象、核心期待不成立、"
            "回报与目标频道相反、或风险说明本身已承认不够爽/令人反感，就应拒绝（status=rejected）。"
            "允许本轮不足 4 个通过。不要替候选脑补吸引力。 "
            "Follow the exact field definitions in the schema (status, checks, calibrated_objectives as flat int dict, "
            "objective_rationales as separate dict). All text fields in Chinese."
            " Every candidate MUST include two channel-enforcement fields: 'channel_verdict' with one of "
            "{fit, partial, mismatch} judging how well this card fits the run's audience channel, and "
            "'protagonist_perspective' with one of {male, female, neutral}. A protagonist perspective opposite to "
            "the run channel is NOT automatically a mismatch: if the card still has acceptable channel fit, judge "
            "'partial' and give the concrete reason in channel_fit; only a genuinely off-channel card is 'mismatch' "
            "with status=rejected. Never claim 'fit' for an opposite-gender perspective."
        )
        if repair_hint:
            base += (
                f" PREVIOUS ATTEMPT FAILED validation with these codes: {repair_hint}. "
                "Fix ONLY the flagged issues. Produce substantive, candidate-specific content for EVERY required field. "
                "Every field must be a REAL review — not placeholder text, not template strings."
                " If MARKET_CHANNEL_VERDICT_INVALID or MARKET_PROTAGONIST_PERSPECTIVE_INVALID: provide both fields "
                "with valid enum values ({fit,partial,mismatch} / {male,female,neutral}). "
                " If CHANNEL_MISMATCH_NOT_REJECTED: either set status=rejected for the mismatch card or correct channel_verdict."
                " If CHANNEL_VERDICT_CONTRADICTS_PERSPECTIVE: downgrade an opposite-gender verdict from 'fit' to 'partial' "
                "with a concrete channel_fit reason (or to 'mismatch'+rejected if truly off-channel)."
            )
        return base
    base = common + (
        f" Independently red-team every item in {output_dir / f'clustered_representatives_r{round_no}.json'}. Return candidates keyed "
        "by candidate_id using the S3 originality review schema. Follow the exact field definitions in the schema "
        "(layers as dict with 4 keys; closest_work_reference as an object with a substantive Chinese identifier "
        "and an evidence_id copied exactly from review_evidence_slice.json; "
        "use exactly {\"identifier\": \"<work name or evidence title>\", \"evidence_id\": \"<registered ID>\"}; "
        "an evidence_id without identifier is invalid; "
        "calibrated_originality_risk as integer 1-5). Reject collisions. All text fields in Chinese."
    )
    if repair_hint:
        base += (
            f" PREVIOUS ATTEMPT FAILED validation with these codes: {repair_hint}. "
            "Fix ONLY the flagged issues. Produce substantive, candidate-specific content for EVERY required field. "
            "Every field must be a REAL red-team review — not placeholder text, not template strings."
        )
        if "CLOSEST_WORK_REFERENCE_INVALID" in repair_hint:
            base += (
                " For CLOSEST_WORK_REFERENCE_INVALID, rewrite every failed closest_work_reference as a complete "
                "object containing a substantive identifier plus an evidence_id copied exactly from "
                "review_evidence_slice.json; do not invent URLs or unregistered references, and do not return "
                "an evidence_id alone."
            )
    return base


def branch_context_path(output_dir: Path, branch: str) -> Path:
    '''Return a sealed single-branch context, creating it for older resumable runs.'''
    if branch not in portfolio.BRANCH_ROLES:
        raise ValueError(f'GENERATION_BRANCH_INVALID:{branch}')
    path = output_dir / f'generation_context_{branch}.json'
    if not path.is_file():
        bundle_path = output_dir / 'generation_contexts.json'
        if not bundle_path.is_file():
            return path
        bundle = load_json(bundle_path)
        context = (bundle.get('contexts') or {}).get(branch)
        if not isinstance(context, dict) or not portfolio.verify_seal(context):
            raise ValueError(f'GENERATION_CONTEXT_SLICE_INVALID:{branch}')
        save_exclusive(path, context)
    return path


def job_input_paths(role: str, output_dir: Path, metadata: dict[str, Any]) -> list[str]:
    schema = output_dir / "_bundle_snapshot" / "schema.md"
    if role == "atoms":
        paths = [output_dir / "evidence_compact_view.json", output_dir / "target_profile.json", schema]
    elif role.startswith('generation_'):
        paths = [branch_context_path(output_dir, role[-1]), schema]
    elif role.startswith('kernel_supplement_'):
        paths = [branch_context_path(output_dir, role[-1]), Path(metadata['kernel_artifact']), schema]
    elif role == 'story_creator':
        paths = [Path(metadata['kernel_path']), branch_context_path(output_dir, str(metadata['branch_id']))]
    elif role == "story_editor":
        paths = [Path(metadata["story_path"])]
    elif role == "candidate_mapper":
        paths = [
            Path(metadata["story_path"]), Path(metadata["review_path"]), Path(metadata["kernel_path"]),
            output_dir / 'target_profile.json', schema,
        ]
    else:
        paths = [
            output_dir / f"clustered_representatives_r{metadata.get('round', 0)}.json",
            output_dir / "review_evidence_slice.json", output_dir / "target_profile.json", schema,
        ]
    return [str(path.resolve()) for path in paths]



def create_job(
    role: str, claim: dict[str, Any], output_dir: Path, round_no: int, *, repair_hint: str = "",
    metadata: dict[str, Any] | None = None, attempt: int | None = None,
) -> dict[str, Any]:
    metadata = dict(metadata or {})
    attempt = attempt if attempt is not None else round_no + 1
    token = str(metadata.get("candidate_id") or metadata.get("branch_id") or role)
    token = re.sub(r"[^A-Za-z0-9_.-]", "-", token)
    job_id = f"{claim['run_id']}-{role}-{token}-r{round_no}-a{attempt}"
    suffix = ".txt" if role in {"story_creator", "story_editor"} else ".json"
    raw_path = output_dir / "raw" / f"{role}-{token}-r{round_no}-a{attempt}{suffix}"
    prompt = job_prompt(
        role, claim, output_dir, raw_path, round_no, repair_hint=repair_hint, metadata=metadata,
    )
    result = {
        "job_id": job_id,
        "role": role,
        "stage": role_stage(role),
        "attempt": attempt,
        "round": round_no,
        "raw_output": str(raw_path),
        "prompt": prompt,
        "status": "pending",
        "input_paths": job_input_paths(role, output_dir, {**metadata, "round": round_no}),
    }
    result.update(metadata)
    return result


def public_state(claim_path: Path, state: dict[str, Any]) -> dict[str, Any]:
    action_keys = (
        "job_id", "role", "attempt", "round", "raw_output", "prompt",
        "candidate_id", "kernel_id", "branch_id", "story_attempt", "input_paths",
    )
    pending = [row for row in state.get("jobs", []) if row.get("status") == "pending"]
    if any(row.get("stage") in {"S2_STORY", "S2_EDIT", "S2_MAP"} for row in pending):
        pending = pending[:MAX_CANDIDATE_CONCURRENCY]
    actions = [
        {key: row[key] for key in action_keys if key in row}
        for row in pending
    ]
    public_status = state["status"]
    if public_status == "running" and not lease_is_valid(state):
        public_status = "paused"
    result = {
        "production_contract_version": CONTRACT_VERSION,
        "run_id": state["run_id"],
        "status": public_status,
        "stage": state["stage"],
        "claim": str(claim_path.resolve()),
        "gap_fill_round": state["gap_fill_round"],
        "generated_count": state.get("generated_count", 0),
        "passed_review_count": state.get("passed_review_count", 0),
        "selected_for_delivery_count": state.get("selected_for_delivery_count", 0),
        "usable_candidate_count": state.get("usable_candidate_count", 0),
        "execution_profile": state.get("execution_profile"),
        "kernels_per_branch": state.get("kernels_per_branch"),
        "recovery_budget": state.get("recovery_budget"),
        "call_budget": state.get("call_budget"),
        "pool_input": state.get("pool_input"),
        "actions": actions,
        "instruction": "Run the deterministic candidate executor; the main agent must not dispatch or author actions."
        if actions else None,
    }
    if state["status"] == "awaiting_user_choice":
        result.update({"cards": state["artifacts"]["cards"], "candidate_count": state["candidate_count"]})
    if state["status"] == "candidate_generation_failed":
        result["failures"] = state.get("failures", [])
    elif state.get("failures"):
        result["recovery_reasons"] = state["failures"]
    return result


def validate_pool_atom_bundle(packet: dict[str, Any], bundle: dict[str, Any], lane: str) -> tuple[dict[str, Any], dict[str, Any]]:
    packet_hash = portfolio.validate_packet(packet, lane)
    failures, audit = portfolio.atom_failures(packet, bundle, lane)
    if failures:
        raise ValueError("POOL_ATOM_GATE:" + json.dumps(failures, ensure_ascii=False))
    if bundle.get("evidence_packet_hash") != packet_hash:
        raise ValueError("POOL_SCAN_SNAPSHOT_MISMATCH")
    return bundle, audit


def materialize_pool_atoms(
    packet: dict[str, Any], bundle: dict[str, Any], profile: dict[str, Any], claim: dict[str, Any],
    output_dir: Path, state: dict[str, Any], source_path: Path,
) -> None:
    bundle, audit = validate_pool_atom_bundle(packet, bundle, claim["lane"])
    atom_path = write_artifact(output_dir, "evidence_atoms.json", bundle)
    audit_path = write_artifact(output_dir, "evidence_atom_audit.json", audit)
    contexts = portfolio.build_contexts(packet, bundle, profile, claim["lane"], claim["run_id"])
    contexts_path = write_artifact(output_dir, "generation_contexts.json", contexts)
    state["artifacts"].update({
        "atoms": str(atom_path), "atom_audit": str(audit_path), "contexts": str(contexts_path),
    })
    state["pool_input"] = {
        "kind": "atom_bundle", "source_hash": file_sha256(source_path),
        "scan_snapshot_hash": claim["evidence_packet_hash"],
        "validity_policy": "valid_until_replaced_by_a_new_scan_snapshot",
        "automatic_age_expiry": False,
    }


def materialize_kernel_bundle(
    packet: dict[str, Any], bundle: dict[str, Any], profile: dict[str, Any], claim: dict[str, Any],
    output_dir: Path, state: dict[str, Any], source_path: Path,
) -> None:
    if (
        bundle.get("stage") != "candidate_kernel_bundle"
        or bundle.get("lane") != claim["lane"]
        or bundle.get("evidence_packet_hash") != claim["evidence_packet_hash"]
        or bundle.get("scan_snapshot_hash") != claim["evidence_packet_hash"]
        or not portfolio.verify_seal(bundle)
    ):
        raise ValueError("POOL_KERNEL_BUNDLE_INVALID")
    atom_bundle = bundle.get("atom_bundle")
    if not isinstance(atom_bundle, dict):
        raise ValueError("POOL_KERNEL_ATOMS_MISSING")
    materialize_pool_atoms(packet, atom_bundle, profile, claim, output_dir, state, source_path)
    contexts = load_json(Path(state["artifacts"]["contexts"]))["contexts"]
    branches = bundle.get("branches")
    if not isinstance(branches, dict) or set(branches) != set(portfolio.BRANCH_ROLES):
        raise ValueError("POOL_KERNEL_BRANCH_SET_INVALID")
    for branch in sorted(portfolio.BRANCH_ROLES):
        normalized, failures = normalize_kernel_payload(
            {"concept_kernels": branches[branch]}, branch, list(contexts[branch]["input_atom_ids"]),
            exact_count=int(claim["kernels_per_branch"]),
        )
        if failures:
            raise ValueError("POOL_KERNEL_GATE:" + json.dumps(failures, ensure_ascii=False))
        payload = portfolio.seal({
            **normalized, "stage": "concept_kernel_generation", "schema_version": portfolio.SCHEMA_VERSION,
            "lane": claim["lane"], "run_id": claim["run_id"], "branch_id": branch,
            "generator_role": contexts[branch]["generator_role"], "context_hash": contexts[branch]["output_hash"],
            "input_atom_ids": contexts[branch]["input_atom_ids"],
            "evidence_packet_hash": claim["evidence_packet_hash"],
            "target_profile_hash": profile["output_hash"], "independent_context": True,
            "visible_branch_ids": [branch],
        })
        artifact = write_artifact(output_dir, f"kernel_generation_{branch}_r0.json", payload)
        state["artifacts"].setdefault("kernel_branches", {})[branch] = str(artifact)
        state["receipts"].append({
            "job_id": f"{claim['run_id']}-pool-kernel-{branch}", "role": f"generation_{branch}",
            "session_id": f"pool:{branch}:{claim['run_id']}", "attempt": 0, "round": 0,
            "artifact_path": str(artifact), "artifact_hash": payload["output_hash"],
            "raw_file_sha256": file_sha256(artifact), "accepted_at": utc_now(),
        })
    state["pool_input"].update({"kind": "kernel_bundle", "source_hash": file_sha256(source_path)})
    schedule_story_tracks(state, claim, output_dir)


def discover_pool_atom_bundle(
    base_root: Path, packet: dict[str, Any], lane: str,
) -> Path | None:
    """Find the newest valid atom pool for this exact frozen scan snapshot."""
    runs_root = canonical_path(base_root / "candidate_runs")
    filesystem_root = win_long_path(runs_root)
    if not filesystem_root.is_dir():
        return None
    candidates = [
        path for path in filesystem_root.glob("cand-*/*/evidence_atoms.json")
        if path.is_file()
    ]
    candidates.sort(key=lambda path: path.stat().st_mtime_ns, reverse=True)
    for filesystem_candidate in candidates:
        candidate = canonical_path(filesystem_candidate)
        try:
            validate_pool_atom_bundle(packet, load_json(candidate), lane)
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            continue
        return candidate
    return None


def init_run(
    base_root: Path, packet_path: Path, lane: str, platform_name: str, channel: str,
    execution_profile: str = "production", atom_bundle_path: Path | None = None,
    kernel_bundle_path: Path | None = None,
) -> dict[str, Any]:
    if execution_profile not in EXECUTION_PROFILES:
        raise ValueError("EXECUTION_PROFILE_INVALID")
    if atom_bundle_path and kernel_bundle_path:
        raise ValueError("POOL_INPUTS_MUTUALLY_EXCLUSIVE")
    packet = load_json(packet_path)
    packet_hash = portfolio.validate_packet(packet, lane)
    profile = portfolio.make_profile(lane, "general", platform_name, channel)
    run_id = f"cand-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    output_dir = (base_root.resolve() / "candidate_runs" / run_id / profile["profile_slug"]).resolve()
    win_long_path(output_dir).mkdir(parents=True, exist_ok=False)
    bundle = bundle_fingerprint()
    snapshot_manifest = snapshot_bundle(output_dir)
    if bundle["bundle_files"] != snapshot_manifest:
        raise ValueError("BUNDLE_SNAPSHOT_HASH_MISMATCH")
    claim = portfolio.seal({
        "stage": "candidate_run_claim", "schema_version": 1,
        "production_contract_version": CONTRACT_VERSION, "run_id": run_id, "lane": lane,
        "output_dir": str(output_dir), "target_profile_hash": profile["output_hash"],
        "evidence_packet_hash": packet_hash,
        "execution_profile": execution_profile,
        "kernels_per_branch": EXECUTION_PROFILES[execution_profile]["kernels_per_branch"],
        "bundle_hash": bundle["bundle_hash"], "bundle_files": snapshot_manifest,
        "created_at": utc_now(),
    })
    save_exclusive(output_dir / "target_profile.json", profile)
    save_exclusive(output_dir / "evidence_packet.json", packet)
    save_exclusive(output_dir / "evidence_compact_view.json", compact_evidence_view(packet, lane, seed=run_id))
    save_exclusive(output_dir / "candidate_run_claim.json", claim)
    state = {
        "production_contract_version": CONTRACT_VERSION, "run_id": run_id, "status": "paused",
        "stage": "S1_ATOMS", "gap_fill_round": 0, "format_retries_used": {},
        "jobs": [],
        "receipts": [], "artifacts": {}, "failures": [], "created_at": utc_now(), "updated_at": utc_now(),
        "generated_count": 0, "passed_review_count": 0,
        "selected_for_delivery_count": 0, "usable_candidate_count": 0,
        "candidate_tracks": {}, "branch_supplement_rounds": {branch: 0 for branch in portfolio.BRANCH_ROLES},
        "execution_profile": execution_profile,
        "kernels_per_branch": int(claim["kernels_per_branch"]),
        "recovery_budget": {"limit": RECOVERY_CALL_BUDGET, "used": 0, "events": []},
        "call_budget": {
            "expected_base_calls": EXECUTION_PROFILES[execution_profile]["expected_base_calls"],
            "warning_threshold": CALL_WARNING_THRESHOLD, "hard_fuse": CALL_FUSE_THRESHOLD,
            "calls_started": 0, "calls": [],
        },
    }
    if kernel_bundle_path:
        materialize_kernel_bundle(
            packet, load_json(kernel_bundle_path), profile, claim, output_dir, state, kernel_bundle_path,
        )
        state["pool_input"]["selection"] = "explicit"
        state["call_budget"]["expected_base_calls"] -= 4
    elif atom_bundle_path:
        materialize_pool_atoms(
            packet, load_json(atom_bundle_path), profile, claim, output_dir, state, atom_bundle_path,
        )
        state["pool_input"]["selection"] = "explicit"
        state["call_budget"]["expected_base_calls"] -= 1
        schedule_generation(state, claim, output_dir)
    else:
        state["jobs"].append(create_job("atoms", claim, output_dir, 0))
    save_state(output_dir / "controller_state.json", state)
    append_manifest(output_dir, {"event": "run_initialized", "run_id": run_id, "packet_hash": packet_hash})
    return public_state(output_dir / "candidate_run_claim.json", state)


def kernel_idea_has_content(kernel: dict[str, Any]) -> bool:
    ignored = {"kernel_id", "cited_atom_ids", "output_hash"}

    def text_values(value: Any) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [text for item in value for text in text_values(item)]
        if isinstance(value, dict):
            return [
                text
                for key, item in value.items()
                if key not in ignored
                for text in text_values(item)
            ]
        return []

    return any(
        portfolio.substantive(value) and not portfolio.low_information(value)
        for key, item in kernel.items()
        if key not in ignored
        for value in text_values(item)
    )


def kernel_failures(
    payload: dict[str, Any], branch: str, *, minimum_count: int = 3,
    exact_count: int | None = None,
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    kernels = payload.get("concept_kernels")
    if exact_count is not None and (not isinstance(kernels, list) or len(kernels) != exact_count):
        return [{"reason": "CONCEPT_KERNEL_COUNT_NOT_EXACT", "branch_id": branch, "expected": exact_count}]
    if exact_count is None and (not isinstance(kernels, list) or len(kernels) < minimum_count):
        return [{"reason": "CONCEPT_KERNEL_COUNT_INSUFFICIENT", "branch_id": branch}]
    for kernel in kernels:
        if not isinstance(kernel, dict):
            failures.append({"reason": "CONCEPT_KERNEL_NOT_OBJECT", "branch_id": branch})
        elif not kernel_idea_has_content(kernel):
            failures.append({"reason": "CONCEPT_KERNEL_CONTENT_EMPTY", "branch_id": branch})
    return failures


def normalize_kernel_payload(
    payload: dict[str, Any], branch: str, input_atom_ids: list[str],
    *, minimum_count: int = 3, exact_count: int | None = None,
    existing_kernel_ids: set[str] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    normalized = dict(payload)
    kernels = payload.get("concept_kernels")
    failures = kernel_failures(payload, branch, minimum_count=minimum_count, exact_count=exact_count)
    if not isinstance(kernels, list):
        return normalized, failures
    used = set(existing_kernel_ids or set())
    normalized_kernels: list[Any] = []
    next_index = 1
    for kernel in kernels:
        if not isinstance(kernel, dict):
            normalized_kernels.append(kernel)
            continue
        result = dict(kernel)
        requested_id = str(result.get("kernel_id") or "").strip()
        if requested_id and requested_id not in used:
            kernel_id = requested_id
        else:
            while f"{branch}-K{next_index:02d}" in used:
                next_index += 1
            kernel_id = f"{branch}-K{next_index:02d}"
            next_index += 1
        used.add(kernel_id)
        result["kernel_id"] = kernel_id
        result["cited_atom_ids"] = list(input_atom_ids)
        normalized_kernels.append(result)
    normalized["concept_kernels"] = normalized_kernels
    return normalized, failures

def make_receipt(job: dict[str, Any], session_id: str, artifact_path: Path, artifact_hash: str) -> dict[str, Any]:
    return {
        "job_id": job["job_id"], "role": job["role"], "session_id": session_id,
        "attempt": job["attempt"], "round": job["round"], "artifact_path": str(artifact_path),
        "artifact_hash": artifact_hash, "raw_file_sha256": file_sha256(Path(job["raw_output"])),
        "accepted_at": utc_now(),
    }


def write_artifact(output_dir: Path, filename: str, payload: dict[str, Any]) -> Path:
    path = output_dir / filename
    save_exclusive(path, payload)
    return path



def write_text_artifact(output_dir: Path, filename: str, content: str) -> Path:
    path = canonical_path(output_dir / filename)
    filesystem_path = win_long_path(path)
    filesystem_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with filesystem_path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(content.rstrip() + "\n")
    except FileExistsError:
        with filesystem_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(content.rstrip() + "\n")
    return path


def platform_for_source(source: dict[str, Any], source_id: str) -> str:
    explicit = str(source.get("platform") or source.get("platform_id") or "").strip()
    if explicit:
        return explicit
    lowered = source_id.casefold()
    for platform_name in (
        "fanqie", "qimao", "xiaohongshu", "bilibili", "qidian", "jjwxc", "zongheng",
    ):
        if platform_name in lowered:
            return platform_name
    return source_id or "frozen_source"


def inject_atom_deterministic_fields(
    raw: Any, claim: dict[str, Any], packet: dict[str, Any],
) -> dict[str, Any]:
    if isinstance(raw, list):
        atoms = raw
    elif isinstance(raw, dict) and isinstance(raw.get("atoms"), list):
        atoms = raw["atoms"]
    else:
        atoms = []
    evidence = portfolio.evidence_index(packet)
    source_to_cohort, _ = portfolio.cohort_index(packet)
    normalized: list[dict[str, Any]] = []
    for index, atom in enumerate(atoms, 1):
        if not isinstance(atom, dict):
            normalized.append(atom)
            continue
        evidence_id = str(atom.get("evidence_id") or "")
        source = evidence.get(evidence_id, {})
        source_id = str(source.get("source_id") or source.get("manifest_id") or "")
        source_item_id = str(source.get("source_item_id") or "")
        counters = atom.get("counter_evidence_ids")
        contradictions = atom.get("contradicting_atom_ids")
        raw_atom_type = str(atom.get("atom_type") or "").strip().lower()
        atom_type = next(
            (
                valid for valid in portfolio.ATOM_TYPES
                if raw_atom_type == valid
                or valid in raw_atom_type
                or (raw_atom_type and raw_atom_type in valid)
            ),
            "desire",
        )
        raw_confidence = atom.get("confidence")
        if isinstance(raw_confidence, (int, float)) and not isinstance(raw_confidence, bool):
            confidence = min(1.0, max(0.0, float(raw_confidence)))
        else:
            confidence_text = str(raw_confidence or "").strip().lower()
            confidence = {
                "high": 0.85,
                "medium": 0.65,
                "low": 0.4,
            }.get(confidence_text, 0.6)
        normalized.append({
            "atom_id": f"atom-{index:04d}-{hashlib.sha256(evidence_id.encode('utf-8')).hexdigest()[:8]}",
            "lane": claim["lane"],
            "atom_type": atom_type,
            "evidence_id": evidence_id,
            "source_item_id": source_item_id,
            "source_id": source_id,
            "source_cohort": portfolio.cohort_for_source(source_to_cohort, source_id) or "",
            "platform": platform_for_source(source, source_id),
            "channel": str(source.get("channel") or "neutral"),
            "channel_basis": str(source.get("channel_basis") or "neutral_default"),
            "observation": atom.get("observation"),
            "inference": atom.get("inference"),
            "confidence": confidence,
            "freshness": str(
                source.get("freshness") or source.get("captured_at")
                or source.get("published_at") or "current_run"
            ),
            "claim_key": atom.get("claim_key"),
            "stance": atom.get("stance"),
            "supporting_evidence_ids": [evidence_id] if evidence_id else [],
            "counter_evidence_ids": list(counters) if isinstance(counters, list) else [],
            "contradicting_atom_ids": list(contradictions) if isinstance(contradictions, list) else [],
            "generation_safe": True,
        })
    return {
        "stage": "evidence_atoms",
        "schema_version": portfolio.SCHEMA_VERSION,
        "lane": claim["lane"],
        "run_id": claim["run_id"],
        "evidence_packet_hash": claim["evidence_packet_hash"],
        "input_hash": claim["evidence_packet_hash"],
        "atoms": normalized,
    }


def register_kernel_track(
    state: dict[str, Any], claim: dict[str, Any], output_dir: Path, branch: str,
    kernel: dict[str, Any], candidate_index: int, *, supplemental: bool = False,
) -> dict[str, Any]:
    candidate_id = f"{branch}-C{candidate_index:02d}"
    kernel_payload = portfolio.seal({
        "stage": "concept_kernel",
        "schema_version": portfolio.SCHEMA_VERSION,
        "lane": claim["lane"],
        "run_id": claim["run_id"],
        "branch_id": branch,
        "candidate_id": candidate_id,
        "kernel": kernel,
        "supplemental": supplemental,
    })
    kernel_path = write_artifact(output_dir, f"kernel_{candidate_id}.json", kernel_payload)
    track = {
        "candidate_id": candidate_id,
        "kernel_id": str(kernel.get("kernel_id") or ""),
        "branch_id": branch,
        "kernel_path": str(kernel_path),
        "status": "awaiting_story",
        "story_attempt": 1,
        "supplemental": supplemental,
        "mapper_retries": 0,
    }
    state["candidate_tracks"][candidate_id] = track
    state["jobs"].append(create_job(
        "story_creator", claim, output_dir, state["gap_fill_round"],
        metadata={
            "candidate_id": candidate_id,
            "kernel_id": track["kernel_id"],
            "branch_id": branch,
            "kernel_path": str(kernel_path),
            "story_attempt": 1,
        },
        attempt=1,
    ))
    return track


def schedule_story_tracks(
    state: dict[str, Any], claim: dict[str, Any], output_dir: Path,
) -> None:
    state["candidate_tracks"] = {}
    for branch in sorted(portfolio.BRANCH_ROLES):
        artifact = load_json(Path(latest_receipt(state, f"generation_{branch}")["artifact_path"]))
        kernels = artifact.get("concept_kernels") or []
        for index, kernel in enumerate(kernels, 1):
            register_kernel_track(state, claim, output_dir, branch, kernel, index)
    state["stage"] = "S2_STORY"


def schedule_story_retry(
    state: dict[str, Any], claim: dict[str, Any], output_dir: Path,
    track: dict[str, Any], feedback: str,
) -> bool:
    if not reserve_recovery_call(
        state, "story_rewrite", candidate_id=track["candidate_id"], branch_id=track["branch_id"],
    ):
        track["status"] = "eliminated"
        state.setdefault("story_failures", []).append({
            "reason": "RECOVERY_CALL_BUDGET_EXHAUSTED",
            "candidate_id": track["candidate_id"], "branch_id": track["branch_id"],
        })
        return False
    track["story_attempt"] += 1
    track["status"] = "awaiting_story"
    state["jobs"].append(create_job(
        "story_creator", claim, output_dir, state["gap_fill_round"],
        metadata={
            "candidate_id": track["candidate_id"],
            "kernel_id": track["kernel_id"],
            "branch_id": track["branch_id"],
            "kernel_path": track["kernel_path"],
            "story_attempt": track["story_attempt"],
            "feedback": feedback,
        },
        attempt=track["story_attempt"],
    ))
    state["stage"] = "S2_STORY"
    return True


def schedule_kernel_supplement(
    state: dict[str, Any], claim: dict[str, Any], output_dir: Path, branch: str,
    *, force: bool = False, reason: str = 'track_shortage',
) -> bool:
    active = [
        track for track in state["candidate_tracks"].values()
        if track["branch_id"] == branch and track["status"] != "eliminated"
    ]
    used = int(state["branch_supplement_rounds"].get(branch, 0))
    pending = any(
        job.get("role") == f"kernel_supplement_{branch}" and job.get("status") == "pending"
        for job in state["jobs"]
    )
    target = int(state.get("kernels_per_branch", 3))
    if (
        (not force and len(active) >= target)
        or used >= MAX_KERNEL_SUPPLEMENT_ROUNDS
        or (pending and not force)
    ):
        return False
    if not reserve_recovery_call(state, "kernel_supplement", branch_id=branch):
        return False
    state["branch_supplement_rounds"][branch] = used + 1
    kernel_artifact = latest_receipt(state, f"generation_{branch}")["artifact_path"]
    state["jobs"].append(create_job(
        f"kernel_supplement_{branch}", claim, output_dir, state["gap_fill_round"],
        metadata={
            'branch_id': branch, 'kernel_artifact': kernel_artifact,
            'supplement_reason': reason,
        },
        attempt=used + 1,
    ))
    state["stage"] = "S2_KERNELS"
    return True


def maybe_schedule_supplement(
    state: dict[str, Any], claim: dict[str, Any], output_dir: Path, branch: str,
) -> bool:
    return schedule_kernel_supplement(state, claim, output_dir, branch)


def schedule_portfolio_recovery(
    state: dict[str, Any], claim: dict[str, Any], output_dir: Path,
    gate: dict[str, Any], failures: list[dict[str, Any]],
) -> bool:
    '''Preserve qualified tracks and create only the missing S4 concepts.'''
    vetoed = {str(value) for value in gate.get('vetoed_candidate_ids') or []}
    frontier = {str(value) for value in gate.get('pareto_frontier_ids') or []}
    tracks = state.get('candidate_tracks') or {}
    veto_branches: list[str] = []
    for candidate_id in sorted(vetoed):
        track = tracks.get(candidate_id)
        if not isinstance(track, dict):
            continue
        branch = str(track.get('branch_id') or '')
        if branch in portfolio.BRANCH_ROLES and branch not in veto_branches:
            veto_branches.append(branch)
        track['status'] = 'eliminated'
        track['elimination_finding'] = 'S3 reviewer veto; excluded from S4 recovery.'

    survivor_counts = {branch: 0 for branch in portfolio.BRANCH_ROLES}
    for candidate_id in frontier:
        track = tracks.get(candidate_id)
        if isinstance(track, dict) and track.get('branch_id') in survivor_counts:
            survivor_counts[str(track['branch_id'])] += 1

    failure_codes = {str(row.get('reason') or '') for row in failures}
    needed = max(1, 4 - len(frontier))
    if 'FINAL_STRATEGY_DIVERSITY_INSUFFICIENT' in failure_codes:
        needed = max(needed, 2 - sum(1 for value in survivor_counts.values() if value))
    if 'FINAL_MECHANISM_DIVERSITY_INSUFFICIENT' in failure_codes:
        needed = max(needed, 1)

    active_counts = {
        branch: sum(
            1 for track in tracks.values()
            if track.get('branch_id') == branch and track.get('status') != 'eliminated'
        )
        for branch in portfolio.BRANCH_ROLES
    }
    post_story_minimum = max(2, int(claim.get('kernels_per_branch', 3)) - 1)
    needed = max(
        needed,
        sum(max(0, post_story_minimum - active_counts[branch]) for branch in portfolio.BRANCH_ROLES),
    )
    branch_order: list[str] = []
    for branch in sorted(portfolio.BRANCH_ROLES):
        branch_order.extend([branch] * max(0, post_story_minimum - active_counts[branch]))
    for branch in veto_branches:
        if branch not in branch_order:
            branch_order.append(branch)
    for branch in sorted(portfolio.BRANCH_ROLES, key=lambda value: (survivor_counts[value], value)):
        if branch not in branch_order:
            branch_order.append(branch)

    original_round = int(state['gap_fill_round'])
    state['gap_fill_round'] = original_round + 1
    scheduled: list[str] = []
    for branch in branch_order:
        if len(scheduled) >= needed:
            break
        if schedule_kernel_supplement(
            state, claim, output_dir, branch, force=True, reason='portfolio_gap_fill',
        ):
            scheduled.append(branch)
    if not scheduled:
        state['gap_fill_round'] = original_round
        return False

    state['failures'] = failures
    recovery = {
        'round': state['gap_fill_round'],
        'preserved_candidate_ids': sorted(frontier),
        'eliminated_candidate_ids': sorted(vetoed),
        'supplement_branches': scheduled,
        'failure_reasons': sorted(failure_codes),
    }
    state.setdefault('portfolio_recoveries', []).append(recovery)
    append_manifest(output_dir, {'event': 'portfolio_targeted_recovery_scheduled', **recovery})
    return True


def eliminate_track(
    state: dict[str, Any], claim: dict[str, Any], output_dir: Path,
    track: dict[str, Any], finding: str, *,
    failure_reason: str = "STORY_REVIEW_REJECTED_AFTER_REWRITE",
    failure_bucket: str = "story_failures",
    details: list[dict[str, Any]] | None = None,
) -> None:
    track["status"] = "eliminated"
    track["elimination_finding"] = finding
    failure = {
        "reason": failure_reason,
        "candidate_id": track["candidate_id"],
        "kernel_id": track["kernel_id"],
        "branch_id": track["branch_id"],
        "finding": finding,
    }
    if details:
        failure["details"] = details
    state.setdefault(failure_bucket, []).append(failure)
    maybe_schedule_supplement(state, claim, output_dir, track["branch_id"])


def accept_story_creator(
    raw_text: str, job: dict[str, Any], output_dir: Path, state: dict[str, Any],
) -> tuple[Path, str]:
    story = raw_text.lstrip("\ufeff").strip()
    if not story:
        raise ValueError("STORY_OUTPUT_EMPTY")
    candidate_id = job["candidate_id"]
    attempt = int(job["story_attempt"])
    story_path = write_text_artifact(output_dir, f"story_{candidate_id}_a{attempt}.txt", story)
    story_hash = portfolio.canonical_hash(story)
    track = state["candidate_tracks"][candidate_id]
    track.update({
        "status": "awaiting_review",
        "story_path": str(story_path),
        "story_hash": story_hash,
        "story_han_characters": len(re.findall(r"[\u3400-\u9fff]", story)),
    })
    return story_path, story_hash


def accept_story_review(
    raw_text: str, job: dict[str, Any], claim: dict[str, Any],
    output_dir: Path, state: dict[str, Any],
) -> tuple[Path, dict[str, Any]]:
    finding = raw_text.lstrip("\ufeff").strip()
    if not finding:
        finding = "编辑未返回判断，读者需要脑补审稿结论。"
    track = state["candidate_tracks"][job["candidate_id"]]
    passed = portfolio.story_review_passed(finding)
    review = portfolio.seal({
        "stage": "story_review",
        "schema_version": portfolio.SCHEMA_VERSION,
        "lane": claim["lane"],
        "run_id": claim["run_id"],
        "candidate_id": track["candidate_id"],
        "kernel_id": track["kernel_id"],
        "story_hash": track["story_hash"],
        "status": "passed" if passed else "rejected",
        "review_text": finding,
        "reviewer_does_not_complete_story": True,
    })
    review_path = write_artifact(
        output_dir,
        f"story_review_{track['candidate_id']}_a{track['story_attempt']}.json",
        review,
    )
    track.update({
        "review_path": str(review_path),
        "review_hash": review["output_hash"],
        "review_text": finding,
    })
    if passed:
        track["status"] = "awaiting_mapping"
        state["jobs"].append(create_job(
            "candidate_mapper", claim, output_dir, state["gap_fill_round"],
            metadata={
                "candidate_id": track["candidate_id"],
                "kernel_id": track["kernel_id"],
                "branch_id": track["branch_id"],
                "kernel_path": track["kernel_path"],
                "story_path": track["story_path"],
                "review_path": track["review_path"],
                "story_attempt": track["story_attempt"],
            },
            attempt=1,
        ))
        state["stage"] = "S2_MAP"
    elif track["story_attempt"] <= MAX_STORY_REWRITES and schedule_story_retry(
        state, claim, output_dir, track, finding,
    ):
        pass
    else:
        eliminate_track(state, claim, output_dir, track, finding)
    return review_path, review


def accept_candidate_mapping(
    raw: dict[str, Any], job: dict[str, Any], claim: dict[str, Any],
    profile: dict[str, Any], output_dir: Path, state: dict[str, Any],
) -> tuple[Path, dict[str, Any]]:
    track = state["candidate_tracks"][job["candidate_id"]]
    candidate = raw.get("candidate") if isinstance(raw.get("candidate"), dict) else dict(raw)
    contexts = load_json(Path(state["artifacts"]["contexts"]))["contexts"]
    context = contexts[track["branch_id"]]
    story = win_long_path(Path(track["story_path"])).read_text(encoding="utf-8").strip()
    review = load_json(Path(track["review_path"]))
    candidate["candidate_id"] = track["candidate_id"]
    candidate["kernel_id"] = track["kernel_id"]
    candidate["generator_branch"] = track["branch_id"]
    candidate["story_proposal"] = story
    candidate["story_review"] = review
    candidate["story_trace"] = {
        "candidate_id": track["candidate_id"],
        "kernel_id": track["kernel_id"],
        "story_hash": track["story_hash"],
        "review_hash": track["review_hash"],
        "mapping_input_hash": portfolio.canonical_hash({
            "candidate_id": track["candidate_id"],
            "kernel_id": track["kernel_id"],
            "story_hash": track["story_hash"],
            "review_hash": track["review_hash"],
        }),
    }
    wrapper = inject_deterministic_fields(
        {"candidates": [candidate]}, f"generation_{track['branch_id']}",
        claim, profile, context,
    )
    candidate = wrapper["candidates"][0]
    failures = [
        {"reason": reason, "candidate_id": track["candidate_id"]}
        for reason in portfolio.candidate_card_shape_failures(candidate, claim["lane"], profile)
    ]
    fingerprint = candidate.get("structural_fingerprint")
    required = set(portfolio.FINGERPRINT_CORE + portfolio.FINGERPRINT_EXTRAS[claim["lane"]])
    if not isinstance(fingerprint, dict) or any(not portfolio.substantive(fingerprint.get(key)) for key in required):
        failures.append({
            "reason": "CANDIDATE_STRUCTURAL_FINGERPRINT_INCOMPLETE",
            "candidate_id": track["candidate_id"],
        })
    failures.extend(portfolio.story_contract_failures(candidate))
    if failures:
        raise ValueError("MAPPING_GATE:" + json.dumps(failures, ensure_ascii=False))
    payload = portfolio.seal({
        "stage": "candidate_mapping",
        "schema_version": portfolio.SCHEMA_VERSION,
        "lane": claim["lane"],
        "run_id": claim["run_id"],
        "candidate_id": track["candidate_id"],
        "story_hash": track["story_hash"],
        "review_hash": track["review_hash"],
        "candidate": candidate,
    })
    mapping_path = write_artifact(output_dir, f"candidate_mapping_{track['candidate_id']}.json", payload)
    track.update({
        "status": "mapped",
        "mapping_path": str(mapping_path),
        "mapping_hash": payload["output_hash"],
    })
    return mapping_path, payload


def handle_mapping_failure(
    state: dict[str, Any], claim: dict[str, Any], output_dir: Path,
    job: dict[str, Any], failures: list[dict[str, Any]],
) -> None:
    track = state["candidate_tracks"][job["candidate_id"]]
    # Every consumed mapper result is terminal for that job. A retry, when
    # permitted, is a new job; otherwise the track is eliminated. Leaving the
    # old job pending would redispatch the same model call until the hard fuse.
    job["status"] = "superseded"
    if track["mapper_retries"] < MAX_FORMAT_RETRIES and reserve_recovery_call(
        state, "mapper_format_repair", candidate_id=track["candidate_id"], branch_id=track["branch_id"],
    ):
        track["mapper_retries"] += 1
        metadata = {
            key: job[key] for key in (
                "candidate_id", "kernel_id", "branch_id", "kernel_path",
                "story_path", "review_path", "story_attempt",
            )
        }
        repair_hint = "; ".join(sorted({str(row.get("reason") or "") for row in failures}))
        state["jobs"].append(create_job(
            "candidate_mapper", claim, output_dir, state["gap_fill_round"],
            metadata=metadata, attempt=track["mapper_retries"] + 1, repair_hint=repair_hint,
        ))
        state["stage"] = "S2_MAP"
    else:
        had_retry = track["mapper_retries"] > 0
        eliminate_track(
            state, claim, output_dir, track,
            (
                "候选卡映射在一次修复后仍不满足公开字段契约。"
                if had_retry else
                "候选卡映射不满足公开字段契约，且共享恢复预算已耗尽，未执行映射修复。"
            ),
            failure_reason=(
                "MAPPING_GATE_REJECTED_AFTER_RETRY"
                if had_retry else "MAPPING_GATE_REJECTED_RECOVERY_UNAVAILABLE"
            ),
            failure_bucket="mapping_failures",
            details=failures,
        )


def accept_kernel_supplement(
    raw: dict[str, Any], job: dict[str, Any], claim: dict[str, Any],
    output_dir: Path, state: dict[str, Any],
) -> tuple[Path, dict[str, Any]]:
    branch = job["branch_id"]
    kernel = raw.get("concept_kernel") if isinstance(raw.get("concept_kernel"), dict) else raw
    existing_kernel_ids = {
        track["kernel_id"] for track in state["candidate_tracks"].values()
        if track["branch_id"] == branch
    }
    context = load_json(Path(state["artifacts"]["contexts"]))["contexts"][branch]
    normalized, failures = normalize_kernel_payload(
        {"concept_kernels": [kernel]}, branch, list(context["input_atom_ids"]),
        minimum_count=1, existing_kernel_ids=existing_kernel_ids,
    )
    if failures:
        raise ValueError("SUPPLEMENT_GATE:" + json.dumps(failures, ensure_ascii=False))
    kernel = normalized["concept_kernels"][0]
    payload = portfolio.seal({
        "stage": "kernel_supplement",
        "schema_version": portfolio.SCHEMA_VERSION,
        "lane": claim["lane"],
        "run_id": claim["run_id"],
        "branch_id": branch,
        "concept_kernel": kernel,
    })
    artifact = write_artifact(
        output_dir,
        f'kernel_supplement_{branch}_r{job["round"]}_a{job["attempt"]}.json',
        payload,
    )
    indices = [
        int(track["candidate_id"].split("C")[-1])
        for track in state["candidate_tracks"].values() if track["branch_id"] == branch
    ]
    register_kernel_track(
        state, claim, output_dir, branch, kernel, max(indices, default=0) + 1, supplemental=True,
    )
    return artifact, payload


def build_story_first_branches(
    state: dict[str, Any], claim: dict[str, Any], profile: dict[str, Any], output_dir: Path,
) -> list[dict[str, Any]]:
    contexts = load_json(Path(state["artifacts"]["contexts"]))["contexts"]
    branches: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for branch in sorted(portfolio.BRANCH_ROLES):
        kernel_artifact = load_json(Path(latest_receipt(state, f"generation_{branch}")["artifact_path"]))
        candidates = []
        for track in sorted(state["candidate_tracks"].values(), key=lambda row: row["candidate_id"]):
            if track["branch_id"] != branch or track["status"] != "mapped":
                continue
            candidate = load_json(Path(track["mapping_path"]))["candidate"]
            candidates.append(candidate)
        raw = {
            "concept_kernels": list(kernel_artifact.get("concept_kernels") or []),
            "candidates": candidates,
        }
        payload = portfolio.seal(inject_deterministic_fields(
            raw, f"generation_{branch}", claim, profile, contexts[branch],
        ))
        branch_failures = portfolio.branch_failures(
            payload, contexts[branch], profile, claim["lane"], max(2, int(claim["kernels_per_branch"]) - 1),
        )
        failures.extend(branch_failures)
        if branch_failures:
            continue
        artifact = write_artifact(
            output_dir, f"generation_{branch}_story_first_r{state['gap_fill_round']}.json", payload,
        )
        receipt = {
            "job_id": f"{claim['run_id']}-story-first-branch-{branch}",
            "role": f"generation_{branch}",
            "session_id": f"controller:story-first:{branch}",
            "attempt": 1,
            "round": state["gap_fill_round"],
            "artifact_path": str(artifact),
            "artifact_hash": payload["output_hash"],
            "raw_file_sha256": file_sha256(artifact),
            "accepted_at": utc_now(),
        }
        state["receipts"].append(receipt)
        branches.append(payload)
    if failures:
        raise ValueError("STORY_BRANCH_GATE:" + json.dumps(failures, ensure_ascii=False))
    return branches


def advance_story_pipeline(
    claim_path: Path, claim: dict[str, Any], profile: dict[str, Any], packet: dict[str, Any],
    output_dir: Path, state_path: Path, state: dict[str, Any],
) -> dict[str, Any]:
    pipeline_roles = {"story_creator", "story_editor", "candidate_mapper"}
    if any(
        job.get("status") == "pending"
        and (job.get("role") in pipeline_roles or str(job.get("role", "")).startswith("kernel_supplement_"))
        for job in state["jobs"]
    ):
        state["updated_at"] = utc_now()
        save_state(state_path, state)
        return public_state(claim_path, state)
    unresolved = [
        track for track in state["candidate_tracks"].values()
        if track["status"] not in {"mapped", "eliminated"}
    ]
    if unresolved:
        failures = [{
            "reason": "STORY_TRACK_STALLED", "candidate_id": track["candidate_id"],
            "status": track["status"],
        } for track in unresolved]
        state = finalize_failure(claim, profile, output_dir, state_path, state, failures)
        return public_state(claim_path, state)
    try:
        branches = build_story_first_branches(state, claim, profile, output_dir)
    except ValueError as exc:
        parsed = json.loads(str(exc).split(":", 1)[1])
        state = finalize_failure(claim, profile, output_dir, state_path, state, parsed)
        return public_state(claim_path, state)
    post_story_minimum = max(2, int(claim["kernels_per_branch"]) - 1)
    clustered = portfolio.cluster_generation(
        packet, load_json(Path(state["artifacts"]["atoms"])),
        load_json(Path(state["artifacts"]["contexts"])), branches,
        profile, claim["lane"], claim["run_id"], post_story_minimum,
    )
    clustered_path = write_artifact(
        output_dir, f"clustered_representatives_r{state['gap_fill_round']}.json", clustered,
    )
    state["artifacts"]["clustered"] = str(clustered_path)
    if clustered.get("status") != "representatives_ready":
        state = finalize_failure(
            claim, profile, output_dir, state_path, state,
            list(clustered.get("failures") or [{"reason": "CLUSTERING_FAILED"}]),
        )
        return public_state(claim_path, state)
    build_review_evidence_slice(
        packet, load_json(Path(state["artifacts"]["atoms"])), clustered,
        claim["lane"], output_dir,
    )
    schedule_reviews(state, claim, output_dir)
    state["updated_at"] = utc_now()
    save_state(state_path, state)
    return public_state(claim_path, state)


def schedule_generation(state: dict[str, Any], claim: dict[str, Any], output_dir: Path) -> None:
    round_no = state["gap_fill_round"]
    state["jobs"].extend([
        create_job(f"generation_{branch}", claim, output_dir, round_no)
        for branch in sorted(portfolio.BRANCH_ROLES)
    ])
    state["stage"] = "S2_KERNELS"


def _failed_generation_branches(failures: list[dict[str, Any]]) -> set[str]:
    """Extract branch IDs that need repair from a failures list.

    Branch info comes in three forms:
    - Direct: ``branch_id`` or ``branch`` key (branch-level failures)
    - Indirect: ``candidate_id`` like "B-C01" where the prefix is the branch
    - Inferred: reason code prefix like "B_GENERATOR_CANDIDATE_COUNT_INSUFFICIENT"
    """
    branches: set[str] = set()
    for row in failures:
        bid = str(row.get("branch_id") or row.get("branch") or "")
        if bid in portfolio.BRANCH_ROLES:
            branches.add(bid)
        # candidate-level failures carry branch in the candidate_id prefix
        cid = str(row.get("candidate_id") or "")
        if "-" in cid:
            prefix = cid.split("-")[0]
            if prefix in portfolio.BRANCH_ROLES:
                branches.add(prefix)
        # Some branch-level failures only have the reason code for identification
        reason = str(row.get("reason") or "")
        for branch in portfolio.BRANCH_ROLES:
            if reason.startswith(f"{branch}_"):
                branches.add(branch)
                break
    return branches


def schedule_generation_gap_fill(
    state: dict[str, Any], claim: dict[str, Any], output_dir: Path,
    failures: list[dict[str, Any]],
) -> None:
    """Only re-dispatch generation jobs for branches that actually failed."""
    round_no = state["gap_fill_round"]
    failed = _failed_generation_branches(failures)
    if not failed:
        failed = set(portfolio.BRANCH_ROLES)  # safety: no branch info → re-dispatch all
    for branch in sorted(failed):
        state["jobs"].append(create_job(f"generation_{branch}", claim, output_dir, round_no))
    state["stage"] = "S2_KERNELS"


def schedule_reviews(state: dict[str, Any], claim: dict[str, Any], output_dir: Path) -> None:
    round_no = state["gap_fill_round"]
    state["jobs"].extend([
        create_job(role, claim, output_dir, round_no)
        for role in ("market_coverage", "originality_craft")
    ])
    state["stage"] = "S3_REVIEW"


def latest_receipt(state: dict[str, Any], role: str) -> dict[str, Any]:
    rows = [row for row in state["receipts"] if row["role"] == role]
    if not rows:
        raise ValueError(f"RECEIPT_MISSING:{role}")
    return rows[-1]


def finalize_failure(
    claim: dict[str, Any], profile: dict[str, Any], output_dir: Path,
    state_path: Path, state: dict[str, Any], failures: list[dict[str, Any]],
) -> dict[str, Any]:
    for job in state["jobs"]:
        if job.get("status") == "pending":
            job["status"] = "superseded"
    gate = portfolio.seal({
        "stage": "candidate_portfolio_gate", "schema_version": portfolio.SCHEMA_VERSION,
        "lane": claim["lane"], "run_id": claim["run_id"],
        "target_profile_hash": profile["output_hash"], "status": "candidate_generation_failed",
        "formal_candidate_generation": "blocked", "failures": failures, "diagnostic_only": True,
    })
    path = output_dir / "candidate_portfolio_failure.json"
    if not path.exists():
        write_artifact(output_dir, path.name, gate)
    state.update({
        "status": "candidate_generation_failed", "stage": "S4_TERMINAL",
        "failures": failures, "usable_candidate_count": 0, "updated_at": utc_now(),
    })
    state["artifacts"]["gate"] = str(path)
    append_manifest(output_dir, {"event": "candidate_generation_failed", "failures": failures})
    save_state(state_path, state)
    return state


def fail_or_gap_fill(
    claim_path: Path, claim: dict[str, Any], profile: dict[str, Any],
    output_dir: Path, state_path: Path, state: dict[str, Any],
    failures: list[dict[str, Any]], *, failed_job_id: str | None = None,
) -> dict[str, Any]:
    # Auto-fixable: controller knows the correct value, just warn and move on.
    # These are field-level metadata and citation fixes where the controller has ground truth.
    AUTO_FIXABLE = {
        # S1/S2 metadata fields — controller owns these values
        "GENERATOR_LANE_MISMATCH", "GENERATOR_RUN_ID_MISMATCH", "GENERATOR_BRANCH_ID_MISMATCH",
        "GENERATOR_GENERATOR_ROLE_MISMATCH", "GENERATOR_EVIDENCE_PACKET_HASH_MISMATCH",
        "GENERATOR_CONTEXT_HASH_MISMATCH", "GENERATOR_TARGET_PROFILE_MISMATCH",
        "GENERATOR_ATOM_SLICE_MISMATCH", "GENERATOR_SAMPLING_CONFIG_MISMATCH",
        "GENERATOR_CONTEXT_NOT_ISOLATED", "GENERATOR_OUTPUT_HASH_INVALID",
        "GENERATOR_ARTIFACT_CONTRACT_INVALID",
        "CANDIDATE_BRANCH_PROVENANCE_INVALID", "CANDIDATE_ATOM_CITATION_INVALID",
        "CARD_ATOM_CITATION_MISMATCH", "PRIMARY_EVIDENCE_NOT_IN_SUPPORT_SET",
        "ATOM_TYPE_INVALID", "ATOM_ID_INVALID_OR_DUPLICATE",
        # S3 reviewer: only mechanical corrections where controller owns the correct value
        "GENERAL_REVIEW_ACTIVITY_FIT_INVALID",
        "MARKET_CAUSAL_CONTRADICTION_PRESENT",
    }
    # Dismissed: cards injected by controller (S2) — these codes fire on controller-injected fields
    # and are never the model's fault. Warn only.
    DISMISSED = {
        "CROSS_SOURCE_CONTRADICTION_NOT_LINKED", "ATOM_OUTPUT_HASH_INVALID",
        "CARD_TARGET_PLATFORM_MISMATCH", "CARD_AUDIENCE_CHANNEL_MISMATCH",
        "CARD_PORTFOLIO_TRACK_MISMATCH", "CARD_TARGET_PROFILE_HASH_MISMATCH",
        "GENERAL_CARD_ACTIVITY_ROUTE_INVALID", "ACTIVITY_CARD_ROUTE_MISSING",
        "ACTIVITY_CARD_ID_MISMATCH", "ACTIVITY_CARD_RULE_EVIDENCE_MISMATCH",
        "ACTIVITY_CARD_REQUIREMENT_MAPPING_INVALID",
        "MARKET_EDITOR_CANDIDATE_SET_MISMATCH", "ORIGINALITY_REDTEAM_CANDIDATE_SET_MISMATCH",
        "MARKET_SCORE_VECTORS_UNIFORM", "MARKET_SCORE_VECTOR_OVERUSED",
    }
    # Format: model can self-correct with one retry.
    # These are structural/schema format problems the model CAN fix when told to.
    # NOTE: codes gated by allow_rejections=True (MARKET_EDITOR_REJECTED, ORIGINALITY_REDTEAM_REJECTED,
    # HIGH_RECOGNITION_COLLISION) never fire at S3 ingest — reviewer judgment is accepted as-is
    # and handled by assembly veto. They are intentionally absent here.
    FORMAT_CODES = {
        # S1 atoms format
        "ATOM_NOT_OBJECT", "CONCEPT_KERNEL_NOT_OBJECT",
        "CONCEPT_KERNEL_CONTENT_EMPTY", "GENERATOR_CANDIDATE_NOT_OBJECT",
        "GENERATOR_CANDIDATE_ID_MISSING", "CARD_FIELD_MISSING",
        "CARD_OPENING_300_INVALID", "CARD_LONG_STAGE_NOT_SUBSTANTIVE",
        "REVIEW_GATE", "GATE_ERROR_INVALID", "GENERATOR_CANDIDATE_COUNT_INSUFFICIENT",
        "ATOM_SCHEMA_VERSION_INVALID", "ATOM_STAGE_OR_LANE_INVALID",
        # S3 market coverage content-quality (all fire with allow_rejections=True)
        "READING_RETURN_CYCLE_INVALID", "MARKET_CALIBRATED_OBJECTIVES_MISSING",
        "MARKET_PLATFORM_FIT_NOT_SUBSTANTIVE", "MARKET_CHANNEL_FIT_NOT_SUBSTANTIVE",
        "MARKET_CAUSAL_CONSISTENCY_NOT_SUBSTANTIVE",
        "LONG_THREE_STAGE_REVIEW_MISSING", "LONG_THREE_STAGE_REVIEW_NOT_SUBSTANTIVE",
        "SHORT_COMPLEXITY_BUDGET_INVALID",
        "MARKET_ENTRY_PROMISE_NOT_SUBSTANTIVE",
        "MARKET_CALIBRATED_OBJECTIVE_INVALID", "MARKET_OBJECTIVE_RATIONALE_MISSING",
        "MARKET_EDITOR_RECORD_INVALID",
        # L3 channel enforcement (2026-09-02): all four are model-fixable format errors
        "MARKET_CHANNEL_VERDICT_INVALID", "MARKET_PROTAGONIST_PERSPECTIVE_INVALID",
        "CHANNEL_MISMATCH_NOT_REJECTED", "CHANNEL_VERDICT_CONTRADICTS_PERSPECTIVE",
        # S3 originality content-quality (all fire with allow_rejections=True)
        "ORIGINALITY_RECORD_INVALID", "ORIGINALITY_LAYER_ORDER_INVALID",
        "CAUSAL_DIFFERENCE_AUDIT_MISSING", "CLOSEST_WORK_REFERENCE_INVALID",
        "ORIGINALITY_RISK_CALIBRATION_INVALID", "ORIGINALITY_RISK_RATIONALE_MISSING",
        "AI_STYLE_METRIC_USED_AS_ORIGINALITY_EVIDENCE",
    }
    code_set = {str(f.get("reason", "")) for f in failures}

    # Auto-fixable: just log warnings, don't retry at all
    auto = code_set & AUTO_FIXABLE
    dismissed = code_set & DISMISSED
    if auto or dismissed:
        append_manifest(output_dir, {
            "event": "auto_fixed_or_dismissed",
            "auto_fixed": sorted(auto) if auto else None,
            "dismissed": sorted(dismissed) if dismissed else None,
        })
        remaining = code_set - AUTO_FIXABLE - DISMISSED
        if not remaining:
            # All failures were auto-fixed or dismissed — accept the job
            # A gate cannot be accepted here because no artifact/receipt exists yet.
            # Convert incomplete normalization into bounded recovery instead of
            # dispatching the same pending job forever.
            failures = [{
                "reason": "CONTROLLER_AUTO_FIX_NOT_APPLIED",
                "original_reasons": sorted(auto | dismissed),
            }]
        else:
            failures = [
                f for f in failures
                if str(f.get("reason", "")) not in (AUTO_FIXABLE | DISMISSED)
            ]

    code_set = {str(f.get("reason", "")) for f in failures}
    is_format_only = bool(code_set) and code_set.issubset(FORMAT_CODES)

    if is_format_only:
        failed_role = next(
            (job.get("role", "unknown") for job in state["jobs"] if job.get("job_id") == failed_job_id),
            "unknown",
        )
        key = failed_role
        used = state.get("format_retries_used", {})
        if used.get(key, 0) < MAX_FORMAT_RETRIES and reserve_recovery_call(
            state, "format_repair", role=failed_role,
        ):
            used[key] = used.get(key, 0) + 1
            state["format_retries_used"] = used
            for job in state["jobs"]:
                if job.get("job_id") == failed_job_id and job.get("status") == "pending":
                    job["status"] = "superseded"
            repair_hint = "; ".join(sorted(code_set))
            # Increment attempt counter so repair job gets a unique job_id,
            # avoiding JOB_ID_NOT_EXPECTED when superseded + pending share same id.
            state.setdefault("format_repair_attempt", 0)
            state["format_repair_attempt"] += 1
            repair_attempt = state["gap_fill_round"] + 1 + state["format_repair_attempt"]
            repairing = create_job(
                failed_role, claim, output_dir, state["gap_fill_round"],
                repair_hint=repair_hint, attempt=repair_attempt,
            )
            state["jobs"].append(repairing)
            state["failures"] = failures
            state["updated_at"] = utc_now()
            save_state(state_path, state)
            append_manifest(output_dir, {
                "event": "format_repair_scheduled", "failed_job": failed_job_id,
                "repair_job": repairing["job_id"], "failure_codes": sorted(code_set),
            })
            return public_state(claim_path, state)

    failed_stage = state["stage"]
    if failed_stage == "S3_REVIEW":
        state = finalize_failure(claim, profile, output_dir, state_path, state, failures)
        return public_state(claim_path, state)
    if failed_stage == "S4_ASSEMBLE":
        recoverable = {
            "QUALIFIED_CANDIDATES_INSUFFICIENT",
            "FINAL_STRATEGY_DIVERSITY_INSUFFICIENT",
            "FINAL_MECHANISM_DIVERSITY_INSUFFICIENT",
        }
        if not {str(row.get("reason") or "") for row in failures}.issubset(recoverable):
            state = finalize_failure(claim, profile, output_dir, state_path, state, failures)
            return public_state(claim_path, state)
        state = finalize_failure(
            claim, profile, output_dir, state_path, state,
            list(failures) + [{'reason': 'TARGETED_PORTFOLIO_RECOVERY_UNAVAILABLE'}],
        )
        return public_state(claim_path, state)

    if reserve_recovery_call(state, "gap_fill", stage=failed_stage):
        failed_role = None
        for job in state["jobs"]:
            if job.get("job_id") == failed_job_id:
                failed_role = job.get("role", "")
                break
        for job in state["jobs"]:
            if job.get("status") == "pending":
                job["status"] = "superseded"
        state["gap_fill_round"] += 1
        state["failures"] = failures
        if failed_stage == "S1_ATOMS":
            repair_hint = "; ".join(sorted(code_set))
            state["jobs"].append(create_job(
                "atoms", claim, output_dir, state["gap_fill_round"], repair_hint=repair_hint,
            ))
            state["stage"] = "S1_ATOMS"
        else:
            schedule_generation_gap_fill(state, claim, output_dir, failures)
        append_manifest(output_dir, {
            "event": "gap_fill_scheduled", "round": state["gap_fill_round"],
            "failed_stage": failed_stage, "failed_role": failed_role,
            "failure_reasons": sorted(code_set),
        })
    else:
        failures = list(failures) + [{
            "reason": "RECOVERY_CALL_BUDGET_EXHAUSTED",
            "limit": state.get("recovery_budget", {}).get("limit", RECOVERY_CALL_BUDGET),
        }]
        state = finalize_failure(claim, profile, output_dir, state_path, state, failures)
        return public_state(claim_path, state)
    state["updated_at"] = utc_now()
    save_state(state_path, state)
    return public_state(claim_path, state)


def assemble_round(
    claim_path: Path, claim: dict[str, Any], profile: dict[str, Any], packet: dict[str, Any],
    output_dir: Path, state_path: Path, state: dict[str, Any],
) -> dict[str, Any]:
    round_no = state["gap_fill_round"]
    atoms = load_json(Path(state["artifacts"]["atoms"]))
    contexts = load_json(Path(state["artifacts"]["contexts"]))
    branches = [
        load_json(Path(latest_receipt(state, f"generation_{branch}")["artifact_path"]))
        for branch in sorted(portfolio.BRANCH_ROLES)
    ]
    market = load_json(Path(latest_receipt(state, "market_coverage")["artifact_path"]))
    originality = load_json(Path(latest_receipt(state, "originality_craft")["artifact_path"]))
    provenance = portfolio.make_job_provenance(
        claim["run_id"],
        {branch: latest_receipt(state, f"generation_{branch}") for branch in sorted(portfolio.BRANCH_ROLES)},
        {role: latest_receipt(state, role) for role in ("market_coverage", "originality_craft")},
        branches, market, originality,
    )
    provenance_path = write_artifact(output_dir, f"delegation_provenance_r{round_no}.json", provenance)
    clustered = load_json(Path(state["artifacts"]["clustered"]))
    state["stage"] = "S4_ASSEMBLE"
    gate = portfolio.assemble_portfolio(
        packet, atoms, contexts, branches, market, originality,
        profile, claim["lane"], claim["run_id"], provenance, clustered,
    )
    gate["controller_manifest_sha256"] = file_sha256(output_dir / "controller_manifest.jsonl")
    gate = portfolio.seal(gate)
    gate_path = write_artifact(output_dir, f"candidate_portfolio_gate_r{round_no}.json", gate)
    if gate.get("status") != "awaiting_user_choice":
        failures = list(gate.get('failures') or [{'reason': 'UNKNOWN_ASSEMBLY_FAILURE'}])
        recoverable = {
            'QUALIFIED_CANDIDATES_INSUFFICIENT',
            'FINAL_STRATEGY_DIVERSITY_INSUFFICIENT',
            'FINAL_MECHANISM_DIVERSITY_INSUFFICIENT',
        }
        if (
            {str(row.get('reason') or '') for row in failures}.issubset(recoverable)
            and schedule_portfolio_recovery(state, claim, output_dir, gate, failures)
        ):
            state['artifacts']['gate'] = str(gate_path)
            state['updated_at'] = utc_now()
            save_state(state_path, state)
            return public_state(claim_path, state)
        return fail_or_gap_fill(
            claim_path, claim, profile, output_dir, state_path, state,
            failures,
            failed_job_id=state["jobs"][0]["job_id"] if state["jobs"] else None,
        )
    cards = portfolio.make_cards_bundle(gate)
    cards_path = write_artifact(output_dir, "pareto_candidate_cards.json", cards)
    state.update({
        "status": "awaiting_user_choice", "stage": "S4_TERMINAL",
        "candidate_count": len(gate["candidate_cards"]), "failures": [], "updated_at": utc_now(),
        "generated_count": gate["generated_count"],
        "passed_review_count": gate["passed_review_count"],
        "selected_for_delivery_count": gate["selected_for_delivery_count"],
        "usable_candidate_count": gate["usable_candidate_count"],
    })
    state["artifacts"].update({
        "provenance": str(provenance_path), "gate": str(gate_path), "cards": str(cards_path),
    })
    append_manifest(output_dir, {
        "event": "awaiting_user_choice", "candidate_count": state["candidate_count"],
        "card_ids": [row["candidate_id"] for row in gate["candidate_cards"]],
    })
    save_state(state_path, state)
    return public_state(claim_path, state)



def accept_atoms(
    raw: Any, claim: dict[str, Any], profile: dict[str, Any],
    packet: dict[str, Any], output_dir: Path, state: dict[str, Any],
) -> tuple[Path, dict[str, Any]]:
    normalized = inject_atom_deterministic_fields(raw, claim, packet)
    payload = portfolio.seal(normalized)
    failures, audit = portfolio.atom_failures(packet, payload, claim["lane"])
    if failures:
        raise ValueError("ATOM_GATE:" + json.dumps(failures, ensure_ascii=False))
    artifact = write_artifact(output_dir, "evidence_atoms.json", payload)
    audit_path = write_artifact(output_dir, "evidence_atom_audit.json", audit)
    contexts = portfolio.build_contexts(packet, payload, profile, claim["lane"], claim["run_id"])
    contexts_path = write_artifact(output_dir, "generation_contexts.json", contexts)
    state["artifacts"].update({
        "atoms": str(artifact), "atom_audit": str(audit_path), "contexts": str(contexts_path),
    })
    return artifact, payload


def inject_deterministic_fields(raw: dict[str, Any], role: str, claim: dict[str, Any], profile: dict[str, Any], context: dict[str, Any] | None) -> dict[str, Any]:
    """Controller fills deterministic fields and auto-corrects model output.
    Model output is treated as content-only; metadata is always overwritten."""
    result = dict(raw)
    result["stage"] = "divergent_generation"
    result["schema_version"] = portfolio.SCHEMA_VERSION
    result["lane"] = claim["lane"]
    result["run_id"] = claim["run_id"]
    result["branch_id"] = role[-1]
    result["evidence_packet_hash"] = claim["evidence_packet_hash"]
    result["target_profile_hash"] = profile["output_hash"]
    result["independent_context"] = True
    result["visible_branch_ids"] = [role[-1]]
    input_atom_ids = []
    if context is not None:
        result["generator_role"] = context["generator_role"]
        result["context_hash"] = context["output_hash"]
        result["input_atom_ids"] = context["input_atom_ids"]
        result["sampling_config"] = context["sampling_config"]
        input_atom_ids = context["input_atom_ids"]

    # Inject metadata into each candidate_card + auto-fix citation references
    for candidate in result.get("candidates", []) or []:
        if not isinstance(candidate, dict):
            continue
        # Fix generator_branch provenance
        candidate["generator_branch"] = role[-1]
        # Auto-fix cited_atom_ids: model frequently mismatches these
        candidate["cited_atom_ids"] = input_atom_ids
        # Auto-fix closest_similar_work: model often writes <4 CJK chars (e.g. 3-char Chinese title
        # stripped of 书名号), which triggers CARD_CLOSEST_WORK_NOT_SUBSTANTIVE (pitfall #27).
        # Only auto-fix when the text already contains CJK characters (skip pure ASCII identifiers).
        # Append suffix when the normalized CJK character count is below threshold.
        def _cjk_chars(s: str) -> int:
            return len(re.sub(r'[^一-鿿]', '', str(s)))
        closest = candidate.get("closest_similar_work", "")
        cjk = _cjk_chars(closest)
        if closest and cjk > 0 and cjk < 4:
            candidate["closest_similar_work"] = f"{closest}之同类作品"
        card = candidate.get("candidate_card")
        if isinstance(card, dict):
            # Auto-fix closest_work in candidate_card (same rule as closest_similar_work above)
            cw = card.get("closest_work", "")
            cw_cjk = _cjk_chars(cw)
            if cw and cw_cjk > 0 and cw_cjk < 4:
                card["closest_work"] = f"{cw}之同类作品"
            card["target_platform"] = profile["target_platform"]
            card["audience_channel"] = profile["audience_channel"]
            card["portfolio_track"] = profile["portfolio_track"]
            card["target_profile_hash"] = profile["output_hash"]
            card["evidence_atom_ids"] = input_atom_ids
    return result


def auto_fix_atoms(raw: dict[str, Any], claim: dict[str, Any]) -> dict[str, Any]:
    """Auto-correct atom_type and supporting_evidence_ids before sealing."""
    atoms = raw.get("atoms")
    if not isinstance(atoms, list):
        return raw
    raw["stage"] = "evidence_atoms"
    raw["schema_version"] = portfolio.SCHEMA_VERSION
    raw["lane"] = claim["lane"]
    raw["run_id"] = claim["run_id"]
    raw["evidence_packet_hash"] = claim["evidence_packet_hash"]
    raw["input_hash"] = claim["evidence_packet_hash"]
    for atom in atoms:
        if not isinstance(atom, dict):
            continue
        # Validate atom_type: fuzzy match against ATOM_TYPES, leave unknown for format repair
        atom_type = str(atom.get("atom_type", ""))
        if atom_type not in portfolio.ATOM_TYPES:
            atom_lower = atom_type.lower()
            matched = None
            for valid in portfolio.ATOM_TYPES:
                if valid in atom_lower or atom_lower in valid:
                    matched = valid
                    break
            if matched:
                atom["atom_type"] = matched
        # Fix duplicate atom_ids: assign sequential id if missing or duplicate
        atom_id = str(atom.get("atom_id", ""))
        if not atom_id:
            idx = atoms.index(atom)
            atom["atom_id"] = f"atom_{idx+1:04d}"
        # Fix supporting_evidence_ids: ensure it contains own evidence_id
        evidence_id = str(atom.get("evidence_id", ""))
        supporting = atom.get("supporting_evidence_ids", [])
        if evidence_id and evidence_id not in {str(s) for s in supporting}:
            atom["supporting_evidence_ids"] = list(supporting) + [evidence_id]
    return raw



def accept_generation(
    raw: dict[str, Any], role: str, round_no: int, claim: dict[str, Any],
    profile: dict[str, Any], output_dir: Path, state: dict[str, Any],
) -> tuple[Path, dict[str, Any]]:
    branch = role[-1]
    context = load_json(Path(state["artifacts"]["contexts"]))["contexts"][branch]
    normalized_raw, failures = normalize_kernel_payload(
        raw, branch, list(context["input_atom_ids"]),
        exact_count=int(claim["kernels_per_branch"]),
    )
    payload = portfolio.seal({
        **normalized_raw,
        "stage": "concept_kernel_generation",
        "schema_version": portfolio.SCHEMA_VERSION,
        "lane": claim["lane"],
        "run_id": claim["run_id"],
        "branch_id": branch,
        "generator_role": context["generator_role"],
        "context_hash": context["output_hash"],
        "input_atom_ids": context["input_atom_ids"],
        "evidence_packet_hash": claim["evidence_packet_hash"],
        "target_profile_hash": profile["output_hash"],
        "independent_context": True,
        "visible_branch_ids": [branch],
    })
    if failures:
        raise ValueError("GENERATION_GATE:" + json.dumps(failures, ensure_ascii=False))
    artifact = write_artifact(output_dir, f"kernel_generation_{branch}_r{round_no}.json", payload)
    state["artifacts"].setdefault("kernel_branches", {})[branch] = str(artifact)
    return artifact, payload


def auto_fix_review(raw: dict[str, Any], candidate_ids: set[str], profile: dict[str, Any], lane: str) -> dict[str, Any]:
    """Auto-correct ONLY structural/mechanical defects that the controller can validate.
    Content-quality issues (missing substantiveness, placeholder data) MUST be surfaced
    as validation failures so they trigger a format retry — never silently patched."""
    result = dict(raw)
    candidates = result.get("candidates")
    # Model sometimes emits a bare candidate map (top-level keys are candidate IDs) instead
    # of {"candidates": {...}}. Normalize that structural drift here — it's mechanical.
    if not isinstance(candidates, dict):
        keys = set(result.keys())
        if keys and keys.issubset(candidate_ids | {"meta", "metadata"}):
            candidates = {k: v for k, v in result.items() if k in candidate_ids}
            result = {"candidates": candidates, **{k: v for k, v in result.items() if k not in candidate_ids}}
    if not isinstance(candidates, dict):
        return result
    for cid, record in list(candidates.items()):
        if not isinstance(record, dict):
            continue
        # Only fix activity_fit for general track — controller knows the correct value
        if profile.get("portfolio_track") == "general" and record.get("activity_fit") != "not_applicable":
            record["activity_fit"] = "not_applicable"
        # Only fix missing/None contradictions — controller knows it must be empty list
        if "contradictions" not in record or record.get("contradictions") is None:
            record["contradictions"] = []
        # Content-quality fields (reward_cycle, calibrated_objectives, objective_rationales,
        # three_stage_engine, platform_fit, channel_fit, causal_consistency, entry_promise)
        # are NOT auto-fixed — missing/unsubstantive content must trigger a format retry.
        # L3 (2026-09-02): channel_verdict / protagonist_perspective are reviewer judgment —
        # the controller must NEVER auto-fill them from the run channel, or the enforcement
        # becomes circular. Missing values must fail validation and be repaired by the model.
        # so the model produces real review content, not placeholder text.
    return result


def accept_review(
    raw: dict[str, Any], job: dict[str, Any], session_id: str,
    claim: dict[str, Any], profile: dict[str, Any], packet: dict[str, Any],
    output_dir: Path, state: dict[str, Any],
) -> tuple[Path, dict[str, Any]]:
    role = job["role"]
    clustered = load_json(Path(state["artifacts"]["clustered"]))
    candidate_ids = set(clustered["representative_ids"])
    stage = "market_editor_review" if role == "market_coverage" else "originality_redteam"
    reviewer_receipt = {
        "reviewer_kind": role, "job_id": job["job_id"], "session_id": session_id,
        "attempt": job["attempt"], "reviewer_run_id": session_id,
        "reviewer_agent_id": session_id, "delegated_task_id": job["job_id"],
        "independent_context": True, "evidence_packet_hash": claim["evidence_packet_hash"],
        "reviewed_candidate_ids": sorted(candidate_ids), "status": "passed", "findings": [],
    }
    raw = auto_fix_review(raw, candidate_ids, profile, claim["lane"])
    if role == "originality_craft":
        ev_index = portfolio.evidence_index(packet)
        for record in (raw.get("candidates") or {}).values():
            if not isinstance(record, dict):
                continue
            ref = record.get("closest_work_reference")
            if isinstance(ref, dict) and ref.get("evidence_id"):
                ev_row = ev_index.get(str(ref["evidence_id"]))
                if ev_row:
                    ref["identifier"] = str(
                        ev_row.get("source_title") or ev_row.get("title")
                        or ev_row.get("source_id") or ref["evidence_id"]
                    )
    payload = portfolio.seal({
        **raw, "stage": stage, "schema_version": portfolio.SCHEMA_VERSION,
        "lane": claim["lane"], "run_id": claim["run_id"],
        "input_hash": clustered["cluster_audit"]["output_hash"],
        "evidence_packet_hash": claim["evidence_packet_hash"],
        "target_profile_hash": profile["output_hash"], "reviewer_receipt": reviewer_receipt,
    })
    arguments = (
        payload, candidate_ids, claim["lane"], claim["run_id"],
        clustered["cluster_audit"]["output_hash"], claim["evidence_packet_hash"], profile,
    )
    failures = (
        portfolio.validate_market_audit(*arguments, allow_rejections=True)
        if role == "market_coverage"
        else portfolio.validate_originality_audit(
            *arguments, portfolio.evidence_reference_registry(packet), allow_rejections=True,
        )
    )
    if failures:
        raise ValueError("REVIEW_GATE:" + json.dumps(failures, ensure_ascii=False))
    return write_artifact(output_dir, f"{stage}_r{job['round']}.json", payload), payload


def parse_gate_error(exc: ValueError) -> list[dict[str, Any]] | None:
    text = str(exc)
    for prefix in ("ATOM_GATE:", "GENERATION_GATE:", "REVIEW_GATE:", "MAPPING_GATE:"):
        if text.startswith(prefix):
            parsed = json.loads(text[len(prefix):])
            return parsed if isinstance(parsed, list) else [{"reason": "GATE_ERROR_INVALID"}]
    return None


def _dedup_jobs(state: dict[str, Any]) -> dict[str, Any]:
    """Remove duplicate job entries, keeping the latest status entry per job_id.
    Superseded entries sharing a job_id with a pending or accepted entry are removed."""
    seen: dict[str, dict[str, Any]] = {}
    for job in state.get("jobs", []):
        jid = job.get("job_id", "")
        if jid not in seen or job.get("status") != "superseded":
            seen[jid] = job
    state["jobs"] = list(seen.values())
    return state



def ingest_job(claim_path: Path, job_id: str, session_id: str, artifact_path: Path) -> dict[str, Any]:
    claim, profile, packet, output_dir, state_path = validate_claim(claim_path)
    state = load_json(state_path)
    if state["status"] in TERMINAL:
        return public_state(claim_path, state)
    state = _dedup_jobs(state)
    matching = [row for row in state["jobs"] if row["job_id"] == job_id]
    if len(matching) != 1:
        raise ValueError("JOB_ID_NOT_EXPECTED")
    job = matching[0]
    if job["status"] != "pending":
        existing = next((row for row in state["receipts"] if row["job_id"] == job_id), None)
        if existing and existing["session_id"] == session_id:
            return public_state(claim_path, state)
        raise ValueError("JOB_ALREADY_INGESTED")
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{6,200}", session_id):
        raise ValueError("SESSION_ID_INVALID")
    if session_id in {row["session_id"] for row in state["receipts"]}:
        raise ValueError("SESSION_ID_REUSED")
    expected_raw = canonical_path(Path(job["raw_output"]))
    if canonical_path(artifact_path) != expected_raw or not win_long_path(expected_raw).is_file():
        raise ValueError("JOB_ARTIFACT_PATH_INVALID")
    role = job["role"]
    plain_text_role = role in {"story_creator", "story_editor"}
    raw: Any = (
        win_long_path(expected_raw).read_text(encoding="utf-8")
        if plain_text_role else load_json(expected_raw)
    )
    if role != "atoms" and not plain_text_role and not isinstance(raw, dict):
        raise ValueError("JOB_ARTIFACT_NOT_OBJECT")
    try:
        if role == "atoms":
            artifact, payload = accept_atoms(raw, claim, profile, packet, output_dir, state)
        elif role.startswith("generation_"):
            artifact, payload = accept_generation(
                raw, role, job["round"], claim, profile, output_dir, state,
            )
        elif role == "story_creator":
            artifact, artifact_hash = accept_story_creator(raw, job, output_dir, state)
            payload = None
        elif role == "story_editor":
            artifact, payload = accept_story_review(raw, job, claim, output_dir, state)
        elif role == "candidate_mapper":
            artifact, payload = accept_candidate_mapping(
                raw, job, claim, profile, output_dir, state,
            )
        elif role.startswith("kernel_supplement_"):
            artifact, payload = accept_kernel_supplement(
                raw, job, claim, output_dir, state,
            )
        else:
            artifact, payload = accept_review(
                raw, job, session_id, claim, profile, packet, output_dir, state,
            )
    except ValueError as exc:
        if role == "story_creator":
            track = state["candidate_tracks"][job["candidate_id"]]
            job["status"] = "superseded"
            if track["story_attempt"] <= MAX_STORY_REWRITES:
                schedule_story_retry(
                    state, claim, output_dir, track,
                    "故事输出为空，必须整段重新创作。",
                )
            else:
                eliminate_track(
                    state, claim, output_dir, track,
                    "两次故事创作均未产生可审读正文。",
                )
            state["updated_at"] = utc_now()
            save_state(state_path, state)
            return advance_story_pipeline(
                claim_path, claim, profile, packet, output_dir, state_path, state,
            )
        if role == "candidate_mapper" and str(exc).startswith("MAPPING_GATE:"):
            failures = json.loads(str(exc)[len("MAPPING_GATE:"):])
            handle_mapping_failure(state, claim, output_dir, job, failures)
            state["updated_at"] = utc_now()
            save_state(state_path, state)
            return advance_story_pipeline(
                claim_path, claim, profile, packet, output_dir, state_path, state,
            )
        if role.startswith("kernel_supplement_"):
            job["status"] = "superseded"
            state.setdefault("story_failures", []).append({
                "reason": "KERNEL_SUPPLEMENT_INVALID",
                "branch_id": job["branch_id"],
                "detail": str(exc),
            })
            state["updated_at"] = utc_now()
            save_state(state_path, state)
            return advance_story_pipeline(
                claim_path, claim, profile, packet, output_dir, state_path, state,
            )
        failures = parse_gate_error(exc)
        if failures is None:
            raise
        return fail_or_gap_fill(
            claim_path, claim, profile, output_dir, state_path, state,
            failures, failed_job_id=job_id,
        )

    if payload is not None:
        artifact_hash = payload["output_hash"]
    accepted = make_receipt(job, session_id, artifact, artifact_hash)
    state["receipts"].append(accepted)
    job["status"] = "accepted"
    append_manifest(output_dir, {"event": "job_accepted", **accepted})

    if role == "atoms":
        schedule_generation(state, claim, output_dir)
    elif role.startswith("generation_"):
        pending_generation = any(
            row.get("status") == "pending" and str(row.get("role", "")).startswith("generation_")
            for row in state["jobs"]
        )
        if not pending_generation:
            schedule_story_tracks(state, claim, output_dir)
    elif role == "story_creator":
        track = state["candidate_tracks"][job["candidate_id"]]
        state["jobs"].append(create_job(
            "story_editor", claim, output_dir, state["gap_fill_round"],
            metadata={
                "candidate_id": track["candidate_id"],
                "kernel_id": track["kernel_id"],
                "branch_id": track["branch_id"],
                "kernel_path": track["kernel_path"],
                "story_path": track["story_path"],
                "story_attempt": track["story_attempt"],
            },
            attempt=track["story_attempt"],
        ))
        state["stage"] = "S2_EDIT"
    elif role in {"story_editor", "candidate_mapper"} or role.startswith("kernel_supplement_"):
        state["updated_at"] = utc_now()
        save_state(state_path, state)
        return advance_story_pipeline(
            claim_path, claim, profile, packet, output_dir, state_path, state,
        )
    else:
        review_roles = {"market_coverage", "originality_craft"}
        accepted_roles = {
            row["role"] for row in state["receipts"]
            if row["round"] == job["round"] and row["role"] in review_roles
        }
        if accepted_roles == review_roles:
            state["updated_at"] = utc_now()
            save_state(state_path, state)
            return assemble_round(
                claim_path, claim, profile, packet, output_dir, state_path, state,
            )
    state["updated_at"] = utc_now()
    save_state(state_path, state)
    return public_state(claim_path, state)


def verify_delivery(claim_path: Path) -> dict[str, Any]:
    _, profile, _, output_dir, state_path = validate_claim(claim_path)
    state = load_json(state_path)
    if state.get("status") != "awaiting_user_choice":
        return {"status": "candidate_generation_failed", "failures": state.get("failures", [])}
    gate = load_json(Path(state["artifacts"]["gate"]))
    cards = load_json(Path(state["artifacts"]["cards"]))
    failures = portfolio.delivery_failures(gate, cards, profile, output_dir)
    counts = {
        "generated_count": int(gate.get("generated_count", 0)),
        "passed_review_count": int(gate.get("passed_review_count", 0)),
        "selected_for_delivery_count": int(gate.get("selected_for_delivery_count", 0)),
        "usable_candidate_count": int(gate.get("usable_candidate_count", 0)),
    }
    if (
        counts["selected_for_delivery_count"] != len(cards.get("cards", []))
        or any(cards.get(key) != value for key, value in counts.items())
    ):
        failures.append({"reason": "CANDIDATE_COUNT_CONTRACT_INVALID", "counts": counts})
    allowed = (
        re.compile(r'^(?:candidate_run_claim|target_profile|evidence_packet|evidence_compact_view|controller_state|evidence_atoms|evidence_atom_audit|generation_contexts|generation_context_[ABC]|clustered_representatives|pareto_candidate_cards|review_evidence_slice)\.json$'),
        re.compile(r"^(?:kernel_generation_[ABC]|generation_[ABC]_story_first|market_editor_review|originality_redteam|delegation_provenance|candidate_portfolio_gate|clustered_representatives)_r\d+\.json$"),
        re.compile(r'^(?:kernel_[ABC]-C\d+|kernel_supplement_[ABC]_r\d+_a\d+|story_review_[ABC]-C\d+_a\d+|candidate_mapping_[ABC]-C\d+)\.json$'),
        re.compile(r"^story_[ABC]-C\d+_a\d+\.txt$"),
        re.compile(r"^controller_manifest\.jsonl$"),
    )
    unexpected = sorted(
        str(path.relative_to(output_dir))
        for path in output_dir.iterdir()
        if path.name not in {"raw", "_bundle_snapshot"} and not any(pattern.fullmatch(path.name) for pattern in allowed)
    )
    if unexpected:
        failures.append({"reason": "OUTPUT_WHITELIST_VIOLATION", "paths": unexpected})
    passed = not failures
    return {
        "status": "passed" if passed else "candidate_generation_failed",
        "failures": failures, "candidate_count": len(cards.get("cards", [])),
        **counts,
        "usable_candidate_count": counts["usable_candidate_count"] if passed else 0,
        "cards": str(Path(state["artifacts"]["cards"])),
    }


def resume(claim_path: Path) -> dict[str, Any]:
    _, _, _, _, state_path = validate_claim(claim_path)
    return public_state(claim_path, load_json(state_path))


def main() -> int:
    parser = argparse.ArgumentParser(description="Novel candidate portfolio controller")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--base-root", type=Path, required=True)
    run.add_argument("--packet", type=Path, required=True)
    run.add_argument("--lane", choices=sorted(portfolio.LANES), required=True)
    run.add_argument("--platform", choices=sorted(portfolio.TARGET_PLATFORMS), required=True)
    run.add_argument("--channel", choices=sorted(portfolio.AUDIENCE_CHANNELS), required=True)
    run.add_argument("--execution-profile", choices=sorted(EXECUTION_PROFILES), default="production")
    pool = run.add_mutually_exclusive_group()
    pool.add_argument("--atom-bundle", type=Path)
    pool.add_argument("--kernel-bundle", type=Path)
    for command in ("resume", "status", "verify"):
        child = sub.add_parser(command)
        child.add_argument("--claim", type=Path, required=True)
    ingest = sub.add_parser("ingest")
    ingest.add_argument("--claim", type=Path, required=True)
    ingest.add_argument("--job-id", required=True)
    ingest.add_argument("--session-id", required=True)
    ingest.add_argument("--artifact", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "run":
            result = init_run(
                args.base_root, args.packet, args.lane, args.platform, args.channel,
                args.execution_profile, args.atom_bundle, args.kernel_bundle,
            )
        elif args.command in {"resume", "status"}:
            result = resume(args.claim)
        elif args.command == "ingest":
            result = ingest_job(args.claim, args.job_id, args.session_id, args.artifact)
        else:
            result = verify_delivery(args.claim)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        result = {"status": "candidate_generation_failed", "error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") in {"paused", "running", "awaiting_user_choice", "passed"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
