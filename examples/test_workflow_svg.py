"""Regression guard for readable Chinese text in the wide README workflow diagram."""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SVG = ROOT / "assets" / "workflow.svg"
README = ROOT / "README.md"

class WorkflowSVGTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=SVG.read_text(encoding="utf-8")
        cls.root=ET.fromstring(cls.source)
        cls.labels=[e.text or "" for e in cls.root.iter() if e.tag.endswith("text")]

    def test_utf8_xml_text_and_large_layout(self):
        self.assertGreaterEqual(sum(0x4E00<=ord(c)<=0x9FFF for c in self.source),180)
        self.assertNotIn("?",self.source,"Broken console encoding")
        self.assertEqual(self.root.get("viewBox"),"0 0 1570 680")
        self.assertGreaterEqual(len(self.labels),23)

    def test_three_spacious_product_stages(self):
        for label in ("观察市场","探索故事","筛选好故事",
                      "七个平台","榜单与社区","A 路线","B 路线","C 路线",
                      "独立审查","候选组合"):
            self.assertIn(label,self.labels)

    def test_readme_embeds_vector_graphic(self):
        s=README.read_text(encoding="utf-8")
        self.assertIn("](assets/workflow.svg)",s)
        self.assertNotIn(chr(96)*3+"mermaid",s)

if __name__=="__main__":
    unittest.main()
