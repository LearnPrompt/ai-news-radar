from datetime import datetime, timedelta, timezone

import pytest

from scripts import update_news
from scripts.project_sources import build_today_projects, parse_github_trending, parse_producthunt_feed


NOW = datetime(2026, 10, 9, 17, tzinfo=timezone.utc)


def project(sid="github_trending", index=0, **changes):
    host = "github.com/team" if sid == "github_trending" else "www.producthunt.com/products"
    return {
        "site_id": sid, "site_name": sid, "project_name": f"Project {index}",
        "url": f"https://{host}/project-{index}", "summary": "AI document search with local LLMs",
        "published_at": NOW - timedelta(hours=1) if sid == "producthunt" else None,
        "observed_at": NOW, "source_rank": index + 1, **changes,
    }


def test_trending_reads_real_description_and_observation_not_publication():
    html = '''<article class="Box-row"><h2><a href="/team/search">team / search</a></h2>
    <p> Local LLM <b>document search</b> </p><span>1,234 stars today</span></article>
    <article class="Box-row"><h2><a href="/team/search">duplicate</a></h2></article>
    <article class="Box-row"><h2><a href="https://evil.example/team/search">bad</a></h2></article>'''
    items = parse_github_trending(html, NOW)
    assert len(items) == 1
    assert items[0]["project_name"] == "team/search"
    assert items[0]["summary"] == "Local LLM document search"
    assert items[0]["stars_today"] == 1234
    assert items[0]["observed_at"] == NOW
    assert items[0]["published_at"] is None


def test_trending_markup_failure_does_not_look_like_healthy_zero():
    with pytest.raises(ValueError, match="no repository"):
        parse_github_trending("<html>Please sign in</html>", NOW)


def test_producthunt_uses_publication_not_updated_and_strips_footer():
    def entry(name, published, updated=NOW.isoformat(), link=None):
        return f'''<entry><title>{name}</title>
        <link href="{link or 'https://www.producthunt.com/products/' + name + '?utm_source=rss'}"/>
        <published>{published}</published><updated>{updated}</updated>
        <content type="html">&lt;p&gt;AI document search&lt;/p&gt;&lt;p&gt;&lt;a href="https://example.com"&gt;Discussion&lt;/a&gt; | &lt;a href="https://example.com"&gt;Link&lt;/a&gt;&lt;/p&gt;</content></entry>'''
    xml = '<feed xmlns="http://www.w3.org/2005/Atom">' + "".join([
        entry("fresh", "2026-10-09T09:00:00-07:00"),
        entry("old", "2026-07-06T01:40:40-07:00"),
        entry("future", "2026-10-10T00:00:00Z"),
        entry("missing", "unknown"),
        entry("unsafe", "2026-10-09T16:00:00Z", link="javascript:alert(1)"),
    ]) + '</feed>'
    items = parse_producthunt_feed(xml, NOW)
    assert len(items) == 1
    assert items[0]["project_name"] == "fresh"
    assert items[0]["summary"] == "AI document search"
    assert items[0]["url"] == "https://www.producthunt.com/products/fresh"
    assert items[0]["published_at"].hour == 16


def test_selection_balances_sources_and_uses_taipei_date():
    candidates = [project(index=i) for i in range(5)] + [project("producthunt", i) for i in range(5)]
    result = build_today_projects(candidates, NOW, [])
    assert result["date"] == "2026-10-10"
    assert result["total_items"] == 4
    assert [i["site_id"] for i in result["items"]] == ["github_trending", "producthunt"] * 2
    assert all(i["recommend_reason_zh"] for i in result["items"])
    assert result["items"][0]["published_at"] is None


def test_selection_fills_from_remaining_source_and_rejects_noise_and_stale():
    candidates = [project(index=i) for i in range(5)] + [
        project(index=10, summary="A finance calculator"),
        project(index=11, summary="AI NSFW virtual girlfriend"),
        project(index=12, summary=""),
        project(index=13, url="https://github.com@evil.example/team/tool"),
        project(index=14, observed_at=NOW - timedelta(days=2)),
        project(index=15, observed_at=NOW + timedelta(hours=1)),
        project("producthunt", 16, published_at=NOW - timedelta(days=3)),
        project(index=0, url=project()["url"] + "?utm_source=rss"),
    ]
    result = build_today_projects(candidates, NOW, [], limit=20)
    assert result["total_items"] == 5
    assert {i["project_name"] for i in result["items"]} == {f"Project {i}" for i in range(5)}


def test_recommendations_cache_by_content_and_do_not_cache_failure():
    calls = []
    def recommend(name, summary):
        calls.append(summary)
        return "用自己的文档试试它的 AI 检索能力。"
    cache = {}
    one = build_today_projects([project()], NOW, [], recommend=recommend, cache=cache)
    two = build_today_projects([project()], NOW, [], recommend=recommend, cache=cache)
    assert one["items"] == two["items"]
    assert len(calls) == 1
    build_today_projects([project(summary="AI speech transcription")], NOW, [], recommend=recommend, cache=cache)
    assert len(calls) == 2
    empty_cache = {}
    result = build_today_projects([project()], NOW, [], recommend=lambda *_: None, cache=empty_cache)
    assert not empty_cache
    assert "检索" in result["items"][0]["recommend_reason_zh"]
    unknown = build_today_projects([project(summary="AI tool for custom widgets")], NOW, [])
    assert "AI tool for custom widgets" in unknown["items"][0]["recommend_reason_zh"]


def test_source_failure_keeps_other_sources_and_module_working(monkeypatch):
    names = ["fetch_official_ai_updates", "fetch_curated_ai_media", "fetch_ai_breakfast", "fetch_follow_builders",
             "fetch_techurls", "fetch_buzzing", "fetch_iris", "fetch_bestblogs", "fetch_zeli",
             "fetch_hacker_news_algolia", "fetch_ai_hubtoday", "fetch_aibase", "fetch_aihot", "fetch_newsnow"]
    for name in names:
        monkeypatch.setattr(update_news, name, lambda *_: [])
    def fail(*_):
        raise ValueError("Trending unavailable")
    monkeypatch.setattr(update_news, "fetch_github_projects", fail)
    monkeypatch.setattr(update_news, "fetch_producthunt_projects", lambda *_: [project("producthunt")])
    raw, statuses = update_news.collect_all(None, NOW)
    status = {s["site_id"]: s for s in statuses}
    assert not status["github_trending"]["ok"]
    assert status["producthunt"]["ok"]
    assert "AI document search" in raw[0].title
    result = build_today_projects([r.meta["project_candidate"] for r in raw], NOW, statuses)
    assert result["total_items"] == 1
    assert len(result["sources"]) == 2


def test_main_writes_project_payload_with_news_outputs(tmp_path, monkeypatch):
    monkeypatch.setattr(update_news, "utc_now", lambda: NOW)
    monkeypatch.setattr(update_news, "collect_all", lambda *_: (update_news.project_raw_items([project()]), []))
    monkeypatch.setattr(update_news, "fetch_service_status", lambda *_: {})
    monkeypatch.setattr(update_news, "fetch_waytoagi_recent_7d", lambda *_: {"updates_7d": [], "updates_today": []})
    monkeypatch.setattr(update_news, "maybe_fetch_agentmail_digest", lambda *_, **kw: (None, {"enabled": False}))
    for name in ["maybe_fetch_x_api_updates", "maybe_fetch_socialdata_updates", "maybe_fetch_tikhub_updates"]:
        monkeypatch.setattr(update_news, name, lambda *_, **kw: ([], {"enabled": False}))
    monkeypatch.setattr(update_news, "add_title_enhancements", lambda items, session, cache: (items, cache))
    monkeypatch.setattr(update_news, "add_recommend_reasons", lambda items, session, cache: (items, cache))
    monkeypatch.setattr(update_news, "recommend_project", lambda *_, **kw: None)
    monkeypatch.setattr("sys.argv", ["update_news.py", "--output-dir", str(tmp_path), "--translate-max-new", "0", "--translate-max-new-broad", "0"])
    assert update_news.main() == 0
    import json
    payload = json.loads((tmp_path / "today-projects.json").read_text())
    assert payload["total_items"] == 1
    assert payload["items"][0]["project_name"] == "Project 0"
    assert (tmp_path / "latest-24h.json").exists()


def test_project_copy_uses_action_prompt_and_rejects_multiple_sentences(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only")
    sent = []
    class Response:
        status_code = 200
        def json(self):
            return {"choices": [{"message": {"content": response_text[0]}}]}
    def post(*args, **kwargs):
        sent.append(kwargs["json"])
        return Response()
    monkeypatch.setattr(update_news.requests, "post", post)
    response_text = ["用一份自己的资料试试它的检索能力。"]
    result = update_news.recommend_project("Search", "AI document search", None)
    assert result == response_text[0]
    assert "今天值得做" in sent[0]["messages"][0]["content"]
    assert "AI document search" in sent[0]["messages"][1]["content"]
    response_text[0] = "这是一个检索项目。你还可以做其他事情。"
    assert update_news.recommend_project("Search", "AI document search", None) is None


def test_copy_generation_exception_falls_back_without_stopping_selection():
    def broken(*_):
        raise RuntimeError("model unavailable")
    result = build_today_projects([project()], NOW, [], recommend=broken)
    assert result["total_items"] == 1
    assert "检索" in result["items"][0]["recommend_reason_zh"]
