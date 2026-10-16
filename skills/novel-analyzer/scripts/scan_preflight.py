#!/usr/bin/env python3
"""Fail fast before a production novel scan starts.

The preflight is intentionally read-only.  It never installs packages, changes
browser state, or starts collectors.  Its output is small enough to keep in the
conversation while the full report is written to disk.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "references" / "source-registry.json"
READY_CONTRACT_STATUS = "verified_executable"
READY_COVERAGE_CAPABILITY = "complete"


def normalized_path(value: str | os.PathLike[str]) -> str:
    return os.path.normcase(os.path.realpath(os.fspath(value)))


def python_interpreter_matches(actual: str, expected: str | None) -> bool:
    """A bare 'python' selects the active interpreter; an explicit path remains pinned."""
    if not expected or expected.strip().lower() in {"python", "python.exe", "python3", "python3.exe"}:
        return True
    return normalized_path(actual) == normalized_path(expected)


def resolve_file_dependency(value: str | os.PathLike[str]) -> Path:
    """Resolve relative external dependencies against the repository root, never CWD."""
    supplied = os.environ.get("NOVEL_FANQIE_COLLECTOR", "").strip()
    canonical = Path("external/FanqieRankTracker/scrape_fanqie_ranks.py")
    path = Path(supplied) if supplied and Path(value) == canonical else Path(value)
    return path if path.is_absolute() else ROOT.parent.parent / path


def probe_url(
    url: str,
    timeout: float,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "novel-analyzer-preflight/1.0", "Accept-Encoding": "identity"},
    )
    try:
        with opener(request, timeout=timeout) as response:
            status = int(getattr(response, "status", response.getcode()))
        return {"url": url, "reachable": 100 <= status < 500, "http_status": status}
    except urllib.error.HTTPError as exc:
        # 401/403 still prove that DNS, TLS and the remote endpoint are reachable.
        status = int(exc.code)
        return {"url": url, "reachable": 100 <= status < 500, "http_status": status}
    except Exception as exc:  # network stacks expose several platform exceptions
        return {"url": url, "reachable": False, "error": f"{type(exc).__name__}: {exc}"}


def referenced_script_collectors(profile_id: str, registry: dict[str, Any]) -> list[str]:
    profile = registry["coverage_profiles"][profile_id]
    source_ids = profile["required_source_ids"]
    definitions = {item["id"]: item for item in registry["sources"]}
    scripts: list[str] = []
    for source_id in source_ids:
        contract = definitions[source_id].get("collection_contract")
        if not isinstance(contract, dict) or contract.get("kind") not in {"python_script", "powershell_script"}:
            continue
        entrypoint = contract.get("entrypoint")
        if isinstance(entrypoint, str) and entrypoint.startswith("scripts/") and entrypoint.endswith(".py"):
            scripts.append(entrypoint)
    return list(dict.fromkeys(scripts))


def manual_capture_sources(profile_id: str, registry: dict[str, Any]) -> list[dict[str, str]]:
    """Compatibility view of sources that cannot start production collection."""
    profile = registry["coverage_profiles"][profile_id]
    definitions = {item["id"]: item for item in registry["sources"]}
    output = []
    for source_id in profile["required_source_ids"]:
        definition = definitions[source_id]
        contract = definition.get("collection_contract")
        status = contract.get("status") if isinstance(contract, dict) else "missing"
        capability = contract.get("coverage_capability") if isinstance(contract, dict) else "none"
        if status != READY_CONTRACT_STATUS or capability != READY_COVERAGE_CAPABILITY:
            output.append({
                "source_id": source_id,
                "acquisition_mode": str(definition.get("acquisition_mode") or "unknown"),
                "collector": str(definition.get("collector") or ""),
                "contract_status": str(status),
                "coverage_capability": str(capability),
                "failure_code": str(contract.get("failure_code") or "REQUIRED_SOURCE_CONTRACT_MISSING")
                if isinstance(contract, dict)
                else "REQUIRED_SOURCE_CONTRACT_MISSING",
            })
    return output


def unsupported_platform_collectors(
    profile_id: str, registry: dict[str, Any], *, platform_name: str | None = None,
) -> list[dict[str, str]]:
    """Identify collector scripts that rely on OS-only system executables."""
    platform = os.name if platform_name is None else platform_name
    if platform == "nt":
        return []
    by_id = {source["id"]: source for source in registry["sources"]}
    issues = []
    for source_id in registry["coverage_profiles"][profile_id]["required_source_ids"]:
        contract = by_id[source_id].get("collection_contract") or {}
        entry = str(contract.get("entrypoint") or "")
        if contract.get("kind") == "powershell_script" and entry.endswith("collect_qidian_browser_ranks.ps1"):
            issues.append({"reason": "COLLECTOR_PLATFORM_UNSUPPORTED",
                           "source_id": source_id, "entrypoint": entry,
                           "required_platform": "Windows", "current_platform": platform})
    return issues


def validate_source_contracts(profile_id: str, registry: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Validate that every required source has a complete executable contract."""
    profile = registry["coverage_profiles"][profile_id]
    definitions = {item["id"]: item for item in registry["sources"]}
    checks: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for source_id in profile["required_source_ids"]:
        definition = definitions.get(source_id)
        if not isinstance(definition, dict):
            failure = {"source_id": source_id, "reason": "REQUIRED_SOURCE_DEFINITION_MISSING"}
            checks.append({**failure, "ready": False})
            failures.append(failure)
            continue
        contract = definition.get("collection_contract")
        if not isinstance(contract, dict):
            failure = {"source_id": source_id, "reason": "REQUIRED_SOURCE_CONTRACT_MISSING"}
            checks.append({**failure, "ready": False})
            failures.append(failure)
            continue
        status = contract.get("status")
        capability = contract.get("coverage_capability")
        kind = contract.get("kind")
        item = {
            "source_id": source_id,
            "status": status,
            "coverage_capability": capability,
            "kind": kind,
            "entrypoint": contract.get("entrypoint"),
            "workflow_id": contract.get("workflow_id"),
            "target": contract.get("target") or contract.get("required_target"),
            "failure_code": contract.get("failure_code"),
            "ready": status == READY_CONTRACT_STATUS and capability == READY_COVERAGE_CAPABILITY,
        }
        checks.append(item)
        if not item["ready"]:
            failures.append({
                "source_id": source_id,
                "reason": "REQUIRED_SOURCE_CONTRACT_NOT_EXECUTABLE",
                "contract_status": status,
                "coverage_capability": capability,
                "source_failure_code": contract.get("failure_code"),
                "required_target": contract.get("required_target"),
            })
            continue
        if kind in {"python_script", "powershell_script"}:
            entrypoint = contract.get("entrypoint")
            expected_suffix = ".py" if kind == "python_script" else ".ps1"
            if not isinstance(entrypoint, str) or not entrypoint.startswith("scripts/") or not entrypoint.endswith(expected_suffix):
                failures.append({
                    "source_id": source_id,
                    "reason": "SCRIPT_COLLECTION_ENTRYPOINT_INVALID",
                    "entrypoint": entrypoint,
                    "kind": kind,
                })
        elif kind == "registered_workflow":
            commands = contract.get("commands")
            if not contract.get("workflow_id") or not isinstance(commands, list) or not commands:
                failures.append({
                    "source_id": source_id,
                    "reason": "REGISTERED_WORKFLOW_CONTRACT_INVALID",
                })
        else:
            failures.append({
                "source_id": source_id,
                "reason": "COLLECTION_CONTRACT_KIND_INVALID",
                "kind": kind,
            })
    return checks, failures


def resolve_chromium_executable(playwright_executable: str | os.PathLike[str]) -> tuple[Path, bool]:
    """Use operator-supplied local Chromium/Chrome binary when configured."""
    configured = os.environ.get("NOVEL_CHROMIUM_EXECUTABLE", "").strip()
    return (Path(configured), True) if configured else (Path(playwright_executable), False)


def check_playwright(launch_browser: bool) -> dict[str, Any]:
    if importlib.util.find_spec("playwright.sync_api") is None:
        return {"available": False, "browser_launch_ok": False, "error": "playwright.sync_api not importable"}
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            executable, overridden = resolve_chromium_executable(playwright.chromium.executable_path)
            result: dict[str, Any] = {
                "available": True,
                "chromium_executable": str(executable),
                "chromium_exists": executable.is_file(),
                "browser_custom_executable": overridden,
                "browser_launch_ok": None,
            }
            if launch_browser:
                if not executable.is_file():
                    raise FileNotFoundError(f"Chromium executable missing: {executable}")
                browser = playwright.chromium.launch(headless=True, executable_path=str(executable) if overridden else None)
                browser.close()
                result["browser_launch_ok"] = True
            return result
    except Exception as exc:
        return {
            "available": True,
            "browser_launch_ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def run_preflight(
    profile_id: str,
    registry: dict[str, Any],
    *,
    expected_python: str | None = None,
    skip_network: bool = False,
    launch_browser: bool = False,
    platform_name: str | None = None,
    command_finder: Callable[[str], str | None] = shutil.which,
    endpoint_opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    runtime = registry.get("runtime_contract", {})
    expected = expected_python or runtime.get("windows_python")
    actual = normalized_path(sys.executable)
    checks: dict[str, Any] = {
        "python": {
            "actual": sys.executable,
            "expected": expected,
            "matches": python_interpreter_matches(sys.executable, expected),
        }
    }
    failures: list[dict[str, Any]] = []
    if not checks["python"]["matches"]:
        failures.append({"reason": "WRONG_PYTHON_INTERPRETER", **checks["python"]})

    playwright = check_playwright(launch_browser)
    checks["playwright"] = playwright
    if not playwright.get("available") or not playwright.get("chromium_exists"):
        failures.append({"reason": "PLAYWRIGHT_RUNTIME_UNAVAILABLE", **playwright})
    if launch_browser and playwright.get("browser_launch_ok") is not True:
        failures.append({"reason": "PLAYWRIGHT_BROWSER_LAUNCH_FAILED", **playwright})

    profile_preflight = runtime.get("preflight_profiles", {}).get(profile_id, {})
    commands = []
    for command in profile_preflight.get("commands", []):
        path = command_finder(command)
        commands.append({"command": command, "path": path, "available": bool(path)})
        if not path:
            failures.append({"reason": "REQUIRED_COMMAND_MISSING", "command": command})
    checks["commands"] = commands

    source_contracts, contract_failures = validate_source_contracts(profile_id, registry)
    checks["source_contracts"] = source_contracts
    failures.extend(contract_failures)
    platform_issues = unsupported_platform_collectors(profile_id, registry, platform_name=platform_name)
    checks["platform_collectors"] = platform_issues
    failures.extend(platform_issues)

    collectors = []
    for relative in referenced_script_collectors(profile_id, registry):
        path = ROOT / relative
        collectors.append({"collector": relative, "path": str(path), "exists": path.is_file()})
        if not path.is_file():
            failures.append({"reason": "REGISTERED_COLLECTOR_MISSING", "collector": relative})
    checks["script_collectors"] = collectors
    file_dependencies = []
    for configured in runtime.get("file_dependencies", []):
        path = resolve_file_dependency(str(configured))
        item = {"path": str(path), "exists": path.is_file()}
        file_dependencies.append(item)
        if not item["exists"]:
            failures.append({"reason": "REQUIRED_FILE_DEPENDENCY_MISSING", **item})
    checks["file_dependencies"] = file_dependencies

    built_in = runtime.get("built_in_fanqie_decoder", "scripts/fanqie_decoder.py")
    bundled_decoder = ROOT / built_in
    configured_decoder = os.environ.get("NOVEL_FANQIE_COLLECTOR", "").strip()
    selected_decoder = resolve_file_dependency(configured_decoder) if configured_decoder else bundled_decoder
    checks["fanqie_decoder"] = {
        "kind": "user_supplied" if configured_decoder else "bundled_conservative",
        "path": str(selected_decoder),
        "exists": selected_decoder.is_file(),
        "custom_font_mapping_included": False if not configured_decoder else None,
    }
    if not selected_decoder.is_file():
        failures.append({"reason": "FANQIE_DECODER_MISSING", "path": str(selected_decoder)})

    checks["manual_capture_sources"] = manual_capture_sources(profile_id, registry)

    endpoints = []
    if not skip_network:
        for url in profile_preflight.get("endpoints", []):
            result = probe_url(url, float(profile_preflight.get("timeout_seconds", 10)), endpoint_opener)
            endpoints.append(result)
            if not result["reachable"]:
                failures.append({"reason": "ENDPOINT_UNREACHABLE", **result})
    checks["endpoints"] = endpoints

    return {
        "schema_version": 1,
        "profile_id": profile_id,
        "status": "ready" if not failures else "blocked",
        "runtime_installs_forbidden": True,
        "checks": checks,
        "failures": failures,
        "next_action": "start_new_scan_run" if not failures else "fix_preflight_only_do_not_start_collectors",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--expected-python")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--skip-network", action="store_true", help="tests only; forbidden for production")
    parser.add_argument("--launch-browser", action="store_true")
    args = parser.parse_args()
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    result = run_preflight(
        args.profile,
        registry,
        expected_python=args.expected_python,
        skip_network=args.skip_network,
        launch_browser=args.launch_browser,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "profile_id": result["profile_id"],
        "failure_count": len(result["failures"]),
        "blocked_source_ids": [
            item["source_id"]
            for item in result["checks"]["source_contracts"]
            if not item["ready"]
        ],
        "manual_capture_source_ids": [item["source_id"] for item in result["checks"]["manual_capture_sources"]],
        "report": str(args.output),
    }, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
