# AI News Radar — 配置与参数手册 (Config Reference)

> 适用文件:`scripts/update_news.py`、`.github/workflows/update-news.yml`
>
> **核心原则:** 除了 **API 密钥**(必须放 GitHub Secrets),几乎所有可调参数都已写进代码常量。改一行常量即可,**不用再去 GitHub 配变量**。
>
> 下面每一项都标了「**改哪里**」=「文件 + 常量名(约第几行)」。⚠️ 行号会随代码改动漂移,**请以「常量名」为准**,在文件里搜索常量名最稳妥。

---

## 1. 一分钟总览(给老板看)

系统每 30 分钟自动抓取过去一段时间的 AI 资讯,来源包括官方源、AI 媒体、RSS 订阅,以及三个**付费社交源**(X、抖音、小红书)。当前生效的关键设置:

| 维度 | 当前值 | 含义 |
|---|---|---|
| 运行频率 | **每 30 分钟** | GitHub Actions 定时任务 |
| 付费源开关逻辑 | **有 key 就自动开** | 密钥在 = 抓取;`ENABLED=0` = 急停 |
| 每个付费源每日上限 | **20 条/天** | 成本保护 |
| 抖音 / 小红书 — 排序 | **最多点赞** | |
| 抖音 / 小红书 — 时间窗 | **最近 4 天** | |
| 抖音 / 小红书 — 笔记类型 | **不限**(视频+图文+直播) | |
| 抖音 / 小红书 — 关键词 | AI 相关词 | `AI, 人工智能, 大模型, OpenAI, Claude, Agent, AI工具` |
| X(SocialData)— 内容 | 中英 AI 关键词 + KOL 精选列表 | |

---

## 2. 数据源开关逻辑(以 API key 为主)

**规则:有密钥就自动抓;`ENABLED=0` 是急停开关;没密钥永不抓。**

| 情况 | 结果 |
|---|---|
| 有 key,`ENABLED` 没设 | ✅ 自动抓取(默认开) |
| 有 key,`ENABLED=0` | ⛔ 急停(连 FORCE_RUN 也压不过) |
| 没 key | ⛔ 永不抓取 |

- **改哪里(逻辑本身):** `scripts/update_news.py` → 函数 `env_flag_default`(约第 3017 行)。一般不用动。
- **急停某个源:** 去 GitHub → Settings → Secrets and variables → Actions → Variables,把 `SOCIALDATA_ENABLED` / `TIKHUB_ENABLED` / `X_API_ENABLED` 设成 `0`。

---

## 3. 抖音(TikHub Douyin)参数

| 参数 | 当前值 | 可选值 | 改哪里(常量名) |
|---|---|---|---|
| 排序 | 最多点赞 | `0`=综合 `1`=最新 `2`=最多点赞 | `TIKHUB_DOUYIN_SORT_TYPE`(约 223 行) |
| 时间窗(API 档位) | 一周内 | `0`不限 `1`一天内 `7`一周内 `180`半年内 | `TIKHUB_DOUYIN_PUBLISH_TIME`(约 224 行) |
| **真实时间窗** | **最近 4 天** | 任意天数(整数) | `TIKHUB_RECENCY_DAYS`(约 219 行) |

> ⚠️ **关于「4 天」:** 抖音/小红书的发布时间筛选**只有** 不限/一天内/一周内/半年内 这几档,**没有「4 天」这一档**。所以我们让 API 取最接近的「一周内」,再在代码里精确砍到 4 天(`TIKHUB_RECENCY_DAYS`)。想改成 3 天 / 5 天,只改这一个数字即可,两个平台同时生效。

---

## 4. 小红书(TikHub Xiaohongshu)参数

| 参数 | 当前值 | 可选值 | 改哪里(常量名) |
|---|---|---|---|
| 排序 | 最多点赞 | `popularity_descending`=最多点赞/最热 · `time_descending`=最新 · `general`=综合 | `TIKHUB_XHS_SORT`(约 230 行) |
| 笔记类型 | 不限 | `不限` / `视频` / `图文` | `TIKHUB_XHS_NOTE_TYPE`(约 231 行) |
| 时间窗(API 档位) | 一周内 | `不限` / `一天内` / `一周内` / `半年内` | `TIKHUB_XHS_TIME_FILTER`(约 232 行) |
| **真实时间窗** | **最近 4 天** | 同抖音,共用 | `TIKHUB_RECENCY_DAYS`(约 219 行) |

> ⚠️ **待确认:** 小红书「最多点赞」的排序代号我设的是 `popularity_descending`(最可能值),但 TikHub 官方文档是动态网页、抓不到原文,我没能 100% 实测。**本地用你的 key 跑一次确认即可**:
> ```
> python scripts/probe_tikhub.py --platforms xiaohongshu --max-results 5
> ```
> 看输出里 `diagnostics.requests` 的 `request_error_count` 是否为 0、有没有小红书条目回来。若被拒,把 `TIKHUB_XHS_SORT` 改成 `"最多点赞"` 再试。代码是分接口容错的,就算这个值不对也不会让整个源崩。
>
> **搜索范围(已看过/未看过/已关注)和 位置距离(同城/附近)** 是小红书 App 里绑定登录账号和定位的个性化筛选,**TikHub 公共 API 不开放**,所以是「不限」=我们根本不发送这两个参数,无需配置。

---

## 5. 抖音 / 小红书 共用参数

| 参数 | 当前值 | 改哪里(常量名) |
|---|---|---|
| 搜索关键词 | `AI,人工智能,大模型,OpenAI,Claude,Agent,AI工具` | `TIKHUB_DEFAULT_QUERY`(约 210 行) |
| 抓哪些平台 | `douyin,xiaohongshu` | `TIKHUB_DEFAULT_PLATFORMS`(约 211 行) |
| 每日上限(条) | 20 | `TIKHUB_DEFAULT_MAX_RESULTS`(约 212 行) |
| 真实时间窗(天) | 4 | `TIKHUB_RECENCY_DAYS`(约 219 行) |

---

## 6. X / Twitter(SocialData)参数

SocialData 同时跑两路:① 中英关键词搜索发现新声音;② 一个精选 KOL 列表(按账号身份稳定追踪,自动过滤转推/回复/机器人)。

| 参数 | 当前值 | 改哪里(常量名) |
|---|---|---|
| 关键词搜索 query | 中英 AI 词(见下) | `SOCIALDATA_DEFAULT_QUERY`(约 197 行) |
| 关键词搜索每日上限 | 20 | `SOCIALDATA_DEFAULT_MAX_RESULTS`(约 198 行) |
| KOL 列表 ID | `1695376776867062037` | `SOCIALDATA_LIST_ID_DEFAULT`(约 204 行) |
| KOL 列表每次最多取 | 50 | `SOCIALDATA_LIST_DEFAULT_MAX_RESULTS`(约 205 行) |
| KOL 列表排除账号 | 无 | `SOCIALDATA_LIST_DEFAULT_EXCLUDE`(约 206 行,逗号分隔 handle) |
| 时间窗(最近 N 天) | 最近 4 天 | `SOCIALDATA_RECENCY_DAYS`(约 212 行) |
| KOL 列表分页硬上限 | 10 页 | `SOCIALDATA_LIST_MAX_PAGES`(约 209 行) |

> 成本口径(已修正):SocialData 一次跑两路——搜索(≤20)+ KOL 列表(≤50),所以每次最多约 **70 次读取**,成本上限已把列表算进去。计费按**实际读取的原始推文数**(列表会丢掉转推/回复,原始读取数 > 入库数);分页有 10 页硬上限,防止失控扣费。

> 当前关键词:`(AI OR "artificial intelligence" OR LLM OR "large language model" OR 人工智能 OR 大模型 OR 大语言模型 OR AIGC OR 智能体 OR Agent) (lang:en OR lang:zh) -filter:retweets`

---

## 7. X API(官方接口,默认未用)

官方 X API 默认关闭(没配 `X_BEARER_TOKEN`)。参数:`X_API_DEFAULT_QUERY`(约 192 行)、`X_API_DEFAULT_MAX_RESULTS`(约 193 行)。

---

## 8. 抓取量、调度与成本

| 参数 | 当前值 | 改哪里 |
|---|---|---|
| 运行频率 | 每 30 分钟 | `.github/workflows/update-news.yml` → `cron: "*/30 * * * *"`(第 6 行) |
| 付费源运行间隔 | 24 小时一次 | `PAID_SOURCE_DEFAULT_INTERVAL_HOURS`(约 188 行) |
| 主时间窗 | 24 小时 | workflow 里 `--window-hours 24`(命令行参数) |
| 归档保留 | 21 天 | workflow 里 `--archive-days 21` |
| SocialData 每次最多读取 | ~70 条(搜索 20 + 列表 50) | `SOCIALDATA_DEFAULT_MAX_RESULTS` / `SOCIALDATA_LIST_DEFAULT_MAX_RESULTS` / `SOCIALDATA_LIST_MAX_PAGES` |

> 付费源虽然每 30 分钟有机会跑,但「24 小时间隔门」保证每天只真正花一次钱。

---

## 9. GitHub 上还需要配什么(只剩密钥 + 急停开关)

代码里搞不定、**必须**留在 GitHub 的,只有这些:

**Secrets(密钥,绝不能写进代码):**
`SOCIALDATA_API_KEY`、`TIKHUB_API_KEY`、`X_BEARER_TOKEN`、`AGENTMAIL_API_KEY`、`AGENTMAIL_INBOX_ID`、`FOLLOW_OPML_B64`

**Variables(可选,只当急停开关用):**
`SOCIALDATA_ENABLED`、`TIKHUB_ENABLED`、`X_API_ENABLED` —— 不设=默认开;设 `0`=关。

AgentMail 另有本地/私有运行变量：`EMAIL_DIGEST_ENABLED=1` 打开邮箱摘要，`AGENTMAIL_PROVIDER=agently_cli` 使用已授权的 QQ `agently-cli message +list`，`EMAIL_DIGEST_INCLUDE_IN_RADAR=1` 才把 metadata-only 邮件摘要作为 `agentmail` 源加入主 Radar 数据。

其余所有调参(query / 排序 / 时间窗 / 每日上限 / 间隔 / 平台)**全部已搬进代码常量,GitHub 上不用再配**。

---

## 10. Top 3 / 伯乐精选 是怎么挑的

「Top Signals(今日 Top 3)」**不是**从该栏目的全部候选里选,而是从一个全站统一、**最多 20 条**的精选「故事池」(`data/daily-brief.json`)里,再筛到当前栏目。这就是为什么自媒体/研究栏目有时只显示 1 条——它们大多是单来源、低分,进不了这 20 条。

**入选门槛**(`story_passes_brief_gate`,理念是"宁缺毋滥"):一条故事要进精选池,必须满足其一:
- **来源数 ≥ 2**(多源印证),或
- **评分 ≥ 0.72**(`BRIEF_SCORE_GATE`,约 4721 行)

**评分公式**(`calculate_item_importance`):
`分 = 编辑权重×0.3 + 来源层级×0.22 + AI相关×0.2 + 新近度×0.18 + 热度×0.1`
来源层级权重:官方 1.0 > AI HOT 0.78 > 自媒体(抖音/小红书)0.48 > X 0.45。自媒体单条很难过线,所以 Top 3 里少。

**想让自媒体/研究 Top 3 更满**:可调低门槛 `BRIEF_SCORE_GATE`,或改前端逻辑(`assets/app.js` 第 ~1529 行)在精选故事不足 3 条时用本栏目自有内容补齐。(此项尚未实施,需要的话可单独做。)

---

## 11. 「我想改 X」速查表

| 我想… | 改这里 |
|---|---|
| 改抖音/小红书的**时间窗**(天数) | `TIKHUB_RECENCY_DAYS`(约 219 行)一个数字 |
| 改抖音/小红书的**排序** | `TIKHUB_DOUYIN_SORT_TYPE` / `TIKHUB_XHS_SORT` |
| 改抖音/小红书**只要图文或只要视频** | `TIKHUB_XHS_NOTE_TYPE`(小红书);抖音改 `content_type` |
| 改抖音/小红书**搜索关键词** | `TIKHUB_DEFAULT_QUERY`(约 210 行) |
| 改**每日抓取上限** | `TIKHUB_DEFAULT_MAX_RESULTS` / `SOCIALDATA_DEFAULT_MAX_RESULTS`(约 212 / 198 行) |
| 改 **X 关键词 / KOL 列表** | `SOCIALDATA_DEFAULT_QUERY` / `SOCIALDATA_LIST_ID_DEFAULT`(约 197 / 204 行) |
| 改 **SocialData 时间窗**(天) | `SOCIALDATA_RECENCY_DAYS` |
| **临时关掉**某个付费源 | GitHub Variables 把对应 `*_ENABLED` 设 `0` |
| 改**运行频率** | workflow 第 6 行 `cron` |
| 改**付费源每天跑几次** | `PAID_SOURCE_DEFAULT_INTERVAL_HOURS`(约 188 行) |

---

*改完代码后,跑一遍测试确认无误:`python -m unittest tests.test_topic_filter -q`*
