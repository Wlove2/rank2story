# Candidate engine operations — portable release candidate

Use `scripts/candidate.py` as the single entry point. Source code is in the adjacent `novel-analyzer/scripts` skill. Run artifacts live in a writable directory supplied by the operator.

## Workflow and validation

Run the controller with a current frozen evidence packet and explicit lane, target platform and audience channel. The controller initializes S1 atoms, S2 A/B/C kernels plus story creator/editor/mapper, two independent S3 reviews, then clustering and Pareto selection at S4.

Use `execute --claim <claim-file> --base-url <your-endpoint> --model <model-id>` to run the deterministic action loop. Optional credential injection is supported through `--api-key-env ENV_VARIABLE_NAME`, not hardcoded keys. The sample endpoint is not supplied by this repository.

For interruption, inspect `status` and `resume`; never edit accepted model artifacts or run state. Finish with `verify --claim ...`; only a `passed` result with no failures qualifies for delivery.

Production initially creates 3 kernels per branch; smoke 2. After editor vetoes, a minimum of one mapped candidate per A/B/C branch is allowed. Actual final selection requires A, B and C each represented by at least one independently approved and structurally distinct card, at least three truly different causal mechanisms, and 3–6 cards. Cross-branch structural collisions trigger bounded targeted recovery (per-branch kernel supplements max 3). Recovery budget=128, warning threshold=400, fuse=512. Content review rejections are legitimate business outcomes and must not be overridden merely to make the batch pass.

All paths in the run claim are authoritative. The run's `_bundle_snapshot` is used for verification and resumption even if current installed Skills have changed. Avoid copying cross-run state.

## Security and external dependencies

The original deployment used privately configured model routing and authorized collectors; those are not bundled. Supply your own compatible model API, review the network/site terms, and never publish cookies, keys, personal paths, or real raw book content.

## Common failure causes

Model output format rejection (repair with controller), mismatched evidence hashes, absent platform/source coverage, channel mismatch veto, incomplete reviewer verdicts, unexpected output files, targeted kernel supplements, and expired executor leases. Errors must be fixed without relaxing validators.

See the project README, `SECURITY.md`, `THIRD_PARTY.md` and `docs/RESULTS.md` for distribution boundaries. Do not publish credentials or raw novel texts.