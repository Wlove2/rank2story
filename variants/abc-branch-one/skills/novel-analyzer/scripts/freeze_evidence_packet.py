#!/usr/bin/env python3
"""Freeze complete acquisition artifacts before candidate deliberation."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "references" / "source-registry.json"


def load_coverage_validator():
    path = Path(__file__).with_name("validate_source_coverage.py")
    spec = importlib.util.spec_from_file_location("validate_source_coverage_for_freeze", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sha_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def attest_file(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    stat = resolved.stat()
    return {
        "path": str(resolved),
        "sha256": sha_file(resolved),
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
    }


def load_source_mix_policy(lane: str, registry: dict[str, Any] | None = None) -> dict[str, Any]:
    registry = registry or json.loads(DEFAULT_REGISTRY.read_text(encoding="utf-8"))
    policy = registry.get("source_mix_policy", {}).get(lane)
    if not isinstance(policy, dict):
        raise ValueError(f"SOURCE_MIX_POLICY_MISSING: {lane}")
    caps = [float(item["cap"]) for item in policy.values() if isinstance(item, dict) and "cap" in item]
    if not caps or abs(sum(caps) - 1.0) > 1e-9:
        raise ValueError(f"SOURCE_MIX_CAPS_INVALID: {lane}")
    return policy


def freeze(
    manifest: dict[str, Any],
    coverage: dict[str, Any],
    evidence: Any,
    sample: Any,
    registry: dict[str, Any] | None = None,
    input_attestations: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if coverage.get("formal_candidate_generation") != "allowed":
        raise ValueError("COVERAGE_GATE_BLOCKED: evidence cannot be frozen for candidates")
    lane = manifest.get("lane") or coverage.get("lane")
    packet = {
        "stage": "evidence_frozen",
        "lane": lane,
        "acquisition_manifest_hash": digest(manifest),
        "coverage_report_hash": digest(coverage),
        "source_mix_policy": load_source_mix_policy(str(lane), registry),
        "provenance": {
            "assurance": "local_content_hash_attestation" if input_attestations else "in_memory_contract_test",
            "collector_cache_verified": bool(manifest.get("collector_cache_verified")),
            "external_timestamp_verified": False,
            "input_files": input_attestations or {},
        },
        "evidence": evidence,
        "analysis_sample": sample,
    }
    packet["evidence_packet_hash"] = digest(packet)
    return packet


def validate_packet(packet: Any, lane: str | None = None) -> str:
    if not isinstance(packet, dict) or packet.get("stage") != "evidence_frozen":
        raise ValueError("candidate stage requires stage=evidence_frozen")
    expected = packet.get("evidence_packet_hash")
    unsigned = dict(packet)
    unsigned.pop("evidence_packet_hash", None)
    if not expected or digest(unsigned) != expected:
        raise ValueError("evidence packet hash mismatch")
    if lane and packet.get("lane") != lane:
        raise ValueError(f"evidence packet lane mismatch: expected {lane}")
    return str(expected)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-manifest", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--coverage", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    load = lambda path: json.loads(path.read_text(encoding="utf-8"))
    registry = load(args.registry)
    run_manifest = load(args.run_manifest)
    run_root = Path(str(run_manifest.get("run_root") or "")).resolve()
    expected_output = Path(run_manifest["paths"]["files"]["evidence_packet"]).resolve()
    if args.output.resolve() != expected_output:
        raise ValueError(f"EVIDENCE_PACKET_PATH_MISMATCH: expected {expected_output}")
    for label, path in {
        "run_manifest": args.run_manifest,
        "manifest": args.manifest,
        "coverage": args.coverage,
        "evidence": args.evidence,
        "sample": args.sample,
    }.items():
        try:
            path.resolve().relative_to(run_root)
        except ValueError as exc:
            raise ValueError(f"FREEZE_INPUT_OUTSIDE_RUN: {label}") from exc
    manifest = load(args.manifest)
    supplied_coverage = load(args.coverage)
    profile_id = run_manifest.get("profile_id")
    if not isinstance(profile_id, str) or not profile_id:
        raise ValueError("RUN_PROFILE_MISSING")
    validator = load_coverage_validator()
    verified_coverage = validator.validate(
        profile_id,
        manifest,
        registry,
        stage="scan",
        run_manifest=run_manifest,
    )
    supplied_comparable = dict(supplied_coverage)
    supplied_comparable.pop("report", None)
    if supplied_comparable != verified_coverage:
        raise ValueError("COVERAGE_REPORT_NOT_CANONICAL: rerun validate_source_coverage.py")
    if verified_coverage.get("formal_candidate_generation") != "allowed":
        raise ValueError("COVERAGE_GATE_BLOCKED: evidence cannot be frozen for candidates")
    inputs = {
        "run_manifest": attest_file(args.run_manifest),
        "manifest": attest_file(args.manifest),
        "coverage": attest_file(args.coverage),
        "evidence": attest_file(args.evidence),
        "sample": attest_file(args.sample),
        "registry": attest_file(args.registry),
    }
    packet = freeze(
        manifest, verified_coverage, load(args.evidence), load(args.sample), registry, inputs
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"stage": packet["stage"], "evidence_packet_hash": packet["evidence_packet_hash"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
