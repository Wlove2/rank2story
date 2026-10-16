"""Guard current release docs against regressions in attribution and data privacy."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PublicationMetadataTests(unittest.TestCase):
    def test_readme_is_chinese_first_and_not_mixed_with_tail_translation(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("第三方许可", readme)
        self.assertIn("数据与隐私", readme)
        self.assertNotIn("**English:**", readme)
        self.assertNotIn("## English", readme)

    def test_external_reference_is_attributed_without_asserting_bundled_license(self):
        third = (ROOT / "THIRD_PARTY.md").read_text(encoding="utf-8")
        self.assertIn("https://github.com/wen1701/FanqieRankTracker", third)
        self.assertIn("README", third)
        self.assertIn("LICENSE", third)
        self.assertIn("未打包", third)
        self.assertIn("独立", third)

    def test_disclosure_and_rights_docs_are_linked(self):
        for filename in ("README.md", "SECURITY.md", "THIRD_PARTY.md", "docs/CONNECTORS.md"):
            path = ROOT / filename
            source = path.read_text(encoding="utf-8")
            for url in re.findall(r"\[[^\]\n]+\]\(([^)]+)\)", source):
                if url.startswith(("https://", "http://", "#")):
                    continue
                target = path.parent / url.split("#")[0]
                self.assertTrue(target.exists(), f"Invalid link {filename} -> {url}")
        self.assertIn("THIRD_PARTY.md", (ROOT / "README.md").read_text(encoding="utf-8"))

    def test_public_documentation_is_account_neutral_and_actionable(self):
        for name in ("README.md","docs/QUICKSTART.md","docs/POLICY_CONFIGURATION.md","PROVENANCE.md","scripts/candidate.py"):
            contents=(ROOT/name).read_text(encoding="utf-8").lower()
            self.assertNotRegex(contents, r"(?i)(?<![a-z])(?:[a-z]:[\\/]|/(?:users|home)/)")
            self.assertNotRegex(contents, r"(?i)[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}")
            self.assertNotRegex(contents, r"(?i)(?:sk-[a-z0-9_-]{24,}|ghp_[a-z0-9]{30,})")
        readme=(ROOT/"README.md").read_text(encoding="utf-8")
        self.assertIn("## License",readme)
        self.assertIn("[查看完整许可证](LICENSE)",readme)
        guide=(ROOT/"docs/QUICKSTART.md").read_text(encoding="utf-8")
        for word in ("MODEL_API_KEY","--api-key-env","run --base-root","execute --claim","verify --claim"):
            self.assertIn(word,guide)

    def test_agent_one_link_onboarding_and_market_packet_reuse(self):
        import re
        readme=(ROOT/"README.md").read_text(encoding="utf-8")
        install=(ROOT/"docs/INSTALL_FOR_AGENTS.md").read_text(encoding="utf-8")
        agent=(ROOT/"docs/AGENT_INTEGRATION.md").read_text(encoding="utf-8")
        quick=(ROOT/"docs/QUICKSTART.md").read_text(encoding="utf-8")
        self.assertIn("INSTALL_FOR_AGENTS.md",readme)
        self.assertIn("INSTALL_FOR_AGENTS.md",quick)
        for name in ("novel-market-scan","novel-candidate-portfolio","novel-analyzer"):
            self.assertIn(name,install)
        for marker in ("长篇","短篇","番茄","七猫","男频","女频","市场证据包"):
            self.assertIn(marker,agent)
        for marker in ("--packet","独立","证据包"):
            self.assertIn(marker,install)
        self.assertIn("MODEL_API_KEY",quick)
        self.assertIn("--api-key-env",quick)
        self.assertNotIn("为我研究目前可合法访问的男频长篇市场信号",agent)
        self.assertIn("https://raw.githubusercontent.com/Wlove2/rank2story/main/docs/INSTALL_FOR_AGENTS.md",readme)
        self.assertTrue((ROOT/"docs/INSTALL_FOR_AGENTS.md").is_file())
        for link in re.findall(r"\[[^\]]+\]\(([^)]+)\)",readme):
            if link.startswith(("https://","http://","#")): continue
            self.assertTrue((ROOT/link.split("#")[0]).exists(),link)

    def test_public_readme_stays_product_focused(self):
        readme=(ROOT/"README.md").read_text(encoding="utf-8")
        quick=(ROOT/"docs/QUICKSTART.md").read_text(encoding="utf-8")
        integration=(ROOT/"docs/AGENT_INTEGRATION.md").read_text(encoding="utf-8")
        self.assertIn("## 快速开始｜通过 Agent 安装与使用",readme)
        self.assertIn("## 市场数据来源与候选定位",readme)
        self.assertIn("| 篇幅 | 长篇 / 短篇 |",readme)
        self.assertIn("| 目标平台 | 番茄 / 七猫 |",readme)
        self.assertIn("| 受众频道 | 男频 / 女频 |",readme)
        for doc in (readme,quick,integration):
            for phrase in ("仓库仍为 Private","当仓库处于 Private","用户截图","如果你的 Agent","不用学终端命令"):
                self.assertNotIn(phrase,doc)
        self.assertNotIn("[自动化测试](.github/workflows/tests.yml)",readme)
        self.assertIn("## License",readme)

    def test_social_quotas_and_registered_references_are_consistent(self):
        registry=json.loads((ROOT/"skills/novel-analyzer/references/source-registry.json").read_text(encoding="utf-8"))
        sources={entry["id"]:entry for entry in registry["sources"]}
        x=sources["xiaohongshu_novel_demand_shared"]
        b=sources["bilibili_novel_demand_shared"]
        policy=(ROOT/"skills/novel-analyzer/references/social-source-policy.md").read_text(encoding="utf-8")
        for source in (x,b):
            ref=source["collection_contract"]["reference"]
            self.assertTrue((ROOT/"skills/novel-analyzer"/ref).is_file(),ref)
        rows={line.split("|")[1].strip():[cell.strip() for cell in line.split("|")[2:4]]
              for line in policy.splitlines() if line.startswith("| ") and line.count("|")>=4}
        for label,key in (
            ("Distinct discovered canonical URLs","min_discovered_unique_entries"),
            ("Entries screened","min_screened_entries"),
            ("Complete signal-eligible entries","min_signal_eligible_entries"),
            ("Unique publishing accounts","min_unique_accounts"),
            ("Entries from any one account (maximum)","max_signal_entries_per_account"),
        ):
            self.assertEqual(rows[label],[str(x["coverage"][key]),str(b["coverage"][key])],label)
        for label,signal in (
            ("Current hotspot or ranking discussion","current_hotspot_or_rank_scan"),
            ("Curator roundup","curator_roundup"),
            ("Reader demand / book shortage","reader_demand_or_book_shortage"),
            ("Negative or avoidance feedback","negative_or_avoidance"),
        ):
            self.assertEqual(rows[label],[str(source["coverage"]["required_primary_signal_type_counts"].get(signal,"—"))
                                          for source in (x,b)],label)

    def test_showcase_metadata_contains_no_authentication_material(self):
        showcase = ROOT / "examples" / "showcase"
        self.assertTrue(showcase.is_dir())
        for item in showcase.glob("*.json"):
            raw = item.read_text(encoding="utf-8")
            json.loads(raw)
            for key in ('"cookie"', '"access_token"', '"authorization"', '"private_key"', '"signed_url"', '"subtitle_segments"'):
                self.assertNotIn(key, raw.lower(), f"{item.name}: {key}")
            self.assertNotRegex(raw, r"(?i)(?:sk-[A-Za-z0-9_-]{24,}|ghp_[A-Za-z0-9]{30,})")


if __name__ == "__main__":
    unittest.main()
