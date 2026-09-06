"""Shared LLM provider resolution for the AI News Radar pipeline.

The pipeline's chat-completions features (persona scoring, title
enhancement, zh translation, recommend-reason generation) all speak the same
OpenAI-compatible endpoint. DeepSeek is the default upstream. Setting
``ORCAROUTER_API_KEY`` switches those features to OrcaRouter, an
OpenAI-compatible AI gateway that exposes the same endpoint while routing
each request across many upstream models behind it.

Keeping this in one module means every call site resolves the provider the
same way, so both ``update_news.py`` and the standalone ``persona_score.py``
stay consistent.
"""

from __future__ import annotations

import os

DEEPSEEK_API_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_DEFAULT_MODEL = "deepseek-v4-flash"

ORCAROUTER_API_BASE_URL = "https://api.orcarouter.ai/v1"
ORCAROUTER_DEFAULT_MODEL = "orcarouter/auto"


def resolve_llm_config(default_model: str | None = None) -> dict:
    """Resolve which provider the LLM features talk to.

    OrcaRouter is used when ``ORCAROUTER_API_KEY`` is set; otherwise the
    pipeline falls back to DeepSeek, preserving current behavior. Returns a
    dict with ``api_key``, ``base_url`` and ``model`` keys, all safe to pass
    straight into a chat-completions request. ``default_model`` overrides the
    DeepSeek fallback model for callers that historically used a different
    default (e.g. ``persona_score.py``).
    """
    orca_key = str(os.environ.get("ORCAROUTER_API_KEY") or "").strip()
    if orca_key:
        return {
            "api_key": orca_key,
            "base_url": (
                str(os.environ.get("ORCAROUTER_API_BASE_URL") or "").strip().rstrip("/")
                or ORCAROUTER_API_BASE_URL
            ),
            "model": (
                str(os.environ.get("ORCAROUTER_MODEL") or "").strip()
                or ORCAROUTER_DEFAULT_MODEL
            ),
        }
    return {
        "api_key": str(os.environ.get("DEEPSEEK_API_KEY") or "").strip(),
        "base_url": (
            str(os.environ.get("DEEPSEEK_API_BASE_URL") or "").strip().rstrip("/")
            or DEEPSEEK_API_BASE_URL
        ),
        "model": (
            str(os.environ.get("DEEPSEEK_MODEL") or "").strip()
            or default_model
            or DEEPSEEK_DEFAULT_MODEL
        ),
    }


def llm_api_key_available() -> bool:
    """True when either the DeepSeek or OrcaRouter key is configured.

    Used by pipeline gates that decide whether to spend LLM budget (and, in
    the translation path, whether a Google-cache title can stand in for a
    stale DeepSeek translation).
    """
    return bool(
        str(os.environ.get("DEEPSEEK_API_KEY") or "").strip()
        or str(os.environ.get("ORCAROUTER_API_KEY") or "").strip()
    )
