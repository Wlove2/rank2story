#!/usr/bin/env python3
"""Create one fixed-location scan run and execute its mandatory preflight."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import scan_preflight as preflight
import scan_run_guard as guard


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "references" / "source-registry.json"


def start_scan(
    profile_id: str,
    registry: dict[str, Any],
    *,
    output_root: Path | None = None,
    now: datetime | None = None,
    skip_network: bool = False,
    launch_browser: bool = True,
    max_social_age_days: int | None = None,
) -> dict[str, Any]:
    if max_social_age_days is not None and (type(max_social_age_days) is not int or max_social_age_days < 0):
        raise ValueError("SOCIAL_FRESHNESS_POLICY_INVALID")
    configured_root = registry.get("runtime_contract", {}).get("scan_output_root")
    environment_root = os.environ.get("NOVEL_SCAN_ROOT")
    root = output_root if output_root is not None else (
        Path(environment_root) if environment_root else (
            Path(configured_root) if configured_root else guard.DEFAULT_OUTPUT_ROOT
        )
    )
    run_root, run_manifest, _ = guard.initialize_run(profile_id, root, registry, now=now)
    if max_social_age_days is not None:
        reference = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        run_manifest["social_freshness"] = {
            "max_age_days": max_social_age_days,
            "as_of_date": reference.date().isoformat(),
        }
    result = preflight.run_preflight(
        profile_id,
        registry,
        skip_network=skip_network,
        launch_browser=launch_browser,
    )
    report_path = Path(run_manifest["paths"]["files"]["preflight_report"])
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    run_manifest["phase"] = "preflight_ready" if result["status"] == "ready" else "preflight_blocked"
    run_manifest["preflight_status"] = result["status"]
    Path(run_manifest["paths"]["files"]["run_manifest"]).write_text(
        json.dumps(run_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {
        "status": result["status"],
        "profile_id": profile_id,
        "run_id": run_manifest["run_id"],
        "run_root": str(run_root),
        "run_manifest": run_manifest["paths"]["files"]["run_manifest"],
        "acquisition_manifest": run_manifest["paths"]["files"]["acquisition_manifest"],
        "preflight_report": str(report_path),
        "failure_count": len(result["failures"]),
        "blocked_source_ids": [
            item["source_id"]
            for item in result["checks"].get("source_contracts", [])
            if not item["ready"]
        ],
        "manual_capture_source_ids": [
            item["source_id"] for item in result["checks"]["manual_capture_sources"]
        ],
        "paths": run_manifest["paths"],
        "social_freshness": run_manifest.get("social_freshness"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True, choices=("short_production", "comprehensive_long_production"))
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--max-social-age-days", type=int, default=None, help="optional eligible social evidence age cap in UTC days")
    parser.add_argument("--skip-network", action="store_true", help="tests only; forbidden for production")
    parser.add_argument("--no-launch-browser", action="store_true", help="tests only; production launches Chromium")
    args = parser.parse_args()
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    result = start_scan(
        args.profile,
        registry,
        skip_network=args.skip_network,
        launch_browser=not args.no_launch_browser,
        max_social_age_days=args.max_social_age_days,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
