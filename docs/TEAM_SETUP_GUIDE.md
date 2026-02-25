# AI News Radar - 团队协作指南

本指南汇总了四个专业团队的研究成果，帮助你在 GitHub 上合理部署和管理项目。

---

## 目录

1. [GitHub Actions 执行规则和最佳实践](#1-github-actions-执行规则和最佳实践)
2. [GitHub Secrets 管理指南](#2-github-secrets-管理指南)
3. [GitHub 通知与 Telegram 集成](#3-github-通知与-telegram-集成)
4. [API 密钥申请指南](#4-api-密钥申请指南)
5. [快速开始清单](#5-快速开始清单)

---

## 1. GitHub Actions 执行规则和最佳实践

### 当前工作流配置

文件：`.github/workflows/update-news.yml`

**当前状态：**
- 频率：每 30 分钟执行一次
- 无并发控制
- 无超时配置
- 无依赖缓存
- 每次提交约 48 MB 数据

### 发现的问题

| 问题 | 严重性 | 影响 |
|------|--------|------|
| 无并发控制 | 中 | 多个工作流可能同时执行，资源浪费 |
| 30分钟频率过高 | 中 | 超额消耗免费额度，大部分时间获取重复数据 |
| 无依赖缓存 | 低 | 每次浪费 30-60 秒安装依赖 |
| 提交大数据文件 | 高 | 仓库膨胀，克隆时间增加 |
| 无超时设置 | 低 | 失败的工作流可能运行长达 6 小时 |
| aihot 源持续失败 | 中 | 每次执行浪费请求时间 |

### 推荐的 Cron 表达式

针对北京时间（UTC+8）的优化：

```yaml
# 推荐：每 2 小时执行一次（24 次/天 vs 48 次/天）
schedule:
  - cron: '0 */2 * * *'  # 每 2 小时

# 或仅在工作时间每 30 分钟（北京时间 8 AM - 10 PM）
schedule:
  - cron: '*/30 0-14 * * *'  # 工作时间每 30 分钟
  - cron: '0 */3 * * *'     # 夜间每 3 小时

# 或核心时段高频更新
schedule:
  - cron: '0 0,6,12,18 * * *'  # 每天 4 次（8AM, 2PM, 8PM, 2AM 北京时间）
```

### 改进后的工作流配置

```yaml
name: Update AI News Snapshot

on:
  workflow_dispatch:  # 手动触发
  schedule:
    - cron: '0 */2 * * *'  # 每 2 小时（推荐）

# 并发控制：防止多个工作流同时执行
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true  # 取消之前的运行

permissions:
  contents: write

jobs:
  update:
    runs-on: ubuntu-latest
    timeout-minutes: 15  # 添加超时限制

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      # 添加依赖缓存
      - name: Cache pip dependencies
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-${{ hashFiles('**/requirements.txt') }}

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: 'pip'  # 内置 pip 缓存

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      # OPML 配置（可选）
      - name: Prepare OPML
        env:
          FOLLOW_OPML_B64: ${{ secrets.FOLLOW_OPML_B64 }}
        run: |
          mkdir -p feeds
          if [ -n "$FOLLOW_OPML_B64" ]; then
            echo "$FOLLOW_OPML_B64" | base64 --decode > feeds/follow.opml
            fi

      # 数据更新
      - name: Update data
        run: |
          if [ -f feeds/follow.opml ]; then
            python scripts/update_news.py --output-dir data --window-hours 24 --rss-opml feeds/follow.opml
          else
            python scripts/update_news.py --output-dir data --window-hours 24

      # 检查变更（避免不必要的提交）
      - name: Check for changes
        id: check_changes
        run: |
          if git diff --quiet -- data/; then
            echo "no_changes=true" >> $GITHUB_OUTPUT
          else
            echo "no_changes=false" >> $GITHUB_OUTPUT

      # 仅在有变更时提交
      - name: Commit and push
        if: steps.check_changes.outputs.no_changes == 'false'
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add data/
          git commit -m "chore: update ai news snapshot"
          git push
```

### 优化效果预估

| 改进 | 预期节省 |
|------|----------|
| 频率从 30 分钟 → 2 小时 | 50% 的 Actions 分钟数 |
| 添加依赖缓存 | 每次节省 30-60 秒 × 48 次 = ~40 分钟/天 |
| 条件性提交 | 避免 60-70% 的无效提交 |
| 添加超时限制 | 防止资源浪费 |

---

## 2. GitHub Secrets 管理指南

### 项目需要的 API 密钥

| 源 | Secret 名称 | 说明 |
|----|-------------|------|
| Reddit | `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` | 用于获取 r/artificial 等版块数据 |
| Product Hunt | `PRODUCT_HUNT_API_KEY` | 用于获取 AI 工具发布数据 |
| GitHub | `GITHUB_TOKEN` | 用于获取 GitHub Trending 仓库数据 |

### Secrets 层级

1. **Repository Secrets**（推荐用于本项目）
   - 位置：仓库设置 → Secrets and variables → Actions
   - 限制：每个仓库最多 100 个 secrets
   - 优点：简单直接，推荐使用
   - 缺点：不能跨仓库共享

2. **Organization Secrets**（可选）
   - 位置：组织设置 → Secrets and variables → Actions
   - 限制：每个组织最多 1000 个 secrets
   - 优点：可以跨多个仓库共享
   - 缺点：需要组织账户

3. **Environment Secrets**（用于环境隔离）
   - 位置：仓库设置 → Environments → [环境名] → Environment secrets
   - 优点：可以为不同环境设置不同的密钥
   - 推荐：用于 production/staging 分离

### 创建 Secrets 步骤

#### 步骤 1：获取各 API 密钥

**Reddit API**
1. 访问 https://www.reddit.com/prefs/apps
2. 点击 "create app" 或 "create application"
3. 填写：
   - name: `AI News Radar Script`
   - app type: 选择 `script`
   - about url: `https://github.com/your-username/ai-news-radar`
   - description: `AI news aggregation from ML subreddits`
   - redirect uri: `http://localhost:8080`（或留空）
   - [x] json: **必须勾选**
4. 点击 "create app"
5. 记录 CLIENT_ID（14个字符）和 CLIENT_SECRET（27个字符）

**Product Hunt API**
1. 访问 https://api.producthunt.com/v2/docs
2. 注册账号并登录
3. 点击 "Applications" 或 "Create App"
4. 填写：
   - name: `AI News Radar`
   - description: `AI news aggregation dashboard`
   - redirect uri: `http://localhost:8080`
5. 点击创建后，找到 "Developer Token" 选项
6. 生成并复制 token

**GitHub Token**
1. 访问 https://github.com/settings/tokens
2. 点击 "Generate new token"
3. 选择类型：
   - **推荐**：Fine-grained token（更安全）
   - **备选**：Classic token
4. 配置：
   - name: `AI News Radar - GitHub Trending`
   - expiration: 选择 `30 days` 或 `90 days`
   - Repository access: 选择 `Only select repositories`
   - 选择要访问的仓库（或选择所有仓库）
   - Permissions（推荐）：
     - [x] Contents: `Read only`
     - [ ] Pull requests
     - [ ] Issues
     - [ ] Actions
     - [x] Metadata: `Read only`
5. 点击 "Generate token"
6. **立即复制 token**（只显示一次）

#### 步骤 2：添加到 GitHub Secrets

1. 进入仓库页面：`https://github.com/your-username/ai-news-radar`
2. 点击 `Settings` 标签
3. 点击左侧 `Secrets and variables`
4. 点击 `Actions` 标签
5. 点击 `New repository secret`
6. 创建以下 5 个 secrets：

| Name | Value | 说明 |
|------|-------|------|
| `REDDIT_CLIENT_ID` | `14字符字符串` | 从 Reddit 复制 |
| `REDDIT_CLIENT_SECRET` | `27字符字符串` | 从 Reddit 复制 |
| `PRODUCT_HUNT_API_KEY` | `60+字符token` | 从 Product Hunt 复制 |
| `GITHUB_TOKEN` | `ghp_xxxxx...` | 从 GitHub 复制 |
| `FOLLOW_OPML_B64` | `base64编码` | 可选，RSS OPML 文件 |

7. 点击 `Add secret`

#### 步骤 3：更新代码使用 Secrets

修改 `scripts/new_sources.py` 中的函数，从环境变量读取密钥：

```python
import os

# Reddit
def fetch_reddit_ai(session: requests.Session, now: datetime) -> list[RawItem]:
    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")

    if not client_id or not client_secret:
        # 如果没有配置密钥，跳过此源
        return []

    # 使用密钥进行认证...
    # 实现代码在 new_sources.py 中

# Product Hunt
def fetch_product_hunt(session: requests.Session, now: datetime) -> list[RawItem]:
    api_key = os.environ.get("PRODUCT_HUNT_API_KEY")

    if not api_key:
        return []

    # 使用密钥进行请求...

# GitHub
def fetch_github_trending(session: requests.Session, now: datetime) -> list[RawItem]:
    token = os.environ.get("GITHUB_TOKEN")

    if not token:
        return []

    # 使用 token 进行 GraphQL 查询...
```

### 安全检查清单

- [ ] 从未加密渠道（邮件、Slack、聊天记录）获取密钥
- [ ] 密钥只存储在 GitHub Secrets 中
- [ ] 代码中不硬编码任何密钥
- [ ] `.env` 文件已添加到 `.gitignore`
- [ ] 使用最小权限原则（只请求必需的权限）
- [ ] 定期轮换密钥（每 30-90 天）
- [ ] 监控 GitHub Actions 日志中的密钥泄露

---

## 3. GitHub 通知与 Telegram 集成

### 推荐方案：appleboy/telegram-action

**理由：**
- 零配置，开箱即用
- 无需自建 Telegram Bot 服务
- 完善的维护（最后更新 2026 年）
- 支持条件执行（成功/失败时发送）
- 免费使用

### Telegram 通知设置步骤

#### 步骤 1：创建 Telegram Bot

1. 在 Telegram 中搜索 `@BotFather`
2. 发送 `/newbot` 命令
3. 填写 Bot 名称（必须以 `bot` 结尾）
4. 获取 Bot Token（格式：`123456789:AAHfiqksKZ8WmR2zSjiQ7_v4TMAKdiHm9T0`）
5. **保存**此 Token（只显示一次）

#### 步骤 2：获取 Chat ID

**方法 A：官方 API**
```bash
curl "https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates"
```
在返回的 JSON 中找到 `"chat":{"id":123456789}`

**方法 B：使用第三方 Bot**
在 Telegram 中搜索并启动 `@userinfobot`，发送 `/start`，复制你的 Chat ID

#### 步骤 3：添加 GitHub Secrets

1. 仓库设置 → Secrets and variables → Actions
2. 创建两个 secrets：
   - `TELEGRAM_BOT_TOKEN`: 你的 bot token
   - `TELEGRAM_CHAT_ID`: 你的 chat ID

#### 步骤 4：更新工作流

在 `.github/workflows/update-news.yml` 中添加通知步骤：

```yaml
      - name: Send Telegram Notification on Success
        if: success()
        uses: appleboy/telegram-action@master
        with:
          to: ${{ secrets.TELEGRAM_CHAT_ID }}
          token: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          format: markdown
          message: |
            ✅ AI News Radar Update Successful

            **Repository:** ${{ github.repository }}
            **Workflow:** ${{ github.workflow }}
            **Commit:** ${{ github.sha }}

            *Items Collected:* ${{ fromJson(steps.update.outputs.stats).items_in_24h }}

      - name: Send Telegram Notification on Failure
        if: failure()
        uses: appleboy/telegram-action@master
        with:
          to: ${{ secrets.TELEGRAM_CHAT_ID }}
          token: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          format: markdown
          message: |
            ❌ AI News Radar Update Failed

            **Repository:** ${{ github.repository }}
            **Workflow:** ${{ github.workflow }}
            **Commit:** ${{ github.sha }}

            *Please check to logs for details*

      - name: Send Source Status Report
        if: always()
        uses: appleboy/telegram-action@master
        with:
          to: ${{ secrets.TELEGRAM_CHAT_ID }}
          token: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          format: markdown
          message: |
            📊 AI News Radar Source Status

            **Successful:** ${{ fromJson(steps.status.outputs.stats).successful_sites }}/${{ fromJson(steps.status.outputs.stats).total_sources }}

            %{{ if fromJson(steps.status.outputs.stats).failed_sites != '' }}%
            ⚠️ *Failed Sources:*
            %{{ for site in fromJson(steps.status.outputs.stats).failed_sites }}%
            - *{{ site.site_name }}*
            %{{ endfor }}%
            %{{ endif }}%
```

### 通知模板示例

**成功通知：**
```
✅ AI News Radar 更新完成

📅 生成时间：2026-02-25 12:00 UTC
📊 数据源：14/17 成功
📰 总条目：1,622 条
⏱️ 执行耗时：32.5 秒
```

**失败通知：**
```
❌ AI News Radar 更新失败

📅 仓库：your-org/ai-news-radar
🔄 工作流：Update AI News Snapshot
💥 提交：abc123def
🔗 运行链接：https://github.com/your-org/ai-news-radar/actions/runs/1234567890

❌ 错误：HTTPConnectionError - Timeout exceeded
```

**源状态报告：**
```
📊 AI News Radar 源状态报告

✅ 正常源：13/17
❌ 失败源：1/17
  - aihot: 403 Forbidden

📰 本轮收集：1,622 条
🔍 零响应源耗时：32.5 秒
```

---

## 4. API 密钥申请指南

### Reddit API

**申请链接：** https://www.reddit.com/prefs/apps

**详细步骤：**
1. 登录 Reddit 账号（需要邮箱验证）
2. 访问 https://www.reddit.com/prefs/apps
3. 点击右上角 "create another app..."
4. 填写表单：
   ```
   name: AI News Radar Script
   type: script
   description: Automated AI news aggregator fetching from ML/AI subreddits
   about url: https://github.com/your-username/ai-news-radar
   redirect uri: http://localhost:8080
   [x] json
   ```
5. 点击 "create app"
6. 找到 "client ID"（14字符）和 "client secret"（27字符）
7. 安全保存这两个值

**权限说明：**
- 基础权限：`read`, `identity`, `mysubreddits`
- 推荐使用 `script` 类型而不是 `web app`（简化认证）

**限流：**
- 未认证：60 次/分钟
- OAuth 认证：600 次/分钟

**Token 刷新：**
- Access Token 1 小时后过期
- 需要在代码中实现 token 自动刷新逻辑

---

### Product Hunt API

**申请链接：** https://api.producthunt.com/v2/docs

**详细步骤：**
1. 注册 Product Hunt 账号（免费）
2. 登录后访问 API 文档页面或直接访问应用面板
3. 点击 "Create App" 或 "New Application"
4. 填写表单：
   ```
   name: AI News Radar
   description: AI news aggregation dashboard displaying trending AI tools
   redirect uri: http://localhost:8080
   scopes: public  # 推荐从 public 开始
   ```
5. 创建应用后，找到 "Developer Token" 选项
6. 生成 Developer Token
7. **立即复制 token**（只显示一次）

**权限说明：**
- `public`：只读公共数据
- `private`：访问用户数据（需要用户授权）
- `private + write`：完整访问（需要联系 hello@producthunt.com）

**限流：**
- 官方策略：基于使用量的合理限流
- 联系 support：hello@producthunt.com 可申请更高的限流

**Token 特点：**
- 不过期
- 可随时从面板撤销

---

### GitHub Token

**申请链接：** https://github.com/settings/tokens

**详细步骤：**
1. 访问 GitHub Settings → Developer settings
2. 找到 "Personal access tokens" 部分
3. 点击 "Generate new token (classic)" 或 "Fine-grained token"

**推荐：Fine-grained Token（更安全）**
1. 点击 "Generate new token"
2. 配置：
   ```
   Note: AI News Radar - GitHub Trending API
   Expiration: 90 days
   Resource owner: 选择你的账号
   Repository access:
     [x] Only select repositories（推荐）
     或选择特定仓库

   Permissions（只勾选必需的）:
     [x] Repository contents: Read-only
     [ ] Metadata: Read-only
     [ ] Pull requests: Read
     [ ] Issues: Read
   [ ] Actions: Read/Write
   [ ] Discussions: Read
   ```
3. 点击 "Generate token"
4. **立即复制** `ghp_xxxx...`（只显示一次）

**备选：Classic Token（简单）**
1. 切换到 "Tokens (classic)" 标签
2. 点击 "Generate new token (classic)"
3. 配置：
   ```
   Note: AI News Radar Classic
   Expiration: 90 days
   Scopes: 选择 `repo`（读写所有仓库权限）
   ```
4. 点击 "Generate token"

**限流：**
- 认证：5,000 次/小时
- 未认证：60 次/小时
- GraphQL：5,000 点/小时

**安全提示：**
- Fine-grained token 可以限制访问特定仓库，更安全
- Token 过期后会自动失效，需要重新生成
- 每个账号最多 50 个 fine-grained token

---

## 5. 快速开始清单

### 准备阶段

- [ ] 所有团队成员都有 GitHub 账号和仓库访问权限
- [ ] 所有团队成员都有 Telegram 账号
- [ ] 已阅读并理解 GitHub Actions 工作流配置
- [ ] 已阅读并理解 Secrets 管理指南

### Secrets 配置

- [ ] Reddit API 密钥已获取并存储到 GitHub Secrets
- [ ] Product Hunt API 密钥已获取并存储到 GitHub Secrets
- [ ] GitHub Token 已获取并存储到 GitHub Secrets
- [ ] Telegram Bot Token 已获取并存储到 GitHub Secrets
- [ ] Telegram Chat ID 已获取并存储到 GitHub Secrets

### 代码更新

- [ ] `scripts/new_sources.py` 已更新以使用环境变量
- [ ] `config/sources.yaml` 已更新（Reddit/Phunt/GitHub 源设置为 enabled）
- [ ] `.github/workflows/update-news.yml` 已应用所有优化：
  - [ ] 并发控制
  - [ ] 超时设置
  - [ ] 依赖缓存
  - [ ] 条件性提交
  - [ ] Telegram 通知步骤

### 测试阶段

- [ ] 本地测试 `python scripts/new_sources.py` 验证源函数工作
- [ ] 手动触发 GitHub Actions workflow_dispatch 测试
- [ ] 验证 Telegram 通知接收正常
- [ ] 检查 GitHub Actions 日志确认 secrets 正确读取

### 部署阶段

- [ ] 推送代码更改到 main 分支
- [ ] 观察首次自动化运行是否成功
- [ ] 验证 source-status.json 正确生成
- [ ] 验证 Telegram 通知内容符合预期

### 监控阶段

- [ ] 设置 GitHub Actions 工作流定期运行观察
- [ ] 监控 GitHub Actions 分钟使用量，确保在免费额度内
- [ ] 观察 Telegram 通知，及时发现失败

---

## 常见问题排查

### 问题：Workflow 运行失败但日志中不显示错误
**原因：** Secrets 配置错误或命名不匹配
**解决：**
```bash
# 在 workflow 中添加调试步骤
- name: Debug environment
  run: |
    echo "REDDIT_CLIENT_ID present: $( [ -n "$REDDIT_CLIENT_ID" ] && echo 'Yes' || echo 'No')"
```

### 问题：Telegram 通知没有收到
**排查：**
1. 检查 Bot Token 和 Chat ID 是否正确
2. 在 Telegram 中向 Bot 发送测试消息
3. 检查 GitHub Actions 日志确认通知步骤执行

### 问题：API 限流导致数据不完整
**解决：**
1. 实现请求队列和退避重试
2. 添加缓存减少 API 调用
3. 优化抓取频率

### 问题：aihot 源返回 403 错误
**当前状态：** 该源被禁止或需要代理
**解决方案：**
1. 在 `config/sources.yaml` 中禁用 aihot 源
2. 或联系 aihot.today 获取 API 访问权限
3. 或添加代理支持（通过环境变量配置）

---

## 附录：相关链接

- [GitHub Actions 官方文档](https://docs.github.com/cn/actions)
- [Cron 表达式生成器](https://crontab.guru/)
- [GitHub Marketplace](https://github.com/marketplace)
- [Reddit API 文档](https://www.reddit.com/dev/api/)
- [Product Hunt API 文档](https://api.producthunt.com/v2/docs)
- [Telegram Bot API](https://core.telegram.org/bots/api)
- [appleboy/telegram-action](https://github.com/appleboy/telegram-action)

---

**文档版本：** 1.0
**最后更新：** 2026-02-25
**维护团队：** AI News Radar 团队
