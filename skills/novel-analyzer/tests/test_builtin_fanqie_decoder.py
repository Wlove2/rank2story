"""Release-only decoder provenance, fallback and failure-closed tests."""
from __future__ import annotations
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import fanqie_decoder
import fanqie_refresh
import scan_preflight


class BuiltInFanqieDecoderTests(unittest.TestCase):
    def test_unambiguous_unicode_stays_identical(self):
        for source in ("现代汉语《样本》：在读 12.3万", "Example text", "", None, "abc-123"):
            actual = fanqie_decoder.decode_text(source)
            self.assertEqual(actual, str(source or ""))

    def test_rejects_unknown_private_font_glyphs(self):
        for custom in ("书名\ue201", "\U000F0012 title", "\U00100012", "损坏\ufffd"):
            with self.assertRaisesRegex(ValueError, "Undecoded custom-font character"):
                fanqie_decoder.decode_text(custom)

    def test_runner_default_is_our_own_decoder(self):
        with patch.dict(os.environ, {"NOVEL_FANQIE_COLLECTOR": ""}):
            path = fanqie_refresh.resolve_optional_collector(None)
        self.assertEqual(path, ROOT / "scripts" / "fanqie_decoder.py")
        self.assertIsInstance(fanqie_refresh.load_decoder(path)("示例"), str)

    def test_clear_ranking_records_decode_without_external_code(self):
        raw = [{
            "title": "样本小说",
            "author": "示例作者",
            "reads": "12.3万在读",
            "intro": "独立合成数据",
            "url": "/page/synthetic"
        }]
        books = fanqie_refresh.normalize_books(raw, fanqie_decoder.decode_text, 10)
        self.assertEqual(len(books), 1)
        self.assertEqual(books[0]["title"], "样本小说")
        self.assertIn("synthetic", books[0]["url"])

    def test_unknown_custom_font_blocks_normalization(self):
        raw = [{"title": "未知\ue123", "author": "作者", "reads": "1万在读"}]
        with self.assertRaises(ValueError):
            fanqie_refresh.normalize_books(raw, fanqie_decoder.decode_text, 10)

    def test_registry_has_no_unlicensed_runtime_file_dependency(self):
        registry = json.loads((ROOT / "references" / "source-registry.json").read_text(encoding="utf-8"))
        contract = registry["runtime_contract"]
        self.assertEqual(contract["file_dependencies"], [])
        self.assertEqual(contract["built_in_fanqie_decoder"], "scripts/fanqie_decoder.py")

    def test_preflight_uses_bundled_decoder_without_external_install(self):
        registry = json.loads((ROOT / "references" / "source-registry.json").read_text(encoding="utf-8"))
        browser = {"available": True, "chromium_exists": True, "browser_launch_ok": None}
        with patch.dict(os.environ, {"NOVEL_FANQIE_COLLECTOR": ""}):
            with patch.object(scan_preflight, "check_playwright", return_value=browser):
                result = scan_preflight.run_preflight(
                    "short_production", registry, skip_network=True,
                    command_finder=lambda name: "/tool/" + name,
                )
        self.assertEqual(result["checks"]["fanqie_decoder"]["kind"], "bundled_conservative")
        self.assertEqual(result["status"], "ready", result["failures"])

    def test_operator_override_missing_must_block(self):
        registry = json.loads((ROOT / "references" / "source-registry.json").read_text(encoding="utf-8"))
        browser = {"available": True, "chromium_exists": True, "browser_launch_ok": None}
        with tempfile.TemporaryDirectory() as tmp:
            missing = str(Path(tmp) / "does-not-exist.py")
            with patch.dict(os.environ, {"NOVEL_FANQIE_COLLECTOR": missing}):
                with patch.object(scan_preflight, "check_playwright", return_value=browser):
                    result = scan_preflight.run_preflight(
                        "short_production", registry, skip_network=True,
                        command_finder=lambda name: "/tool/" + name,
                    )
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(any(x["reason"] == "FANQIE_DECODER_MISSING" for x in result["failures"]))


if __name__ == "__main__":
    unittest.main()
