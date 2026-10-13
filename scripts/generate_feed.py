#!/usr/bin/env python3
"""Generate an RSS 2.0 feed from the curated daily brief.

Output lands at data/feed.xml so the workflow's ``git add data/`` publishes it
with every hourly snapshot. Public URL: https://news.learnprompt.pro/data/feed.xml

Feed content is the curated layer (daily-brief clusters, persona-reviewed);
falls back to top AI-scored items from latest-24h.json when the brief is
missing. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

SITE = "https://news.learnprompt.pro"
FEED_PATH = "data/feed.xml"
EN_FEED_URL_PATH = "en/feed.xml"  # public URL of the English feed (vercel rewrite -> data/feed-en.xml)
MAX_ITEMS = 20

_CJK_RE = re.compile(r"[\u3000-\u303f\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af\uff00-\uffef]")
# importance_label values written by update_news.py (Chinese) -> English feed categories
EN_CATEGORY = {
    "官方更新": "Official update",
    "多源热议": "Multi-source buzz",
    "行业动态": "Industry news",
    "值得关注": "Worth watching",
}


def has_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text or ""))


def en_title(primary: dict) -> str:
    """English headline: en.title -> title_en -> title_original (if CJK-free) -> zh title."""
    en = primary.get("en") or {}
    for cand in (en.get("title"), primary.get("title_en"), primary.get("title_original")):
        cand = str(cand or "").strip()
        if cand and not has_cjk(cand):
            return cand
    return str(primary.get("title_zh") or primary.get("title") or "").strip()


def en_description(item: dict) -> str:
    """en.reason -> en.summary -> summary (only if CJK-free) -> title."""
    en = item.get("en") or {}
    for cand in (en.get("reason"), en.get("summary")):
        cand = str(cand or "").strip()
        if cand:
            return cand
    summary = str(item.get("summary") or "").strip()
    if summary and not has_cjk(summary):
        return summary
    return en_title(item)


def rfc822(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return ""
    return dt.strftime("%a, %d %b %Y %H:%M:%S %z")


def brief_entries(data_dir: Path, lang: str = "zh") -> tuple[list[dict], str]:
    path = data_dir / "daily-brief.json"
    if not path.exists():
        return [], ""
    brief = json.loads(path.read_text(encoding="utf-8"))
    entries = []
    for cluster in brief.get("items", [])[:MAX_ITEMS]:
        primary = cluster.get("primary_item") or {}
        url = cluster.get("primary_url") or primary.get("url") or ""
        if lang == "en":
            title = en_title(primary)
            label = EN_CATEGORY.get(cluster.get("importance_label") or "", "")
            source = cluster.get("source") or primary.get("source_name") or ""
            if has_cjk(source):
                source = ""
            if not (title and url):
                continue
            entries.append(
                {
                    "title": title,
                    "url": url,
                    "desc": en_description(primary),
                    "category": label,
                    "source": source,
                    "date": cluster.get("latest_at") or cluster.get("earliest_at") or "",
                }
            )
            continue
        title_zh = primary.get("title_zh") or primary.get("title") or ""
        title_en = primary.get("title_en") or ""
        title = title_zh if title_zh else title_en
        if title_en and title_zh and title_en != title_zh:
            title = f"{title_zh} / {title_en}"
        desc = (
            cluster.get("persona_review")
            or primary.get("recommend_reason_zh")
            or primary.get("summary")
            or ""
        )
        label = cluster.get("importance_label") or ""
        source = cluster.get("source") or primary.get("source_name") or ""
        if not (title and url):
            continue
        entries.append(
            {
                "title": title,
                "url": url,
                "desc": desc,
                "category": label,
                "source": source,
                "date": cluster.get("latest_at") or cluster.get("earliest_at") or "",
            }
        )
    return entries, brief.get("generated_at", "")


def latest_entries(data_dir: Path, lang: str = "zh") -> tuple[list[dict], str]:
    path = data_dir / "latest-24h.json"
    if not path.exists():
        return [], ""
    data = json.loads(path.read_text(encoding="utf-8"))
    items = sorted(
        data.get("items", []),
        key=lambda it: float(it.get("ai_score") or 0),
        reverse=True,
    )[:MAX_ITEMS]
    entries = []
    for it in items:
        if lang == "en":
            title = en_title(it)
            if not (title and it.get("url")):
                continue
            source = it.get("source") or ""
            entries.append(
                {
                    "title": title,
                    "url": it["url"],
                    "desc": en_description(it),
                    "category": "",
                    "source": "" if has_cjk(source) else source,
                    "date": it.get("published_at") or it.get("first_seen_at") or "",
                }
            )
            continue
        title = it.get("title_zh") or it.get("title") or ""
        if not (title and it.get("url")):
            continue
        entries.append(
            {
                "title": title,
                "url": it["url"],
                "desc": it.get("recommend_reason_zh") or "",
                "category": it.get("source_tier_label") or "",
                "source": it.get("source") or "",
                "date": it.get("published_at") or it.get("first_seen_at") or "",
            }
        )
    return entries, data.get("generated_at", "")


def build_feed(entries: list[dict], generated_at: str, lang: str = "zh") -> str:
    now = rfc822(generated_at) or rfc822(datetime.now(timezone.utc).isoformat())
    if lang == "en":
        head = [
            "<title>AI News Radar</title>",
            f"<link>{SITE}/en</link>",
            "<description>A curated 24-hour radar of AI news: official releases, new models and high-signal discussion.</description>",
            "<language>en</language>",
        ]
        self_href = f"{SITE}/{EN_FEED_URL_PATH}"
    else:
        head = [
            "<title>AI 更新雷达 · 每日精选</title>",
            f"<link>{SITE}</link>",
            "<description>24 小时 AI 更新雷达的策展精选：官方发布、模型上新、高信号讨论。</description>",
            "<language>zh-cn</language>",
        ]
        self_href = f"{SITE}/{FEED_PATH}"
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0">',
        "<channel>",
        *head,
        f"<lastBuildDate>{now}</lastBuildDate>",
        f'<atom10:link xmlns:atom10="http://www.w3.org/2005/Atom" rel="self" type="application/rss+xml" href="{self_href}"/>',
    ]
    for e in entries:
        desc = e["desc"]
        if e["source"]:
            if lang == "en":
                desc = f"{desc} ({e['source']})" if desc else e["source"]
            else:
                desc = f"{desc}（{e['source']}）" if desc else e["source"]
        parts += [
            "<item>",
            f"<title>{escape(e['title'])}</title>",
            f"<link>{escape(e['url'])}</link>",
            f'<guid isPermaLink="true">{escape(e["url"])}</guid>',
            f"<description>{escape(desc)}</description>",
        ]
        if e["category"]:
            parts.append(f"<category>{escape(e['category'])}</category>")
        pub = rfc822(e["date"])
        if pub:
            parts.append(f"<pubDate>{pub}</pubDate>")
        parts.append("</item>")
    parts += ["</channel>", "</rss>", ""]
    return "\n".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--lang", choices=("zh", "en"), default="zh")
    ap.add_argument("--out", default=None, help="Output path (default: <data-dir>/feed.xml)")
    args = ap.parse_args()
    data_dir = Path(args.data_dir)
    lang = args.lang

    entries, generated_at = brief_entries(data_dir, lang)
    source = "daily-brief"
    if not entries:
        entries, generated_at = latest_entries(data_dir, lang)
        source = "latest-24h"
    if not entries:
        raise SystemExit("no feed entries: neither daily-brief.json nor latest-24h.json usable")

    out = Path(args.out) if args.out else data_dir / "feed.xml"
    out.write_text(build_feed(entries, generated_at, lang), encoding="utf-8")
    print(f"{out.name}: {len(entries)} items from {source} -> {out}")


if __name__ == "__main__":
    main()
