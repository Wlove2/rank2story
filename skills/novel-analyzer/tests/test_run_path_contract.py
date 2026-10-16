import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import scan_run_guard as guard
import scan_start as start


class RunPathContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads((ROOT / "references" / "source-registry.json").read_text(encoding="utf-8"))

    def test_registry_uses_portable_scan_root(self):
        self.assertEqual(self.registry["runtime_contract"]["scan_output_root"], "./data/scans")

    def test_run_uses_date_then_unique_lane_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            first, first_manifest, _ = guard.initialize_run(
                "short_production",
                Path(directory),
                self.registry,
                now=datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc),
            )
            second, _, _ = guard.initialize_run(
                "short_production",
                Path(directory),
                self.registry,
                now=datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc),
            )
            self.assertEqual(first.parent.name, "20260719")
            self.assertEqual(first.name, "20260719T100000Z-short")
            self.assertEqual(second.name, "20260719T100000Z-short-2")
            self.assertTrue(first_manifest["storage_contract"]["paths_are_authoritative"])

    def test_every_source_gets_a_distinct_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            _, manifest, acquisition = guard.initialize_run(
                "comprehensive_long_production",
                Path(directory),
                self.registry,
                now=datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc),
            )
            self.assertEqual(set(manifest["paths"]["candidate_output_dirs"]), {"long"})
            self.assertIn("long_raw_input", manifest["paths"]["files"])
            self.assertNotIn("short_raw_input", manifest["paths"]["files"])
            paths = manifest["paths"]["source_dirs"]
            self.assertEqual(len(paths), len(set(paths.values())))
            self.assertEqual(
                {row["output_dir"] for row in acquisition["sources"]},
                set(paths.values()),
            )
            self.assertTrue(all(Path(value).is_dir() for value in paths.values()))

    def test_path_collision_is_audit_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            _, manifest, acquisition = guard.initialize_run(
                "short_production",
                Path(directory),
                self.registry,
                now=datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc),
            )
            keys = list(manifest["paths"]["source_dirs"])
            manifest["paths"]["source_dirs"][keys[1]] = manifest["paths"]["source_dirs"][keys[0]]
            result = guard.audit_manifest(manifest, acquisition)
            self.assertTrue(any(row["reason"] == "SOURCE_OUTPUT_PATH_COLLISION" for row in result["failures"]))

    def test_scan_start_writes_preflight_inside_the_new_run(self):
        fake = {
            "status": "ready",
            "failures": [],
            "checks": {"manual_capture_sources": []},
        }
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(start.preflight, "run_preflight", return_value=fake):
            result = start.start_scan(
                "short_production",
                self.registry,
                output_root=Path(directory),
                now=datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc),
            )
            self.assertEqual(result["status"], "ready")
            self.assertTrue(Path(result["preflight_report"]).is_file())
            self.assertTrue(guard.is_within(Path(result["preflight_report"]), Path(result["run_root"])))
            manifest = json.loads(Path(result["run_manifest"]).read_text(encoding="utf-8"))
            self.assertEqual(manifest["phase"], "preflight_ready")

    def test_cli_does_not_offer_an_output_root_override(self):
        text = (ROOT / "scripts" / "scan_run_guard.py").read_text(encoding="utf-8")
        start_text = (ROOT / "scripts" / "scan_start.py").read_text(encoding="utf-8")
        self.assertNotIn('add_argument("--output-root"', text)
        self.assertNotIn('add_argument("--output-root"', start_text)
    def test_missing_file_dependency_blocks_preflight(self):
        registry = json.loads(json.dumps(self.registry))
        registry["runtime_contract"]["file_dependencies"] = ["C:/definitely/missing/decoder.py"]
        result = start.preflight.run_preflight(
            "short_production",
            registry,
            skip_network=True,
            command_finder=lambda _name: "C:/tool.exe",
        )
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(any(row["reason"] == "REQUIRED_FILE_DEPENDENCY_MISSING" for row in result["failures"]))



    def test_skill_has_no_old_shared_output_placeholders(self):
        router = (ROOT / 'SKILL.md').read_text(encoding='utf-8')
        scan = (ROOT.parent / 'novel-market-scan' / 'SKILL.md').read_text(encoding='utf-8')
        self.assertIn('./data/scans', scan)
        self.assertIn('novel-market-scan', router)
        self.assertNotIn('<short-source-dir>', router + scan)
        self.assertNotIn('<long-output-dir>', router + scan)
        return
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("D:/example/搜索/YYYYMMDD/", text)
        self.assertIn("scripts/scan_start.py --profile", text)
        self.assertNotIn("<short-source-dir>", text)
        self.assertNotIn("<long-output-dir>", text)
        self.assertNotIn("D:/example/source_snapshots", text.replace("禁止自行选择 Desktop、`D:/example/source_snapshots`", ""))


if __name__ == "__main__":
    unittest.main()
