"""Execute the optional project module in both views with a small DOM stub."""

from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("view", ["assets/app.js", "classic/assets/app.js"])
def test_project_rendering_freshness_safety_and_loading(view):
    # Load the real declarations and project renderer, without the news boot code.
    source = (ROOT / view).read_text(encoding="utf-8")
    prefix = source[: source.index("function fmtTime(iso)")]
    prefix += source[source.index("function timelineIso(item)"):source.index("function timelineMs(item)")]
    script = r'''
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
const source = fs.readFileSync(0, "utf8");
const fixedNow = "2026-10-09T16:30:00Z";
class FixedDate extends Date {
  constructor(...args) { super(...(args.length ? args : [fixedNow])); }
  static now() { return new Date(fixedNow).getTime(); }
}
function element() {
  return {
    children: [], textContent: "",
    append(...nodes) { this.children.push(...nodes); },
    appendChild(node) { this.children.push(node); },
    replaceChildren() { this.children = []; },
    setAttribute(name, value) { this[name] = value; },
    set innerHTML(value) { throw new Error("Untrusted text must use textContent"); },
  };
}
const nodes = new Map();
const context = {
  document: {
    getElementById(id) {
      if (!nodes.has(id)) nodes.set(id, element());
      return nodes.get(id);
    },
    querySelector: () => null,
    createElement: element,
  },
  window: { location: { search: "?data=https://example.com/probe/data/" } },
  localStorage: { getItem: () => "", setItem() {} },
  URL, URLSearchParams, Intl, Date: FixedDate, AbortController,
  setTimeout, clearTimeout,
};
vm.createContext(context);
vm.runInContext(source, context);
const list = nodes.get("todayProjectsList");
const meta = nodes.get("todayProjectsMeta");
const valid = {
  project_name: "<img src=x onerror=alert(1)>",
  site_id: "github_trending", site_name: "GitHub Trending",
  url: "https://github.com/example/demo",
  recommend_reason_zh: "用自己的资料试一次检索。", summary: "AI search tool",
};
function render(payload, failed = false) {
  context.payload = payload;
  context.failed = failed;
  vm.runInContext("renderTodayProjects(payload, failed)", context);
}
const today = "2026-10-10"; // Taipei has advanced to the next day; UTC has not.
assert.equal(vm.runInContext("todayProjectsDate()", context), today);
render({ date: today, items: Array.from({ length: 6 }, () => ({ ...valid })) });
assert.equal(list.children.length, 4);
assert.equal(meta.textContent, "4 个项目");
const card = list.children[0];
assert.equal(card.children[0].children[0].textContent, valid.project_name);
assert.equal(card.children[0].children[1].textContent, "GitHub Trending");
assert.equal(card.children[1].textContent, valid.recommend_reason_zh);
assert.equal(card.children[2].href, valid.url);
assert.equal(card.children[2].rel, "noopener noreferrer");
assert.equal(card.children[2].target, "_blank");
const recent = { ...valid, site_id: "producthunt", site_name: "Product Hunt",
  recency_basis: "updated_at", published_at: "2026-07-06T08:40:40Z", updated_at: fixedNow };
render({ date: today, items: [recent] });
assert.equal(list.children[0].children[0].children[1].textContent, "Product Hunt · 近期更新");
context.recent = recent;
assert.equal(vm.runInContext("timelineIso(recent)", context), fixedNow);
context.recent = { ...recent, updated_at: null };
assert.equal(vm.runInContext("timelineIso(recent)", context), "");
context.recent = { ...recent, recency_basis: "published_at", updated_at: null };
assert.equal(vm.runInContext("timelineIso(recent)", context), recent.published_at);
render({ date: today, items: [context.recent] });
assert.equal(list.children[0].children[0].children[1].textContent, "Product Hunt");
render({ date: "2026-10-09", items: [valid] });
assert.equal(list.children[0].textContent, "今天的项目推荐更新中。");
assert.equal(meta.textContent, "");
render({ date: today, items: [
  null,
  { ...valid, url: "javascript:alert(1)" },
  { ...valid, url: "data:text/html,bad" },
  { ...valid, recommend_reason_zh: " " },
  { ...valid, project_name: "creampie" },
  { ...valid, summary: "NSFW virtual girlfriend" },
  { ...valid, recommend_reason_zh: "NSFW 虚拟女友" },
] });
assert.equal(list.children.length, 1);
assert.equal(list.children[0].textContent, "今天暂无合适的项目推荐。");
render({ date: today, items: [], sources: [{ ok: false }, { ok: false }] });
assert.equal(list.children[0].textContent, "项目数据暂时加载失败，请稍后再试。");
(async () => {
  let requested;
  let requestOptions;
  context.fetch = async (url, options) => {
    requested = url; requestOptions = options;
    return { ok: true, json: async () => ({ date: today, items: [valid] }) };
  };
  await vm.runInContext("initTodayProjects()", context);
  assert.match(requested, /^https:\/\/example\.com\/probe\/data\/today-projects\.json\?t=/);
  assert.ok(requestOptions.signal instanceof AbortSignal);
  assert.equal(list.children.length, 1);
  assert.equal(list.children[0].className, "today-project-card");
  vm.runInContext('state.dataBaseUrl = ""', context);
  await vm.runInContext("initTodayProjects()", context);
  assert.match(requested, /^data\/today-projects\.json\?t=/);
  for (const response of [
    async () => { throw new Error("offline <script>"); },
    async () => ({ ok: false, status: 404 }),
    async () => ({ ok: true, json: async () => null }),
    async () => ({ ok: true, json: async () => ({}) }),
  ]) {
    context.fetch = response;
    await vm.runInContext("initTodayProjects()", context);
    assert.equal(list.children[0].textContent, "项目数据暂时加载失败，请稍后再试。");
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
    result = subprocess.run(
        ["node", "-e", script], input=prefix, text=True,
        capture_output=True, cwd=ROOT, timeout=20,
    )
    assert result.returncode == 0, result.stderr
