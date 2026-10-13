#!/usr/bin/env python3
"""One-off backfill of the English-edition (/en) fields into the existing data files.

Reads data/latest-24h.json, latest-24h-all.json, stories-merged.json,
daily-brief.json and today-projects.json, fills ``en`` (and the project
``recommend_reason_en``) in place using the same add_en_fields / en-cache.json
the hourly pipeline uses, and writes the files back with the pipeline's own JSON
formatting. Creator (Douyin / Xiaohongshu) items are skipped.

Needs DEEPSEEK_API_KEY (export it locally, or run via workflow_dispatch).
``--dry-run`` calls nothing and needs no key: it only prints how many
DeepSeek calls each kind would take.

    python scripts/backfill_en.py --dry-run
    DEEPSEEK_API_KEY=... python scripts/backfill_en.py --max-new 300
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

try:
    from scripts.project_sources import project_reason_cache_key, project_reason_en
    from scripts.update_news import (
        EN_CACHE_FILENAME,
        add_en_fields,
        count_en_calls,
        load_en_cache,
        load_title_zh_cache,
        recommend_project_en,
        sanitize_public_payload,
        save_en_cache,
        utc_now,
    )
except ModuleNotFoundError:  # direct execution: python scripts/backfill_en.py
    from project_sources import project_reason_cache_key, project_reason_en
    from update_news import (
        EN_CACHE_FILENAME,
        add_en_fields,
        count_en_calls,
        load_en_cache,
        load_title_zh_cache,
        recommend_project_en,
        sanitize_public_payload,
        save_en_cache,
        utc_now,
    )

import requests

DATA_FILES = (
    "latest-24h.json",
    "latest-24h-all.json",
    "stories-merged.json",
    "daily-brief.json",
    "today-projects.json",
)


def _is_dict_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(x, dict) for x in value)


def collect_item_refs(name: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Live references to every item dict that should carry ``en`` in this file
    (de-duplicated by identity; creator pools are not touched)."""
    refs: list[dict[str, Any]] = []
    seen: set[int] = set()

    def add(d: Any) -> None:
        if isinstance(d, dict) and id(d) not in seen:
            seen.add(id(d))
            refs.append(d)

    if name == "latest-24h.json":
        for key in ("items", "items_ai"):
            for d in payload.get(key) or []:
                add(d)
    elif name == "latest-24h-all.json":
        for key in ("items_all", "items_all_raw"):
            for d in payload.get(key) or []:
                add(d)
    elif name in ("stories-merged.json", "daily-brief.json"):
        stories = payload.get("stories") if name == "stories-merged.json" else payload.get("items")
        for story in stories or []:
            if not isinstance(story, dict):
                continue
            add(story.get("primary_item"))
            for key in ("sources", "items"):
                for d in story.get(key) or []:
                    add(d)
    return refs


def project_refs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [d for d in payload.get("items") or [] if isinstance(d, dict)]


def dump_like(original_text: str, payload: dict[str, Any]) -> str:
    """Serialize like the pipeline: indent=2 when the file was pretty-printed,
    compact separators otherwise; trailing newline preserved."""
    pretty = "\n" in original_text.strip()
    clean = sanitize_public_payload(payload)
    if pretty:
        text = json.dumps(clean, ensure_ascii=False, indent=2)
    else:
        text = json.dumps(clean, ensure_ascii=False, separators=(",", ":"))
    if original_text.endswith("\n"):
        text += "\n"
    return text


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Backfill English-edition fields into data/*.json")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--max-new", type=int, default=300, help="Max new DeepSeek calls this run (default 300)")
    ap.add_argument("--dry-run", action="store_true", help="Print would-be call counts per kind; call nothing, write nothing")
    args = ap.parse_args(argv)

    data_dir = Path(args.data_dir)
    now = utc_now()
    en_cache_path = data_dir / EN_CACHE_FILENAME
    title_cache_path = data_dir / "title-zh-cache.json"
    en_cache = load_en_cache(en_cache_path)

    loaded: dict[str, tuple[str, dict[str, Any]]] = {}
    for name in DATA_FILES:
        path = data_dir / name
        if not path.exists():
            print(f"skip (missing): {path}")
            continue
        text = path.read_text(encoding="utf-8")
        loaded[name] = (text, json.loads(text))

    if args.dry_run:
        total = {"title": 0, "summary": 0, "reason": 0, "project": 0}
        title_cache = load_title_zh_cache(title_cache_path)
        # 同一条目会出现在多个文件里（items / stories / daily-brief），缓存 key 相同只算一次调用
        dedup: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        for name, (_, payload) in loaded.items():
            if name == "today-projects.json":
                continue
            for d in collect_item_refs(name, payload):
                dedup[(
                    str(d.get("url") or ""),
                    str(d.get("title_original") or d.get("title") or ""),
                    str(d.get("summary") or ""),
                    str(d.get("recommend_reason_zh") or ""),
                )] = d
        for kind, n in count_en_calls(list(dedup.values()), en_cache, now).items():
            total[kind] = n
        projects = loaded.get("today-projects.json")
        if projects:
            for d in project_refs(projects[1]):
                if d.get("recommend_reason_en"):
                    continue
                key = project_reason_cache_key(d.get("url", ""), d.get("summary", ""), "en")
                if not title_cache.get(key):
                    total["project"] += 1
        grand = sum(total.values())
        print("dry-run: no DeepSeek calls made, nothing written")
        for kind in ("title", "summary", "reason", "project"):
            print(f"  {kind}: {total[kind]} calls")
        print(f"  total: {grand} calls (cap per run: --max-new {args.max_new})")
        return 0

    if not str(os.environ.get("DEEPSEEK_API_KEY") or "").strip():
        print("DEEPSEEK_API_KEY is not set; nothing to do (use --dry-run to preview call counts)")
        return 0

    session = requests.Session()
    budget = max(0, args.max_new)
    used_total = 0
    title_cache = load_title_zh_cache(title_cache_path)
    title_cache_dirty = False

    try:
        for name, (original_text, payload) in loaded.items():
            if name == "today-projects.json":
                continue
            refs = collect_item_refs(name, payload)
            new_items, en_cache, used = add_en_fields(refs, en_cache, budget - used_total, now)
            used_total += used
            for orig, new in zip(refs, new_items):
                if "en" in new:
                    orig["en"] = new["en"]
            new_text = dump_like(original_text, payload)
            if new_text != original_text:
                (data_dir / name).write_text(new_text, encoding="utf-8")
            print(f"{name}: {len(refs)} items, {used} new calls")

        projects = loaded.get("today-projects.json")
        if projects:
            original_text, payload = projects
            for d in project_refs(payload):
                if d.get("recommend_reason_en"):
                    continue
                before = len(title_cache)
                key = project_reason_cache_key(d.get("url", ""), d.get("summary", ""), "en")
                needs_call = not title_cache.get(key)
                if needs_call and used_total >= budget:
                    continue
                if needs_call:
                    used_total += 1
                d["recommend_reason_en"] = project_reason_en(
                    {k: d.get(k) for k in ("project_name", "url", "summary", "site_id")},
                    lambda name_, summary_: recommend_project_en(name_, summary_, session),
                    title_cache,
                )
                title_cache_dirty = title_cache_dirty or len(title_cache) != before
            new_text = dump_like(original_text, payload)
            if new_text != original_text:
                (data_dir / "today-projects.json").write_text(new_text, encoding="utf-8")
            print("today-projects.json: projects filled")
    finally:
        save_en_cache(en_cache_path, en_cache, now)
        if title_cache_dirty:
            title_cache_path.write_text(
                json.dumps(sanitize_public_payload(title_cache), ensure_ascii=False, indent=2), encoding="utf-8"
            )
    print(f"done: {used_total} new DeepSeek calls (cap {args.max_new}); cache -> {en_cache_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
