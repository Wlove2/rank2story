# Candidate action output contract 4.4.0-rc1

This file describes only model-authored fields. The controller injects run IDs, stages, hashes, lane/profile fields, receipts, branch provenance, evidence slices, and output seals. Write one JSON object to the action's exact `raw_output`; do not add scripts or edit other artifacts.

## S1 atoms

Return `atoms`, a list of objects with:

```text
atom_id, lane, atom_type, evidence_id, source_item_id, source_id,
source_cohort, platform, observation, inference, confidence, freshness,
claim_key, stance, supporting_evidence_ids, counter_evidence_ids,
contradicting_atom_ids, generation_safe
```

Use only evidence IDs and sources present in `evidence_packet.json`. `observation` states what the evidence shows; `inference` states a story implication and must not copy the observation. `generation_safe` must be true. Valid `stance` values are `support`, `counter`, and `mixed`.

## S2 generation branch

Return:

```text
{
  "branch_id": "A|B|C",
  "concept_kernels": [kernel, kernel, kernel, ...],
  "candidates": [candidate, candidate, candidate, ...]
}
```

Each kernel requires:

```text
kernel_id, mechanism_signature, premise, causal_chain,
reader_payoff, execution_plan, cited_atom_ids
```

Each candidate requires:

```text
kernel_id, candidate_id, cited_atom_ids, structural_fingerprint,
candidate_card
```

`structural_fingerprint` requires these causal fields:

```text
audience_desire, protagonist_lack, agency, core_mechanism,
mechanism_cost, opponent_interest, escalation, payoff_mode,
reaction_chain, ending_reward
```

Short lane also requires `opening_form` and `short_closure`. Long lane also requires `relationship_engine`, `world_expansion`, and `stage_engine`.

Each `candidate_card` requires:

```text
one_line_concept, target_reader, opening_300_beats, reward_cycle,
three_payoffs, closest_work, causal_difference, risks
```

- `opening_300_beats`: exactly five substantive strings.
- `reward_cycle`: exactly six strings in causal order: pressure/gap, choice, irreversible action, visible result, world reaction, new cost/desire.
- `three_payoffs`: exactly three substantive strings.
- `closest_work` and `causal_difference`: generator hypotheses only. Make both candidate-specific. Never copy a branch goal or reuse one causal difference across candidates.
- `risks`: non-empty substantive strings.
- Short lane: include substantive `short_closure`.
- Long lane: include `long_run_stages` with keys `300k`, `800k`, `1500k`; every value is an object containing `goal`, `relationship_change`, `world_expansion`, `irreversible_change`, and `stage_payoff`.

The controller overwrites target platform/channel/profile, evidence atom IDs, branch metadata, and hashes.

## S2 candidate_mapper

Return one candidate object containing only `structural_fingerprint` and `candidate_card`. Map facts already present in the story; do not add a new cause, motivation, mechanism rule, ending condition, score, or audit.

CRITICAL LANGUAGE RULE: ALL text fields in candidate_card (`one_line_concept`, `target_reader`, `opening_300_beats`, `reward_cycle`, `three_payoffs`, `closest_work`, `causal_difference`, `risks`, `short_closure`) MUST be written in Chinese (中文). Never output English sentences in any card field.

Short lane: the candidate_card MUST include a substantive `short_closure` field (2-4 sentences describing how the short story ends and closes its emotional loop).

## S3 market review

Return `candidates`, a JSON object keyed by every representative candidate ID. Each value requires:

```text
status, checks, entry_promise, reward_cycle, platform_fit, channel_fit,
activity_fit, causal_consistency, contradictions,
calibrated_objectives, objective_rationales
channel_verdict, protagonist_perspective
```

Field definitions:

- `status`: `"passed"` or `"rejected"`. Use rejected when the candidate should not proceed.
- `checks`: dict with keys `{story_review_passed, representative, entry_promise, reward_cycle, platform_fit, activity_fit, short_closure}` (short lane) or `{story_review_passed, representative, entry_promise, reward_cycle, platform_fit, activity_fit, three_stage_engine}` (long lane). All true for passing candidates; rejected candidates may have false values indicating which checks failed.
- `entry_promise`: substantive Chinese string describing the reader's entry hook.
- `reward_cycle`: list of 4-6 substantive Chinese strings in causal order.
- `platform_fit`: substantive Chinese string assessing platform suitability.
- `channel_fit`: substantive Chinese string assessing channel suitability.
- `activity_fit`: `"not_applicable"` for general runs; dict with `activity_id`, `matched_requirements`, `violations` for activity runs.
- `causal_consistency`: substantive Chinese string assessing causal coherence.
- `contradictions`: empty list `[]` for passing candidates; may list specific contradictions for rejected ones.
- `calibrated_objectives`: MUST be a flat dict with exactly 5 keys (`commercial_certainty`, `structural_novelty`, `emotional_impact`, `producibility`, `originality_risk`) each mapped to an INTEGER 1-5. Do NOT nest score+rationale into values.
- `objective_rationales`: MUST be a SEPARATE dict with the SAME 5 keys each mapped to a substantive Chinese rationale string.
- `channel_verdict` (L3, required): one of `fit` / `partial` / `mismatch` — how well this card matches the run's audience channel. An opposite-gender perspective is NOT automatically mismatch; judge `partial` with a concrete `channel_fit` reason when the card still has acceptable channel fit. `mismatch` MUST be paired with `status=rejected`; never claim `fit` for an opposite-gender perspective.
- `protagonist_perspective` (L3, required): one of `male` / `female` / `neutral` — the protagonist's gender perspective.

Short lane adds `complexity_budget`: dict with `mechanism_count` (integer 1-3) and `assessment` (substantive Chinese string).

Long lane adds `three_stage_engine`: dict with keys `300k`, `800k`, `1500k`; each value is an object containing `goal`, `relationship_change`, `world_expansion`, `irreversible_change`, `stage_payoff` (all substantive Chinese strings).

## S3 originality review

Return `candidates`, a JSON object keyed by every representative candidate ID. Each value requires:

```text
layers, closest_work, causal_difference, closest_work_reference,
evidence_methods, calibrated_originality_risk,
originality_risk_rationale
```

Field definitions:

- `layers`: MUST be a JSON OBJECT (dict, NOT an array) with keys exactly `"expression"`, `"semantic"`, `"structural"`, `"causal"`. Each key's value is a dict with `status` (`"passed"`), `collision`, `high_recognition_collision` (boolean), `closest_match`, `evidence` (all substantive). The reviewer may correct the generator's closest-work hypothesis and causal difference; assembly uses the reviewer values.
- `closest_work`: substantive Chinese string identifying the nearest known work.
- `causal_difference`: substantive Chinese string explaining the causal distinction from the closest work.
- `closest_work_reference`: an object with a substantive `identifier` and an `evidence_id` present in the frozen evidence slice.
  Invented evidence IDs and unregistered URLs fail.
- `evidence_methods`: non-empty list of strings describing verification methods used.
- `calibrated_originality_risk`: integer from 1 to 5.
- `originality_risk_rationale`: substantive Chinese string justifying the risk score.

Do not use AI-detector, perplexity, or AI-probability scores as originality evidence.
