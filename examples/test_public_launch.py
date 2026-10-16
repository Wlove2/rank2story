"""Public README, link, attribution and repository naming smoke tests."""
from __future__ import annotations
import re
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class PublicLaunchTests(unittest.TestCase):
    def test_readme_clones_the_correct_repository(self):
        s=(ROOT/"README.md").read_text(encoding="utf-8")
        self.assertTrue(s.startswith("# Rank2Story\n"))
        self.assertIn("https://github.com/Wlove2/rank2story.git",s)
        self.assertIn("cd rank2story",s)
        self.assertNotIn("[自动化测试](.github/workflows/tests.yml)",s)
        self.assertIn("docs/INSTALL_FOR_AGENTS.md",s)
        clone_urls=re.findall(r"(?m)^git clone\s+(\S+)\s*$",s)
        self.assertEqual(clone_urls,["https://github.com/Wlove2/rank2story.git"])
        self.assertIn("[参与贡献](CONTRIBUTING.md)",s)

    def test_relative_markdown_links_resolve_locally(self):
        paths=[ROOT/"README.md",ROOT/"CONTRIBUTING.md",ROOT/"THIRD_PARTY.md",ROOT/"SECURITY.md",
               ROOT/"docs/RESULTS.md",ROOT/"docs/QUICKSTART.md"]
        for p in paths:
            s=p.read_text(encoding="utf-8")
            for url in re.findall(r"\[[^\]\n]+\]\(([^)]+)\)",s):
                if url.startswith(("https://","http://","#")):
                    continue
                rel=url.split("#")[0]
                self.assertTrue((p.parent/rel).exists(),f"{p.name}: {url}")

    def test_brand_and_provenance_are_consistent(self):
        p=(ROOT/"pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('name = "rank2story"',p)
        self.assertTrue((ROOT/"LICENSE").exists())
        self.assertIn("wen1701/FanqieRankTracker",(ROOT/"THIRD_PARTY.md").read_text(encoding="utf-8"))
        graph=(ROOT/"assets/workflow.svg").read_text(encoding="utf-8")
        self.assertIn("Rank2Story",graph)
        self.assertGreater(sum(0x4e00<=ord(c)<=0x9fff for c in graph),160)
        self.assertNotIn("?",graph)

    def test_community_templates_are_present(self):
        for rel in ("CONTRIBUTING.md",".github/ISSUE_TEMPLATE/bug_report.yml",
                    ".github/ISSUE_TEMPLATE/feature_request.yml",".github/pull_request_template.md"):
            self.assertTrue((ROOT/rel).is_file(),rel)

    def test_only_selected_candidates_are_promoted_publicly(self):
        readme=(ROOT/"README.md").read_text(encoding="utf-8")
        detail=(ROOT/"docs/CANDIDATE_SHOWCASE_20260905.md").read_text(encoding="utf-8")
        for cid in ("B-C03", "C-C02"):
            self.assertIn(cid,readme)
        self.assertNotIn(chr(21478)+chr(22806)+chr(22235)+chr(20010),readme)
        self.assertNotIn("## "+chr(21478)+chr(22806)+chr(22235)+chr(20010),detail)
        self.assertFalse((ROOT/"examples/showcase/additional_draft_candidates_20260905.json").exists())
        self.assertIn("A-C02",detail)

if __name__=="__main__":
    unittest.main()
