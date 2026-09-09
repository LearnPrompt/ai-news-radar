from datetime import datetime, timezone
from pathlib import Path

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
    assert incident["title_zh"] == "OpenAI 服务错误率升高"
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


def test_severity_then_latest_update_determine_order():
    now = datetime(2026, 9, 9, tzinfo=UTC)
    incidents = [
        {"id": "minor", "name": "Minor", "status": "investigating", "impact": "minor"},
        {"id": "older", "name": "Older", "status": "identified", "impact": "major", "updated_at": "2026-09-08T00:00:00Z"},
        {"id": "newer", "name": "Newer", "status": "monitoring", "impact": "major", "updated_at": "2026-09-09T00:00:00Z"},
        {"id": "done", "name": "Done", "status": "resolved", "impact": "critical"},
        None,
    ]
    result = build_openai_service_status_payload({"incidents": incidents}, now)
    assert [item["id"] for item in result["incidents"]] == ["newer", "older", "minor"]


def test_invalid_api_response_is_not_reported_as_healthy():
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return ["unexpected"]

    class Session:
        def get(self, *args, **kwargs):
            return Response()

    result = fetch_service_status(Session(), datetime(2026, 9, 9, tzinfo=UTC))
    assert result["ok"] is False


def test_both_pages_load_existing_shared_assets_and_preserve_domain():
    root = Path(__file__).resolve().parents[1]
    for name, prefix in (("index.html", "./"), ("classic/index.html", "../")):
        source = (root / name).read_text()
        assert source.count('id="serviceStatusPanel"') == 1
        assert f'{prefix}assets/service-status.js?v=20260909' in source
        assert f'{prefix}assets/service-status.css?v=20260909' in source
        assert 'https://news.learnprompt.pro/' in source
        assert '1625517181-jpg' not in source
    assert (root / 'CNAME').read_text().strip() == 'news.learnprompt.pro'
