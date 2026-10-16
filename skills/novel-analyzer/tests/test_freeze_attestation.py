from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "freeze_evidence_packet.py"


def load(name):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


GUARD = load("scan_run_guard")
COVERAGE = load("validate_source_coverage")


class FreezeAttestationTest(unittest.TestCase):
    def test_cli_packet_binds_every_freeze_input_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry_path = ROOT / "references" / "source-registry.json"
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            _, run_manifest, manifest = GUARD.initialize_run(
                "short_production",
                root,
                registry,
            )
            definitions = {item["id"]: item for item in registry["sources"]}
            captured_at = datetime.now(timezone.utc).isoformat()
            for row in manifest["sources"]:
                if row["phase"] != "scan":
                    continue
                raw = Path(row["output_dir"]) / "raw.json"
                if row["source_id"] in {"xiaohongshu_novel_demand_shared", "bilibili_novel_demand_shared"}:
                    signal_types = [
                        "current_hotspot_or_rank_scan", "current_hotspot_or_rank_scan",
                        "curator_roundup", "curator_roundup",
                        "reader_demand_or_book_shortage", "reader_demand_or_book_shortage",
                        "negative_or_avoidance", "creator_market_analysis",
                    ]
                    items = []
                    for index, signal_type in enumerate(signal_types):
                        item = {
                            "source_url": f"https://example.test/{row['source_id']}/{index}",
                            "author": f"account-{index % 5}",
                            "published_at": "2026-07-20T10:00:00Z",
                            "primary_signal_type": signal_type,
                            "engagement": {"likes": index + 1},
                            "content_complete": True,
                            "full_text": "complete evidence " * 30,
                        }
                        if row["source_id"].startswith("xiaohongshu"):
                            item.update({"images_total": 2, "images_read": 2})
                        items.append(item)
                    raw.write_text(json.dumps({
                        "discovery": {"discovered_unique_entries": 30, "screened_entries": 15},
                        "items": items,
                    }), encoding="utf-8")
                else:
                    raw.write_text(json.dumps({"source_id": row["source_id"]}), encoding="utf-8")
                definition = definitions[row["source_id"]]
                row.update({
                    "status": "success",
                    "captured_at": captured_at,
                    "artifacts": [GUARD.attest_artifact(run_manifest, raw, "raw_response")],
                    "acquired_list_ids": definition.get("coverage", {}).get("required_list_ids", []),
                    "category_taxonomy_complete": True,
                    "signal_eligible_entries": 8,
                    "discovered_unique_entries": 30,
                    "screened_entries": 15,
                    "unique_accounts": 5,
                    "max_entries_per_account": 2,
                    "primary_signal_type_counts": {
                        "current_hotspot_or_rank_scan": 2,
                        "curator_roundup": 2,
                        "reader_demand_or_book_shortage": 2,
                        "negative_or_avoidance": 1,
                    },
                })
            paths = run_manifest["paths"]["files"]
            manifest_path = Path(paths["acquisition_manifest"])
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            coverage = COVERAGE.validate(
                "short_production",
                manifest,
                registry,
                stage="scan",
                run_manifest=run_manifest,
            )
            self.assertEqual(coverage["formal_candidate_generation"], "allowed")
            coverage_path = Path(paths["scan_coverage_report"])
            coverage_path.write_text(json.dumps(coverage), encoding="utf-8")
            evidence_path = Path(run_manifest["paths"]["directories"]["normalized"]) / "evidence.json"
            sample_path = Path(run_manifest["paths"]["directories"]["normalized"]) / "sample.json"
            evidence_path.write_text(json.dumps({"entries": [{"id": "e1"}]}), encoding="utf-8")
            sample_path.write_text(json.dumps({"selected_works": []}), encoding="utf-8")
            output = Path(paths["evidence_packet"])
            result = subprocess.run([
                sys.executable,
                str(SCRIPT),
                "--run-manifest", str(paths["run_manifest"]),
                "--manifest", str(manifest_path),
                "--coverage", str(coverage_path),
                "--evidence", str(evidence_path),
                "--sample", str(sample_path),
                "--output", str(output),
            ], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            packet = json.loads(output.read_text(encoding="utf-8"))
            provenance = packet["provenance"]
            self.assertEqual(provenance["assurance"], "local_content_hash_attestation")
            self.assertFalse(provenance["external_timestamp_verified"])
            self.assertEqual(
                set(provenance["input_files"]),
                {"run_manifest", "manifest", "coverage", "evidence", "sample", "registry"},
            )
            self.assertEqual(
                provenance["input_files"]["manifest"]["sha256"],
                hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            )


if __name__ == "__main__":
    unittest.main()
