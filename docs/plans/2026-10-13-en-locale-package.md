# 执行包：AI News Radar 英文版（P0 en）

日期：2026-10-13
分支：feat/en-locale，worktree `~/agent-workbench/worktrees/ai-news-radar-feat-en-locale`，基于 origin/master ab227dd4
看板卡：T-e4fb5c
来源：~/Downloads/aihot-lessons-2026-10-11/02-ai-news-radar.md 第 1 项，总方案第五节 P0

## 基准

- 远端 master ab227dd4（2026-10-13）。主工作树 ~/projects/ai-news-radar 落后 279 个提交（绝大多数是数据快照），本包不动它。
- 测试基线：Python 3.12 venv 下 `python -m pytest -q` 277 过；`node --check` 三个 JS 文件通过；CI 用 3.12。
- 生产：GitHub Actions `update-news.yml` 分时段跑 `scripts/update_news.py` 写 `data/`，Vercel 静态托管 news.learnprompt.pro（`outputDirectory "."`，`trailingSlash: false`，无 rewrites）。

## 卡尔 2026-10-13 拍板的参数

1. P0 只做默认视图 `/en/`；classic 视图（独立 3237 行 JS 分叉）延后，`/en/` 上隐藏「经典版」切换。
2. 英文版不展示博主区块（抖音、小红书创作者内容），不翻译。
3. DeepSeek 按上限跑：新增 `--translate-en-max-new` 默认 60；一次性回填约 250 次（推荐理由 143、中文摘要 21、中文标题约 80），之后每轮约 30 到 60 次。按 flash 单价一次性约 3 元，每天不到 1 元。

## 盘点结论（决定做法的几条）

- `classic/assets/app.js` 是独立分叉，不共享，所以延后。
- 摘要是抓取的不是模型写的，78 条非空摘要里 57 条本来就是英文，只有约 21 条中文的要译。模型文本只有 `recommend_reason_zh` 和项目一句话 `recommend_reason_zh`。
- `title_en` 在中文站当英文副标题用（`assets/app.js:624`），翻译出来的英文标题不能写进它。
- `story_item_link`（update_news.py 6416）和 `primary_item`（6493）是显式字段白名单，新字段必须加进去，否则 stories 和 daily-brief 里没有。
- `translate_to_zh_deepseek`（5270）的校验要求结果含 CJK，英文输出要新写校验；无重试，失败回退 Google。
- 缓存 `data/title-zh-cache.json` 10 MB、5.6 万条、从不修剪、每轮入库。英文缓存要单独一个文件并按 21 天修剪。
- 前端用相对路径取 `data/…` 和 `./assets/…`，复制到 `/en/` 会 404；`view-mode.js` 用 `data-root` 不认 `<base>`。
- `trailingSlash: false` 让 `/en/` 308 到 `/en`，canonical、hreflang、sitemap 都要用去斜杠的形式。
- 没有 sitemap、robots、hreflang，feed 只有中文一份且路径写死。
- 测试 `test_today_projects_ui.py`、`test_dual_view_contract.py` 断言中文字面量，抽串后要改。

## 范围

### A. 数据层（Python）

- `scripts/update_news.py`
  - 新增 `translate_to_en_deepseek(text)`：复用 DeepSeek 客户端与术语表的保护词；英文校验 `is_valid_en_translation`（无 CJK、不含拒答标记、长度在原文 0.3 到 3 倍之间）；失败返回 None，不回退 Google。
  - 新增 `add_en_fields(items, cache, max_new)`：每条写 `en: {title, summary, reason}`。title 只对含 CJK 的标题翻译，否则 None（前端回退 `title_en` / `title_original`）；summary 只对含 CJK 的摘要翻译；reason 对已有 `recommend_reason_zh` 的条目调 `generate_recommend_reason_deepseek(..., lang="en")`（同一函数加 lang 参数，英文 prompt，20 到 40 词），creator 条目一律跳过。
  - 缓存 `data/en-cache.json`，键 `en1|<kind>|sha1(url|text)`，值带 `at`，21 天修剪，随 data/ 入库。
  - 参数 `--translate-en-max-new`（默认 60，环境变量 `TRANSLATE_EN_MAX_NEW` 可覆盖），缺 DeepSeek key 时整段 no-op。
  - `story_item_link`、`primary_item` 白名单加 `en`。`importance_label` 保持中文，前端按映射表译。
  - 新增 `scripts/backfill_en.py`：只读现有 `data/latest-24h.json`、`latest-24h-all.json`、`stories-merged.json`、`daily-brief.json`、`today-projects.json`，补 `en` 字段写回，走同一缓存和上限（`--max-new`），用于一次性回填，也可在 Actions 手动触发。
- `scripts/project_sources.py`：`recommend_reason_en` 走同一路径，`recommendation_fallback` 加英文模板。
- `scripts/generate_feed.py`：`--lang zh|en --out <path>`；en 时频道标题、描述、`<language>en`，条目正文 `en.reason` → `en.summary` → 英文原文 summary。默认行为不变。
- `.github/workflows/update-news.yml`：在 generate_feed 之后加 `python scripts/generate_feed.py --lang en --out data/feed-en.xml`；`git add data/` 已覆盖。

### B. 前端与站点

- `assets/i18n/zh.json`、`assets/i18n/en.json`：键集合一致，带复数形式（`items: {one, other}`）。
- `assets/i18n.js`：`LANG` 取 `document.documentElement.lang`（en 开头为 en，否则 zh）；`t(key, params)`，复数用 `Intl.PluralRules`；`fmtNumber`、`fmtDate`、`collator` 按 LANG。
- `assets/app.js`：只替换用户可见的串（约 140 条），匹配逻辑用的正则和来源识别一律不动；`SOURCE_KINDS`、`SECTION_DEFS`、AI 标签、来源标签、`importance_label` 映射走 i18n；LANG 为 en 时隐藏博主区块与「经典版」切换；标题取法 en：`en.title` → `title_en`（多数英文时）→ `title_original` → `title`；摘要 `en.summary || summary`；理由 `en.reason`，没有就不显示 why-box；`Intl.*("zh-CN")` 与 `localeCompare(…,"zh-CN")` 改按 LANG。
- `en/index.html`：英文页面，`<html lang="en">`，`data-root="/en/"`，资源与数据用绝对路径 `/assets/…`、`/data/…`；canonical `https://news.learnprompt.pro/en`；hreflang zh-CN `/`、en `/en`、x-default `/`（含自身）；og、twitter 英文；`<link rel="alternate" type="application/rss+xml" href="/en/feed.xml">`。
- `index.html`：补同一组 hreflang 与 RSS alternate，其余不动。
- `assets/view-mode.js`：按 `data-root` 生成切换链接；en 下不渲染经典版入口。
- `sitemap.xml`、`robots.txt`（根目录静态文件）：列 `/`、`/classic`、`/en`，用 `xhtml:link` 写 alternates；robots 带 `Sitemap:` 行。
- `vercel.json`：rewrite `/en/feed.xml` → `/data/feed-en.xml`。
- `scripts/check_i18n_site.py`：解析两份 HTML 与 sitemap，断言 hreflang 互指且含自身、sitemap 里每个 URL 对应文件存在、en.json 与 zh.json 键一致、`/en/index.html` 的 UI 串不含 CJK（允许术语表里的专有名词）。
- `.github/workflows/test.yml`：`node --check` 加 `assets/i18n.js`、`assets/view-mode.js`；跑 `python scripts/check_i18n_site.py`。
- 测试：`test_today_projects_ui.py`、`test_dual_view_contract.py` 改成读 i18n JSON 断言；新增 `tests/i18n.test.mjs`（t 与复数）、`tests/test_i18n_site.py`。

## 非目标

- classic 视图英文化。
- 博主区块翻译。
- ja。
- 改 `title_en` 的语义。
- 改中文站任何可见文案。

## 依赖

- DeepSeek key 只在 Actions secrets 和卡尔本机环境里，仓库不碰。
- 回填要在有 key 的环境跑：卡尔本机 `DEEPSEEK_API_KEY` 导出后跑 `scripts/backfill_en.py`，或在 Actions 里 `workflow_dispatch` 一次。

## 产物

- 上面列的脚本、JSON、HTML、workflow 改动
- `data/en-cache.json`（回填后）
- `docs/README` 里加一段英文版说明（README.en.md 已有，补 /en 入口）
- 本文档

## 测试命令

```bash
. .venv/bin/activate
python -m py_compile scripts/update_news.py scripts/generate_feed.py scripts/backfill_en.py scripts/check_i18n_site.py
python -m pytest -q
node --check assets/app.js && node --check assets/i18n.js && node --check assets/view-mode.js
node --test tests/i18n.test.mjs tests/service-status.test.mjs
python scripts/check_i18n_site.py
git diff --check
```

## 预览验收

- 本地 `python -m http.server 8080`，打开 `/en/` 与 `/`：en 页无中文 UI 串（专有名词例外），博主区块与经典版入口不出现，精选 / 全量切换、搜索、来源筛选、今天值得做都能用；`?data=` 覆盖仍生效；zh 页与改前逐像素无差异（截图对比）。
- `check_i18n_site.py` 通过：hreflang 互指含自身，sitemap URL 文件存在，JSON 键一致。
- 回填后抽 20 条英文理由人工看质量，记录到 WORKLOG。
- Actions 一次运行耗时增幅在 20% 以内（对比最近 3 次运行）。
- Search Console 提交 /en 只作上线后观察，不作结项条件。

## 上线与回滚

- 合并进 master 即生效（Vercel 自动部署，Actions 下一轮写 en 字段与 feed-en）。
- 回滚：revert 该 PR；`data/en-cache.json` 留着无害。`/en/` 文件删掉即下线，中文站不受影响。
- push、PR、合并都等卡尔下指令。
