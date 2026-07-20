# HR Radar Phase 2 Development Plan

**Status:** Ready for implementation  
**Planning date:** 2026-07-20  
**Working branch:** `codex/hr-radar-quality-pilot`  
**Working tree:** `$HOME/agent-workbench/worktrees/ai-news-radar-hr-quality`  
**Current branch head:** `2519e72`  
**Current `origin/master`:** `ece3e61618f03f32cb028de234b6350eee13bdd5`  
**Related external PR:** `LearnPrompt/ai-news-radar#22`, head `13b43a3`

## Objective

Turn the source-quality pilot into a production-compatible, advanced HR radar path without changing the default AI News Radar experience.

The next implementation must first prove that two new China-focused HR research or editorial sources improve the non-policy signal mix:

1. HRTechChina AI archive
2. HREC research reports

`中国人力资源开发` remains a research watchlist source until an exact publication timestamp can be obtained. PR #22 remains reference material only; its RSS filtering and fallback-to-now behavior must not be reused.

## Product boundary

### Target user

- China-based HR, HRBP, recruiting, HRIS, learning, and organization-development practitioners
- Maintainers deciding whether the HR vertical is strong enough for a separate advanced route

### Narrowest useful result

A repeatable source-quality and normalized-data pipeline that can run locally and expose its failures. A public HR page is not required to complete the first two development phases.

### Non-goals

- Do not add an HR tab or source controls to the default AI News Radar homepage.
- Do not merge, close, or modify PR #22 without separate authorization.
- Do not enable a production workflow or publish a Pages route in the source-adapter phase.
- Do not commit generated news snapshots or `/tmp` reports.
- Do not use cookies, login state, browser automation, paid APIs, or private inboxes.
- Do not replace missing publication dates with fetch time.
- Do not present policy aggregation as legal advice.

## Current evidence

The first pilot retained 17 of the tested records:

- 12 policy and labor-compliance items
- 1 independent HR x AI editorial item from HR Dive
- 4 relevant but vendor-authored Moka items

The new source intake found:

| Source | Public path | Local 180-day sample | Timestamp | Intake decision |
| --- | --- | ---: | --- | --- |
| HRTechChina AI | `https://www.hrtechchina.com/tag/ai/` | 6 recent items on the first parsed page | explicit day | implement in pilot |
| HREC reports | `https://www.hrecchina.org/publication_yjbg/` | 4 recent reports | explicit day | implement in pilot |
| 中国人力资源开发 | `https://zrzk.cbpt.cnki.net/portal/journal/portal/client/index` | 12 current-issue article links | issue only | watchlist |

No usable RSS, Atom, or sitemap endpoint was found for the two selected sources. Both therefore use focused public-static-page adapters.

## Architecture decision

Use a gated two-step architecture.

### Step A: extend the maintainer-facing quality probe

Keep source discovery, filtering, source bias, and quality metrics in the existing standalone pilot:

- `config/hr_source_candidates.json`
- `scripts/probe_hr_radar_quality.py`
- `tests/test_hr_radar_quality.py`

This is the smallest path that can prove information quality without creating another product surface.

### Step B: create a separate advanced data pipeline only after quality passes

After the source gate passes, refactor the validated adapters into:

- `scripts/hr_radar_sources.py`: source adapters and normalized HR item model
- `scripts/update_hr_radar.py`: CLI, archive handling, filtering, status, and output orchestration
- `config/hr_sources.json`: approved advanced HR sources only
- `tests/test_hr_radar_sources.py`: adapter and pipeline contract tests

The HR path should follow the repository's `RawItem`, URL normalization, retry, source-status, archive, and explicit-failure patterns where practical. It must not be registered in `collect_all()` or pass through the default AI relevance scorer.

## Source contracts

### HRTechChina AI

- URL: `https://www.hrtechchina.com/tag/ai/`
- Source class: Chinese HR technology vertical media
- Parser target: `ul.news_con > li`
- Title/link: `.tag-text-con > a[href]`
- Date: `.tag-time-con`
- Canonical URL: normalized `https://www.hrtechchina.com/<id>.html`
- Encoding: response-detected UTF-8
- Relevance rule: require both an HR signal and an AI/automation signal
- Risk rule: flag event promotion, registration, award, vendor ranking, investment roundup, and product-selection language
- Source cap: no more than 6 retained items per run during the pilot

### HREC research reports

- URL: `https://www.hrecchina.org/publication_yjbg/`
- Source class: professional membership research organization
- Parser target: report `li` nodes containing `time.time`
- Title: the report-title link inside the same list item
- Date: `time.time`
- Canonical URL: prefer the `线上阅读` link such as `/yulan.shtml?ID=<id>`
- Artifact URL: retain the direct PDF link as metadata; do not use it as the canonical article URL
- Encoding: force or detect UTF-8 with BOM safely
- Relevance rule: accept HR research reports, then classify AI crossover separately
- Risk rule: mark jointly produced, sponsored, supplier-guide, or procurement-oriented reports as `research_partner_risk`
- Source cap: no more than 4 retained items per run during the pilot

### 中国人力资源开发

- Source class: academic journal
- Current decision: `watchlist`
- Reason: current issue and canonical article links are public, but the listing exposes an issue number rather than an exact publication day
- Promotion condition: obtain an explicit article publication date from a stable public field without login

## Normalized item contract

Every retained item must expose:

```json
{
  "id": "stable hash from source id and canonical URL",
  "source_id": "hrtechchina_ai",
  "source_name": "HRTechChina",
  "source_kind": "editorial | research | official_policy | vendor",
  "source_bias": "independent | commercial_media | research_partner | vendor",
  "title": "original title",
  "url": "canonical article or online-reading URL",
  "artifact_url": "optional PDF URL",
  "published_at": "UTC ISO timestamp",
  "timestamp_quality": "explicit | inferred_from_url",
  "region": "中国 | 全国 | 北京 | 全球",
  "category": "one approved HR category",
  "hr_signals": [],
  "ai_signals": [],
  "quality_flags": [],
  "marketing_risk": false
}
```

Missing timestamps, invalid canonical URLs, and parser failures must remain visible in source status and must not produce retained items.

## Implementation sequence

### Phase 0: synchronize and protect the baseline

1. Confirm the original worktree and this worktree are both clean or contain only known user changes.
2. Rebase the local pilot branch onto the latest `origin/master`; it is currently one commit ahead and one commit behind.
3. Rerun the existing 243-test baseline before behavior changes.
4. Record the new base SHA in this plan or the implementation handoff.

Stop if the rebase overlaps source, scoring, or data-contract changes from `master`; review the conflict instead of auto-resolving it.

### Phase 1: add fixtures and source adapters

Files:

- Modify `config/hr_source_candidates.json`
- Modify `scripts/probe_hr_radar_quality.py`
- Modify `tests/test_hr_radar_quality.py`
- Add `tests/fixtures/hrtechchina_ai.html`
- Add `tests/fixtures/hrec_reports.html`

Work:

1. Add the two source definitions with explicit selectors, caps, source kind, and source bias.
2. Separate title selection from canonical-link selection so HREC can use `线上阅读` rather than a PDF download redirect.
3. Add an optional artifact URL field for HREC PDF files.
4. Add source-level encoding handling without weakening TLS verification.
5. Deduplicate by canonical URL first and normalized title second.
6. Add `--source <id>` to the probe for source-only validation.

Tests:

- Parse HRTechChina title, date, and canonical URL from a fixture.
- Parse HREC title, explicit date, online-reading URL, and PDF artifact URL.
- Reject an HREC item with no date.
- Reject a malformed or off-domain canonical URL.
- Ensure event and supplier language is flagged, not silently treated as independent evidence.
- Ensure duplicate titles or URLs collapse deterministically.

### Phase 2: strengthen quality and provenance

Files:

- Modify `scripts/probe_hr_radar_quality.py`
- Modify `tests/test_hr_radar_quality.py`
- Update `docs/research/2026-07-20-hr-radar-source-quality-pilot.md`

Work:

1. Add source-kind and source-bias fields to retained records and summaries.
2. Report independent, official, research-partner, and vendor contributions separately.
3. Keep the strict HR-plus-AI rule for broad editorial pages.
4. Allow curated HR research listings to pass as HR research while preserving a separate crossover flag.
5. Add editorial-value flags for event recaps, registration pages, technical notices, award posts, and vendor roundups.
6. Add source-specific keep caps after relevance evaluation so one archive cannot dominate the report.
7. Add a manual-audit section listing every retained candidate for review.

### Phase 3: run the quality gate

Run a 180-day backfill and at least seven source-only fetches spread across 14 calendar days. Generated artifacts stay under `/tmp`.

Required reports:

- combined Markdown and JSON source-quality report
- per-source retained and rejected samples
- timestamp-quality summary
- category balance
- source-bias contribution
- parser failure history

Gate A — technical intake:

- HRTechChina parses at least 5 items in the 180-day sample.
- HREC parses at least 3 reports in the 180-day sample.
- 100% of retained items have explicit source dates and stable canonical URLs.
- All failures and empty results appear in status output.
- Neither source requires login, cookies, secrets, or browser automation.

Gate B — information quality:

- Manual topical precision is at least 85%.
- At least 8 retained non-policy items come from the two new sources in the backfill.
- The non-policy set covers at least three HR categories.
- Promotional or partner-backed material is flagged with 100% recall in the audited sample.
- Vendor or partner material is never counted as independent corroboration.
- Source fetch availability is at least 95% across the 14-day observation period.

If Gate A or Gate B fails, keep the project as a quality probe and do not start the data pipeline or UI phase.

### Phase 4: build the advanced HR data pipeline

Start only after both quality gates pass.

Files:

- Add `scripts/hr_radar_sources.py`
- Add `scripts/update_hr_radar.py`
- Add `config/hr_sources.json`
- Add `tests/test_hr_radar_sources.py`
- Update `docs/SOURCE_COVERAGE.md`

Outputs under a caller-provided directory:

- `latest.json`: retained HR records for the selected window
- `archive.json`: canonical deduplicated history
- `source-status.json`: success, failure, zero count, latency, and parser diagnostics
- `quality-summary.json`: category, source-bias, timestamp, and risk statistics

CLI contract:

```bash
python scripts/update_hr_radar.py \
  --config config/hr_sources.json \
  --output-dir /tmp/ai-news-radar-hr-preview \
  --window-hours 168 \
  --archive-days 180
```

Use a seven-day default display window for low-frequency HR research. Keep an explicit timestamp field so the UI can still show the real source date rather than fetch time.

### Phase 5: evaluate the separate HR page

Start only after the normalized data contract is stable.

PR #22's `hr/index.html` may be used as a visual reference, but do not copy its data assumptions unchanged. A revised page must:

- read the new advanced HR data schema
- show original source date and source type
- visibly label official, editorial, research-partner, and vendor material
- expose source-health or stale-data state
- preserve the legal-information disclaimer
- escape all source-controlled strings
- avoid adding navigation or controls to the default homepage

Validate at 390px and 1440px widths, with keyboard navigation and no horizontal overflow. Opening a public route, linking it from the homepage, or deploying it remains a separate user decision.

### Phase 6: optional automation

Do not modify the production update workflow during source development. After the data and page gates pass, propose a manually triggered branch-preview workflow first. Scheduling, Pages publication, and production deployment require separate approval.

## Commit and review structure

Keep implementation reviewable:

1. `test: add HRTechChina and HREC parser fixtures`
2. `feat: add Chinese HR source adapters and provenance flags`
3. `feat: add advanced HR radar data pipeline`
4. `feat: add HR radar preview` — only after the quality gate

Do not combine source adapters, generated data, UI, and workflow activation in one commit or one review decision.

## Validation commands

```bash
RADAR_PYTHON="$HOME/agent-workbench/projects/ai-news-radar/.venv/bin/python"

"$RADAR_PYTHON" -m py_compile \
  scripts/probe_hr_radar_quality.py \
  scripts/hr_radar_sources.py \
  scripts/update_hr_radar.py

"$RADAR_PYTHON" -m pytest -q \
  tests/test_hr_radar_quality.py \
  tests/test_hr_radar_sources.py

"$RADAR_PYTHON" -m pytest -q

"$RADAR_PYTHON" scripts/probe_hr_radar_quality.py \
  --config config/hr_source_candidates.json \
  --output-dir /tmp/ai-news-radar-hr-quality

"$RADAR_PYTHON" scripts/update_hr_radar.py \
  --config config/hr_sources.json \
  --output-dir /tmp/ai-news-radar-hr-preview \
  --window-hours 168 \
  --archive-days 180

git diff --check
```

During Phases 1–3, omit commands for files that do not exist yet. After Phase 5, also run the repository's existing browser and JavaScript checks against the HR preview.

## Stop conditions

Stop and report instead of advancing when any of these is true:

- either selected source fails two consecutive source-only probes
- retained-item timestamp quality drops below 100%
- manual topical precision is below 85%
- promotional material cannot be reliably identified
- a source starts requiring login, cookies, secrets, or browser automation
- the implementation would require changing the default homepage or production workflow before the quality gate
- current `master` introduces an incompatible data-contract or source-pipeline change

## Rollback

- Source-adapter work remains on the local feature branch until review.
- Generated outputs remain under `/tmp` and can be discarded without touching tracked data.
- Each phase is a separate commit and can be reverted independently.
- No force push, branch deletion, PR closure, merge, workflow activation, or deployment is part of this plan.

## Definition of done

This development plan is complete when:

1. HRTechChina and HREC pass the technical and information-quality gates.
2. The advanced HR data CLI emits deterministic records plus visible source status.
3. All focused and full tests pass.
4. Default AI News Radar data, UI, and workflow remain unchanged.
5. A final review recommends one of three outcomes with evidence: keep experimenting, open a replacement PR, or stop the HR vertical.
