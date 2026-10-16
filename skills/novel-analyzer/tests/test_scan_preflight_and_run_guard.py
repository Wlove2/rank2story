import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(name):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


PREFLIGHT = load("scan_preflight")
GUARD = load("scan_run_guard")
COVERAGE = load("validate_source_coverage")


class FakeResponse:
    status = 401

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def getcode(self):
        return self.status


class ScanPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads((ROOT / "references" / "source-registry.json").read_text(encoding="utf-8"))

    def test_wrong_python_fails_before_collectors(self):
        result = PREFLIGHT.run_preflight(
            "short_production",
            self.registry,
            expected_python="C:/definitely/not/the/current/python.exe",
            skip_network=True,
            command_finder=lambda _name: "C:/tool.exe",
        )
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(any(item["reason"] == "WRONG_PYTHON_INTERPRETER" for item in result["failures"]))
        self.assertEqual(result["next_action"], "fix_preflight_only_do_not_start_collectors")

    def test_http_401_is_reachable_transport(self):
        result = PREFLIGHT.probe_url("https://example.invalid/private", 1, opener=lambda *_args, **_kwargs: FakeResponse())
        self.assertTrue(result["reachable"])
        self.assertEqual(result["http_status"], 401)

    def test_verified_reader_sources_are_not_manual_placeholders(self):
        source_ids = {item["source_id"] for item in PREFLIGHT.manual_capture_sources("short_production", self.registry)}
        self.assertNotIn("fanqie_reader_short_rank_center", source_ids)

    def test_verified_reader_contracts_allow_start(self):
        checks, failures = PREFLIGHT.validate_source_contracts("short_production", self.registry)
        by_source = {item["source_id"]: item for item in checks}
        self.assertTrue(by_source["fanqie_reader_short_rank_center"]["ready"])
        self.assertTrue(by_source["qimao_reader_story_rank_center"]["ready"])
        self.assertFalse(any(item["source_id"] in {
            "fanqie_reader_short_rank_center", "qimao_reader_story_rank_center"
        } for item in failures))

    def test_verified_paid_collectors_are_executable_contracts(self):
        checks, failures = PREFLIGHT.validate_source_contracts("comprehensive_long_production", self.registry)
        by_source = {item["source_id"]: item for item in checks}
        for source_id in ("zongheng_public_rank_snapshot", "jjwxc_quarter_rank_snapshot", "qidian_paid_trend_target"):
            self.assertTrue(by_source[source_id]["ready"])
        self.assertFalse(any(item.get("source_id") in by_source and item.get("source_id") in {
            "zongheng_public_rank_snapshot", "jjwxc_quarter_rank_snapshot", "qidian_paid_trend_target"
        } for item in failures))

    def test_qidian_windows_only_collector_preflight(self):
        source = "qidian_paid_trend_target"
        issues = PREFLIGHT.unsupported_platform_collectors(
            "comprehensive_long_production", self.registry, platform_name="posix")
        self.assertEqual([item["source_id"] for item in issues], [source])
        self.assertEqual(issues[0]["reason"], "COLLECTOR_PLATFORM_UNSUPPORTED")
        self.assertEqual(PREFLIGHT.unsupported_platform_collectors(
            "comprehensive_long_production", self.registry, platform_name="nt"), [])
        self.assertEqual(PREFLIGHT.unsupported_platform_collectors(
            "short_production", self.registry, platform_name="posix"), [])
        result = PREFLIGHT.run_preflight(
            "comprehensive_long_production", self.registry,
            skip_network=True, platform_name="posix", command_finder=lambda _: "mock-cli")
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(any(item["reason"] == "COLLECTOR_PLATFORM_UNSUPPORTED"
                            for item in result["failures"]))

    def test_prose_collector_without_machine_contract_is_rejected(self):
        registry = json.loads(json.dumps(self.registry))
        target = next(
            item for item in registry["sources"]
            if item["id"] == "fanqie_writer_hot_stories"
        )
        target.pop("collection_contract")
        target["collector"] = "registered target: model should find it"
        _, failures = PREFLIGHT.validate_source_contracts("short_production", registry)
        self.assertTrue(any(
            item["source_id"] == "fanqie_writer_hot_stories"
            and item["reason"] == "REQUIRED_SOURCE_CONTRACT_MISSING"
            for item in failures
        ))


class ScanRunGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads((ROOT / "references" / "source-registry.json").read_text(encoding="utf-8"))

    def test_init_is_current_run_only_and_starts_all_sources_not_run(self):
        with tempfile.TemporaryDirectory() as directory:
            run_root, run_manifest, acquisition = GUARD.initialize_run(
                "short_production",
                Path(directory),
                self.registry,
                now=datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc),
            )
            self.assertEqual(run_manifest["rank_input_policy"], "current_run_only")
            self.assertFalse(run_manifest["previous_rank_inputs_allowed"])
            self.assertTrue((run_root / "raw").is_dir())
            self.assertTrue(all(item["status"] == "not_run" for item in acquisition["sources"]))

    def test_success_without_nonempty_attested_raw_file_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            _, run_manifest, acquisition = GUARD.initialize_run(
                "short_production",
                Path(directory),
                self.registry,
                now=datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc),
            )
            source = acquisition["sources"][0]
            source.update({"status": "success", "captured_at": "2026-07-19T10:01:00Z"})
            result = GUARD.audit_manifest(run_manifest, acquisition)
            self.assertEqual(result["artifact_integrity"], "failed")
            self.assertTrue(any(item["reason"] == "SUCCESS_WITHOUT_RAW_ARTIFACT" for item in result["failures"]))

    def test_attested_current_run_raw_file_passes_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            run_root, run_manifest, acquisition = GUARD.initialize_run(
                "short_production",
                Path(directory),
                self.registry,
                now=datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc),
            )
            raw = run_root / "raw" / "fanqie.json"
            raw.write_text('{"items":[1]}\n', encoding="utf-8")
            source = acquisition["sources"][0]
            source.update({
                "status": "success",
                "captured_at": "2026-07-19T10:01:00Z",
                "artifacts": [GUARD.attest_artifact(run_manifest, raw, "raw_response")],
            })
            result = GUARD.audit_manifest(run_manifest, acquisition)
            self.assertEqual(result["artifact_integrity"], "passed")

    def test_ad_hoc_executable_inside_run_is_audit_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            run_root, run_manifest, acquisition = GUARD.initialize_run(
                "short_production",
                Path(directory),
                self.registry,
                now=datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc),
            )
            (run_root / "collect.sh").write_text("echo unsafe\n", encoding="utf-8")
            result = GUARD.audit_manifest(run_manifest, acquisition)
            self.assertTrue(any(
                item["reason"] == "AD_HOC_EXECUTABLE_IN_RUN"
                for item in result["failures"]
            ))

    def test_candidate_context_is_not_part_of_scan_gate(self):
        profile = self.registry["coverage_profiles"]["short_production"]
        definitions = {item["id"]: item for item in self.registry["sources"]}
        sources = []
        for source_id in profile["required_source_ids"]:
            definition = definitions[source_id]
            row = {
                "source_id": source_id,
                "status": "success",
                "acquired_list_ids": definition.get("coverage", {}).get("required_list_ids", []),
                "category_taxonomy_complete": True,
                "signal_eligible_entries": 8,
                "discovered_unique_entries": 30,
                "screened_entries": 15,
                "unique_accounts": 5,
                "max_entries_per_account": 2,
                "primary_signal_type_counts": {"current_hotspot_or_rank_scan": 2, "curator_roundup": 2, "reader_demand_or_book_shortage": 2, "negative_or_avoidance": 1},
            }
            sources.append(row)
        scan = COVERAGE.validate("short_production", {"sources": sources}, self.registry, stage="scan")
        candidate = COVERAGE.validate("short_production", {"sources": sources}, self.registry, stage="candidate")
        self.assertEqual(scan["formal_candidate_generation"], "allowed")
        self.assertEqual(candidate["formal_candidate_generation"], "blocked")
        self.assertTrue(any(item["source_id"] == "fanqie_writer_activities" for item in candidate["failures"]))


if __name__ == "__main__":
    unittest.main()
