# Social evidence source policy (Bilibili and Xiaohongshu)

This is the public explanation of the **existing deterministic contract** in `references/source-registry.json`, `scripts/social_evidence.py`, `scripts/normalize_current_run_sources.py`, and `scripts/validate_source_coverage.py`. It is not a permission to fetch content from any site.

## Registered source IDs

- `xiaohongshu_novel_demand_shared`: reader/creator observations from public posts, when platform access is authorized.
- `bilibili_novel_demand_shared`: videos, summaries, and **complete** transcripts, when access is authorized.

A source may be used as independent signal evidence only when the collection and audit gate pass. A URL-only or metadata-only search result is **not** a complete independent demand signal.

## Quantitative audit gates (per platform, per new run)

The two platforms have different quotas. The authoritative values are the respective `coverage` entries in `references/source-registry.json`.

| Gate | Xiaohongshu | Bilibili |
| --- | ---: | ---: |
| Distinct discovered canonical URLs | 12 | 20 |
| Entries screened | 6 | 10 |
| Complete signal-eligible entries | 4 | 5 |
| Unique publishing accounts | 3 | 3 |
| Entries from any one account (maximum) | 2 | 2 |
| Current hotspot or ranking discussion | — | 1 |
| Curator roundup | — | 1 |
| Reader demand / book shortage | 1 | 1 |
| Negative or avoidance feedback | — | 1 |

Numbers in the first four rows and the required signal-type rows are minimums. A dash means there is no per-type minimum for that platform, not that the signal type is prohibited. The recognized `creator_market_analysis` type has no independent minimum. Failing a required gate must remain a degraded source, not be silently replaced by another platform.

## Entry completeness contract

The code audits a normalized evidence record containing:
- Canonicalizable `source_url` / `url`, publishing `author`, `published_at`, and numeric `engagement`;
- One valid `primary_signal_type` and a nonempty `full_text` or `transcript`;
- Explicit `content_complete: true`, independently supported by the capture process;
- For Bilibili: transcript length of at least 200 characters under the existing rule;
- For Xiaohongshu: integers `images_total` and `images_read` must match;
- `source_relation`, allowing an `official_rank_repost` to be retained while not counted as an independent demand signal unless original analysis is established.

`scripts/social_evidence.py` computes eligible counts from artifacts instead of trusting a claimed count in a summary. Canonical URL deduplication removes query strings, including signed parameters.

## Privacy, rights, and reproducibility

**Public repository distribution:** include only synthetic/mock social records, not copied posts, full transcripts, screenshots, personal account details, browser cookies, or signed platform URLs. Keep any permitted live captures in a private local run directory outside Git.

Website terms, access authorization, copyright, personal data minimization, and rate limits apply separately. A technically accessible endpoint does not automatically confer permission to scrape or redistribute its contents. Do not defeat access controls to meet source quotas.

If collection is unavailable or incomplete, report the actual missing source IDs and coverage failures; the candidate generator must not treat a degraded market scan as a successful frozen packet.
