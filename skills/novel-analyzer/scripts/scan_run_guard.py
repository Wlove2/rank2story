#!/usr/bin/env python3
"""Create isolated scan runs and audit claims made by acquisition manifests."""

from __future__ import annotations

import argparse
import os
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "references" / "source-registry.json"
DEFAULT_OUTPUT_ROOT = Path(os.environ.get("NOVEL_SCAN_ROOT", str(Path.cwd() / "data" / "scans")))
PASS_STATUSES = {"success", "complete"}
RAW_ARTIFACT_TYPES = {
    "raw_response",
    "raw_snapshot",
    "structured_capture",
    "transcript",
    "screenshot",
}
STAGE_DIRECTORY_NAMES = (
    "raw",
    "normalized",
    "manifests",
    "reports",
    "market",
    "candidates",
    "reviews",
)
FORBIDDEN_RUN_EXECUTABLE_SUFFIXES = {".py", ".cmd", ".bat", ".ps1", ".sh"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def path_text(path: Path) -> str:
    return str(path.resolve())


def build_run_paths(run_root: Path, source_ids: list[str], lane: str) -> dict[str, Any]:
    directories = {name: run_root / name for name in STAGE_DIRECTORY_NAMES}
    source_dirs = {
        source_id: directories["raw"] / source_id
        for source_id in source_ids
    }
    for directory in [*directories.values(), *source_dirs.values()]:
        directory.mkdir(parents=True, exist_ok=False)
    files = {
        "run_manifest": path_text(run_root / "run_manifest.json"),
        "acquisition_manifest": path_text(run_root / "acquisition_manifest.json"),
        "preflight_report": path_text(directories["reports"] / "preflight.json"),
        "scan_coverage_report": path_text(directories["reports"] / "scan_coverage.json"),
        "candidate_coverage_report": path_text(directories["reports"] / "candidate_coverage.json"),
        "evidence_packet": path_text(directories["normalized"] / "evidence_packet.json"),
        "deliberation_state": path_text(directories["reviews"] / "deliberation_state.json"),
        "deliberation_gate": path_text(directories["reviews"] / "deliberation_gate.json"),
    }
    if lane == "short":
        files.update({
            "short_evidence_catalog": path_text(directories["normalized"] / "short_evidence_catalog.json"),
            "short_raw_input": path_text(directories["candidates"] / "short_raw_input.json"),
            "short_verification": path_text(directories["reviews"] / "short_verification.json"),
        })
    else:
        files.update({
            "long_raw_input": path_text(directories["candidates"] / "long_raw_input.json"),
            "long_evidence_packet": path_text(directories["normalized"] / "long_evidence_packet.json"),
        })
    return {
        "directories": {key: path_text(value) for key, value in directories.items()},
        "source_dirs": {key: path_text(value) for key, value in source_dirs.items()},
        "candidate_output_dirs": {lane: path_text(directories["candidates"] / lane)},
        "files": files,
    }


def initialize_run(
    profile_id: str,
    output_root: Path,
    registry: dict[str, Any],
    *,
    now: datetime | None = None,
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    local_started = now or datetime.now().astimezone()
    if local_started.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    started = local_started.astimezone(timezone.utc)
    lane = "short" if profile_id == "short_production" else "long"
    date_partition = local_started.strftime("%Y%m%d")
    base_id = f"{started:%Y%m%dT%H%M%SZ}-{lane}"
    run_id = base_id
    date_root = output_root / date_partition
    run_root = date_root / run_id
    suffix = 2
    while run_root.exists():
        run_id = f"{base_id}-{suffix}"
        run_root = date_root / run_id
        suffix += 1
    run_root.mkdir(parents=True)
    profile = registry["coverage_profiles"][profile_id]
    scan_source_ids = list(profile["required_source_ids"])
    candidate_source_ids = list(profile.get("candidate_context_source_ids", []))
    source_phases = {
        **{source_id: "scan" for source_id in scan_source_ids},
        **{source_id: "candidate_context" for source_id in candidate_source_ids},
    }
    source_ids = list(source_phases)
    paths = build_run_paths(run_root, source_ids, lane)
    run_manifest = {
        "schema_version": 2,
        "run_id": run_id,
        "profile_id": profile_id,
        "lane": lane,
        "date_partition": date_partition,
        "started_at": iso(started),
        "run_root": path_text(run_root),
        "storage_contract": {
            "base_root": path_text(output_root),
            "layout": "base_root/YYYYMMDD/YYYYMMDDTHHMMSSZ-lane[-N]",
            "paths_are_authoritative": True,
            "desktop_output_forbidden": True,
        },
        "paths": paths,
        "rank_input_policy": "current_run_only",
        "previous_rank_inputs_allowed": False,
        "phase": "initialized",
    }
    acquisition_manifest = {
        "schema_version": 2,
        "run_id": run_id,
        "profile_id": profile_id,
        "lane": lane,
        "started_at": iso(started),
        "sources": [
            {
                "source_id": source_id,
                "phase": source_phases[source_id],
                "output_dir": paths["source_dirs"][source_id],
                "run_id": run_id,
                "status": "not_run",
                "artifacts": [],
            }
            for source_id in source_ids
        ],
    }
    Path(paths["files"]["run_manifest"]).write_text(
        json.dumps(run_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    Path(paths["files"]["acquisition_manifest"]).write_text(
        json.dumps(acquisition_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return run_root, run_manifest, acquisition_manifest


def attest_artifact(run_manifest: dict[str, Any], path: Path, artifact_type: str) -> dict[str, Any]:
    run_root = Path(run_manifest["run_root"]).resolve()
    resolved = path.resolve()
    if artifact_type not in RAW_ARTIFACT_TYPES:
        raise ValueError(f"unsupported artifact type: {artifact_type}")
    if not is_within(resolved, run_root):
        raise ValueError(f"artifact must stay inside run root: {resolved}")
    if not resolved.is_file() or resolved.stat().st_size <= 0:
        raise ValueError(f"artifact is missing or empty: {resolved}")
    return {
        "path": resolved.relative_to(run_root).as_posix(),
        "artifact_type": artifact_type,
        "bytes": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
        "file_mtime": iso(datetime.fromtimestamp(resolved.stat().st_mtime, tz=timezone.utc)),
    }


def audit_path_contract(run_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    run_root = Path(str(run_manifest.get("run_root") or "")).resolve()
    storage = run_manifest.get("storage_contract")
    paths = run_manifest.get("paths")
    if not isinstance(storage, dict) or storage.get("paths_are_authoritative") is not True:
        return [{"reason": "PATH_CONTRACT_MISSING"}]
    base_root = Path(str(storage.get("base_root") or "")).resolve()
    if not is_within(run_root, base_root):
        failures.append({"reason": "RUN_ROOT_OUTSIDE_STORAGE_ROOT", "run_root": str(run_root)})
    if not isinstance(paths, dict):
        return failures + [{"reason": "RUN_PATHS_MISSING"}]
    for group in ("directories", "files", "source_dirs", "candidate_output_dirs"):
        values = paths.get(group)
        if not isinstance(values, dict) or not values:
            failures.append({"reason": "RUN_PATH_GROUP_MISSING", "group": group})
            continue
        for key, value in values.items():
            path = Path(str(value)).resolve()
            if not is_within(path, run_root):
                failures.append({"reason": "RUN_PATH_OUTSIDE_ROOT", "group": group, "key": key, "path": str(path)})
    source_dirs = paths.get("source_dirs", {})
    if isinstance(source_dirs, dict):
        resolved = [str(Path(str(value)).resolve()) for value in source_dirs.values()]
        if len(resolved) != len(set(resolved)):
            failures.append({"reason": "SOURCE_OUTPUT_PATH_COLLISION"})
    return failures


def audit_manifest(
    run_manifest: dict[str, Any],
    acquisition_manifest: dict[str, Any],
) -> dict[str, Any]:
    failures = audit_path_contract(run_manifest)
    run_id = run_manifest.get("run_id")
    run_root = Path(str(run_manifest.get("run_root") or "")).resolve()
    started = parse_time(run_manifest.get("started_at"))
    if run_root.is_dir():
        for path in run_root.rglob("*"):
            if path.is_file() and path.suffix.lower() in FORBIDDEN_RUN_EXECUTABLE_SUFFIXES:
                failures.append({
                    "reason": "AD_HOC_EXECUTABLE_IN_RUN",
                    "path": path.relative_to(run_root).as_posix(),
                })
    if acquisition_manifest.get("run_id") != run_id:
        failures.append({"reason": "RUN_ID_MISMATCH", "expected": run_id, "observed": acquisition_manifest.get("run_id")})
    if run_manifest.get("rank_input_policy") != "current_run_only" or run_manifest.get("previous_rank_inputs_allowed") is not False:
        failures.append({"reason": "CURRENT_RUN_ONLY_POLICY_MISSING"})
    for source in acquisition_manifest.get("sources", []):
        if source.get("status") not in PASS_STATUSES:
            continue
        source_id = source.get("source_id")
        if source.get("run_id") != run_id:
            failures.append({"source_id": source_id, "reason": "SOURCE_RUN_ID_MISMATCH"})
        expected_output = run_manifest.get("paths", {}).get("source_dirs", {}).get(source_id)
        if source.get("output_dir") != expected_output:
            failures.append({"source_id": source_id, "reason": "SOURCE_OUTPUT_PATH_MISMATCH"})
        captured = parse_time(source.get("captured_at"))
        if captured is None:
            failures.append({"source_id": source_id, "reason": "CAPTURED_AT_MISSING_OR_INVALID"})
        elif started is not None and captured < started:
            failures.append({"source_id": source_id, "reason": "ARTIFACT_PREDATES_RUN"})
        artifacts = source.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            failures.append({"source_id": source_id, "reason": "SUCCESS_WITHOUT_RAW_ARTIFACT"})
            continue
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                failures.append({"source_id": source_id, "reason": "ARTIFACT_ATTESTATION_MISSING"})
                continue
            relative = artifact.get("path")
            if not isinstance(relative, str) or not relative:
                failures.append({"source_id": source_id, "reason": "ARTIFACT_PATH_MISSING"})
                continue
            path = (run_root / relative).resolve()
            if not is_within(path, run_root):
                failures.append({"source_id": source_id, "reason": "ARTIFACT_OUTSIDE_RUN_ROOT", "path": relative})
                continue
            if not path.is_file() or path.stat().st_size <= 0:
                failures.append({"source_id": source_id, "reason": "ARTIFACT_MISSING_OR_EMPTY", "path": relative})
                continue
            if artifact.get("artifact_type") not in RAW_ARTIFACT_TYPES:
                failures.append({"source_id": source_id, "reason": "ARTIFACT_TYPE_INVALID", "path": relative})
            actual_size = path.stat().st_size
            if artifact.get("bytes") != actual_size:
                failures.append({"source_id": source_id, "reason": "ARTIFACT_SIZE_MISMATCH", "path": relative})
            actual_hash = sha256_file(path)
            if artifact.get("sha256") != actual_hash:
                failures.append({"source_id": source_id, "reason": "ARTIFACT_HASH_MISMATCH", "path": relative})
            artifact_mtime = parse_time(artifact.get("file_mtime"))
            actual_mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if artifact_mtime is None or abs((artifact_mtime - actual_mtime).total_seconds()) > 1:
                failures.append({"source_id": source_id, "reason": "ARTIFACT_MTIME_MISMATCH", "path": relative})
            elif started is not None and artifact_mtime < started:
                failures.append({"source_id": source_id, "reason": "ARTIFACT_FILE_PREDATES_RUN", "path": relative})
    return {
        "run_id": run_id,
        "artifact_integrity": "passed" if not failures else "failed",
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--profile", required=True)
    init_parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)

    attest_parser = subparsers.add_parser("attest")
    attest_parser.add_argument("--run-manifest", type=Path, required=True)
    attest_parser.add_argument("--artifact", type=Path, required=True)
    attest_parser.add_argument("--artifact-type", required=True, choices=sorted(RAW_ARTIFACT_TYPES))

    audit_parser = subparsers.add_parser("audit")
    audit_parser.add_argument("--run-manifest", type=Path, required=True)
    audit_parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "init":
        registry = json.loads(args.registry.read_text(encoding="utf-8"))
        configured_root = registry.get("runtime_contract", {}).get("scan_output_root")
        output_root = Path(configured_root) if configured_root else DEFAULT_OUTPUT_ROOT
        run_root, run_manifest, _ = initialize_run(args.profile, output_root, registry)
        print(json.dumps({
            "run_id": run_manifest["run_id"],
            "run_root": str(run_root),
            "run_manifest": run_manifest["paths"]["files"]["run_manifest"],
            "acquisition_manifest": run_manifest["paths"]["files"]["acquisition_manifest"],
            "paths": run_manifest["paths"],
        }, ensure_ascii=False, indent=2))
        return 0
    run_manifest = json.loads(args.run_manifest.read_text(encoding="utf-8"))
    if args.command == "attest":
        print(json.dumps(attest_artifact(run_manifest, args.artifact, args.artifact_type), ensure_ascii=False, indent=2))
        return 0
    acquisition_manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    result = audit_manifest(run_manifest, acquisition_manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["artifact_integrity"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
