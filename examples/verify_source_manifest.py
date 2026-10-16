"""Verify every published Skill file byte-for-byte against the release manifest."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "source-manifest.json").read_text(encoding="utf-8"))
LOCKED_PRODUCTION = {
    "skills/novel-analyzer/scripts/candidate_workflow.py": "671ba37470355d41bd9e00c3cfa223b09ef5e26c46be842a2318983e8497466a",
    "skills/novel-analyzer/scripts/candidate_portfolio.py": "89f700dd5142760466e4529bc3f4e45a7b869ac8241644ffe04ad2b860a32047",
    "skills/novel-candidate-portfolio/scripts/candidate.py": "e100bb7477ab105177281a45e739174c1689a354c1e54d01dd3f7d13edc85378",
}
def main():
    failures = []
    names = set()
    for item in MANIFEST["files"]:
        name = item["file"]
        if name in names or not name.startswith("skills/"):
            failures.append(f"invalid or duplicate manifest path: {name}")
            continue
        names.add(name)
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():
            failures.append(f"missing or invalid: {name}")
            continue
        found = hashlib.sha256(path.read_bytes()).hexdigest()
        if found != item["release_sha256"]:
            failures.append(f"release content mismatch: {name}")
        if name in LOCKED_PRODUCTION:
            expected = LOCKED_PRODUCTION[name]
            if item["baseline_sha256"] != expected or found != expected:
                failures.append(f"locked 2026-09-05 core version mismatch: {name}")
    for name in LOCKED_PRODUCTION:
        if name not in names:
            failures.append(f"locked core missing: {name}")
    print(f"Manifest: {len(MANIFEST['files'])} Skill files; verified={len(MANIFEST['files'])-len(failures)}; failures={len(failures)}")
    for msg in failures:
        print("FAIL", msg)
    if failures:
        raise SystemExit(1)
    print("PASS: release hashes and three unchanged production core hashes match")

if __name__ == "__main__":
    main()
