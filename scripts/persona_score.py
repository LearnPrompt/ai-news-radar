#!/usr/bin/env python3
"""Persona scoring for the daily brief.

Reads ``{data-dir}/daily-brief.json`` produced by ``update_news.py``, scores
each item with a persona-flavored LLM call (DeepSeek), writes the persona
fields back into ``daily-brief.json``, and generates a multi-persona TOP3
review file ``{data-dir}/top3-personas.json``.

Design constraints:

- Standalone: communicates with the rest of the pipeline only through JSON
  files. Never imports ``update_news.py``.
- Zero new dependencies: standard library plus ``requests``.
- Runs without any API key: falls back to a rules-based score derived from
  ``importance_score`` so the public repo stays runnable key-free.
- Exit code is always 0 except for argument errors or corrupted input JSON.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

try:
    from scripts.llm_provider import resolve_llm_config
except ModuleNotFoundError:  # pragma: no cover - direct `python scripts/persona_score.py`
    from llm_provider import resolve_llm_config

DEFAULT_MODEL = "deepseek-chat"
CACHE_VERSION = 1
CACHE_MAX_AGE_DAYS = 21
REVIEW_MAX_CHARS = 60
RETRY_BACKOFF_SECONDS = 2.0

ITEM_CONTEXT_FIELDS = (
    "story_id",
    "title",
    "url",
    "importance_score",
    "importance_label",
    "category",
    "reasons",
    "source_count",
)

PERSONA_ID_RE = re.compile(r"^[a-z-]+$")
CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
WHITESPACE_RE = re.compile(r"\s+")


class PersonaError(Exception):
    """Raised for invalid persona files."""


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse a ``---`` delimited frontmatter block of simple ``key: value`` lines.

    Returns (metadata dict, body). Raises PersonaError when the block is
    missing or malformed.
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        raise PersonaError("missing frontmatter opening '---'")
    meta: dict = {}
    end_index = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_index = i
            break
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            raise PersonaError(f"invalid frontmatter line: {line!r}")
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()
        if value.lower() in {"true", "false"}:
            meta[key] = value.lower() == "true"
        else:
            meta[key] = value
    if end_index is None:
        raise PersonaError("missing frontmatter closing '---'")
    body = "\n".join(lines[end_index + 1 :]).strip()
    return meta, body


def load_personas(personas_dir: Path) -> list[dict]:
    """Load persona definitions from ``personas_dir``.

    Each persona is a dict: id, name, name_en, default, prompt, sha8 (first 8
    hex chars of the sha1 of the full file text).
    """
    personas = []
    if not personas_dir.is_dir():
        return personas
    for path in sorted(personas_dir.glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        text = path.read_text(encoding="utf-8")
        try:
            meta, body = parse_frontmatter(text)
        except PersonaError as exc:
            print(f"persona: skipping {path.name}: {exc}", file=sys.stderr)
            continue
        persona_id = str(meta.get("id", "")).strip()
        if not PERSONA_ID_RE.match(persona_id):
            print(
                f"persona: skipping {path.name}: invalid id {persona_id!r}",
                file=sys.stderr,
            )
            continue
        personas.append(
            {
                "id": persona_id,
                "name": str(meta.get("name", persona_id)),
                "name_en": str(meta.get("name_en", persona_id)),
                "default": bool(meta.get("default", False)),
                "prompt": body,
                "sha8": hashlib.sha1(text.encode("utf-8")).hexdigest()[:8],
            }
        )
    return personas


def pick_default_persona(personas: list[dict]) -> dict | None:
    for persona in personas:
        if persona.get("default"):
            return persona
    return personas[0] if personas else None


def sanitize_review(review: str) -> str:
    review = CONTROL_CHARS_RE.sub("", str(review))
    review = WHITESPACE_RE.sub(" ", review).strip()
    return review[:REVIEW_MAX_CHARS]


def clamp_score(value) -> int:
    try:
        score = int(round(float(value)))
    except (TypeError, ValueError):
        score = 0
    return max(0, min(100, score))


def title_hash(title: str) -> str:
    return hashlib.sha1(str(title).encode("utf-8")).hexdigest()[:8]


def cache_key(story_id: str, persona: dict) -> str:
    return f"{story_id}|{persona['id']}|{persona['sha8']}"


def load_cache(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return {"version": CACHE_VERSION, "entries": {}}
    if not isinstance(data, dict) or data.get("version") != CACHE_VERSION:
        return {"version": CACHE_VERSION, "entries": {}}
    entries = data.get("entries")
    if not isinstance(entries, dict):
        entries = {}
    return {"version": CACHE_VERSION, "entries": entries}


def prune_cache(cache: dict, now: datetime) -> None:
    cutoff = now - timedelta(days=CACHE_MAX_AGE_DAYS)
    kept = {}
    for key, entry in cache.get("entries", {}).items():
        if not isinstance(entry, dict):
            continue
        scored_at = entry.get("scored_at")
        try:
            when = datetime.fromisoformat(str(scored_at).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if when >= cutoff:
            kept[key] = entry
    cache["entries"] = kept


def save_cache(path: Path, cache: dict, now: datetime) -> None:
    prune_cache(cache, now)
    path.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def build_item_context(item: dict) -> dict:
    context = {}
    for field in ITEM_CONTEXT_FIELDS:
        if field in item:
            context[field] = item[field]
    sources = item.get("sources")
    if isinstance(sources, list):
        context["sources"] = [
            {"source": src.get("source")}
            for src in sources
            if isinstance(src, dict) and src.get("source")
        ]
    return context


def call_persona_api(
    persona: dict,
    item: dict,
    *,
    api_key: str,
    base_url: str,
    model: str,
    timeout: float,
) -> tuple[int, str] | None:
    """Call the DeepSeek chat completions API for one item with one persona.

    Retries once on failure (2s backoff). Returns (score, review) or None.
    """
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": persona["prompt"]},
            {
                "role": "user",
                "content": json.dumps(build_item_context(item), ensure_ascii=False),
            },
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.3,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    last_error = None
    for attempt in range(2):
        if attempt:
            time.sleep(RETRY_BACKOFF_SECONDS)
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=timeout)
            if response.status_code == 429:
                last_error = "rate limited (429)"
                continue
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            score = clamp_score(parsed.get("score"))
            review = sanitize_review(parsed.get("review", ""))
            if not review:
                last_error = "empty review"
                continue
            return score, review
        except (requests.RequestException, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            last_error = str(exc)
            continue
    print(
        f"persona: {persona['id']} failed for {item.get('story_id')}: {last_error}",
        file=sys.stderr,
    )
    return None


def score_with_persona(
    persona: dict,
    item: dict,
    cache: dict,
    *,
    api_key: str,
    base_url: str,
    model: str,
    timeout: float,
    stats: dict,
) -> tuple[int, str] | None:
    """Score one item with one persona, using the cache when possible."""
    story_id = str(item.get("story_id", ""))
    key = cache_key(story_id, persona)
    thash = title_hash(item.get("title", ""))
    entry = cache["entries"].get(key)
    if isinstance(entry, dict) and entry.get("title_hash") == thash:
        stats["cached"] += 1
        return clamp_score(entry.get("score")), sanitize_review(entry.get("review", ""))
    result = call_persona_api(
        persona,
        item,
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout=timeout,
    )
    if result is None:
        stats["failed"] += 1
        return None
    score, review = result
    cache["entries"][key] = {
        "score": score,
        "review": review,
        "title_hash": thash,
        "scored_at": utcnow_iso(),
    }
    stats["scored"] += 1
    return score, review


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run_fallback(items: list[dict], default_persona: dict | None) -> None:
    persona_id = default_persona["id"] if default_persona else "pragmatic"
    scored_at = utcnow_iso()
    for item in items:
        item["persona_id"] = persona_id
        item["persona_score"] = clamp_score(item.get("importance_score", 0))
        item.pop("persona_review", None)
        item["persona_meta"] = {"mode": "rules_fallback", "scored_at": scored_at}


def build_top3_payload(
    items: list[dict],
    personas: list[dict],
    cache: dict,
    *,
    top3: int,
    api_key: str,
    base_url: str,
    model: str,
    timeout: float,
    stats: dict,
) -> dict:
    ranked = sorted(
        [item for item in items if "persona_score" in item],
        key=lambda it: (
            -float(it.get("persona_score", 0)),
            -float(it.get("importance_score", 0) or 0),
        ),
    )[:top3]
    top_items = []
    for rank, item in enumerate(ranked, start=1):
        reviews = {}
        for persona in personas:
            result = score_with_persona(
                persona,
                item,
                cache,
                api_key=api_key,
                base_url=base_url,
                model=model,
                timeout=timeout,
                stats=stats,
            )
            if result is None:
                continue
            score, review = result
            reviews[persona["id"]] = {"score": score, "review": review}
        top_items.append(
            {
                "story_id": item.get("story_id"),
                "title": item.get("title"),
                "url": item.get("url"),
                "rank": rank,
                "reviews": reviews,
            }
        )
    return {
        "generated_at": utcnow_iso(),
        "model": model,
        "personas": [{"id": p["id"], "name": p["name"]} for p in personas],
        "items": top_items,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Persona scoring for daily brief")
    parser.add_argument("--data-dir", default="data", help="data directory")
    parser.add_argument("--personas-dir", default="personas", help="personas directory")
    parser.add_argument("--max-items", type=int, default=40, help="max items to score")
    parser.add_argument("--top3", type=int, default=3, help="TOP N multi-persona items")
    parser.add_argument("--timeout", type=float, default=30, help="API timeout seconds")
    parser.add_argument(
        "--dry-run", action="store_true", help="run without writing any files"
    )
    parser.add_argument(
        "--list-personas", action="store_true", help="list personas and exit"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    personas_dir = Path(args.personas_dir)
    personas = load_personas(personas_dir)
    default_persona = pick_default_persona(personas)

    if args.list_personas:
        if not personas:
            print("persona: no personas found")
            return 0
        for persona in personas:
            marker = " (default)" if persona is default_persona else ""
            print(f"{persona['id']}\t{persona['name']} / {persona['name_en']}{marker}")
        return 0

    data_dir = Path(args.data_dir)
    brief_path = data_dir / "daily-brief.json"
    top3_path = data_dir / "top3-personas.json"
    cache_path = data_dir / "persona-cache.json"

    if not brief_path.is_file():
        print(f"persona: {brief_path} not found, nothing to do")
        print("persona: scored=0 cached=0 skipped=0 failed=0")
        return 0

    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    all_items = brief.get("items", [])
    if not isinstance(all_items, list):
        raise SystemExit(f"persona: {brief_path} has invalid 'items'")
    items = all_items[: args.max_items]
    skipped = len(all_items) - len(items)

    config = resolve_llm_config(default_model=DEFAULT_MODEL)
    api_key = config["api_key"]
    base_url = config["base_url"]
    model = config["model"]
    enabled = os.environ.get("PERSONA_ENABLED", "").strip() != "0"

    now = datetime.now(timezone.utc)
    stats = {"scored": 0, "cached": 0, "failed": 0}

    if not api_key or not enabled or default_persona is None:
        run_fallback(items, default_persona)
        top3_payload = {"generated_at": utcnow_iso(), "items": []}
        if not args.dry_run:
            brief_path.write_text(
                json.dumps(brief, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            top3_path.write_text(
                json.dumps(top3_payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        print(
            f"persona: scored=0 cached=0 skipped={skipped} failed=0"
        )
        return 0

    cache = load_cache(cache_path)
    scored_at = utcnow_iso()

    for item in items:
        result = score_with_persona(
            default_persona,
            item,
            cache,
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout=args.timeout,
            stats=stats,
        )
        if result is None:
            continue
        score, review = result
        item["persona_id"] = default_persona["id"]
        item["persona_score"] = score
        item["persona_review"] = review
        item["persona_meta"] = {
            "mode": "llm",
            "model": model,
            "scored_at": scored_at,
        }

    top3_payload = build_top3_payload(
        items,
        personas,
        cache,
        top3=args.top3,
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout=args.timeout,
        stats=stats,
    )

    if not args.dry_run:
        brief_path.write_text(
            json.dumps(brief, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        top3_path.write_text(
            json.dumps(top3_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        save_cache(cache_path, cache, now)

    print(
        "persona: scored={scored} cached={cached} skipped={skipped} failed={failed}".format(
            scored=stats["scored"],
            cached=stats["cached"],
            skipped=skipped,
            failed=stats["failed"],
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
