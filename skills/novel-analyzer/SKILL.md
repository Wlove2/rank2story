---
name: novel-analyzer
description: Compatibility router for Chinese web-fiction market analysis and candidate requests. Use when a request names novel-analyzer, combines market scanning with candidate generation, or is ambiguous between those workflows. Route collection to novel-market-scan and sealed-packet candidate work to novel-candidate-portfolio.
---

# Novel Analyzer Router

Route work; do not duplicate either production workflow.

- Market ranks, demand evidence, source coverage, refresh, or freezing: load `novel-market-scan`.
- Candidates from an existing sealed evidence packet: load `novel-candidate-portfolio`.
- End to end: first check whether an existing, dated, verified evidence packet matches the requested lane and coverage. If so and the user accepts its age, reuse it; otherwise run `novel-market-scan` and validate a new packet. Pass only the selected packet path and hash to `novel-candidate-portfolio`.
- Story drafting or continuation: do not invoke candidate generation unless the user explicitly requests new candidate selection.

The scripts in this directory are shared engines. **With the full repository installed**, use the root `scripts/candidate.py` entry; the default is A/B/C 4.4.2, and `--policy quality_strict` selects the alternative candidate-survival policy for new tasks. All claim operations use their frozen controller snapshot. Standalone Skill-folder installs may use `novel-candidate-portfolio/scripts/candidate.py` independently, but cannot load a root policy config that is not installed.

For a candidate run, report only controller-defined paths, status, verification result, and the four count fields. Never count directories or artifacts as candidates, and never repair an accepted run by hand-editing JSON.
