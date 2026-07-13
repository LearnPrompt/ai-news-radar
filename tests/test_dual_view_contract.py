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
