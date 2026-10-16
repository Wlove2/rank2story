# Social evidence extraction: registered workflow reference

This reference accompanies the Xiaohongshu and Bilibili `registered_workflow` entries in [source-registry.json](source-registry.json).

- The **current per-platform quotas and completeness gates** are documented in [social-source-policy.md](social-source-policy.md); the registry remains authoritative.
- Bundled collectors: `scripts/collect_xiaohongshu_public_notes.py` and `scripts/collect_bilibili_public_videos.py` (paths relative to `novel-analyzer`). Both depend on authorized external browser access.
- Normalize evidence with `scripts/normalize_current_run_sources.py` and validate coverage with `scripts/validate_source_coverage.py` before freezing an evidence packet.

A working OpenCLI/Agent Reach installation alone is not proof of complete note images, video transcripts or sufficient source coverage. Do not mark partial or inaccessible records as eligible.
