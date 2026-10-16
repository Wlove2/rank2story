"""S3 model review only receives evidence IDs actually cited by candidates.

The full evidence packet is still validated and remains available to the
deterministic review gate. This test is synthetic and never calls a live model.
"""
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCRIPTS=ROOT/"variants/abc-branch-one/skills/novel-analyzer/scripts"


class CitedEvidenceSliceTests(unittest.TestCase):
    def test_review_input_drops_unreferenced_registry_not_validation(self):
        code=r"""
from pathlib import Path
from unittest.mock import patch
import tempfile,json,sys
sys.path.insert(0,sys.argv[1])
import candidate_workflow as w
import candidate_portfolio as p
refs={
  "e1":{"evidence_id":"e1","source_id":"s1","url":"https://test.example/1","platform":"sample"},
  "e2":{"evidence_id":"e2","source_id":"s2","url":"https://test.example/2"},
  "e3":{"evidence_id":"e3","source_id":"s3","url":"https://test.example/3"},
}
registered_ids=set(refs)|{f"uncited{i}" for i in range(120)}
registered_urls={x["url"] for x in refs.values()}|{f"https://test.example/other{i}" for i in range(120)}
full_packet={"mock":True}
atoms={"atoms":[
  {"atom_id":"a1","evidence_id":"e1",
   "supporting_evidence_ids":["e2"],"counter_evidence_ids":["e3"]},
  {"atom_id":"a2","evidence_id":"uncited0"}
]}
clustered={"representative_ids":["A-C01"],"representatives":[
  {"candidate_id":"A-C01","cited_atom_ids":["a1"]}]}
with tempfile.TemporaryDirectory() as tmp, \
     patch.object(p,"validate_packet",return_value="signed_full_packet"), \
     patch.object(p,"evidence_reference_registry",return_value={"evidence_ids":registered_ids,"urls":registered_urls}), \
     patch.object(p,"evidence_index",return_value=refs):
  result=w.build_review_evidence_slice(full_packet,atoms,clustered,"short",Path(tmp))
  payload=json.loads(result.read_text(encoding="utf-8"))
  assert payload["reference_scope"]=="candidate_cited_evidence_only"
  assert payload["evidence_ids"]==["e1","e2","e3"]
  assert set(payload["registered_urls"])=={x["url"] for x in refs.values()}
  assert set(payload["referenced_evidence"])==set(payload["evidence_ids"])
  assert len(payload["cited_atoms"])==1
  assert payload["evidence_packet_hash"]=="signed_full_packet"
  assert p.verify_seal(payload)
"""
        proc=subprocess.run([sys.executable,"-c",code,str(SCRIPTS.resolve())],capture_output=True,
                            text=True,encoding="utf-8",timeout=20)
        self.assertEqual(proc.returncode,0,proc.stdout+"\n"+proc.stderr)


if __name__=="__main__":
    unittest.main()
