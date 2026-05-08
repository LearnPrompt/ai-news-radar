<div align="center">

# 伯乐Skill

> 从一堆信源里选出千里马。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](../../LICENSE)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Skill-blueviolet)](https://claude.ai/code)
[![GitHub Pages](https://img.shields.io/badge/GitHub%20Pages-Ready-green)](https://pages.github.com/)

<br>

**伯乐Skill is Scout Skill for AI News Radar.**

它帮你判断哪些 AI 信息源值得长期追踪，并把它们接入一个自动更新的 AI 日报网站。

<br>

[在线示例](https://learnprompt.github.io/ai-news-radar/) · [安装](#安装) · [安装后第一句话](#安装后第一句话) · [快速录入信息源](#快速录入信息源) · [伯乐会选什么](#伯乐Skill会选什么) · [工作原理](#工作原理)

</div>

---

## 它解决什么问题

一到假期，信息焦虑就会变严重。

不是没东西看，而是东西太多了。

RSS里一堆更新，X上有人分享新工具，飞书知识库里还有资料，聚合站每天刷出几十页。真正的问题变成了：我到底该看什么？哪些源值得长期追？哪些源只是制造噪音？怎么把这些东西变成每天真的能看的AI日报？

AI News Radar原本是给自己用的AI日报网站，专门覆盖那些平时自然信息流里看不到的信息源。

但用了一段时间后，新的问题来了：如果一直往里面加信息源，它很快就会变成一天几千条、几万条更新。看起来很强，实际上还是看不完。

所以这次没有继续简单加源，而是在AI News Radar上做了一个Skill。

它叫：**伯乐Skill**。

伯乐Skill不是什么源都加。它只做一件事：

**从乱七八糟的信源里，选出值得长期追踪的千里马。**

---

## 在线示例

你可以先看公开版：

https://learnprompt.github.io/ai-news-radar/

这个页面会持续更新AI、开发者、官方博客、技术聚合站和公开日报类来源。

它不是最终答案，而是一个可以fork、可以改、可以接入你自己信息源的起点。

---

## 安装

如果你只是想看日报，不需要安装，直接打开在线页面即可：

```text
https://learnprompt.github.io/ai-news-radar/
```

如果你想做自己的版本：

```bash
git clone https://github.com/LearnPrompt/ai-news-radar.git
cd ai-news-radar
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/update_news.py --output-dir data --window-hours 24
python -m http.server 8080
```

然后打开：

```text
http://localhost:8080
```

如果你在Claude Code、Codex或其他支持Skill的Agent里使用，请让Agent读取：

```text
skills/ai-news-radar/SKILL.md
```

---

## 安装后第一句话

安装或fork之后，不知道怎么开始，就直接对Agent说：

```text
请使用伯乐Skill，先问我要信息源清单，然后帮我判断每个信源该用 RSS、OPML、公开 feed、静态页面、Jina 兜底、AgentMail 邮箱还是跳过。目标是部署一个不需要服务器、能用 GitHub Actions 自动更新的 AI 日报网站。不要把任何 API Key、cookies、token、真实 OPML、邮箱正文或私有邮件内容写入仓库。
```

这句话的作用是把Agent拉回正确路线：先判断来源，再决定接入方式，不要一上来乱抓网页。

---

## 快速录入信息源

你可以直接把信息源丢给伯乐Skill。

```text
我想用伯乐Skill搭一个自己的AI日报网站。

这是我常看的信息源：

1. https://openai.com/news/
2. https://www.anthropic.com/news
3. https://huggingface.co/blog
4. https://news.ycombinator.com/
5. 一个OPML文件：feeds/follow.opml
6. 一个AgentMail收件箱：newsletter@你的inbox.agentmail.to
7. 一些我关注的X账号：karpathy、sama、nearcyan

请你帮我完成：

1. 判断每个源适合用RSS、OPML、公开页面、GitHub feed、AgentMail邮箱，还是需要跳过。
2. 能用RSS/OPML的优先用RSS/OPML。
3. AgentMail只作为私有进阶源，默认不发布完整正文。
4. 不要把需要登录、cookies、token的来源作为默认公共源。
5. 把适合公开内置的源加入项目。
6. 把私人订阅源放进本地OPML、AgentMail或GitHub Secret方案。
7. 本地跑一次数据生成。
8. 如果通过验证，指导我部署到GitHub Pages。
```

如果你想让用户按表格录入，可以用这个版本：

```text
请使用伯乐Skill，帮我搭建自己的AI日报网站。

你先让我按下面格式填写信息源：

| 名称 | URL或账号 | 类型 | 是否私人 | 我为什么想看它 |
|---|---|---|---|---|
| OpenAI News | https://openai.com/news/ | 网站/RSS | 否 | 官方更新 |
| Karpathy | @karpathy | X账号 | 否 | AI观点 |
| 我的RSS列表 | follow.opml | OPML | 是 | 个人订阅 |
| Newsletter收件箱 | AgentMail inbox | 邮箱 | 是 | 产品周报和newsletter |

填完后，请你帮我判断哪些能直接接入、哪些应该进入OPML、哪些不适合接入、哪些需要Jina兜底、哪些需要以后用私有集成处理。然后生成本地日报数据，并指导我部署到GitHub Pages。
```

---

## 伯乐Skill会选什么

伯乐Skill主要会选五类东西。

| 能力 | 说明 |
|---|---|
| 信息源判断 | 判断一个网站适合RSS、OPML、静态解析、公开JSON，还是不适合接入 |
| 去重和过滤 | 把聚合站、日报、RSS里的重复信息压下去 |
| AI信号识别 | 区分真正的AI相关内容和只是蹭到关键词的噪音 |
| 源健康检查 | 看每个源是否还活着、每天贡献多少信息 |
| 静态部署 | 不买服务器，用GitHub Actions和GitHub Pages自动更新日报网站 |

伯乐Skill的目标不是让你看更多信息。

它的目标是让你少看垃圾信息。

---

## 支持的信息源类型

| 类型 | 推荐程度 | 说明 |
|---|---|---|
| 官方RSS / Atom | 高 | 最稳定，优先使用 |
| OPML | 高 | 适合批量导入个人RSS订阅 |
| 公开GitHub生成Feed | 高 | 适合Follow Builders这类公开数据源 |
| 公开Newsletter归档 | 中 | 优先用公开页面或公开feed |
| 聚合站分页 | 中 | 可覆盖盲区，但需要去重和过滤 |
| X / Twitter | 中低 | 优先使用稳定的公开中间feed，不建议默认依赖账号登录 |
| 飞书知识库 | 进阶 | 适合个人知识库场景，不建议作为公共默认源 |
| AgentMail邮箱 | 进阶 | 适合newsletter、产品周报、GitHub通知；默认关闭，只输出脱敏摘要 |
| 需要登录的网站 | 谨慎 | 会引入cookies、额度和稳定性问题，不建议默认接入 |

---

## 为什么不用Agent一直跑

AI日报不应该每次都依赖Agent临时执行。

伯乐Skill采用的是更稳定的路径：

```text
信息源 → 抓取 → 去重 → 过滤 → 结构化JSON → GitHub Pages网页
```

数据更新可以交给GitHub Actions定时运行。

这意味着：

- 不需要买服务器
- 不需要每天手动运行
- 不需要每次消耗Agent额度
- 手机、iPad、电脑都能打开
- fork之后可以变成你自己的日报站

Agent负责帮你判断、配置和维护信息源。真正的日报更新，交给自动化流程。

---

## 工作原理

伯乐Skill处理信息源时，会做四步。

**1. 来源分类**

先判断来源属于哪一类：

```text
RSS / Atom
OPML
公开GitHub feed
公开网页
聚合站分页
X桥接源
私有知识库
AgentMail邮箱
需要登录的来源
```

不同来源走不同策略。能用RSS就不用网页解析。能用公开feed就不重写爬虫。AgentMail只作为私有邮箱情报入口，适合newsletter和产品周报，不作为公共默认源。需要登录和cookies的来源，不放进公共默认配置。

**2. 抓取和结构化**

把不同来源抓到的数据统一整理成结构化JSON。

这样Agent可以读，网页也可以读。

**3. 去重和AI过滤**

对重复标题、重复链接、聚合站转载进行去重。

同时区分AI强相关、全量信息和原始覆盖池。宽泛词不会单独决定一条新闻是不是AI新闻。比如`agent`可能是AI Agent，也可能只是普通代理。

**4. 静态部署**

最后输出到`data/*.json`，再通过GitHub Pages展示。

默认数据由GitHub Actions定时更新。

---

## 源健康和信息密度

伯乐Skill不是只会加源，也会帮你淘汰源。

页面会展示源健康和信息密度，比如：

```text
源是否正常
最近是否更新
每天贡献多少条信息
AI强相关内容占比
```

一个简单的淘汰标准：

```text
如果一个源连续一周平均每天贡献不到1条有价值信息，就可以考虑移除。
```

这比无限加源更重要。

因为AI日报的敌人不是信息不够，而是噪音太多。

---

## OPML支持

如果你是RSS老玩家，可以直接用OPML批量导入订阅源。

本地方式：

```bash
cp feeds/follow.example.opml feeds/follow.opml
# 把你的OPML内容放进 feeds/follow.opml
python scripts/update_news.py --output-dir data --window-hours 24 --rss-opml feeds/follow.opml
```

注意：

```text
feeds/follow.opml 是你的私人订阅文件，不要提交到公开仓库。
```

如果要部署到GitHub Actions，建议把OPML转成base64，放进GitHub Secret：

```bash
base64 < feeds/follow.opml | pbcopy
```

然后在仓库Secrets里添加：

```text
FOLLOW_OPML_B64
```

---

## AgentMail邮箱情报入口

如果你希望Newsletter、产品周报、GitHub通知进入日报链路，可以创建一个专门给AI日报使用的AgentMail收件箱。

本地方式：

```bash
export EMAIL_DIGEST_ENABLED=1
export AGENTMAIL_API_KEY="你的AgentMail API Key"
export AGENTMAIL_INBOX_ID="你的Inbox ID"
python scripts/update_news.py --output-dir data --window-hours 24
```

安全默认值：

```text
默认不启用AgentMail。
默认只调用 GET /v0/inboxes/{inbox_id}/messages。
默认不读取 /raw，不读取 text/html 正文。
默认只输出脱敏后的标题、预览片段、发件域名、链接、附件数量和时间。
GitHub Actions默认不会提交 data/email-digest.json；只有设置 EMAIL_DIGEST_PUBLISH=1 才会提交。
```

建议把AgentMail理解成“AI日报的专用情报收件箱”，不是读取你的私人邮箱。

---

## 安全边界

伯乐Skill默认不会要求你提供API Key。

公开仓库里也不应该出现：

```text
API Key
cookies
token
.env
真实OPML订阅文件
邮箱正文或私有邮件内容
AgentMail API Key或Inbox ID
浏览器登录态
```

推荐做法：

- 公共默认源只使用稳定公开来源
- 私人订阅放进OPML
- AgentMail只作为私有进阶源，默认关闭
- OPML不要提交到仓库
- GitHub Actions里用Secret保存私有配置
- 需要登录的网站不要作为默认抓取源

一个AI日报项目，自己用可以粗糙一点。一旦开源，就要替fork用户提前挡坑。

---

## 适合谁

伯乐Skill适合这些人：

- 每天需要追AI新闻的人
- 有一堆RSS订阅但看不过来的人
- 想把X、博客、聚合站、Newsletter统一到一个页面的人
- 想fork一个自己的AI日报站的人
- 想让Codex或Claude Code长期维护信息源的人
- 想做自媒体选题雷达的人

不适合这些场景：

- 想实时监控所有新闻
- 想抓取需要登录的网站
- 想把私人邮箱、AgentMail API Key和cookies直接塞进公开项目
- 想用它替代完整RSS阅读器

伯乐Skill不是万能信息中台。它更像一个AI信号雷达。

---

## 仓库结构

```text
ai-news-radar/
├── index.html
├── assets/
│   ├── app.js
│   └── styles.css
├── data/
│   ├── latest-24h.json
│   ├── latest-24h-all.json
│   ├── source-status.json
│   ├── email-digest.json  # 可选，AgentMail开启后生成
│   └── archive.json
├── feeds/
│   ├── follow.example.opml
│   └── social-x.example.opml
├── scripts/
│   └── update_news.py
├── docs/
│   ├── SOURCE_COVERAGE.md
│   ├── GPT_HANDOFF.md
│   └── V2_PRODUCT_BRIEF.md
└── skills/
    └── ai-news-radar/
        ├── SKILL.md
        ├── README.md
        └── references/
```

---

## English

> Find the thoroughbred sources before they enter the radar.

**Scout Skill** is the English-facing name for 伯乐Skill in AI News Radar. It helps you choose high-signal AI sources worth tracking instead of blindly adding every noisy feed.

It classifies and ingests sources from RSS, OPML, public websites, GitHub-generated feeds, newsletters, X-related feeds, and private knowledge bases, then deploys the result as a GitHub Pages site.

It does not try to know everything.

It only helps AI News Radar find sources worth tracking.

**Live demo:**

https://learnprompt.github.io/ai-news-radar/

**Repository:**

https://github.com/LearnPrompt/ai-news-radar

### Quick prompt after install

```text
Use Scout Skill to help me build my own AI daily radar.

First read README.md, docs/SOURCE_COVERAGE.md, docs/GPT_HANDOFF.md, and skills/ai-news-radar/SKILL.md.

Then ask me for my source list: websites, RSS feeds, OPML files, X accounts, newsletters, GitHub projects, or private knowledge bases.

For each source, classify whether it should be handled as RSS, OPML, public feed, static page, Jina fallback, optional private integration, or skipped.

Prefer stable public sources. Do not commit API keys, cookies, tokens, private OPML files, or email contents.

After classification, generate the local data, verify the JSON output, and guide me through GitHub Pages deployment.
```

---

## 背后的故事

伯乐Skill是在一次假期信息焦虑里做出来的。

我一边自驾，一边用语音把需求丢给Codex。想到一个源、一个过滤规则、一个页面问题，就让Agent继续改。

最后它变成了一个很适合AI时代的东西：不是让AI帮我多看一点信息，而是让AI帮我少看一点垃圾信息。

所以它叫伯乐Skill：先选千里马，再上雷达。

它看的不是天下大事。它先看的，是哪些信源值得进入雷达。

---

## License

MIT — 随便用，随便改，随便让它帮你选千里马。

---

<div align="center">

**RSS阅读器**帮你订阅信息。  
**AI News Radar**帮你展示AI信号。  
**伯乐Skill**帮你判断哪些信源是值得长期追踪的千里马。

<br>

*从一堆信源里选出千里马。*

</div>
