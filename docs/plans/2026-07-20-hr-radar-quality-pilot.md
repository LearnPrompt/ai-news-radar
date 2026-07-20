# HR Radar Source Quality Pilot Plan

**Goal:** Determine whether a China-focused HR x AI vertical can produce a consistently useful daily signal before any part of PR #22 is merged.

**Branch:** `codex/hr-radar-quality-pilot`

**Baseline:** `origin/master` at `c20a89a6069362c0cc1d67e88cfb5ced1892d632`

**Architecture:** Keep this round as a maintainer-facing quality probe. Reuse the repository's existing HTTP, date-normalization, status, and JSON patterns where practical, but write all live outputs to `/tmp`. Do not add an HR choice to the default reader UI and do not wire the probe into the production workflow yet.

## Product decision

The pilot is for two audiences:

1. China-based HR, HRBP, recruiting, HRIS, and learning teams that need public policy and HR x AI signals.
2. AI News Radar maintainers deciding whether the vertical belongs in this repository, an advanced route, or a separate repository.

The narrowest useful output is a quality report, not a second news product. The report must show whether official policy sources and HR x AI sources are timely, parseable, low-noise, and distinct enough to justify maintenance.

## Non-goals

- Do not merge, modify, or close PR #22 in this round.
- Do not modify `scripts/update_news.py`, the default homepage, or the production workflow.
- Do not commit generated news snapshots.
- Do not use login state, cookies, private inboxes, private OPML, paid APIs, or browser automation.
- Do not present automated summaries as legal advice.
- Do not claim daily coverage until a source has a stable URL, canonical links, usable timestamps, and a successful live probe.

## Candidate source lanes

### Lane A: official China policy

- Ministry of Human Resources and Social Security
- State Council policy releases
- Cyberspace Administration of China
- National Bureau of Statistics employment releases
- Shanghai HRSS
- Beijing HRSS
- Shenzhen HRSS

### Lane B: HR x AI practice

- HR product release or research pages with public feeds or stable archives
- Public enterprise HR digitalization case studies
- Global HR research feeds only when the item is applicable to the China HR audience

The probe should begin with a small representative sample. A named organization in this plan is only a candidate, not a validated source.

## Quality rubric

Each candidate receives the following fields:

| Field | Meaning |
| --- | --- |
| `fetch_status` | HTTP and parser outcome |
| `source_type` | RSS, Atom, JSON, or public static page |
| `recent_items` | Items inside the configured lookback window |
| `timestamp_quality` | explicit, inferred, missing, or invalid |
| `canonical_url_quality` | stable article URL vs listing/search URL |
| `hr_relevance_rate` | manually inspectable rule-based keep rate |
| `ai_hr_crossover_rate` | items matching both an HR concept and an AI concept |
| `policy_authority` | official policy, official interpretation, or industry reporting |
| `region_coverage` | national, Shanghai, Beijing, Shenzhen, global, or unknown |
| `noise_samples` | representative false positives |
| `decision` | `pilot`, `watchlist`, `skip`, or `needs-adapter` |

## Relevance rules

An item is eligible when one of these conditions is true:

1. It comes from a curated official policy listing, where the page itself establishes the policy context.
2. It comes from a broad official HR news page and matches an HR concept plus a policy, regulatory, compliance, or AI concept.
3. It matches at least one HR concept and at least one AI/automation concept.

Pure model, chip, coding-tool, image, video, crypto, entertainment, and generic AI news must not pass only because the title contains `AI`, `model`, `agent`, `training`, or another broad substring. ASCII terms must use word-boundary matching.

## Implementation phases

### Phase 1: source discovery and live probe

- Resolve candidate feed/archive URLs from official sites.
- Record redirects, status codes, content type, item count, timestamp fields, and canonical links.
- Reject login-bound, unstable, stale, or undated sources.

### Phase 2: quality probe

- Add a standalone script that reads a public candidate config.
- Normalize RSS/Atom entries and explicitly report empty or failed sources.
- Apply the two-part relevance rule and category assignment.
- Produce JSON data plus a Markdown quality report under a caller-provided output directory.

### Phase 3: tests

- Pure AI news is rejected.
- HR x AI crossover items are retained.
- Official HR policy items can pass without an AI keyword.
- ASCII substring collisions such as `training`, `model`, and `candidate` do not become false AI/HR signals.
- Missing timestamps are reported and never replaced silently with the current time.
- Empty or failed feeds appear in source status.

### Phase 4: real-data evaluation

- Run the probe into `/tmp/ai-news-radar-hr-quality`.
- Manually inspect the retained items and false-positive samples.
- Compare source contribution, region coverage, recency, and category balance.

## Done when

The pilot is complete when all of the following are true:

- At least one official national or city policy source is successfully parsed, or the report documents why none can be used without a dedicated static-page adapter.
- At least one HR x AI practice source is successfully parsed.
- Every retained item has a canonical URL and an explicit source timestamp.
- The output reports failures and empty sources instead of silently returning zero items.
- Focused tests pass on the repository's documented local Python path and CI Python 3.11.
- The final report recommends one route: merge a revised vertical into this repo, keep it as an advanced experiment, or move it to a separate repository.

## Validation

```bash
python3 -m py_compile scripts/probe_hr_radar_quality.py
python3 -m pytest -q tests/test_hr_radar_quality.py
python3 scripts/probe_hr_radar_quality.py \
  --config config/hr_source_candidates.json \
  --output-dir /tmp/ai-news-radar-hr-quality
git diff --check
```

## Rollback

This branch is isolated from the existing working tree. Rollback is limited to deleting the local pilot branch/worktree after review; production code, workflow, Pages data, and PR #22 remain unchanged.
