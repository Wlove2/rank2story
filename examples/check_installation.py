"""Read-only installation self-check: does not connect to external websites."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "skills" / "novel-analyzer" / "references" / "source-registry.json"


def check_environment() -> dict:
    config = json.loads(REGISTRY.read_text(encoding="utf-8"))
    runtime = config["runtime_contract"]
    custom_decoder = os.environ.get("NOVEL_FANQIE_COLLECTOR", "").strip()
    decoder = Path(custom_decoder) if custom_decoder else ROOT / "skills" / "novel-analyzer" / "scripts" / "fanqie_decoder.py"
    if custom_decoder and not decoder.is_absolute():
        decoder = ROOT / decoder
    configured_browser = os.environ.get("NOVEL_CHROMIUM_EXECUTABLE", "").strip()
    browser_path = Path(configured_browser) if configured_browser else None
    if browser_path is None and importlib.util.find_spec("playwright"):
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                browser_path = Path(playwright.chromium.executable_path)
        except Exception:
            browser_path = None
    details = {
        "python": {
            "version": ".".join(map(str, sys.version_info[:3])),
            "supported": sys.version_info >= (3, 11),
        },
        "packages": {
            name: bool(importlib.util.find_spec(name))
            for name in ("lxml", "playwright", "pytest")
        },
        "commands": {
            name: bool(shutil.which(name))
            for name in ("opencli", "agent-reach")
        },
        "skills": {
            name: (ROOT / "skills" / name / "SKILL.md").is_file()
            for name in ("novel-market-scan", "novel-candidate-portfolio", "novel-analyzer")
        },
        "agent_skill_registration": "not_checked_by_this_script",
        "long_scan_os_supported": os.name == "nt",
        "external_files": {},
        "fanqie_decoder": {
            "source": "NOVEL_FANQIE_COLLECTOR" if custom_decoder else "bundled_conservative",
            "exists": decoder.is_file(),
            "custom_font_support": "operator_defined" if custom_decoder else "none_fail_closed",
        },
        "browser": {
            "source": "NOVEL_CHROMIUM_EXECUTABLE" if configured_browser else "playwright_default",
            "executable_exists": browser_path.is_file() if browser_path else False,
            "launch_tested": False,
        },
        "scan_root": {
            "source": "NOVEL_SCAN_ROOT" if os.environ.get("NOVEL_SCAN_ROOT") else "registry",
            "configured": bool(os.environ.get("NOVEL_SCAN_ROOT")),
        },
        "model_endpoint": "user supplied; not tested",
        "live_scraping_performed": False,
    }
    for raw in runtime.get("file_dependencies", []):
        location = Path(raw)
        if not location.is_absolute():
            location = ROOT / location
        details["external_files"][raw] = location.is_file()
    details["offline_ready"] = (
        details["python"]["supported"]
        and all(details["packages"].values())
        and all(details["skills"].values())
    )
    details["local_collection_dependencies_present"] = (
        details["offline_ready"]
        and all(details["commands"].values())
        and all(details["external_files"].values())
        and details["fanqie_decoder"]["exists"]
        and details["browser"]["executable_exists"]
    )
    details["next_steps"] = []
    if not all(details["skills"].values()):
        details["next_steps"].append("Restore all three Skill directories from the complete repository.")
    if not details["offline_ready"]:
        details["next_steps"].append("Use Python 3.11+ and install requirements.txt in an isolated environment.")
    if not details["browser"]["executable_exists"]:
        details["next_steps"].append("With approval, run: python -m playwright install chromium; or set NOVEL_CHROMIUM_EXECUTABLE.")
    for name, found in details["commands"].items():
        if not found:
            details["next_steps"].append(f"Install and configure {name} from its verified upstream project, with approval.")
    if not details["long_scan_os_supported"]:
        details["next_steps"].append("Full long-form scanning requires Windows for the current Qidian collector.")
    if details["fanqie_decoder"]["custom_font_support"] == "none_fail_closed":
        details["next_steps"].append("Fanqie custom-font ranks may need a separately licensed external decoder.")
    details["next_steps"].append("Platform authorization, browser launch, and live scraping remain unverified.")
    details["authenticated_site_access_verified"] = False
    details["live_scan_verified"] = False
    return details


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    state = check_environment()
    if args.json:
        print(json.dumps(state, indent=2, ensure_ascii=False))
    else:
        for group in ("python", "packages", "commands", "external_files"):
            print(group, state[group])
        print("Offline ready:", state["offline_ready"])
        print("Local scan dependencies present:", state["local_collection_dependencies_present"])
        print("Authenticated site access verified:", state["authenticated_site_access_verified"])
        print("No network requests or live collection were performed.")
    return 0  # An installation audit is a diagnostic, not a scan.


if __name__ == "__main__":
    raise SystemExit(main())
