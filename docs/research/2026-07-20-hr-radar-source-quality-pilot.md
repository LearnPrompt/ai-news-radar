# HR Radar Source Quality Pilot Results

**Run date:** 2026-07-20  
**Branch:** `codex/hr-radar-quality-pilot`  
**Baseline:** `origin/master` at `c20a89a6069362c0cc1d67e88cfb5ced1892d632`  
**Live output:** `/tmp/ai-news-radar-hr-quality-20260720-v3/`

## Decision

Keep the HR vertical as an advanced experiment. Do not merge PR #22 as-is and do not add it to the default radar yet.

The policy lane is useful enough to continue testing, but the independent HR x AI practice lane is too thin for a daily product. The current sample is also heavily weighted toward policy and compliance rather than recruiting, HR products, learning, and organizational change.

## Live result

The probe evaluated six public source candidates over a 180-day window:

| Source | Recent | Kept | Relevance | Crossover | Risk | Decision |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| 中国就业网 | 49 | 8 | 16.3% | 2.0% | 40 missing timestamps; dates inferred from 57 URLs | `pilot` |
| 北京市人社局政策 | 4 | 4 | 100.0% | 0.0% | none observed | `pilot` |
| 上海市人社局政策 | 0 | 0 | 0.0% | 0.0% | current static selector returns no items | `needs-adapter` |
| 深圳市人社局政策 | 0 | 0 | 0.0% | 0.0% | local TLS handshake fails | `needs-adapter` |
| HR Dive | 10 | 1 | 10.0% | 10.0% | low China specificity | `pilot` |
| Moka AI招聘 | 12 | 4 | 33.3% | 33.3% | all four retained items are vendor-authored | `watchlist` |

The final retained set contains 17 items:

- 12 policy and labor-compliance items
- 2 organization and talent-management items
- 2 case, report, or trend items
- 1 HR product and digitalization item

## Manual quality audit

The stricter rule reduced the first live run from 35 retained items to 17. It removed generic job fairs, employment service activity, personnel appearances, and other broad employment news that was topically related but not useful enough for a specialist radar.

Of the final 17 items:

- 16 are clearly relevant to policy, compliance, HR operations, or HR x AI.
- 1 public-employment competition technical notice is relevant by rule but low in editorial value.
- 4 Moka items are relevant but cannot be treated as independent evidence; the report marks every retained vendor item as marketing risk.
- 12 items are usable without a vendor-bias caveat, although several official case updates are medium rather than high editorial priority.

The probe also fixed two failure modes seen in the original PR experiment:

1. ASCII keywords use word boundaries, so `training`, `candidate`, or a generic model title cannot create an AI or HR match by substring accident.
2. Missing timestamps are reported and skipped instead of silently replaced with the current time.

## What is good enough

- Beijing's policy listing provides explicit dates, stable article URLs, and a clean official-policy lane.
- China Job can contribute national policy and compliance signals after the stricter policy-or-AI gate.
- HR Dive provides a stable RSS feed and a small independent practice lane.
- Source failures, empty parsers, timestamp quality, relevance rate, crossover rate, and vendor risk are visible in both JSON and Markdown outputs.

## What blocks product integration

- Only one retained item comes from an independent HR x AI editorial source in this live window.
- The retained mix is 70.6% policy and labor compliance, so it does not yet represent the proposed HR vertical evenly.
- Shanghai requires a dedicated dynamic-page adapter, while Shenzhen needs a transport workaround or a different official endpoint.
- China Job has no explicit timestamps in the parsed listing; 57 dates are inferred from canonical URL paths and 40 undated links are skipped.
- The Moka lane is useful for product discovery but must stay labeled as vendor material.

## Next quality gate

Before product integration, rerun the pilot only after adding at least two independent, publicly accessible China-focused HR research or editorial sources. A revised vertical should also prove that it can produce non-policy coverage across at least three HR categories without relying on vendor pages.

## Reproduction

```bash
python3 -m py_compile scripts/probe_hr_radar_quality.py
python3 -m pytest -q tests/test_hr_radar_quality.py
python3 scripts/probe_hr_radar_quality.py \
  --config config/hr_source_candidates.json \
  --output-dir /tmp/ai-news-radar-hr-quality-20260720-v3
git diff --check
```

The probe does not modify `scripts/update_news.py`, the homepage, workflows, or production data.
