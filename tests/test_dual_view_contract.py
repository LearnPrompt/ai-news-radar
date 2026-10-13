"""Regression checks for the mobile/classic data and safety contract (plus the /en surface)."""

import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_FILES = (
    "latest-24h.json",
    "latest-24h-all.json",
    "waytoagi-7d.json",
    "source-status.json",
    "daily-brief.json",
    "stories-merged.json",
    "today-projects.json",
)


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


# 静态页面里写死的串从词条取，避免三份 HTML 与 i18n JSON 各说各话
ZH = json.loads(read("assets/i18n/zh.json"))
EN = json.loads(read("assets/i18n/en.json"))


def test_both_views_share_data_source_override_contract():
    for path in ("assets/app.js", "classic/assets/app.js"):
        source = read(path)
        assert 'get("data")' in source
        assert 'localStorage.getItem("dataBaseUrl")' in source
        assert "function dataUrl(path)" in source
        for filename in DATA_FILES:
            assert filename in source


def test_view_router_preserves_data_parameter_between_surfaces():
    source = read("assets/view-mode.js")
    assert 'passthrough.delete("view")' in source
    assert 'passthrough.delete("data")' not in source


def test_both_views_apply_same_last_mile_content_safety_gate():
    for path in ("assets/app.js", "classic/assets/app.js"):
        source = read(path)
        assert "UNSAFE_HARD_PATTERNS" in source
        assert "UNSAFE_PROMO_PATTERNS" in source
        assert "function safeItems(items)" in source
        assert "function isUnsafeStory(story)" in source


def test_both_pages_expose_bidirectional_view_switch():
    for path in ("index.html", "classic/index.html"):
        source = read(path)
        assert 'data-radar-view-target="mobile"' in source
        assert 'data-radar-view-target="classic"' in source
        assert "assets/view-mode.js" in source


def test_view_switch_follows_update_time_in_both_headers():
    for path in ("index.html", "classic/index.html"):
        source = read(path)
        updated_position = source.index('id="updatedAt"')
        switch_position = source.index('class="view-switch"')
        status_position = source.index('id="sourceStatusPill"')

        assert updated_position < switch_position < status_position
        assert 'class="view-toolbar"' not in source


def test_both_headers_keep_time_and_switch_inside_the_headline():
    for path in ("index.html", "classic/index.html"):
        source = read(path)
        headline_position = source.index('class="hero-headline"')
        updated_position = source.index('id="updatedAt"')
        switch_position = source.index('class="view-switch"')
        meta_position = source.index('class="hero-meta"')

        assert headline_position < updated_position < switch_position < meta_position
        assert 'class="hero-tag"' not in source
        assert f">{ZH['page.githubLink']}</a>" in source


def test_classic_header_does_not_animate_the_view_switch_container():
    source = read("classic/assets/motion.js")

    assert 'addFrom(".hero-headline"' not in source
    assert 'addFrom(".hero-meta"' not in source


def test_mobile_is_the_versioned_default_view():
    source = read("assets/view-mode.js")

    assert 'const STORAGE_KEY = "aiNewsRadarViewV2"' in source
    assert 'const LEGACY_STORAGE_KEY = "aiNewsRadarView"' in source
    assert 'const MOBILE_OVERRIDE_KEY = "aiNewsRadarMobileViewOnce"' in source
    assert 'const MOBILE_BREAKPOINT = "(max-width: 760px)"' in source
    assert "const isMobileViewport = window.matchMedia(MOBILE_BREAKPOINT).matches" in source
    assert 'const mobileOverride = isMobileViewport ? readMobileOverride() : ""' in source
    assert "const preference = isMobileViewport" in source
    assert "? mobileOverride" in source
    assert 'const deviceDefault = "mobile"' in source


def test_mobile_classic_choice_is_one_navigation_only():
    source = read("assets/view-mode.js")

    assert "function readMobileOverride()" in source
    assert "window.sessionStorage.removeItem(MOBILE_OVERRIDE_KEY)" in source
    assert "function writeMobileOverride(view)" in source
    assert "writeMobileOverride(view)" in source


def test_both_views_show_today_projects_after_news():
    for path in ("index.html", "classic/index.html"):
        source = read(path)
        assert f'id="todayProjectsTitle">{ZH["page.todayProjectsTitle"]}' in source
        assert 'id="todayProjectsList"' in source
        assert source.index('id="newsList"') < source.index('id="todayProjectsWrap"')
        from bs4 import BeautifulSoup
        main_sections = BeautifulSoup(source, "html.parser").select("main > section")
        assert main_sections[-1].get("id") == "todayProjectsWrap"


def test_today_projects_load_independently_in_both_views():
    for path in ("assets/app.js", "classic/assets/app.js"):
        source = read(path)
        assert "initTodayProjects();\ninit();" in source
        init_source = source[source.index("async function init()") :]
        assert "await initTodayProjects" not in init_source
        assert 'timeZone: "Asia/Taipei"' in source


def test_zh_page_declares_hreflang_rss_and_loads_i18n_before_app():
    source = read("index.html")
    assert 'hreflang="zh-CN" href="https://news.learnprompt.pro/"' in source
    assert 'hreflang="en" href="https://news.learnprompt.pro/en"' in source
    assert 'hreflang="x-default" href="https://news.learnprompt.pro/"' in source
    assert 'type="application/rss+xml"' in source
    assert source.index("assets/i18n/zh.js") < source.index("assets/i18n.js") < source.index("assets/app.js")
    assert source.index("assets/i18n.js") < source.index("assets/service-status.js")


def test_english_page_is_the_mobile_view_rooted_at_en():
    source = read("en/index.html")
    assert '<html lang="en"' in source
    assert 'data-root="/en/"' in source
    assert 'src="/assets/view-mode.js' in source
    assert source.index("/assets/i18n/en.js") < source.index("/assets/i18n.js") < source.index("/assets/app.js")
    # all local resources are absolute: the page is served from /en, so "./" would 404
    assert 'src="./' not in source and 'href="./' not in source
    assert 'href="/site.webmanifest"' in source


def test_english_page_has_no_classic_entry_and_no_view_switch():
    source = read("en/index.html")
    assert "data-radar-view-target" not in source
    assert "classic" not in source.lower()
    assert 'class="view-switch"' not in source


def test_english_page_declares_hreflang_canonical_and_rss():
    source = read("en/index.html")
    assert '<link rel="canonical" href="https://news.learnprompt.pro/en" />' in source
    assert 'hreflang="zh-CN" href="https://news.learnprompt.pro/"' in source
    assert 'hreflang="en" href="https://news.learnprompt.pro/en"' in source
    assert 'hreflang="x-default" href="https://news.learnprompt.pro/"' in source
    assert 'type="application/rss+xml" title="AI News Radar" href="/en/feed.xml"' in source


def test_english_page_keeps_the_same_section_layout_as_zh():
    from bs4 import BeautifulSoup

    zh_sections = [s.get("id") for s in BeautifulSoup(read("index.html"), "html.parser").select("main > section")]
    en_soup = BeautifulSoup(read("en/index.html"), "html.parser")
    assert [s.get("id") for s in en_soup.select("main > section")] == zh_sections
    # same element ids as the zh page, so app.js works unchanged (the view switch is the only deliberate gap)
    zh_ids = {el.get("id") for el in BeautifulSoup(read("index.html"), "html.parser").select("[id]")}
    en_ids = {el.get("id") for el in en_soup.select("[id]")}
    assert zh_ids == en_ids
    assert html.escape(EN["page.todayProjectsTitle"], quote=False) in read("en/index.html")
    assert f'id="todayProjectsTitle">{EN["page.todayProjectsTitle"]}' in read("en/index.html")
    assert f">{html.escape(EN['page.githubLink'], quote=False)}</a>" in read("en/index.html")


def test_view_router_skips_classic_when_rooted_at_en():
    source = read("assets/view-mode.js")
    assert "const classicAvailable = !/^\\/en\\/?$/.test(rootHint)" in source
    assert "classicAvailable ? (preference || deviceDefault) : deviceDefault" in source
    assert "!classicAvailable" in source


def test_data_urls_resolve_from_site_root_on_the_english_page():
    source = read("assets/app.js")
    assert 'document.documentElement?.dataset?.root' in source
    assert 'startsWith("/")' in source
    # a ?data= / localStorage override still wins and only keeps the file name
    assert 'return `${base}/${file}`' in source


def test_sitemap_robots_and_feed_rewrite_exist():
    assert "https://news.learnprompt.pro/en" in read("sitemap.xml")
    assert "Sitemap: https://news.learnprompt.pro/sitemap.xml" in read("robots.txt")
    config = json.loads(read("vercel.json"))
    assert {"source": "/en/feed.xml", "destination": "/data/feed-en.xml"} in config["rewrites"]
    assert config["headers"][0]["source"] == "/data/(.*)"
