from __future__ import annotations

from datetime import datetime, timedelta, timezone

from scripts.update_news import add_source_tier_fields, enrich_source_health_statuses, merge_story_items


NOW = datetime(2026, 6, 2, 12, 0, tzinfo=timezone.utc)


def make_item(idx: int, *, site_id: str, title: str, ai_score: float = 0.9) -> dict:
    item = {
        "id": f"item-{idx}",
        "site_id": site_id,
        "site_name": site_id.title(),
        "source": "Test Feed",
        "title": title,
        "url": f"https://example.com/{idx}",
        "published_at": (NOW - timedelta(hours=idx)).isoformat().replace("+00:00", "Z"),
        "ai_is_related": ai_score >= 0.65,
        "ai_score": ai_score,
    }
    return add_source_tier_fields(item)


def test_source_status_enrichment_returns_non_empty_sane_metrics():
    statuses = [
        {"site_id": "official_ai", "site_name": "Official AI", "ok": True, "item_count": 2},
        {"site_id": "tophub", "site_name": "TopHub", "ok": True, "item_count": 1},
        {"site_id": "broken", "site_name": "Broken", "ok": False, "item_count": 0},
    ]
    items = [
        make_item(1, site_id="official_ai", title="OpenAI releases Codex model update"),
        make_item(2, site_id="official_ai", title="OpenAI releases Codex model update"),
        make_item(3, site_id="tophub", title="OpenAI releases Codex model update", ai_score=0.7),
    ]
    stories, _events = merge_story_items(items, NOW, 24)

    enriched = enrich_source_health_statuses(statuses, items, stories)

    by_site = {row["site_id"]: row for row in enriched}
    official = by_site["official_ai"]
    assert official["source_tier"] == "official"
    assert official["source_type"] == "official"
    assert official["source_tier_label"]
    assert official["source_type_label"]
    assert official["health_status"] == "healthy"
    assert official["items_24h"] == 2

    for row in enriched:
        for key in ("ai_relevance_rate", "duplicate_rate", "unique_coverage", "trust_score"):
            assert 0.0 <= row[key] <= 1.0
        assert row["health_status"]

    assert by_site["broken"]["health_status"] == "failed"
