from datetime import datetime, timezone

from scripts.update_news import (
    build_openai_service_status_payload,
    fetch_service_status,
)


UTC = timezone.utc


def test_openai_service_status_keeps_only_active_incidents():
    now = datetime(2026, 7, 24, 9, 0, tzinfo=UTC)
    payload = {
        "incidents": [
            {
                "id": "active-1",
                "name": "Elevated Error Rates",
                "status": "monitoring",
                "impact": "minor",
                "created_at": "2026-07-23T15:36:02Z",
                "updated_at": "2026-07-23T20:22:47Z",
                "components": [{"name": "ChatGPT"}, {"name": "API"}],
                "incident_updates": [
                    {
                        "status": "monitoring",
                        "body": "We have applied the mitigation.",
                        "created_at": "2026-07-23T20:22:47Z",
                        "updated_at": "2026-07-23T20:22:47Z",
                    }
                ],
            },
            {
                "id": "resolved-1",
                "name": "Resolved incident",
                "status": "resolved",
                "impact": "minor",
                "created_at": "2026-07-23T10:00:00Z",
                "updated_at": "2026-07-23T11:00:00Z",
                "incident_updates": [],
            },
        ]
    }

    result = build_openai_service_status_payload(payload, now)

    assert result["ok"] is True
    assert result["active_count"] == 1
    assert len(result["incidents"]) == 1
    incident = result["incidents"][0]
    assert incident["title_zh"] == "ChatGPT 等 OpenAI 服务错误率升高"
    assert incident["status"] == "monitoring"
    assert incident["affected_components"] == ["API", "ChatGPT"]
    assert incident["url"].endswith("/incidents/active-1")


def test_service_status_failure_is_explicit_and_empty():
    class FailingSession:
        def get(self, *args, **kwargs):
            raise RuntimeError("network down")

    result = fetch_service_status(
        FailingSession(),
        datetime(2026, 7, 24, 9, 0, tzinfo=UTC),
    )

    assert result["ok"] is False
    assert result["active_count"] == 0
    assert result["incidents"] == []
    assert result["providers"][0]["ok"] is False
