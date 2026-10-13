// i18n 运行时、词条完整性与渲染快照测试：node --test tests/i18n.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { runScenario } from "./helpers/render-harness.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (rel) => readFileSync(path.join(ROOT, rel), "utf8");
const zhDict = JSON.parse(read("assets/i18n/zh.json"));
const enDict = JSON.parse(read("assets/i18n/en.json"));
const CJK = /[㐀-䶿一-鿿豈-﫿　-〿]/;
const APP = path.join(ROOT, "assets/app.js");

// 只加载词典 + i18n.js 的轻量上下文
function loadI18n(lang) {
  const context = { document: { documentElement: { lang: lang === "en" ? "en" : "zh-CN" } }, window: {}, Intl, Date };
  vm.createContext(context);
  vm.runInContext(read(`assets/i18n/${lang}.js`), context);
  vm.runInContext(read("assets/i18n.js"), context);
  return context.window.AINewsRadarI18n;
}

test("词条键集合 zh/en 一致，复数结构一致", () => {
  assert.deepEqual(Object.keys(zhDict).sort(), Object.keys(enDict).sort());
  for (const key of Object.keys(zhDict)) {
    assert.equal(typeof zhDict[key], typeof enDict[key], key);
    if (typeof zhDict[key] === "object") {
      assert.ok("one" in zhDict[key] && "other" in zhDict[key], `${key} zh plural`);
      assert.ok("one" in enDict[key] && "other" in enDict[key], `${key} en plural`);
    }
  }
});

test("英文词条不含 CJK（外部专有名词需先加入白名单）", () => {
  const flat = (v) => (typeof v === "string" ? [v] : Object.values(v));
  for (const [key, value] of Object.entries(enDict)) {
    for (const text of flat(value)) assert.ok(!CJK.test(text), `${key}: ${text}`);
  }
});

test("生成的 zh.js / en.js 与 JSON 同步", () => {
  execFileSync(process.execPath, [path.join(ROOT, "scripts/build_i18n.mjs"), "--check"], { stdio: "pipe" });
});

test("语言由 <html lang> 决定", () => {
  assert.equal(loadI18n("en").LANG, "en");
  assert.equal(loadI18n("en").isEN, true);
  assert.equal(loadI18n("zh").LANG, "zh");
  assert.equal(loadI18n("zh").isEN, false);
});

test("t：插值、复数、缺失键回退", () => {
  const en = loadI18n("en");
  assert.equal(en.t("count.items", { n: 1 }), "1 item");
  assert.equal(en.t("count.items", { n: 0 }), "0 items");
  assert.equal(en.t("count.items", { n: 1234 }), "1,234 items");
  assert.equal(en.t("rel.minutes", { n: 1 }), "1 minute ago");
  assert.equal(en.t("rel.minutes", { n: 5 }), "5 minutes ago");
  assert.equal(en.t("status.ok", { ok: 3, total: 4 }), "3/4 sources OK");
  assert.equal(en.t("today.openAria", { name: "<b>x</b>" }), "Open project: <b>x</b>");
  assert.equal(en.t("no.such.key"), "no.such.key");
  assert.equal(en.t("today.openAria"), "Open project: {name}", "缺参数保留占位符");
  const zh = loadI18n("zh");
  assert.equal(zh.t("count.items", { n: 1 }), "1 条");
  assert.equal(zh.t("count.items", { n: 2 }), "2 条");
  assert.equal(zh.t("rel.hours", { n: 3 }), "3 小时前");
  assert.equal(zh.t("status.okFailed", { ok: 1, total: 2, failed: 1 }), "1/2 源正常 · 失败 1");
});

test("fmtNumber / fmtRelative / collator 跟随语言", () => {
  const en = loadI18n("en");
  assert.equal(en.fmtNumber(1234567), "1,234,567");
  assert.equal(en.fmtNumber(undefined), "0");
  const now = Date.parse("2026-10-13T12:00:00Z");
  assert.equal(en.fmtRelative(now - 30 * 1000, now), "1 minute ago");
  assert.equal(en.fmtRelative(now - 3 * 3600 * 1000, now), "3 hours ago");
  assert.equal(en.fmtRelative(now - 72 * 3600 * 1000, now), "3 days ago");
  assert.equal(en.fmtRelative(now + 1000, now), "Just now");
  assert.equal(en.fmtRelative(0, now), "Time unknown");
  assert.equal(loadI18n("zh").fmtRelative(now - 3 * 3600 * 1000, now), "3 小时前");
  assert.ok(en.collator.compare("a", "b") < 0);
  assert.match(en.fmtDate(new Date("2026-10-13T00:00:00Z"), { timeZone: "UTC", month: "short", day: "numeric" }), /Oct\s+13/);
});

test("中文站渲染与改造前逐字节一致（快照）", () => {
  const golden = JSON.parse(read("tests/fixtures/zh-render-golden.json"));
  const stdout = execFileSync(process.execPath, [path.join(ROOT, "tests/helpers/render-harness.mjs"), `--app=${APP}`, "--lang=zh"], {
    env: { ...process.env, TZ: "UTC" }, maxBuffer: 64 * 1024 * 1024,
  }).toString();
  assert.deepEqual(JSON.parse(stdout), golden);
});

test("英文站渲染：无中文 UI 串、自媒体整块隐藏、数据走 /data/ 绝对路径", async () => {
  const out = await runScenario({ appPath: APP, lang: "en" });
  const text = JSON.stringify(out);
  assert.ok(!CJK.test(text), `EN 渲染里出现中文: ${text.match(/.{20}[㐀-鿿]+.{10}/)?.[0]}`);
  assert.ok(!/Creators|tikhub|Douyin|WeChat/i.test(text.replace(/TikHub Douyin/g, "")), "自媒体栏目/条目应隐藏");
  assert.ok(!/data-section":\s*"creator"|"section":\s*"creator"/.test(text));
  assert.deepEqual(out.requested.filter((url) => !url.startsWith("/data/")), []);
  assert.ok(out.requested.includes("/data/latest-24h.json"));
  // 空结果态使用英文串
  assert.match(text, /No matching results/);
});

test("英文站：来源状态表不含自媒体行；其余来源保留", async () => {
  const out = await runScenario({ appPath: APP, lang: "en" });
  const html = JSON.stringify(out.initial.sourceStatusTable);
  assert.ok(!html.includes("TikHub Douyin"));
  assert.ok(html.includes("Hacker News"));
});

test("?data= 覆盖对 zh / en 都生效，且只拼文件名", async () => {
  for (const lang of ["zh", "en"]) {
    const out = await runScenario({ appPath: APP, lang, search: "?data=https://example.com/probe/data/" });
    assert.ok(out.requested.length > 0);
    assert.deepEqual(out.requested.filter((url) => !url.startsWith("https://example.com/probe/data/")), [], lang);
  }
});

test("dataUrl：zh 保持相对路径，en 取站点根 /data/", async () => {
  const zh = (await runScenario({ appPath: APP, lang: "zh" })).context;
  const en = (await runScenario({ appPath: APP, lang: "en" })).context;
  assert.equal(vm.runInContext('dataUrl("data/x.json")', zh), "data/x.json");
  assert.equal(vm.runInContext('dataUrl("data/x.json")', en), "/data/x.json");
  assert.equal(vm.runInContext('dataUrl("/data/x.json")', en), "/data/x.json");
  assert.equal(vm.runInContext('dataUrl("https://cdn.example.com/x.json")', en), "https://cdn.example.com/x.json");
});

test("英文标题取法：en.title → title_en（多数英文）→ title_original → title", async () => {
  const { context } = await runScenario({ appPath: APP, lang: "en" });
  const call = (code, vars) => { Object.assign(context, vars); return vm.runInContext(code, context); };
  assert.equal(call("itemTitleText(item)", { item: { en: { title: "EN T" }, title_en: "Title En Here", title_zh: "中" } }), "EN T");
  assert.equal(call("itemTitleText(item)", { item: { title_en: "Title En Here", title_original: "Orig", title_zh: "中" } }), "Title En Here");
  assert.equal(call("itemTitleText(item)", { item: { title_en: "中文标题", title_original: "Original Title", title: "中 / Mixed" } }), "Original Title");
  assert.equal(call("itemTitleText(item)", { item: { title: "中文标题 / English Part Here" } }), "English Part Here");
  assert.equal(call("itemTitleText(item)", { item: {} }), "Untitled update");
  assert.equal(call("storyPrimaryTitleText(story)", { story: { title: "Story Title Here", primary_item: { en: { title: "Primary EN" } } } }), "Primary EN");
  assert.equal(call("storyPrimaryTitleText(story)", { story: { title: "中文 / Story Title Here", primary_item: {} } }), "Story Title Here");
  assert.equal(call("itemOriginalTitleText(item)", { item: { title_en: "English Title Here" } }), "");
});

test("英文摘要与理由：en.summary || summary；理由只认 en.reason", async () => {
  const { context } = await runScenario({ appPath: APP, lang: "en" });
  const call = (code, vars) => { Object.assign(context, vars); return vm.runInContext(code, context); };
  assert.equal(call("itemSummaryText(item)", { item: { summary: "原文", en: { summary: "Translated" } } }), "Translated");
  assert.equal(call("itemSummaryText(item)", { item: { summary: "Plain summary" } }), "Plain summary");
  assert.equal(call("whyImportantText(row)", { row: { item: { recommend_reason_zh: "中文理由" }, story: {} } }), "");
  assert.equal(call("whyImportantText(row)", { row: { item: { en: { reason: "Because." } }, story: {} } }), "Because.");
  assert.equal(call("whyImportantText(row)", { row: { item: {}, story: { primary_item: { en: { reason: "From primary." } } } } }), "From primary.");
});

test("中文站：标题/摘要/理由函数不受 en 字段影响", async () => {
  const { context } = await runScenario({ appPath: APP, lang: "zh" });
  const call = (code, vars) => { Object.assign(context, vars); return vm.runInContext(code, context); };
  const item = { title: "中文标题 / English Title", title_zh: "中文标题", title_en: "English Title", summary: "原文摘要", recommend_reason_zh: "中文理由",
    en: { title: "EN T", summary: "EN S", reason: "EN R" } };
  assert.equal(call("itemTitleText(item)", { item }), "中文标题");
  assert.equal(call("itemOriginalTitleText(item)", { item }), "English Title");
  assert.equal(call("itemSummaryText(item)", { item }), "原文摘要");
  assert.equal(call("whyImportantText(row)", { row: { item, story: {} } }), "中文理由");
  assert.equal(call("storyPrimaryTitleText(story)", { story: { primary_item: item } }), "中文标题");
});

test("importance_label 映射与来源标签", async () => {
  const en = (await runScenario({ appPath: APP, lang: "en" })).context;
  const zh = (await runScenario({ appPath: APP, lang: "zh" })).context;
  for (const [label, key] of [["官方更新", "importance.official"], ["多源热议", "importance.multi_source"], ["行业动态", "importance.industry"], ["值得关注", "importance.watch"]]) {
    assert.equal(vm.runInContext(`importanceLabelText(${JSON.stringify(label)})`, en), enDict[key]);
    assert.equal(vm.runInContext(`importanceLabelText(${JSON.stringify(label)})`, zh), label);
  }
  assert.equal(vm.runInContext('importanceLabelText("其它")', en), "其它");
  assert.equal(vm.runInContext('sourceSignalLabel("HN热议")', en), "HN buzz");
  assert.equal(vm.runInContext('sourceSignalTone(sourceSignal({site_name:"Hacker News"}))', en), "aggregate");
});

// ---- service-status.js ----
async function renderStatus(lang, withI18n) {
  const source = read("assets/service-status.js");
  const element = () => ({
    children: [], hidden: true, classList: { toggle() {} }, attrs: {},
    append(...items) { this.children.push(...items); }, appendChild(item) { this.children.push(item); },
    replaceChildren() { this.children = []; }, setAttribute(name, value) { this.attrs[name] = value; },
  });
  const panel = element();
  const context = {
    document: { getElementById: () => panel, createElement: element, currentScript: { src: "https://news.learnprompt.pro/assets/service-status.js" },
      documentElement: { lang: lang === "en" ? "en" : "zh-CN" } },
    window: { location: { search: "" }, setTimeout, clearTimeout },
    localStorage: { getItem: () => "" }, URL, URLSearchParams, AbortController, Intl, Date,
    fetch: async () => ({ ok: true, json: async () => ({ ok: true, generated_at: new Date().toISOString(),
      incidents: [{ provider: "OpenAI", title: "Elevated Error Rates", title_zh: "错误率升高", status: "monitoring", impact: "minor", url: "https://status.openai.com/x" },
        { provider: "OpenAI", title: "Login issue", title_zh: "登录异常", status: "investigating", impact: "minor", url: "https://status.openai.com/y" }] }) }),
  };
  vm.createContext(context);
  if (withI18n) {
    vm.runInContext(read(`assets/i18n/${lang}.js`), context);
    vm.runInContext(read("assets/i18n.js"), context);
  }
  vm.runInContext(source, context);
  await new Promise((resolve) => setImmediate(resolve));
  return panel;
}

test("service-status：zh 词条与 zh.json 一致（含无 i18n 的经典版回退）", async () => {
  for (const withI18n of [true, false]) {
    const panel = await renderStatus("zh", withI18n);
    const heading = panel.children[0];
    assert.equal(heading.children[0].children[1].textContent, zhDict["svc.heading"]);
    assert.equal(heading.children[1].textContent, zhDict["svc.count"].other.replace("{n}", "2"));
    assert.equal(panel.attrs["aria-label"], zhDict["svc.aria"].other.replace("{n}", "2"));
    const main = panel.children[1].children[0].children[0]; // incident row -> main -> [meta, title]
    assert.equal(main.children[0].children[1].textContent, zhDict["svc.monitoring"]);
    assert.equal(main.children[1].textContent, zhDict["svc.elevatedErrors"]);
  }
});

test("service-status：en 全英文，标题取官方英文", async () => {
  const panel = await renderStatus("en", true);
  assert.equal(panel.children[0].children[0].children[1].textContent, enDict["svc.heading"]);
  assert.equal(panel.children[0].children[1].textContent, "2 official incidents");
  const second = panel.children[1].children[1].children[0];
  assert.equal(second.children[1].textContent, "Login issue");
  assert.equal(second.children[0].children[1].textContent, enDict["svc.investigating"]);
  assert.ok(!CJK.test(JSON.stringify(panel.attrs)));
});

test("英文站隐藏 WaytoAGI：不拉数据、区块保持 hidden、社区栏目下也不渲染", async () => {
  const out = await runScenario({ appPath: APP, lang: "en" });
  assert.ok(!out.requested.some((url) => url.includes("waytoagi")), "不应请求 waytoagi-7d.json");
  const { context } = out;
  assert.equal(vm.runInContext("waytoagiWrapEl.hidden", context), true);
  for (const snapshot of [out.initial, out.community, out.waytoagi7d && { waytoagiList: out.waytoagi7d }]) {
    assert.ok(snapshot);
    assert.ok(!snapshot.waytoagiList?.children?.length, "WaytoAGI 列表应为空");
    assert.ok(!snapshot.waytoagiMeta?.children?.length, "WaytoAGI 元信息应为空");
  }
  assert.ok(!JSON.stringify(out).includes("WaytoAGI sample update"));
});

test("中文站仍请求并渲染 WaytoAGI", async () => {
  const out = await runScenario({ appPath: APP, lang: "zh" });
  assert.ok(out.requested.some((url) => url.includes("waytoagi-7d.json")));
  assert.ok(out.community.waytoagiList.children.length > 0);
});
