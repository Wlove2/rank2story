"""Offline installation diagnostic tests."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("installation_diagnostic", ROOT / "examples" / "check_installation.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class InstallReadinessTests(unittest.TestCase):
    def test_skill_and_live_scan_status_are_separate(self):
        state = module.check_environment()
        self.assertEqual(set(state["skills"]), {"novel-analyzer", "novel-market-scan", "novel-candidate-portfolio"})
        self.assertTrue(all(state["skills"].values()))
        self.assertEqual(state["agent_skill_registration"], "not_checked_by_this_script")
        self.assertIsInstance(state["next_steps"], list)
        self.assertFalse(state["live_scan_verified"])
        self.assertFalse(state["authenticated_site_access_verified"])
        self.assertIsInstance(state["long_scan_os_supported"], bool)
        self.assertFalse(state["browser"]["launch_tested"])


if __name__ == "__main__":
    unittest.main()
