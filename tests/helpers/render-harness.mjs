// 渲染快照 harness：用最小假 DOM 跑 assets/app.js，把关键区域序列化成 JSON 输出。
// 用法：node tests/helpers/render-harness.mjs --app=assets/app.js --lang=zh|en
// 固定 TZ=UTC 与固定时间，同一份 fixture 在 zh 下应与改造前（无 i18n）的输出逐字节一致。
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import path from "node:path";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const FIXED_NOW = "2026-10-13T12:00:00Z";
const INTERNAL = new Set(["children", "parent", "listeners", "tagName", "dataset", "attrs", "content"]);

class FakeEl {
  constructor(tag = "div") {
    this.tagName = String(tag).toUpperCase();
    this.children = [];
    this.parent = null;
    this.listeners = {};
    this.dataset = {};
    this.attrs = {};
    this._text = "";
    this._html = "";
  }
  get className() { return this._className || ""; }
  set className(v) { this._className = String(v); }
  get classList() {
    const el = this;
    const list = () => el.className.split(/\s+/).filter(Boolean);
    return {
      add: (...names) => { el.className = Array.from(new Set([...list(), ...names])).join(" "); },
      remove: (...names) => { el.className = list().filter((n) => !names.includes(n)).join(" "); },
      contains: (name) => list().includes(name),
      toggle: (name, force) => {
        const has = list().includes(name);
        const on = force === undefined ? !has : Boolean(force);
        if (on && !has) el.className = [...list(), name].join(" ");
        if (!on && has) el.className = list().filter((n) => n !== name).join(" ");
        return on;
      },
    };
  }
  get textContent() { return this.children.length ? this.children.map((c) => c.textContent).join("") : this._text; }
  set textContent(v) { this.children.forEach((c) => { c.parent = null; }); this.children = []; this._html = ""; this._text = String(v); }
  get innerHTML() { return this._html; }
  set innerHTML(v) { this.children.forEach((c) => { c.parent = null; }); this.children = []; this._text = ""; this._html = String(v); }
  get firstElementChild() { return this.children[0] || null; }
  appendChild(node) {
    if (node.tagName === "#FRAGMENT") { node.children.splice(0).forEach((c) => this.appendChild(c)); return node; }
    if (node.parent) node.parent.children = node.parent.children.filter((c) => c !== node);
    node.parent = this;
    this.children.push(node);
    return node;
  }
  append(...nodes) { nodes.forEach((n) => this.appendChild(typeof n === "string" ? Object.assign(new FakeEl("#text"), { _text: n }) : n)); }
  replaceChildren(...nodes) { this.textContent = ""; this.append(...nodes); }
  insertAdjacentElement(position, node) {
    if (position !== "afterend") throw new Error(`unsupported position ${position}`);
    if (node.parent) node.parent.children = node.parent.children.filter((c) => c !== node);
    const siblings = this.parent.children;
    siblings.splice(siblings.indexOf(this) + 1, 0, node);
    node.parent = this.parent;
    return node;
  }
  remove() { if (this.parent) this.parent.children = this.parent.children.filter((c) => c !== this); this.parent = null; }
  setAttribute(name, value) { this.attrs[name] = String(value); }
  getAttribute(name) { return name in this.attrs ? this.attrs[name] : null; }
  removeAttribute(name) { delete this.attrs[name]; }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  scrollIntoView() {}
  cloneNode(deep) {
    const copy = new FakeEl(this.tagName);
    Object.keys(this).filter((k) => !INTERNAL.has(k) && k !== "_text" && k !== "_html").forEach((k) => { copy[k] = this[k]; });
    copy._text = this._text; copy._html = this._html;
    copy.dataset = { ...this.dataset }; copy.attrs = { ...this.attrs };
    if (deep) this.children.forEach((c) => copy.appendChild(c.cloneNode(true)));
    return copy;
  }
  matches(selector) {
    if (selector.startsWith(".")) return this.className.split(/\s+/).includes(selector.slice(1));
    return this.tagName === selector.toUpperCase();
  }
  querySelector(selector) {
    for (const child of this.children) {
      if (child.matches(selector)) return child;
      const hit = child.querySelector(selector);
      if (hit) return hit;
    }
    return null;
  }
  querySelectorAll(selector) {
    const out = [];
    this.children.forEach((c) => { if (c.matches(selector)) out.push(c); out.push(...c.querySelectorAll(selector)); });
    return out;
  }
}

function el(tag, className, props = {}) {
  const node = new FakeEl(tag);
  if (className) node.className = className;
  Object.assign(node, props);
  return node;
}

// 与 index.html 里 <template id="itemTpl"> 同构
function buildItemTemplate() {
  const article = el("article", "news-card");
  const body = el("div", "news-card-body");
  const meta = el("div", "meta-row");
  meta.append(el("span", "curated-badge", { hidden: true }), el("span", "site"), el("span", "source"), el("strong", "score-badge", { hidden: true }));
  const why = el("div", "why-box", { hidden: true });
  why.append(el("span", "why-label"), el("span", "why-text"));
  body.append(meta, el("a", "title"), el("p", "news-summary"), why, el("div", "persona-slot"));
  article.appendChild(body);
  return { content: { firstElementChild: article } };
}

export function serialize(node) {
  const props = {};
  Object.keys(node).filter((k) => !INTERNAL.has(k) && !k.startsWith("_")).sort().forEach((k) => { props[k] = node[k]; });
  if (node._className) props.className = node._className;
  const out = { tag: node.tagName.toLowerCase() };
  if (Object.keys(props).length) out.props = props;
  if (Object.keys(node.dataset).length) out.dataset = { ...node.dataset };
  if (Object.keys(node.attrs).length) out.attrs = { ...node.attrs };
  if (node._text) out.text = node._text;
  if (node._html) out.html = node._html;
  if (node.children.length) out.children = node.children.map(serialize);
  return out;
}

function findAll(node, predicate, out = []) {
  node.children.forEach((c) => { if (predicate(c)) out.push(c); findAll(c, predicate, out); });
  return out;
}

const defaultFixtures = JSON.parse(readFileSync(path.join(ROOT, "tests/fixtures/render-data.json"), "utf8"));

export async function runScenario({ appPath, lang, search = "", fixtures = defaultFixtures, i18nDir = path.join(ROOT, "assets") }) {
  const nodes = new Map();
  const byClass = new Map();
  const doc = {
    documentElement: { lang: lang === "en" ? "en" : "zh-CN", dataset: lang === "en" ? { root: "/en/" } : {} },
    hidden: false,
    getElementById(id) {
      if (id === "itemTpl") { if (!nodes.has(id)) nodes.set(id, Object.assign(new FakeEl("template"), buildItemTemplate())); return nodes.get(id); }
      if (!nodes.has(id)) nodes.set(id, new FakeEl("div"));
      return nodes.get(id);
    },
    querySelector(sel) {
      if (!byClass.has(sel)) byClass.set(sel, new FakeEl("div"));
      return byClass.get(sel);
    },
    createElement: (tag) => new FakeEl(tag),
    createDocumentFragment: () => new FakeEl("#fragment"),
    dispatchEvent() {},
  };
  const store = new Map();
  class FixedDate extends Date {
    constructor(...args) { super(...(args.length ? args : [FIXED_NOW])); }
    static now() { return new Date(FIXED_NOW).getTime(); }
  }
  const requested = [];
  const context = {
    document: doc,
    window: { location: { search, pathname: lang === "en" ? "/en/" : "/", href: "" } },
    localStorage: { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v), removeItem: (k) => store.delete(k) },
    Intl, Date: FixedDate, URL, URLSearchParams, AbortController, Promise, console,
    setTimeout, clearTimeout,
    requestAnimationFrame: (cb) => cb(),
    CustomEvent: class { constructor(name) { this.type = name; } },
    fetch: async (url) => {
      requested.push(String(url));
      const file = String(url).split("?")[0].split("/").pop();
      if (!(file in fixtures)) return { ok: false, status: 404, json: async () => ({}) };
      return { ok: true, status: 200, json: async () => JSON.parse(JSON.stringify(fixtures[file])) };
    },
  };
  vm.createContext(context);
  const run = (file) => vm.runInContext(readFileSync(file, "utf8"), context, { filename: file });
  run(path.join(i18nDir, "i18n", `${lang === "en" ? "en" : "zh"}.js`));
  run(path.join(i18nDir, "i18n.js"));
  run(appPath);
  const flush = () => new Promise((resolve) => setTimeout(resolve, 20));
  await flush();

  const ids = ["updatedAt", "sourceStatusPill", "resultCount", "listTitle", "modeHint", "clearFiltersBtn", "allDedupeLabel",
    "sectionTabs", "siteSelect", "newsList", "hotBoardList", "hotBoardMeta", "waytoagiUpdatedAt", "waytoagiMeta", "waytoagiList",
    "sourceHealth", "sourceHealthDetails", "sourceStatusTable", "todayProjectsList", "todayProjectsMeta", "dataSourceIndicatorText"];
  const snap = () => Object.fromEntries(ids.map((id) => [id, serialize(doc.getElementById(id))]));
  const fire = async (node, type, event = {}) => {
    for (const fn of node.listeners[type] || []) await fn({ preventDefault() {}, stopPropagation() {}, target: node, ...event });
    await flush();
  };
  const tabs = () => doc.getElementById("sectionTabs").children;
  const out = {};
  out.initial = snap();

  // 展开多源 chip 与热点行信源
  const multi = findAll(doc.getElementById("newsList"), (n) => n.className === "multi-chip");
  if (multi[0]) { await fire(multi[0], "click"); out.multiExpanded = serialize(doc.getElementById("newsList")); }
  const hotToggle = findAll(doc.getElementById("hotBoardList"), (n) => n.className === "hot-row-source-toggle");
  if (hotToggle[0]) { await fire(hotToggle[0], "click"); out.hotExpanded = serialize(doc.getElementById("hotBoardList")); }

  // 栏目切换：社区（含 WaytoAGI）
  const community = tabs().find((t) => t.dataset.section === "community");
  if (community) { await fire(community, "click"); out.community = snap(); }
  const w7 = doc.getElementById("waytoagi7dBtn");
  await fire(w7, "click"); out.waytoagi7d = serialize(doc.getElementById("waytoagiList"));

  // 搜索：命中与空结果
  const searchInput = doc.getElementById("searchInput");
  await fire(tabs().find((t) => t.dataset.section === "all"), "click");
  await fire(searchInput, "input", { target: { value: "copilot" } }); out.searchHit = snap();
  await fire(searchInput, "input", { target: { value: "zzzz-no-match" } }); out.searchEmpty = snap();
  await fire(searchInput, "input", { target: { value: "" } });

  // 全量模式 + 去重关
  await fire(doc.getElementById("modeAllBtn"), "click"); out.allMode = snap();
  await fire(doc.getElementById("allDedupeToggle"), "change", { target: { checked: false } }); out.allModeNoDedup = snap();

  // X 博主列表展开
  const xToggle = findAll(doc.getElementById("sourceHealthDetails"), (n) => n.className === "source-health-authors-toggle");
  if (xToggle[0]) { await fire(xToggle[0], "click"); out.authors = serialize(doc.getElementById("sourceHealthDetails")); }

  // 数据源覆盖指示器
  out.requested = requested.filter((u, i) => requested.indexOf(u) === i).map((u) => u.replace(/\?t=\d+/, "")).sort();
  // vm 上下文挂在不可枚举属性上，供单测直接调用 app.js 里的函数；JSON 输出不含它
  Object.defineProperty(out, "context", { value: context });
  return out;
}

// 其他 app.js 暴露的纯函数，供单测直接调用
export function evalIn(context, code) { return vm.runInContext(code, context); }

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const arg = (name, fallback) => (process.argv.find((a) => a.startsWith(`--${name}=`)) || "").split("=").slice(1).join("=") || fallback;
  const appPath = path.resolve(arg("app", path.join(ROOT, "assets/app.js")));
  const lang = arg("lang", "zh");
  const result = await runScenario({ appPath, lang });
  process.stdout.write(`${JSON.stringify(result, null, 1)}\n`);
}
