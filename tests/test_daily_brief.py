from __future__ import annotations

from datetime import datetime, timedelta, timezone

from scripts.update_news import (
    add_source_tier_fields,
    build_daily_brief_payload,
    calculate_item_importance,
    merge_story_items,
)


NOW = datetime(2026, 6, 2, 12, 0, tzinfo=timezone.utc)


def make_item(
    idx: int,
    *,
    site_id: str = "official_ai",
    title: str | None = None,
    hours_ago: int = 1,
    ai_score: float = 0.9,
) -> dict:
    item = {
        "id": f"item-{idx}",
        "site_id": site_id,
        "site_name": site_id.replace("_", " ").title(),
        "source": "Test Feed",
        "title": title or f"OpenAI ships Codex data pipeline update {idx}",
        "url": f"https://example.com/news/{idx}",
        "published_at": (NOW - timedelta(hours=hours_ago)).isoformat().replace("+00:00", "Z"),
        "ai_is_related": True,
        "ai_score": ai_score,
    }
    return add_source_tier_fields(item)


def test_importance_score_favors_official_relevant_recent_items():
    official = make_item(1, site_id="official_ai", hours_ago=1, ai_score=0.95)
    discussion = make_item(2, site_id="tophub", hours_ago=20, ai_score=0.65)

    official_score = calculate_item_importance(official, NOW, 24)["score"]
    discussion_score = calculate_item_importance(discussion, NOW, 24)["score"]

    assert official_score > discussion_score


def test_daily_brief_respects_10_to_20_cap_when_enough_stories_exist():
    items = [make_item(i, title=f"OpenAI releases distinct model platform update {i}") for i in range(25)]
    stories, _events = merge_story_items(items, NOW, 24, title_threshold=1.1)

    payload = build_daily_brief_payload(stories, generated_at="2026-06-02T12:00:00Z", window_hours=24)

    assert len(stories) == 25
    assert payload["total_items"] == 20
    assert len(payload["items"]) == 20


def test_daily_brief_records_include_score_label_primary_item_and_sources():
    items = [
        make_item(1, title="OpenAI releases Codex agent orchestration"),
        make_item(2, site_id="aihot", title="OpenAI releases Codex agent orchestration", ai_score=0.86),
    ]
    stories, events = merge_story_items(items, NOW, 24)

    payload = build_daily_brief_payload(stories, generated_at="2026-06-02T12:00:00Z", window_hours=24)
    record = payload["items"][0]

    assert events
    assert record["importance_score"] > 0
    assert record["importance_label"]
    assert record["primary_item"]["id"] == "item-1"
    assert record["primary_item"]["title"]
    assert record["primary_item"]["url"]
    assert len(record["sources"]) == 2
