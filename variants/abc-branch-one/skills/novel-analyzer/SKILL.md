---
name: novel-analyzer
description: Compatibility router for Chinese web-fiction market analysis and candidate requests. Use when a request names novel-analyzer, combines market scanning with candidate generation, or is ambiguous between those workflows. Route collection to novel-market-scan and sealed-packet candidate work to novel-candidate-portfolio.
---

# Novel Analyzer Router

Route work; do not duplicate either production workflow.

- Market ranks, demand evidence, source coverage, refresh, or freezing: load `novel-market-scan`.
- Candidates from an existing sealed evidence packet: load `novel-candidate-portfolio`.
- End to end: finish `novel-market-scan`, then pass only its sealed packet path and hash to `novel-candidate-portfolio`.
- Story drafting or continuation: do not invoke candidate generation unless the user explicitly requests new candidate selection.

The scripts in this directory are shared deterministic engines. The model-facing candidate entry is `novel-candidate-portfolio/scripts/candidate.py`; do not call internal portfolio functions to bypass its controller.

For a candidate run, report only controller-defined paths, status, verification result, and the four count fields. Never count directories or artifacts as candidates, and never repair an accepted run by hand-editing JSON.
