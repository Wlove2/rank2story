"""Offline synthetic scan artifact -> coverage -> freeze CLI -> story-first handoff.

No website access or real collection is performed. Synthetic source records
exercise real file attestation, coverage gates, freezing and candidate delivery.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "tests"))

import scan_run_guard as guard
import sync_acquisition_manifest as manifest_sync
import validate_source_coverage as coverage_validator
import freeze_evidence_packet as freezer
import test_candidate_controller_e2e as _candidate_fixture_module

REGISTRY_PATH = ROOT / "references" / "source-registry.json"
SOCIAL_IDS = {"bilibili_novel_demand_shared", "xiaohongshu_novel_demand_shared"}
SIGNAL_TYPES = (
    "current_hotspot_or_rank_scan", "current_hotspot_or_rank_scan",
    "curator_roundup", "curator_roundup",
    "reader_demand_or_book_shortage", "reader_demand_or_book_shortage",
    "negative_or_avoidance", "creator_market_analysis",
)


def save(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def social_payload(source_id: str, *, complete=True) -> dict:
    items = []
    for index, signal_type in enumerate(SIGNAL_TYPES):
        item = {
            "source_url": f"https://example.test/synthetic/{source_id}/{index}",
            "author": f"synthetic-account-{index % 5}",
            "published_at": "2026-10-01T01:00:00Z",
            "primary_signal_type": signal_type,
            "engagement": {"likes": index + 1},
            "content_complete": complete,
            "full_text": "synthetic full text " * 30,
            "source_relation": "independent",
        }
        if source_id.startswith("xiaohongshu"):
            item.update({"images_total": 2, "images_read": 2})
        items.append(item)
    return {
        "discovery": {"discovered_unique_entries": 30, "screened_entries": 15},
        "items": items,
    }


def prepare_synthetic_run(tmp: Path, lane: str, *, social_complete=True) -> dict:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    profile = "short_production" if lane == "short" else "comprehensive_long_production"
    root, run, manifest = guard.initialize_run(profile, tmp, registry)
    fixture = _candidate_fixture_module.CandidateControllerEndToEndTests()
    source_defs = {entry["id"]: entry for entry in registry["sources"]}
    raw_files = []

    for row in manifest["sources"]:
        if row["phase"] != "scan":
            continue
        source_id = row["source_id"]
        output = Path(row["output_dir"])
        expected_lists = source_defs[source_id].get("coverage", {}).get("required_list_ids", [])
        if source_id in SOCIAL_IDS:
            raw = output / "synthetic_social.json"
            save(raw, social_payload(source_id, complete=social_complete))
        elif source_id == "fanqie_public_web_ranks":
            raw = output / "collection_summary.json"
            ranks = [
                {"gender": gender, "rank_type": rank_type, "status": "success",
                 "valid_category_count": categories}
                for gender, rank_type, categories in (
                    ("female", "new_ranks", 18), ("female", "read_ranks", 18),
                    ("male", "new_ranks", 19), ("male", "read_ranks", 19)
                )
            ]
            save(raw, {
                "status": "success", "empty_categories": [], "valid_book_count": 80,
                "ranks": ranks, "synthetic_fixture": True
            })
        elif source_id == "qimao_public_web_ranks":
            raw = output / "manifest.json"
            save(raw, {
                "channels": [
                    {"channel": list_id, "status": "success", "valid_entries": 8}
                    for list_id in expected_lists
                ],
                "synthetic_fixture": True,
            })
        elif source_id == "fanqie_writer_hot_stories":
            raw = output / "manifest.json"
            save(raw, {
                "acquired_list_ids": expected_lists,
                "synthetic_fixture": True,
            })
            save(output / "normalized.json", [
                {"book_id": f"synthetic-{n}", "title": "合成标题"}
                for n in range(8)
            ])
        elif source_id == "qidian_paid_trend_target":
            # Synthetic fixture must use the real collector's verified schema,
            # including same-list URLs, twenty distinct book IDs and SHA256.
            official_urls = {
                "monthly_ticket": "https://www.qidian.com/rank/yuepiao/",
                "hot_sales": "https://www.qidian.com/rank/hotsales/",
                "read_index": "https://www.qidian.com/rank/readindex/",
                "recommendation": "https://www.qidian.com/rank/recom/",
                "new_book": "https://www.qidian.com/rank/signNewBkAll/",
            }
            captures = []
            for list_id in expected_lists:
                filename = f"raw_{list_id}_01.json"
                target = output / filename
                save(target, {
                    "url": official_urls[list_id],
                    "items": [
                        {"position": i + 1, "title": f"synthetic title {i}",
                         "url": f"https://www.qidian.com/book/{1040000000 + i}/"}
                        for i in range(20)
                    ],
                    "synthetic_fixture": True,
                })
                captures.append({
                    "list_id": list_id, "raw_file": filename,
                    "raw_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                    "final_url": official_urls[list_id], "item_count": 20,
                })
            save(output / "manifest.json", {
                "required_list_ids": list(expected_lists), "captures": captures,
                "synthetic_fixture": True,
            })
        else:
            raw = output / "manifest.json"
            save(raw, {
                "required_list_ids": expected_lists,
                "category_taxonomy_complete": True,
                "synthetic_fixture": True,
            })
        raw_files.append(raw)
    manifest = manifest_sync.sync(run, manifest, registry)
    paths = run["paths"]["files"]
    acquisition_path = Path(paths["acquisition_manifest"])
    save(acquisition_path, manifest)
    coverage = coverage_validator.validate(
        profile, manifest, registry, stage="scan", run_manifest=run
    )
    coverage_path = Path(paths["scan_coverage_report"])
    save(coverage_path, coverage)
    packet_path = Path(paths["evidence_packet"])
    evidence_path = packet_path.parent / "synthetic_evidence.json"
    sample_path = packet_path.parent / "synthetic_sample.json"
    packet_for_story = fixture.packet(lane)
    save(evidence_path, packet_for_story["evidence"])
    save(sample_path, packet_for_story["analysis_sample"])
    return {
        "registry": registry, "profile": profile, "run": run,
        "manifest": manifest, "coverage": coverage,
        "run_root": root, "raw_files": raw_files,
        "paths": paths, "packet_path": packet_path,
        "acquisition_path": acquisition_path, "coverage_path": coverage_path,
        "evidence_path": evidence_path, "sample_path": sample_path,
    }


def freeze_by_cli(state: dict) -> subprocess.CompletedProcess:
    return subprocess.run([
        sys.executable, str(SCRIPTS / "freeze_evidence_packet.py"),
        "--run-manifest", str(state["paths"]["run_manifest"]),
        "--manifest", str(state["acquisition_path"]),
        "--coverage", str(state["coverage_path"]),
        "--evidence", str(state["evidence_path"]),
        "--sample", str(state["sample_path"]),
        "--registry", str(REGISTRY_PATH),
        "--output", str(state["packet_path"]),
    ], capture_output=True, text=True, encoding="utf-8")


class ScanToCandidateHandoffTests(unittest.TestCase):
    def verify_handoff(self, lane: str) -> dict:
        with tempfile.TemporaryDirectory(prefix="webnovel-offline-handoff-") as temp:
            state = prepare_synthetic_run(Path(temp), lane)
            self.assertEqual(
                state["coverage"]["formal_candidate_generation"],
                "allowed", state["coverage"]["failures"]
            )
            self.assertEqual(
                state["coverage"]["artifact_audit"]["artifact_integrity"], "passed"
            )
            outcome = freeze_by_cli(state)
            self.assertEqual(outcome.returncode, 0, outcome.stdout + outcome.stderr)
            packet = json.loads(state["packet_path"].read_text(encoding="utf-8"))
            freezer.validate_packet(packet, lane=lane)
            self.assertEqual(packet["provenance"]["assurance"], "local_content_hash_attestation")
            self.assertEqual(
                packet["provenance"]["input_files"]["manifest"]["sha256"],
                hashlib.sha256(state["acquisition_path"].read_bytes()).hexdigest()
            )

            class FrozenPacketStoryHarness(_candidate_fixture_module.CandidateControllerEndToEndTests):
                def packet(self, selected_lane="short"):
                    if selected_lane != lane:
                        raise AssertionError("handoff lane mismatch")
                    return packet

            platform, channel = ("qimao", "male") if lane == "short" else ("fanqie", "male")
            result = FrozenPacketStoryHarness().run_case(lane, platform, channel)
            self.assertEqual(result["status"], "passed")
            self.assertGreaterEqual(result["usable_candidate_count"], 4)
            self.assertEqual(result["generated_count"], 9)

            # Mutation must invalidate the frozen packet's own hash.
            forged = dict(packet)
            forged["evidence"] = []
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                freezer.validate_packet(forged, lane)

            # Tampering with a previously attested raw file must block source coverage.
            state["raw_files"][0].write_text('{"tampered":true}', encoding="utf-8")
            report = coverage_validator.validate(
                state["profile"], state["manifest"], state["registry"],
                stage="scan", run_manifest=state["run"]
            )
            self.assertEqual(report["formal_candidate_generation"], "blocked")
            self.assertTrue(any(
                issue["reason"] in {"ARTIFACT_HASH_MISMATCH", "ARTIFACT_SIZE_MISMATCH"}
                for issue in report["failures"]
            ))
            return {
                "lane": lane, "coverage": "allowed", "freeze": "passed",
                "candidate_verify": result["status"],
                "usable_candidates": result["usable_candidate_count"],
                "tamper_detection": "passed",
            }

    def test_short_source_to_candidate_handoff(self):
        self.verify_handoff("short")

    def test_long_source_to_candidate_handoff(self):
        self.verify_handoff("long")

    def test_required_ranking_list_missing_blocks_freeze(self):
        with tempfile.TemporaryDirectory(prefix="webnovel-list-blocked-") as temp:
            state = prepare_synthetic_run(Path(temp), "short")
            source_id = "qimao_reader_story_rank_center"
            source_dir = Path(state["run"]["paths"]["source_dirs"][source_id])
            manifest_file = source_dir / "manifest.json"
            payload = json.loads(manifest_file.read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(payload["required_list_ids"]), 2)
            payload["required_list_ids"].pop()
            save(manifest_file, payload)
            updated = manifest_sync.sync(state["run"], state["manifest"], state["registry"])
            report = coverage_validator.validate(
                state["profile"], updated, state["registry"],
                stage="scan", run_manifest=state["run"]
            )
            self.assertEqual(report["formal_candidate_generation"], "blocked")
            self.assertTrue(any(
                issue.get("source_id") == source_id and
                issue["reason"] in {"SOURCE_NOT_SUCCESS", "REQUIRED_LISTS_MISSING"}
                for issue in report["failures"]
            ))
            self.assertFalse(state["packet_path"].exists())

    def test_incomplete_social_content_blocks_freeze(self):
        with tempfile.TemporaryDirectory(prefix="webnovel-blocked-") as temp:
            state = prepare_synthetic_run(Path(temp), "short", social_complete=False)
            self.assertEqual(state["coverage"]["formal_candidate_generation"], "blocked")
            self.assertTrue(any(
                f["reason"] in {"COMPLETE_SIGNAL_ENTRY_SHORTFALL",
                                "SOCIAL_COMPLETE_CONTENT_COUNT_MISMATCH",
                                "SOURCE_NOT_SUCCESS"}
                for f in state["coverage"]["failures"]
            ))
            outcome = freeze_by_cli(state)
            self.assertNotEqual(outcome.returncode, 0)
            self.assertFalse(state["packet_path"].exists())


if __name__ == "__main__":
    unittest.main()
