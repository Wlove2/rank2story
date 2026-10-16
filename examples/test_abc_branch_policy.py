"""Portable integrity and behavioral-entry checks for the opt-in A/B/C workflow."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
VARIANT=ROOT/"variants"/"abc-branch-one"
SCRIPTS=VARIANT/"skills"/"novel-analyzer"/"scripts"

class AbcVersionedPolicyTests(unittest.TestCase):
    def test_manifest_attests_all_versioned_files(self):
        manifest=json.loads((VARIANT/"V442_POLICY_MANIFEST.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"],"4.4.2-input-efficiency")
        hashes=manifest["source_hashes"]
        self.assertEqual(len(hashes),10)
        for rel,expect in hashes.items():
            with self.subTest(rel=rel):
                self.assertEqual(hashlib.sha256((VARIANT/rel).read_bytes()).hexdigest(),expect)

    def test_unmodified_production_core_hashes_are_verified(self):
        manifest=json.loads((ROOT/"source-manifest.json").read_text(encoding="utf-8"))
        index={v["file"]:v for v in manifest["files"]}
        for name in ("candidate_workflow.py","candidate_portfolio.py"):
            rel="skills/novel-analyzer/scripts/"+name
            with self.subTest(core=rel):
                row=index[rel]
                self.assertFalse(row["changed"])
                self.assertEqual(row["baseline_sha256"],row["release_sha256"])
                self.assertEqual(hashlib.sha256((ROOT/rel).read_bytes()).hexdigest(),row["baseline_sha256"])
        adapted="skills/novel-analyzer/scripts/candidate_executor.py"
        self.assertTrue(index[adapted]["changed"])
        self.assertNotEqual(index[adapted]["baseline_sha256"],index[adapted]["release_sha256"])
        self.assertEqual(hashlib.sha256((ROOT/adapted).read_bytes()).hexdigest(),index[adapted]["release_sha256"])
        rel="skills/novel-candidate-portfolio/scripts/candidate.py"
        self.assertFalse(index[rel]["changed"])
        self.assertEqual(hashlib.sha256((ROOT/rel).read_bytes()).hexdigest(),index[rel]["baseline_sha256"])

    def test_variant_executes_actual_policy_objects(self):
        script=r"""
import json,sys,inspect
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import candidate_workflow as w
import candidate_portfolio as p
assemble=inspect.getsource(p.assemble_portfolio)
source=inspect.getsource(w.schedule_cluster_diversity_recovery)
print(json.dumps({
  "initial":w.EXECUTION_PROFILES["production"]["kernels_per_branch"],
  "limit":w.MAX_KERNEL_SUPPLEMENT_ROUNDS,
  "branches":sorted(p.BRANCH_ROLES),
  "post_story_minimum_is_one":"post_story_minimum = 1" in inspect.getsource(w.advance_story_pipeline),
  "explicit_final_abc":"FINAL_BRANCH_COVERAGE_INSUFFICIENT" in assemble,
  "bounded_structural_recovery":"BRANCH_REPRESENTATIVE_DIVERSITY_INSUFFICIENT" in source and "schedule_kernel_supplement" in source,
  "reviewer_veto_never_overridden":"'reviewer_veto_overridden': False" in source or '"reviewer_veto_overridden": False' in source,
  "portfolio_module":str(Path(p.__file__).resolve())
},ensure_ascii=False))
"""
        ran=subprocess.run([sys.executable,"-c",script,str(SCRIPTS.resolve())],capture_output=True,text=True,timeout=20)
        self.assertEqual(ran.returncode,0,ran.stderr)
        policy=json.loads(ran.stdout.strip())
        self.assertEqual(policy["initial"],3)
        self.assertEqual(policy["limit"],3)
        self.assertEqual(policy["branches"],["A","B","C"])
        self.assertTrue(policy["post_story_minimum_is_one"])
        self.assertTrue(policy["explicit_final_abc"])
        self.assertTrue(policy["bounded_structural_recovery"])
        self.assertTrue(policy["reviewer_veto_never_overridden"])
        self.assertTrue(policy["portfolio_module"].replace("\\","/").endswith("variants/abc-branch-one/skills/novel-analyzer/scripts/candidate_portfolio.py"))

    def test_versioned_entry_cli_is_available(self):
        cli=VARIANT/"skills"/"novel-candidate-portfolio"/"scripts"/"candidate.py"
        ran=subprocess.run([sys.executable,str(cli),"--help"],capture_output=True,text=True,timeout=20)
        self.assertEqual(ran.returncode,0,ran.stderr)
        self.assertIn("run",ran.stdout)
        self.assertIn("verify",ran.stdout)

if __name__=="__main__":
    unittest.main()
