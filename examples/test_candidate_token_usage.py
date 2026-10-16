"""Ensure the publicly reported token usage is arithmetically consistent and private-data-free."""
from pathlib import Path
import json
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]
USAGE=ROOT/"examples/showcase/candidate_token_usage_20260905.json"

class CandidateUsageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text=USAGE.read_text(encoding="utf-8")
        cls.data=json.loads(cls.text)

    def test_exact_archived_counts_and_stage_consistency(self):
        d=self.data
        self.assertEqual(d["model_reported"],"not_disclosed")
        self.assertEqual((d["generation_count"],d["selected_count"]),(9,5))
        self.assertEqual(d["source_call_count"],36)
        t=d["totals"]
        self.assertEqual((t["calls"],t["prompt_tokens"],t["completion_tokens"],t["total_tokens"]),(36,332861,104823,437684))
        self.assertEqual(t["prompt_tokens"]+t["completion_tokens"],t["total_tokens"])
        self.assertEqual(len(d["stages"]),7)
        for key in ("calls","prompt_tokens","completion_tokens","total_tokens"):
            self.assertEqual(sum(x[key] for x in d["stages"]),t[key])
        self.assertEqual(sum(x["total_tokens"] for x in d["stages"] if x["stage"] in ("evidence_atoms","market_review","originality_review")),228326)

    def test_public_usage_contains_no_private_artifacts(self):
        raw=self.text
        for key in ('"raw_response"','"request"','"messages"','"prompt_text"','"api_key"','"token_ids"'):
            self.assertNotIn(key,raw)
        self.assertNotRegex(raw,r"(?i)(?<![a-z])(?:[a-z]:[\\/]|/(?:users|home)/)")
        self.assertNotRegex(raw,r"(?i)(?:sk-[a-z0-9_-]{24,}|ghp_[a-z0-9]{30,})")
        self.assertNotRegex(raw,r"(?i)[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}")

    def test_description_is_linked_and_qualifies_scope(self):
        summary=(ROOT/"docs/CANDIDATE_MODEL_AND_TOKENS.md").read_text(encoding="utf-8")
        readme=(ROOT/"README.md").read_text(encoding="utf-8")
        self.assertIn("437,684",summary)
        self.assertIn("332,861",summary)
        self.assertIn("104,823",summary)
        self.assertIn("36",readme)
        self.assertIn("docs/CANDIDATE_MODEL_AND_TOKENS.md",readme)
        self.assertIn("candidate_token_usage_20260905.json",summary)
        self.assertIn("A-C02",summary)
        self.assertTrue((ROOT/"docs/CANDIDATE_MODEL_AND_TOKENS.md").exists())

if __name__=="__main__":
    unittest.main()
