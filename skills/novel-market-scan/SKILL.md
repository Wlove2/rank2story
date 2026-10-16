---
name: novel-market-scan
description: Auditable web-fiction market scanning, source coverage, normalization and frozen evidence packets. Do not generate candidate stories.
---

# Novel Market Scan

Build a verified scan run from registered sources. Stop at a sealed evidence packet; the candidate pipeline is a separate skill.

## Profiles and paths

- Short lane: `short_production`.
- Long lane: `comprehensive_long_production` (not `long_production`).
- Default output root: `./data/scans` relative to the working directory; override with the `NOVEL_SCAN_ROOT` environment variable.
- Scan runs are placed under a date partition with a unique run ID. Always use manifest paths as authoritative.

## Workflow

1. Start a run using `scripts/start.py --profile short_production` or `scripts/start.py --profile comprehensive_long_production`.
2. Check the run's source registry, requirements and preflight. Some collectors require external tools or authorized browser access.
3. Collect into the current run's registered source directories only. Record source URL, retrieval time, byte count and SHA-256 where applicable.
4. Sync acquisition manifest; normalize evidence for that run; validate source coverage and artifact integrity. If the user explicitly requests a recent social-evidence window and supplies its length, pass `--max-social-age-days N` when initializing the scan. The UTC as-of date is frozen in the run manifest and rechecked at coverage and freeze; the default has no social-age cap.
5. Freeze the evidence packet with deterministic paths and hashes. Only report success after validator exit status 0.
6. Return the packet path, hash, run ID, lane, coverage status and any failed sources. Do not invoke the candidate engine without a user instruction.

## External collection access

Supported platform adapters can require browser automation, `opencli`, `agent-reach`, or external collector scripts. No signed URL, login account, cookie, browser profile or scraped content is provided by this repository. Verify your access permissions and platform terms before running. Do not evade access controls, harvest credentials or publish private records.

## Reproducibility and hard stops

- Do not reuse last run's ranks **as current data**. A dated, verified packet may be reused for another candidate run when its coverage/lane remain valid and the user accepts its original collection date. Never silently refresh the recorded timestamp.
- Do not invent sources, bypass coverage gates or claim successful collection based solely on partial output. Never claim that other lists are sufficient.
- Treat obsolete platform selectors, blocked access and missing collectors as explicit failures/degraded sources.
- Do not publish original source snapshots, social posts or full novel text as test fixtures.

Tests and shared engines are in the sibling `novel-analyzer` skill. Verified historical scanning results and their limitations are described in the project-root `docs/RESULTS.md` and `PROVENANCE.md`.