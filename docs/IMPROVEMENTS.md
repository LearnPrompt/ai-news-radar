# AI News Radar - 项目改进文档

## 概述

本文档描述了对 AI News Radar 项目的改进和新增功能。

## 改进内容

### 1. 可插拔的源管理架构

新增了 `scripts/sources_config.py` 模块，提供了基于插件的源管理架构：

- **SourceConfig**: 数据类，定义单个信息源的配置
- **SourceFetcher**: 抽象基类，定义源获取器接口
- **源注册表**: 支持动态注册和查询信息源

**使用示例：**
```python
from sources_config import register_source, SourceConfig, SourceFetcher

# 注册新的信息源
config = SourceConfig(
    site_id="mysource",
    site_name="My Source",
    type="api",
    category="ai",
    enabled=True,
)
register_source(config, MySourceFetcher)
```

### 2. 新增信息源

#### 无需授权的源（7个）

| 源ID | 名称 | 类型 | 描述 |
|------|------|------|------|
| `hacker_news` | Hacker News (Official) | API | 官方 Hacker News API |
| `arxiv_ai` | Arxiv AI/ML Papers | API | AI/ML 研究论文 |
| `papers_with_code` | Papers With Code | Web | 带代码的 ML 论文 |
| `lobsters` | Lobsters | RSS | 科技聚合社区 |
| `dev_ai` | Dev.to (AI Tag) | API | Dev.to AI 标签文章 |
| `medium_ai` | Medium (AI Publications) | RSS | Medium AI/ML 出版物 |
| `indiehackers` | Indie Hackers | RSS | AI 创业故事 |

#### 需要授权的源（3个）

| 源ID | 名称 | 类型 | 授权要求 |
|------|------|------|----------|
| `reddit_ai` | Reddit (AI Subreddits) | API | `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` |
| `product_hunt` | Product Hunt | API | `PRODUCT_HUNT_API_KEY` |
| `github_trending` | GitHub Trending | API | `GITHUB_TOKEN` |

### 3. 配置文件管理系统

新增 `scripts/config_manager.py` 模块：

- **YAML 配置文件**: `config/sources.yaml` - 主配置文件
- **本地覆盖**: `config/local.yaml` - 本地自定义配置（不会被提交）
- **环境变量**: `config/.env` - 环境变量支持

**配置结构：**
```yaml
sources:
  - id: hacker_news
    name: Hacker News (Official)
    enabled: true
    priority: 15
    type: api
    category: tech
    auth:
      required: false
    filters:
      min_score: 10
      max_items: 30

settings:
  update_interval: 30
  window_hours: 24
  archive_days: 45
  translate_max_new: 80
```

### 4. 源状态监控面板

新增前端源状态监控面板：

- **实时状态显示**: 每个信息源的获取状态
- **统计信息**: 总源数、已启用、正常、异常、总条目数
- **详细信息**: 条目数、获取耗时、最后更新时间
- **授权状态**: 显示需要授权的源
- **错误信息**: 显示失败的源的错误消息

**状态指示器：**
- 🟢 绿色 - 正常
- 🟡 黄色 - 部分成功
- 🔴 红色 - 错误
- ⚪ 灰色 - 已禁用

### 5. 前端优化

- 更新页面描述，反映新的源数量（17+ 个信息源）
- 添加源状态面板折叠/展开功能
- 响应式布局优化

## 文件结构

```
ai-news-radar/
├── config/
│   ├── sources.yaml           # 主配置文件
│   ├── local.example.yaml    # 本地配置示例
│   └── .env                 # 环境变量（不提交）
├── scripts/
│   ├── sources_config.py      # 源管理架构
│   ├── config_manager.py     # 配置管理器
│   ├── new_sources.py        # 新增信息源实现
│   └── update_news.py       # 主脚本（已更新）
├── data/
│   ├── sources-status.json   # 源状态数据（自动生成）
│   ├── latest-24h.json
│   ├── archive.json
│   └── waytoagi-7d.json
└── docs/
    └── IMPROVEMENTS.md      # 本文档
```

## 使用指南

### 启用新的免费源

免费源已默认启用，无需额外配置。

### 启用需要授权的源

1. 创建 `config/.env` 文件：
```bash
# Reddit
REDDIT_CLIENT_ID=your_client_id
REDDIT_CLIENT_SECRET=your_client_secret

# Product Hunt
PRODUCT_HUNT_API_KEY=your_api_key

# GitHub
GITHUB_TOKEN=your_github_token
```

2. 创建 `config/local.yaml` 并启用源：
```yaml
sources:
  - id: reddit_ai
    enabled: true
  - id: product_hunt
    enabled: true
  - id: github_trending
    enabled: true
```

### 本地运行

```bash
# 安装依赖（如果需要 PyYAML）
pip install pyyaml

# 运行更新脚本
python scripts/update_news.py \
  --output-dir data \
  --window-hours 24 \
  --rss-opml feeds/follow.opml

# 启动本地服务器
python -m http.server 8080

# 访问 http://localhost:8080
```

### 使用配置管理器

```bash
# 测试配置加载
python scripts/config_manager.py

# 测试新源
python scripts/new_sources.py
```

## 获取 API 密钥

### Reddit API
1. 访问 https://www.reddit.com/prefs/apps
2. 创建应用（选择 "script" 类型）
3. 获取 client ID 和 secret

### Product Hunt API
1. 访问 https://api.producthunt.com/
2. 申请 API 密钥

### GitHub Token
1. 访问 https://github.com/settings/tokens
2. 生成新的 Personal Access Token
3. 选择适当的权限范围

## 团队协作

### 添加新的信息源

1. 在 `scripts/new_sources.py` 中实现新的 fetch 函数
2. 在 `scripts/sources_config.py` 中注册源
3. 在 `config/sources.yaml` 中添加配置
4. 更新本文档

### 贡献者角色

| 角色 | 职责 |
|------|------|
| 源开发者 | 实现和维护信息源 |
| 配置管理员 | 管理配置文件 |
| 前端开发者 | 维护 UI 和用户体验 |
| 文档维护者 | 更新文档和指南 |

## 下一步计划

- [ ] 添加更多免费信息源
- [ ] 实现源过滤功能（按分类、标签）
- [ ] 添加通知功能（源失败时）
- [ ] 实现数据导出功能
- [ ] 添加订阅功能（RSS 输出）
- [ ] 优化移动端体验

## 相关链接

- GitHub: https://github.com/your-repo/ai-news-radar
- 项目主页: https://your-site.ai-news-radar.com

## 许可证

与主项目保持一致。
