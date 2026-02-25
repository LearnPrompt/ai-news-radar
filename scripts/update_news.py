#!/usr/bin/env python3
"""Aggregate updates from multiple AI news sites and produce 24h snapshot data."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import logging
import random
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from zoneinfo import ZoneInfo

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dtparser
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    import feedparser
except ModuleNotFoundError:
    feedparser = None

# Import storage layer
import sys
from pathlib import Path as P
# Add src to path for imports
src_path = P(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

try:
    from storage import (
        NewsItem,
        StatusRecord,
        SnapshotMetadata,
        create_storage,
        InitializationError,
        ConnectionError,
        StorageError,
    )
    STORAGE_AVAILABLE = True
except ImportError:
    STORAGE_AVAILABLE = False
    StorageError = Exception

UTC = timezone.utc
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


@dataclass
class RawItem:
    site_id: str
    site_name: str
    source: str
    title: str
    url: str
    published_at: datetime | None
    meta: dict[str, Any]


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
        dt = dtparser.parse(dt_str)
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
        dt = dtparser.parse(s, tzinfos={"UT": 0, "UTC": 0, "GMT": 0})
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except Exception:
        return None


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
        title = clean_update_title(block_text(bd))
        if not title:
            continue
        key = (day.isoformat(), title)
        if key in seen:
            continue
        seen.add(key)
        updates.append({"date": day.isoformat(), "title": title, "url": page_url})

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
        try:
            if feedparser is not None:
                parsed = feedparser.parse(feed_url)
                source_name = str(feed_name or getattr(parsed, "feed", {}).get("title") or "Iris Feed")
                for entry in parsed.entries:
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


def fetch_tophub(session: requests.Session, now: datetime) -> list[RawItem]:
    site_id = "tophub"
    site_name = "TopHub"

    r = session.get("https://tophub.today/", timeout=30)
    r.raise_for_status()
    html = r.content.decode("utf-8", errors="replace")
    if "�" in html:
        for enc in ("gb18030", "utf-8"):
            try:
                candidate = r.content.decode(enc, errors="replace")
                if candidate.count("�") < html.count("�"):
                    html = candidate
            except Exception:
                continue
    soup = BeautifulSoup(html, "html.parser")

    out: list[RawItem] = []
    for block in soup.select(".cc-cd"):
        source_name_tag = block.select_one(".cc-cd-lb span")
        board_tag = block.select_one(".cc-cd-sb-st")
        source_name = source_name_tag.get_text(" ", strip=True) if source_name_tag else "TopHub"
        board_name = board_tag.get_text(" ", strip=True) if board_tag else ""
        source_name = maybe_fix_mojibake(source_name)
        board_name = maybe_fix_mojibake(board_name)
        source = f"{source_name} · {board_name}" if board_name else source_name

        for a in block.select(".cc-cd-cb-l a"):
            href = a.get("href", "").strip()
            row = a.select_one(".cc-cd-cb-ll")
            title_tag = row.select_one(".t") if row else None
            metric_tag = row.select_one(".e") if row else None

            title = (
                title_tag.get_text(" ", strip=True)
                if title_tag
                else a.get_text(" ", strip=True)
            )
            title = maybe_fix_mojibake(title)
            if not title or not href:
                continue

            full_url = href if href.startswith("http") else urljoin("https://tophub.today", href)
            row_text = row.get_text(" ", strip=True) if row else title
            published = parse_relative_time_zh(row_text, now)

            out.append(
                RawItem(
                    site_id=site_id,
                    site_name=site_name,
                    source=source,
                    title=title,
                    url=full_url,
                    published_at=published,
                    meta={"metric": metric_tag.get_text(" ", strip=True) if metric_tag else ""},
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


def fetch_ai_hubtoday(session: requests.Session, now: datetime) -> list[RawItem]:
    site_id = "aihubtoday"
    site_name = "AI HubToday"

    r = session.get("https://ai.hubtoday.app/", timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    issue_date = None
    text = soup.get_text(" ", strip=True)
    m = re.search(r"AI资讯日报\s*(\d{4})/(\d{1,2})/(\d{1,2})", text)
    if not m:
        m = re.search(r"AI资讯日报\s*(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if m:
        issue_date = datetime(
            int(m.group(1)),
            int(m.group(2)),
            int(m.group(3)),
            tzinfo=UTC,
        )

    out: list[RawItem] = []
    seen_urls: set[str] = set()

    def add_item(title: str, href: str, source: str = "Daily Digest", fallback_title: str | None = None) -> None:
        title = (title or "").strip()
        href = (href or "").strip()
        fallback_title = (fallback_title or "").strip()
        if is_hubtoday_generic_anchor_title(title) and fallback_title:
            title = fallback_title
        if len(title) < 5 or not href.startswith("http"):
            return
        if title in {"自媒体账号"} or "source.hubtoday.app" in href or is_hubtoday_generic_anchor_title(title):
            return
        key_url = normalize_url(href)
        if key_url in seen_urls:
            return
        seen_urls.add(key_url)
        out.append(
            RawItem(
                site_id=site_id,
                site_name=site_name,
                source=source,
                title=title,
                url=href,
                published_at=issue_date,
                meta={},
            )
        )

    for p in soup.select("article .content li p"):
        link = p.select_one("a[href^='http']")
        if not link:
            continue
        strong = p.find("strong")
        strong_title = strong.get_text(" ", strip=True) if strong else ""
        add_item(strong_title, link.get("href") or "", source="Daily Digest")

    for a in soup.select("article .content a[target='_blank']"):
        fallback_title = ""
        p = a.find_parent("p")
        if p:
            strong = p.find("strong")
            if strong:
                fallback_title = strong.get_text(" ", strip=True)
        add_item(a.get_text(" ", strip=True), a.get("href") or "", fallback_title=fallback_title)

    # include article-level links without target='_blank' (e.g. GitHub 链接)
    for a in soup.select("article a[href^='http']"):
        fallback_title = ""
        p = a.find_parent("p")
        if p:
            strong = p.find("strong")
            if strong:
                fallback_title = strong.get_text(" ", strip=True)
        add_item(a.get_text(" ", strip=True), a.get("href") or "", fallback_title=fallback_title)

    if not out:
        # fallback: parse all external links in page when article container changes
        for a in soup.select("a[href^='http']"):
            fallback_title = ""
            p = a.find_parent("p")
            if p:
                strong = p.find("strong")
                if strong:
                    fallback_title = strong.get_text(" ", strip=True)
            add_item(
                a.get_text(" ", strip=True),
                a.get("href") or "",
                source="Page Fallback",
                fallback_title=fallback_title,
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


def fetch_aihot(session: requests.Session, now: datetime) -> list[RawItem]:
    site_id = "aihot"
    site_name = "AI今日热榜"

    r = session.get("https://aihot.today/", timeout=30)
    r.raise_for_status()
    initial_data = None
    source_list = None

    decoded = extract_next_f_merged(r.text)
    if decoded:
        try:
            initial_data = extract_balanced_json(decoded, "initialDataMap")
            source_list = extract_balanced_json(decoded, "dataSources")
        except Exception:
            initial_data = None
            source_list = None

    if initial_data is None or source_list is None:
        next_data = extract_next_data_payload(r.text) or {}
        page_props = (
            next_data.get("props", {})
            .get("pageProps", {})
        )
        if isinstance(page_props.get("initialDataMap"), dict):
            initial_data = page_props.get("initialDataMap")
        if isinstance(page_props.get("dataSources"), list):
            source_list = page_props.get("dataSources")

    if initial_data is None or source_list is None:
        return []

    source_map = {str(s.get("id")): s.get("title", str(s.get("id"))) for s in source_list if isinstance(s, dict)}

    out: list[RawItem] = []
    for source_id, items in initial_data.items():
        source_name = maybe_fix_mojibake(source_map.get(str(source_id), str(source_id)))
        if not isinstance(items, list):
            continue
        for item in items:
            title = maybe_fix_mojibake(str(item.get("title_trans") or item.get("title") or "").strip())
            link = str(item.get("link") or "").strip()
            if not title or not link:
                continue
            published = parse_date_any(item.get("publish_time"), now) or now
            out.append(
                RawItem(
                    site_id=site_id,
                    site_name=site_name,
                    source=source_name,
                    title=title,
                    url=link,
                    published_at=published,
                    meta={"raw_source_id": source_id},
                )
            )

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
        ("techurls", "TechURLs", fetch_techurls),
        ("buzzing", "Buzzing", fetch_buzzing),
        ("iris", "Info Flow", fetch_iris),
        ("bestblogs", "BestBlogs", fetch_bestblogs),
        ("tophub", "TopHub", fetch_tophub),
        ("zeli", "Zeli", fetch_zeli),
        ("aihubtoday", "AI HubToday", fetch_ai_hubtoday),
        ("aibase", "AIbase", fetch_aibase),
        ("aihot", "AI今日热榜", fetch_aihot),
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

            if feedparser is not None:
                parsed = feedparser.parse(resp.content)
                source_name = first_non_empty(
                    feed_title,
                    getattr(parsed, "feed", {}).get("title"),
                    host_of_url(feed_url),
                )
                entries = parsed.entries
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
                for entry in entries:
                    published = parse_date_any(entry.get("published"), now)
                    if not published:
                        continue
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


# Storage layer helper functions
def dict_to_news_item(record: dict[str, Any]) -> NewsItem:
    """Convert a dictionary record to a NewsItem."""
    return NewsItem(
        id=record["id"],
        site_id=record["site_id"],
        site_name=record["site_name"],
        source=record["source"],
        title=record["title"],
        url=record["url"],
        published_at=record.get("published_at"),
        first_seen_at=record["first_seen_at"],
        last_seen_at=record["last_seen_at"],
        meta=record.get("meta", {}),
        title_zh=record.get("title_zh"),
        summary=record.get("summary"),
        categories=record.get("categories"),
    )


def news_item_to_dict(item: NewsItem) -> dict[str, Any]:
    """Convert a NewsItem to a dictionary."""
    return item.to_dict()


def dict_to_status_record(record: dict[str, Any], now: datetime) -> StatusRecord:
    """Convert a dictionary status record to a StatusRecord."""
    return StatusRecord(
        site_id=record["site_id"],
        site_name=record["site_name"],
        ok=record.get("ok", True),
        item_count=record.get("item_count", 0),
        last_check_at=iso(now),
        error_message=record.get("error"),
        response_time_ms=record.get("duration_ms"),
        metadata={k: v for k, v in record.items() if k not in {"site_id", "site_name", "ok", "item_count", "error", "duration_ms"}},
    )


def initialize_storage() -> Any:
    """Initialize and return the storage backend.

    Returns:
        Storage backend instance or None if storage is not available
    """
    if not STORAGE_AVAILABLE:
        return None

    try:
        storage = create_storage(enable_fallback=True)
        logging.info(f"Storage initialized: {type(storage).__name__}")
        return storage
    except (ConnectionError, InitializationError) as e:
        logging.warning(f"Storage initialization failed, using file fallback: {e}")
        return None
    except Exception as e:
        logging.warning(f"Unexpected error initializing storage: {e}")
        return None


def event_time(record: dict[str, Any]) -> datetime | None:
    # RSS sources must rely on the source's publish time only.
    # first_seen_at is fetch time and would falsely mark historical items as "24h".
    if str(record.get("site_id") or "") == "opmlrss":
        return parse_iso(record.get("published_at"))
    return parse_iso(record.get("published_at")) or parse_iso(record.get("first_seen_at"))


AI_KEYWORDS = [
    "aigc",
    "llm",
    "gpt",
    "claude",
    "gemini",
    "deepseek",
    "openai",
    "anthropic",
    "hugging face",
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

TOPHUB_ALLOW_KEYWORDS = [
    "readhub · ai",
    "hacker news",
    "github",
    "product hunt",
    "v2ex",
    "少数派",
    "infoq",
    "36氪",
    "机器之心",
    "量子位",
    "科技",
    "人工智能",
    "机器人",
    "具身",
    "开源",
]

TOPHUB_BLOCK_KEYWORDS = [
    "热销总榜",
    "淘宝",
    "天猫",
    "京东",
    "拼多多",
    "抖音",
    "快手",
    "微博",
    "小红书",
]


def contains_any_keyword(haystack: str, keywords: list[str]) -> bool:
    h = haystack.lower()
    return any(k in h for k in keywords)


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
    site_id = str(record.get("site_id") or "")
    title = str(record.get("title") or "")
    source = str(record.get("source") or "")
    site_name = str(record.get("site_name") or "")
    url = str(record.get("url") or "")
    text = f"{title} {source} {site_name} {url}".lower()

    # zeli 按需求只保留 Hacker News 24h 最热。
    if site_id == "zeli":
        return "24h" in source.lower() or "24h最热" in source

    if site_id == "tophub":
        source_l = source.lower()
        if has_mojibake_noise(source) or has_mojibake_noise(title):
            return False
        if contains_any_keyword(source_l, TOPHUB_BLOCK_KEYWORDS):
            return False
        if not contains_any_keyword(source_l, TOPHUB_ALLOW_KEYWORDS):
            return False

    # AI/热点聚合站默认保留，避免误杀。
    if site_id in {"aibase", "aihot", "aihubtoday"}:
        return True

    has_ai = contains_any_keyword(text, AI_KEYWORDS) or EN_SIGNAL_RE.search(text) is not None
    has_tech = contains_any_keyword(text, TECH_KEYWORDS)

    if not (has_ai or has_tech):
        return False

    if contains_any_keyword(text, COMMERCE_NOISE_KEYWORDS) and not has_ai:
        return False

    # 如果是明显噪声且没有 AI 信号，则丢弃。
    if contains_any_keyword(text, NOISE_KEYWORDS) and not has_ai:
        return False

    return True


def load_title_zh_cache(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items() if str(k).strip() and str(v).strip()}
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


def add_bilingual_fields(
    items_ai: list[dict[str, Any]],
    items_all: list[dict[str, Any]],
    session: requests.Session,
    cache: dict[str, str],
    max_new_translations: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, str]]:
    zh_by_url: dict[str, str] = {}
    for it in items_all:
        title = str(it.get("title") or "").strip()
        url = normalize_url(str(it.get("url") or ""))
        if title and url and has_cjk(title):
            zh_by_url[url] = title

    translated_now = 0

    def enrich(item: dict[str, Any], allow_translate: bool) -> dict[str, Any]:
        nonlocal translated_now
        out = dict(item)
        title = str(out.get("title") or "").strip()
        url = normalize_url(str(out.get("url") or ""))

        out["title_original"] = title
        out["title_en"] = None
        out["title_zh"] = None
        out["title_bilingual"] = title

        if has_cjk(title):
            out["title_zh"] = title
            return out

        if not is_mostly_english(title):
            return out

        out["title_en"] = title

        zh_title = zh_by_url.get(url)
        if not zh_title:
            zh_title = cache.get(title)
        if not zh_title and allow_translate and translated_now < max_new_translations:
            tr = translate_to_zh_cn(session, title)
            if tr and has_cjk(tr):
                zh_title = tr
                cache[title] = tr
                translated_now += 1

        if zh_title:
            out["title_zh"] = zh_title
            out["title_bilingual"] = f"{zh_title} / {title}"
        return out

    ai_out = [enrich(it, allow_translate=True) for it in items_ai]
    all_out = [enrich(it, allow_translate=False) for it in items_all]
    return ai_out, all_out, cache


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
            chosen = max(
                values,
                key=lambda x: (
                    event_time(x) or datetime.min.replace(tzinfo=UTC),
                    str(x.get("id") or ""),
                ),
            )
            out.append(chosen)

    out.sort(key=lambda x: event_time(x) or datetime.min.replace(tzinfo=UTC), reverse=True)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate AI news updates from multiple sources")
    parser.add_argument("--output-dir", default="data", help="Directory for output JSON files")
    parser.add_argument("--window-hours", type=int, default=24, help="24h window size")
    parser.add_argument("--archive-days", type=int, default=45, help="Keep archive for N days")
    parser.add_argument("--translate-max-new", type=int, default=80, help="Max new EN->ZH title translations per run")
    parser.add_argument("--rss-opml", default="", help="Optional OPML file path to include RSS sources")
    parser.add_argument("--rss-max-feeds", type=int, default=0, help="Optional max OPML RSS feeds to fetch (0 means all)")
    parser.add_argument("--no-storage", action="store_true", help="Disable storage layer, use file I/O only")
    args = parser.parse_args()

    now = utc_now()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    archive_path = output_dir / "archive.json"
    latest_path = output_dir / "latest-24h.json"
    status_path = output_dir / "source-status.json"
    waytoagi_path = output_dir / "waytoagi-7d.json"
    title_cache_path = output_dir / "title-zh-cache.json"

    # Initialize storage layer
    storage = None
    if not args.no_storage:
        try:
            storage = initialize_storage()
            if storage:
                logging.info(f"Using storage backend: {type(storage).__name__}")
            else:
                logging.warning("Storage not available, using file I/O")
        except Exception as e:
            logging.warning(f"Storage initialization error: {e}, using file I/O")

    # Load archive
    if storage:
        archive_dicts = {k: v.to_dict() for k, v in storage.load_archive().items()}
    else:
        archive = load_archive(archive_path)
        archive_dicts = archive

    session = create_session()
    raw_items, statuses = collect_all(session, now)
    rss_feed_statuses: list[dict[str, Any]] = []

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

        existing = archive_dicts.get(item_id)
        if existing is None:
            archive_dicts[item_id] = {
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

    # Prune old archive
    keep_after = now - timedelta(days=args.archive_days)
    pruned: dict[str, dict[str, Any]] = {}
    for item_id, record in archive_dicts.items():
        ts = (
            parse_iso(record.get("last_seen_at"))
            or parse_iso(record.get("published_at"))
            or parse_iso(record.get("first_seen_at"))
            or now
        )
        if ts >= keep_after:
            pruned[item_id] = record
    archive_dicts = pruned

    # Load title cache
    if storage:
        title_cache = storage.load_title_cache()
    else:
        title_cache = load_title_zh_cache(title_cache_path)

    # 24h view
    window_start = now - timedelta(hours=args.window_hours)
    latest_items_all: list[dict[str, Any]] = []
    for record in archive_dicts.values():
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
            latest_items_all.append(normalized)

    latest_items_all = normalize_aihubtoday_records(latest_items_all)

    latest_items_all.sort(key=lambda x: event_time(x) or datetime.min.replace(tzinfo=UTC), reverse=True)
    latest_items = [record for record in latest_items_all if is_ai_related_record(record)]
    latest_items, latest_items_all, title_cache = add_bilingual_fields(
        latest_items,
        latest_items_all,
        session,
        title_cache,
        max_new_translations=max(0, args.translate_max_new),
    )
    latest_items_ai_dedup = dedupe_items_by_title_url(latest_items, random_pick=False)
    latest_items_all_dedup = dedupe_items_by_title_url(latest_items_all, random_pick=True)

    # site stats
    site_stat: dict[str, dict[str, Any]] = {}
    raw_count_by_site: dict[str, int] = {}
    for record in latest_items_all:
        sid = record["site_id"]
        raw_count_by_site[sid] = raw_count_by_site.get(sid, 0) + 1

    site_name_by_id: dict[str, str] = {}
    for record in latest_items_all:
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
        "generated_at": iso(now),
        "window_hours": args.window_hours,
        "total_items": len(latest_items_ai_dedup),
        "total_items_ai_raw": len(latest_items),
        "total_items_raw": len(latest_items_all),
        "total_items_all_mode": len(latest_items_all_dedup),
        "topic_filter": "ai_tech_robotics",
        "archive_total": len(archive),
        "site_count": len(site_stat),
        "source_count": len({f"{i['site_id']}::{i['source']}" for i in latest_items_ai_dedup}),
        "site_stats": sorted(site_stat.values(), key=lambda x: x["count"], reverse=True),
        "items": latest_items_ai_dedup,
        "items_ai": latest_items_ai_dedup,
        "items_all_raw": latest_items_all,
        "items_all": latest_items_all_dedup,
    }

    archive_payload = {
        "generated_at": iso(now),
        "total_items": len(archive),
        "items": sorted(
            archive.values(),
            key=lambda x: parse_iso(x.get("last_seen_at")) or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        ),
    }

    status_payload = {
        "generated_at": iso(now),
        "sites": statuses,
        "successful_sites": sum(1 for s in statuses if s["ok"]),
        "failed_sites": [s["site_id"] for s in statuses if not s["ok"]],
        "zero_item_sites": [s["site_id"] for s in statuses if s.get("ok") and int(s.get("item_count") or 0) == 0],
        "fetched_raw_items": len(raw_items),
        "items_before_topic_filter": len(latest_items_all),
        "items_in_24h": len(latest_items_ai_dedup),
        "rss_opml": {
            "enabled": bool(args.rss_opml),
            "path": str(Path(args.rss_opml).expanduser()) if args.rss_opml else None,
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
    }

    try:
        waytoagi_payload = fetch_waytoagi_recent_7d(session, now, WAYTOAGI_DEFAULT)
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

    # Save using storage layer or fall back to file I/O
    if storage:
        try:
            # Save archive items
            archive_items = [dict_to_news_item(r) for r in archive_dicts.values()]
            storage.save_archive_items(archive_items)

            # Save latest snapshot
            metadata = SnapshotMetadata(
                generated_at=iso(now),
                window_hours=args.window_hours,
                total_items=len(latest_items_ai_dedup),
                total_items_raw=len(latest_items),
                site_count=len(site_stat),
                source_count=len({f"{i['site_id']}::{i['source']}" for i in latest_items_ai_dedup}),
                topic_filter="ai_tech_robotics",
                archive_total=len(archive_dicts),
            )
            storage.save_snapshot(
                "latest",
                metadata,
                [dict_to_news_item(r) for r in latest_items_ai_dedup],
                items_ai=[dict_to_news_item(r) for r in latest_items_ai_dedup],
                items_all_raw=[dict_to_news_item(r) for r in latest_items_all],
                items_all=[dict_to_news_item(r) for r in latest_items_all_dedup],
                site_stats=list(site_stat.values()),
            )

            # Save status records
            status_records = [dict_to_status_record(s, now) for s in statuses]
            storage.save_status_records(status_records)

            # Save WaytoAGI data
            storage.save_waytoagi_data(waytoagi_payload)

            # Save title cache
            storage.save_title_cache(title_cache)

            print(f"Saved to storage: {len(latest_items_ai_dedup)} items")
            print(f"Storage backend: {type(storage).__name__}")
        except Exception as e:
            logging.error(f"Storage save failed, falling back to file I/O: {e}")
            storage = None

    # Fall back to file I/O if storage is not available or failed
    if not storage:
        latest_path.write_text(json.dumps(latest_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        archive_path.write_text(json.dumps(archive_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        status_path.write_text(json.dumps(status_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        waytoagi_path.write_text(json.dumps(waytoagi_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        title_cache_path.write_text(json.dumps(title_cache, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"Wrote: {latest_path} ({len(latest_items)} items)")
        print(f"Wrote: {archive_path} ({len(archive_dicts)} items)")
        print(f"Wrote: {status_path}")
        print(f"Wrote: {waytoagi_path} ({waytoagi_payload.get('count_7d', 0)} items)")
        print(f"Wrote: {title_cache_path} ({len(title_cache)} entries)")

    # Close storage connection
    if storage:
        try:
            storage.close()
        except Exception as e:
            logging.error(f"Error closing storage: {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
