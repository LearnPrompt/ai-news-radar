#!/usr/bin/env python3
"""Static checks for the zh / en site surface (no network, no DB).

Checks:
- hreflang sets on / and /en are mutual, include the page itself, and match canonical
- every sitemap URL maps to an existing file; sitemap alternates match the pages' hreflang
- assets/i18n/zh.json and en.json have identical key sets and plural shapes
- the generated assets/i18n/{zh,en}.js are in sync with the JSON
- en/index.html has no CJK text outside a small allowlist of proper nouns
- en/index.html uses absolute asset paths that exist, and does not link the classic view

Exit code is non-zero on any failure.
"""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SITE = "https://news.learnprompt.pro"
PAGES = {
    "zh-CN": {"file": "index.html", "url": f"{SITE}/"},
    "en": {"file": "en/index.html", "url": f"{SITE}/en"},
}
EXPECTED_HREFLANG = {
    "zh-CN": f"{SITE}/",
    "en": f"{SITE}/en",
    "x-default": f"{SITE}/",
}
# CJK 专有名词白名单：英文页里允许出现的中文品牌词（目前英文页一个都不需要，留作扩展点）。
CJK_ALLOWLIST = ["伯乐Skill", "伯乐", "好案例"]
CJK_RE = re.compile(r"[㐀-䶿一-鿿豈-﫿　-〿＀-￯]")
SITEMAP_NS = {
    "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
    "xhtml": "http://www.w3.org/1999/xhtml",
}


class HeadParser(HTMLParser):
    """Collects <html> attrs, link/meta tags and local src/href references."""

    def __init__(self) -> None:
        super().__init__()
        self.html_attrs: dict[str, str] = {}
        self.links: list[dict[str, str]] = []
        self.metas: list[dict[str, str]] = []
        self.refs: list[tuple[str, str]] = []  # (tag, ref) of local-file references; rel=alternate links are routes, not files

    def handle_starttag(self, tag, attrs):
        attr = {k: (v or "") for k, v in attrs}
        if tag == "html":
            self.html_attrs = attr
        elif tag == "link":
            self.links.append(attr)
        elif tag == "meta":
            self.metas.append(attr)
        for key in ("src", "href"):
            if key in attr and tag in {"script", "link", "img", "a"}:
                if tag == "link" and attr.get("rel") in {"alternate", "canonical"}:
                    continue
                self.refs.append((tag, attr[key]))


def parse(path: Path) -> HeadParser:
    parser = HeadParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser


def hreflang_map(parser: HeadParser) -> dict[str, str]:
    return {
        link["hreflang"]: link.get("href", "")
        for link in parser.links
        if link.get("rel") == "alternate" and link.get("hreflang")
    }


def canonical(parser: HeadParser) -> str:
    for link in parser.links:
        if link.get("rel") == "canonical":
            return link.get("href", "")
    return ""


def url_to_file(url: str) -> Path | None:
    parsed = urlparse(url)
    if f"{parsed.scheme}://{parsed.netloc}" != SITE:
        return None
    rel = parsed.path.strip("/")
    for candidate in ((ROOT / rel / "index.html") if rel else (ROOT / "index.html"), ROOT / rel):
        if candidate.is_file():
            return candidate
    return None


def check_pages(errors: list[str]) -> dict[str, HeadParser]:
    parsed: dict[str, HeadParser] = {}
    for lang, page in PAGES.items():
        path = ROOT / page["file"]
        if not path.is_file():
            errors.append(f"missing page: {page['file']}")
            continue
        parser = parse(path)
        parsed[lang] = parser
        if canonical(parser) != page["url"]:
            errors.append(f"{page['file']}: canonical {canonical(parser)!r} != {page['url']!r}")
        hreflang = hreflang_map(parser)
        if hreflang != EXPECTED_HREFLANG:
            errors.append(f"{page['file']}: hreflang {hreflang} != {EXPECTED_HREFLANG}")
        # 含自身：本页语言的 hreflang 必须指向本页 canonical
        if hreflang.get(lang) != page["url"]:
            errors.append(f"{page['file']}: hreflang[{lang}] does not point at the page itself")
        # 互指：hreflang 里每个目标都能解析到一个已知页面文件
        for target_lang, target_url in hreflang.items():
            target = url_to_file(target_url)
            if target is None:
                errors.append(f"{page['file']}: hreflang[{target_lang}] -> {target_url} has no file")
        expected_lang = "zh-CN" if lang == "zh-CN" else "en"
        if parser.html_attrs.get("lang", "").lower() != expected_lang.lower():
            errors.append(f"{page['file']}: <html lang> is {parser.html_attrs.get('lang')!r}, want {expected_lang!r}")
    if len(parsed) == 2 and hreflang_map(parsed["zh-CN"]) != hreflang_map(parsed["en"]):
        errors.append("hreflang sets differ between / and /en (they must be mutual and identical)")
    return parsed


def check_sitemap(errors: list[str]) -> None:
    path = ROOT / "sitemap.xml"
    if not path.is_file():
        errors.append("missing sitemap.xml")
        return
    tree = ET.parse(path)
    locs: dict[str, dict[str, str]] = {}
    for url in tree.getroot().findall("sm:url", SITEMAP_NS):
        loc = (url.findtext("sm:loc", default="", namespaces=SITEMAP_NS) or "").strip()
        alternates = {
            link.get("hreflang", ""): link.get("href", "")
            for link in url.findall("xhtml:link", SITEMAP_NS)
            if link.get("rel") == "alternate"
        }
        locs[loc] = alternates
        if url_to_file(loc) is None:
            errors.append(f"sitemap.xml: {loc} does not map to an existing file")
    for required in (f"{SITE}/", f"{SITE}/classic", f"{SITE}/en"):
        if required not in locs:
            errors.append(f"sitemap.xml: missing {required}")
    for page_url in (f"{SITE}/", f"{SITE}/en"):
        if locs.get(page_url) != EXPECTED_HREFLANG:
            errors.append(f"sitemap.xml: alternates for {page_url} are {locs.get(page_url)}, want {EXPECTED_HREFLANG}")
    robots = ROOT / "robots.txt"
    if not robots.is_file() or f"Sitemap: {SITE}/sitemap.xml" not in robots.read_text(encoding="utf-8"):
        errors.append("robots.txt must contain the Sitemap line")


def shape(value) -> str:
    if isinstance(value, dict):
        return "plural:" + ",".join(sorted(value))
    return "string"


def check_catalogs(errors: list[str]) -> None:
    catalogs = {}
    for lang in ("zh", "en"):
        path = ROOT / "assets/i18n" / f"{lang}.json"
        if not path.is_file():
            errors.append(f"missing assets/i18n/{lang}.json")
            return
        catalogs[lang] = json.loads(path.read_text(encoding="utf-8"))
    zh, en = catalogs["zh"], catalogs["en"]
    for key in sorted(set(zh) ^ set(en)):
        errors.append(f"i18n key only in {'zh' if key in zh else 'en'}.json: {key}")
    for key in sorted(set(zh) & set(en)):
        if shape(zh[key]) != shape(en[key]):
            errors.append(f"i18n key {key}: zh is {shape(zh[key])}, en is {shape(en[key])}")
    for lang, data in catalogs.items():
        js_path = ROOT / "assets/i18n" / f"{lang}.js"
        if not js_path.is_file():
            errors.append(f"missing generated assets/i18n/{lang}.js (run node scripts/build_i18n.mjs)")
            continue
        body = js_path.read_text(encoding="utf-8")
        match = re.search(r"window\.__I18N\s*=\s*(\{.*\});\s*$", body, re.S)
        if not match or json.loads(match.group(1)) != data:
            errors.append(f"assets/i18n/{lang}.js is out of sync with {lang}.json (run node scripts/build_i18n.mjs)")


def check_en_page(errors: list[str], parser: HeadParser | None) -> None:
    path = ROOT / PAGES["en"]["file"]
    if parser is None or not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    stripped = text
    for word in CJK_ALLOWLIST:
        stripped = stripped.replace(word, "")
    leftovers = sorted(set(CJK_RE.findall(stripped)))
    if leftovers:
        errors.append(f"en/index.html contains CJK outside the allowlist: {''.join(leftovers)}")
    if parser.html_attrs.get("data-root") != "/en/":
        errors.append('en/index.html: <html> must carry data-root="/en/"')
    if "data-radar-view-target" in text or "classic" in text.lower():
        errors.append("en/index.html must not render or link the classic view")
    if not any(link.get("rel") == "alternate" and link.get("type") == "application/rss+xml" and link.get("href") == "/en/feed.xml" for link in parser.links):
        errors.append("en/index.html: missing RSS alternate /en/feed.xml")
    for tag, ref in parser.refs:
        if ref.startswith(("http://", "https://", "#", "mailto:")):
            if tag != "a" and ref.startswith("http") and "news.learnprompt.pro" in ref and "/assets/" in ref:
                target = ROOT / urlparse(ref).path.lstrip("/")
                if not target.is_file():
                    errors.append(f"en/index.html: {ref} does not exist")
            continue
        if not ref.startswith("/"):
            errors.append(f"en/index.html: relative {tag} reference {ref!r} (must be absolute)")
            continue
        target = ROOT / urlparse(ref).path.lstrip("/")
        if tag in {"script", "link", "img"} and not target.is_file():
            errors.append(f"en/index.html: {ref} does not exist")


def main() -> int:
    errors: list[str] = []
    parsed = check_pages(errors)
    check_sitemap(errors)
    check_catalogs(errors)
    check_en_page(errors, parsed.get("en"))
    if errors:
        print("check_i18n_site: FAIL", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("check_i18n_site: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
