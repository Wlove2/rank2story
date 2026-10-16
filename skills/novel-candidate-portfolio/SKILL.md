---
name: novel-candidate-portfolio
description: Verified story-first, evidence-bound A/B/C candidate portfolio generation with dual review and Pareto selection.
---

# Novel Candidate Portfolio · 统一候选 Skills 工作流

**Recommended:** use the repository-level `scripts/candidate.py` entry, which reads `config/candidate.json` and defaults to A/B/C (`abc_branch_one`). Select `quality_strict` when higher intermediate candidate survival is desired. Claim operations run against each task's frozen snapshot. When only the standalone Skill folders are installed, the local `scripts/candidate.py` is an independent compatibility entry and does not inherit root-level policy selection. See the full repository's `docs/POLICY_CONFIGURATION.md`.

## Use from an Agent

A Skills-capable Agent should load this instruction alongside the sibling scanning
and routing Skills, retain access to the **full Rank2Story repository**, and call the
root-level `scripts/candidate.py` command for real candidate operations.
The run must start from a validated frozen evidence packet; never treat the
standalone Skill YAML header as proof that platform access or a model endpoint exists.

For automatic model jobs, a user may configure the untracked root `.env`
(from `.env.example`), or inject model settings using their Agent's secret manager.
`python scripts/model.py status` checks setup without printing any credential.
The Agent's conversational model is not automatically the executor's HTTP model service;
using it directly requires an explicit supported adapter or API endpoint.
See `docs/AGENT_INTEGRATION.md` and `docs/QUICKSTART.md`.

## Inputs

Resolve three user-facing choices for a full candidate run: lane (`short`/`long`), target platform (`fanqie`/`qimao`), and audience channel (`male`/`female`), e.g., 番茄男频长篇 or 七猫女频短篇. The target platform describes the candidate positioning, not the only permissible market evidence source. Candidate execution also requires a validated sealed packet, writable output root and configured model API (with a Key only when needed).

## CLI — complete repository (recommended; defaults to 4.4.2)

From repository root, always use the single configurable entry:

```bash
python scripts/candidate.py config
python scripts/candidate.py run --base-root ./data/runs --packet "<packet.json>" --lane long --platform fanqie --channel male
python scripts/candidate.py run --policy quality_strict --base-root ./data/runs --packet "<packet.json>" --lane long --platform fanqie --channel male
python scripts/candidate.py status --claim "<claim.json>"
python scripts/candidate.py execute --claim "<claim.json>"  # loads root .env if configured
python scripts/candidate.py verify --claim "<claim.json>"
```

**The default is `abc_branch_one`**, not the historical baseline. Use `config/candidate.json` or `run --policy` to select the run's controller. `status/resume/execute/verify` always use the claim's immutable frozen snapshot and reject any attempt to change its policy.

## Standalone Skill CLI (when not installing the full repository)

This local entry uses the `quality_strict` compatibility policy independently of the project-level config. From this Skill directory:

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
- Production expects 3 kernels per branch, smoke expects 2. All repair actions share a 128-call recovery budget, warning at 400 calls, fuse at 512 calls. Under the default `abc_branch_one` policy, deliver 3–6 reviewed cards with at least one qualified card from each of A, B and C, plus at least three distinct mechanisms. The standalone `quality_strict` policy has its own historical delivery rules.
- Stop at `awaiting_user_choice`; fiction drafting is another downstream workflow.

## Reusing a market evidence packet

A verified `evidence_packet.json` is a reusable, dated market research snapshot: check its lane, source coverage and collection date before another run. The same `--packet` path may initialize multiple **separate new runs**, each with independent generation, reviews and verification. Never overwrite previous runs or call an old packet fresh data; cross-run candidate novelty is not guaranteed.

## Recovery

Use the controller's `status`, `resume` and `verify` on the same frozen claim. Do not manually edit accepted stage JSON, substitute old evidence, fabricate source IDs or bypass schema and channel checks. See `references/operations.md`.

## Credentials and copyright

Provide your own inference server and API key environment variable if needed. Neither login sessions nor raw website content is bundled; ensure collection is authorized and complies with site terms.