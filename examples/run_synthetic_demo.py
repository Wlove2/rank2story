"""Offline deterministic story-first demo; no model service or live web data."""
from __future__ import annotations
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "novel-analyzer" / "scripts"
FIXTURE = ROOT / "skills" / "novel-analyzer" / "tests" / "test_candidate_controller_e2e.py"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("_synthetic_e2e", FIXTURE)
if spec is None or spec.loader is None:
    raise RuntimeError("Synthetic fixture is unavailable")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

def main():
    result = module.CandidateControllerEndToEndTests().run_case("short", "qimao", "male")
    keys = ("status", "candidate_count", "generated_count", "passed_review_count",
            "selected_for_delivery_count", "usable_candidate_count", "failures")
    view = {key: result.get(key) for key in keys}
    print(json.dumps(view, ensure_ascii=False, indent=2))
    if view["status"] != "passed" or view["usable_candidate_count"] < 3:
        raise SystemExit("Synthetic run failed verification")
    print("PASS: synthetic evidence -> story-first A/B/C -> S3 reviews -> Pareto -> verify")

if __name__ == "__main__":
    main()
