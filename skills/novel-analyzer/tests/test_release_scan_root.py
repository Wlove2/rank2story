"""Offline checks for portable release scan-root configuration."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import scan_start
import scan_preflight
import fanqie_refresh


class ReleaseScanRootTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads((ROOT / "references" / "source-registry.json").read_text(encoding="utf-8"))

    def mocked_scan(self, profile="short_production", **kwargs):
        with mock.patch.object(scan_start.preflight, "run_preflight", return_value={
            "status": "ready", "failures": [],
            "checks": {"source_contracts": [], "manual_capture_sources": []},
        }):
            return scan_start.start_scan(profile, self.registry, **kwargs)

    def test_environment_root_overrides_registry_default(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "safe-project-scans"
            with mock.patch.dict(os.environ, {"NOVEL_SCAN_ROOT": str(root)}):
                result = self.mocked_scan()
            run = Path(result["run_root"])
            self.assertTrue(run.is_relative_to(root))
            self.assertTrue(Path(result["run_manifest"]).is_file())
            self.assertEqual(result["status"], "ready")

    def test_generic_python_configuration_accepts_active_virtualenv(self):
        self.assertTrue(scan_preflight.python_interpreter_matches(sys.executable, "python"))
        self.assertTrue(scan_preflight.python_interpreter_matches(sys.executable, "python3"))
        self.assertTrue(scan_preflight.python_interpreter_matches(sys.executable, None))
        self.assertFalse(scan_preflight.python_interpreter_matches(
            sys.executable, str(ROOT / "fake_python_executable")
        ))

    def test_browser_override_uses_operator_supplied_executable(self):
        with mock.patch.dict(os.environ, {"NOVEL_CHROMIUM_EXECUTABLE": str(ROOT / "example-chrome.exe")}):
            path, custom = scan_preflight.resolve_chromium_executable("/missing/bundled/chromium")
        self.assertEqual(path, ROOT / "example-chrome.exe")
        self.assertTrue(custom)

    def test_browser_without_override_uses_playwright_bundled_path(self):
        with mock.patch.dict(os.environ, {"NOVEL_CHROMIUM_EXECUTABLE": ""}):
            path, custom = scan_preflight.resolve_chromium_executable("/playwright/bundled/chromium")
        self.assertEqual(path, Path("/playwright/bundled/chromium"))
        self.assertFalse(custom)

    def test_external_collector_override_is_consistent_between_preflight_and_runner(self):
        with tempfile.TemporaryDirectory() as temporary:
            custom = Path(temporary) / "authorized-collector.py"
            custom.write_text("def decode_text(value): return value\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"NOVEL_FANQIE_COLLECTOR": str(custom)}):
                preflight_path = scan_preflight.resolve_file_dependency(
                    "external/FanqieRankTracker/scrape_fanqie_ranks.py"
                )
                runner_path = fanqie_refresh.resolve_optional_collector(None)
            self.assertEqual(preflight_path, custom)
            self.assertEqual(runner_path, custom)
            self.assertTrue(preflight_path.is_file())

    def test_external_dependency_is_resolved_from_repository_not_cwd(self):
        expected = ROOT.parent.parent / "external" / "FanqieRankTracker" / "scrape_fanqie_ranks.py"
        self.assertEqual(
            scan_preflight.resolve_file_dependency(
                "external/FanqieRankTracker/scrape_fanqie_ranks.py"
            ), expected
        )

    def test_explicit_output_root_wins_over_environment(self):
        with tempfile.TemporaryDirectory() as temp:
            explicit = Path(temp) / "explicit"
            env_value = Path(temp) / "environment"
            with mock.patch.dict(os.environ, {"NOVEL_SCAN_ROOT": str(env_value)}):
                result = self.mocked_scan(output_root=explicit)
            self.assertTrue(Path(result["run_root"]).is_relative_to(explicit))
            self.assertFalse(env_value.exists())


if __name__ == "__main__":
    unittest.main()
