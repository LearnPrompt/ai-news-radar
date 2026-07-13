#!/usr/bin/env python3
"""Explainable AI relevance scoring for news records."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

AI_KEYWORDS = [
    "a.i.",
    "agent view",
    "agent skills",
    "for agents",
    "parallel agent",
    "并行 agent",
    "known agents",
    "hermes-agent",
    "agentmemory",
    "cursor",
    "aigc",
    "llm",
    "gpt",
    "grok",
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
    "多模态",
    "交互模型",
    "变换器",
    "语言模型",
    "视觉语言模型",
    "基础模型",
    "本地模型",
    "具身智能",
    "大模型",
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
    "benchmark",
    "dataset",
    "eval",
    "evaluation",
    "sandbox",
    "context",
    "开源",
    "技术",
    "编程",
    "软件",
    "沙箱",
    "上下文",
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

UNSAFE_HARD_PATTERNS = [
    re.compile(r"\bcreampie\b", re.I),
    re.compile(r"\bblowjob\b", re.I),
    re.compile(r"\bsuck (?:your|my) (?:dick|cock)\b", re.I),
    re.compile(r"中出|婊子|吸你的鸡鸡|操虚拟女友", re.I),
]

UNSAFE_PROMO_PATTERNS = [
    re.compile(r"\b(?:nsfw|nudes?|porn(?:ography)?)\b", re.I),
    re.compile(r"\buncensored pictures?\b", re.I),
    re.compile(r"\bvirtual girlfriends?\b", re.I),
    re.compile(r"\bknock her up\b", re.I),
    re.compile(r"未经审查的图片|虚拟女友|色情内容|成人内容", re.I),
]

EN_SIGNAL_RE = re.compile(
    r"(?i)(?<![a-z0-9])(ai|aigc|llm|gpt|openai|anthropic|deepseek|gemini|claude|robot|robotics|embodied|autonomous|machine learning|artificial intelligence|transformer|diffusion|agent)(?![a-z0-9])"
)
MEANINGFUL_EN_SIGNAL_RE = re.compile(
    r"(?i)(?<![a-z0-9])(ai|aigc|llm|gpt|openai|anthropic|deepseek|gemini|claude|robot|robotics|embodied|autonomous|machine learning|artificial intelligence|transformer|diffusion)(?![a-z0-9])"
)
BROAD_AI_TERMS = {"agent", "模型", "推理"}
AI_RELEVANCE_THRESHOLD = 0.65

SOURCE_PRIORS = {
    "official_ai": 0.35,
    "curated_media": 0.18,
    "aibase": 0.45,
    "aihot": 0.45,
    "aihubtoday": 0.45,
    "followbuilders": 0.25,
    "opmlrss": 0.15,
    "xapi": 0.15,
    "socialdata_x": 0.15,
}
AI_DEFAULT_SOURCES = {"aibase", "aihot", "aihubtoday"}
CURATED_MEDIA_TRUSTED_SOURCE_KEYWORDS = [
    "the decoder ai news",
    "techcrunch ai",
    "venturebeat ai",
    "artificial intelligence news",
    "claude code releases",
]
CURATED_MEDIA_RESEARCH_SOURCE_KEYWORDS = [
    "marktechpost research",
]
CURATED_MEDIA_RESEARCH_TERMS = [
    "paper",
    "arxiv",
    "research",
    "benchmark",
    "bench",
    "eval",
    "evaluation",
    "dataset",
    "model",
    "llm",
    "agent",
    "diffusion",
    "transformer",
    "multimodal",
    "reasoning",
    "inference",
    "training",
    "open-source",
    "robot",
    "governance",
]
CURATED_MEDIA_BUSINESS_TERMS = [
    "funding",
    "raises",
    "raised",
    "startup",
    "acquire",
    "acquisition",
    "merger",
    "revenue",
    "enterprise",
    "ipo",
    "valuation",
]

LABEL_KEYWORDS = [
    ("model_release", ["model", "gpt", "grok", "claude", "gemini", "deepseek", "llm", "模型", "大模型", "发布", "release"]),
    ("developer_tool", ["copilot", "codex", "mcp", "api", "sdk", "developer", "开发者", "编程", "代码", "coding"]),
    ("agent_workflow", ["agent", "智能体", "workflow", "工作流", "tool use", "function calling"]),
    ("research_paper", ["paper", "arxiv", "research", "benchmark", "eval", "论文", "研究", "评测", "榜单"]),
    ("infra_compute", ["gpu", "npu", "cuda", "chip", "semiconductor", "算力", "芯片", "推理"]),
    ("robotics", ["robot", "robotics", "embodied", "机器人", "具身"]),
    ("industry_business", ["funding", "acquire", "融资", "收购", "估值", "营收", "公司"]),
    ("ai_product_update", ["openai", "anthropic", "google", "perplexity", "cursor", "产品", "上线", "更新"]),
]


def contains_any_keyword(haystack: str, keywords: list[str]) -> bool:
    h = haystack.lower()
    return any(k in h for k in keywords)


def contains_keyword(haystack: str, keyword: str) -> bool:
    """Match ASCII keywords as terms, while keeping CJK substring matching."""
    h = haystack.lower()
    k = keyword.lower()
    if re.search(r"[a-z0-9]", k):
        return re.search(rf"(?<![a-z0-9]){re.escape(k)}(?![a-z0-9])", h) is not None
    return k in h


def contains_unsafe_promotional_content(text: str) -> bool:
    """Block explicit adult promotion without hiding a single policy/news mention."""
    if any(pattern.search(text) for pattern in UNSAFE_HARD_PATTERNS):
        return True
    return sum(bool(pattern.search(text)) for pattern in UNSAFE_PROMO_PATTERNS) >= 2


def matched_keywords(haystack: str, keywords: list[str]) -> list[str]:
    return sorted({k for k in keywords if contains_keyword(haystack, k)})


def contains_meaningful_ai_signal(haystack: str) -> bool:
    h = haystack.lower()
    if MEANINGFUL_EN_SIGNAL_RE.search(h):
        return True
    return any(contains_keyword(h, k) for k in AI_KEYWORDS if k not in BROAD_AI_TERMS)


def _label_for_text(text: str, has_tech: bool) -> str:
    for label, keywords in LABEL_KEYWORDS:
        if contains_any_keyword(text, keywords):
            return label
    if has_tech:
        return "ai_tech"
    return "ai_general"


def _result(
    *,
    is_ai_related: bool,
    score: float,
    label: str,
    reason: str,
    signals: list[str] | None = None,
    noise: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "is_ai_related": bool(is_ai_related),
        "score": round(max(0.0, min(1.0, score)), 2),
        "label": label,
        "reason": reason,
        "signals": signals or [],
        "noise": noise or [],
    }


def score_ai_relevance(record: dict[str, Any]) -> dict[str, Any]:
    """Return an explainable relevance score while preserving the old keep/drop behavior."""
    site_id = str(record.get("site_id") or "")
    title = str(record.get("title") or "")
    source = str(record.get("source") or "")
    site_name = str(record.get("site_name") or "")
    url = str(record.get("url") or "")
    # Relevance is primarily based on reader-visible text. A hostname may add a
    # known full keyword such as `openai`, but a generic `.ai` suffix is not
    # evidence and URL paths never participate.
    text = f"{title} {source} {site_name}".lower()
    try:
        url_host = (urlparse(url).netloc or "").lower()
    except Exception:
        url_host = ""
    signal_text = f"{text} {url_host}"

    ai_signals = matched_keywords(signal_text, AI_KEYWORDS)
    tech_signals = matched_keywords(signal_text, TECH_KEYWORDS)
    noise = matched_keywords(text, NOISE_KEYWORDS) + matched_keywords(text, COMMERCE_NOISE_KEYWORDS)
    source_prior = SOURCE_PRIORS.get(site_id, 0.0)

    if contains_unsafe_promotional_content(text):
        return _result(
            is_ai_related=False,
            score=0.0,
            label="unsafe_content",
            reason="unsafe_promotional_content",
            signals=[],
            noise=["unsafe_promotional_content"],
        )

    if site_id == "zeli" and not ("24h" in source.lower() or "24h最热" in source):
        return _result(
            is_ai_related=False,
            score=0.2,
            label="source_scope_drop",
            reason="zeli_only_keeps_24h_hot_source",
            signals=ai_signals + tech_signals,
            noise=noise,
        )

    if site_id == "curated_media":
        source_l = source.lower()
        title_l = title.lower()
        trusted_source = contains_any_keyword(source_l, CURATED_MEDIA_TRUSTED_SOURCE_KEYWORDS)
        research_source = contains_any_keyword(source_l, CURATED_MEDIA_RESEARCH_SOURCE_KEYWORDS)
        title_has_ai = contains_meaningful_ai_signal(title_l)
        title_has_broad_ai = contains_any_keyword(title_l, list(BROAD_AI_TERMS)) or EN_SIGNAL_RE.search(title_l) is not None
        title_has_research = contains_any_keyword(title_l, CURATED_MEDIA_RESEARCH_TERMS)

        if research_source and not (title_has_ai or title_has_research):
            return _result(
                is_ai_related=False,
                score=0.22,
                label="source_scope_drop",
                reason="curated_research_source_requires_research_or_ai_title_signal",
                signals=ai_signals + tech_signals,
                noise=noise,
            )

        if not (trusted_source or research_source or title_has_ai or (title_has_broad_ai and bool(tech_signals))):
            return _result(
                is_ai_related=False,
                score=source_prior + (0.28 if title_has_broad_ai else 0.0),
                label="source_scope_drop",
                reason="curated_media_requires_ai_title_or_trusted_ai_feed",
                signals=ai_signals + tech_signals,
                noise=noise,
            )

        if research_source or title_has_research:
            label = "research_paper"
        elif contains_any_keyword(title_l, CURATED_MEDIA_BUSINESS_TERMS):
            label = "industry_business"
        else:
            label = _label_for_text(text, bool(tech_signals))
        base = 0.58 if trusted_source else 0.5
        score = source_prior + base + min(0.12, 0.03 * len(ai_signals)) + min(0.08, 0.02 * len(tech_signals))
        if research_source:
            score = min(score, 0.76)
        if noise and not title_has_ai:
            score -= min(0.16, 0.04 * len(noise))
        return _result(
            is_ai_related=score >= AI_RELEVANCE_THRESHOLD,
            score=score,
            label=label,
            reason="curated_media_source_filter",
            signals=ai_signals + tech_signals or ([source_l] if trusted_source else []),
            noise=noise,
        )

    if site_id in AI_DEFAULT_SOURCES:
        return _result(
            is_ai_related=True,
            score=max(AI_RELEVANCE_THRESHOLD, 0.72 + source_prior),
            label=_label_for_text(text, bool(tech_signals)),
            reason="trusted_ai_source_default_keep",
            signals=ai_signals or [site_id],
            noise=noise,
        )

    has_ai = contains_meaningful_ai_signal(text) or any(k not in BROAD_AI_TERMS for k in ai_signals)
    has_broad_ai = contains_any_keyword(text, list(BROAD_AI_TERMS)) or EN_SIGNAL_RE.search(text) is not None
    has_tech = bool(tech_signals)

    if not (has_ai or (has_broad_ai and has_tech)):
        return _result(
            is_ai_related=False,
            score=source_prior + (0.32 if has_broad_ai else 0.0) + (0.08 if has_tech else 0.0),
            label="not_ai",
            reason="missing_meaningful_ai_signal",
            signals=ai_signals + tech_signals,
            noise=noise,
        )

    if contains_any_keyword(text, COMMERCE_NOISE_KEYWORDS) and not has_ai:
        return _result(
            is_ai_related=False,
            score=0.25 + source_prior,
            label="commerce_noise",
            reason="commerce_noise_without_strong_ai_signal",
            signals=ai_signals + tech_signals,
            noise=noise,
        )

    if contains_any_keyword(text, NOISE_KEYWORDS) and not has_ai:
        return _result(
            is_ai_related=False,
            score=0.25 + source_prior,
            label="noise",
            reason="noise_without_strong_ai_signal",
            signals=ai_signals + tech_signals,
            noise=noise,
        )

    score = source_prior + (0.52 if has_ai else 0.34) + min(0.18, 0.04 * len(ai_signals)) + min(0.12, 0.03 * len(tech_signals))
    if noise:
        score -= min(0.18, 0.04 * len(noise))
    if has_broad_ai and has_tech and not has_ai:
        score = max(score, AI_RELEVANCE_THRESHOLD)
    if has_ai:
        score = max(score, AI_RELEVANCE_THRESHOLD)

    return _result(
        is_ai_related=True,
        score=score,
        label=_label_for_text(text, has_tech),
        reason="matched_ai_signal" if has_ai else "matched_broad_ai_plus_tech_signal",
        signals=ai_signals + tech_signals,
        noise=noise,
    )


def is_ai_related_record(record: dict[str, Any]) -> bool:
    return bool(score_ai_relevance(record)["is_ai_related"])


def add_ai_relevance_fields(record: dict[str, Any]) -> dict[str, Any]:
    relevance = score_ai_relevance(record)
    out = dict(record)
    out["ai_is_related"] = relevance["is_ai_related"]
    out["ai_score"] = relevance["score"]
    out["ai_label"] = relevance["label"]
    out["ai_relevance_reason"] = relevance["reason"]
    out["ai_signals"] = relevance["signals"]
    out["ai_noise"] = relevance["noise"]
    return out
