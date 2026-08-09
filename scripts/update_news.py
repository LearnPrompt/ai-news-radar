#!/usr/bin/env python3
"""Aggregate updates from multiple AI news sites and produce 24h snapshot data."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from email.utils import parseaddr
import hashlib
import json
import math
import os
import random
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlparse, urlunparse
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dtparser
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from scripts.ai_relevance import AI_BROAD_RELEVANCE_FLOOR, add_ai_relevance_fields, is_broadly_ai_related, score_ai_relevance
except ModuleNotFoundError:  # pragma: no cover - direct `python scripts/update_news.py`
    from ai_relevance import AI_BROAD_RELEVANCE_FLOOR, add_ai_relevance_fields, is_broadly_ai_related, score_ai_relevance

try:
    import feedparser
except ModuleNotFoundError:
    feedparser = None

UTC = timezone.utc
TZINFOS = {"CET": 3600, "CEST": 7200, "EST": -18000, "EDT": -14400,
           "PST": -28800, "PDT": -25200, "CST": -21600, "CDT": -18000,
           "MST": -25200, "MDT": -21600, "BST": 3600, "JST": 32400}
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
SH_TZ = ZoneInfo("Asia/Shanghai")
WAYTOAGI_DEFAULT = (
    "https://waytoagi.feishu.cn/wiki/QPe5w5g7UisbEkkow8XcDmOpn8e?fromScene=spaceOverview"
)
WAYTOAGI_HISTORY_FALLBACK = "https://waytoagi.feishu.cn/wiki/FjiOwWp2giA7hRk6jjfcPioCnAc"

RSS_FEED_REPLACEMENTS: dict[str, str] = {
    "https://rsshub.app/infoq/recommend": "https://www.infoq.cn/feed",
    "https://rsshub.app/huggingface/blog-zh": "https://huggingface.co/blog/feed.xml",
    "https://rsshub.app/readhub/daily": "https://readhub.cn/rss",
    "https://rsshub.app/36kr/hot-list": "https://36kr.com/feed",
    "https://rsshub.app/sspai/index": "https://sspai.com/feed",
    "https://rsshub.app/sspai/matrix": "https://sspai.com/feed",
    "https://rsshub.app/meituan/tech": "https://tech.meituan.com/feed",
    "https://mjg59.dreamwidth.org/data/rss": "http://mjg59.dreamwidth.org/data/rss",
}

RSS_FEED_SKIP_PREFIXES: tuple[str, ...] = (
    "https://rsshub.app/telegram/channel/",
    "https://rsshub.app/jike/",
    "https://rsshub.app/bilibili/",
    "https://rsshub.app/zhihu/",
    "https://rsshub.app/xiaoyuzhou/podcast/",
    "https://rsshub.app/xyzrank",
    "https://rsshub.app/mittrchina/hot",
    "https://wechat2rss.bestblogs.dev/",
    "https://werss.bestblogs.dev/",
    "http://47.122.94.119:18080/",
)

RSS_FEED_SKIP_EXACT: set[str] = {
    "https://rachelbythebay.com/w/atom.xml",
    "https://flak.tedunangst.com/rss",
}

OFFICIAL_AI_FEEDS: tuple[dict[str, str], ...] = (
    {
        "title": "OpenAI News",
        "xml_url": "https://openai.com/news/rss.xml",
        "html_url": "https://openai.com/news",
    },
    {
        "title": "Google DeepMind",
        "xml_url": "https://deepmind.google/blog/rss.xml",
        "html_url": "https://deepmind.google/blog",
    },
    {
        "title": "Google AI Blog",
        "xml_url": "https://blog.google/innovation-and-ai/technology/ai/rss/",
        "html_url": "https://blog.google/innovation-and-ai/technology/ai/",
    },
    {
        "title": "Hugging Face Blog",
        "xml_url": "https://huggingface.co/blog/feed.xml",
        "html_url": "https://huggingface.co/blog",
    },
    {
        "title": "GitHub AI & ML",
        "xml_url": "https://github.blog/ai-and-ml/feed/",
        "html_url": "https://github.blog/ai-and-ml/",
    },
    {
        "title": "GitHub Changelog",
        "xml_url": "https://github.blog/changelog/feed/",
        "html_url": "https://github.blog/changelog/",
    },
    {
        "title": "OpenAI Skills",
        "xml_url": "https://github.com/openai/skills/commits/main.atom",
        "html_url": "https://github.com/openai/skills",
        "include_keywords": "hatch,pet,migrate-to-codex",
    },
)
OFFICIAL_AI_MAX_AGE_DAYS = 45
CURATED_AI_MEDIA_MAX_AGE_DAYS = 30
# Per-fetch item cap for wide discussion-tier aggregators (buzzing/iris).
# They dominate raw volume with very low AI keep rates (see
# reports/source-quality/v0.8-audit.md); cap them at the fetch layer so a
# single round cannot flood the archive. Override via env for experiments.
DISCUSSION_FETCH_CAP = int(os.environ.get("DISCUSSION_FETCH_CAP", "50"))
CURATED_AI_MEDIA_FEEDS: tuple[dict[str, Any], ...] = (
    {
        "title": "The Decoder AI News",
        "xml_url": "https://the-decoder.com/feed/",
        "html_url": "https://the-decoder.com/",
        "max_entries": 10,
    },
    {
        "title": "TechCrunch AI",
        "xml_url": "https://techcrunch.com/category/artificial-intelligence/feed/",
        "html_url": "https://techcrunch.com/category/artificial-intelligence/",
        "max_entries": 8,
    },
    {
        # The Verge's AI topic RSS endpoint is not currently public/stable;
        # keep the all-site RSS behind strict title-level AI filtering.
        "title": "The Verge",
        "xml_url": "https://www.theverge.com/rss/index.xml",
        "html_url": "https://www.theverge.com/ai-artificial-intelligence",
        "include_keywords": "ai,artificial intelligence,openai,anthropic,claude,chatgpt,gpt,gemini,llm,agent,copilot",
        "max_entries": 6,
        "strict_title_filter": True,
    },
    {
        "title": "MarkTechPost Research",
        "xml_url": "https://www.marktechpost.com/feed/",
        "html_url": "https://www.marktechpost.com/",
        "include_keywords": "paper,research,arxiv,benchmark,dataset,model,llm,agent,diffusion,transformer,multimodal,reasoning,inference,training,open-source",
        "max_entries": 6,
        "strict_title_filter": True,
        "research_only": True,
    },
    {
        "title": "VentureBeat AI",
        "xml_url": "https://venturebeat.com/category/ai/feed",
        "html_url": "https://venturebeat.com/category/ai/",
        "max_entries": 8,
    },
    {
        "title": "Artificial Intelligence News",
        "xml_url": "https://www.artificialintelligence-news.com/feed/",
        "html_url": "https://www.artificialintelligence-news.com/",
        "max_entries": 8,
    },
    {
        "title": "Claude Code Releases",
        "xml_url": "https://github.com/anthropics/claude-code/releases.atom",
        "html_url": "https://github.com/anthropics/claude-code/releases",
        "max_entries": 6,
    },
)
AIBREAKFAST_JINA_URL = "https://r.jina.ai/https://aibreakfast.beehiiv.com/"
AIHOT_ITEMS_API_URL = "https://aihot.virxact.com/api/public/items"
AIHOT_MIN_SCORE = 60
AIHOT_API_TAKE = 100
AIHOT_API_MAX_PAGES = 5
AIHOT_API_UA = f"{BROWSER_UA} aihot-skill/0.2.0 AI-News-Radar/0.7"
AIHOT_FEED_URL = "https://aihot.virxact.com/feed.xml"
AIHOT_FALLBACK_FEED_URLS = (
    "https://aihot.virxact.com/rss.xml",
    "https://aihot.virxact.com/feed",
    "https://aihot.virxact.com/feed/daily.xml",
)
FOLLOW_BUILDERS_FEED_BASE = "https://raw.githubusercontent.com/zarazhangrui/follow-builders/main"
HN_ALGOLIA_URL = "https://hn.algolia.com/api/v1/search_by_date"
HN_ALGOLIA_QUERIES: tuple[str, ...] = (
    "OpenAI",
    "Anthropic",
    "Claude Code",
    "Claude",
    "Gemini",
    "Google AI",
    "DeepSeek",
    "Qwen",
    "AI agent",
    "AI coding",
    "Codex",
    "Cursor",
    "MCP",
    "LLM",
    "GPT",
    "Sora",
    "Copilot",
    "Nvidia AI",
)
HN_ALGOLIA_KEYWORDS: tuple[str, ...] = (
    "openai",
    "anthropic",
    "claude",
    "claude code",
    "codex",
    "cursor",
    "mcp",
    "gemini",
    "deepseek",
    "qwen",
    "llm",
    "gpt",
    "sora",
    "copilot",
    "agent",
    "ai coding",
    "benchmark",
    "eval",
    "paper",
    "model",
    "inference",
)
HN_ALGOLIA_HITS_PER_QUERY = 35
HN_ALGOLIA_MIN_KEYWORD_SCORE = 0.38
HN_ALGOLIA_MIN_COMMENTS = 2
HN_ALGOLIA_MIN_POINTS = 10
HN_ALGOLIA_QUERY_PAUSE_SECONDS = 0.1
AGENTMAIL_API_BASE_DEFAULT = "https://api.agentmail.to"
AGENTMAIL_DIGEST_FILE = "email-digest.json"
AGENTMAIL_DEFAULT_LIMIT = 50
AGENTMAIL_PROVIDER_DEFAULT = "agently_cli"
AGENTMAIL_CLI_DEFAULT = "agently-cli"
AGENTMAIL_PUBLIC_LINK_TEXT_RE = re.compile(
    r"\b(read\s+online|view\s+in\s+browser|read\s+in\s+browser|open\s+in\s+browser|"
    r"read\s+on\s+web|view\s+online|web\s+version)\b",
    re.I,
)
AGENTMAIL_PUBLIC_LINK_REJECT_RE = re.compile(
    r"\b(unsubscribe|manage\s+preferences|privacy|terms|sponsor|advertise|"
    r"feedback|rate\s+this|log\s+in|subscribe)\b",
    re.I,
)
AGENTMAIL_PUBLIC_URL_REJECT_HOSTS = (
    "agent.qq.com",
    "email.beehiivstatus.com",
)
AGENTMAIL_TRACKING_QUERY_PREFIXES = ("utm_",)
AGENTMAIL_TRACKING_QUERY_KEYS = {
    "_bhlid",
    "email",
    "email_id",
    "mc_cid",
    "mc_eid",
    "ref",
    "subscriber",
    "subscriber_id",
}
PAID_SOURCE_STATE_FILE = "paid-source-state.json"
PAID_SOURCE_DEFAULT_INTERVAL_HOURS = 24
PAID_SOURCE_DEFAULT_INTERVAL_HOURS_BY_PREFIX = {
    "SOCIALDATA": 12,
    "TIKHUB": 24,
}
PAID_SOURCE_MAX_INTERVAL_HOURS = 24 * 14
X_API_BASE_DEFAULT = "https://api.x.com"
X_API_POST_READ_COST_USD = 0.005
X_API_DEFAULT_QUERY = '(AI OR "artificial intelligence" OR "large language model" OR LLM) lang:en -is:retweet has:links'
X_API_DEFAULT_MAX_RESULTS = 20
X_API_MAX_QUERY_CHARS = 512
SOCIALDATA_API_BASE_DEFAULT = "https://api.socialdata.tools"
SOCIALDATA_TWEET_READ_COST_USD = 0.0002
SOCIALDATA_DEFAULT_QUERY = '(AI OR "artificial intelligence" OR LLM OR "large language model" OR 人工智能 OR 大模型 OR 大语言模型 OR AIGC OR 智能体 OR Agent) (lang:en OR lang:zh) -filter:retweets'
SOCIALDATA_DEFAULT_MAX_RESULTS = 20
SOCIALDATA_MAX_QUERY_CHARS = 512
# Curated X list "AI is cool, i guess" (owner @aiwarts). The list timeline pulls
# each member's own posts by identity, which is far higher-signal than the broad
# keyword search. No member is excluded by default; set SOCIALDATA_LIST_EXCLUDE
# (comma-separated handles) to drop specific accounts if needed.
SOCIALDATA_LIST_ID_DEFAULT = "1695376776867062037"
SOCIALDATA_LIST_DEFAULT_MAX_RESULTS = 50
SOCIALDATA_LIST_DEFAULT_EXCLUDE = ""
# Hard cap on list pagination so a heavily-filtered list can't page (and bill)
# without bound. Each page is a paid read.
SOCIALDATA_LIST_MAX_PAGES = 10
# Exact recency window for SocialData results, in days (search + list). Kept
# consistent with TikHub. Tweets older than this are dropped after fetch.
SOCIALDATA_RECENCY_DAYS = 4
# Keep only first-party posts; drop retweets and replies (conversational noise).
SOCIALDATA_LIST_ALLOWED_TYPES = frozenset({"tweet", "quote"})
TIKHUB_API_BASE_DEFAULT = "https://api.tikhub.io"
TIKHUB_DEFAULT_QUERY = "OpenAI,Claude,大模型,Agent,AI工具,人工智能,AI"
TIKHUB_DEFAULT_PLATFORMS = "douyin,xiaohongshu"
TIKHUB_DEFAULT_MAX_RESULTS = 20
TIKHUB_MAX_QUERY_CHARS = 256
TIKHUB_RESPONSE_SCAN_LIMIT = 100
CREATOR_HOT_WINDOW_DAYS = 7
CREATOR_FRESHNESS_BONUS_HOURS = 24
CREATOR_FRESHNESS_BONUS_POINTS = 15.0
CREATOR_SITE_IDS = frozenset({"tikhub_douyin", "tikhub_xiaohongshu"})
# --- TikHub search ranking / time-window tuning (edit here, no env var needed) ---
# Exact recency window for TikHub results, in days. Douyin/Xiaohongshu search
# only expose coarse buckets (不限/一天内/一周内/半年内), so we ask the API for
# 一周内 and then enforce the exact current-week window in code.
TIKHUB_RECENCY_DAYS = 7              # keep only current-week posts
# Douyin fetch_general_search_v2 enums (standard Douyin search filter):
#   sort_type:    0=综合, 1=最多点赞(most likes), 2=最新
#   publish_time: 0=不限, 1=一天内, 7=一周内, 180=半年内
TIKHUB_DOUYIN_SORT_TYPE = "1"        # 最多点赞 / most likes
TIKHUB_DOUYIN_PUBLISH_TIME = "7"     # 一周内; real cap = TIKHUB_RECENCY_DAYS
# Xiaohongshu search. app_v2 uses the app's filter labels; sort uses the
# popularity/time/general tokens (web_v3 already takes "time_descending").
#   sort:        general(综合) / time_descending(最新) / popularity_descending(最多点赞/最热)
#   note_type:   "不限"(app_v2, all) ; web_v3 uses 0 for "all"
#   time_filter: "不限" / "一天内" / "一周内" / "半年内"
TIKHUB_XHS_SORT = "popularity_descending"  # 最多点赞 / most likes
TIKHUB_XHS_NOTE_TYPE = "不限"               # all note types
TIKHUB_XHS_TIME_FILTER = "一周内"           # 一周内; real cap = TIKHUB_RECENCY_DAYS


@dataclass
class RawItem:
    site_id: str
    site_name: str
    source: str
    title: str
    url: str
    published_at: datetime | None
    meta: dict[str, Any]


PUBLIC_RAW_META_FIELDS: tuple[str, ...] = (
    "aihot_score",
    "aihot_category",
    "aihot_selected",
    "provided_title_en",
    "provided_title_zh",
    "creator_metrics",
    "search_surface",
    "summary",
)


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def iso(dt: datetime | None) -> str | None:
    if not dt:
        return None
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_iso(dt_str: str | None) -> datetime | None:
    if not dt_str:
        return None
    try:
        dt = dtparser.parse(dt_str, tzinfos=TZINFOS)
    except Exception:
        return None
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def normalize_url(raw_url: str) -> str:
    try:
        parsed = urlparse(raw_url.strip())
        if not parsed.scheme:
            return raw_url.strip()
        query = []
        for k, v in parse_qsl(parsed.query, keep_blank_values=True):
            lk = k.lower()
            if lk.startswith("utm_"):
                continue
            if lk in {
                "ref",
                "spm",
                "fbclid",
                "gclid",
                "igshid",
                "mkt_tok",
                "mc_cid",
                "mc_eid",
                "_hsenc",
                "_hsmi",
            }:
                continue
            query.append((k, v))
        parsed = parsed._replace(
            scheme=parsed.scheme.lower(),
            netloc=parsed.netloc.lower(),
            fragment="",
            query=urlencode(query, doseq=True),
        )
        normalized = urlunparse(parsed)
        return normalized.rstrip("/")
    except Exception:
        return raw_url.strip()


def host_of_url(raw_url: str) -> str:
    try:
        return urlparse(raw_url).netloc.lower()
    except Exception:
        return ""


def first_non_empty(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        s = str(value).strip()
        if s:
            return s
    return ""


def maybe_fix_mojibake(text: str) -> str:
    s = (text or "").strip()
    if not s:
        return s
    # Common mojibake signature from UTF-8 bytes decoded as Latin-1.
    if re.search(r"[Ãâåèæïð]|[\x80-\x9f]|æ|ç|å|é", s) is None:
        return s
    for enc in ("latin1", "cp1252"):
        try:
            fixed = s.encode(enc).decode("utf-8")
            if fixed and fixed != s:
                return fixed
        except Exception:
            continue
    return s


def has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def is_mostly_english(text: str) -> bool:
    s = (text or "").strip()
    if not s:
        return False
    if has_cjk(s):
        return False
    letters = re.findall(r"[A-Za-z]", s)
    return len(letters) >= max(6, len(s) // 4)


def parse_feed_entries_via_xml(feed_xml: bytes) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    try:
        root = ET.fromstring(feed_xml)
    except Exception:
        return out

    for tag in (".//item", ".//{*}item", ".//entry", ".//{*}entry"):
        for node in root.findall(tag):
            title = (
                node.findtext("title")
                or node.findtext("{*}title")
                or ""
            ).strip()
            link = ""
            link_node = node.find("link")
            if link_node is None:
                link_node = node.find("{*}link")
            if link_node is not None:
                link = (link_node.get("href") or link_node.text or "").strip()
            if not link:
                link = (node.findtext("{*}link") or node.findtext("link") or "").strip()
            published = (
                node.findtext("pubDate")
                or node.findtext("{*}pubDate")
                or node.findtext("published")
                or node.findtext("{*}published")
                or node.findtext("updated")
                or node.findtext("{*}updated")
            )
            if title and link:
                key = (title, link)
                if key in seen:
                    continue
                seen.add(key)
                out.append({"title": title, "link": link, "published": published})
    return out


def make_item_id(site_id: str, source: str, title: str, url: str) -> str:
    key = "||".join(
        [
            site_id.strip().lower(),
            source.strip().lower(),
            title.strip().lower(),
            normalize_url(url),
        ]
    )
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def parse_unix_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        n = float(value)
    except Exception:
        return None
    if n > 10_000_000_000:
        n /= 1000.0
    try:
        return datetime.fromtimestamp(n, tz=UTC)
    except Exception:
        return None


def parse_relative_time_zh(text: str, now: datetime) -> datetime | None:
    text = (text or "").strip()
    if not text:
        return None

    m = re.search(r"(\d+)\s*分钟前", text)
    if m:
        return now - timedelta(minutes=int(m.group(1)))

    m = re.search(r"(\d+)\s*小时前", text)
    if m:
        return now - timedelta(hours=int(m.group(1)))

    m = re.search(r"(\d+)\s*天前", text)
    if m:
        return now - timedelta(days=int(m.group(1)))

    if "刚刚" in text:
        return now

    if "昨天" in text:
        return now - timedelta(days=1)

    m = re.fullmatch(r"(?:今天)?\s*(\d{1,2}):(\d{2})", text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate > now + timedelta(minutes=5):
            candidate -= timedelta(days=1)
        return candidate

    m = re.fullmatch(r"昨天\s*(\d{1,2}):(\d{2})", text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
        return (now - timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)

    m = re.fullmatch(r"(?:\d{4}年\s*)?(\d{1,2})月(\d{1,2})日", text)
    if m:
        month = int(m.group(1))
        day = int(m.group(2))
        year = now.year
        try:
            candidate = datetime(year, month, day, tzinfo=UTC)
            if candidate > now + timedelta(days=2):
                candidate = datetime(year - 1, month, day, tzinfo=UTC)
            return candidate
        except Exception:
            return None

    return None


def parse_date_any(value: Any, now: datetime) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.astimezone(UTC)

    if isinstance(value, (int, float)):
        return parse_unix_timestamp(value)

    s = str(value).strip()
    if not s:
        return None

    if s.startswith("$D"):
        s = s[2:]

    if re.fullmatch(r"\d{12,}", s):
        return parse_unix_timestamp(int(s))

    if re.fullmatch(r"\d{9,11}", s):
        return parse_unix_timestamp(int(s))

    dt = parse_relative_time_zh(s, now)
    if dt:
        return dt

    # TechURLs format: 2026-02-19 11:54:21AM UTC
    m = re.search(r"(\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}:\d{2}[AP]M)\s+UTC", s)
    if m:
        try:
            dt = datetime.strptime(m.group(1), "%Y-%m-%d %I:%M:%S%p")
            return dt.replace(tzinfo=UTC)
        except Exception:
            pass

    try:
        dt = dtparser.parse(s, tzinfos={"UT": 0, "UTC": 0, "GMT": 0, **TZINFOS})
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except Exception:
        return None


FUTURE_PUBLISH_SKEW = timedelta(hours=2)
CST_MISLABEL_OFFSET = timedelta(hours=8)


def correct_future_published(
    published: datetime | None,
    now: datetime,
    *,
    assume_cst_mislabel: bool = False,
) -> datetime | None:
    """兜住源头 feed 错标时区产生的"未来"发布时间。

    典型病例：InfoQ CN 的 RSS 把北京时间直接标成 GMT（如
    "Tue, 14 Jul 2026 22:01:15 GMT" 实为 22:01 北京时间），按标记解析后
    published 领先真实时间 8 小时，前端时间轴出现未来条目。
    中文源先尝试减 8 小时纠正；纠正后仍在未来（或非中文源）则回退抓取时间。
    """
    if published is None:
        return None
    limit = now + FUTURE_PUBLISH_SKEW
    if published <= limit:
        return published
    if assume_cst_mislabel:
        corrected = published - CST_MISLABEL_OFFSET
        if corrected <= limit:
            return corrected
    return now


def correct_feed_published_batch(
    published_list: list[datetime],
    now: datetime,
    *,
    assume_cst_mislabel: bool = False,
) -> list[datetime]:
    """feed 级错标推断：同一 feed 只要最新条目在未来且减 8h 后合理，

    即可判定整个 feed 都把北京时间错标成了 GMT，本轮全部条目统一纠正——
    这样没越过"现在"的错标条目（不会触发单条防御）也能修对。
    否则退回逐条防御。
    """
    if not published_list:
        return published_list
    if assume_cst_mislabel:
        limit = now + FUTURE_PUBLISH_SKEW
        newest = max(published_list)
        if newest > limit and newest - CST_MISLABEL_OFFSET <= limit:
            return [p - CST_MISLABEL_OFFSET for p in published_list]
    return [
        correct_future_published(p, now, assume_cst_mislabel=assume_cst_mislabel)
        for p in published_list
    ]


def apply_public_raw_meta(record: dict[str, Any], raw: RawItem) -> None:
    """Promote safe source metadata needed by public scoring and UI ranking."""
    meta = raw.meta if isinstance(raw.meta, dict) else {}
    for key in PUBLIC_RAW_META_FIELDS:
        if key in meta and meta.get(key) is not None:
            record[key] = sanitize_public_value(meta.get(key))


def decode_escaped_json(raw: str) -> dict[str, Any] | None:
    s = raw.replace('\\"', '"').replace("\\/", "/")
    try:
        return json.loads(s)
    except Exception:
        return None


def extract_waytoagi_history_url(root_html: str) -> str:
    pattern = r'\{\\"id\\":\\"[^\"]+\\",\\"type\\":\\"mention_doc\\",\\"data\\":\{[^\}]+\}\}'
    for raw in re.findall(pattern, root_html):
        obj = decode_escaped_json(raw)
        if not obj:
            continue
        data = obj.get("data", {})
        title = str(data.get("title") or "")
        if "历史更新" in title or "更新日志" in title:
            raw_url = str(data.get("raw_url") or "").strip()
            if raw_url:
                return raw_url
    return WAYTOAGI_HISTORY_FALLBACK


def extract_feishu_client_vars(page_html: str) -> dict[str, Any]:
    marker = "window.DATA = Object.assign({}, window.DATA, { clientVars: Object("
    idx = page_html.find(marker)
    if idx == -1:
        raise ValueError("Cannot locate Feishu clientVars marker")

    start = idx + len(marker)
    depth = 1
    in_str = False
    escaped = False
    end = None

    for i, ch in enumerate(page_html[start:], start):
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue

        if ch == '"':
            in_str = True
            continue

        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                end = i
                break

    if end is None:
        raise ValueError("Cannot parse Feishu clientVars payload")

    payload = page_html[start:end]
    return json.loads(payload)


def block_text(block_data: dict[str, Any]) -> str:
    text_obj = block_data.get("text", {}) if isinstance(block_data, dict) else {}
    initial = text_obj.get("initialAttributedTexts", {}).get("text", {}) if isinstance(text_obj, dict) else {}
    if not isinstance(initial, dict):
        return ""

    def key_int(k: Any) -> int:
        try:
            return int(k)
        except Exception:
            return 0

    return "".join(str(v) for k, v in sorted(initial.items(), key=lambda kv: key_int(kv[0]))).strip()


def block_text_runs(block_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return text runs with optional link info from a Feishu block.

    Each run is ``{"text": str, "link": str | None}``.

    Feishu wiki blocks store linked document mentions as ``inline-component``
    entries in ``text.apool.numToAttrib``.  The mention JSON payload carries
    the real article title (``data.title``) and URL (``data.raw_url``), while
    the block's visible ``initialAttributedTexts.text`` holds a summary with
    ``《 》`` as a placeholder for the mention.
    """
    text_obj = block_data.get("text", {}) if isinstance(block_data, dict) else {}
    if not isinstance(text_obj, dict):
        return []

    initial = text_obj.get("initialAttributedTexts", {})
    text_map = initial.get("text", {})
    if not isinstance(text_map, dict):
        return []

    def key_int(k: Any) -> int:
        try:
            return int(k)
        except Exception:
            return 0

    full_text = "".join(
        str(v) for _, v in sorted(text_map.items(), key=lambda kv: key_int(kv[0]))
    ).strip()

    # Look for inline-component mention_doc in apool
    apool = text_obj.get("apool", {})
    num_to_attrib = apool.get("numToAttrib", {}) if isinstance(apool, dict) else {}

    mention_title: str | None = None
    mention_url: str | None = None

    for _k, v in num_to_attrib.items():
        if not isinstance(v, list) or len(v) < 2 or v[0] != "inline-component":
            continue
        try:
            comp = json.loads(v[1]) if isinstance(v[1], str) else v[1]
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(comp, dict) or comp.get("type") != "mention_doc":
            continue
        data = comp.get("data", {})
        t = str(data.get("title") or "").strip()
        u = str(data.get("raw_url") or "").strip()
        if t:
            mention_title = t
            mention_url = u or None
            break

    runs: list[dict[str, Any]] = []
    if mention_title:
        runs.append({"text": mention_title, "link": mention_url})
        summary = full_text.replace("《 》", "").replace("《》", "").strip()
        if summary:
            runs.append({"text": summary, "link": None})
    elif full_text:
        runs.append({"text": full_text, "link": None})

    return runs


def clean_update_title(text: str) -> str:
    text = text.replace("《 》", "").replace("《》", "")
    return re.sub(r"\s+", " ", text).strip()


def parse_ym_heading(text: str) -> tuple[int, int] | None:
    m = re.search(r"(20\d{2})\s*年\s*(\d{1,2})\s*月", text)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def parse_md_heading(text: str) -> tuple[int, int] | None:
    m = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日", text)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def infer_shanghai_year_for_month_day(now_sh: datetime, month: int, day: int) -> int | None:
    year = now_sh.year
    try:
        candidate = date(year, month, day)
    except Exception:
        return None
    if candidate > (now_sh.date() + timedelta(days=2)):
        year -= 1
    return year


def extract_waytoagi_recent_updates_from_block_map(
    block_map: dict[str, Any],
    now_sh: datetime,
    page_url: str,
) -> list[dict[str, Any]]:
    if not isinstance(block_map, dict) or not block_map:
        return []

    ym_by_heading2: dict[str, tuple[int, int]] = {}
    near_log_parent_ids: set[str] = set()

    for bid, block in block_map.items():
        bd = block.get("data", {})
        btype = bd.get("type")
        if btype not in {"heading1", "heading2", "heading3"}:
            continue
        heading_text = block_text(bd)
        if "近7日更新日志" in heading_text or "近 7 日更新日志" in heading_text:
            parent_id = str(bd.get("parent_id") or "").strip()
            if parent_id:
                near_log_parent_ids.add(parent_id)

    heading3_dates: dict[str, date] = {}

    for bid, block in block_map.items():
        bd = block.get("data", {})
        if bd.get("type") != "heading2":
            continue
        ym = parse_ym_heading(block_text(bd))
        if ym:
            ym_by_heading2[bid] = ym

    for bid, block in block_map.items():
        bd = block.get("data", {})
        if bd.get("type") != "heading3":
            continue
        md = parse_md_heading(block_text(bd))
        if not md:
            continue
        month, day = md
        parent = bd.get("parent_id")
        if near_log_parent_ids and parent not in near_log_parent_ids:
            continue
        year = ym_by_heading2.get(parent, (now_sh.year, month))[0]
        inferred = infer_shanghai_year_for_month_day(now_sh, month, day)
        if inferred is not None:
            year = inferred
        try:
            heading3_dates[bid] = date(year, month, day)
        except Exception:
            continue

    parent_map: dict[str, str] = {}
    for bid, block in block_map.items():
        bd = block.get("data", {})
        parent = str(bd.get("parent_id") or "").strip()
        if parent:
            parent_map[bid] = parent

    def nearest_heading_date(block_id: str) -> date | None:
        cur = parent_map.get(block_id)
        hops = 0
        while cur and hops < 20:
            if cur in heading3_dates:
                return heading3_dates[cur]
            cur = parent_map.get(cur)
            hops += 1
        return None

    updates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for bid, block in block_map.items():
        bd = block.get("data", {})
        if bd.get("type") not in {"bullet", "text", "todo", "ordered"}:
            continue

        day = nearest_heading_date(bid)
        if not day:
            continue

        runs = block_text_runs(bd)
        linked_run = next((r for r in runs if r.get("link")), None)
        if linked_run:
            title = clean_update_title(linked_run["text"])
            summary_parts = [
                clean_update_title(r["text"])
                for r in runs
                if r is not linked_run and clean_update_title(r["text"])
            ]
            summary = " ".join(summary_parts) if summary_parts else title
            item_url = linked_run["link"] or page_url
        else:
            title = clean_update_title(block_text(bd))
            summary = title
            item_url = page_url

        if not title:
            continue
        key = (day.isoformat(), title)
        if key in seen:
            continue
        seen.add(key)
        updates.append({
            "date": day.isoformat(),
            "title": title,
            "summary": summary,
            "url": item_url,
        })

    return updates


def fetch_waytoagi_recent_7d(session: requests.Session, now_utc: datetime, root_url: str) -> dict[str, Any]:
    now_sh = now_utc.astimezone(SH_TZ)
    root_html = session.get(root_url, timeout=30).text
    history_url = extract_waytoagi_history_url(root_html)

    root_client_vars = extract_feishu_client_vars(root_html)
    root_block_map = root_client_vars.get("data", {}).get("block_map", {})
    updates: list[dict[str, Any]] = extract_waytoagi_recent_updates_from_block_map(root_block_map, now_sh, root_url)

    if history_url and history_url != root_url:
        try:
            history_html = session.get(history_url, timeout=30).text
            history_client_vars = extract_feishu_client_vars(history_html)
            history_block_map = history_client_vars.get("data", {}).get("block_map", {})
            updates.extend(
                extract_waytoagi_recent_updates_from_block_map(history_block_map, now_sh, history_url)
            )
        except Exception:
            pass

    dedup_updates: dict[tuple[str, str], dict[str, Any]] = {}
    for item in updates:
        key = (str(item.get("date") or ""), str(item.get("title") or ""))
        if key[0] and key[1] and key not in dedup_updates:
            dedup_updates[key] = item

    start_date = now_sh.date() - timedelta(days=6)
    end_date = now_sh.date()
    recent = [
        u
        for u in dedup_updates.values()
        if start_date <= date.fromisoformat(str(u.get("date") or "1970-01-01")) <= end_date
    ]
    recent.sort(key=lambda x: (x["date"], x["title"]), reverse=True)
    latest_date = recent[0]["date"] if recent else None
    updates_today = [u for u in recent if u.get("date") == latest_date] if latest_date else []

    warning = "近7日未解析到更新条目" if not recent else None
    return {
        "generated_at": iso(now_utc),
        "timezone": "Asia/Shanghai",
        "root_url": root_url,
        "history_url": history_url,
        "window_days": 7,
        "latest_date": latest_date,
        "count_today": len(updates_today),
        "updates_today": updates_today,
        "count_7d": len(recent),
        "updates_7d": recent,
        "warning": warning,
        "has_error": False,
        "error": None,
    }


def waytoagi_updates_to_raw_items(payload: dict[str, Any], now: datetime) -> list[RawItem]:
    updates = payload.get("updates_today")
    if not isinstance(updates, list):
        updates = []
    out: list[RawItem] = []
    for update in updates:
        if not isinstance(update, dict):
            continue
        title = str(update.get("title") or "").strip()
        url = str(update.get("url") or payload.get("root_url") or WAYTOAGI_DEFAULT).strip()
        if not title or not url:
            continue
        update_date = str(update.get("date") or payload.get("latest_date") or "").strip()
        source = f"社区更新 · {update_date}" if update_date else "社区更新"
        out.append(
            RawItem(
                site_id="waytoagi",
                site_name="WaytoAGI",
                source=source,
                title=title,
                url=url,
                # WaytoAGI update logs only expose a date. Treat currently
                # visible latest-date entries as fresh community signals for
                # the 24h board while the 7d payload keeps exact date context.
                published_at=now,
                meta={"summary": update.get("summary") or title},
            )
        )
    return out


def create_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.8,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(["GET", "POST"]),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent": BROWSER_UA, "Accept-Language": "zh-CN,zh;q=0.9"})
    return session


def extract_next_f_merged(html: str) -> str:
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', html, re.S)
    if not chunks:
        return ""
    merged = "".join(chunks)
    try:
        return bytes(merged, "utf-8").decode("unicode_escape")
    except Exception:
        return merged


def extract_balanced_json(decoded: str, key: str) -> Any:
    idx = decoded.find(key)
    if idx == -1:
        raise ValueError(f"Key not found: {key}")

    start = idx + len(key)
    while start < len(decoded) and decoded[start] != ":":
        start += 1
    start += 1
    while start < len(decoded) and decoded[start] not in "[{":
        start += 1

    open_ch = decoded[start]
    close_ch = "}" if open_ch == "{" else "]"
    depth = 0
    in_str = False
    esc = False
    end = None

    for i, ch in enumerate(decoded[start:], start):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break

    if end is None:
        raise ValueError(f"Cannot parse JSON block for key: {key}")

    snippet = decoded[start:end]
    snippet = snippet.replace("$undefined", "null")
    snippet = re.sub(r'"\$D([^\"]+)"', r'"\1"', snippet)
    return json.loads(snippet)


def extract_next_data_payload(html: str) -> dict[str, Any] | None:
    m = re.search(
        r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>\s*(\{.*?\})\s*</script>',
        html,
        re.S,
    )
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None


def fetch_techurls(session: requests.Session, now: datetime) -> list[RawItem]:
    site_id = "techurls"
    site_name = "TechURLs"
    r = session.get("https://techurls.com/", timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    out: list[RawItem] = []
    for block in soup.select("div.publisher-block"):
        primary = (
            block.select_one(".publisher-text .primary").get_text(strip=True)
            if block.select_one(".publisher-text .primary")
            else block.get("data-publisher", "unknown")
        )
        secondary = (
            block.select_one(".publisher-text .secondary").get_text(strip=True)
            if block.select_one(".publisher-text .secondary")
            else ""
        )
        source = f"{primary} · {secondary}" if secondary and secondary != primary else primary

        for link_row in block.select("div.publisher-link"):
            a = link_row.select_one("a.article-link")
            if not a or not a.get("href"):
                continue
            title = a.get_text(" ", strip=True)
            url = a["href"].strip()

            time_hint = ""
            aside = link_row.select_one(".aside .text")
            if aside:
                time_hint = aside.get("title", "") or aside.get_text(" ", strip=True)

            published = parse_date_any(time_hint, now)
            out.append(
                RawItem(
                    site_id=site_id,
                    site_name=site_name,
                    source=source,
                    title=title,
                    url=url,
                    published_at=published,
                    meta={"time_hint": time_hint},
                )
            )

    return out


def fetch_buzzing(session: requests.Session, now: datetime) -> list[RawItem]:
    site_id = "buzzing"
    site_name = "Buzzing"
    r = session.get("https://www.buzzing.cc/feed.json", timeout=30)
    r.raise_for_status()
    payload = r.json()
    items = payload.get("items", [])

    out: list[RawItem] = []
    for it in items:
        if len(out) >= DISCUSSION_FETCH_CAP:
            break
        title = (it.get("title") or "").strip()
        url = (it.get("url") or "").strip()
        if not title or not url:
            continue
        source = first_non_empty(
            it.get("source"),
            it.get("site_name"),
            it.get("channel"),
            it.get("category"),
            host_of_url(url),
            site_name,
        )
        published = parse_date_any(it.get("date_published") or it.get("date_modified"), now)
        out.append(
            RawItem(
                site_id=site_id,
                site_name=site_name,
                source=source,
                title=title,
                url=url,
                published_at=published,
                meta={"raw": {k: it.get(k) for k in ("source", "site_name", "channel", "category")}},
            )
        )
    return out


def fetch_iris(session: requests.Session, now: datetime) -> list[RawItem]:
    site_id = "iris"
    site_name = "Info Flow"

    r = session.get("https://iris.findtruman.io/web/info_flow", timeout=30)
    r.raise_for_status()
    html = r.text

    m = re.search(r"const\s+feeds\s*=\s*\[(.*?)\]\s*;", html, re.S)
    if not m:
        return []

    section = m.group(1)
    feeds = re.findall(
        r"\{\s*name:\s*'([^']+)'\s*,\s*url:\s*'([^']+)'\s*\}",
        section,
        re.S,
    )

    out: list[RawItem] = []
    for feed_name, feed_url in feeds:
        if len(out) >= DISCUSSION_FETCH_CAP:
            break
        try:
            if feedparser is not None:
                parsed = feedparser.parse(feed_url)
                source_name = str(feed_name or getattr(parsed, "feed", {}).get("title") or "Iris Feed")
                for entry in parsed.entries:
                    if len(out) >= DISCUSSION_FETCH_CAP:
                        break
                    title = str(entry.get("title", "")).strip()
                    url = str(entry.get("link", "")).strip()
                    if not title or not url:
                        continue
                    published = (
                        parse_date_any(entry.get("published"), now)
                        or parse_date_any(entry.get("updated"), now)
                        or parse_date_any(entry.get("pubDate"), now)
                    )
                    out.append(
                        RawItem(
                            site_id=site_id,
                            site_name=site_name,
                            source=source_name,
                            title=title,
                            url=url,
                            published_at=published,
                            meta={"feed_url": feed_url},
                        )
                    )
                continue

            feed_resp = session.get(feed_url, timeout=30)
            feed_resp.raise_for_status()
            entries = parse_feed_entries_via_xml(feed_resp.content)
            source_name = str(feed_name or "Iris Feed")
            for entry in entries:
                if len(out) >= DISCUSSION_FETCH_CAP:
                    break
                out.append(
                    RawItem(
                        site_id=site_id,
                        site_name=site_name,
                        source=source_name,
                        title=entry["title"],
                        url=entry["link"],
                        published_at=parse_date_any(entry.get("published"), now),
                        meta={"feed_url": feed_url},
                    )
                )
        except Exception:
            # Skip blocked/broken sub feeds and keep remaining feeds.
            continue
    return out


def fetch_bestblogs(session: requests.Session, now: datetime) -> list[RawItem]:
    site_id = "bestblogs"
    site_name = "BestBlogs"

    api = "https://api.bestblogs.dev/api/newsletter/list"
    out: list[RawItem] = []
    seen: set[str] = set()

    try:
        current_page = 1
        page_count = 1

        while current_page <= page_count and current_page <= 12:
            payload = {
                "currentPage": current_page,
                "pageSize": 20,
                "userLanguage": "en",
            }
            r = session.post(api, json=payload, timeout=30)
            r.raise_for_status()
            body = r.json()
            data = body.get("data", {})
            page_count = int(data.get("pageCount", 1) or 1)

            for issue in data.get("dataList", []):
                issue_id = str(issue.get("id", "")).strip()
                title = str(issue.get("title", "")).strip()
                if not issue_id or not title:
                    continue
                url = f"https://www.bestblogs.dev/en/newsletter#{issue_id}"
                if url in seen:
                    continue
                seen.add(url)

                published = parse_unix_timestamp(issue.get("createdTimestamp"))
                out.append(
                    RawItem(
                        site_id=site_id,
                        site_name=site_name,
                        source="Weekly Newsletter",
                        title=title,
                        url=url,
                        published_at=published,
                        meta={
                            "issue_id": issue_id,
                            "article_count": issue.get("articleCount"),
                        },
                    )
                )
            current_page += 1
    except Exception:
        pass

    if out:
        return out

    r = session.get("https://www.bestblogs.dev/en/newsletter", timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    for a in soup.select("a[href*='/newsletter']"):
        href = (a.get("href") or "").strip()
        if not href:
            continue
        url = href if href.startswith("http") else urljoin("https://www.bestblogs.dev", href)
        title = a.get_text(" ", strip=True)
        if len(title) < 8:
            continue
        if url in seen:
            continue
        seen.add(url)
        dt = None
        time_tag = a.select_one("time")
        if time_tag:
            dt = parse_date_any(time_tag.get("datetime") or time_tag.get_text(" ", strip=True), now)
        out.append(
            RawItem(
                site_id=site_id,
                site_name=site_name,
                source="Weekly Newsletter",
                title=title,
                url=url,
                published_at=dt,
                meta={},
            )
        )

    return out


def fetch_zeli(session: requests.Session, now: datetime) -> list[RawItem]:
    site_id = "zeli"
    site_name = "Zeli"
    out: list[RawItem] = []

    url = "https://zeli.app/api/hacker-news?type=hot24h"
    r = session.get(url, timeout=30)
    r.raise_for_status()
    body = r.json()
    posts = body.get("posts", [])
    for p in posts:
        title = str(p.get("title", "")).strip()
        link = str(p.get("url", "")).strip()
        if not title or not link:
            continue
        published = parse_unix_timestamp(p.get("time")) or now
        out.append(
            RawItem(
                site_id=site_id,
                site_name=site_name,
                source="Hacker News · 24h最热",
                title=title,
                url=link,
                published_at=published,
                meta={"hn_id": p.get("id")},
            )
        )

    return out


def hn_algolia_keyword_score(title: str) -> float:
    blob = title.lower()
    hits = 0
    for keyword in HN_ALGOLIA_KEYWORDS:
        if re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", blob):
            hits += 1
    return min(1.0, hits / 3)


def parse_hn_algolia_hits(payloads: list[tuple[str, dict[str, Any]]], now: datetime) -> list[RawItem]:
    seen_ids: set[str] = set()
    out: list[RawItem] = []

    for query, payload in payloads:
        hits = payload.get("hits")
        if not isinstance(hits, list):
            continue

        for hit in hits:
            if not isinstance(hit, dict):
                continue
            object_id = str(hit.get("objectID") or "").strip()
            if not object_id or object_id in seen_ids:
                continue
            seen_ids.add(object_id)

            title = maybe_fix_mojibake(str(first_non_empty(hit.get("title"), hit.get("story_title"))))
            if not title or hn_algolia_keyword_score(title) < HN_ALGOLIA_MIN_KEYWORD_SCORE:
                continue

            try:
                comments = int(hit.get("num_comments") or 0)
            except Exception:
                comments = 0
            try:
                points = int(hit.get("points") or 0)
            except Exception:
                points = 0
            if comments < HN_ALGOLIA_MIN_COMMENTS and points < HN_ALGOLIA_MIN_POINTS:
                continue

            item_url = str(hit.get("url") or "").strip()
            hn_url = f"https://news.ycombinator.com/item?id={object_id}"
            published = parse_date_any(hit.get("created_at"), now) or parse_unix_timestamp(hit.get("created_at_i")) or now

            out.append(
                RawItem(
                    site_id="hackernews",
                    site_name="Hacker News",
                    source="HN Algolia · AI 24h",
                    title=title,
                    url=item_url or hn_url,
                    published_at=published,
                    meta={
                        "hn_id": object_id,
                        "hn_url": hn_url,
                        "hn_query": query,
                        "hn_comments": comments,
                        "hn_points": points,
                    },
                )
            )

    out.sort(
        key=lambda item: (
            int(item.meta.get("hn_comments") or 0),
            int(item.meta.get("hn_points") or 0),
            item.published_at or datetime.min.replace(tzinfo=UTC),
        ),
        reverse=True,
    )
    return out


def fetch_hacker_news_algolia(session: requests.Session, now: datetime) -> list[RawItem]:
    start_ts = int((now - timedelta(hours=24)).timestamp())
    payloads: list[tuple[str, dict[str, Any]]] = []
    errors: list[str] = []

    for query in HN_ALGOLIA_QUERIES:
        try:
            response = session.get(
                HN_ALGOLIA_URL,
                params={
                    "query": query,
                    "tags": "story",
                    "numericFilters": f"created_at_i>{start_ts}",
                    "hitsPerPage": HN_ALGOLIA_HITS_PER_QUERY,
                },
                headers={"Accept": "application/json"},
                timeout=16,
            )
            response.raise_for_status()
            payloads.append((query, response.json()))
        except Exception as exc:
            errors.append(f"{query}: {exc}")
        time.sleep(HN_ALGOLIA_QUERY_PAUSE_SECONDS)

    if not payloads and errors:
        raise ValueError(f"HN Algolia queries failed: {'; '.join(errors[:3])}")

    return parse_hn_algolia_hits(payloads, now)


def parse_anthropic_news_items(page_html: str, now: datetime) -> list[RawItem]:
    site_id = "official_ai"
    site_name = "Official AI Updates"
    soup = BeautifulSoup(page_html, "html.parser")
    out: list[RawItem] = []
    seen: set[str] = set()

    for a in soup.select('a[href^="/news/"]'):
        href = str(a.get("href") or "").strip()
        if not href or href == "/news/" or href == "/news":
            continue

        title_tag = a.select_one("h1, h2, h3, h4")
        title = title_tag.get_text(" ", strip=True) if title_tag else ""
        title = maybe_fix_mojibake(title)
        if not title or title.lower() == "news":
            continue

        url = urljoin("https://www.anthropic.com", href)
        if url in seen:
            continue
        seen.add(url)

        time_tag = a.select_one("time")
        published = None
        if time_tag:
            published = parse_date_any(time_tag.get("datetime") or time_tag.get_text(" ", strip=True), now)
        if not published:
            continue
        if now and published < now - timedelta(days=OFFICIAL_AI_MAX_AGE_DAYS):
            continue

        out.append(
            RawItem(
                site_id=site_id,
                site_name=site_name,
                source="Anthropic News",
                title=title,
                url=url,
                published_at=published,
                meta={"provider": "Anthropic"},
            )
        )

    return out


def parse_openai_codex_changelog_items(page_html: str, now: datetime) -> list[RawItem]:
    site_id = "official_ai"
    site_name = "Official AI Updates"
    soup = BeautifulSoup(page_html, "html.parser")
    out: list[RawItem] = []
    seen: set[str] = set()

    for node in soup.select("#codex-changelog-content li[id], li[id]"):
        item_id = str(node.get("id") or "").strip()
        if not item_id or item_id in seen:
            continue

        time_tag = node.select_one("time")
        title_tag = node.select_one("h3")
        if not time_tag or not title_tag:
            continue

        title = maybe_fix_mojibake(title_tag.get_text(" ", strip=True))
        published = parse_date_any(time_tag.get("datetime") or time_tag.get_text(" ", strip=True), now)
        if not title or not published:
            continue
        if now and published < now - timedelta(days=OFFICIAL_AI_MAX_AGE_DAYS):
            continue

        seen.add(item_id)
        out.append(
            RawItem(
                site_id=site_id,
                site_name=site_name,
                source="OpenAI Codex Changelog",
                title=title,
                url=f"https://developers.openai.com/codex/changelog#{item_id}",
                published_at=published,
                meta={"provider": "OpenAI"},
            )
        )

    return out


def fetch_feed_as_official_items(
    session: requests.Session,
    feed: dict[str, str],
    now: datetime,
) -> list[RawItem]:
    site_id = "official_ai"
    site_name = "Official AI Updates"
    feed_url = feed["xml_url"]
    feed_title = feed["title"]

    resp = session.get(
        feed_url,
        timeout=20,
        headers={
            "User-Agent": BROWSER_UA,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        },
    )
    resp.raise_for_status()

    entries: list[dict[str, Any]]
    if feedparser is not None:
        parsed = feedparser.parse(resp.content)
        entries = list(parsed.entries)
    else:
        entries = parse_feed_entries_via_xml(resp.content)

    out: list[RawItem] = []
    include_keywords = [
        keyword.strip().lower()
        for keyword in str(feed.get("include_keywords") or "").split(",")
        if keyword.strip()
    ]
    for entry in entries:
        title = str(entry.get("title", "")).strip()
        link = str(entry.get("link", "")).strip()
        if not title or not link:
            continue
        if include_keywords:
            haystack = f"{title} {link}".lower()
            if not any(keyword in haystack for keyword in include_keywords):
                continue
        published = (
            parse_date_any(entry.get("published"), now)
            or parse_date_any(entry.get("updated"), now)
            or parse_date_any(entry.get("pubDate"), now)
        )
        if not published:
            continue
        if published < now - timedelta(days=OFFICIAL_AI_MAX_AGE_DAYS):
            continue

        out.append(
            RawItem(
                site_id=site_id,
                site_name=site_name,
                source=feed_title,
                title=maybe_fix_mojibake(title),
                url=link,
                published_at=published,
                meta={
                    "feed_url": feed_url,
                    "feed_home": feed.get("html_url") or "",
                },
            )
        )

    return out


def feed_entry_title_link_published(entry: dict[str, Any], now: datetime) -> tuple[str, str, datetime | None]:
    title = maybe_fix_mojibake(str(entry.get("title", "")).strip())
    link = str(entry.get("link", "")).strip()
    published = (
        parse_date_any(entry.get("published"), now)
        or parse_date_any(entry.get("updated"), now)
        or parse_date_any(entry.get("pubDate"), now)
    )
    return title, link, published


def feed_keywords(feed: dict[str, Any]) -> list[str]:
    return [
        keyword.strip().lower()
        for keyword in str(feed.get("include_keywords") or "").split(",")
        if keyword.strip()
    ]


def curated_feed_entry_allowed(feed: dict[str, Any], title: str, link: str) -> bool:
    include_keywords = feed_keywords(feed)
    if not include_keywords:
        return True
    haystack = title.lower()
    if not feed.get("strict_title_filter"):
        haystack = f"{haystack} {link.lower()} {feed.get('title', '').lower()}"
    return any(keyword in haystack for keyword in include_keywords)


def parse_curated_ai_media_feed_items(
    feed_content: bytes,
    feed: dict[str, Any],
    now: datetime,
) -> list[RawItem]:
    site_id = "curated_media"
    site_name = "Curated Media"
    feed_url = str(feed["xml_url"])
    feed_title = str(feed["title"])

    if feedparser is not None:
        parsed = feedparser.parse(feed_content)
        entries = list(parsed.entries)
    else:
        entries = parse_feed_entries_via_xml(feed_content)

    out: list[RawItem] = []
    seen_urls: set[str] = set()
    max_entries = max(1, int(feed.get("max_entries") or 8))
    for entry in entries:
        title, link, published = feed_entry_title_link_published(entry, now)
        if not title or not link or not published:
            continue
        if published < now - timedelta(days=CURATED_AI_MEDIA_MAX_AGE_DAYS):
            continue
        if not curated_feed_entry_allowed(feed, title, link):
            continue
        normalized_url = normalize_url(link)
        if normalized_url in seen_urls:
            continue
        seen_urls.add(normalized_url)
        out.append(
            RawItem(
                site_id=site_id,
                site_name=site_name,
                source=feed_title,
                title=title,
                url=link,
                published_at=published,
                meta={
                    "feed_url": feed_url,
                    "feed_home": feed.get("html_url") or "",
                    "research_only": bool(feed.get("research_only")),
                    "strict_title_filter": bool(feed.get("strict_title_filter")),
                },
            )
        )
        if len(out) >= max_entries:
            break

    return out


def fetch_curated_ai_media(session: requests.Session, now: datetime) -> list[RawItem]:
    out: list[RawItem] = []
    failures: list[str] = []

    for feed in CURATED_AI_MEDIA_FEEDS:
        try:
            resp = session.get(
                str(feed["xml_url"]),
                timeout=20,
                headers={
                    "User-Agent": BROWSER_UA,
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
                },
            )
            resp.raise_for_status()
            out.extend(parse_curated_ai_media_feed_items(resp.content, feed, now))
        except Exception:
            failures.append(str(feed.get("title") or feed.get("xml_url") or "unknown"))

    if not out and failures:
        raise ValueError(f"No curated media items parsed; failed feeds: {', '.join(failures[:4])}")
    return out


def fetch_official_ai_updates(session: requests.Session, now: datetime) -> list[RawItem]:
    out: list[RawItem] = []

    for feed in OFFICIAL_AI_FEEDS:
        try:
            out.extend(fetch_feed_as_official_items(session, feed, now))
        except Exception:
            continue

    try:
        r = session.get("https://www.anthropic.com/news", timeout=20)
        r.raise_for_status()
        out.extend(parse_anthropic_news_items(r.text, now))
    except Exception:
        pass

    try:
        r = session.get("https://developers.openai.com/codex/changelog", timeout=20)
        r.raise_for_status()
        out.extend(parse_openai_codex_changelog_items(r.text, now))
    except Exception:
        pass

    if not out:
        raise ValueError("No official AI update sources returned items")

    return out


def parse_ai_breakfast_items(markdown_text: str, now: datetime) -> list[RawItem]:
    site_id = "aibreakfast"
    site_name = "AI Breakfast"
    out: list[RawItem] = []
    seen: set[str] = set()
    pattern = re.compile(
        r"([A-Z][a-z]{2}\s+\d{1,2},\s+\d{4})\s+•\s+\d+\s+min read\s+###\s+\*\*(.*?)\*\*.*?"
        r"\]\((https?://aibreakfast\.beehiiv\.com/p/[^)]+)\)",
        re.S,
    )

    for date_text, title_text, url in pattern.findall(markdown_text or ""):
        url = url.strip()
        if not url or url in seen:
            continue
        published = parse_date_any(date_text, now)
        if not published:
            continue
        if now and published < now - timedelta(days=OFFICIAL_AI_MAX_AGE_DAYS):
            continue

        seen.add(url)
        title = re.sub(r"\s+", " ", title_text).strip()
        out.append(
            RawItem(
                site_id=site_id,
                site_name=site_name,
                source="AI Breakfast",
                title=maybe_fix_mojibake(title),
                url=url,
                published_at=published,
                meta={"feed_home": "https://aibreakfast.beehiiv.com/"},
            )
        )

    return out


def fetch_ai_breakfast(session: requests.Session, now: datetime) -> list[RawItem]:
    resp = session.get(
        AIBREAKFAST_JINA_URL,
        timeout=25,
        headers={
            "User-Agent": BROWSER_UA,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept": "text/plain, */*",
        },
    )
    resp.raise_for_status()
    out = parse_ai_breakfast_items(resp.text, now)
    if not out:
        raise ValueError("No AI Breakfast items parsed")
    return out


def parse_follow_builders_items(feeds: dict[str, dict[str, Any]], now: datetime) -> list[RawItem]:
    site_id = "followbuilders"
    site_name = "Follow Builders"
    out: list[RawItem] = []

    for builder in feeds.get("x", {}).get("x", []) or []:
        name = str(builder.get("name") or builder.get("handle") or "").strip()
        handle = str(builder.get("handle") or "").strip()
        source = f"Follow Builders · X · {name or handle}".strip(" ·")
        for tweet in builder.get("tweets", []) or []:
            text = str(tweet.get("text") or "").strip()
            url = str(tweet.get("url") or "").strip()
            published = parse_date_any(tweet.get("createdAt"), now)
            if not text or not url or not published:
                continue
            title = re.sub(r"\s+", " ", text)
            if len(title) > 220:
                title = title[:217].rstrip() + "..."
            out.append(
                RawItem(
                    site_id=site_id,
                    site_name=site_name,
                    source=source,
                    title=maybe_fix_mojibake(title),
                    url=url,
                    published_at=published,
                    meta={"handle": handle, "feed": "feed-x.json"},
                )
            )

    for article in feeds.get("blogs", {}).get("blogs", []) or []:
        title = str(article.get("title") or "").strip()
        url = str(article.get("url") or "").strip()
        published = parse_date_any(article.get("publishedAt"), now) or parse_date_any(
            feeds.get("blogs", {}).get("generatedAt"), now
        )
        if not title or not url or not published:
            continue
        out.append(
            RawItem(
                site_id=site_id,
                site_name=site_name,
                source=f"Follow Builders · Blog · {article.get('name') or 'Blog'}",
                title=maybe_fix_mojibake(title),
                url=url,
                published_at=published,
                meta={"feed": "feed-blogs.json"},
            )
        )

    for episode in feeds.get("podcasts", {}).get("podcasts", []) or []:
        title = str(episode.get("title") or "").strip()
        url = str(episode.get("url") or "").strip()
        published = parse_date_any(episode.get("publishedAt"), now) or parse_date_any(
            feeds.get("podcasts", {}).get("generatedAt"), now
        )
        if not title or not url or not published:
            continue
        out.append(
            RawItem(
                site_id=site_id,
                site_name=site_name,
                source=f"Follow Builders · Podcast · {episode.get('name') or 'Podcast'}",
                title=maybe_fix_mojibake(title),
                url=url,
                published_at=published,
                meta={"feed": "feed-podcasts.json"},
            )
        )

    return out


def fetch_follow_builders(session: requests.Session, now: datetime) -> list[RawItem]:
    feeds: dict[str, dict[str, Any]] = {}
    for key, filename in (
        ("x", "feed-x.json"),
        ("blogs", "feed-blogs.json"),
        ("podcasts", "feed-podcasts.json"),
    ):
        resp = session.get(
            f"{FOLLOW_BUILDERS_FEED_BASE}/{filename}",
            timeout=20,
            headers={
                "User-Agent": BROWSER_UA,
                "Accept": "application/json, */*",
            },
        )
        resp.raise_for_status()
        feeds[key] = resp.json()

    out = parse_follow_builders_items(feeds, now)
    if not out:
        raise ValueError("No Follow Builders items parsed")
    return out


def is_hubtoday_placeholder_title(title: str) -> bool:
    t = (title or "").strip()
    if not t:
        return True
    if "详情见官方介绍" in t:
        return True
    return t in {"原文链接", "查看详情", "点击查看", "详情"}


def is_hubtoday_generic_anchor_title(title: str) -> bool:
    t = (title or "").strip()
    if not t:
        return True
    if is_hubtoday_placeholder_title(t):
        return True
    return bool(re.search(r"\(AI资讯\)\s*$", t))


def normalize_aihubtoday_records(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_url: dict[str, list[dict[str, Any]]] = {}
    keep: list[dict[str, Any]] = []

    for item in items:
        if str(item.get("site_id") or "") != "aihubtoday":
            keep.append(item)
            continue
        url = normalize_url(str(item.get("url") or ""))
        if not url:
            continue
        by_url.setdefault(url, []).append(item)

    for group in by_url.values():
        if not group:
            continue
        preferred = [g for g in group if not is_hubtoday_generic_anchor_title(str(g.get("title") or ""))]
        source = preferred if preferred else group
        best = max(
            source,
            key=lambda x: (
                event_time(x) or datetime.min.replace(tzinfo=UTC),
                str(x.get("id") or ""),
            ),
        )
        keep.append(best)

    keep.sort(key=lambda x: event_time(x) or datetime.min.replace(tzinfo=UTC), reverse=True)
    return keep


AIHUBTODAY_RSS_URL = "https://hex2077.dev/rss-zh-CN.xml"


def fetch_ai_hubtoday(session: requests.Session, now: datetime) -> list[RawItem]:
    site_id = "aihubtoday"
    site_name = "AI HubToday"
    # ai.hubtoday.app migrated to hex2077.dev (a Next.js SPA), so the old HTML
    # selectors no longer match and produced 0 usable items. Read the site's
    # structured RSS feed instead: every entry has a real title, link and date,
    # which is far more robust than scraping a client-rendered page.
    r = session.get(AIHUBTODAY_RSS_URL, timeout=30)
    r.raise_for_status()
    if feedparser is not None:
        entries = list(feedparser.parse(r.content).entries)
    else:
        entries = parse_feed_entries_via_xml(r.content)

    out: list[RawItem] = []
    seen_urls: set[str] = set()
    for entry in entries:
        title, link, published = feed_entry_title_link_published(entry, now)
        if len(title) < 5 or not link.startswith("http"):
            continue
        if is_hubtoday_placeholder_title(title):
            continue
        key_url = normalize_url(link)
        if key_url in seen_urls:
            continue
        seen_urls.add(key_url)
        out.append(
            RawItem(
                site_id=site_id,
                site_name=site_name,
                source="Daily Digest",
                title=title,
                url=link,
                published_at=published,
                meta={"feed_url": AIHUBTODAY_RSS_URL},
            )
        )
    return out

def fetch_aibase(session: requests.Session, now: datetime) -> list[RawItem]:
    site_id = "aibase"
    site_name = "AIbase"

    r = session.get("https://www.aibase.com/zh/news", timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    out: list[RawItem] = []
    for a in soup.select("a[href^='/news/']"):
        h3 = a.select_one("h3")
        if not h3:
            continue
        title = h3.get_text(" ", strip=True)
        href = a.get("href", "").strip()
        if not title or not href:
            continue

        time_text = ""
        time_tag = a.select_one("div.text-sm.text-gray-400 span")
        if time_tag:
            time_text = time_tag.get_text(" ", strip=True)

        published = parse_date_any(time_text, now)
        out.append(
            RawItem(
                site_id=site_id,
                site_name=site_name,
                source=site_name,
                title=title,
                url=urljoin("https://www.aibase.com", href),
                published_at=published,
                meta={"time_hint": time_text},
            )
        )

    return out


def parse_aihot_feed_items(feed_content: bytes, now: datetime, feed_url: str = AIHOT_FEED_URL) -> list[RawItem]:
    site_id = "aihot"
    site_name = "AI HOT"
    source_name = site_name
    if feedparser is not None:
        parsed = feedparser.parse(feed_content)
        entries = list(parsed.entries)
        source_name = first_non_empty(getattr(parsed, "feed", {}).get("title"), site_name)
    else:
        entries = parse_feed_entries_via_xml(feed_content)

    out: list[RawItem] = []
    seen_urls: set[str] = set()
    for entry in entries:
        title = maybe_fix_mojibake(str(entry.get("title") or "").strip())
        link = str(entry.get("link") or "").strip()
        if not title or not link:
            continue
        normalized_url = normalize_url(link)
        if normalized_url in seen_urls:
            continue
        seen_urls.add(normalized_url)
        published = (
            parse_date_any(entry.get("published"), now)
            or parse_date_any(entry.get("updated"), now)
            or parse_date_any(entry.get("pubDate"), now)
        )
        if not published:
            continue
        author_detail = entry.get("author_detail") or {}
        entry_source = first_non_empty(
            author_detail.get("name") if isinstance(author_detail, dict) else "",
            entry.get("author"),
            source_name,
        )
        out.append(
            RawItem(
                site_id=site_id,
                site_name=site_name,
                source=maybe_fix_mojibake(entry_source),
                title=title,
                url=link,
                published_at=published,
                meta={"feed_url": feed_url},
            )
        )

    return out


def parse_aihot_api_items(payload: dict[str, Any], now: datetime | None = None) -> list[RawItem]:
    site_id = "aihot"
    site_name = "AI HOT"
    out: list[RawItem] = []
    seen_urls: set[str] = set()

    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        return out

    for entry in raw_items:
        if not isinstance(entry, dict):
            continue
        raw_score = entry.get("score")
        if isinstance(raw_score, bool):
            continue
        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            continue
        if score < AIHOT_MIN_SCORE:
            continue

        title = maybe_fix_mojibake(str(first_non_empty(entry.get("title"), entry.get("title_en")) or "").strip())
        link = str(entry.get("url") or "").strip()
        if not title or not link:
            continue
        normalized_url = normalize_url(link)
        if normalized_url in seen_urls:
            continue
        seen_urls.add(normalized_url)

        published = parse_iso(str(entry.get("publishedAt") or "")) or parse_date_any(entry.get("publishedAt"), now)
        source = maybe_fix_mojibake(str(first_non_empty(entry.get("source"), site_name)))
        score_value: int | float = int(score) if score.is_integer() else score
        out.append(
            RawItem(
                site_id=site_id,
                site_name=site_name,
                source=source,
                title=title,
                url=link,
                published_at=published,
                meta={
                    "api_url": AIHOT_ITEMS_API_URL,
                    "aihot_id": entry.get("id"),
                    "aihot_score": score_value,
                    "aihot_category": entry.get("category"),
                    "aihot_selected": bool(entry.get("selected")),
                    "provided_title_zh": entry.get("title"),
                    "provided_title_en": entry.get("title_en"),
                    "summary": entry.get("summary"),
                },
            )
        )

    return out


def fetch_aihot(session: requests.Session, now: datetime) -> list[RawItem]:
    out: list[RawItem] = []
    cursor = ""
    for _ in range(AIHOT_API_MAX_PAGES):
        params: dict[str, Any] = {"mode": "selected", "take": AIHOT_API_TAKE}
        if cursor:
            params["cursor"] = cursor
        r = session.get(
            AIHOT_ITEMS_API_URL,
            timeout=30,
            params=params,
            headers={
                "User-Agent": AIHOT_API_UA,
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept": "application/json",
            },
        )
        r.raise_for_status()
        payload = r.json()
        out.extend(parse_aihot_api_items(payload, now))
        cursor = str(payload.get("nextCursor") or "")
        if not payload.get("hasNext") or not cursor:
            break
    return out




def extract_newsnow_source_ids(js: str) -> list[str]:
    marker = "{v2ex:vL"
    start = js.find(marker)
    if start == -1:
        return ["hackernews", "producthunt", "github", "sspai", "juejin", "36kr"]

    # Locate beginning "{" and parse until matching "}"
    block_start = start
    depth = 0
    end = None
    in_str = False
    esc = False

    for i, ch in enumerate(js[block_start:], block_start):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue

        if ch == '"':
            in_str = True
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end is None:
        return ["hackernews", "producthunt", "github", "sspai", "juejin", "36kr"]

    obj = js[block_start:end]
    all_keys = [m.group(2) for m in re.finditer(r'(["\']?)([a-zA-Z0-9_-]+)\1\s*:', obj)]

    ignore = {
        "name",
        "column",
        "home",
        "https",
        "color",
        "interval",
        "title",
        "type",
        "redirect",
        "desc",
    }

    source_ids: list[str] = []
    for key in all_keys:
        if key in ignore:
            continue
        if key not in source_ids:
            source_ids.append(key)

    # API currently returns around 57 source ids successfully.
    return source_ids


def fetch_newsnow(session: requests.Session, now: datetime) -> list[RawItem]:
    site_id = "newsnow"
    site_name = "NewsNow"

    home = session.get("https://newsnow.busiyi.world/", timeout=30)
    home.raise_for_status()
    soup = BeautifulSoup(home.text, "html.parser")

    bundle = None
    for script in soup.select("script[src]"):
        src = script.get("src", "")
        if "/assets/index-" in src and src.endswith(".js"):
            bundle = urljoin("https://newsnow.busiyi.world/", src)
            break

    source_ids = ["hackernews", "producthunt", "github", "sspai", "juejin", "36kr"]
    if bundle:
        js = session.get(bundle, timeout=30).text
        source_ids = extract_newsnow_source_ids(js)

    headers = {
        "User-Agent": BROWSER_UA,
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://newsnow.busiyi.world",
        "Referer": "https://newsnow.busiyi.world/",
    }

    response = session.post(
        "https://newsnow.busiyi.world/api/s/entire",
        json={"sources": source_ids},
        headers=headers,
        timeout=45,
    )

    if response.status_code != 200:
        # fallback to per-source API
        source_blocks = []
        for sid in source_ids:
            rr = session.get(f"https://newsnow.busiyi.world/api/s?id={sid}", headers=headers, timeout=20)
            if rr.status_code == 200:
                try:
                    source_blocks.append(rr.json())
                except Exception:
                    pass
    else:
        body = response.json()
        source_blocks = body.get("data") if isinstance(body, dict) else body
    if not isinstance(source_blocks, list):
        source_blocks = []

    out: list[RawItem] = []
    for block in source_blocks:
        sid = str(block.get("id") or "unknown")
        source_title = first_non_empty(block.get("title"), block.get("name"), block.get("desc"), sid)
        source_label = f"{source_title} ({sid})" if source_title != sid else sid
        updated = parse_unix_timestamp(block.get("updatedTime")) or now
        items = block.get("items") or []
        for it in items:
            title = str(it.get("title") or "").strip()
            url = str(it.get("url") or "").strip()
            if not title or not url:
                continue

            published = None
            published = published or parse_date_any(it.get("pubDate"), now)
            if not published:
                extra = it.get("extra") or {}
                if isinstance(extra, dict):
                    published = parse_date_any(extra.get("date"), now)
            if not published:
                published = updated

            out.append(
                RawItem(
                    site_id=site_id,
                    site_name=site_name,
                    source=source_label,
                    title=title,
                    url=url,
                    published_at=published,
                    meta={},
                )
            )

    return out


def collect_all(session: requests.Session, now: datetime) -> tuple[list[RawItem], list[dict[str, Any]]]:
    tasks = [
        ("official_ai", "Official AI Updates", fetch_official_ai_updates),
        ("curated_media", "Curated Media", fetch_curated_ai_media),
        ("aibreakfast", "AI Breakfast", fetch_ai_breakfast),
        ("followbuilders", "Follow Builders", fetch_follow_builders),
        ("techurls", "TechURLs", fetch_techurls),
        ("buzzing", "Buzzing", fetch_buzzing),
        ("iris", "Info Flow", fetch_iris),
        ("bestblogs", "BestBlogs", fetch_bestblogs),
        ("zeli", "Zeli", fetch_zeli),
        ("hackernews", "Hacker News", fetch_hacker_news_algolia),
        ("aihubtoday", "AI HubToday", fetch_ai_hubtoday),
        ("aibase", "AIbase", fetch_aibase),
        ("aihot", "AI HOT", fetch_aihot),
        ("newsnow", "NewsNow", fetch_newsnow),
    ]

    raw_items: list[RawItem] = []
    statuses: list[dict[str, Any]] = []

    for site_id, site_name, fn in tasks:
        start = time.perf_counter()
        error = None
        count = 0
        try:
            items = fn(session, now)
            count = len(items)
            raw_items.extend(items)
        except Exception as exc:
            error = str(exc)
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        statuses.append(
            {
                "site_id": site_id,
                "site_name": site_name,
                "ok": error is None,
                "item_count": count,
                "duration_ms": elapsed_ms,
                "error": error,
            }
        )

    return raw_items, statuses


def parse_opml_subscriptions(opml_path: Path) -> list[dict[str, str]]:
    root = ET.parse(opml_path).getroot()
    out: list[dict[str, str]] = []
    seen: set[str] = set()

    for outline in root.findall(".//outline"):
        xml_url = str(outline.attrib.get("xmlUrl") or "").strip()
        if not xml_url:
            continue
        if xml_url in seen:
            continue
        seen.add(xml_url)
        title = first_non_empty(
            outline.attrib.get("title"),
            outline.attrib.get("text"),
            host_of_url(xml_url),
            xml_url,
        )
        html_url = str(outline.attrib.get("htmlUrl") or "").strip()
        out.append(
            {
                "title": title,
                "xml_url": xml_url,
                "html_url": html_url,
            }
        )
    return out


def resolve_official_rss_url(feed_url: str) -> tuple[str | None, str | None]:
    src = (feed_url or "").strip()
    if not src:
        return None, "empty_url"
    if src in RSS_FEED_SKIP_EXACT:
        return None, "no_official_rss_or_unreachable"
    for prefix in RSS_FEED_SKIP_PREFIXES:
        if src.startswith(prefix):
            return None, "no_official_rss_for_source_type"
    replaced = RSS_FEED_REPLACEMENTS.get(src)
    if replaced:
        return replaced, "official_replacement"
    return src, None


def resolve_opml_bridge_source(feed_url: str, html_url: str = "") -> dict[str, str] | None:
    src = (feed_url or "").strip()
    parsed = urlparse(src)
    path = parsed.path.strip("/")
    parts = [p for p in path.split("/") if p]

    if parsed.netloc == "rsshub.app" and len(parts) >= 3 and parts[:2] == ["telegram", "channel"]:
        slug = parts[2]
        return {
            "bridge_type": "telegram",
            "bridge_slug": slug,
            "url": f"https://t.me/s/{slug}",
        }

    if parsed.netloc == "rsshub.app" and len(parts) >= 3 and parts[0] == "jike":
        kind = parts[1]
        ident = parts[2]
        if kind == "topic":
            return {
                "bridge_type": "jike",
                "bridge_kind": "topic",
                "bridge_slug": ident,
                "url": f"https://m.okjike.com/topics/{ident}",
            }
        if kind == "user":
            return {
                "bridge_type": "jike",
                "bridge_kind": "user",
                "bridge_slug": ident,
                "url": f"https://m.okjike.com/users/{ident}",
            }

    html = (html_url or "").strip()
    if html.startswith("https://t.me/s/"):
        slug = html.rstrip("/").split("/")[-1]
        return {"bridge_type": "telegram", "bridge_slug": slug, "url": html}
    if html.startswith("https://m.okjike.com/topics/"):
        ident = html.rstrip("/").split("/")[-1]
        return {"bridge_type": "jike", "bridge_kind": "topic", "bridge_slug": ident, "url": html}
    if html.startswith("https://m.okjike.com/users/"):
        ident = html.rstrip("/").split("/")[-1]
        return {"bridge_type": "jike", "bridge_kind": "user", "bridge_slug": ident, "url": html}

    return None


def compact_title(text: str, limit: int = 96) -> str:
    s = re.sub(r"\s+", " ", text or "").strip()
    if len(s) <= limit:
        return s
    return s[: limit - 1].rstrip() + "…"


def parse_telegram_public_items(
    html: str,
    *,
    now: datetime,
    source_name: str,
    slug: str,
) -> list[RawItem]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[RawItem] = []
    for msg in soup.select(".tgme_widget_message"):
        data_post = str(msg.get("data-post") or "").strip()
        if not data_post:
            continue
        text_node = msg.select_one(".tgme_widget_message_text")
        text = text_node.get_text(" ", strip=True) if text_node else ""
        if not text:
            preview_title = msg.select_one(".tgme_widget_message_link_preview_title")
            text = preview_title.get_text(" ", strip=True) if preview_title else ""
        if not text:
            continue
        time_node = msg.select_one("time[datetime]")
        published = parse_date_any(time_node.get("datetime") if time_node else None, now)
        if not published:
            continue
        url = f"https://t.me/{data_post}"
        out.append(
            RawItem(
                site_id="opmlrss",
                site_name="OPML RSS",
                source=source_name,
                title=compact_title(text),
                url=url,
                published_at=published,
                meta={"bridge_type": "telegram", "bridge_slug": slug, "feed_home": f"https://t.me/s/{slug}"},
            )
        )
    return out


def parse_jike_public_items(
    html: str,
    *,
    now: datetime,
    source_name: str,
    source_url: str,
) -> list[RawItem]:
    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    if script is None or not script.string:
        return []
    try:
        payload = json.loads(script.string)
    except Exception:
        return []
    page_props = payload.get("props", {}).get("pageProps", {})
    posts = page_props.get("posts") or []
    out: list[RawItem] = []
    for post in posts:
        if not isinstance(post, dict):
            continue
        post_id = str(post.get("id") or "").strip()
        text = str(post.get("content") or "").strip()
        if not post_id or not text:
            continue
        published = parse_date_any(post.get("createdAt") or post.get("actionTime"), now)
        if not published:
            continue
        out.append(
            RawItem(
                site_id="opmlrss",
                site_name="OPML RSS",
                source=source_name,
                title=compact_title(text),
                url=f"https://m.okjike.com/originalPosts/{post_id}",
                published_at=published,
                meta={"bridge_type": "jike", "feed_home": source_url},
            )
        )
    return out


def fetch_opml_rss(
    now: datetime,
    opml_path: Path,
    max_feeds: int = 0,
) -> tuple[list[RawItem], dict[str, Any], list[dict[str, Any]]]:
    feeds = parse_opml_subscriptions(opml_path)
    if max_feeds > 0:
        feeds = feeds[:max_feeds]

    out: list[RawItem] = []
    feed_statuses: list[dict[str, Any]] = []
    resolved_feeds: list[dict[str, str]] = []

    for feed in feeds:
        original_url = feed["xml_url"]
        bridge = resolve_opml_bridge_source(original_url, feed.get("html_url") or "")
        if bridge:
            record = dict(feed)
            record["xml_url_original"] = original_url
            record["xml_url"] = bridge["url"]
            record["replaced"] = True
            record.update(bridge)
            resolved_feeds.append(record)
            continue

        resolved_url, skip_reason = resolve_official_rss_url(original_url)
        if not resolved_url:
            feed_id = hashlib.sha1(original_url.encode("utf-8")).hexdigest()[:10]
            feed_statuses.append(
                {
                    "site_id": f"opmlrss:{feed_id}",
                    "site_name": "OPML RSS",
                    "feed_title": feed["title"],
                    "feed_url": original_url,
                    "effective_feed_url": None,
                    "ok": True,
                    "item_count": 0,
                    "duration_ms": 0,
                    "error": None,
                    "skipped": True,
                    "skip_reason": skip_reason or "skipped",
                    "replaced": False,
                }
            )
            continue
        record = dict(feed)
        record["xml_url_original"] = original_url
        record["xml_url"] = resolved_url
        record["replaced"] = bool(resolved_url != original_url)
        resolved_feeds.append(record)

    def fetch_single_feed(feed: dict[str, str]) -> tuple[list[RawItem], dict[str, Any]]:
        feed_url = feed["xml_url"]
        original_feed_url = str(feed.get("xml_url_original") or feed_url)
        feed_title = feed["title"]
        feed_id = hashlib.sha1(feed_url.encode("utf-8")).hexdigest()[:10]
        start = time.perf_counter()
        error = None
        local_items: list[RawItem] = []

        try:
            resp = requests.get(
                feed_url,
                timeout=12,
                headers={
                    "User-Agent": BROWSER_UA,
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                },
            )
            resp.raise_for_status()

            bridge_type = str(feed.get("bridge_type") or "")
            if bridge_type == "telegram":
                local_items = parse_telegram_public_items(
                    resp.text,
                    now=now,
                    source_name=feed_title,
                    slug=str(feed.get("bridge_slug") or ""),
                )
            elif bridge_type == "jike":
                local_items = parse_jike_public_items(
                    resp.text,
                    now=now,
                    source_name=feed_title,
                    source_url=feed_url,
                )
            elif feedparser is not None:
                parsed = feedparser.parse(resp.content)
                source_name = first_non_empty(
                    feed_title,
                    getattr(parsed, "feed", {}).get("title"),
                    host_of_url(feed_url),
                )
                entries = parsed.entries
                cn_feed = ".cn/" in feed_url or feed_url.endswith(".cn") or has_cjk(str(feed_title or ""))
                pending: list[tuple[str, str, datetime]] = []
                for entry in entries:
                    title = str(entry.get("title", "")).strip()
                    link = str(entry.get("link", "")).strip()
                    if not title or not link:
                        continue
                    published = (
                        parse_date_any(entry.get("published"), now)
                        or parse_date_any(entry.get("updated"), now)
                        or parse_date_any(entry.get("pubDate"), now)
                    )
                    if not published:
                        continue
                    pending.append((title, link, published))
                corrected_times = correct_feed_published_batch(
                    [p for _, _, p in pending],
                    now,
                    assume_cst_mislabel=cn_feed or any(has_cjk(t) for t, _, _ in pending),
                )
                for (title, link, _), published in zip(pending, corrected_times):
                    local_items.append(
                        RawItem(
                            site_id="opmlrss",
                            site_name="OPML RSS",
                            source=source_name,
                            title=title,
                            url=link,
                            published_at=published,
                            meta={
                                "feed_url": feed_url,
                                "feed_home": feed.get("html_url") or "",
                            },
                        )
                    )
            else:
                source_name = first_non_empty(feed_title, host_of_url(feed_url))
                entries = parse_feed_entries_via_xml(resp.content)
                cn_feed = ".cn/" in feed_url or feed_url.endswith(".cn") or has_cjk(str(feed_title or ""))
                pending_xml: list[tuple[dict[str, str], datetime]] = []
                for entry in entries:
                    published = parse_date_any(entry.get("published"), now)
                    if not published:
                        continue
                    pending_xml.append((entry, published))
                corrected_times = correct_feed_published_batch(
                    [p for _, p in pending_xml],
                    now,
                    assume_cst_mislabel=cn_feed
                    or any(has_cjk(str(e.get("title") or "")) for e, _ in pending_xml),
                )
                for (entry, _), published in zip(pending_xml, corrected_times):
                    local_items.append(
                        RawItem(
                            site_id="opmlrss",
                            site_name="OPML RSS",
                            source=source_name,
                            title=entry.get("title", ""),
                            url=entry.get("link", ""),
                            published_at=published,
                            meta={
                                "feed_url": feed_url,
                                "feed_home": feed.get("html_url") or "",
                            },
                        )
                    )
        except Exception as exc:
            error = str(exc)

        duration_ms = int((time.perf_counter() - start) * 1000)
        status = {
            "site_id": f"opmlrss:{feed_id}",
            "site_name": "OPML RSS",
            "feed_title": feed_title,
            "feed_url": original_feed_url,
            "effective_feed_url": feed_url,
            "ok": error is None,
            "item_count": len(local_items),
            "duration_ms": duration_ms,
            "error": error,
            "skipped": False,
            "skip_reason": None,
            "replaced": bool(original_feed_url != feed_url),
            "bridge_type": feed.get("bridge_type"),
        }
        return local_items, status

    if resolved_feeds:
        worker_count = min(20, max(4, len(resolved_feeds)))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [executor.submit(fetch_single_feed, feed) for feed in resolved_feeds]
            for future in as_completed(futures):
                items, status = future.result()
                out.extend(items)
                feed_statuses.append(status)

    feed_statuses.sort(key=lambda x: str(x.get("feed_title") or x.get("feed_url") or ""))
    total_duration_ms = sum(int(s.get("duration_ms") or 0) for s in feed_statuses)
    ok_feeds = sum(1 for s in feed_statuses if s["ok"])
    failed_feeds = sum(1 for s in feed_statuses if not s["ok"])
    skipped_feeds = sum(1 for s in feed_statuses if s.get("skipped"))
    replaced_feeds = sum(1 for s in feed_statuses if s.get("replaced"))

    summary_status = {
        "site_id": "opmlrss",
        "site_name": "OPML RSS",
        "ok": ok_feeds > 0,
        "partial_failures": failed_feeds,
        "item_count": len(out),
        "duration_ms": total_duration_ms,
        "error": None if failed_feeds == 0 else f"{failed_feeds} feeds failed",
        "feed_count": len(feeds),
        "effective_feed_count": len(resolved_feeds),
        "ok_feed_count": ok_feeds,
        "failed_feed_count": failed_feeds,
        "skipped_feed_count": skipped_feeds,
        "replaced_feed_count": replaced_feeds,
    }
    return out, summary_status, feed_statuses


def load_archive(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    items = payload.get("items", [])
    out: dict[str, dict[str, Any]] = {}
    if isinstance(items, list):
        for it in items:
            item_id = it.get("id")
            if item_id:
                out[item_id] = it
    elif isinstance(items, dict):
        for item_id, it in items.items():
            if isinstance(it, dict):
                it["id"] = item_id
                out[item_id] = it
    return out


def event_time(record: dict[str, Any]) -> datetime | None:
    # RSS sources must rely on the source's publish time only.
    # first_seen_at is fetch time and would falsely mark historical items as "24h".
    if str(record.get("site_id") or "") == "opmlrss":
        return parse_iso(record.get("published_at"))
    return parse_iso(record.get("published_at")) or parse_iso(record.get("first_seen_at"))


SOURCE_TIER_BY_SITE: dict[str, tuple[str, str, int]] = {
    "official_ai": ("official", "官方一手源", 0),
    "curated_media": ("ai_media", "精选AI媒体", 2),
    "aibreakfast": ("ai_vertical", "AI垂直源", 1),
    "aihubtoday": ("ai_vertical", "AI垂直源", 1),
    "aibase": ("ai_vertical", "AI垂直源", 1),
    "aihot": ("ai_vertical", "AI垂直源", 1),
    "bestblogs": ("ai_vertical", "AI垂直源", 1),
    "waytoagi": ("community", "社区更新", 2),
    "followbuilders": ("builders", "Builders/X源", 2),
    "opmlrss": ("user_opml", "RSS/OPML", 3),
    "tikhub_douyin": ("self_media", "自媒体源", 4),
    "tikhub_xiaohongshu": ("self_media", "自媒体源", 4),
    "xapi": ("advanced", "高级源", 4),
    "socialdata_x": ("advanced", "高级源", 4),
    "techurls": ("discussion", "热议参考", 5),
    "buzzing": ("discussion", "热议参考", 5),
    "iris": ("discussion", "热议参考", 5),
    "zeli": ("discussion", "热议参考", 5),
    "hackernews": ("discussion", "热议参考", 5),
    "newsnow": ("discussion", "热议参考", 5),
}

SOURCE_TIER_IMPORTANCE = {
    "official": 1.0,
    "ai_vertical": 0.78,
    "ai_media": 0.58,
    "community": 0.54,
    "builders": 0.62,
    "user_opml": 0.5,
    "self_media": 0.48,
    "advanced": 0.45,
    "discussion": 0.32,
    "other": 0.25,
}

# ---------------------------------------------------------------------------
# aihot first-party source override
# ---------------------------------------------------------------------------
# Items from aihot that originate from official company channels (not individual
# analysts/bloggers) should be promoted to the "official" tier.  The strings
# below are exact ``source`` field values as returned by the aihot public API.
AIHOT_FIRST_PARTY_SOURCE_NAMES: frozenset[str] = frozenset({
    # --- OpenAI ---
    "OpenAI：官网动态（RSS · 排除企业/客户案例）",
    "X：OpenAI Developers (@OpenAIDevs)",
    "X：ChatGPT (@ChatGPTapp)",
    # --- Anthropic ---
    "Anthropic：Newsroom（网页）",
    "Claude Code：GitHub Releases（RSS）",
    "X：Claude Devs (@ClaudeDevs)",
    # --- Google ---
    "Google Developers Blog（RSS）",
    "Google Research：Blog（网页）",
    "X：Google DeepMind (@GoogleDeepMind)",
    "X：NotebookLM (@NotebookLM)",
    # --- Meta ---
    "X：AI at Meta (@AIatMeta)",
    # --- Mistral ---
    "Mistral AI：News（网页）",
    # --- Hugging Face ---
    "Hugging Face：Blog（RSS）",
    "HuggingFace Daily Papers（社区热门论文）",
    # --- Perplexity ---
    "X：Perplexity (@perplexity_ai)",
    # --- Runway ---
    "X：Runway (@runwayml)",
    # --- Alibaba / Qwen ---
    "X：阿里云 / Alibaba Cloud (@alibaba_cloud)",
    # --- ByteDance / Kling ---
    "X：可灵 Kling AI (@Kling_ai)",
})


def source_tier_for_record(site_id: str, source: str) -> tuple[str, str, int] | None:
    """Return ``("official", "官方一手源", 0)`` when an aihot item comes from a
    known first-party company channel, otherwise ``None`` (caller falls through
    to the global ``SOURCE_TIER_BY_SITE`` lookup)."""
    if site_id != "aihot":
        return None
    src = source.strip()
    if src in AIHOT_FIRST_PARTY_SOURCE_NAMES:
        return ("official", "官方一手源", 0)
    return None


TITLE_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "for",
    "from",
    "in",
    "into",
    "is",
    "new",
    "of",
    "on",
    "the",
    "to",
    "with",
    "发布",
    "推出",
    "上线",
    "更新",
}

VENDOR_ALIASES = {
    "openai": "openai",
    "anthropic": "anthropic",
    "claude": "anthropic",
    "google": "google",
    "deepmind": "google",
    "gemini": "google",
    "microsoft": "microsoft",
    "github": "github",
    "huggingface": "huggingface",
    "hugging face": "huggingface",
    "meta": "meta",
    "llama": "meta",
    "deepseek": "deepseek",
    "mistral": "mistral",
    "xai": "xai",
    "grok": "xai",
}

MODEL_RE = re.compile(
    r"(?i)\b("
    r"gpt[-\s]?\d+(?:\.\d+)?[a-z]*|"
    r"claude(?:[-\s]?(?:opus|sonnet|haiku))?[-\s]?\d+(?:\.\d+)?|"
    r"gemini[-\s]?\d+(?:\.\d+)?|"
    r"llama[-\s]?\d+(?:\.\d+)?|"
    r"deepseek[-\s]?[a-z0-9.]+|"
    r"grok[-\s]?\d+(?:\.\d+)?|"
    r"mistral[-\s]?[a-z0-9.]+"
    r")\b"
)


def source_tier_for_site(site_id: str) -> dict[str, Any]:
    sid = str(site_id or "").strip().lower()
    if sid.startswith("opmlrss"):
        sid = "opmlrss"
    tier, label, rank = SOURCE_TIER_BY_SITE.get(sid, ("other", "其他来源", 9))
    return {"source_tier": tier, "source_tier_label": label, "source_tier_rank": rank}


def add_source_tier_fields(record: dict[str, Any]) -> dict[str, Any]:
    out = dict(record)
    site_id = str(out.get("site_id") or "")
    # For aihot items, check if the source is a known first-party channel first
    override = source_tier_for_record(site_id, str(out.get("source") or ""))
    if override is not None:
        tier, label, rank = override
        out["source_tier"] = tier
        out["source_tier_label"] = label
        out["source_tier_rank"] = rank
    else:
        out.update(source_tier_for_site(site_id))
    return out


def source_tier_sort_key(record: dict[str, Any]) -> tuple[int, float, str]:
    tier = source_tier_for_site(str(record.get("site_id") or ""))
    ts = event_time(record)
    return (int(tier["source_tier_rank"]), -(ts.timestamp() if ts else 0), str(record.get("title") or ""))


AI_KEYWORDS = [
    "aigc",
    "llm",
    "gpt",
    "claude",
    "gemini",
    "deepseek",
    "openai",
    "anthropic",
    "copilot",
    "codex",
    "mcp",
    "hugging face",
    "huggingface",
    "transformer",
    "prompt",
    "diffusion",
    "agent",
    "多模态",
    "大模型",
    "模型",
    "人工智能",
    "机器学习",
    "深度学习",
    "智能体",
    "算力",
    "推理",
    "微调",
]

TECH_KEYWORDS = [
    "robot",
    "robotics",
    "embodied",
    "autonomous",
    "vision",
    "chip",
    "semiconductor",
    "cuda",
    "npu",
    "gpu",
    "cloud",
    "developer",
    "开源",
    "技术",
    "编程",
    "软件",
    "芯片",
    "机器人",
    "具身",
]

NOISE_KEYWORDS = [
    "娱乐",
    "明星",
    "八卦",
    "足球",
    "篮球",
    "彩票",
    "情感",
    "旅游",
    "美食",
]

COMMERCE_NOISE_KEYWORDS = [
    "淘宝",
    "天猫",
    "京东",
    "拼多多",
    "券后",
    "热销总榜",
    "促销",
    "优惠",
    "补贴",
    "下单",
    "首发价",
]

EN_SIGNAL_RE = re.compile(
    r"(?i)(?<![a-z0-9])(ai|aigc|llm|gpt|openai|anthropic|deepseek|gemini|claude|robot|robotics|embodied|autonomous|machine learning|artificial intelligence|transformer|diffusion|agent)(?![a-z0-9])"
)

MEANINGFUL_EN_SIGNAL_RE = re.compile(
    r"(?i)(?<![a-z0-9])(ai|aigc|llm|gpt|openai|anthropic|deepseek|gemini|claude|robot|robotics|embodied|autonomous|machine learning|artificial intelligence|transformer|diffusion)(?![a-z0-9])"
)
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
SECRET_LIKE_RE = re.compile(r"\b(sk-(?!hynix\b)[A-Za-z0-9_-]{12,}|(?:api[_-]?key|secret|token)=([^\s&]{6,}))\b", re.I)
BROAD_AI_TERMS = {"agent", "模型", "推理"}


def contains_any_keyword(haystack: str, keywords: list[str]) -> bool:
    h = haystack.lower()
    return any(k in h for k in keywords)


def contains_meaningful_ai_signal(haystack: str) -> bool:
    h = haystack.lower()
    if MEANINGFUL_EN_SIGNAL_RE.search(h):
        return True
    return any(k in h for k in AI_KEYWORDS if k not in BROAD_AI_TERMS)


def redact_public_text(text: str) -> str:
    if not isinstance(text, str) or not text:
        return text
    text = EMAIL_RE.sub("[redacted-email]", text)
    return SECRET_LIKE_RE.sub("[redacted-secret]", text)


def sanitize_public_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_public_text(value)
    if isinstance(value, list):
        return [sanitize_public_value(item) for item in value]
    if isinstance(value, dict):
        return {key: sanitize_public_value(val) for key, val in value.items()}
    return value


def sanitize_public_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return sanitize_public_value(payload)


def compact_public_snippet(text: str, max_chars: int = 240) -> str:
    """Return a short redacted snippet suitable for public/static JSON."""
    snippet = re.sub(r"\s+", " ", str(text or "")).strip()
    snippet = redact_public_text(snippet)
    if len(snippet) <= max_chars:
        return snippet
    return snippet[: max_chars - 1].rstrip() + "…"


def sender_domain_from_address(raw_sender: str) -> str | None:
    """Extract only the sender domain; never expose the raw email address."""
    _, email_addr = parseaddr(str(raw_sender or ""))
    if "@" not in email_addr:
        return None
    domain = email_addr.rsplit("@", 1)[-1].strip().lower().strip(">")
    return domain or None


def parse_domain_filter(raw: str) -> list[str]:
    """Parse a comma-separated sender-domain allowlist for private newsletter demos."""
    domains: list[str] = []
    for part in re.split(r"[,\s]+", str(raw or "")):
        domain = part.strip().lower().lstrip("@")
        if domain and re.match(r"^[a-z0-9.-]+\.[a-z]{2,}$", domain):
            domains.append(domain)
    return sorted(set(domains))


def domain_matches_filter(sender_domain: str | None, allowed_domains: list[str]) -> bool:
    if not allowed_domains:
        return True
    domain = str(sender_domain or "").lower().strip()
    return any(domain == allowed or domain.endswith(f".{allowed}") for allowed in allowed_domains)


def filter_agentmail_messages_by_domain(
    messages: list[dict[str, Any]],
    allowed_domains: list[str],
) -> list[dict[str, Any]]:
    if not allowed_domains:
        return messages
    return [
        msg
        for msg in messages
        if domain_matches_filter(agentmail_sender_domain(msg), allowed_domains)
    ]


def agentmail_sender_domain(message: dict[str, Any]) -> str | None:
    sender = message.get("from")
    if isinstance(sender, dict):
        return sender_domain_from_address(str(sender.get("email") or ""))
    return sender_domain_from_address(str(sender or ""))


def agentmail_message_timestamp(message: dict[str, Any]) -> Any:
    return message.get("timestamp") or message.get("created_at") or message.get("received_at")


def agentmail_message_preview(message: dict[str, Any]) -> str:
    return str(message.get("preview") or message.get("snippet") or "")


def agentmail_message_id(message: dict[str, Any]) -> str:
    return str(message.get("message_id") or message.get("id") or "").strip()


def clean_agentmail_public_url(raw_url: Any) -> str:
    """Return a public, browser-openable newsletter URL without common tracking params."""
    url = str(raw_url or "").strip()
    if not url:
        return ""
    url = url.replace("&amp;", "&")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    decoded_path = unquote(parsed.path)
    nested_match = re.search(r"https?://[^/\s]+[^\s]*", decoded_path)
    if nested_match and parsed.netloc.lower().startswith("tracking."):
        return clean_agentmail_public_url(nested_match.group(0))
    host = parsed.netloc.lower()
    if any(host == blocked or host.endswith(f".{blocked}") for blocked in AGENTMAIL_PUBLIC_URL_REJECT_HOSTS):
        return ""
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in AGENTMAIL_TRACKING_QUERY_KEYS
        and not any(key.lower().startswith(prefix) for prefix in AGENTMAIL_TRACKING_QUERY_PREFIXES)
    ]
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            urlencode(query, doseq=True),
            "",
        )
    )


def agentmail_explicit_public_url(message: dict[str, Any]) -> str:
    """Use URL-like fields from list/API metadata when providers expose them."""
    for key in ("public_url", "web_url", "permalink", "archive_url", "url"):
        cleaned = clean_agentmail_public_url(message.get(key))
        if cleaned:
            return cleaned
    links = message.get("links")
    candidates: list[Any] = []
    if isinstance(links, dict):
        candidates.extend(links.values())
    elif isinstance(links, list):
        candidates.extend(links)
    for link in candidates:
        if isinstance(link, dict):
            cleaned = clean_agentmail_public_url(link.get("url") or link.get("href"))
        else:
            cleaned = clean_agentmail_public_url(link)
        if cleaned:
            return cleaned
    return ""


def score_agentmail_public_link(text: str, url: str) -> int:
    cleaned = clean_agentmail_public_url(url)
    if not cleaned:
        return -100
    label = re.sub(r"\s+", " ", str(text or "")).strip()
    if AGENTMAIL_PUBLIC_LINK_REJECT_RE.search(label) or AGENTMAIL_PUBLIC_LINK_REJECT_RE.search(cleaned):
        return -100
    host = urlparse(cleaned).netloc.lower()
    score = 0
    if AGENTMAIL_PUBLIC_LINK_TEXT_RE.search(label):
        score += 100
    if "link.mail.beehiiv.com" in host or "substack.com" in host:
        score += 15
    if "youtube.com" in host or "youtu.be" in host or "linkedin.com" in host:
        score -= 20
    if label and label.lower().strip() in {"read more", "read the full issue", "continue reading"}:
        score += 40
    return score


def extract_agentmail_public_url_from_body(body: str) -> str:
    """Extract a public newsletter issue URL from a message body without storing the body."""
    html = str(body or "")
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[tuple[int, str]] = []
    for anchor in soup.find_all("a"):
        href = anchor.get("href")
        if not href:
            continue
        text = anchor.get_text(" ", strip=True)
        cleaned = clean_agentmail_public_url(href)
        score = score_agentmail_public_link(text, cleaned)
        if score > 0:
            candidates.append((score, cleaned))
    if not candidates:
        for raw_url in re.findall(r"https?://[^\s\"'<>]+", html):
            cleaned = clean_agentmail_public_url(raw_url)
            score = score_agentmail_public_link("", cleaned)
            if score > 0:
                candidates.append((score, cleaned))
    if not candidates:
        return ""
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def read_agentmail_public_url_via_cli(message_id: str, cli_path: str = AGENTMAIL_CLI_DEFAULT) -> str:
    """Read one message only to extract a public newsletter URL; body is never returned or stored."""
    if not message_id:
        return ""
    command = [cli_path or AGENTMAIL_CLI_DEFAULT, "message", "+read", "--id", message_id]
    completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=45)
    if completed.returncode != 0:
        return ""
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    try:
        payload = extract_json_object_from_cli_output(output)
    except Exception:
        return ""
    data = payload.get("data") if isinstance(payload, dict) else {}
    if not isinstance(data, dict):
        data = {}
    explicit = agentmail_explicit_public_url(data)
    if explicit:
        return explicit
    return extract_agentmail_public_url_from_body(str(data.get("body") or ""))


def enrich_agentmail_messages_with_public_urls(
    messages: list[dict[str, Any]],
    *,
    cli_path: str = AGENTMAIL_CLI_DEFAULT,
    resolve_public_urls: bool = False,
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for message in messages:
        copy = dict(message)
        public_url = agentmail_explicit_public_url(copy)
        if not public_url and resolve_public_urls:
            public_url = read_agentmail_public_url_via_cli(agentmail_message_id(copy), cli_path=cli_path)
        if public_url:
            copy["public_url"] = public_url
        enriched.append(copy)
    return enriched


def safe_agentmail_item(message: dict[str, Any]) -> dict[str, Any]:
    """Convert an AgentMail MessageItem into a metadata-only public digest item."""
    message_id = agentmail_message_id(message)
    stable_id = hashlib.sha1(message_id.encode("utf-8")).hexdigest()[:12] if message_id else "unknown"
    domain = agentmail_sender_domain(message)
    attachments = message.get("attachments") or []
    if not isinstance(attachments, list):
        attachments = []
    item = {
        "id": f"agentmail:{stable_id}",
        "source_type": "email_newsletter",
        "source": f"AgentMail · {domain}" if domain else "AgentMail",
        "sender_domain": domain,
        "subject": compact_public_snippet(str(message.get("subject") or ""), max_chars=180),
        "preview": compact_public_snippet(agentmail_message_preview(message), max_chars=240),
        "received_at": agentmail_message_timestamp(message),
        "has_attachments": bool(attachments),
        "attachment_count": len(attachments),
    }
    public_url = clean_agentmail_public_url(message.get("public_url"))
    if public_url:
        item["public_url"] = public_url
    return item


def build_agentmail_digest_payload(
    messages: list[dict[str, Any]],
    generated_at: str,
    window_hours: int,
    allowed_sender_domains: list[str] | None = None,
) -> dict[str, Any]:
    """Build a privacy-preserving digest from AgentMail list-message results."""
    filtered_messages = filter_agentmail_messages_by_domain(messages, allowed_sender_domains or [])
    items = [safe_agentmail_item(msg) for msg in filtered_messages]
    return sanitize_public_payload(
        {
            "generated_at": generated_at,
            "source": "agentmail",
            "enabled": True,
            "window_hours": window_hours,
            "privacy": "metadata_only_no_body",
            "allowed_sender_domains": allowed_sender_domains or [],
            "total_messages": len(items),
            "items": items,
        }
    )


def fetch_agentmail_digest(
    session: requests.Session,
    api_key: str,
    inbox_id: str,
    generated_at: str,
    after: str,
    limit: int = AGENTMAIL_DEFAULT_LIMIT,
    base_url: str = AGENTMAIL_API_BASE_DEFAULT,
    window_hours: int = 24,
    allowed_sender_domains: list[str] | None = None,
) -> dict[str, Any]:
    """Fetch AgentMail MessageItem metadata; deliberately does not request bodies or raw .eml."""
    base = (base_url or AGENTMAIL_API_BASE_DEFAULT).rstrip("/")
    url = f"{base}/v0/inboxes/{inbox_id}/messages"
    response = session.get(
        url,
        headers={"Authorization": f"Bearer {api_key}"},
        params={
            "limit": max(1, min(int(limit or AGENTMAIL_DEFAULT_LIMIT), 100)),
            "after": after,
            "ascending": "false",
            "include_spam": "false",
            "include_trash": "false",
            "include_blocked": "false",
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    messages = payload.get("messages") if isinstance(payload, dict) else []
    if not isinstance(messages, list):
        messages = []
    return build_agentmail_digest_payload(
        messages,
        generated_at=generated_at,
        window_hours=window_hours,
        allowed_sender_domains=allowed_sender_domains,
    )


def extract_json_object_from_cli_output(output: str) -> dict[str, Any]:
    """Parse a JSON envelope from CLI output that may include tip lines."""
    text = str(output or "")
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON object found in agently-cli output")
    parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("agently-cli output is not a JSON object")
    return parsed


def extract_agently_cli_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data") if isinstance(payload, dict) else {}
    if isinstance(data, dict):
        inner = data.get("data")
        if isinstance(inner, list):
            return [msg for msg in inner if isinstance(msg, dict)]
        messages = data.get("messages")
        if isinstance(messages, list):
            return [msg for msg in messages if isinstance(msg, dict)]
    messages = payload.get("messages") if isinstance(payload, dict) else []
    if isinstance(messages, list):
        return [msg for msg in messages if isinstance(msg, dict)]
    return []


def fetch_agentmail_digest_via_cli(
    *,
    generated_at: str,
    after: str,
    limit: int = AGENTMAIL_DEFAULT_LIMIT,
    cli_path: str = AGENTMAIL_CLI_DEFAULT,
    window_hours: int = 24,
    allowed_sender_domains: list[str] | None = None,
    resolve_public_urls: bool = False,
) -> dict[str, Any]:
    """Fetch QQ Agent Mail metadata through agently-cli; never reads message bodies."""
    command = [
        cli_path or AGENTMAIL_CLI_DEFAULT,
        "message",
        "+list",
        "--dir",
        "inbox",
        "--limit",
        str(max(1, min(int(limit or AGENTMAIL_DEFAULT_LIMIT), 100))),
        "--after",
        after,
    ]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=45,
    )
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    if completed.returncode != 0:
        raise RuntimeError(f"agently-cli exited with {completed.returncode}")
    payload = extract_json_object_from_cli_output(output)
    if payload.get("ok") is False:
        raise RuntimeError("agently-cli returned ok=false")
    messages = extract_agently_cli_messages(payload)
    messages = enrich_agentmail_messages_with_public_urls(
        messages,
        cli_path=cli_path,
        resolve_public_urls=resolve_public_urls,
    )
    return build_agentmail_digest_payload(
        messages,
        generated_at=generated_at,
        window_hours=window_hours,
        allowed_sender_domains=allowed_sender_domains,
    )


def agentmail_digest_items_to_raw_items(payload: dict[str, Any]) -> list[RawItem]:
    items = payload.get("items") if isinstance(payload, dict) else []
    out: list[RawItem] = []
    if not isinstance(items, list):
        return out
    for item in items:
        if not isinstance(item, dict):
            continue
        subject = compact_public_snippet(str(item.get("subject") or ""), max_chars=180)
        preview = compact_public_snippet(str(item.get("preview") or ""), max_chars=260)
        if not subject:
            continue
        public_url = clean_agentmail_public_url(item.get("public_url"))
        if not public_url:
            continue
        received_at = parse_date_any(item.get("received_at"), utc_now())
        domain = str(item.get("sender_domain") or "").strip()
        out.append(
            RawItem(
                site_id="agentmail",
                site_name="AgentMail",
                source=f"AgentMail · {domain}" if domain else "AgentMail",
                title=subject,
                url=public_url,
                published_at=received_at,
                meta={
                    "summary": preview,
                    "email_source_type": "newsletter_metadata",
                },
            )
        )
    return out


def env_flag(name: str) -> bool:
    return str(os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def env_flag_default(name: str, default: bool) -> bool:
    """Three-state toggle: unset/blank -> default; explicit truthy/falsey wins.

    Used for the *_ENABLED switches so API-key presence is the primary driver
    (key in env -> source runs) while ENABLED stays available as an explicit
    kill switch: set it to 0/false/no/off to force a paid source off even when a
    key is present."""
    raw = str(os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    try:
        return int(str(os.environ.get(name) or default).strip() or default)
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(str(os.environ.get(name) or default).strip() or default)
    except ValueError:
        return default


def load_paid_source_state(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    sources = payload.get("sources")
    if not isinstance(sources, dict):
        sources = {}
    return {"schema_version": 1, "sources": sources}


def paid_source_interval_hours(prefix: str) -> int:
    default = PAID_SOURCE_DEFAULT_INTERVAL_HOURS_BY_PREFIX.get(prefix, PAID_SOURCE_DEFAULT_INTERVAL_HOURS)
    interval = env_int(f"{prefix}_RUN_INTERVAL_HOURS", default)
    return max(1, min(interval, PAID_SOURCE_MAX_INTERVAL_HOURS))


def paid_source_state_entry(state: dict[str, Any] | None, source_key: str) -> dict[str, Any]:
    if not isinstance(state, dict):
        return {}
    sources = state.get("sources")
    if not isinstance(sources, dict):
        return {}
    entry = sources.get(source_key)
    return entry if isinstance(entry, dict) else {}


def paid_source_run_gate(
    prefix: str,
    source_key: str,
    now: datetime,
    state: dict[str, Any] | None,
) -> tuple[bool, str | None]:
    if env_flag(f"{prefix}_FORCE_RUN"):
        return True, None

    current = now.astimezone(UTC)
    interval_hours = paid_source_interval_hours(prefix)
    entry = paid_source_state_entry(state, source_key)
    last_run = parse_iso(str(entry.get("last_run_at") or ""))
    if last_run:
        due_at = last_run.astimezone(UTC) + timedelta(hours=interval_hours)
        if current < due_at:
            return False, f"before_{source_key}_run_interval"
        return True, None

    run_hour = max(0, min(env_int(f"{prefix}_RUN_UTC_HOUR", 0), 23))
    minute_max = max(0, min(env_int(f"{prefix}_RUN_UTC_MINUTE_MAX", 10), 59))
    if current.hour == run_hour and current.minute <= minute_max:
        return True, None
    return False, f"outside_{source_key}_initial_window"


def update_paid_source_state(
    state: dict[str, Any],
    source_key: str,
    status: dict[str, Any],
    now: datetime,
) -> None:
    if not status.get("attempted"):
        return
    sources = state.setdefault("sources", {})
    if not isinstance(sources, dict):
        sources = {}
        state["sources"] = sources
    entry = sources.setdefault(source_key, {})
    if not isinstance(entry, dict):
        entry = {}
        sources[source_key] = entry
    entry["last_run_at"] = iso(now)
    entry["last_ok"] = bool(status.get("ok"))
    entry["last_item_count"] = int(status.get("item_count") or 0)
    if status.get("ok"):
        entry["last_success_at"] = iso(now)
        entry.pop("last_error", None)
    elif status.get("error"):
        entry["last_error"] = status.get("error")


def sync_paid_source_status_timestamps(
    status: dict[str, Any],
    state: dict[str, Any],
    source_key: str,
) -> None:
    """Keep the published status aligned with the state used by the run gate."""
    entry = paid_source_state_entry(state, source_key)
    status["last_run_at"] = entry.get("last_run_at")
    status["last_success_at"] = entry.get("last_success_at")


def maybe_fetch_agentmail_digest(
    session: requests.Session,
    generated_at: str,
    after: str,
    window_hours: int,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Fetch AgentMail only when explicitly enabled and fully configured."""
    status: dict[str, Any] = {
        "enabled": env_flag("EMAIL_DIGEST_ENABLED"),
        "ok": None,
        "item_count": 0,
        "privacy": "metadata_only_no_body",
        "published_by_default": False,
        "provider": None,
        "include_in_radar": env_flag("EMAIL_DIGEST_INCLUDE_IN_RADAR"),
    }
    if not status["enabled"]:
        return None, status

    provider = str(os.environ.get("AGENTMAIL_PROVIDER") or "").strip().lower()
    agentmail_api_key = str(os.environ.get("AGENTMAIL_API_KEY") or "").strip()
    agentmail_inbox_id = str(os.environ.get("AGENTMAIL_INBOX_ID") or "").strip()
    if not provider:
        provider = "api" if (agentmail_api_key and agentmail_inbox_id) else AGENTMAIL_PROVIDER_DEFAULT
    status["provider"] = provider

    agentmail_base_url = str(os.environ.get("AGENTMAIL_API_BASE_URL") or AGENTMAIL_API_BASE_DEFAULT).strip()
    agentmail_limit = env_int("AGENTMAIL_LIMIT", AGENTMAIL_DEFAULT_LIMIT)
    agentmail_cli = str(os.environ.get("AGENTMAIL_CLI") or AGENTMAIL_CLI_DEFAULT).strip()
    allowed_sender_domains = parse_domain_filter(str(os.environ.get("AGENTMAIL_ALLOWED_SENDER_DOMAINS") or ""))
    resolve_public_urls = env_flag("AGENTMAIL_RESOLVE_PUBLIC_URLS")
    status["allowed_sender_domains"] = allowed_sender_domains
    status["resolve_public_urls"] = resolve_public_urls

    if provider == "api" and not (agentmail_api_key and agentmail_inbox_id):
        status["ok"] = False
        status["error"] = "missing_agentmail_credentials"
        return None, status
    if provider not in {"api", "agently_cli"}:
        status["ok"] = False
        status["error"] = "unsupported_agentmail_provider"
        return None, status

    try:
        if provider == "api":
            payload = fetch_agentmail_digest(
                session,
                api_key=agentmail_api_key,
                inbox_id=agentmail_inbox_id,
                generated_at=generated_at,
                after=after,
                limit=agentmail_limit,
                base_url=agentmail_base_url,
                window_hours=window_hours,
                allowed_sender_domains=allowed_sender_domains,
            )
        else:
            payload = fetch_agentmail_digest_via_cli(
                generated_at=generated_at,
                after=after,
                limit=agentmail_limit,
                cli_path=agentmail_cli,
                window_hours=window_hours,
                allowed_sender_domains=allowed_sender_domains,
                resolve_public_urls=resolve_public_urls,
            )
        status["ok"] = True
        status["item_count"] = int(payload.get("total_messages") or 0)
        return payload, status
    except Exception as exc:
        status["ok"] = False
        status["error"] = type(exc).__name__
        return None, status


def x_api_should_run_now(now: datetime) -> bool:
    """Gate paid X API reads so a 30-minute cron does not spend every run."""
    if env_flag("X_API_FORCE_RUN"):
        return True
    run_hour = max(0, min(env_int("X_API_RUN_UTC_HOUR", 0), 23))
    minute_max = max(0, min(env_int("X_API_RUN_UTC_MINUTE_MAX", 10), 59))
    return now.astimezone(UTC).hour == run_hour and now.astimezone(UTC).minute <= minute_max


def x_api_status_base(now: datetime) -> dict[str, Any]:
    daily_post_limit = max(0, env_int("X_API_DAILY_POST_LIMIT", X_API_DEFAULT_MAX_RESULTS))
    max_results = max(10, min(env_int("X_API_MAX_RESULTS", X_API_DEFAULT_MAX_RESULTS), 100))
    effective_cap = min(max_results, daily_post_limit) if daily_post_limit else 0
    enable_toggle = env_flag_default("X_API_ENABLED", True)
    token_present = bool(
        str(os.environ.get("X_BEARER_TOKEN") or os.environ.get("X_API_BEARER_TOKEN") or "").strip()
    )
    return {
        "enabled": enable_toggle and token_present,
        "enable_toggle": enable_toggle,
        "api_key_present": token_present,
        "ok": None,
        "item_count": 0,
        "privacy": "public_posts_metadata_only",
        "published_by_default": False,
        "official_free_read_quota": False,
        "unit_cost_usd_per_post_read": X_API_POST_READ_COST_USD,
        "daily_post_limit": daily_post_limit,
        "max_results_per_run": max_results,
        "effective_result_cap": effective_cap,
        "estimated_max_cost_usd_per_run": round(effective_cap * X_API_POST_READ_COST_USD, 4),
        "run_utc_hour": max(0, min(env_int("X_API_RUN_UTC_HOUR", 0), 23)),
        "generated_date_utc": now.astimezone(UTC).date().isoformat(),
    }


def fetch_x_api_recent_search(
    session: requests.Session,
    bearer_token: str,
    query: str,
    now: datetime,
    max_results: int,
    base_url: str = X_API_BASE_DEFAULT,
) -> list[RawItem]:
    """Fetch public recent-search Posts from X API v2; no writes and no DMs."""
    query = re.sub(r"\s+", " ", (query or X_API_DEFAULT_QUERY).strip())
    if len(query) > X_API_MAX_QUERY_CHARS:
        raise ValueError("x_query_too_long")
    capped_max_results = max(10, min(int(max_results or X_API_DEFAULT_MAX_RESULTS), 100))
    url = f"{(base_url or X_API_BASE_DEFAULT).rstrip('/')}/2/tweets/search/recent"
    response = session.get(
        url,
        headers={"Authorization": f"Bearer {bearer_token}"},
        params={
            "query": query,
            "max_results": capped_max_results,
            "tweet.fields": "created_at,author_id,public_metrics,lang",
            "expansions": "author_id",
            "user.fields": "username,name,verified",
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    users = {
        str(user.get("id")): user
        for user in (payload.get("includes", {}) or {}).get("users", [])
        if isinstance(user, dict) and user.get("id")
    }
    out: list[RawItem] = []
    for post in payload.get("data") or []:
        if not isinstance(post, dict):
            continue
        post_id = str(post.get("id") or "").strip()
        text = compact_public_snippet(str(post.get("text") or ""), max_chars=220)
        if not (post_id and text):
            continue
        user = users.get(str(post.get("author_id") or ""), {})
        username = str(user.get("username") or "i/web").strip() or "i/web"
        published = parse_iso(str(post.get("created_at") or "")) or now
        out.append(
            RawItem(
                site_id="xapi",
                site_name="X API",
                source=f"@{username}",
                title=text,
                url=f"https://x.com/{username}/status/{post_id}",
                published_at=published,
                meta={
                    "post_id": post_id,
                    "lang": post.get("lang"),
                    "public_metrics": post.get("public_metrics") or {},
                },
            )
        )
    return out


def maybe_fetch_x_api_updates(
    session: requests.Session,
    now: datetime,
) -> tuple[list[RawItem], dict[str, Any]]:
    """Fetch X when a bearer token is present and ENABLED is not turned off, then
    only if scheduled and capped. The token is the primary switch; ENABLED is an
    optional kill switch (set it to 0 to force off)."""
    status = x_api_status_base(now)
    if not status["enable_toggle"]:
        status["disabled_reason"] = "disabled_by_toggle"
        return [], status
    if not status["api_key_present"]:
        status["disabled_reason"] = "no_bearer_token"
        return [], status

    if status["effective_result_cap"] < 10:
        status["ok"] = False
        status["error"] = "x_daily_post_limit_below_api_minimum"
        return [], status

    if not x_api_should_run_now(now):
        status["skipped"] = True
        status["skip_reason"] = "outside_x_api_daily_window"
        return [], status

    bearer_token = str(os.environ.get("X_BEARER_TOKEN") or os.environ.get("X_API_BEARER_TOKEN") or "").strip()

    query = str(os.environ.get("X_API_QUERY") or X_API_DEFAULT_QUERY).strip()
    base_url = str(os.environ.get("X_API_BASE_URL") or X_API_BASE_DEFAULT).strip()
    try:
        items = fetch_x_api_recent_search(
            session,
            bearer_token=bearer_token,
            query=query,
            now=now,
            max_results=int(status["effective_result_cap"]),
            base_url=base_url,
        )
        status["ok"] = True
        status["item_count"] = len(items)
        status["estimated_cost_usd"] = round(len(items) * X_API_POST_READ_COST_USD, 4)
        return items, status
    except Exception as exc:
        status["ok"] = False
        status["error"] = type(exc).__name__
        return [], status


def socialdata_should_run_now(now: datetime, paid_source_state: dict[str, Any] | None = None) -> tuple[bool, str | None]:
    """Gate paid SocialData reads so a 30-minute cron does not spend every run."""
    return paid_source_run_gate("SOCIALDATA", "socialdata", now, paid_source_state)


def socialdata_status_base(now: datetime, paid_source_state: dict[str, Any] | None = None) -> dict[str, Any]:
    daily_tweet_limit = max(0, env_int("SOCIALDATA_DAILY_TWEET_LIMIT", SOCIALDATA_DEFAULT_MAX_RESULTS))
    max_results = max(1, min(env_int("SOCIALDATA_MAX_RESULTS", SOCIALDATA_DEFAULT_MAX_RESULTS), 100))
    effective_cap = min(max_results, daily_tweet_limit) if daily_tweet_limit else 0
    state_entry = paid_source_state_entry(paid_source_state, "socialdata")
    enable_toggle = env_flag_default("SOCIALDATA_ENABLED", True)
    api_key_present = bool(str(os.environ.get("SOCIALDATA_API_KEY") or "").strip())
    # The curated KOL list is a SECOND paid path on top of the keyword search,
    # so the per-run cost ceiling must include it (search cap + list cap).
    list_id = str(os.environ.get("SOCIALDATA_LIST_ID") or SOCIALDATA_LIST_ID_DEFAULT).strip()
    list_enabled = bool(list_id) and env_flag_default("SOCIALDATA_LIST_ENABLED", True)
    list_cap = max(0, min(env_int("SOCIALDATA_LIST_MAX_RESULTS", SOCIALDATA_LIST_DEFAULT_MAX_RESULTS), 200)) if list_enabled else 0
    combined_cap = effective_cap + list_cap
    return {
        "enabled": enable_toggle and api_key_present,
        "enable_toggle": enable_toggle,
        "api_key_present": api_key_present,
        "ok": None,
        "item_count": 0,
        "privacy": "public_posts_metadata_only",
        "published_by_default": False,
        "unit_cost_usd_per_tweet_read": SOCIALDATA_TWEET_READ_COST_USD,
        "daily_tweet_limit": daily_tweet_limit,
        "max_results_per_run": max_results,
        "effective_result_cap": effective_cap,
        "search_result_cap": effective_cap,
        "list_result_cap": list_cap,
        "combined_result_cap": combined_cap,
        "recency_days": SOCIALDATA_RECENCY_DAYS,
        "estimated_max_cost_usd_per_run": round(combined_cap * SOCIALDATA_TWEET_READ_COST_USD, 4),
        "run_interval_hours": paid_source_interval_hours("SOCIALDATA"),
        "run_utc_hour": max(0, min(env_int("SOCIALDATA_RUN_UTC_HOUR", 0), 23)),
        "run_utc_minute_max": max(0, min(env_int("SOCIALDATA_RUN_UTC_MINUTE_MAX", 10), 59)),
        "last_run_at": state_entry.get("last_run_at"),
        "last_success_at": state_entry.get("last_success_at"),
        "generated_date_utc": now.astimezone(UTC).date().isoformat(),
    }


def fetch_socialdata_search(
    session: requests.Session,
    api_key: str,
    query: str,
    now: datetime,
    max_results: int,
    search_type: str = "Top",
    base_url: str = SOCIALDATA_API_BASE_DEFAULT,
) -> tuple[list[RawItem], dict[str, Any]]:
    """Fetch public X search results through SocialData; no writes and no private data."""
    query = re.sub(r"\s+", " ", (query or SOCIALDATA_DEFAULT_QUERY).strip())
    if len(query) > SOCIALDATA_MAX_QUERY_CHARS:
        raise ValueError("socialdata_query_too_long")
    capped_max_results = max(1, min(int(max_results or SOCIALDATA_DEFAULT_MAX_RESULTS), 100))
    # 默认 Top:Latest 返回的是 API 调用瞬间刚发出的推文,一批的原帖时间挤在同一分钟,
    # 时间轴上表现为同分钟刷屏;Top 按热度返回时间窗内的推文,原帖时间自然散布。
    effective_search_type = search_type if search_type in {"Latest", "Top"} else "Top"
    out: list[RawItem] = []
    raw_tweet_count = 0
    response_top_level_keys: list[str] = []
    page_count = 0
    cursor = ""
    seen_cursors: set[str] = set()
    seen_tweet_ids: set[str] = set()
    pagination_error: str | None = None
    while len(out) < capped_max_results:
        params = {
            "query": query,
            "type": effective_search_type,
        }
        if cursor:
            params["cursor"] = cursor
        try:
            response = session.get(
                f"{(base_url or SOCIALDATA_API_BASE_DEFAULT).rstrip('/')}/twitter/search",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Accept": "application/json",
                },
                params=params,
                timeout=30,
            )
            response.raise_for_status()
        except Exception as exc:
            if page_count == 0:
                raise
            pagination_error = type(exc).__name__
            break

        payload = response.json()
        page_count += 1
        if isinstance(payload, dict) and not response_top_level_keys:
            response_top_level_keys = sorted(payload.keys())[:12]
        tweets = payload.get("tweets") if isinstance(payload, dict) else []
        raw_tweet_count += len(tweets) if isinstance(tweets, list) else 0
        for tweet in tweets or []:
            if len(out) >= capped_max_results:
                break
            if not isinstance(tweet, dict):
                continue
            tweet_id = str(tweet.get("id_str") or tweet.get("id") or "").strip()
            text = compact_public_snippet(str(tweet.get("full_text") or tweet.get("text") or ""), max_chars=220)
            if not (tweet_id and text) or tweet_id in seen_tweet_ids:
                continue
            seen_tweet_ids.add(tweet_id)
            user = tweet.get("user") if isinstance(tweet.get("user"), dict) else {}
            username = str(user.get("screen_name") or "i/web").strip().lstrip("@") or "i/web"
            published = parse_iso(str(tweet.get("tweet_created_at") or tweet.get("created_at") or "")) or now
            out.append(
                RawItem(
                    site_id="socialdata_x",
                    site_name="SocialData X",
                    source=f"@{username}",
                    title=text,
                    url=f"https://x.com/{username}/status/{tweet_id}",
                    published_at=published,
                    meta={
                        "post_id": tweet_id,
                        "lang": tweet.get("lang"),
                        "public_metrics": {
                            "reply_count": tweet.get("reply_count"),
                            "retweet_count": tweet.get("retweet_count"),
                            "quote_count": tweet.get("quote_count"),
                            "favorite_count": tweet.get("favorite_count"),
                            "bookmark_count": tweet.get("bookmark_count"),
                            "views_count": tweet.get("views_count"),
                        },
                    },
                )
            )

        next_cursor = str(payload.get("next_cursor") or "").strip() if isinstance(payload, dict) else ""
        if not next_cursor or next_cursor in seen_cursors:
            break
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    diagnostics = {
        "endpoint": "/twitter/search",
        "search_type": effective_search_type,
        "query_chars": len(query),
        "response_top_level_keys": response_top_level_keys,
        "raw_tweet_count": raw_tweet_count,
        "mapped_tweet_count": len(out),
        "page_count": page_count,
        "cursor_request_count": max(0, page_count - 1),
        "reached_result_cap": len(out) >= capped_max_results,
    }
    if pagination_error:
        diagnostics["pagination_error"] = pagination_error
    if raw_tweet_count == 0:
        diagnostics["empty_reason"] = "no_tweets_returned_by_socialdata"
    elif len(out) == 0:
        diagnostics["empty_reason"] = "tweets_returned_but_none_mapped"
    return out, diagnostics


def fetch_socialdata_list_tweets(
    session: requests.Session,
    api_key: str,
    list_id: str,
    now: datetime,
    max_results: int,
    exclude_handles: set[str] | None = None,
    base_url: str = SOCIALDATA_API_BASE_DEFAULT,
    max_pages: int = SOCIALDATA_LIST_MAX_PAGES,
) -> tuple[list[RawItem], dict[str, Any]]:
    """Pull a curated X list timeline through SocialData, keeping only members'
    own AI posts. Retweets, replies, the excluded owner, and egg-avatar accounts
    are dropped so the list stays a high-signal, bot-free source. Pagination is
    hard-capped at ``max_pages`` so a heavily-filtered list can't bill without
    bound."""
    list_id = str(list_id or "").strip()
    if not list_id:
        raise ValueError("socialdata_list_id_empty")
    capped_max_results = max(1, min(int(max_results or SOCIALDATA_LIST_DEFAULT_MAX_RESULTS), 200))
    exclude = {h.strip().lstrip("@").lower() for h in (exclude_handles or set()) if h.strip()}
    out: list[RawItem] = []
    raw_tweet_count = 0
    skipped = {"retweet_or_reply": 0, "excluded_author": 0, "bot_like": 0, "empty": 0, "duplicate": 0}
    page_count = 0
    cursor = ""
    seen_cursors: set[str] = set()
    seen_tweet_ids: set[str] = set()
    pagination_error: str | None = None
    page_cap = max(1, int(max_pages or 1))
    hit_page_cap = False
    while len(out) < capped_max_results and page_count < page_cap:
        params: dict[str, str] = {}
        if cursor:
            params["cursor"] = cursor
        try:
            response = session.get(
                f"{(base_url or SOCIALDATA_API_BASE_DEFAULT).rstrip('/')}/twitter/list/{list_id}/tweets",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Accept": "application/json",
                },
                params=params,
                timeout=30,
            )
            response.raise_for_status()
        except Exception as exc:
            if page_count == 0:
                raise
            pagination_error = type(exc).__name__
            break

        payload = response.json()
        page_count += 1
        tweets = payload.get("tweets") if isinstance(payload, dict) else []
        raw_tweet_count += len(tweets) if isinstance(tweets, list) else 0
        for tweet in tweets or []:
            if len(out) >= capped_max_results:
                break
            if not isinstance(tweet, dict):
                continue
            tweet_type = str(tweet.get("type") or "tweet").lower()
            if tweet_type not in SOCIALDATA_LIST_ALLOWED_TYPES:
                skipped["retweet_or_reply"] += 1
                continue
            user = tweet.get("user") if isinstance(tweet.get("user"), dict) else {}
            username = str(user.get("screen_name") or "").strip().lstrip("@")
            if username.lower() in exclude:
                skipped["excluded_author"] += 1
                continue
            if user.get("default_profile_image"):
                skipped["bot_like"] += 1
                continue
            tweet_id = str(tweet.get("id_str") or tweet.get("id") or "").strip()
            text = compact_public_snippet(str(tweet.get("full_text") or tweet.get("text") or ""), max_chars=220)
            if not (tweet_id and text and username):
                skipped["empty"] += 1
                continue
            if tweet_id in seen_tweet_ids:
                skipped["duplicate"] += 1
                continue
            seen_tweet_ids.add(tweet_id)
            published = parse_iso(str(tweet.get("tweet_created_at") or tweet.get("created_at") or "")) or now
            out.append(
                RawItem(
                    site_id="socialdata_x",
                    site_name="SocialData X",
                    source=f"@{username}",
                    title=text,
                    url=f"https://x.com/{username}/status/{tweet_id}",
                    published_at=published,
                    meta={
                        "post_id": tweet_id,
                        "via": "list",
                        "list_id": list_id,
                        "tweet_type": tweet_type,
                        "lang": tweet.get("lang"),
                        "public_metrics": {
                            "reply_count": tweet.get("reply_count"),
                            "retweet_count": tweet.get("retweet_count"),
                            "quote_count": tweet.get("quote_count"),
                            "favorite_count": tweet.get("favorite_count"),
                            "bookmark_count": tweet.get("bookmark_count"),
                            "views_count": tweet.get("views_count"),
                        },
                    },
                )
            )

        next_cursor = str(payload.get("next_cursor") or "").strip() if isinstance(payload, dict) else ""
        if not next_cursor or next_cursor in seen_cursors:
            break
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    hit_page_cap = page_count >= page_cap and len(out) < capped_max_results
    diagnostics = {
        "endpoint": f"/twitter/list/{list_id}/tweets",
        "list_id": list_id,
        "raw_tweet_count": raw_tweet_count,
        "mapped_tweet_count": len(out),
        "page_count": page_count,
        "max_pages": page_cap,
        "hit_page_cap": hit_page_cap,
        "skipped": skipped,
        "excluded_handles": sorted(exclude),
        "reached_result_cap": len(out) >= capped_max_results,
    }
    if pagination_error:
        diagnostics["pagination_error"] = pagination_error
    return out, diagnostics


def maybe_fetch_socialdata_updates(
    session: requests.Session,
    now: datetime,
    paid_source_state: dict[str, Any] | None = None,
) -> tuple[list[RawItem], dict[str, Any]]:
    """Fetch SocialData when an API key is present and ENABLED is not turned off,
    then only if scheduled and capped. The key is the primary switch; ENABLED is
    an optional kill switch (set it to 0 to force off)."""
    status = socialdata_status_base(now, paid_source_state)
    if not status["enable_toggle"]:
        status["disabled_reason"] = "disabled_by_toggle"
        return [], status
    if not status["api_key_present"]:
        status["disabled_reason"] = "no_api_key"
        return [], status

    if status["effective_result_cap"] < 1:
        status["ok"] = False
        status["error"] = "socialdata_daily_tweet_limit_below_minimum"
        return [], status

    should_run, skip_reason = socialdata_should_run_now(now, paid_source_state)
    if not should_run:
        status["skipped"] = True
        status["skip_reason"] = skip_reason or "outside_socialdata_run_window"
        return [], status

    api_key = str(os.environ.get("SOCIALDATA_API_KEY") or "").strip()

    query = str(os.environ.get("SOCIALDATA_QUERY") or SOCIALDATA_DEFAULT_QUERY).strip()
    base_url = str(os.environ.get("SOCIALDATA_API_BASE_URL") or SOCIALDATA_API_BASE_DEFAULT).strip()
    search_type = str(os.environ.get("SOCIALDATA_SEARCH_TYPE") or "Top").strip() or "Top"
    list_id = str(os.environ.get("SOCIALDATA_LIST_ID") or SOCIALDATA_LIST_ID_DEFAULT).strip()
    list_enabled = bool(list_id) and str(os.environ.get("SOCIALDATA_LIST_ENABLED", "1")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    list_max_results = max(0, min(env_int("SOCIALDATA_LIST_MAX_RESULTS", SOCIALDATA_LIST_DEFAULT_MAX_RESULTS), 200))
    list_exclude = {
        handle.strip().lstrip("@").lower()
        for handle in str(os.environ.get("SOCIALDATA_LIST_EXCLUDE") or SOCIALDATA_LIST_DEFAULT_EXCLUDE).split(",")
        if handle.strip()
    }
    status["attempted"] = True

    items: list[RawItem] = []
    seen_urls: set[str] = set()
    errors: list[str] = []
    recency_cutoff = now - timedelta(days=SOCIALDATA_RECENCY_DAYS) if SOCIALDATA_RECENCY_DAYS else None
    skipped_stale = 0

    # 1) Broad keyword search: discovers new voices across en/zh.
    try:
        search_items, diagnostics = fetch_socialdata_search(
            session,
            api_key=api_key,
            query=query,
            now=now,
            max_results=int(status["effective_result_cap"]),
            search_type=search_type,
            base_url=base_url,
        )
        status["diagnostics"] = diagnostics
        for item in search_items:
            if recency_cutoff and item.published_at and item.published_at < recency_cutoff:
                skipped_stale += 1
                continue
            if item.url in seen_urls:
                continue
            seen_urls.add(item.url)
            items.append(item)
    except Exception as exc:
        errors.append(f"search:{type(exc).__name__}")

    # 2) Curated list timeline: stably tracks known KOLs by identity, bot-filtered.
    list_item_count = 0
    if list_enabled and list_max_results >= 1:
        try:
            list_items, list_diagnostics = fetch_socialdata_list_tweets(
                session,
                api_key=api_key,
                list_id=list_id,
                now=now,
                max_results=list_max_results,
                exclude_handles=list_exclude,
                base_url=base_url,
            )
            status["list_diagnostics"] = list_diagnostics
            for item in list_items:
                if recency_cutoff and item.published_at and item.published_at < recency_cutoff:
                    skipped_stale += 1
                    continue
                if item.url in seen_urls:
                    continue
                seen_urls.add(item.url)
                items.append(item)
                list_item_count += 1
        except Exception as exc:
            errors.append(f"list:{type(exc).__name__}")

    # SocialData bills per tweet READ (raw), not per kept item; the list discards
    # retweets/replies/stale posts, so raw reads exceed mapped items. Cost and the
    # ceiling in socialdata_status_base both track raw reads across BOTH paths.
    search_raw = int((status.get("diagnostics") or {}).get("raw_tweet_count") or 0)
    list_raw = int((status.get("list_diagnostics") or {}).get("raw_tweet_count") or 0)
    status["list_enabled"] = list_enabled
    status["list_item_count"] = list_item_count
    status["search_item_count"] = len(items) - list_item_count
    status["item_count"] = len(items)
    status["recency_days"] = SOCIALDATA_RECENCY_DAYS
    status["skipped_stale_count"] = skipped_stale
    status["raw_reads"] = search_raw + list_raw
    status["estimated_cost_usd"] = round((search_raw + list_raw) * SOCIALDATA_TWEET_READ_COST_USD, 4)
    if errors and not items:
        status["ok"] = False
        status["error"] = ";".join(errors)
    else:
        status["ok"] = True
        if errors:
            status["partial_error"] = ";".join(errors)
    return items, status


def tikhub_should_run_now(now: datetime, paid_source_state: dict[str, Any] | None = None) -> tuple[bool, str | None]:
    """Gate paid TikHub reads so scheduled workflows do not spend every run."""
    return paid_source_run_gate("TIKHUB", "tikhub", now, paid_source_state)


def tikhub_status_base(now: datetime, paid_source_state: dict[str, Any] | None = None) -> dict[str, Any]:
    daily_limit = max(0, env_int("TIKHUB_DAILY_ITEM_LIMIT", TIKHUB_DEFAULT_MAX_RESULTS))
    max_results = max(1, min(env_int("TIKHUB_MAX_RESULTS", TIKHUB_DEFAULT_MAX_RESULTS), 100))
    effective_cap = min(max_results, daily_limit) if daily_limit else 0
    enable_toggle = env_flag_default("TIKHUB_ENABLED", True)
    api_key_present = bool(str(os.environ.get("TIKHUB_API_KEY") or "").strip())
    platforms = [
        part.strip().lower()
        for part in str(os.environ.get("TIKHUB_PLATFORMS") or TIKHUB_DEFAULT_PLATFORMS).split(",")
        if part.strip()
    ]
    state_entry = paid_source_state_entry(paid_source_state, "tikhub")
    return {
        "enabled": enable_toggle and api_key_present,
        "enable_toggle": enable_toggle,
        "api_key_present": api_key_present,
        "enabled_by": "disabled_by_toggle" if not enable_toggle else ("ready" if api_key_present else "no_api_key"),
        "ok": None,
        "item_count": 0,
        "privacy": "public_social_posts_metadata_only",
        "published_by_default": False,
        "billing": "tikhub_charged_request",
        "daily_item_limit": daily_limit,
        "max_results_per_run": max_results,
        "effective_result_cap": effective_cap,
        "platforms": platforms,
        "run_interval_hours": paid_source_interval_hours("TIKHUB"),
        "run_utc_hour": max(0, min(env_int("TIKHUB_RUN_UTC_HOUR", 0), 23)),
        "run_utc_minute_max": max(0, min(env_int("TIKHUB_RUN_UTC_MINUTE_MAX", 10), 59)),
        "last_run_at": state_entry.get("last_run_at"),
        "last_success_at": state_entry.get("last_success_at"),
        "generated_date_utc": now.astimezone(UTC).date().isoformat(),
    }


def iter_nested_dicts(value: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if isinstance(value, dict):
        out.append(value)
        for child in value.values():
            out.extend(iter_nested_dicts(child))
    elif isinstance(value, list):
        for child in value:
            out.extend(iter_nested_dicts(child))
    return out


def tikhub_payload_shape(payload: Any) -> dict[str, Any]:
    """Return a sanitized structural summary for debugging API schema drift."""
    dicts = iter_nested_dicts(payload)
    data = payload.get("data") if isinstance(payload, dict) else None
    data_items = data.get("items") if isinstance(data, dict) else None
    data_business = data.get("business_data") if isinstance(data, dict) else None
    sample_nodes: list[dict[str, Any]] = []
    for node in dicts:
        if len(sample_nodes) >= 3:
            break
        keys = sorted(str(key) for key in node.keys())[:16]
        if {"aweme_info", "note_card", "display_title", "desc", "title", "id", "note_id"} & set(keys):
            sample_nodes.append({"keys": keys})
    return {
        "dict_count": len(dicts),
        "data_type": type(data).__name__ if data is not None else None,
        "data_keys": sorted(data.keys())[:16] if isinstance(data, dict) else [],
        "data_items_count": len(data_items) if isinstance(data_items, list) else None,
        "data_business_count": len(data_business) if isinstance(data_business, list) else None,
        "aweme_info_count": sum(1 for node in dicts if isinstance(node.get("aweme_info"), dict)),
        "note_card_count": sum(1 for node in dicts if isinstance(node.get("note_card"), dict)),
        "sample_nodes": sample_nodes,
    }


def parse_epoch_any(value: Any, now: datetime) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value).strip()
        if not text:
            return None
        if re.fullmatch(r"\d+(\.\d+)?", text):
            number = float(text)
        else:
            return parse_date_any(text, now)
    if number > 10_000_000_000:
        number = number / 1000
    try:
        return datetime.fromtimestamp(number, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def is_tikhub_generic_audio_title(title: str) -> bool:
    return bool(
        re.fullmatch(
            r"@?.{1,80}(?:创作的原声|的原声|original\s+sound)",
            (title or "").strip(),
            flags=re.IGNORECASE,
        )
    )


def first_tikhub_douyin_title(aweme: dict[str, Any]) -> str:
    share_info = aweme.get("share_info") if isinstance(aweme.get("share_info"), dict) else {}
    candidates = (
        aweme.get("desc"),
        aweme.get("title"),
        aweme.get("caption"),
        share_info.get("share_desc"),
        share_info.get("share_title"),
    )
    for candidate in candidates:
        title = compact_public_snippet(str(candidate or ""), max_chars=220)
        if title and not is_tikhub_generic_audio_title(title):
            return title
    return ""


def parse_tikhub_published_at(record: dict[str, Any], now: datetime, fields: tuple[str, ...]) -> datetime | None:
    for field in fields:
        value = record.get(field)
        published = parse_epoch_any(value, now) or parse_date_any(value, now)
        if published:
            return published
    return None


def parse_xiaohongshu_note_id_published_at(note_id: str, now: datetime) -> datetime | None:
    """Infer Xiaohongshu note creation time from the timestamp prefix in note id."""
    raw = str(note_id or "").strip()
    match = re.match(r"^([0-9a-fA-F]{8})", raw)
    if not match:
        return None
    published = parse_unix_timestamp(int(match.group(1), 16))
    if not published:
        return None
    earliest_supported = datetime(2013, 1, 1, tzinfo=UTC)
    latest_supported = now.astimezone(UTC)
    if published < earliest_supported or published > latest_supported:
        return None
    return published


def is_credible_xiaohongshu_published_at(published: datetime | None, now: datetime) -> bool:
    if not published:
        return False
    return datetime(2013, 1, 1, tzinfo=UTC) <= published <= now.astimezone(UTC)


def creator_metric_count(*values: Any) -> int:
    for value in values:
        if value is None or value == "":
            continue
        try:
            return max(0, int(float(str(value).replace(",", "").strip())))
        except (TypeError, ValueError):
            continue
    return 0


def normalize_creator_metrics(platform: str, *records: dict[str, Any]) -> dict[str, int]:
    merged: dict[str, Any] = {}
    for record in records:
        if isinstance(record, dict):
            merged.update(record)
    if platform == "douyin":
        return {
            "likes": creator_metric_count(merged.get("digg_count"), merged.get("like_count")),
            "comments": creator_metric_count(merged.get("comment_count"), merged.get("comments_count")),
            "collects": creator_metric_count(merged.get("collect_count"), merged.get("collected_count")),
            "shares": creator_metric_count(merged.get("share_count"), merged.get("shared_count")),
        }
    return {
        "likes": creator_metric_count(
            merged.get("liked_count"),
            merged.get("likes_count"),
            merged.get("like_count"),
            merged.get("digg_count"),
        ),
        "comments": creator_metric_count(merged.get("comments_count"), merged.get("comment_count")),
        "collects": creator_metric_count(merged.get("collected_count"), merged.get("collect_count")),
        "shares": creator_metric_count(merged.get("shared_count"), merged.get("share_count")),
    }


def parse_tikhub_douyin_items(payload: dict[str, Any], now: datetime, keyword: str, limit: int) -> list[RawItem]:
    out: list[RawItem] = []
    seen_ids: set[str] = set()
    for node in iter_nested_dicts(payload):
        # TikHub wraps real videos in ``aweme_info``. Walking arbitrary nested
        # dictionaries without this guard also reaches ``music`` objects, whose
        # generic titles look like "@…创作的原声" and are not video titles.
        wrapped_aweme = node.get("aweme_info") if isinstance(node.get("aweme_info"), dict) else None
        aweme = wrapped_aweme or node
        if not isinstance(aweme, dict):
            continue
        post_id = str(aweme.get("aweme_id") or aweme.get("awemeId") or "").strip()
        title = first_tikhub_douyin_title(aweme)
        if not (post_id and title) or post_id in seen_ids:
            continue
        seen_ids.add(post_id)
        author = aweme.get("author") if isinstance(aweme.get("author"), dict) else {}
        source = str(author.get("nickname") or author.get("unique_id") or "Douyin Search").strip() or "Douyin Search"
        share = first_non_empty(
            aweme.get("share_url"),
            aweme.get("share_info", {}).get("share_url") if isinstance(aweme.get("share_info"), dict) else "",
            f"https://www.douyin.com/video/{post_id}",
        )
        published = parse_tikhub_published_at(
            aweme,
            now,
            (
                "create_time",
                "create_time_stamp",
                "createTime",
                "createTimeStamp",
                "created_at",
                "publish_time",
                "publishTime",
                "publish_timestamp",
                "time",
            ),
        ) or now
        statistics = aweme.get("statistics") if isinstance(aweme.get("statistics"), dict) else {}
        out.append(
            RawItem(
                site_id="tikhub_douyin",
                site_name="TikHub Douyin",
                source=source,
                title=title,
                url=str(share),
                published_at=published,
                meta={
                    "platform": "douyin",
                    "keyword": keyword,
                    "post_id": post_id,
                    "public_metrics": statistics,
                    "creator_metrics": normalize_creator_metrics("douyin", statistics),
                },
            )
        )
        if len(out) >= limit:
            break
    return out


def parse_tikhub_xiaohongshu_items(payload: dict[str, Any], now: datetime, keyword: str, limit: int) -> list[RawItem]:
    out: list[RawItem] = []
    seen_ids: set[str] = set()
    for node in iter_nested_dicts(payload):
        note = next(
            (
                node.get(key)
                for key in ("note_card", "note_info", "note", "note_data", "noteCard")
                if isinstance(node.get(key), dict)
            ),
            node,
        )
        if not isinstance(note, dict):
            continue
        note_id = str(
            note.get("note_id")
            or note.get("noteId")
            or note.get("id")
            or node.get("noteId")
            or node.get("note_id")
            or node.get("id")
            or ""
        ).strip()
        title = compact_public_snippet(
            str(
                note.get("display_title")
                or note.get("displayTitle")
                or note.get("title")
                or note.get("desc")
                or note.get("description")
                or note.get("content")
                or node.get("display_title")
                or node.get("title")
                or node.get("desc")
                or ""
            ),
            max_chars=220,
        )
        if not (note_id and title) or note_id in seen_ids:
            continue
        seen_ids.add(note_id)
        user = next(
            (
                owner
                for owner in (note.get("user"), note.get("user_info"), node.get("user"), node.get("user_info"))
                if isinstance(owner, dict)
            ),
            {},
        )
        source = str(
            user.get("nickname")
            or user.get("nick_name")
            or user.get("nickName")
            or user.get("name")
            or "Xiaohongshu Search"
        ).strip() or "Xiaohongshu Search"
        xsec_token = str(note.get("xsec_token") or node.get("xsec_token") or "").strip()
        url = first_non_empty(
            note.get("url"),
            note.get("share_url"),
            note.get("shareUrl"),
            node.get("url"),
            node.get("share_url"),
            node.get("shareUrl"),
            f"https://www.xiaohongshu.com/explore/{note_id}{'?xsec_token=' + xsec_token if xsec_token else ''}",
        )
        published = parse_tikhub_published_at(
            note,
            now,
            (
                "time",
                "create_time",
                "created_at",
                "last_update_time",
                "createTime",
                "createdAt",
                "lastUpdateTime",
                "publish_time",
                "publishTime",
            ),
        )
        if not is_credible_xiaohongshu_published_at(published, now):
            published = parse_tikhub_published_at(
                node,
                now,
                (
                    "time",
                    "create_time",
                    "created_at",
                    "last_update_time",
                    "createTime",
                    "createdAt",
                    "lastUpdateTime",
                    "publish_time",
                    "publishTime",
                ),
            )
        if not is_credible_xiaohongshu_published_at(published, now):
            published = parse_xiaohongshu_note_id_published_at(note_id, now)
        interact_info = note.get("interact_info") if isinstance(note.get("interact_info"), dict) else {}
        creator_metrics = normalize_creator_metrics("xiaohongshu", node, note, interact_info)
        out.append(
            RawItem(
                site_id="tikhub_xiaohongshu",
                site_name="TikHub Xiaohongshu",
                source=source,
                title=title,
                url=str(url),
                published_at=published,
                meta={
                    "platform": "xiaohongshu",
                    "keyword": keyword,
                    "post_id": note_id,
                    "public_metrics": interact_info or creator_metrics,
                    "creator_metrics": creator_metrics,
                },
            )
        )
        if len(out) >= limit:
            break
    return out


def tikhub_raw_item_key(item: RawItem) -> str:
    post_id = str((item.meta or {}).get("post_id") or "").strip()
    if post_id:
        return f"{item.site_id}:{post_id}"
    return f"{item.site_id}:{normalize_url(item.url)}:{item.title.strip()}"


def fetch_tikhub_search(
    session: requests.Session,
    api_key: str,
    query: str,
    now: datetime,
    max_results: int,
    platforms: list[str],
    base_url: str = TIKHUB_API_BASE_DEFAULT,
) -> tuple[list[RawItem], dict[str, Any]]:
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    root = (base_url or TIKHUB_API_BASE_DEFAULT).rstrip("/")
    keywords = [part.strip() for part in query.split(",") if part.strip()]
    if not keywords:
        raise ValueError("tikhub_query_empty")
    if any(len(keyword) > TIKHUB_MAX_QUERY_CHARS for keyword in keywords):
        raise ValueError("tikhub_query_too_long")

    capped_max_results = max(1, min(int(max_results or TIKHUB_DEFAULT_MAX_RESULTS), 100))
    platform_list = []
    for platform in platforms:
        if platform in {"douyin", "xiaohongshu"} and platform not in platform_list:
            platform_list.append(platform)
    out: list[RawItem] = []
    per_platform_cap = max(1, (capped_max_results + max(len(platform_list), 1) - 1) // max(len(platform_list), 1))
    per_keyword_cap = max(1, (per_platform_cap + max(len(keywords), 1) - 1) // max(len(keywords), 1))
    diagnostics: dict[str, Any] = {
        "keywords": keywords,
        "platforms": platform_list,
        "per_keyword_cap": per_keyword_cap,
        "requests": [],
        "successful_request_count": 0,
        "request_error_count": 0,
        "recency_days": TIKHUB_RECENCY_DAYS,
        "skipped_missing_published_at_count": 0,
        "skipped_stale_count": 0,
    }
    seen_item_keys: set[str] = set()
    recency_cutoff = now - timedelta(days=TIKHUB_RECENCY_DAYS) if TIKHUB_RECENCY_DAYS else None

    def append_mapped_items(mapped: list[RawItem], surface: str, remaining: int) -> int:
        appended = 0
        for item in mapped:
            if appended >= remaining:
                break
            # Enforce the exact recency window (the API only has coarse buckets).
            if not item.published_at:
                diagnostics["skipped_missing_published_at_count"] += 1
                continue
            if recency_cutoff and item.published_at and item.published_at < recency_cutoff:
                diagnostics["skipped_stale_count"] += 1
                continue
            key = tikhub_raw_item_key(item)
            if key in seen_item_keys:
                continue
            seen_item_keys.add(key)
            item.meta["search_surface"] = surface
            out.append(item)
            appended += 1
        return appended

    def request_error_info(exc: Exception) -> dict[str, Any]:
        response = getattr(exc, "response", None)
        return {
            "error": type(exc).__name__,
            "status_code": getattr(response, "status_code", None),
        }

    for platform in platform_list:
        platform_count = 0
        for keyword in keywords:
            remaining = min(capped_max_results - len(out), per_platform_cap - platform_count, per_keyword_cap)
            if remaining <= 0:
                break
            if platform == "douyin":
                endpoint = "/api/v1/douyin/search/fetch_general_search_v2"
                request_info = {
                    "platform": platform,
                    "surface": "douyin_general_v2",
                    "endpoint": endpoint,
                    "keyword": keyword,
                }
                try:
                    response = session.post(
                        f"{root}{endpoint}",
                        headers={**headers, "Content-Type": "application/json"},
                        json={
                            "keyword": keyword,
                            "cursor": 0,
                            "sort_type": TIKHUB_DOUYIN_SORT_TYPE,
                            "publish_time": TIKHUB_DOUYIN_PUBLISH_TIME,
                            "filter_duration": "0",
                            "content_type": "0",
                            "search_id": "",
                            "backtrace": "",
                        },
                        timeout=30,
                    )
                    response.raise_for_status()
                    payload = response.json()
                    mapped = parse_tikhub_douyin_items(
                        payload,
                        now=now,
                        keyword=keyword,
                        limit=max(remaining, TIKHUB_RESPONSE_SCAN_LIMIT),
                    )
                    appended = append_mapped_items(mapped, "douyin_general_v2", remaining)
                    platform_count += appended
                    request_info.update(
                        {
                            "mapped_item_count": len(mapped),
                            "appended_item_count": appended,
                            "response_top_level_keys": sorted(payload.keys())[:12] if isinstance(payload, dict) else [],
                            "payload_shape": tikhub_payload_shape(payload),
                        }
                    )
                    diagnostics["successful_request_count"] += 1
                except Exception as exc:
                    diagnostics["request_error_count"] += 1
                    request_info.update(request_error_info(exc))
                diagnostics["requests"].append(request_info)
            else:
                # TikHub documents App V2 as the preferred Xiaohongshu API and
                # Web V3 as the next public web path; scan both because results
                # can differ between mobile and web surfaces.
                xhs_surfaces = (
                    (
                        "xiaohongshu_app_v2",
                        "/api/v1/xiaohongshu/app_v2/search_notes",
                        {
                            "keyword": keyword,
                            "page": 1,
                            "sort_type": TIKHUB_XHS_SORT,
                            "note_type": TIKHUB_XHS_NOTE_TYPE,
                            "time_filter": TIKHUB_XHS_TIME_FILTER,
                            "search_id": "",
                            "search_session_id": "",
                            "source": "explore_feed",
                            "ai_mode": 0,
                        },
                    ),
                    (
                        "xiaohongshu_web_v3",
                        "/api/v1/xiaohongshu/web_v3/fetch_search_notes",
                        {"keyword": keyword, "page": 1, "sort": TIKHUB_XHS_SORT, "note_type": 0},
                    ),
                )
                keyword_count = 0
                for surface, endpoint, params in xhs_surfaces:
                    surface_remaining = min(
                        remaining - keyword_count,
                        capped_max_results - len(out),
                        per_platform_cap - platform_count,
                    )
                    if surface_remaining <= 0:
                        break
                    request_info = {
                        "platform": platform,
                        "surface": surface,
                        "endpoint": endpoint,
                        "keyword": keyword,
                    }
                    try:
                        response = session.get(f"{root}{endpoint}", headers=headers, params=params, timeout=30)
                        response.raise_for_status()
                        payload = response.json()
                        mapped = parse_tikhub_xiaohongshu_items(
                            payload,
                            now=now,
                            keyword=keyword,
                            limit=max(surface_remaining, TIKHUB_RESPONSE_SCAN_LIMIT),
                        )
                        appended = append_mapped_items(mapped, surface, surface_remaining)
                        platform_count += appended
                        keyword_count += appended
                        request_info.update(
                            {
                                "mapped_item_count": len(mapped),
                                "appended_item_count": appended,
                                "response_top_level_keys": sorted(payload.keys())[:12] if isinstance(payload, dict) else [],
                                "payload_shape": tikhub_payload_shape(payload),
                            }
                        )
                        if surface == "xiaohongshu_app_v2" and keyword_count < remaining:
                            request_info["fallback_reason"] = (
                                "no_items_mapped_try_web_v3"
                                if not mapped
                                else "insufficient_recent_items_try_web_v3"
                            )
                        diagnostics["successful_request_count"] += 1
                    except Exception as exc:
                        diagnostics["request_error_count"] += 1
                        request_info.update(request_error_info(exc))
                    diagnostics["requests"].append(request_info)
        if len(out) >= capped_max_results:
            break
    diagnostics["mapped_item_count"] = len(out)
    if diagnostics["request_error_count"] and not diagnostics["successful_request_count"]:
        raise ValueError("tikhub_all_requests_failed")
    return out, diagnostics


def maybe_fetch_tikhub_updates(
    session: requests.Session,
    now: datetime,
    paid_source_state: dict[str, Any] | None = None,
) -> tuple[list[RawItem], dict[str, Any]]:
    """Fetch TikHub when an API key is present and ENABLED is not turned off,
    then only if scheduled and capped. The key is the primary switch; ENABLED is
    an optional kill switch (set it to 0 to force off)."""
    status = tikhub_status_base(now, paid_source_state)
    if not status["enable_toggle"]:
        status["disabled_reason"] = "disabled_by_toggle"
        return [], status
    if not status["api_key_present"]:
        status["disabled_reason"] = "no_api_key"
        return [], status

    if status["effective_result_cap"] < 1:
        status["ok"] = False
        status["error"] = "tikhub_daily_item_limit_below_minimum"
        return [], status

    should_run, skip_reason = tikhub_should_run_now(now, paid_source_state)
    if not should_run:
        status["skipped"] = True
        status["skip_reason"] = skip_reason or "outside_tikhub_run_window"
        return [], status

    api_key = str(os.environ.get("TIKHUB_API_KEY") or "").strip()

    query = str(os.environ.get("TIKHUB_QUERY") or TIKHUB_DEFAULT_QUERY).strip()
    base_url = str(os.environ.get("TIKHUB_API_BASE_URL") or TIKHUB_API_BASE_DEFAULT).strip()
    status["attempted"] = True
    try:
        items, diagnostics = fetch_tikhub_search(
            session,
            api_key=api_key,
            query=query,
            now=now,
            max_results=int(status["effective_result_cap"]),
            platforms=status["platforms"],
            base_url=base_url,
        )
        status["ok"] = True
        status["item_count"] = len(items)
        status["diagnostics"] = diagnostics
        return items, status
    except Exception as exc:
        status["ok"] = False
        status["error"] = type(exc).__name__
        return [], status


def has_mojibake_noise(text: str) -> bool:
    if not text:
        return False
    return bool(re.search(r"(Ã|Â|â€|æ·|�)", text))


def normalize_source_for_display(site_id: str, source: str, url: str) -> str:
    src = (source or "").strip()
    if not src:
        host = host_of_url(url)
        if host.startswith("www."):
            host = host[4:]
        return host or "未分区"
    if site_id == "buzzing" and src.lower() == "buzzing":
        host = host_of_url(url)
        if host.startswith("www."):
            host = host[4:]
        return host or src
    return src


def is_ai_related_record(record: dict[str, Any]) -> bool:
    if has_mojibake_noise(str(record.get("source") or "")) or has_mojibake_noise(str(record.get("title") or "")):
        return False
    return bool(score_ai_relevance(record)["is_ai_related"])


def load_title_zh_cache(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            # Note: keep empty-string values (e.g. title-enhance negative-cache
            # entries under TITLE_ENHANCE_CACHE_PREFIX) so they survive reload
            # instead of being retried every run.
            return {str(k): str(v) for k, v in data.items() if str(k).strip()}
    except Exception:
        pass
    return {}


def translate_to_zh_cn(session: requests.Session, text: str) -> str | None:
    s = (text or "").strip()
    if not s:
        return None
    try:
        r = session.get(
            "https://translate.googleapis.com/translate_a/single",
            params={
                "client": "gtx",
                "sl": "auto",
                "tl": "zh-CN",
                "dt": "t",
                "q": s,
            },
            timeout=12,
        )
        r.raise_for_status()
        payload = r.json()
        if not isinstance(payload, list) or not payload:
            return None
        segs = payload[0]
        if not isinstance(segs, list):
            return None
        translated = "".join(str(seg[0]) for seg in segs if isinstance(seg, list) and seg and seg[0])
        translated = translated.strip()
        if translated and translated != s:
            return translated
    except Exception:
        return None
    return None


ZH_CACHE_DS_PREFIX = "ds1|"

TRANSLATION_GLOSSARY_FILENAME = "translation-glossary.txt"

# 进程级词表缓存：None 表示尚未加载，加载后为 (protected_terms, repairs)。
_GLOSSARY_CACHE: tuple[list[str], list[tuple[str, str, str | None]]] | None = None


def load_translation_glossary(
    path: str | Path = TRANSLATION_GLOSSARY_FILENAME,
) -> tuple[list[str], list[tuple[str, str, str | None]]]:
    """解析根目录翻译词表，返回 (protected_terms, repairs)。

    词表格式（fork 用户直接编辑 translation-glossary.txt）：
    - 普通行 = 保护术语（翻译时保留原文）
    - ``bad => good [@guard]`` = 修正规则；guard 表示只有英文原标题
      包含该关键词（大小写不敏感）才执行替换，可省略。
    文件缺失或解析异常时静默返回空表，fork 删掉文件也不影响管线。
    """
    protected_terms: list[str] = []
    repairs: list[tuple[str, str, str | None]] = []
    try:
        p = Path(path)
        if not p.is_absolute():
            p = Path(__file__).resolve().parent.parent / p
        for raw_line in p.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=>" in line:
                bad, _, rest = line.partition("=>")
                bad = bad.strip()
                rest = rest.strip()
                guard: str | None = None
                if "@" in rest:
                    good_part, _, guard_part = rest.rpartition("@")
                    good = good_part.strip()
                    guard = guard_part.strip() or None
                else:
                    good = rest
                if bad and good:
                    repairs.append((bad, good, guard))
            else:
                protected_terms.append(line)
    except Exception:
        return [], []
    return protected_terms, repairs


def _get_translation_glossary() -> tuple[list[str], list[tuple[str, str, str | None]]]:
    global _GLOSSARY_CACHE
    if _GLOSSARY_CACHE is None:
        _GLOSSARY_CACHE = load_translation_glossary()
    return _GLOSSARY_CACHE


def translate_to_zh_deepseek(text: str, timeout: int = 20) -> str | None:
    s = (text or "").strip()
    if not s:
        return None
    api_key = str(os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    if not api_key:
        return None
    base_url = str(os.environ.get("DEEPSEEK_API_BASE_URL") or "https://api.deepseek.com").strip().rstrip("/")
    model = str(os.environ.get("DEEPSEEK_MODEL") or "deepseek-v4-flash").strip()
    protected_terms, _ = _get_translation_glossary()
    if protected_terms:
        term_list = "、".join(protected_terms)
    else:
        term_list = "Codex、Claude、OpenAI、Anthropic、Hugging Face、The Information"
    system_prompt = (
        "你是科技新闻编辑，把英文 AI/科技新闻标题翻译成地道的简体中文。"
        "产品名、公司名、模型名、媒体名、人名一律保留英文原文不翻译"
        f"（如 {term_list}）。"
        "用自然的中文表达，说人话，避免翻译腔。"
        "只返回译文本身，不加引号，不加解释，长度贴近原标题的信息量。"
    )
    try:
        r = requests.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": s},
                ],
            },
            timeout=timeout,
        )
        if r.status_code != 200:
            return None
        payload = r.json()
        choices = payload.get("choices") if isinstance(payload, dict) else None
        if not isinstance(choices, list) or not choices:
            return None
        content = str(((choices[0] or {}).get("message") or {}).get("content") or "").strip()
        content = content.strip("\"'“”「」").strip()
        if content and content != s:
            return content
    except Exception:
        return None
    return None


def repair_zh_title_translation(original: str, translated: str) -> str:
    """Repair recurring machine-translation errors in AI product/news titles."""
    source = str(original or "")
    result = str(translated or "").strip()
    if not result:
        return result
    if re.search(r"\bCodex\b", source, re.I):
        result = result.replace("法典", "Codex")
    if re.search(r"\bBug Bounty\b", source, re.I):
        result = result.replace("错误赏金", "漏洞悬赏").replace("Bug 赏金", "漏洞悬赏")
    if re.search(r"\bBio Bug Bounty\b", source, re.I):
        result = result.replace("生物漏洞悬赏", "生物安全漏洞悬赏")
    if re.search(r"\brepositor(?:y|ies)\b", source, re.I):
        result = result.replace("存储库", "代码仓库")
    if re.search(r"\bdesktop app\b", source, re.I):
        result = result.replace("桌面应用程序", "桌面应用")
    # 模型架构 Transformer 被译成电影名；排除原文明显在谈电影/玩具的场景防误伤。
    if re.search(r"\btransformers?\b", source, re.I) and not re.search(
        r"\b(movie|film|trailer|hasbro|toy)\b", source, re.I
    ):
        result = result.replace("变形金刚", "Transformer")
    # 公司名 Hugging Face 被直译；仅当原文出现该公司名时才替换。
    if re.search(r"\bHugging\s*Face\b", source, re.I):
        result = result.replace("拥抱脸", "Hugging Face").replace("抱抱脸", "Hugging Face")
    # 公司名 OpenAI 偶尔被拆词直译；"开放人工智能"日常中文几乎不用，误伤面小。
    if re.search(r"\bOpenAI\b", source, re.I):
        result = result.replace("开放人工智能", "OpenAI")
    # 公司名 Anthropic 被误译为哲学词；仅替换"人择"这类专有误译，不动泛指"人类"的句子。
    if re.search(r"\bAnthropic\b", source, re.I):
        result = result.replace("人择", "Anthropic").replace("人类学公司", "Anthropic")
    # 媒体名 The Information 被译成普通名词；只替换书名号/报社式误译，避免动正文里的"信息"。
    if re.search(r"\bThe Information\b", source):
        result = result.replace("《信息》", "The Information").replace("信息报", "The Information")
    # 模型名 Gemini 被译成星座；AI 信源里原文含 Gemini 基本都指模型。
    if re.search(r"\bGemini\b", source):
        result = result.replace("双子座", "Gemini")
    # 模型名 Llama 被译成动物名；仅当原文点名 Llama 时替换。
    if re.search(r"\bLlama\b", source, re.I):
        result = result.replace("骆驼", "Llama").replace("羊驼", "Llama")
    # 产品名 Copilot 被直译；仅当原文出现 Copilot 时替换，不影响航空语境。
    if re.search(r"\bCopilot\b", source, re.I):
        result = result.replace("副驾驶", "Copilot")
    # 产品名 Cursor 被译成"光标"；仅当原文以大写 Cursor 出现（产品名写法）时替换。
    if re.search(r"\bCursor\b", source):
        result = result.replace("光标", "Cursor")
    # 公司名 Perplexity 被译成"困惑"；大小写敏感匹配，避免误伤指标含义的 perplexity。
    if re.search(r"\bPerplexity\b", source):
        result = result.replace("困惑", "Perplexity")
    # 词表修正规则（translation-glossary.txt）：guard 语义与上面硬编码规则一致——
    # 只有英文原标题包含 guard 关键词才替换，防误伤。
    _, glossary_repairs = _get_translation_glossary()
    for bad, good, guard in glossary_repairs:
        if bad not in result:
            continue
        if guard and not re.search(re.escape(guard), source, re.I):
            continue
        result = result.replace(bad, good)
        # 替换目标为纯 ASCII 术语时，清理机翻残留的紧贴书名号，如《Fable 5》→ Fable 5。
        if good.isascii():
            result = re.sub(r"《(" + re.escape(good) + r"[^《》]*)》", r"\1", result)
    return result


ZH_TRANSLATION_REFUSAL_MARKERS = [
    "抱歉",
    "我无法处理",
    "我无法翻译",
    "我无法提供",
    "sorry",
    "cannot",
    "i can't",
    "无法处理",
    "请提供",
    "请直接提供",
]
_ZH_REFUSAL_LEADING_STRIP_RE = re.compile(r'^[\s"\'“”‘’「」『』(（,，.。:：]+')


def _looks_like_translation_refusal(text: str) -> bool:
    """A real refusal ("抱歉，我无法处理链接内容。请直接提供英文标题文本。")
    leads with its refusal phrase. A genuine headline translation can also
    contain "抱歉"/"我无法" as ordinary vocabulary anywhere mid-sentence (e.g.
    "OpenAI 老板...深感抱歉", "我无法想象没有他的生活") — matching those as a
    substring anywhere in the text produces false positives, seen on 22 real
    cached translations. Requiring the marker to lead the (punctuation-
    stripped) text scopes this to actual refusal-style openings only."""
    lowered = _ZH_REFUSAL_LEADING_STRIP_RE.sub("", text.lower())
    return any(lowered.startswith(marker.lower()) for marker in ZH_TRANSLATION_REFUSAL_MARKERS)


def is_valid_zh_translation(original: str, translated: str, *, strict: bool = True) -> bool:
    """Validate a raw MT/LLM translation candidate before it's cached and
    shown as an item's headline. Rejects two recurring failure modes seen
    with SocialData X titles that collapse to a bare t.co link after
    `compact_public_snippet` truncation:
    - LLM refusal sentences (e.g. DeepSeek replying "抱歉，我无法处理链接内容。
      请直接提供英文标题文本。" instead of translating a link-only "title").
    - Degenerate/too-short outputs (e.g. a full headline translated down to
      a single fragment like "前体" / "Precursor").
    Reuses the length/CJK-count sanity checks from `enhance_title_deepseek()`'s
    validator; skips its stricter entity-echo check since that's tuned for
    title rewrites, not plain translation.

    `strict=False` (used to re-validate existing cache entries) only checks
    refusal phrases plus the `cjk_count >= 4` degenerate floor, skipping the
    `8 <= effective_len <= 36` band: that upper/lower band is tuned for
    freshly-generated `enhance_title_deepseek()`-style rewrites, but short
    yet complete plain translations of already-terse titles (e.g. a 7-char
    cached translation of a 5-word title) are legitimate and get corrected
    for glossary mismatches by `repair_zh_title_translation()`, not rejected.
    """
    text = str(translated or "").strip()
    if not text or not has_cjk(text):
        return False
    if _looks_like_translation_refusal(text):
        return False
    cjk_count, effective_len = _title_enhance_effective_length(text)
    if cjk_count < 4:
        return False
    if strict and not (8 <= effective_len <= 36):
        return False
    return True


def agentmail_title_translation_input(title: str) -> str:
    """Remove trailing emoji/decorative markers that often make newsletter titles hard to translate."""
    cleaned = re.sub(r"[^\w\s.,:;!?&'()/+-]", "", str(title or ""), flags=re.UNICODE)
    cleaned = re.sub(r"[\s,，、·|/\\:;!！?？.\-–—_]+$", "", cleaned).strip()
    return cleaned or str(title or "").strip()


def is_acceptable_agentmail_translation(translated: str) -> bool:
    text = str(translated or "").strip()
    return bool(text and has_cjk(text) and not _looks_like_translation_refusal(text))


def add_bilingual_fields(
    items_ai: list[dict[str, Any]],
    items_all: list[dict[str, Any]],
    session: requests.Session,
    cache: dict[str, str],
    max_new_translations: int,
    max_new_translations_all: int = 0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, str]]:
    zh_by_url: dict[str, str] = {}
    for it in items_all:
        title = str(it.get("title") or "").strip()
        url = normalize_url(str(it.get("url") or ""))
        if title and url and has_cjk(title):
            zh_by_url[url] = title

    translated_now_ai = 0
    translated_now_all = 0

    def enrich(item: dict[str, Any], allow_translate: bool, is_ai_pool: bool) -> dict[str, Any]:
        nonlocal translated_now_ai, translated_now_all
        out = dict(item)
        title = str(out.get("title") or "").strip()
        url = normalize_url(str(out.get("url") or ""))
        is_agentmail_item = str(out.get("site_id") or "") == "agentmail"
        provided_zh = str(out.pop("provided_title_zh", "") or "").strip()
        provided_en_raw = str(out.pop("provided_title_en", "") or "").strip()
        provided_en = provided_en_raw if is_mostly_english(provided_en_raw) else ""

        out["title_original"] = title
        out["title_en"] = None
        out["title_zh"] = None
        out["title_bilingual"] = title

        if provided_en:
            zh_title = provided_zh if has_cjk(provided_zh) else (title if has_cjk(title) else "")
            out["title_original"] = provided_en
            out["title_en"] = provided_en
            out["title_zh"] = zh_title or None
            out["title_bilingual"] = f"{zh_title} / {provided_en}" if zh_title else provided_en
            return out

        if has_cjk(title):
            out["title_zh"] = title
            return out

        english_probe = agentmail_title_translation_input(title) if is_agentmail_item else title
        if not is_mostly_english(english_probe):
            return out

        out["title_en"] = title

        has_ds_key = bool(str(os.environ.get("DEEPSEEK_API_KEY") or "").strip())
        cache_hit_key: str | None = None
        zh_title = zh_by_url.get(url)
        if not zh_title:
            ds_key = ZH_CACHE_DS_PREFIX + title
            cached_ds = cache.get(ds_key)
            if cached_ds and (
                is_valid_zh_translation(title, cached_ds, strict=False)
                or (is_agentmail_item and is_acceptable_agentmail_translation(cached_ds))
            ):
                zh_title = cached_ds
                cache_hit_key = ds_key
            elif not has_ds_key:
                # 谷歌时代的裸 key 旧缓存只在 DeepSeek 不可用时兜底命中；
                # 有 key 时视为 miss，触发 DeepSeek 重译逐步替换旧翻译。
                cached_google = cache.get(title)
                if cached_google and (
                    is_valid_zh_translation(title, cached_google, strict=False)
                    or (is_agentmail_item and is_acceptable_agentmail_translation(cached_google))
                ):
                    zh_title = cached_google
                    cache_hit_key = title
        if not zh_title and allow_translate:
            budget = max_new_translations if is_ai_pool else max_new_translations_all
            translated_now = translated_now_ai if is_ai_pool else translated_now_all
            if translated_now < budget:
                translation_input = english_probe
                tr = translate_to_zh_deepseek(translation_input)
                if tr and (is_valid_zh_translation(title, tr) or (is_agentmail_item and is_acceptable_agentmail_translation(tr))):
                    zh_title = repair_zh_title_translation(title, tr)
                    cache[ZH_CACHE_DS_PREFIX + title] = zh_title
                    if is_ai_pool:
                        translated_now_ai += 1
                    else:
                        translated_now_all += 1
                else:
                    tr = translate_to_zh_cn(session, translation_input)
                    if tr and (is_valid_zh_translation(title, tr) or (is_agentmail_item and is_acceptable_agentmail_translation(tr))):
                        zh_title = repair_zh_title_translation(title, tr)
                        cache[title] = zh_title
                        if is_ai_pool:
                            translated_now_ai += 1
                        else:
                            translated_now_all += 1

        if zh_title:
            zh_title = repair_zh_title_translation(title, zh_title)
            if cache_hit_key and cache.get(cache_hit_key) != zh_title:
                cache[cache_hit_key] = zh_title
            out["title_zh"] = zh_title
            out["title_bilingual"] = f"{zh_title} / {title}"
        return out

    if max_new_translations > 0:
        # AgentMail items are visible in the default AI timeline too; warm
        # them before other AI sources consume the smaller primary cap.
        for it in items_ai:
            if str(it.get("site_id") or "") == "agentmail":
                enrich(it, allow_translate=True, is_ai_pool=True)
    ai_out = [enrich(it, allow_translate=True, is_ai_pool=True) for it in items_ai]
    if max_new_translations_all > 0:
        # AgentMail newsletter items often enter only the broad/all pool; warm
        # their translations before broader public-source noise consumes the cap.
        for it in items_all:
            if str(it.get("site_id") or "") == "agentmail":
                enrich(it, allow_translate=True, is_ai_pool=False)
    all_out = [
        enrich(it, allow_translate=max_new_translations_all > 0, is_ai_pool=False) for it in items_all
    ]
    return ai_out, all_out, cache


TITLE_ENHANCE_CACHE_PREFIX = "te1|"

RECOMMEND_REASON_CACHE_PREFIX = "re1|"

_TITLE_ENHANCE_GATED_TIERS = {"discussion", "aggregate", "community"}
_TITLE_ENHANCE_EXEMPT_TIERS = {"official", "curated"}

_TITLE_ENHANCE_YEAR_SUFFIX_RE = re.compile(r"[(（]20\d{2}[)）]\s*$")

_TITLE_ENHANCE_ENTITY_RE = re.compile(r"[A-Za-z][A-Za-z0-9]+")


def title_needs_enhance(item: dict[str, Any]) -> bool:
    """Gate for the micro-crawl + DeepSeek title-rewrite step: many source
    titles are bare product/company names or jargon-heavy aggregator titles
    that don't read as self-explanatory news headlines."""
    site_id = str(item.get("site_id") or "").strip().lower()
    tier = str(item.get("source_tier") or "").strip().lower()
    if site_id == "official_ai" or tier in _TITLE_ENHANCE_EXEMPT_TIERS:
        return False

    zh_title = str(item.get("title_zh") or "").strip()
    en_title = str(item.get("title_en") or item.get("title_original") or "").strip()
    effective_title = zh_title or en_title

    # Upstream-pre-translated cryptic titles ending in a parenthesized year
    # (half-width "(2025)" or full-width "（2025）") are a strong "this is an
    # aggregator/discussion repost, not a real headline" signal on their own.
    # This must run BEFORE the CJK-length exemption below: those titles are
    # often long CJK strings that would otherwise be waved through as
    # already self-explanatory.
    if (
        tier in _TITLE_ENHANCE_GATED_TIERS
        and effective_title
        and _TITLE_ENHANCE_YEAR_SUFFIX_RE.search(effective_title)
    ):
        return True

    # A decent-length Chinese title is already self-explanatory; never gate it,
    # regardless of tier. Guards against CJK titles false-positiving on the
    # space-separated word-count rule below (CJK has no spaces).
    if effective_title and has_cjk(effective_title) and len(effective_title) >= 12:
        return False

    # Word-count rule only makes sense for genuinely English titles.
    if en_title and is_mostly_english(en_title) and 1 <= len(en_title.split()) <= 4:
        return True

    if tier in _TITLE_ENHANCE_GATED_TIERS:
        if effective_title and len(effective_title) < 18:
            return True
        if en_title and _TITLE_ENHANCE_YEAR_SUFFIX_RE.search(en_title):
            return True

    return False


def _fetch_context_bytes(
    session: requests.Session, url: str, headers: dict[str, str], timeout: int, limit: int = 512 * 1024
) -> bytes:
    """Stream up to `limit` bytes from `url`, closing the connection early.
    Any failure (non-200, timeout, connection error) yields b""."""
    resp = None
    try:
        resp = session.get(url, timeout=timeout, headers=headers, stream=True)
        resp.raise_for_status()
        chunks: list[bytes] = []
        total = 0
        for chunk in resp.iter_content(chunk_size=8192):
            if not chunk:
                continue
            chunks.append(chunk)
            total += len(chunk)
            if total >= limit:
                break
        return b"".join(chunks)
    except Exception:
        return b""
    finally:
        if resp is not None:
            try:
                resp.close()
            except Exception:
                pass


def _parse_html_page_context(raw: bytes, max_paragraphs: int = 3) -> str:
    if not raw:
        return ""
    soup = BeautifulSoup(raw, "html.parser")

    parts: list[str] = []
    for attrs in (
        {"property": "og:description"},
        {"name": "description"},
        {"name": "twitter:description"},
        {"property": "twitter:description"},
    ):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            text = str(tag.get("content")).strip()
            if text:
                parts.append(text)

    p_count = 0
    for p in soup.find_all("p"):
        if p_count >= max_paragraphs:
            break
        if p.find_parent(["script", "style", "nav"]):
            continue
        text = p.get_text(" ", strip=True)
        if text:
            parts.append(text)
            p_count += 1

    return "\n".join(part for part in parts if part).strip()


_JINA_MD_LINK_RE = re.compile(r"!?\[[^\]]*\]\([^)]*\)")
_JINA_MD_BULLET_RE = re.compile(r"^[*\-+]\s+|^\d+\.\s+")


def _jina_line_is_prose(line: str) -> bool:
    """Heuristic to skip nav-menu markdown link spaghetti (e.g. ProductHunt's
    "* [Best of the day](https://...)" sidebar rows) while keeping real body
    text. Strips markdown link syntax and bullet/heading markup; a line is
    treated as prose only if enough plain text remains."""
    stripped = _JINA_MD_LINK_RE.sub("", line)
    stripped = _JINA_MD_BULLET_RE.sub("", stripped)
    stripped = re.sub(r"[#>*_`|]", " ", stripped)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    return len(stripped) >= 20


def _parse_jina_reader_context(raw: bytes, max_lines: int = 40, max_prose_lines: int = 3) -> str:
    """r.jina.ai renders a page to markdown; the first line is
    "Title: <descriptive page title>" followed by "URL Source: ..." and
    "Markdown Content: ..." section markers before the actual body text."""
    if not raw:
        return ""
    try:
        text = raw.decode("utf-8", errors="ignore")
    except Exception:
        return ""
    lines = [ln.strip() for ln in text.splitlines()]

    title_line = next((ln for ln in lines if ln.lower().startswith("title:")), "")

    content_lines: list[str] = []
    for ln in lines[:max_lines]:
        if len(content_lines) >= max_prose_lines:
            break
        if not ln or ln.lower().startswith(("title:", "url source:", "markdown content:")):
            continue
        if not _jina_line_is_prose(ln):
            continue
        content_lines.append(ln)

    if not content_lines:
        # No real prose in the first 40 lines (nav-heavy page). The title
        # alone is often informative enough — PH-style titles read as full
        # descriptive sentences — so fall back to just that.
        return title_line.strip()

    parts = ([title_line] if title_line else []) + content_lines
    return "\n".join(part for part in parts if part).strip()


def fetch_title_context(session: requests.Session, url: str) -> str:
    """Micro-crawl the source page for enough context (meta descriptions +
    first paragraphs) to let the LLM rewrite a terse title informatively.
    Any failure or empty extraction returns "" so callers can skip cleanly.

    Some sources (e.g. ProductHunt) sit behind Cloudflare and 403 a direct
    crawl. When the direct fetch yields no usable context, fall back to a
    single request through r.jina.ai — a free, keyless third-party reader
    proxy (~20 rpm) that renders the page to markdown. This only fires on
    direct-fetch failure and is gated by the same TITLE_ENHANCE_MAX_PER_RUN
    cap as the LLM call, so it stays well under the reader's rate limit.
    """
    u = str(url or "").strip()
    if not u:
        return ""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml",
    }
    raw = _fetch_context_bytes(session, u, headers, timeout=8)
    context = _parse_html_page_context(raw)
    if context:
        return context[:800]

    jina_headers = {"Accept": "text/plain"}
    jina_raw = _fetch_context_bytes(session, f"https://r.jina.ai/{u}", jina_headers, timeout=15)
    jina_context = _parse_jina_reader_context(jina_raw)
    return jina_context[:800]


FULL_TEXT_CONTEXT_CHAR_CAP = 3500


def fetch_full_text_context(session: requests.Session, url: str) -> str:
    """Micro-crawl the source page for real article body text (not just a
    short snippet) so an LLM can write a genuine, fact-grounded "why this is
    worth reading" reason. Shares the same fetch machinery as
    `fetch_title_context()` (byte-stream cap, direct-fetch-then-jina-fallback
    strategy) but with much higher paragraph/line extraction limits and a
    larger char cap, since we want real body content rather than a
    description-length snippet. Any failure or empty extraction returns ""
    so callers can skip cleanly.
    """
    u = str(url or "").strip()
    if not u:
        return ""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml",
    }
    raw = _fetch_context_bytes(session, u, headers, timeout=8)
    context = _parse_html_page_context(raw, max_paragraphs=40)
    if context:
        return context[:FULL_TEXT_CONTEXT_CHAR_CAP]

    jina_headers = {"Accept": "text/plain"}
    jina_raw = _fetch_context_bytes(session, f"https://r.jina.ai/{u}", jina_headers, timeout=15)
    jina_context = _parse_jina_reader_context(jina_raw, max_lines=400, max_prose_lines=60)
    return jina_context[:FULL_TEXT_CONTEXT_CHAR_CAP]


def _title_enhance_entity_tokens(title: str) -> list[str]:
    return [tok for tok in _TITLE_ENHANCE_ENTITY_RE.findall(str(title or "")) if len(tok) >= 2]


_TITLE_ENHANCE_TOKEN_RE = re.compile(r"[A-Za-z0-9.+-]+")


def _title_enhance_effective_length(text: str) -> tuple[int, int]:
    """Length validation uses editorial "字" count, not raw chars: a title
    that correctly keeps English entities verbatim (Claude, ChatGPT, Cursor)
    blows past a raw-char cap even when it reads as a normal-length headline.
    Returns (cjk_char_count, effective_length) where each CJK char counts 1,
    each latin/alnum token (a run of [A-Za-z0-9.+-]+) counts as one "word"
    worth 2 if it contains a letter (Claude -> 2, not 6) else 1 (bare digit
    runs like a year); punctuation and spaces are free."""
    s = str(text or "")
    cjk_count = len(re.findall(r"[一-鿿]", s))
    weight = 0
    for token in _TITLE_ENHANCE_TOKEN_RE.findall(s):
        weight += 2 if re.search(r"[A-Za-z]", token) else 1
    return cjk_count, cjk_count + weight


def enhance_title_deepseek(title: str, context: str, timeout: int = 45) -> str | None:
    """Rewrite a terse/jargon title into an informative Chinese one-liner,
    grounded in `context` (micro-crawled page text). Validates the candidate
    before returning so a non-None result can be trusted by callers."""
    title_s = str(title or "").strip()
    context_s = str(context or "").strip()
    if not title_s:
        return None
    api_key = str(os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    if not api_key:
        return None
    base_url = str(os.environ.get("DEEPSEEK_API_BASE_URL") or "https://api.deepseek.com").strip().rstrip("/")
    model = str(os.environ.get("DEEPSEEK_MODEL") or "deepseek-v4-flash").strip()
    system_prompt = (
        "你是科技新闻编辑，负责把语焉不详、看不出信息量的英文标题改写成一条完整的中文资讯标题。"
        "输出一条中文资讯标题，不超过28个字（英文名称按一个词计）。"
        "原文中的关键实体（公司名、产品名、人名）必须原样保留英文，不要翻译或音译。"
        "不得编造原文和参考资料之外的数字或事实。"
        "使用新闻陈述语气，不要营销口号腔调。"
        "只输出标题本身，不加引号，不加任何解释。"
    )
    user_content = f"原标题：{title_s}"
    if context_s:
        user_content += f"\n\n参考网页内容：\n{context_s}"
    try:
        r = requests.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "temperature": 0.3,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
            },
            timeout=timeout,
        )
        if r.status_code != 200:
            return None
        payload = r.json()
        choices = payload.get("choices") if isinstance(payload, dict) else None
        if not isinstance(choices, list) or not choices:
            return None
        content = str(((choices[0] or {}).get("message") or {}).get("content") or "").strip()
        content = content.strip("\"'“”「」").strip()
    except Exception:
        return None

    if not content or not has_cjk(content):
        return None
    cjk_count, effective_len = _title_enhance_effective_length(content)
    if cjk_count < 4 or not (8 <= effective_len <= 36):
        return None

    entities = _title_enhance_entity_tokens(title_s)
    if entities:
        lowered = content.lower()
        if not any(tok.lower() in lowered for tok in entities):
            return None

    return content


def add_title_enhancements(
    items_ai: list[dict[str, Any]],
    session: requests.Session,
    cache: dict[str, str],
    max_new_per_run: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Micro-crawl + DeepSeek-rewrite gated items_ai entries into an
    informative `title_enhanced_zh`. No-ops entirely without a DeepSeek key."""
    if not str(os.environ.get("DEEPSEEK_API_KEY") or "").strip():
        return items_ai, cache

    if max_new_per_run is None:
        try:
            max_new_per_run = int(os.environ.get("TITLE_ENHANCE_MAX_PER_RUN") or 30)
        except Exception:
            max_new_per_run = 30
    max_new_per_run = max(0, max_new_per_run)

    used = 0
    out: list[dict[str, Any]] = []
    for item in items_ai:
        new_item = dict(item)
        if not title_needs_enhance(new_item):
            out.append(new_item)
            continue

        url = normalize_url(str(new_item.get("url") or ""))
        title = str(
            new_item.get("title_en") or new_item.get("title_original") or new_item.get("title") or ""
        ).strip()
        cache_key = TITLE_ENHANCE_CACHE_PREFIX + hashlib.sha1(f"{url}|{title}".encode("utf-8")).hexdigest()

        if cache_key in cache:
            cached = cache.get(cache_key) or ""
            if cached:
                new_item["title_enhanced_zh"] = cached
            out.append(new_item)
            continue

        if used >= max_new_per_run:
            out.append(new_item)
            continue

        used += 1
        context = fetch_title_context(session, str(new_item.get("url") or ""))
        if not context:
            cache[cache_key] = ""
            out.append(new_item)
            continue

        enhanced = enhance_title_deepseek(title, context)
        if enhanced:
            cache[cache_key] = enhanced
            new_item["title_enhanced_zh"] = enhanced
        else:
            cache[cache_key] = ""
        out.append(new_item)

    return out, cache


def generate_recommend_reason_deepseek(
    title: str, full_text: str, session: requests.Session | None = None, timeout: int = 45
) -> str | None:
    """Given the real article title + full text, write one Chinese sentence
    explaining concretely what this specific piece covers and why it's worth
    reading. Unlike `enhance_title_deepseek()` this is prose, not a structured
    title, so validation only does a basic sanity check (non-empty, has CJK,
    reasonable length, not a verbatim echo of the title) rather than the
    stricter entity/length rules used for title rewrites. `session` is
    accepted for calling-convention parity with the rest of this module's
    fetch helpers but is unused: the DeepSeek call itself is a one-off POST,
    same as `enhance_title_deepseek()`. Returns None on any failure (network
    error, empty text, validation failure)."""
    title_s = str(title or "").strip()
    text_s = str(full_text or "").strip()
    if not title_s or not text_s:
        return None
    api_key = str(os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    if not api_key:
        return None
    base_url = str(os.environ.get("DEEPSEEK_API_BASE_URL") or "https://api.deepseek.com").strip().rstrip("/")
    model = str(os.environ.get("DEEPSEEK_MODEL") or "deepseek-v4-flash").strip()
    system_prompt = (
        "你是科技新闻编辑，负责为一篇具体的文章写一句「为什么值得读」的中文推荐语。"
        "输出一句中文，40到80个字之间。"
        "必须引用原文中的具体事实、数字或细节，讲清楚这篇内容具体讲了什么，不能写空洞的营销话术。"
        "不得编造原文之外的数字或事实。"
        "原文中的关键实体（公司名、产品名、人名）保留英文原样，不要翻译或音译。"
        "只输出这一句推荐语本身，不加引号，不加任何解释或前缀。"
    )
    user_content = f"标题：{title_s}\n\n正文：\n{text_s}"
    try:
        r = requests.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "temperature": 0.3,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
            },
            timeout=timeout,
        )
        if r.status_code != 200:
            return None
        payload = r.json()
        choices = payload.get("choices") if isinstance(payload, dict) else None
        if not isinstance(choices, list) or not choices:
            return None
        content = str(((choices[0] or {}).get("message") or {}).get("content") or "").strip()
        content = content.strip("\"'“”「」").strip()
    except Exception:
        return None

    if not content or not has_cjk(content):
        return None
    if len(content) < 10 or len(content) > 200:
        return None
    if content.strip() == title_s.strip():
        return None

    return content


def _recommend_reason_summary_is_placeholder(summary: str, title: str) -> bool:
    """Heuristic for "this item's summary field isn't real editorial content
    and is worth backfilling with fetched full-text": empty, or just a copy
    of the title (a common upstream fallback, see `waytoagi`'s
    `summary = title` pattern above)."""
    s = str(summary or "").strip()
    if not s:
        return True
    return s == str(title or "").strip()


def add_recommend_reasons(
    items_ai: list[dict[str, Any]],
    session: requests.Session,
    cache: dict[str, str],
    max_new_per_run: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Full-text-fetch + DeepSeek-authored, per-item `recommend_reason_zh`
    for the already AI-relevance-filtered `items_ai` set (same scope as
    `add_title_enhancements()` — deliberately not expanded to the unfiltered
    pool, to control fetch/LLM cost). No-ops entirely without a DeepSeek key.
    Uses an independent per-run budget (`REASON_ENHANCE_MAX_PER_RUN`) from
    title enhancement, since full-text fetch + reasoning is more expensive
    per item; shares the same on-disk cache dict/file as title enhancement
    (distinct `RECOMMEND_REASON_CACHE_PREFIX` key namespace) for consistency."""
    if not str(os.environ.get("DEEPSEEK_API_KEY") or "").strip():
        return items_ai, cache

    if max_new_per_run is None:
        try:
            max_new_per_run = int(os.environ.get("REASON_ENHANCE_MAX_PER_RUN") or 30)
        except Exception:
            max_new_per_run = 30
    max_new_per_run = max(0, max_new_per_run)

    used = 0
    out: list[dict[str, Any]] = []
    for item in items_ai:
        new_item = dict(item)
        url = normalize_url(str(new_item.get("url") or ""))
        title = str(
            new_item.get("title_en") or new_item.get("title_original") or new_item.get("title") or ""
        ).strip()
        cache_key = RECOMMEND_REASON_CACHE_PREFIX + hashlib.sha1(f"{url}|{title}".encode("utf-8")).hexdigest()

        if cache_key in cache:
            cached = cache.get(cache_key) or ""
            if cached:
                new_item["recommend_reason_zh"] = cached
            out.append(new_item)
            continue

        if not title or used >= max_new_per_run:
            out.append(new_item)
            continue

        used += 1
        full_text = fetch_full_text_context(session, str(new_item.get("url") or ""))
        if not full_text:
            cache[cache_key] = ""
            out.append(new_item)
            continue

        reason = generate_recommend_reason_deepseek(title, full_text)
        if reason:
            cache[cache_key] = reason
            new_item["recommend_reason_zh"] = reason
        else:
            cache[cache_key] = ""

        if _recommend_reason_summary_is_placeholder(str(new_item.get("summary") or ""), title):
            new_item["summary"] = full_text[:500]

        out.append(new_item)

    return out, cache


def dedupe_items_by_title_url(items: list[dict[str, Any]], random_pick: bool = True) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        site_id = str(item.get("site_id") or "").strip().lower()
        title = str(item.get("title_original") or item.get("title") or "").strip().lower()
        url = normalize_url(str(item.get("url") or ""))
        if site_id == "aihubtoday":
            key = f"url::{url}"
        else:
            key = f"{title}||{url}"
        groups.setdefault(key, []).append(item)

    out: list[dict[str, Any]] = []
    for values in groups.values():
        if random_pick:
            out.append(random.choice(values))
        else:
            chosen = min(values, key=source_tier_sort_key)
            out.append(chosen)

    out.sort(key=source_tier_sort_key)
    return out


def suppress_near_duplicate_items(
    items: list[dict[str, Any]],
    window_hours: float = 6.0,
    similarity_threshold: float = 0.9,
) -> list[dict[str, Any]]:
    """Collapse near-identical items from the same site (rewritten syndication,
    e.g. "推出法案" vs "推出立法") that exact title||url dedup cannot catch.
    Keeps the more authoritative copy (tier, then ai_score, then earliest)."""

    def quality(item: dict[str, Any]) -> tuple:
        tier_rank = item.get("source_tier_rank")
        try:
            tier_rank = int(tier_rank)
        except Exception:
            tier_rank = 99
        try:
            score = float(item.get("ai_score") or 0)
        except Exception:
            score = 0.0
        ts = event_time(item) or datetime.max.replace(tzinfo=UTC)
        return (-tier_rank, score, -ts.timestamp())

    by_site: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        by_site.setdefault(str(item.get("site_id") or ""), []).append(item)

    dropped_ids: set[str] = set()
    for site_items in by_site.values():
        ordered = sorted(site_items, key=lambda x: event_time(x) or datetime.min.replace(tzinfo=UTC))
        kept: list[tuple[dict[str, Any], str, set[str], datetime | None]] = []
        for item in ordered:
            title = normalized_story_title(item)
            tokens = title_tokens(title)
            ts = event_time(item)
            if not title_is_mergeable(title):
                kept.append((item, title, tokens, ts))
                continue
            duplicate_of = None
            for kept_entry in reversed(kept[-60:]):
                other, other_title, other_tokens, other_ts = kept_entry
                if ts and other_ts and abs((ts - other_ts).total_seconds()) / 3600 > window_hours:
                    continue
                if not tokens or not other_tokens:
                    continue
                jaccard = len(tokens & other_tokens) / len(tokens | other_tokens)
                if jaccard < 0.5:
                    continue
                if title_similarity(title, other_title) >= similarity_threshold and story_titles_can_merge(title, other_title):
                    duplicate_of = kept_entry
                    break
            if duplicate_of is None:
                kept.append((item, title, tokens, ts))
                continue
            other = duplicate_of[0]
            if quality(item) > quality(other):
                dropped_ids.add(str(other.get("id") or id(other)))
                kept[kept.index(duplicate_of)] = (item, title, tokens, ts)
            else:
                dropped_ids.add(str(item.get("id") or id(item)))

    return [item for item in items if str(item.get("id") or id(item)) not in dropped_ids]


def canonical_story_url(raw_url: str) -> str:
    normalized = normalize_url(raw_url)
    try:
        parsed = urlparse(normalized)
    except Exception:
        return normalized
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    if query_pairs:
        identity_keys = {"id", "item", "p"}
        kept = [(k, v) for k, v in query_pairs if k.lower() in identity_keys]
        parsed = parsed._replace(query=urlencode(kept, doseq=True))
    return urlunparse(parsed).rstrip("/")


def title_tokens(title: str) -> set[str]:
    compact = re.sub(r"https?://\S+", " ", str(title or "").lower())
    tokens = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}", compact)
    return {tok for tok in tokens if tok not in TITLE_STOPWORDS and len(tok) >= 2}


def normalized_story_title(item: dict[str, Any]) -> str:
    title = str(item.get("title_original") or item.get("title") or "").strip().lower()
    if item.get("title_bilingual"):
        title = re.sub(r"\s*/\s*.+$", "", title)
    return re.sub(r"\s+", " ", title)


def title_is_mergeable(title: str) -> bool:
    tokens = title_tokens(title)
    return len(tokens) >= 4 and len(str(title or "").strip()) >= 18


def title_similarity(a: str, b: str) -> float:
    ta = title_tokens(a)
    tb = title_tokens(b)
    if not ta or not tb:
        return 0.0
    jaccard = len(ta & tb) / len(ta | tb)
    sequence = SequenceMatcher(None, a.lower(), b.lower()).ratio()
    return round(max(sequence, (sequence * 0.6) + (jaccard * 0.4)), 4)


def title_entities(title: str) -> tuple[set[str], set[str]]:
    lower = str(title or "").lower()
    vendors = {canonical for alias, canonical in VENDOR_ALIASES.items() if alias in lower}
    models = {re.sub(r"\s+", "-", match.group(1).lower()) for match in MODEL_RE.finditer(lower)}
    return vendors, models


def story_titles_can_merge(a: str, b: str) -> bool:
    vendors_a, models_a = title_entities(a)
    vendors_b, models_b = title_entities(b)
    if vendors_a and vendors_b and vendors_a.isdisjoint(vendors_b):
        return False
    if models_a and models_b and models_a.isdisjoint(models_b):
        return False
    return True


def recency_score(record: dict[str, Any], now: datetime, window_hours: int) -> float:
    ts = event_time(record)
    if not ts:
        return 0.0
    age_hours = max(0.0, (now - ts).total_seconds() / 3600)
    return max(0.0, min(1.0, (float(window_hours) - age_hours) / max(1.0, float(window_hours))))


def headline_freshness_score(record: dict[str, Any], now: datetime, half_life_hours: float = 48.0) -> float:
    ts = event_time(record)
    if not ts:
        return 0.0
    age_hours = max(0.0, (now - ts).total_seconds() / 3600)
    return max(0.0, min(1.0, 0.5 ** (age_hours / max(1.0, half_life_hours))))


def ai_relevance_score(record: dict[str, Any]) -> float:
    value = record.get("ai_relevance_score")
    if value is None:
        value = record.get("ai_score")
    if value is None and isinstance(record.get("ai_relevance"), dict):
        value = record["ai_relevance"].get("score")
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 1.0 if record.get("ai_is_related") else 0.0


def add_creator_ranking_fields(record: dict[str, Any], now: datetime) -> dict[str, Any]:
    out = dict(record)
    metrics = record.get("creator_metrics") if isinstance(record.get("creator_metrics"), dict) else {}
    likes = creator_metric_count(metrics.get("likes"))
    comments = creator_metric_count(metrics.get("comments"))
    collects = creator_metric_count(metrics.get("collects"))
    shares = creator_metric_count(metrics.get("shares"))
    weighted_engagement = likes + (comments * 2.0) + (collects * 1.5) + (shares * 2.0)

    # Xiaohongshu engagement is smaller in absolute terms than Douyin, so use
    # separate fixed log scales instead of pretending raw counts are comparable.
    scale = 22.0 if str(record.get("site_id") or "") == "tikhub_xiaohongshu" else 20.0
    heat_score = min(100.0, scale * math.log10(1.0 + weighted_engagement))
    published = event_time(record)
    age_hours = (now - published).total_seconds() / 3600 if published else float("inf")
    freshness_bonus = CREATOR_FRESHNESS_BONUS_POINTS if 0 <= age_hours <= CREATOR_FRESHNESS_BONUS_HOURS else 0.0
    hot_score = min(100.0, (heat_score * 0.85) + freshness_bonus)

    out["creator_metrics"] = {
        "likes": likes,
        "comments": comments,
        "collects": collects,
        "shares": shares,
    }
    out["creator_engagement_total"] = round(weighted_engagement, 1)
    out["creator_heat_score"] = round(heat_score, 1)
    out["creator_freshness_bonus"] = round(freshness_bonus, 1)
    out["creator_hot_score"] = round(hot_score, 1)
    return out


def editorial_score(record: dict[str, Any]) -> float:
    """External or internal editorial strength used by the headline ranker."""
    value = record.get("aihot_score")
    try:
        if value is not None:
            score = float(value)
            return max(0.0, min(1.0, score / 100 if score > 1 else score))
    except Exception:
        pass
    site_id = str(record.get("site_id") or "")
    if site_id == "official_ai":
        return 0.9
    if site_id == "aihot":
        return 0.78
    if record.get("ai_is_related"):
        return max(0.45, ai_relevance_score(record) * 0.72)
    return ai_relevance_score(record) * 0.6


def story_id_for_item(item: dict[str, Any]) -> str:
    url = canonical_story_url(str(item.get("url") or ""))
    title = normalized_story_title(item)
    # Include the title alongside the URL so that distinct notes published under
    # a shared generic URL (e.g. a wiki hub page) get distinct story ids instead
    # of colliding into a single group.
    if url and title:
        basis = f"{url}\x1f{title}"
    else:
        basis = url or title or str(item.get("id") or "")
    return "story_" + hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]


def calculate_item_importance(
    item: dict[str, Any],
    now: datetime,
    window_hours: int,
    duplicate_count: int = 1,
) -> dict[str, Any]:
    tier = str(item.get("source_tier") or source_tier_for_site(str(item.get("site_id") or "")).get("source_tier"))
    source_score = SOURCE_TIER_IMPORTANCE.get(tier, SOURCE_TIER_IMPORTANCE["other"])
    relevance = ai_relevance_score(item)
    recency = headline_freshness_score(item, now)
    editorial = editorial_score(item)
    heat = min(1.0, max(0, duplicate_count - 1) / 4)
    score = (editorial * 0.3) + (source_score * 0.22) + (relevance * 0.2) + (recency * 0.18) + (heat * 0.1)
    return {
        "score": round(max(0.0, min(1.0, score)), 4),
        "breakdown": {
            "editorial": round(editorial, 4),
            "source_tier": round(source_score, 4),
            "ai_relevance": round(relevance, 4),
            "recency": round(recency, 4),
            "story_heat": round(heat, 4),
        },
    }


def story_category(score: float, primary_item: dict[str, Any], duplicate_count: int) -> str:
    tier = str(primary_item.get("source_tier") or source_tier_for_site(str(primary_item.get("site_id") or "")).get("source_tier"))
    if tier == "official":
        return "official"
    if duplicate_count >= 3:
        return "multi_source"
    if score >= 0.72:
        return "industry"
    return "watch"


def importance_label(category: str) -> str:
    return {
        "official": "官方更新",
        "multi_source": "多源热议",
        "industry": "行业动态",
        "watch": "值得关注",
    }.get(category, "值得关注")


def choose_primary_story_item(
    items: list[dict[str, Any]],
    now: datetime,
    window_hours: int,
) -> dict[str, Any]:
    def key(item: dict[str, Any]) -> tuple[int, float, float, str]:
        tier_rank = int(source_tier_for_site(str(item.get("site_id") or "")).get("source_tier_rank", 9))
        importance = calculate_item_importance(item, now, window_hours, duplicate_count=len(items))["score"]
        ts = event_time(item)
        return (tier_rank, -importance, -(ts.timestamp() if ts else 0), str(item.get("title") or ""))

    return min(items, key=key)


def story_item_link(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "title": item.get("title_enhanced_zh") or item.get("title_bilingual") or item.get("title"),
        "title_zh": item.get("title_enhanced_zh") or item.get("title_zh"),
        "title_en": item.get("title_en"),
        "title_original": item.get("title_original"),
        "summary": item.get("summary"),
        "recommend_reason_zh": item.get("recommend_reason_zh"),
        "url": item.get("url"),
        "source": item.get("source"),
        "source_name": item.get("site_name"),
        "site_id": item.get("site_id"),
        "published_at": item.get("published_at"),
    }


def story_reasons(primary: dict[str, Any], score: float, duplicate_count: int) -> list[str]:
    reasons: list[str] = []
    tier = source_tier_for_site(str(primary.get("site_id") or ""))
    if tier["source_tier"] == "official":
        reasons.append("official_source")
    if duplicate_count >= 2:
        reasons.append("multi_source")
    if ai_relevance_score(primary) >= 0.8:
        reasons.append("high_ai_relevance")
    if score >= 0.75:
        reasons.append("high_importance")
    if not reasons:
        reasons.append("recent_ai_signal")
    return reasons


def build_story_record(
    story_id: str,
    items: list[dict[str, Any]],
    now: datetime,
    window_hours: int,
) -> dict[str, Any]:
    sorted_items = sorted(items, key=source_tier_sort_key)
    primary = choose_primary_story_item(sorted_items, now, window_hours)
    importance = calculate_item_importance(primary, now, window_hours, duplicate_count=len(items))
    score = importance["score"]
    category = story_category(score, primary, len(items))
    times = [ts for ts in (event_time(item) for item in sorted_items) if ts]
    # 与前端 timelineIso 的未来时间防御对齐：错标时区的条目漏到 story 层时，
    # earliest_at/latest_at 不得超过当前时间（精选模式排序/展示走的是这两个字段）
    story_future_limit = now + timedelta(minutes=10)
    times = [ts if ts <= story_future_limit else now for ts in times]
    source_refs = [story_item_link(item) for item in sorted_items]
    source_names = sorted({str(item.get("source") or item.get("site_name") or "") for item in sorted_items if item.get("source") or item.get("site_name")})
    title = primary.get("title_enhanced_zh") or primary.get("title_bilingual") or primary.get("title")
    url = primary.get("url")
    return {
        "story_id": story_id,
        "title": title,
        "url": url,
        "primary_url": url,
        "source": primary.get("source"),
        "source_name": primary.get("site_name"),
        "sources": source_refs,
        "source_count": len(source_refs),
        "source_names": source_names,
        "items": source_refs,
        "item_count": len(sorted_items),
        "duplicate_count": len(sorted_items),
        "score": score,
        "importance": score,
        "importance_score": score,
        "importance_label": importance_label(category),
        "importance_breakdown": importance["breakdown"],
        "category": category,
        "reasons": story_reasons(primary, score, len(sorted_items)),
        "earliest_at": iso(min(times)) if times else None,
        "latest_at": iso(max(times)) if times else None,
        "primary_item": {
            "id": primary.get("id"),
            "title": title,
            "title_zh": primary.get("title_enhanced_zh") or primary.get("title_zh"),
            "title_en": primary.get("title_en"),
            "title_original": primary.get("title_original"),
            "summary": primary.get("summary"),
            "recommend_reason_zh": primary.get("recommend_reason_zh"),
            "url": url,
            "source": primary.get("source"),
            "source_name": primary.get("site_name"),
        },
    }


def merge_story_items(
    items: list[dict[str, Any]],
    now: datetime,
    window_hours: int,
    title_window_hours: int = 6,
    title_threshold: float = 0.86,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    group_titles: dict[str, str] = {}
    group_times: dict[str, datetime | None] = {}
    group_site_ids: dict[str, str] = {}
    canonical_to_story: dict[str, list[str]] = {}
    events: list[dict[str, Any]] = []

    ordered = sorted(items, key=lambda item: event_time(item) or datetime.min.replace(tzinfo=UTC))
    for item in ordered:
        item_id = str(item.get("id") or "")
        canonical_url = canonical_story_url(str(item.get("url") or ""))
        title = normalized_story_title(item)
        item_site_id = str(item.get("site_id") or "")
        item_time = event_time(item)
        story_id: str | None = None
        reason = ""
        similarity = 0.0

        if canonical_url:
            for candidate_id in canonical_to_story.get(canonical_url, []):
                candidate_title = group_titles.get(candidate_id, "")
                candidate_site_id = group_site_ids.get(candidate_id, "")
                if (
                    item_site_id
                    and candidate_site_id == item_site_id
                    and title != candidate_title
                    and title_similarity(title, candidate_title) < title_threshold
                ):
                    # Same-site items sharing a generic/shared URL (e.g. a wiki hub
                    # page) but with clearly different titles are distinct notes,
                    # not repeated reports of one event - don't cluster them.
                    continue
                story_id = candidate_id
                reason = "canonical_url"
                similarity = 1.0
                break

        if story_id is None and title_is_mergeable(title):
            for candidate_id, candidate_title in group_titles.items():
                candidate_time = group_times.get(candidate_id)
                if item_time and candidate_time:
                    delta_hours = abs((item_time - candidate_time).total_seconds()) / 3600
                    if delta_hours > title_window_hours:
                        continue
                sim = title_similarity(title, candidate_title)
                if sim >= title_threshold and story_titles_can_merge(title, candidate_title):
                    story_id = candidate_id
                    reason = "title_similarity"
                    similarity = sim
                    break

        if story_id is None:
            story_id = story_id_for_item(item)
            groups[story_id] = []
            group_titles[story_id] = title
            group_times[story_id] = item_time
            group_site_ids[story_id] = item_site_id
            if canonical_url:
                canonical_to_story.setdefault(canonical_url, []).append(story_id)
        else:
            events.append(
                {
                    "story_id": story_id,
                    "item_id": item_id,
                    "merged_into": story_id,
                    "reason": reason,
                    "similarity": round(similarity, 4),
                }
            )
            if canonical_url:
                bucket = canonical_to_story.setdefault(canonical_url, [])
                if story_id not in bucket:
                    bucket.append(story_id)

        groups.setdefault(story_id, []).append(item)

    stories = [build_story_record(story_id, group_items, now, window_hours) for story_id, group_items in groups.items()]
    stories.sort(key=lambda story: (-float(story.get("score") or 0), str(story.get("latest_at") or ""), str(story.get("title") or "")))
    return stories, events


BRIEF_SCORE_GATE = 0.72


def story_passes_brief_gate(story: dict[str, Any]) -> bool:
    """宁缺毋滥: a story earns a brief slot via multi-source confirmation or a
    strong score. Quiet days produce a short (possibly empty) brief instead of
    a padded one."""
    try:
        sources = int(story.get("source_count") or 1)
    except Exception:
        sources = 1
    try:
        score = float(story.get("score") or 0)
    except Exception:
        score = 0.0
    return sources >= 2 or score >= BRIEF_SCORE_GATE


def select_diverse_stories(
    stories: list[dict[str, Any]],
    limit: int,
    same_source_penalty: float = 0.03,
) -> list[dict[str, Any]]:
    """Greedy top-N by score with a per-source decay so one prolific source
    cannot fill the brief, plus same-cluster suppression across the whole
    window: a story whose title near-duplicates an already picked one is
    skipped, so an event reposted hours apart (outside the merge window)
    still occupies only one slot."""
    candidates = sorted(stories, key=lambda story: (-float(story.get("score") or 0), str(story.get("title") or "")))
    picked: list[dict[str, Any]] = []
    picked_titles: list[tuple[str, set[str]]] = []
    picked_per_source: dict[str, int] = {}
    remaining = list(candidates)

    def near_duplicate_of_picked(story: dict[str, Any]) -> bool:
        title = normalized_story_title(story)
        if not title_is_mergeable(title):
            return False
        tokens = title_tokens(title)
        for other_title, other_tokens in picked_titles:
            if not tokens or not other_tokens:
                continue
            if len(tokens & other_tokens) / len(tokens | other_tokens) < 0.4:
                continue
            if title_similarity(title, other_title) >= 0.86 and story_titles_can_merge(title, other_title):
                return True
        return False

    while remaining and len(picked) < limit:
        best_idx = -1
        best_eff = float("-inf")
        for idx, story in enumerate(remaining):
            source = str(story.get("source") or story.get("source_name") or "")
            eff = float(story.get("score") or 0) - same_source_penalty * picked_per_source.get(source, 0)
            if eff > best_eff:
                best_eff = eff
                best_idx = idx
        if best_idx < 0:
            break
        chosen = remaining.pop(best_idx)
        if near_duplicate_of_picked(chosen):
            continue
        source = str(chosen.get("source") or chosen.get("source_name") or "")
        picked_per_source[source] = picked_per_source.get(source, 0) + 1
        picked.append(chosen)
        picked_titles.append((normalized_story_title(chosen), title_tokens(normalized_story_title(chosen))))
    return picked


def build_daily_brief_payload(
    stories: list[dict[str, Any]],
    generated_at: str,
    window_hours: int,
    max_items: int = 20,
) -> dict[str, Any]:
    gated = [story for story in stories if story_passes_brief_gate(story)]
    items = select_diverse_stories(gated, max_items)
    return {
        "generated_at": generated_at,
        "window_hours": window_hours,
        "total_items": len(items),
        "items": items,
    }


def build_stories_payload(
    stories: list[dict[str, Any]],
    generated_at: str,
    window_hours: int,
) -> dict[str, Any]:
    return {
        "generated_at": generated_at,
        "window_hours": window_hours,
        "total_stories": len(stories),
        "stories": stories,
    }


def build_merge_log_payload(events: list[dict[str, Any]], generated_at: str) -> dict[str, Any]:
    return {
        "generated_at": generated_at,
        "merge_strategy": "url_or_title_similarity_v0_6",
        "total_events": len(events),
        "events": events,
    }


def build_creator_hot_items(
    archive: dict[str, dict[str, Any]],
    now: datetime,
    *,
    ai_only: bool,
) -> list[dict[str, Any]]:
    window_start = now - timedelta(days=CREATOR_HOT_WINDOW_DAYS)
    items: list[dict[str, Any]] = []
    for record in archive.values():
        if str(record.get("site_id") or "") not in CREATOR_SITE_IDS:
            continue
        if not isinstance(record.get("creator_metrics"), dict):
            continue
        published = event_time(record)
        if not published or published < window_start or published > now:
            continue
        normalized = dict(record)
        normalized["title"] = maybe_fix_mojibake(str(normalized.get("title") or ""))
        normalized["source"] = maybe_fix_mojibake(normalize_source_for_display(
            str(normalized.get("site_id") or ""),
            str(normalized.get("source") or ""),
            str(normalized.get("url") or ""),
        ))
        normalized = add_ai_relevance_fields(normalized)
        if ai_only and not normalized.get("ai_is_related", is_ai_related_record(normalized)):
            continue
        normalized = add_source_tier_fields(normalized)
        items.append(add_creator_ranking_fields(normalized, now))

    deduped = suppress_near_duplicate_items(dedupe_items_by_title_url(items, random_pick=False))
    deduped.sort(
        key=lambda item: (
            float(item.get("creator_hot_score") or 0),
            event_time(item) or datetime.min.replace(tzinfo=UTC),
        ),
        reverse=True,
    )
    return deduped


def build_latest_payloads(latest_payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split initial AI payload from bulky all-mode lists for lazy browser loading."""
    slim_payload = dict(latest_payload)
    all_payload = {
        "generated_at": latest_payload.get("generated_at"),
        "window_hours": latest_payload.get("window_hours"),
        "topic_filter": latest_payload.get("topic_filter"),
        "ai_relevance_threshold": latest_payload.get("ai_relevance_threshold"),
        "total_items_raw": latest_payload.get("total_items_raw"),
        "total_items_all_mode": latest_payload.get("total_items_all_mode"),
        "items_all": latest_payload.get("items_all", []),
        "items_all_raw": latest_payload.get("items_all_raw", []),
    }
    slim_payload.pop("items_all", None)
    slim_payload.pop("items_all_raw", None)
    slim_payload["all_mode_data_url"] = "data/latest-24h-all.json"
    slim_payload["stories_data_url"] = "data/stories-merged.json"
    return slim_payload, all_payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate AI news updates from multiple sources")
    parser.add_argument("--output-dir", default="data", help="Directory for output JSON files")
    parser.add_argument("--window-hours", type=int, default=24, help="24h window size")
    parser.add_argument("--archive-days", type=int, default=21, help="Keep archive for N days")
    parser.add_argument("--translate-max-new", type=int, default=80, help="Max new EN->ZH title translations per run")
    parser.add_argument(
        "--translate-max-new-broad",
        type=int,
        default=30,
        help="Max new EN->ZH title translations per run for the broad all-items pool (independent from --translate-max-new)",
    )
    parser.add_argument("--rss-opml", default="", help="Optional OPML file path to include RSS sources")
    parser.add_argument("--rss-max-feeds", type=int, default=0, help="Optional max OPML RSS feeds to fetch (0 means all)")
    args = parser.parse_args()

    now = utc_now()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    archive_path = output_dir / "archive.json"
    latest_path = output_dir / "latest-24h.json"
    latest_all_path = output_dir / "latest-24h-all.json"
    latest_all_raw_path = output_dir / "latest-24h-all-raw.json"
    status_path = output_dir / "source-status.json"
    daily_brief_path = output_dir / "daily-brief.json"
    stories_merged_path = output_dir / "stories-merged.json"
    merge_log_path = output_dir / "merge-log.json"
    waytoagi_path = output_dir / "waytoagi-7d.json"
    title_cache_path = output_dir / "title-zh-cache.json"
    email_digest_path = output_dir / AGENTMAIL_DIGEST_FILE
    paid_source_state_path = output_dir / PAID_SOURCE_STATE_FILE

    archive = load_archive(archive_path)
    paid_source_state = load_paid_source_state(paid_source_state_path)

    session = create_session()
    raw_items, statuses = collect_all(session, now)
    rss_feed_statuses: list[dict[str, Any]] = []
    email_digest_payload, agentmail_status = maybe_fetch_agentmail_digest(
        session,
        generated_at=iso(now),
        after=iso(now - timedelta(hours=args.window_hours)),
        window_hours=args.window_hours,
    )
    if agentmail_status.get("enabled"):
        agentmail_items = agentmail_digest_items_to_raw_items(email_digest_payload or {})
        email_items = (email_digest_payload or {}).get("items")
        if not isinstance(email_items, list):
            email_items = []
        agentmail_status["public_url_count"] = sum(1 for item in email_items if isinstance(item, dict) and item.get("public_url"))
        agentmail_status["radar_item_count"] = len(agentmail_items)
        if agentmail_status.get("include_in_radar") and agentmail_items:
            raw_items.extend(agentmail_items)
        statuses.append(
            {
                "site_id": "agentmail",
                "site_name": "AgentMail",
                "ok": bool(agentmail_status.get("ok")) if agentmail_status.get("ok") is not None else True,
                "item_count": len(agentmail_items) if agentmail_status.get("include_in_radar") else 0,
                "duration_ms": 0,
                "error": agentmail_status.get("error"),
                "skipped": not bool(agentmail_status.get("include_in_radar")),
                "skip_reason": None if agentmail_status.get("include_in_radar") else "email_digest_not_included_in_radar",
            }
        )
    x_api_items, x_api_status = maybe_fetch_x_api_updates(session, now)
    if x_api_status.get("enabled"):
        raw_items.extend(x_api_items)
        statuses.append(
            {
                "site_id": "xapi",
                "site_name": "X API",
                "ok": bool(x_api_status.get("ok")) if x_api_status.get("ok") is not None else True,
                "item_count": int(x_api_status.get("item_count") or 0),
                "duration_ms": 0,
                "error": x_api_status.get("error"),
                "skipped": bool(x_api_status.get("skipped")),
                "skip_reason": x_api_status.get("skip_reason"),
            }
        )
    socialdata_items, socialdata_status = maybe_fetch_socialdata_updates(session, now, paid_source_state)
    update_paid_source_state(paid_source_state, "socialdata", socialdata_status, now)
    sync_paid_source_status_timestamps(socialdata_status, paid_source_state, "socialdata")
    if socialdata_status.get("enabled"):
        raw_items.extend(socialdata_items)
        statuses.append(
            {
                "site_id": "socialdata_x",
                "site_name": "SocialData X",
                "ok": bool(socialdata_status.get("ok")) if socialdata_status.get("ok") is not None else True,
                "item_count": int(socialdata_status.get("item_count") or 0),
                "duration_ms": 0,
                "error": socialdata_status.get("error"),
                "skipped": bool(socialdata_status.get("skipped")),
                "skip_reason": socialdata_status.get("skip_reason"),
            }
        )
    tikhub_items, tikhub_status = maybe_fetch_tikhub_updates(session, now, paid_source_state)
    update_paid_source_state(paid_source_state, "tikhub", tikhub_status, now)
    sync_paid_source_status_timestamps(tikhub_status, paid_source_state, "tikhub")
    if tikhub_status.get("enabled"):
        raw_items.extend(tikhub_items)
        tikhub_counts: dict[str, int] = {}
        for item in tikhub_items:
            tikhub_counts[item.site_id] = tikhub_counts.get(item.site_id, 0) + 1
        for site_id, site_name in (
            ("tikhub_douyin", "TikHub Douyin"),
            ("tikhub_xiaohongshu", "TikHub Xiaohongshu"),
        ):
            if site_id.split("_", 1)[1] not in set(tikhub_status.get("platforms") or []):
                continue
            statuses.append(
                {
                    "site_id": site_id,
                    "site_name": site_name,
                    "ok": bool(tikhub_status.get("ok")) if tikhub_status.get("ok") is not None else True,
                    "item_count": tikhub_counts.get(site_id, 0),
                    "duration_ms": 0,
                    "error": tikhub_status.get("error"),
                    "skipped": bool(tikhub_status.get("skipped")),
                    "skip_reason": tikhub_status.get("skip_reason"),
                }
            )

    waytoagi_started = time.perf_counter()
    try:
        waytoagi_payload = fetch_waytoagi_recent_7d(session, now, WAYTOAGI_DEFAULT)
        waytoagi_items = waytoagi_updates_to_raw_items(waytoagi_payload, now)
        raw_items.extend(waytoagi_items)
        statuses.append(
            {
                "site_id": "waytoagi",
                "site_name": "WaytoAGI",
                "ok": True,
                "item_count": len(waytoagi_items),
                "duration_ms": int((time.perf_counter() - waytoagi_started) * 1000),
                "error": None,
            }
        )
    except Exception as exc:
        waytoagi_payload = {
            "generated_at": iso(now),
            "timezone": "Asia/Shanghai",
            "root_url": WAYTOAGI_DEFAULT,
            "history_url": None,
            "window_days": 7,
            "count_7d": 0,
            "updates_7d": [],
            "warning": "WaytoAGI 近7日更新抓取失败",
            "has_error": True,
            "error": str(exc),
        }
        statuses.append(
            {
                "site_id": "waytoagi",
                "site_name": "WaytoAGI",
                "ok": False,
                "item_count": 0,
                "duration_ms": int((time.perf_counter() - waytoagi_started) * 1000),
                "error": str(exc),
            }
        )

    if args.rss_opml:
        opml_path = Path(args.rss_opml).expanduser()
        if opml_path.exists():
            rss_items, rss_summary_status, rss_feed_statuses = fetch_opml_rss(
                now,
                opml_path,
                max_feeds=max(0, int(args.rss_max_feeds)),
            )
            raw_items.extend(rss_items)
            statuses.append(rss_summary_status)
        else:
            statuses.append(
                {
                    "site_id": "opmlrss",
                    "site_name": "OPML RSS",
                    "ok": False,
                    "item_count": 0,
                    "duration_ms": 0,
                    "error": f"OPML not found: {opml_path}",
                    "feed_count": 0,
                    "ok_feed_count": 0,
                    "failed_feed_count": 0,
                }
            )

    seen_this_run: set[str] = set()

    for raw in raw_items:
        title = raw.title.strip()
        url = normalize_url(raw.url)
        if not title or not url:
            continue
        if not url.startswith("http"):
            continue

        item_id = make_item_id(raw.site_id, raw.source, title, url)
        seen_this_run.add(item_id)

        existing = archive.get(item_id)
        if existing is None:
            archive[item_id] = {
                "id": item_id,
                "site_id": raw.site_id,
                "site_name": raw.site_name,
                "source": raw.source,
                "title": title,
                "url": url,
                "published_at": iso(raw.published_at),
                "first_seen_at": iso(now),
                "last_seen_at": iso(now),
            }
            apply_public_raw_meta(archive[item_id], raw)
        else:
            existing["site_id"] = raw.site_id
            existing["site_name"] = raw.site_name
            existing["source"] = raw.source
            existing["title"] = title
            existing["url"] = url
            if raw.published_at:
                # OPML RSS may fix previously wrong publish times; allow overwrite.
                if raw.site_id == "opmlrss" or not existing.get("published_at"):
                    existing["published_at"] = iso(raw.published_at)
            existing["last_seen_at"] = iso(now)
            apply_public_raw_meta(existing, raw)

    # Prune old archive
    keep_after = now - timedelta(days=args.archive_days)
    pruned: dict[str, dict[str, Any]] = {}
    for item_id, record in archive.items():
        ts = (
            parse_iso(record.get("last_seen_at"))
            or parse_iso(record.get("published_at"))
            or parse_iso(record.get("first_seen_at"))
            or now
        )
        if ts >= keep_after:
            pruned[item_id] = record
    archive = pruned

    # 24h view
    window_start = now - timedelta(hours=args.window_hours)
    latest_items_all_raw: list[dict[str, Any]] = []
    for record in archive.values():
        ts = event_time(record)
        if not ts:
            continue
        if ts >= window_start:
            normalized = dict(record)
            normalized["title"] = maybe_fix_mojibake(str(normalized.get("title") or ""))
            normalized["source"] = maybe_fix_mojibake(normalize_source_for_display(
                str(normalized.get("site_id") or ""),
                str(normalized.get("source") or ""),
                str(normalized.get("url") or ""),
            ))
            if str(normalized.get("site_id") or "") == "aihubtoday" and is_hubtoday_placeholder_title(
                str(normalized.get("title") or "")
            ):
                continue
            normalized = add_ai_relevance_fields(normalized)
            normalized = add_source_tier_fields(normalized)
            latest_items_all_raw.append(normalized)

    latest_items_all_raw = normalize_aihubtoday_records(latest_items_all_raw)

    latest_items_all_raw.sort(key=lambda x: event_time(x) or datetime.min.replace(tzinfo=UTC), reverse=True)
    # Broad-AI filter: keep items whose pre-computed ai_score clears the floor
    latest_items_all = [record for record in latest_items_all_raw if record.get("ai_score", 0) >= AI_BROAD_RELEVANCE_FLOOR]
    latest_items = [record for record in latest_items_all_raw if record.get("ai_is_related", is_ai_related_record(record))]
    title_cache = load_title_zh_cache(title_cache_path)
    latest_items, latest_items_all, title_cache = add_bilingual_fields(
        latest_items,
        latest_items_all,
        session,
        title_cache,
        max_new_translations=max(0, args.translate_max_new),
        max_new_translations_all=max(0, args.translate_max_new_broad),
    )
    creator_items_ai = build_creator_hot_items(archive, now, ai_only=True)
    creator_items_all = build_creator_hot_items(archive, now, ai_only=False)
    creator_items_ai, creator_items_all, title_cache = add_bilingual_fields(
        creator_items_ai,
        creator_items_all,
        session,
        title_cache,
        max_new_translations=0,
    )
    latest_items_ai_dedup = suppress_near_duplicate_items(dedupe_items_by_title_url(latest_items, random_pick=False))
    latest_items_all_dedup = dedupe_items_by_title_url(latest_items_all, random_pick=True)
    latest_items_all_raw_dedup = dedupe_items_by_title_url(latest_items_all_raw, random_pick=True)
    latest_items_ai_dedup, title_cache = add_title_enhancements(latest_items_ai_dedup, session, title_cache)
    latest_items_ai_dedup, title_cache = add_recommend_reasons(latest_items_ai_dedup, session, title_cache)
    stories, merge_events = merge_story_items(latest_items_ai_dedup, now=now, window_hours=args.window_hours)
    generated_at = iso(now)
    daily_brief_payload = build_daily_brief_payload(stories, generated_at=generated_at, window_hours=args.window_hours)
    stories_merged_payload = build_stories_payload(stories, generated_at=generated_at, window_hours=args.window_hours)
    merge_log_payload = build_merge_log_payload(merge_events, generated_at=generated_at)

    # site stats
    site_stat: dict[str, dict[str, Any]] = {}
    raw_count_by_site: dict[str, int] = {}
    for record in latest_items_all_raw:
        sid = record["site_id"]
        raw_count_by_site[sid] = raw_count_by_site.get(sid, 0) + 1

    site_name_by_id: dict[str, str] = {}
    for record in latest_items_all_raw:
        site_name_by_id[record["site_id"]] = record["site_name"]
    for s in statuses:
        sid = s["site_id"]
        if sid not in site_name_by_id:
            site_name_by_id[sid] = s.get("site_name") or sid

    for record in latest_items_ai_dedup:
        sid = record["site_id"]
        if sid not in site_stat:
            site_stat[sid] = {
                "site_id": sid,
                "site_name": record["site_name"],
                "count": 0,
                "raw_count": raw_count_by_site.get(sid, 0),
            }
        site_stat[sid]["count"] += 1

    for sid, site_name in site_name_by_id.items():
        if sid in site_stat:
            continue
        site_stat[sid] = {
            "site_id": sid,
            "site_name": site_name,
            "count": 0,
            "raw_count": raw_count_by_site.get(sid, 0),
        }

    latest_payload = {
        "generated_at": generated_at,
        "window_hours": args.window_hours,
        "total_items": len(latest_items_ai_dedup),
        "total_items_ai_raw": len(latest_items),
        "total_items_raw": len(latest_items_all_raw),
        "total_items_all_mode": len(latest_items_all_dedup),
        "topic_filter": "ai_relevance_scoring_v0_4",
        "ai_relevance_threshold": 0.65,
        "archive_total": len(archive),
        "site_count": len(site_stat),
        "source_count": len({f"{i['site_id']}::{i['source']}" for i in latest_items_ai_dedup}),
        "site_stats": sorted(site_stat.values(), key=lambda x: x["count"], reverse=True),
        "creator_window_days": CREATOR_HOT_WINDOW_DAYS,
        "creator_ranking": "engagement_85_fresh_24h_bonus_15_v1",
        "creator_items_ai": creator_items_ai,
        "creator_items_all": creator_items_all,
        "items": latest_items_ai_dedup,
        "items_ai": latest_items_ai_dedup,
        "items_all_raw": latest_items_all,
        "items_all": latest_items_all_dedup,
    }

    archive_payload = {
        "generated_at": generated_at,
        "total_items": len(archive),
        "items": sorted(
            archive.values(),
            key=lambda x: parse_iso(x.get("last_seen_at")) or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        ),
    }

    empty_advanced_sources = [
        {
            "site_id": s["site_id"],
            "site_name": s.get("site_name") or s["site_id"],
            "reason": "connected_no_matching_results",
        }
        for s in statuses
        if s.get("ok")
        and int(s.get("item_count") or 0) == 0
        and str(s.get("site_id") or "") in {"xapi", "socialdata_x", "tikhub_douyin", "tikhub_xiaohongshu"}
        and not s.get("skipped")
    ]
    empty_advanced_site_ids = {item["site_id"] for item in empty_advanced_sources}

    status_payload = {
        "generated_at": generated_at,
        "sites": statuses,
        "successful_sites": sum(1 for s in statuses if s["ok"]),
        "failed_sites": [s["site_id"] for s in statuses if not s["ok"]],
        "zero_item_sites": [
            s["site_id"]
            for s in statuses
            if s.get("ok")
            and int(s.get("item_count") or 0) == 0
            and not s.get("skipped")
            and str(s.get("site_id") or "") not in empty_advanced_site_ids
        ],
        "empty_advanced_sources": empty_advanced_sources,
        "fetched_raw_items": len(raw_items),
        "items_before_topic_filter": len(latest_items_all_raw),
        "items_in_24h": len(latest_items_ai_dedup),
        "rss_opml": {
            "enabled": bool(args.rss_opml),
            "path": "configured" if args.rss_opml else None,
            "feed_total": len(rss_feed_statuses),
            "effective_feed_total": sum(1 for s in rss_feed_statuses if not s.get("skipped")),
            "ok_feeds": sum(1 for s in rss_feed_statuses if s["ok"] and not s.get("skipped")),
            "failed_feeds": [s.get("effective_feed_url") or s["feed_url"] for s in rss_feed_statuses if not s["ok"]],
            "zero_item_feeds": [
                s.get("effective_feed_url") or s["feed_url"]
                for s in rss_feed_statuses
                if s["ok"] and not s.get("skipped") and int(s.get("item_count") or 0) == 0
            ],
            "skipped_feeds": [
                {"feed_url": s["feed_url"], "reason": s.get("skip_reason")}
                for s in rss_feed_statuses
                if s.get("skipped")
            ],
            "replaced_feeds": [
                {"from": s["feed_url"], "to": s.get("effective_feed_url")}
                for s in rss_feed_statuses
                if s.get("replaced") and s.get("effective_feed_url")
            ],
            "feeds": rss_feed_statuses,
        },
        "agentmail": agentmail_status,
        "x_api": x_api_status,
        "socialdata": socialdata_status,
        "tikhub": tikhub_status,
    }

    latest_payload, latest_all_payload = build_latest_payloads(latest_payload)

    # Developer-only raw payload (all records, no AI filtering)
    latest_all_raw_payload = {
        "generated_at": latest_all_payload.get("generated_at"),
        "window_hours": latest_all_payload.get("window_hours"),
        "topic_filter": latest_all_payload.get("topic_filter"),
        "ai_relevance_threshold": latest_all_payload.get("ai_relevance_threshold"),
        "total_items_raw": len(latest_items_all_raw),
        "total_items_all_mode": len(latest_items_all_raw_dedup),
        "items_all": latest_items_all_raw_dedup,
        "items_all_raw": latest_items_all_raw,
    }

    latest_path.write_text(json.dumps(sanitize_public_payload(latest_payload), ensure_ascii=False, indent=2), encoding="utf-8")
    latest_all_path.write_text(json.dumps(sanitize_public_payload(latest_all_payload), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    latest_all_raw_path.write_text(json.dumps(sanitize_public_payload(latest_all_raw_payload), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    daily_brief_path.write_text(
        json.dumps(sanitize_public_payload(daily_brief_payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    stories_merged_path.write_text(
        json.dumps(sanitize_public_payload(stories_merged_payload), ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    merge_log_path.write_text(
        json.dumps(sanitize_public_payload(merge_log_payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    archive_path.write_text(
        json.dumps(sanitize_public_payload(archive_payload), ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    status_path.write_text(json.dumps(sanitize_public_payload(status_payload), ensure_ascii=False, indent=2), encoding="utf-8")
    paid_source_state_path.write_text(
        json.dumps(sanitize_public_payload(paid_source_state), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if email_digest_payload is not None:
        email_digest_path.write_text(
            json.dumps(sanitize_public_payload(email_digest_payload), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    waytoagi_path.write_text(json.dumps(sanitize_public_payload(waytoagi_payload), ensure_ascii=False, indent=2), encoding="utf-8")
    title_cache_path.write_text(json.dumps(sanitize_public_payload(title_cache), ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote: {latest_path} ({len(latest_items)} items)")
    print(f"Wrote: {latest_all_path} ({len(latest_items_all_dedup)} all-mode items)")
    print(f"Wrote: {latest_all_raw_path} ({len(latest_items_all_raw_dedup)} raw items, dev-only)")
    print(f"Wrote: {daily_brief_path} ({daily_brief_payload.get('total_items', 0)} brief items)")
    print(f"Wrote: {stories_merged_path} ({stories_merged_payload.get('total_stories', 0)} stories)")
    print(f"Wrote: {merge_log_path} ({len(merge_events)} merge events)")
    print(f"Wrote: {archive_path} ({len(archive)} items)")
    print(f"Wrote: {status_path}")
    print(f"Wrote: {paid_source_state_path}")
    if email_digest_payload is not None:
        print(f"Wrote: {email_digest_path} ({email_digest_payload.get('total_messages', 0)} email items)")
    print(f"Wrote: {waytoagi_path} ({waytoagi_payload.get('count_7d', 0)} items)")
    print(f"Wrote: {title_cache_path} ({len(title_cache)} entries)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
