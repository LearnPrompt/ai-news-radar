"""Regression checks for the mobile/classic data and safety contract."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_FILES = (
    "latest-24h.json",
    "latest-24h-all.json",
    "waytoagi-7d.json",
    "source-status.json",
    "daily-brief.json",
    "stories-merged.json",
)


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


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


def test_both_pages_share_the_service_status_banner():
    loader = read("assets/service-status.js")
    assert 'get("data")' in loader
    assert 'localStorage.getItem("dataBaseUrl")' in loader
    assert "service-status.json" in loader
    assert 'incident.status !== "resolved"' in loader
    assert "ChatGPT / OpenAI 服务状态" in loader
    assert "ChatGPT 等 OpenAI 服务错误率升高" in loader

    mobile_source = read("index.html")
    classic_source = read("classic/index.html")
    assert 'id="serviceStatusPanel"' in mobile_source
    assert 'id="serviceStatusPanel"' in classic_source
    assert './assets/service-status.js?v=chatgpt-status-0724' in mobile_source
    assert './assets/service-status.js?v=chatgpt-status-0724' in classic_source


def test_data_fetches_revalidate_without_unique_cache_busters():
    for path in ("assets/app.js", "classic/assets/app.js"):
        source = read(path)
        assert "async function fetchJson(path)" in source
        assert 'cache: "no-cache"' in source
        assert "AbortController" in source
        assert '?t=${Date.now()}' not in source

    loader = read("assets/service-status.js")
    assert 'cache: "no-cache"' in loader
    assert "AbortController" in loader
    assert '?t=${Date.now()}' not in loader


def test_both_pages_are_self_hosted_and_have_social_previews():
    for path in ("index.html", "classic/index.html"):
        source = read(path)
        assert "https://github.com/1625517181-jpg/ai-news-radar" in source
        assert "https://github.com/LearnPrompt/ai-news-radar" not in source
        assert 'content="summary_large_image"' in source
        assert "/assets/og.jpg" in source
        assert "cdn.jsdelivr.net/npm/gsap" not in source

    assert (ROOT / "assets/og.jpg").stat().st_size > 0


def test_motion_uses_native_browser_animations():
    for path in ("assets/motion.js", "classic/assets/motion.js"):
        source = read(path)
        assert ".animate(" in source
        assert "prefers-reduced-motion: reduce" in source
        assert "window.gsap" not in source


def test_both_views_offer_a_reload_path_after_primary_data_failure():
    for path in ("assets/app.js", "classic/assets/app.js"):
        source = read(path)
        assert "function renderPrimaryLoadError(error)" in source
        assert 'retry.textContent = "重新加载"' in source
        assert "window.location.reload()" in source


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
        assert ">GitHub 与接入指南</a>" in source


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
