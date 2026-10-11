"""Public project sources and the small, daily '今天值得做' selection."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import urlparse, urlunparse
from zoneinfo import ZoneInfo

import feedparser
from bs4 import BeautifulSoup
from dateutil import parser as dtparser

try:
    from scripts.ai_relevance import score_ai_relevance
except ModuleNotFoundError:  # direct execution of update_news.py
    from ai_relevance import score_ai_relevance

GITHUB_TRENDING_URL = "https://github.com/trending?since=daily"
PRODUCTHUNT_FEED_URL = "https://www.producthunt.com/feed"
PROJECT_SOURCES = {"github_trending": "GitHub Trending", "producthunt": "Product Hunt"}
UTC = timezone.utc


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", BeautifulSoup(str(value or ""), "html.parser").get_text(" ", strip=True)).strip()


def public_url(value: Any, host: str) -> str:
    try:
        parsed = urlparse(str(value or "").strip())
        if parsed.scheme != "https" or parsed.hostname not in {host, f"www.{host}"} or parsed.username or parsed.password:
            return ""
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))
    except ValueError:
        return ""


def parse_github_trending(html: str, now: datetime) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("article.Box-row")
    if not rows:
        raise ValueError("GitHub Trending returned no repository rows")
    out = []
    seen = set()
    for rank, row in enumerate(rows[:50], 1):
        anchor = row.select_one("h2 a[href]")
        if anchor is None:
            continue
        href = str(anchor.get("href") or "")
        url = public_url(f"https://github.com{href}" if href.startswith("/") else href, "github.com")
        path = urlparse(url).path.strip("/")
        if not url or not re.fullmatch(r"[\w.-]+/[\w.-]+", path) or url in seen:
            continue
        seen.add(url)
        description = row.select_one("p")
        summary = clean_text(description.get_text(" ", strip=True) if description else "")[:800]
        stars = re.search(r"([\d,]+)\s+stars?\s+today", row.get_text(" ", strip=True), re.I)
        out.append({
            "site_id": "github_trending", "site_name": PROJECT_SOURCES["github_trending"],
            "project_name": path, "url": url, "summary": summary,
            "published_at": None, "observed_at": now, "source_rank": rank,
            "stars_today": int(stars.group(1).replace(",", "")) if stars else None,
        })
    if not out:
        raise ValueError("GitHub Trending repository links could not be parsed")
    return out


def source_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = dtparser.parse(str(value))
        return parsed.replace(tzinfo=UTC) if not parsed.tzinfo else parsed.astimezone(UTC)
    except (ValueError, TypeError, OverflowError):
        return None


def producthunt_activity(project: dict[str, Any]) -> datetime | None:
    # Only a missing update permits a publication fallback; invalid updates
    # must not turn into a different, apparently fresh event.
    return project.get("updated_at") if project.get("recency_basis") == "updated_at" else project.get("published_at")


def parse_producthunt_feed(xml: str, now: datetime) -> list[dict[str, Any]]:
    feed = feedparser.parse(xml)
    if not feed.entries:
        raise ValueError("Product Hunt returned no feed entries")
    out = []
    seen = set()
    for rank, entry in enumerate(feed.entries[:80], 1):
        name = clean_text(entry.get("title"))[:200]
        url = public_url(entry.get("link"), "producthunt.com")
        if not name or not url or url in seen:
            continue
        # Feed updates are useful discovery signals, not verified first launches.
        # feedparser aliases missing updated to published; a plain dict reads
        # only the actual feed fields so the fallback remains explicit.
        timestamps = dict(entry)
        published = source_timestamp(timestamps.get("published"))
        updated = source_timestamp(timestamps.get("updated"))
        basis = "updated_at" if "updated" in timestamps else "published_at"
        activity = updated if basis == "updated_at" else published
        if activity is None or not now - timedelta(hours=24) <= activity <= now:
            continue
        seen.add(url)
        contents = entry.get("content") or []
        body = entry.get("summary") or (contents[0].get("value") if contents else "") or ""
        soup = BeautifulSoup(body, "html.parser")
        # The official feed separates its tagline and Discussion/Link footer.
        for anchor in soup.select("a"):
            anchor.decompose()
        summary = clean_text(soup.get_text(" ", strip=True)).strip(" |")[:800]
        out.append({
            "site_id": "producthunt", "site_name": PROJECT_SOURCES["producthunt"],
            "project_name": name, "url": url, "summary": summary,
            "published_at": published, "updated_at": updated, "recency_basis": basis,
            "observed_at": now, "source_rank": rank,
        })
    return out


def fetch_github_projects(session: Any, now: datetime) -> list[dict[str, Any]]:
    response = session.get(GITHUB_TRENDING_URL, timeout=25)
    response.raise_for_status()
    return parse_github_trending(response.text, now)


def fetch_producthunt_projects(
    session: Any, now: datetime, *, clock: Callable[[], datetime] | None = None,
) -> list[dict[str, Any]]:
    response = session.get(PRODUCTHUNT_FEED_URL, timeout=25)
    response.raise_for_status()
    # Earlier sources can take minutes. Updates already present in this response
    # must be compared with observation time, not the whole job's start time.
    observed_at = max(now, clock() if clock else datetime.now(UTC))
    return parse_producthunt_feed(response.text, observed_at)


def recommendation_fallback(project: dict[str, Any]) -> str:
    summary = str(project["summary"]).rstrip("。.!")
    # These action suggestions only match capabilities in the source description.
    actions = (
        (r"diagram", "用它画一张你正在讲解的示意图，看看能否省下手工排版的时间。"),
        (r"code review", "拿一段自己的代码试试它的 AI 审查，看看能否发现遗漏的问题。"),
        (r"file organiz", "用一小批文件试试它的 AI 整理效果，看看是否符合你的习惯。"),
        (r"cost tracking.*AI coding|AI coding.*cost tracking", "选一个正在开发的项目，看看它的 AI 编程费用记录能否帮你控制成本。"),
        (r"video editor|video editing", "用一段自己的素材试试 AI 视频剪辑，看看能否减少手工操作。"),
        (r"document search|retrieval|\bRAG\b", "用一份自己的资料试试检索，看看能否更快找到需要的信息。"),
        (r"transcri", "用一段自己的录音试试转写，看看准确度是否满足你的需求。"),
        (r"desktop.*agent|agent.*desktop", "挑一个日常桌面任务试试它的 AI Agent，看看能否减少重复操作。"),
    )
    for pattern, action in actions:
        if re.search(pattern, summary, re.I):
            return action
    # Quote the source's own capability instead of inventing a trial result.
    summary = summary if len(summary) <= 140 else summary[:137] + "…"
    if project["site_id"] == "github_trending":
        return f"看看这个开源项目的「{summary}」能力，判断能否用到你手头的任务中。"
    return f"体验它主打的「{summary}」，看看是否解决你当前的问题。"


def build_today_projects(
    projects: list[dict[str, Any]], now: datetime, statuses: list[dict[str, Any]],
    *, limit: int = 4, recommend: Callable[[str, str], str | None] | None = None,
    cache: dict[str, str] | None = None,
) -> dict[str, Any]:
    cache = cache if cache is not None else {}
    buckets: dict[str, list[dict[str, Any]]] = {sid: [] for sid in PROJECT_SOURCES}
    seen = set()
    for project in sorted(projects, key=lambda p: int(p.get("source_rank") or 999)):
        sid = project.get("site_id")
        if sid not in buckets or not project.get("summary") or not project.get("project_name"):
            continue
        url = public_url(project.get("url"), "github.com" if sid == "github_trending" else "producthunt.com")
        observed = project.get("observed_at")
        if not url or url in seen or not isinstance(observed, datetime) or not now - timedelta(hours=24) <= observed <= now:
            continue
        if sid == "producthunt":
            activity = producthunt_activity(project)
            if not isinstance(activity, datetime) or not now - timedelta(hours=24) <= activity <= now:
                continue
        # Project names alone often contain no AI signal; score the real tagline too.
        relevance = score_ai_relevance({"title": f"{project['project_name']} {project['summary']}", "url": url})
        if not relevance["is_ai_related"]:
            continue
        seen.add(url)
        buckets[sid].append({**project, "url": url})

    selected = []
    # Alternate the two rankings so one busy source cannot crowd out the other.
    while len(selected) < max(0, limit) and any(buckets.values()):
        for bucket in buckets.values():
            if bucket and len(selected) < limit:
                selected.append(bucket.pop(0))

    items = []
    for project in selected:
        name, summary = project["project_name"], project["summary"]
        cache_key = "project-recommend::" + hashlib.sha256(f"{project['url']}\n{summary}".encode()).hexdigest()
        reason = cache.get(cache_key)
        if not reason and recommend:
            try:
                reason = recommend(name, summary)
            except Exception:
                reason = None  # Optional copy generation must not stop public sources.
            if reason:
                cache[cache_key] = reason
        items.append({
            "id": "project_" + hashlib.sha1(project["url"].encode()).hexdigest()[:12],
            "project_name": name, "url": project["url"], "summary": summary,
            "site_id": project["site_id"], "site_name": PROJECT_SOURCES[project["site_id"]],
            "recommend_reason_zh": reason or recommendation_fallback(project),
            "published_at": project["published_at"].astimezone(UTC).isoformat().replace("+00:00", "Z") if project["published_at"] else None,
            "updated_at": project["updated_at"].astimezone(UTC).isoformat().replace("+00:00", "Z") if project.get("updated_at") else None,
            "recency_basis": project.get("recency_basis"),
            "observed_at": project["observed_at"].astimezone(UTC).isoformat().replace("+00:00", "Z"),
        })
    return {
        "generated_at": now.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "date": now.astimezone(ZoneInfo("Asia/Taipei")).date().isoformat(),
        "total_items": len(items), "items": items,
        "sources": [s for s in statuses if s.get("site_id") in PROJECT_SOURCES],
    }
