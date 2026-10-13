"""Run scripts/check_i18n_site.py, and prove it actually fails on the problems it guards against."""

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/check_i18n_site.py"
COPIED = ["index.html", "en/index.html", "classic/index.html", "sitemap.xml", "robots.txt"]


def test_check_script_passes_on_the_repo():
    result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


@pytest.fixture()
def sandbox(tmp_path):
    """A minimal copy of the files the checker reads, so tests can break them safely."""
    for rel in COPIED:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, tmp_path / rel)
    shutil.copytree(ROOT / "assets/i18n", tmp_path / "assets/i18n")
    for rel in ("assets/i18n.js", "assets/app.js", "assets/view-mode.js", "assets/styles.css", "assets/service-status.css",
                "assets/service-status.js", "assets/motion.js", "assets/logo.svg", "site.webmanifest"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, tmp_path / rel)
    shutil.copytree(ROOT / "assets/icons", tmp_path / "assets/icons")
    spec = importlib.util.spec_from_file_location("check_i18n_site_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT = tmp_path
    return module, tmp_path


def errors_of(module):
    errors = []
    parsed = module.check_pages(errors)
    module.check_sitemap(errors)
    module.check_catalogs(errors)
    module.check_en_page(errors, parsed.get("en"))
    return errors


def test_sandbox_baseline_is_clean(sandbox):
    module, _ = sandbox
    assert errors_of(module) == []


def test_flags_cjk_in_english_page(sandbox):
    module, root = sandbox
    page = root / "en/index.html"
    page.write_text(page.read_text(encoding="utf-8").replace("Skip to hot stories", "跳到当前热点"), encoding="utf-8")
    assert any("CJK" in error for error in errors_of(module))


def test_allowlisted_proper_noun_is_tolerated(sandbox):
    module, root = sandbox
    page = root / "en/index.html"
    page.write_text(page.read_text(encoding="utf-8").replace("Scout Skill helps", "Scout Skill (伯乐Skill) helps", 1), encoding="utf-8")
    assert not any("CJK" in error for error in errors_of(module))


def test_flags_missing_self_reference_in_hreflang(sandbox):
    module, root = sandbox
    page = root / "en/index.html"
    text = page.read_text(encoding="utf-8").replace(
        '<link rel="alternate" hreflang="en" href="https://news.learnprompt.pro/en" />\n', "")
    page.write_text(text, encoding="utf-8")
    assert any("hreflang" in error for error in errors_of(module))


def test_flags_canonical_mismatch(sandbox):
    module, root = sandbox
    page = root / "en/index.html"
    page.write_text(page.read_text(encoding="utf-8").replace(
        'rel="canonical" href="https://news.learnprompt.pro/en"', 'rel="canonical" href="https://news.learnprompt.pro/en/"'), encoding="utf-8")
    assert any("canonical" in error for error in errors_of(module))


def test_flags_sitemap_url_without_file(sandbox):
    module, root = sandbox
    sitemap = root / "sitemap.xml"
    sitemap.write_text(sitemap.read_text(encoding="utf-8").replace("/classic</loc>", "/nowhere</loc>"), encoding="utf-8")
    assert any("nowhere" in error for error in errors_of(module))


def test_flags_key_parity_and_stale_generated_js(sandbox):
    module, root = sandbox
    en_path = root / "assets/i18n/en.json"
    data = json.loads(en_path.read_text(encoding="utf-8"))
    data.pop("common.source")
    en_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    messages = "\n".join(errors_of(module))
    assert "common.source" in messages
    assert "out of sync" in messages


def test_flags_relative_asset_paths_in_english_page(sandbox):
    module, root = sandbox
    page = root / "en/index.html"
    page.write_text(page.read_text(encoding="utf-8").replace('href="/assets/styles.css', 'href="./assets/styles.css'), encoding="utf-8")
    assert any("relative" in error for error in errors_of(module))
