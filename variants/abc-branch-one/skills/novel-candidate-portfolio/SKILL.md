---
name: novel-candidate-portfolio
description: Verified story-first, evidence-bound A/B/C candidate portfolio generation with dual review and Pareto selection.
---

# Novel Candidate Portfolio 4.4.2 (repository-default A/B/C policy)

**Version discriminator:** the repository-level `scripts/candidate.py` uses this versioned V4.4.2 A/B/C controller for new runs by default (`abc_branch_one`). The optional `quality_strict` strategy uses the separate historical controller. All existing claims continue with their own frozen code snapshots, independently of current default policy. `variants/abc-branch-one/V442_POLICY_MANIFEST.json` records variant file hashes; the root `source-manifest.json` records the published `skills/` files.

## Inputs

Sealed evidence packet, lane (`short`/`long`), platform (`fanqie`/`qimao`), channel (`male`/`female`), writable base root, and operator-supplied inference endpoint/model.

## CLI

From this skill directory:

```bash
python scripts/candidate.py run --base-root ../../data/runs --packet <packet.json> --lane short --platform qimao --channel male
python scripts/candidate.py execute --claim <claim.json> --base-url <your-llm-url> --model <your-model-id> --max-tokens 48000
python scripts/candidate.py status --claim <claim.json>
python scripts/candidate.py resume --claim <claim.json>
python scripts/candidate.py verify --claim <claim.json>
```

## Contract

- S1: generate source-traced evidence atoms.
- S2: A/B/C isolated kernel tracks, then story creator, story editor and candidate mapper.
- S3: independent market coverage and originality reviews. Channel verdicts must be validated, never silently repaired into a pass.
- S4: clustering, independent vetoes, Pareto selection, then verify.
- Deliver only when controller reports `status=passed`. Never infer counts by reading directories.
- Production still expects 3 initial kernels per branch (smoke 2). After S2 story/editor vetoes, each branch needs only 1 mapped survivor; final delivery requires independently reviewed A, B, C with at least 1 qualified card each, at least 3 distinct mechanisms, and 3–6 cards. Cross-branch dedup and reviewer vetoes remain strict. Per-branch kernel supplementation is capped at 3, and all repair actions share the original 128-call recovery budget, warning at 400 calls, fuse at 512 calls. A rejected batch is a legitimate business outcome, not automatically a software crash.
- Stop at `awaiting_user_choice`; fiction drafting is another downstream workflow.

## Recovery

Use the controller's `status`, `resume` and `verify` on the same frozen claim. Do not manually edit accepted stage JSON, substitute old evidence, fabricate source IDs or bypass schema and channel checks. See `references/operations.md`.

## Credentials and copyright

Provide your own inference server and API key environment variable if needed. Neither login sessions nor raw website content is bundled; ensure collection is authorized and complies with site terms.