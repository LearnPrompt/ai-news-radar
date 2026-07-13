#!/usr/bin/env python3
"""Cross-audit source quality against AIHOT curation and story selection.

This is a maintainer-facing audit tool. It never mutates pipeline data: it
reads ``archive.json`` / ``stories-merged.json`` / ``daily-brief.json`` from
``--data-dir`` and writes a markdown report. Per-source metrics:

1. total items and AI relevance keep rate (``ai_is_related``; recomputed via
   ``scripts.ai_relevance`` when the archive record lacks the field)
2. AIHOT hit rate: share of items matching an AIHOT-curated item by
   normalized-URL exact match or title-token Jaccard >= 0.6
3. exclusive contribution rate: share of items no other source covered
4. selection rate: share of items surfacing in daily-brief or multi-source
   merged stories
5. average ``importance_score`` when items carry one

Matching is implemented locally on purpose so this audit does not import the
full ``update_news`` pipeline module.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# Allow `python scripts/audit_source_quality.py ...` from the repo root while
# keeping package imports working under pytest.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ai_relevance import is_ai_related_record  # noqa: E402

JACCARD_THRESHOLD = 0.6
# Tokens shared by more than this many items are too generic to seed fuzzy
# candidate lookup (e.g. "ai", "模型"); they still count inside Jaccard itself.
CANDIDATE_TOKEN_DF_CAP = 400

DISCUSSION_SITE_IDS = {
    "buzzing",
    "iris",
    "techurls",
    "zeli",
    "hackernews",
    "newsnow",
}

TRACKING_PARAMS = {
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
}

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
    "it",
    "of",
    "on",
    "the",
    "to",
    "with",
}

_CJK_RE = re.compile(r"[一-鿿]")
_NON_WORD_RE = re.compile(r"[^a-z0-9一-鿿]+")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_url_for_match(raw_url: str) -> str:
    """Local URL normalization: lowercase host, drop tracking params/fragment."""
    try:
        parsed = urlparse(str(raw_url or "").strip())
        if not parsed.scheme:
            return str(raw_url or "").strip().rstrip("/")
        query = [
            (k, v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS
        ]
        parsed = parsed._replace(
            scheme=parsed.scheme.lower(),
            netloc=parsed.netloc.lower(),
            fragment="",
            query=urlencode(query, doseq=True),
        )
        return urlunparse(parsed).rstrip("/")
    except Exception:
        return str(raw_url or "").strip()


def title_tokens(title: str) -> frozenset[str]:
    """Lowercased, punctuation-free tokens: ASCII words plus CJK bigrams."""
    text = _NON_WORD_RE.sub(" ", str(title or "").lower())
    tokens: set[str] = set()
    for chunk in text.split():
        if _CJK_RE.search(chunk):
            chars = [c for c in chunk if _CJK_RE.match(c)]
            ascii_part = "".join(c for c in chunk if not _CJK_RE.match(c))
            if len(ascii_part) > 1 and ascii_part not in TITLE_STOPWORDS:
                tokens.add(ascii_part)
            if len(chars) == 1:
                tokens.add(chars[0])
            for i in range(len(chars) - 1):
                tokens.add(chars[i] + chars[i + 1])
        elif len(chunk) > 1 and chunk not in TITLE_STOPWORDS:
            tokens.add(chunk)
    return frozenset(tokens)


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if not inter:
        return 0.0
    return inter / (len(a) + len(b) - inter)


def event_time_of(item: dict[str, Any]) -> datetime | None:
    raw = str(item.get("published_at") or item.get("first_seen_at") or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def ai_related(item: dict[str, Any]) -> bool:
    value = item.get("ai_is_related")
    if isinstance(value, bool):
        return value
    return is_ai_related_record(item)


def is_aihot_truth(item: dict[str, Any]) -> bool:
    if str(item.get("site_id") or "") == "aihot":
        return True
    meta = item.get("meta")
    if isinstance(meta, dict) and meta.get("aihot_selected"):
        return True
    return bool(item.get("aihot_selected"))


class MatchIndex:
    """URL + fuzzy-title index over a set of items for cheap lookups."""

    def __init__(self, items: list[dict[str, Any]]) -> None:
        self.items = items
        self.urls: dict[str, list[int]] = defaultdict(list)
        self.tokens: list[frozenset[str]] = []
        token_df: Counter[str] = Counter()
        for idx, item in enumerate(items):
            url = normalize_url_for_match(str(item.get("url") or ""))
            if url:
                self.urls[url].append(idx)
            toks = title_tokens(str(item.get("title") or ""))
            self.tokens.append(toks)
            token_df.update(toks)
        self.token_index: dict[str, list[int]] = defaultdict(list)
        for idx, toks in enumerate(self.tokens):
            for token in toks:
                if token_df[token] <= CANDIDATE_TOKEN_DF_CAP:
                    self.token_index[token].append(idx)

    def match(
        self,
        url: str,
        toks: frozenset[str],
        *,
        exclude: set[int] | None = None,
        exclude_site: str | None = None,
    ) -> int | None:
        """Return the index of a matching item, or None."""
        exclude = exclude or set()
        for idx in self.urls.get(url, ()):
            if idx in exclude:
                continue
            if exclude_site and str(self.items[idx].get("site_id") or "") == exclude_site:
                continue
            return idx
        seen: set[int] = set()
        for token in toks:
            for idx in self.token_index.get(token, ()):
                if idx in seen or idx in exclude:
                    continue
                seen.add(idx)
                if exclude_site and str(self.items[idx].get("site_id") or "") == exclude_site:
                    continue
                if jaccard(toks, self.tokens[idx]) >= JACCARD_THRESHOLD:
                    return idx
        return None


def selected_keys_from_stories(
    stories_payload: dict[str, Any], brief_payload: dict[str, Any]
) -> tuple[set[str], set[str]]:
    """Collect item ids and normalized URLs that made the curated layer."""
    ids: set[str] = set()
    urls: set[str] = set()

    def absorb(story: dict[str, Any]) -> None:
        for src in story.get("sources") or []:
            if src.get("id"):
                ids.add(str(src["id"]))
            url = normalize_url_for_match(str(src.get("url") or ""))
            if url:
                urls.add(url)
        for sub in story.get("items") or []:
            if isinstance(sub, dict) and sub.get("id"):
                ids.add(str(sub["id"]))

    for story in stories_payload.get("stories") or []:
        distinct_sites = {
            str(src.get("site_id") or "") for src in story.get("sources") or []
        } - {""}
        if len(distinct_sites) > 1:
            absorb(story)
    for story in brief_payload.get("items") or []:
        absorb(story)
    return ids, urls


def importance_by_site(stories_payload: dict[str, Any]) -> dict[str, list[float]]:
    """Story-level importance_score grouped by contributing site."""
    out: dict[str, list[float]] = defaultdict(list)
    for story in stories_payload.get("stories") or []:
        score = story.get("importance_score")
        if score is None:
            continue
        sites = {str(src.get("site_id") or "") for src in story.get("sources") or []}
        for site in sites:
            if site:
                out[site].append(float(score))
    return out


def pct(numerator: int, denominator: int) -> str:
    if not denominator:
        return "—"
    return f"{numerator / denominator:.1%}"


# 2026-05-12 v0.4.0 AI relevance audit keep rates, for trend comparison.
# Source: reports/ai-relevance-audit/v0.4.0-2026-05-12.md
HISTORICAL_KEEP_RATE = {
    "buzzing": 0.117,
    "iris": 0.171,
    "techurls": 0.275,
    "newsnow": 0.288,
    "zeli": 1.0,
}

DISCUSSION_NOTES = {
    "buzzing": "buzzing.cc 全量 feed，主题不限 AI；已于 2026-07-13 从公开流水线退役。",
    "iris": "Info Flow 多 feed 聚合，科技向但非 AI 专属；已于 2026-07-13 从公开流水线退役。",
    "techurls": "科技新闻聚合，科技占比高但 AI 纯度一般。",
    "newsnow": "热点聚合，量级中等。",
    "zeli": "Zeli 只取 HN 24h 最热；2026-07-13 起取消整榜白名单，每条标题必须通过 AI 信号门槛。",
    "hackernews": "HN 官方源，量小且规则默认放行。",
}


def recommendation_sections(stats: dict[str, dict[str, Any]]) -> list[str]:
    """Rule-based三档建议, with the data that justifies each call."""

    def row(sid: str) -> str:
        s = stats.get(sid)
        if not s or not s["total"]:
            return f"- **{sid}**：窗口内无数据，维持现状并观察。"
        return (
            f"- **{sid}**：{s['total']} 条 / AI保留率 {pct(s['ai_kept'], s['total'])}"
            f" / AIHOT命中率 {pct(s['aihot_hits'], s['total'])}"
            f" / 独家率 {pct(s['exclusive'], s['total'])}"
            f" / 进精选率 {pct(s['selected'], s['total'])}"
        )

    delete: list[str] = []
    throttle: list[str] = []
    keep: list[str] = []
    for sid in DISCUSSION_SITE_IDS:
        s = stats.get(sid)
        if not s or not s["total"]:
            keep.append(row(sid))
            continue
        keep_rate = s["ai_kept"] / s["total"]
        selected_rate = s["selected"] / s["total"]
        if s["total"] >= 5000 and keep_rate < 0.05 and selected_rate < 0.001:
            delete.append(row(sid))
        elif s["total"] >= 1000 and (keep_rate < 0.30 or selected_rate < 0.01):
            throttle.append(row(sid))
        else:
            keep.append(row(sid))

    lines = [
        "",
        "## 三档建议（仅供决策：删源需 Carl 拍板，本报告只供决策）",
        "",
        "判据：删 = 量极大(>=5000)且 AI 保留率 <5% 且几乎从不进精选(<0.1%)；"
        "降权限流 = 量较大(>=1000)且（AI 保留率 <30% 或进精选率 <1%）；其余保留。",
        "",
        "### 删（候选）",
        "",
    ]
    lines.extend(delete or ["- （无）"])
    lines.extend(["", "### 降权限流", ""])
    lines.extend(throttle or ["- （无）"])
    lines.extend(
        [
            "",
            "当前实施状态：TopHub、Buzzing、Info Flow 已从公开抓取任务退役，"
            "旧归档记录在加载时清除；Zeli 已取消整榜白名单。"
            "TechURLs、NewsNow 与聚焦关键词的 Hacker News 暂时保留。",
            "",
            "### 保留",
            "",
        ]
    )
    lines.extend(keep or ["- （无）"])
    return lines


def build_report(
    window_items: list[dict[str, Any]],
    stats: dict[str, dict[str, Any]],
    *,
    days: int,
    window_start: datetime,
    window_end: datetime,
    generated_at: str,
) -> str:
    site_ids = sorted(
        stats,
        key=lambda s: stats[s]["total"] - stats[s]["ai_kept"],
        reverse=True,
    )
    lines = [
        "# 信源质量交叉审计 — v0.8",
        "",
        f"- 生成时间：`{generated_at}`",
        f"- 数据窗口：近 {days} 天（`{window_start.date()}` 至 `{window_end.date()}`，"
        f"以 archive 最新条目时间为锚点），共 `{len(window_items)}` 条",
        "- 数据来源：`data/archive.json`（21 天滚动全量）、`data/stories-merged.json`、"
        "`data/daily-brief.json`（后两者仅覆盖最近一轮 24h 窗口，「进精选率」按此口径解读）",
        "",
        "## 方法",
        "",
        "- **AI 保留率**：条目 `ai_is_related` 占比；archive 记录缺该字段时用"
        " `scripts/ai_relevance.py` 的同一套规则现算，与流水线口径一致。",
        "- **AIHOT 命中率**：以 AIHOT 精选条目（`site_id=aihot` 或 `aihot_selected`，"
        "收录门槛 aihot_score>=60）为 ground truth；URL 归一化（去 utm/跟踪参数、"
        "小写主机名）精确匹配，或标题小写去标点后 token（英文词 + 中文双字）"
        f"Jaccard >= {JACCARD_THRESHOLD} 模糊匹配。",
        "- **独家贡献率**：条目未被任何其他 site_id 的条目（同样的 URL/标题匹配规则）覆盖的比例。",
        "- **进精选率**：条目出现在 `daily-brief.json` 或 `stories-merged.json` 多源"
        " story 的 sources 里（按 item id 或归一化 URL 匹配）的比例。",
        "- **平均 importance**：条目自带 `importance_score` 时的均值；archive 条目"
        "普遍不带该字段，故补充「story 层均值」= 该源参与的 story 的平均 importance_score。",
        "",
        "## 总表（按 AI 无关噪音条数从高到低）",
        "",
        "| site_id | tier | 总条数 | AI保留率 | AIHOT命中率 | 独家贡献率 | 进精选率 | 平均importance | story层均值 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for sid in site_ids:
        s = stats[sid]
        tier = "discussion" if sid in DISCUSSION_SITE_IDS else ("aihot(基准)" if sid == "aihot" else "-")
        imp = f"{s['importance_sum'] / s['importance_n']:.1f}" if s["importance_n"] else "—"
        story_imp = f"{s['story_importance_avg']:.1f}" if s["story_importance_avg"] is not None else "—"
        aihot_rate = "基准" if sid == "aihot" else pct(s["aihot_hits"], s["total"])
        lines.append(
            f"| {sid} | {tier} | {s['total']} | {pct(s['ai_kept'], s['total'])} "
            f"| {aihot_rate} | {pct(s['exclusive'], s['total'])} "
            f"| {pct(s['selected'], s['total'])} | {imp} | {story_imp} |"
        )

    lines.extend(
        [
            "",
            "## Discussion tier 聚合站逐源分析",
            "",
            "与 2026-05-12 的 v0.4.0 审计"
            "（`reports/ai-relevance-audit/v0.4.0-2026-05-12.md`）对比；"
            "另参照 2026-07-10 的 AIHOT 对比结论"
            "（`reports/usability/2026-07-10-source-quality/AIHOT_COMPARISON.md`）：",
            "「AI News Radar 的主要问题不是源不够，而是默认层太宽」——"
            "前五个宽聚合源曾贡献 76.9% 的 AI 入池数据。",
            "",
        ]
    )
    for sid in sorted(
        (s for s in DISCUSSION_SITE_IDS if s in stats),
        key=lambda s: stats[s]["total"],
        reverse=True,
    ):
        s = stats[sid]
        keep_rate = s["ai_kept"] / s["total"] if s["total"] else 0.0
        hist = HISTORICAL_KEEP_RATE.get(sid)
        hist_note = (
            f"v0.4.0 审计保留率 {hist:.1%}，本窗口 {keep_rate:.1%}，"
            + ("基本持平。" if abs(keep_rate - hist) < 0.05 else "有明显变化。")
            if hist is not None
            else "v0.4.0 审计未单列该源。"
        )
        lines.extend(
            [
                f"### {sid}",
                "",
                f"- 近 {days} 天 {s['total']} 条；AI 保留率 {pct(s['ai_kept'], s['total'])}；"
                f"AIHOT 命中率 {pct(s['aihot_hits'], s['total'])}；"
                f"独家贡献率 {pct(s['exclusive'], s['total'])}；"
                f"进精选率 {pct(s['selected'], s['total'])}。",
                f"- {hist_note}",
                f"- {DISCUSSION_NOTES.get(sid, '')}",
                "",
            ]
        )

    lines.extend(recommendation_sections(stats))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit per-source quality against AIHOT and story selection")
    parser.add_argument("--data-dir", default="data", help="Directory with archive.json etc.")
    parser.add_argument("--days", type=int, default=14, help="Lookback window in days")
    parser.add_argument(
        "--output",
        default="reports/source-quality/v0.8-audit.md",
        help="Markdown report path",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    archive = load_json(data_dir / "archive.json")
    items = [it for it in (archive.get("items") or []) if isinstance(it, dict)]
    stories_payload = load_json(data_dir / "stories-merged.json")
    brief_payload = load_json(data_dir / "daily-brief.json")

    timestamps = [t for t in (event_time_of(it) for it in items) if t]
    if not timestamps:
        print("archive.json has no timestamped items", file=sys.stderr)
        return 1
    window_end = max(timestamps)
    window_start = window_end - timedelta(days=max(1, args.days))
    window_items = [it for it in items if (t := event_time_of(it)) and t >= window_start]

    aihot_truth = [it for it in window_items if is_aihot_truth(it)]
    aihot_index = MatchIndex(aihot_truth)
    all_index = MatchIndex(window_items)
    selected_ids, selected_urls = selected_keys_from_stories(stories_payload, brief_payload)
    story_importance = importance_by_site(stories_payload)

    stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "total": 0,
            "ai_kept": 0,
            "aihot_hits": 0,
            "exclusive": 0,
            "selected": 0,
            "importance_sum": 0.0,
            "importance_n": 0,
            "story_importance_avg": None,
        }
    )

    for idx, item in enumerate(window_items):
        sid = str(item.get("site_id") or "unknown")
        s = stats[sid]
        s["total"] += 1
        if ai_related(item):
            s["ai_kept"] += 1

        url = normalize_url_for_match(str(item.get("url") or ""))
        toks = title_tokens(str(item.get("title") or ""))

        if sid != "aihot" and aihot_index.match(url, toks) is not None:
            s["aihot_hits"] += 1
        if all_index.match(url, toks, exclude={idx}, exclude_site=sid) is None:
            s["exclusive"] += 1
        if str(item.get("id") or "") in selected_ids or (url and url in selected_urls):
            s["selected"] += 1
        raw_importance = item.get("importance_score")
        if raw_importance is not None:
            try:
                s["importance_sum"] += float(raw_importance)
                s["importance_n"] += 1
            except (TypeError, ValueError):
                pass

    for sid, scores in story_importance.items():
        if sid in stats and scores:
            stats[sid]["story_importance_avg"] = sum(scores) / len(scores)

    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    report = build_report(
        window_items,
        dict(stats),
        days=args.days,
        window_start=window_start,
        window_end=window_end,
        generated_at=generated_at,
    )

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report + "\n", encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
