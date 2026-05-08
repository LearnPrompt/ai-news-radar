# GPT Handoff: AI News Radar V2

Use this document to hand the project to a fresh GPT/Codex/Claude session for
verification.

## Local Project

- Local path: `/Users/carl2077/workspace/ai-news-radar`
- Public site: `https://learnprompt.github.io/ai-news-radar/`
- Local preview used during development: `http://127.0.0.1:8091/`
- Local preview directory: `/tmp/ai-news-radar-preview`

The working repo may use skip-worktree for large `data/*.json` files. For
browser validation, prefer the preview URL above or rebuild a preview directory
from Git-tracked data. If a checked-out copy already has `data/*.json`, this is
enough:

```bash
cd /Users/carl2077/workspace/ai-news-radar
python -m http.server 8080
```

## What This Project Is

AI News Radar is a static 24h AI/tech news radar:

- ordinary readers open the hosted page and read 24h AI updates
- maintainers can fork it and add private OPML/RSS via GitHub Secrets
- Codex / Claude Code can use `skills/ai-news-radar/SKILL.md` to maintain source
  coverage, evaluate new feeds, and keep the product simple

## Implemented V2 Work

Product/UI:

- Added first-viewport coverage radar:
  - source health
  - AI signal density
  - official/newsletter coverage
  - Builders/X coverage through Follow Builders
  - aggregator breadth
  - private extension readiness through OPML/Secrets
- Added source-type tags on news cards, such as official, newsletter,
  Builders/X, and aggregator.
- Kept advanced filters inside the advanced panel so ordinary readers are not
  forced to choose between many source controls.
- Added SVG favicon from the existing logo.

Sources and coverage:

- Built-in official AI sources include OpenAI News, OpenAI Codex Changelog,
  OpenAI Skills commits filtered for Codex/pet-related updates, Anthropic,
  Google DeepMind, Google AI, Hugging Face, and GitHub AI/Changelog.
- AI Breakfast is read through its public archive path because Beehiiv feed
  access can be blocked in CLI/GitHub Actions environments.
- Follow Builders is consumed as public generated JSON feed files. The project
  does not copy its X API token flow.
- X API, email inboxes, WeChat, cookies, and login-bound bridges are treated as
  advanced/private integrations, not public defaults.

Skill/docs:

- Added `skills/ai-news-radar/SKILL.md` for Codex/Claude workflows.
- Added `skills/ai-news-radar/references/source-intake.md`.
- Added `skills/ai-news-radar/references/v2-method.md`.
- Added `docs/SOURCE_COVERAGE.md`.
- Added `docs/V2_PRODUCT_BRIEF.md`.
- Updated `README.md` so readers, fork users, and agent users each have a clear
  entry point.

## Validation Already Run

```bash
node --check assets/app.js
/tmp/ai-news-radar-venv/bin/python /Users/carl2077/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/ai-news-radar
/tmp/ai-news-radar-venv/bin/pytest -q
git diff --check
```

Last known result:

- Skill validator: `Skill is valid!`
- Tests: `28 passed`
- GitHub Pages deployment: success

## Verification Checklist For A Fresh GPT

Please verify:

1. Reader path: Can a normal user understand that they only need to open the
   public page?
2. Fork path: Can a GitHub user understand how to fork, enable Pages/Actions,
   and optionally add OPML through `FOLLOW_OPML_B64`?
3. Agent path: Can Codex/Claude find the Skill and know which files to read
   first?
4. Coverage honesty: Does the repo clearly distinguish public default sources
   from advanced/private integrations?
5. UI: Does the first viewport show source coverage without overwhelming new
   users?
6. Safety: Are private OPML files, tokens, cookies, inboxes, and API keys kept
   out of the repository?
7. Maintenance: Are validation commands and source-intake rules clear enough for
   a future agent to add or reject new sources?

## Suggested Prompt For New GPT

```text
你现在接手本地项目：
/Users/carl2077/workspace/ai-news-radar

请使用项目内 Skill：
skills/ai-news-radar/SKILL.md

请先阅读：
README.md
docs/GPT_HANDOFF.md
docs/SOURCE_COVERAGE.md
docs/V2_PRODUCT_BRIEF.md
skills/ai-news-radar/references/source-intake.md
skills/ai-news-radar/references/v2-method.md

任务：
1. 判断这个 AI 新闻聚合项目是否已经达到 v2 soft launch / 可公开发布状态。
2. 分别从普通读者、fork 用户、Codex/Claude Skill 用户三个角度验收 README 和项目结构。
3. 检查是否有隐私/密钥/OPML 泄漏风险。
4. 检查信息源覆盖是否诚实：哪些是公共默认源，哪些只是高级/私有路径。
5. 如果发现问题，请按严重程度列出具体文件和建议修复方式。

不要直接重构。先做验收报告。
```
