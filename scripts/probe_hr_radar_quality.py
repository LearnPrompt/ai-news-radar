#!/usr/bin/env python3
"""Probe candidate HR sources without changing production radar data."""

from __future__ import annotations

import argparse
import json
import re
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin, urlparse, urlunparse

import feedparser
import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

UTC = timezone.utc
CHINA_TZ = timezone(timedelta(hours=8))
USER_AGENT = "Mozilla/5.0 AI-News-Radar HR source-quality probe"

POLICY_TERMS = (
    "劳动",
    "用工",
    "就业",
    "招聘",
    "职工",
    "员工",
    "工资",
    "薪酬",
    "社保",
    "社会保险",
    "养老保险",
    "工伤",
    "失业保险",
    "公积金",
    "职称",
    "职业技能",
    "人力资源",
    "人资系统",
    "人才",
    "绩效",
    "劳动关系",
    "劳动争议",
    "竞业限制",
    "个人信息",
    "数据合规",
    "human resources",
    "workforce",
    "employee",
    "employees",
    "employer",
    "employers",
    "employment",
    "hiring",
    "recruitment",
    "recruiting",
    "talent acquisition",
    "talent management",
    "people management",
    "payroll",
    "benefits",
    "workplace",
    "labor law",
    "labour law",
    "upskilling",
    "reskilling",
)

AI_TERMS = (
    "人工智能",
    "生成式ai",
    "生成式 ai",
    "大模型",
    "智能体",
    "机器学习",
    "深度学习",
    "算法决策",
    "自动化决策",
    "招聘自动化",
    "智能招聘",
    "ai招聘",
    "ai 招聘",
    "ai面试",
    "ai 面试",
    "ai agent",
    "hr agent",
    "agentic ai",
    "artificial intelligence",
    "generative ai",
    "machine learning",
    "automated decision",
    "resume screening",
    "llm",
    "ai",
)

OFFICIAL_NEWS_SIGNAL_TERMS = (
    "通知",
    "通告",
    "公告",
    "办法",
    "规定",
    "条例",
    "意见",
    "方案",
    "规划",
    "标准",
    "政策",
    "解读",
    "法规",
    "监管",
    "合规",
    "权益保障",
    "劳动纠纷",
    "工资支付",
)

AI_RECRUITING_TERMS = (
    "ai招聘",
    "ai 招聘",
    "智能招聘",
    "ai面试",
    "ai 面试",
    "简历筛选",
    "招聘自动化",
    "resume screening",
    "ai recruiting",
    "ai hiring",
    "talent acquisition",
)

LEARNING_TERMS = (
    "学习发展",
    "技能转型",
    "职业技能",
    "企业培训",
    "人才培养",
    "upskilling",
    "reskilling",
    "learning and development",
)

ORG_TALENT_TERMS = (
    "组织",
    "人才",
    "绩效",
    "员工体验",
    "人才盘点",
    "组织设计",
    "people analytics",
    "talent management",
    "employee experience",
    "workforce",
)

HR_PRODUCT_TERMS = (
    "hr saas",
    "hris",
    "人力资源系统",
    "人事系统",
    "人资系统",
    "招聘系统",
    "人才系统",
    "hr系统",
    "hr 系统",
    "moka",
    "北森",
    "workday",
)

MARKETING_TERMS = (
    "免费试用",
    "top榜",
    "top 榜",
    "选型指南",
    "选型全景",
    "深度对比",
    "横评",
    "厂商",
    "最强",
    "核心引擎",
    "完整拆解",
    "不能忽视",
    "值得关注",
)


@dataclass
class CandidateItem:
    source_id: str
    source_name: str
    source_url: str
    source_type: str
    authority: str
    region: str
    title: str
    url: str
    published_at: datetime
    timestamp_quality: str = "explicit"


def normalize_space(value: Any) -> str:
    return " ".join(str(value or "").split())


def normalize_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"}:
        return ""
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, "", parsed.query, ""))


def has_cjk(value: str) -> bool:
    return re.search(r"[\u3400-\u9fff]", value) is not None


def matches_term(text: str, term: str) -> bool:
    haystack = text.casefold()
    needle = term.casefold()
    if has_cjk(needle):
        return needle in haystack
    return re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", haystack) is not None


def matched_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    return sorted({term for term in terms if matches_term(text, term)})


def parse_datetime(value: Any, default_tz: timezone = CHINA_TZ) -> Optional[datetime]:
    text = normalize_space(value)
    if not text:
        return None
    text = re.sub(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日", r"\1-\2-\3", text)
    if re.fullmatch(r"\d{8}", text):
        text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    try:
        parsed = date_parser.parse(text, fuzzy=False)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=default_tz)
    return parsed.astimezone(UTC)


def extract_date_from_url(url: str, patterns: list[str]) -> Optional[datetime]:
    for pattern in patterns:
        match = re.search(pattern, url)
        if not match:
            continue
        value = match.groupdict().get("date") or match.group(1)
        parsed = parse_datetime(value)
        if parsed:
            return parsed
    return None


def parse_feed_content(source: dict[str, Any], content: bytes) -> tuple[list[CandidateItem], int, int]:
    parsed = feedparser.parse(content)
    items: list[CandidateItem] = []
    missing_timestamp = 0
    seen = 0
    for entry in parsed.entries:
        title = normalize_space(entry.get("title"))
        url = normalize_url(str(entry.get("link") or ""))
        if not title or not url:
            continue
        seen += 1
        published = (
            parse_datetime(entry.get("published"), UTC)
            or parse_datetime(entry.get("updated"), UTC)
            or parse_datetime(entry.get("pubDate"), UTC)
        )
        if not published:
            missing_timestamp += 1
            continue
        items.append(build_item(source, title, url, published, "explicit"))
    return items, seen, missing_timestamp


def parse_html_content(source: dict[str, Any], html: str) -> tuple[list[CandidateItem], int, int]:
    soup = BeautifulSoup(html, "html.parser")
    item_selector = str(source.get("item_selector") or "a[href]")
    title_selector = str(source.get("title_selector") or "")
    date_selector = str(source.get("date_selector") or "")
    allowed_hosts = {str(host).lower() for host in source.get("allowed_hosts", [])}
    date_regexes = [str(pattern) for pattern in source.get("date_regexes", [])]
    items: list[CandidateItem] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    missing_timestamp = 0
    seen = 0

    for node in soup.select(item_selector):
        title_node = node.select_one(title_selector) if title_selector else node
        if title_node is None:
            continue
        link_node = title_node if getattr(title_node, "name", None) == "a" else title_node.select_one("a[href]")
        if link_node is None:
            continue
        title = normalize_space(link_node.get("title") or link_node.get_text(" ", strip=True))
        url = normalize_url(urljoin(str(source["url"]), str(link_node.get("href") or "")))
        title_key = title.casefold()
        if not title or not url or url in seen_urls or title_key in seen_titles:
            continue
        if allowed_hosts and (urlparse(url).hostname or "").lower() not in allowed_hosts:
            continue
        seen_urls.add(url)
        seen_titles.add(title_key)
        seen += 1

        date_text = ""
        if date_selector:
            date_node = node.select_one(date_selector)
            if date_node is not None:
                date_text = normalize_space(date_node.get_text(" ", strip=True))
        published = parse_datetime(date_text)
        timestamp_quality = "explicit"
        if not published:
            published = extract_date_from_url(url, date_regexes)
            timestamp_quality = "inferred_from_url"
        if not published:
            missing_timestamp += 1
            continue
        items.append(build_item(source, title, url, published, timestamp_quality))

    return items, seen, missing_timestamp


def build_item(
    source: dict[str, Any],
    title: str,
    url: str,
    published_at: datetime,
    timestamp_quality: str,
) -> CandidateItem:
    return CandidateItem(
        source_id=str(source["id"]),
        source_name=str(source["name"]),
        source_url=str(source["url"]),
        source_type=str(source["type"]),
        authority=str(source.get("authority") or "unknown"),
        region=str(source.get("region") or "未知"),
        title=title,
        url=url,
        published_at=published_at,
        timestamp_quality=timestamp_quality,
    )


def classify_item(title: str, authority: str) -> str:
    if authority.startswith("official_"):
        return "政策与劳动合规"
    if matched_terms(title, AI_RECRUITING_TERMS):
        return "AI 招聘与招聘工具"
    if matched_terms(title, LEARNING_TERMS):
        return "学习发展与技能转型"
    if matched_terms(title, HR_PRODUCT_TERMS):
        return "HR 产品与数字化"
    if matched_terms(title, ORG_TALENT_TERMS):
        return "组织与人才管理"
    return "案例、报告与趋势"


def evaluate_item(item: CandidateItem) -> dict[str, Any]:
    hr_signals = matched_terms(item.title, POLICY_TERMS)
    ai_signals = matched_terms(item.title, AI_TERMS)
    marketing_signals = matched_terms(item.title, MARKETING_TERMS)
    official_news_signals = matched_terms(item.title, OFFICIAL_NEWS_SIGNAL_TERMS)
    is_official_listing = item.authority == "official_policy"
    is_official_news = item.authority == "official_hr_news"
    if is_official_listing:
        kept = True
    elif is_official_news:
        kept = bool(hr_signals and (official_news_signals or ai_signals))
    else:
        kept = bool(hr_signals and ai_signals)

    if kept and is_official_listing:
        reason = "official_policy_listing"
    elif kept and is_official_news:
        reason = "official_policy_or_ai"
    elif kept:
        reason = "ai_hr_crossover"
    elif not hr_signals:
        reason = "missing_hr_signal"
    elif is_official_news and not (official_news_signals or ai_signals):
        reason = "missing_policy_or_ai_signal"
    else:
        reason = "missing_ai_signal"
    if item.authority == "vendor":
        marketing_signals = sorted({*marketing_signals, "vendor_source"})
    payload = asdict(item)
    payload["published_at"] = item.published_at.isoformat().replace("+00:00", "Z")
    payload.update(
        {
            "kept": kept,
            "reason": reason,
            "category": classify_item(item.title, item.authority) if kept else None,
            "hr_signals": hr_signals,
            "ai_signals": ai_signals,
            "official_news_signals": official_news_signals,
            "marketing_signals": marketing_signals,
            "marketing_risk": bool(marketing_signals),
        }
    )
    return payload


def create_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(["GET"]),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"})
    return session


def source_decision(status: dict[str, Any]) -> str:
    if not status["ok"]:
        return "needs-adapter" if status["authority"].startswith("official_") else "skip"
    if status["raw_count"] == 0:
        return "needs-adapter" if status["authority"].startswith("official_") else "watchlist"
    if status["recent_count"] == 0 or status["kept_count"] == 0:
        return "watchlist"
    if status["authority"] == "vendor" and status["marketing_risk_rate"] >= 0.5:
        return "watchlist"
    return "pilot"


def probe_source(
    session: requests.Session,
    source: dict[str, Any],
    now: datetime,
    lookback_days: int,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    started = time.perf_counter()
    status: dict[str, Any] = {
        "source_id": source["id"],
        "source_name": source["name"],
        "source_url": source["url"],
        "source_type": source["type"],
        "authority": source.get("authority", "unknown"),
        "region": source.get("region", "未知"),
        "ok": False,
        "error": None,
        "raw_count": 0,
        "missing_timestamp_count": 0,
        "recent_count": 0,
        "kept_count": 0,
        "crossover_count": 0,
        "marketing_risk_count": 0,
        "marketing_risk_rate": 0.0,
        "hr_relevance_rate": 0.0,
        "ai_hr_crossover_rate": 0.0,
        "timestamp_quality": {"explicit": 0, "inferred_from_url": 0, "missing": 0},
        "canonical_url_quality": "unverified",
    }
    evaluated: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    try:
        response = session.get(str(source["url"]), timeout=20)
        response.raise_for_status()
        if source["type"] == "rss":
            parsed_items, raw_count, missing_timestamp = parse_feed_content(source, response.content)
        elif source["type"] == "html":
            parsed_items, raw_count, missing_timestamp = parse_html_content(source, response.text)
        else:
            raise ValueError(f"Unsupported source type: {source['type']}")

        status["ok"] = True
        status["raw_count"] = raw_count
        status["missing_timestamp_count"] = missing_timestamp
        timestamp_counts = Counter(item.timestamp_quality for item in parsed_items)
        status["timestamp_quality"] = {
            "explicit": timestamp_counts.get("explicit", 0),
            "inferred_from_url": timestamp_counts.get("inferred_from_url", 0),
            "missing": missing_timestamp,
        }
        cutoff = now - timedelta(days=lookback_days)
        recent = [item for item in parsed_items if cutoff <= item.published_at <= now + timedelta(days=1)]
        status["recent_count"] = len(recent)
        for item in recent:
            result = evaluate_item(item)
            if result["kept"]:
                evaluated.append(result)
            else:
                rejected.append(result)
        status["kept_count"] = len(evaluated)
        status["crossover_count"] = sum(bool(item["ai_signals"] and item["hr_signals"]) for item in evaluated)
        status["marketing_risk_count"] = sum(bool(item["marketing_risk"]) for item in evaluated)
        if evaluated:
            status["marketing_risk_rate"] = round(status["marketing_risk_count"] / len(evaluated), 3)
        if recent:
            status["hr_relevance_rate"] = round(status["kept_count"] / len(recent), 3)
            status["ai_hr_crossover_rate"] = round(status["crossover_count"] / len(recent), 3)
        status["canonical_url_quality"] = "stable_article_urls" if parsed_items else "unverified"
    except Exception as exc:  # source failures are report data, not process failures
        status["error"] = f"{type(exc).__name__}: {exc}"
    status["duration_ms"] = int((time.perf_counter() - started) * 1000)
    status["decision"] = source_decision(status)
    return status, evaluated, rejected[:5]


def build_markdown_report(payload: dict[str, Any]) -> str:
    lines = [
        "# HR Radar Source Quality Report",
        "",
        f"Generated: `{payload['generated_at']}`",
        f"Lookback: `{payload['lookback_days']} days`",
        "",
        "## Source summary",
        "",
        "| Source | Region | Type | Fetch | Raw | Recent | Kept | Marketing | Decision |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for status in payload["sources"]:
        fetch = "ok" if status["ok"] else "failed"
        lines.append(
            f"| {status['source_name']} | {status['region']} | {status['source_type']} | {fetch} | "
            f"{status['raw_count']} | {status['recent_count']} | {status['kept_count']} | "
            f"{status['marketing_risk_count']} | {status['decision']} |"
        )
    lines.extend(["", "## Category balance", ""])
    if payload["category_counts"]:
        for category, count in payload["category_counts"].items():
            lines.append(f"- {category}: {count}")
    else:
        lines.append("- No retained items.")

    lines.extend(["", "## Source details", ""])
    items_by_source: dict[str, list[dict[str, Any]]] = {}
    for item in payload["items"]:
        items_by_source.setdefault(item["source_id"], []).append(item)
    rejected_by_source = payload["rejected_samples"]
    for status in payload["sources"]:
        lines.append(f"### {status['source_name']}")
        lines.append("")
        lines.append(f"- Decision: `{status['decision']}`")
        lines.append(f"- Status: `{'ok' if status['ok'] else status['error']}`")
        lines.append(f"- Missing timestamps: `{status['missing_timestamp_count']}`")
        timestamps = status["timestamp_quality"]
        lines.append(
            f"- Timestamp quality: explicit `{timestamps['explicit']}`, URL-inferred "
            f"`{timestamps['inferred_from_url']}`, missing `{timestamps['missing']}`"
        )
        lines.append(f"- Canonical URL quality: `{status['canonical_url_quality']}`")
        lines.append(
            f"- Relevance rate: `{status['hr_relevance_rate']:.1%}`; "
            f"AI x HR crossover rate: `{status['ai_hr_crossover_rate']:.1%}`"
        )
        kept = items_by_source.get(status["source_id"], [])[:8]
        if kept:
            lines.append("- Retained samples:")
            for item in kept:
                risk = " [marketing-risk]" if item["marketing_risk"] else ""
                lines.append(f"  - [{item['title']}]({item['url']}){risk}")
        rejected = rejected_by_source.get(status["source_id"], [])[:3]
        if rejected:
            lines.append("- Rejected samples:")
            for item in rejected:
                lines.append(f"  - {item['title']} (`{item['reason']}`)")
        lines.append("")

    lines.extend(["## Pilot recommendation", ""])
    decisions = Counter(status["decision"] for status in payload["sources"])
    lines.append(
        f"Pilot sources: {decisions.get('pilot', 0)}; watchlist: {decisions.get('watchlist', 0)}; "
        f"needs adapter: {decisions.get('needs-adapter', 0)}; skip: {decisions.get('skip', 0)}."
    )
    lines.append("")
    lines.append("This report is a source-quality probe, not legal advice and not a production publishing decision.")
    return "\n".join(lines) + "\n"


def run(config_path: Path, output_dir: Path, now: datetime, lookback_override: Optional[int]) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    lookback_days = lookback_override or int(config.get("lookback_days") or 30)
    session = create_session()
    statuses: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    rejected_samples: dict[str, list[dict[str, Any]]] = {}

    for source in config.get("sources", []):
        status, kept, rejected = probe_source(session, source, now, lookback_days)
        statuses.append(status)
        items.extend(kept)
        rejected_samples[str(source["id"])] = rejected

    items.sort(key=lambda item: item["published_at"], reverse=True)
    category_counts = dict(sorted(Counter(item["category"] for item in items).items()))
    payload = {
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "lookback_days": lookback_days,
        "source_count": len(statuses),
        "retained_count": len(items),
        "category_counts": category_counts,
        "sources": statuses,
        "items": items,
        "rejected_samples": rejected_samples,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "hr-source-quality.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "hr-source-quality.md").write_text(build_markdown_report(payload), encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--lookback-days", type=int)
    parser.add_argument("--now", help="Optional ISO timestamp for deterministic probes")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    now = parse_datetime(args.now, UTC) if args.now else datetime.now(UTC)
    if now is None:
        raise SystemExit("Invalid --now timestamp")
    payload = run(args.config, args.output_dir, now, args.lookback_days)
    print(f"sources={payload['source_count']} retained={payload['retained_count']}")
    for status in payload["sources"]:
        print(
            f"{status['source_id']}: ok={status['ok']} raw={status['raw_count']} "
            f"recent={status['recent_count']} kept={status['kept_count']} decision={status['decision']}"
        )
    print(args.output_dir / "hr-source-quality.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
