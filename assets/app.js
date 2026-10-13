// i18n：assets/i18n.js 先于本文件加载，按 <html lang> 选 zh / en 词典；
// 下面各处匹配逻辑用的中文关键词（不安全词、语气嗅探、标题修复、栏目正则、来源识别）不是 UI 文案，不翻译。
const i18n = window.AINewsRadarI18n;
const { t, isEN: IS_EN, locale: LOCALE } = i18n;

const state = {
  itemsAi: [],
  itemsAll: [],
  itemsAllRaw: [],
  creatorItemsAi: [],
  creatorItemsAll: [],
  creatorWindowDays: 7,
  statsAi: [],
  totalAi: 0,
  totalRaw: 0,
  totalAllMode: 0,
  allDedup: true,
  allDataLoaded: false,
  allDataUrl: "data/latest-24h-all.json",
  allDataPromise: null,
  siteFilter: "",
  authorFilter: "",
  query: "",
  // 单层信息架构：category（内容 tab） x mode（精选/全量全局开关）两个维度。
  // mode=selected 主列表读 mergedStories()（AI 相关合并事件池，纯时间倒序）；
  // mode=all 主列表读 itemsAllRaw/itemsAll（全量原始条目池）。
  mode: "selected",
  waytoagiMode: "today",
  waytoagiData: null,
  sourceStatus: null,
  generatedAt: null,
  dailyBrief: null,
  top3Personas: null,
  storiesMerged: null,
  storiesDataUrl: "data/stories-merged.json",
  // 内容 tab：单值，默认 "all"（全部，无过滤）
  activeSection: "all",
  mainListVisibleCount: 0,
  xAuthorsExpanded: false,
};

// DATA_BASE_URL 数据同源开关：优先级 ?data= 查询参数 > localStorage("dataBaseUrl") > "" (相对路径，原行为)
// ?data= 命中时持久化到 localStorage，方便刷新/后续访问保持同一数据源。
function resolveDataBaseUrl() {
  let fromQuery = "";
  try {
    fromQuery = new URLSearchParams(window.location.search).get("data") || "";
  } catch {
    fromQuery = "";
  }
  if (fromQuery) {
    const normalized = fromQuery.trim().replace(/\/+$/, "");
    try { localStorage.setItem("dataBaseUrl", normalized); } catch {}
    return normalized;
  }
  try {
    const stored = localStorage.getItem("dataBaseUrl") || "";
    return stored.trim().replace(/\/+$/, "");
  } catch {
    return "";
  }
}

state.dataBaseUrl = resolveDataBaseUrl();

// 所有 data/*.json 抓取都必须经过这个 helper，才能让 ?data= / localStorage 覆盖生效。
// 传入的 path 可能是 "data/xxx.json"（本地默认）或后端下发的同款相对路径；
// 一旦切换到远端 base，只拼文件名，避免拼出 base/data/xxx.json 这种双重 data/ 路径。
// 站点根（<html data-root>）为绝对路径（如 /en/）时，本地数据取站点根下的 /data/…；
// zh 页没有 data-root，保持原来的相对路径。?data= / localStorage 覆盖永远优先。
const DATA_ROOT_ABSOLUTE = String(document.documentElement?.dataset?.root || "").startsWith("/");

function dataUrl(path) {
  const base = state.dataBaseUrl;
  if (!base) {
    const raw = String(path || "");
    if (!DATA_ROOT_ABSOLUTE || raw.startsWith("/") || /^[a-z][a-z0-9+.-]*:/i.test(raw)) return path;
    return `/${raw}`;
  }
  const file = String(path || "").split("/").pop();
  return `${base}/${file}`;
}

const siteSelectEl = document.getElementById("siteSelect");
const newsListEl = document.getElementById("newsList");
const updatedAtEl = document.getElementById("updatedAt");
const sourceStatusPillEl = document.getElementById("sourceStatusPill");
const searchInputEl = document.getElementById("searchInput");
const resultCountEl = document.getElementById("resultCount");
const listTitleEl = document.getElementById("listTitle");
const itemTpl = document.getElementById("itemTpl");
const modeSelectedBtnEl = document.getElementById("modeSelectedBtn");
const modeAllBtnEl = document.getElementById("modeAllBtn");
const hotBoardWrapEl = document.getElementById("hotBoardWrap");
const hotBoardListEl = document.getElementById("hotBoardList");
const hotBoardMetaEl = document.getElementById("hotBoardMeta");
const top3BoardWrapEl = document.getElementById("top3BoardWrap");
const top3BoardListEl = document.getElementById("top3BoardList");
const top3BoardMetaEl = document.getElementById("top3BoardMeta");
const newsListWrapEl = document.getElementById("newsListWrap");
const modeHintEl = document.getElementById("modeHint");
const allDedupeWrapEl = document.getElementById("allDedupeWrap");
const allDedupeToggleEl = document.getElementById("allDedupeToggle");
const allDedupeLabelEl = document.getElementById("allDedupeLabel");
const sourceHealthEl = document.getElementById("sourceHealth");
const sourceHealthDetailsEl = document.getElementById("sourceHealthDetails");
const sourceStatusTableEl = document.getElementById("sourceStatusTable");
const clearFiltersBtnEl = document.getElementById("clearFiltersBtn");
const dataSourceIndicatorEl = document.getElementById("dataSourceIndicator");
const dataSourceIndicatorTextEl = document.getElementById("dataSourceIndicatorText");
const dataSourceResetBtnEl = document.getElementById("dataSourceResetBtn");

const waytoagiWrapEl = document.querySelector(".waytoagi-wrap");
const waytoagiUpdatedAtEl = document.getElementById("waytoagiUpdatedAt");
const waytoagiMetaEl = document.getElementById("waytoagiMeta");
const waytoagiListEl = document.getElementById("waytoagiList");
const waytoagiTodayBtnEl = document.getElementById("waytoagiTodayBtn");
const waytoagi7dBtnEl = document.getElementById("waytoagi7dBtn");
const sectionTabsEl = document.getElementById("sectionTabs");

const SOURCE_KINDS = {
  official_ai: { label: t("sourceKind.official"), tone: "official" },
  curated_media: { label: t("sourceKind.curatedMedia"), tone: "aihub" },
  aihot: { label: "AI HOT", tone: "hot" },
  aibreakfast: { label: t("sourceKind.newsletter"), tone: "newsletter" },
  followbuilders: { label: "Builders/X", tone: "builders" },
  github_trending: { label: "GitHub Trending", tone: "builders" },
  producthunt: { label: "Product Hunt", tone: "aihub" },
  xapi: { label: "X API", tone: "builders" },
  socialdata_x: { label: t("sourceKind.xSearch"), tone: "builders" },
  tikhub_douyin: { label: t("sourceKind.douyin"), tone: "creator" },
  tikhub_xiaohongshu: { label: t("sourceKind.xiaohongshu"), tone: "creator" },
  techurls: { label: t("sourceKind.aggregate"), tone: "aggregate" },
  buzzing: { label: t("sourceKind.aggregate"), tone: "aggregate" },
  iris: { label: t("sourceKind.aggregate"), tone: "aggregate" },
  bestblogs: { label: t("sourceKind.blogs"), tone: "blogs" },
  zeli: { label: t("sourceKind.aggregate"), tone: "aggregate" },
  hackernews: { label: "HN", tone: "aggregate" },
  aihubtoday: { label: t("sourceKind.aiSites"), tone: "aihub" },
  aibase: { label: t("sourceKind.aiSites"), tone: "aihub" },
  waytoagi: { label: t("sourceKind.community"), tone: "builders" },
  newsnow: { label: t("sourceKind.aggregate"), tone: "aggregate" },
  opmlrss: { label: "OPML", tone: "newsletter" },
};

// aihotSubSource() 结果 → 卡片小标签文案/色调，色调复用既有 .category.kind-* 规则，不新增样式
const AIHOT_SUB_LABELS = { x: "X", wechat: t("aihotSub.wechat"), hn: "HN", rss: "RSS" };
const AIHOT_SUB_TONES = { x: "builders", wechat: "creator", hn: "aggregate", rss: "newsletter" };

// 单层内容 tab：全部（默认，无过滤）+ 5 个主题栏目 + 社区 + 自媒体，互斥单值。
// 英文版不展示自媒体栏目（抖音、小红书、公众号创作者内容不翻译）。
const SECTION_DEFS = [
  { id: "all", label: t("section.all.label"), short: t("section.all.label"), description: t("section.all.description") },
  { id: "models", label: t("section.models.label"), short: t("section.models.label"), description: t("section.models.description") },
  { id: "products", label: t("section.products.label"), short: t("section.products.label"), description: t("section.products.description") },
  { id: "devtools", label: t("section.devtools.label"), short: t("section.devtools.label"), description: t("section.devtools.description") },
  { id: "industry", label: t("section.industry.label"), short: t("section.industry.label"), description: t("section.industry.description") },
  { id: "research", label: t("section.research.label"), short: t("section.research.label"), description: t("section.research.description") },
  { id: "community", label: t("section.community.label"), short: t("section.community.label"), description: t("section.community.description") },
  { id: "creator", label: t("section.creator.label"), short: t("section.creator.label"), description: t("section.creator.description") },
].filter((section) => !(IS_EN && section.id === "creator"));

const SECTION_BY_ID = Object.fromEntries(SECTION_DEFS.map((section) => [section.id, section]));

function fmtNumber(n) {
  return i18n.fmtNumber(n);
}

const UNSAFE_HARD_PATTERNS = [
  /\bcreampie\b/i,
  /\bblowjob\b/i,
  /\bsuck (?:your|my) (?:dick|cock)\b/i,
  /中出|婊子|吸你的鸡鸡|操虚拟女友/i,
];

const UNSAFE_PROMO_PATTERNS = [
  /\b(?:nsfw|nudes?|porn(?:ography)?)\b/i,
  /\buncensored pictures?\b/i,
  /\bvirtual girlfriends?\b/i,
  /\bknock her up\b/i,
  /未经审查的图片|虚拟女友|色情内容|成人内容/i,
];

function contentSafetyText(record) {
  return [
    record?.title,
    record?.title_zh,
    record?.title_en,
    record?.title_original,
    record?.source,
    record?.source_name,
  ].filter(Boolean).join(" ");
}

function isUnsafeContent(record) {
  const text = contentSafetyText(record);
  if (!text) return false;
  if (UNSAFE_HARD_PATTERNS.some((pattern) => pattern.test(text))) return true;
  return UNSAFE_PROMO_PATTERNS.filter((pattern) => pattern.test(text)).length >= 2;
}

// 英文版整体隐藏自媒体来源（itemSourceGroup 为 creator）：条目、故事、来源状态行都不展示。
function isLocaleHiddenItem(item) {
  return IS_EN && itemSourceGroup(item) === "creator";
}

function safeItems(items) {
  return (Array.isArray(items) ? items : []).filter((item) => !isUnsafeContent(item) && !isLocaleHiddenItem(item));
}

function isLocaleHiddenStory(story) {
  return IS_EN && itemSourceGroup(storyRepresentativeItem(story) || story) === "creator";
}

function isUnsafeStory(story) {
  const refs = [
    story,
    story?.primary_item,
    ...(Array.isArray(story?.sources) ? story.sources : []),
    ...(Array.isArray(story?.items) ? story.items : []),
  ].filter(Boolean);
  return refs.some((ref) => isUnsafeContent(ref));
}

// Today's projects are optional and load independently from the news timeline.
const todayProjectsListEl = document.getElementById("todayProjectsList");
const todayProjectsMetaEl = document.getElementById("todayProjectsMeta");

function todayProjectsDate(now = new Date()) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Taipei", year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(now);
  const value = (type) => parts.find((part) => part.type === type).value;
  return `${value("year")}-${value("month")}-${value("day")}`;
}

function todayProjectUrl(value) {
  if (typeof value !== "string") return "";
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
}

// 英文版只用英文推荐语（recommend_reason_en / en.reason），没有就不展示该项目，不回退中文。
function todayProjectReason(item) {
  return IS_EN ? (item.recommend_reason_en || item.en?.reason) : item.recommend_reason_zh;
}

function renderTodayProjects(payload, failed = false) {
  if (!todayProjectsListEl || !todayProjectsMetaEl) return;
  todayProjectsListEl.replaceChildren();
  todayProjectsMetaEl.textContent = "";
  const current = payload?.date === todayProjectsDate();
  const items = current && Array.isArray(payload?.items) ? payload.items : [];
  // Project names and recommendations need the same last-mile safety gate as news.
  const visible = safeItems(items.filter((item) => item && typeof item === "object").map((item) => ({
    ...item, title: item.project_name, title_zh: todayProjectReason(item), title_original: item.summary,
  }))).filter((item) => typeof item.project_name === "string" && item.project_name.trim()
    && typeof todayProjectReason(item) === "string" && todayProjectReason(item).trim()
    && todayProjectUrl(item.url)).slice(0, 4);
  if (!visible.length) {
    const empty = document.createElement("p");
    empty.className = "today-projects-empty";
    const sourcesFailed = Array.isArray(payload?.sources) && payload.sources.length > 0
      && payload.sources.every((source) => source?.ok === false);
    empty.textContent = failed || sourcesFailed ? t("today.failed")
      : payload && !current ? t("today.updating") : t("today.none");
    todayProjectsListEl.appendChild(empty);
    return;
  }
  todayProjectsMetaEl.textContent = t("today.count", { n: visible.length });
  visible.forEach((item) => {
    const card = document.createElement("article");
    card.className = "today-project-card";
    const heading = document.createElement("div");
    heading.className = "today-project-heading";
    const name = document.createElement("h3");
    name.textContent = item.project_name.trim();
    const source = document.createElement("span");
    source.className = "today-project-source";
    source.textContent = (item.site_name || t("today.sourceFallback"))
      + (item.site_id === "producthunt" && item.recency_basis === "updated_at" ? ` · ${t("today.recentUpdate")}` : "");
    heading.append(name, source);
    const recommendation = document.createElement("p");
    recommendation.className = "today-project-reason";
    recommendation.textContent = todayProjectReason(item).trim();
    const link = document.createElement("a");
    link.className = "today-project-link";
    link.href = todayProjectUrl(item.url);
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = t("today.open");
    link.setAttribute("aria-label", t("today.openAria", { name: item.project_name.trim() }));
    card.append(heading, recommendation, link);
    todayProjectsListEl.appendChild(card);
  });
}

async function initTodayProjects() {
  if (!todayProjectsListEl) return;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 12000);
  try {
    const res = await fetch(`${dataUrl("data/today-projects.json")}?t=${Date.now()}`, {
      signal: controller.signal,
    });
    if (!res.ok) throw new Error(t("error.load", { file: "today-projects.json", status: res.status }));
    const payload = await res.json();
    if (!payload || typeof payload.date !== "string" || !Array.isArray(payload.items)) {
      throw new Error(t("error.badFormat"));
    }
    renderTodayProjects(payload);
  } catch {
    renderTodayProjects(null, true);
  } finally {
    clearTimeout(timeout);
  }
}
// End of today's projects module.

function fmtTime(iso) {
  if (!iso) return t("common.unknownTime");
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return t("common.unknownTime");
  return new Intl.DateTimeFormat(LOCALE, IS_EN
    ? { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }
    : {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }).format(d);
}

function fmtDate(iso) {
  if (!iso) return t("common.unknownDate");
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat(LOCALE, IS_EN
    ? { month: "short", day: "numeric" }
    : {
      month: "2-digit",
      day: "2-digit",
    }).format(d);
}

function fmtHHMM(ms) {
  if (!ms) return "--:--";
  const d = new Date(ms);
  if (Number.isNaN(d.getTime())) return "--:--";
  return new Intl.DateTimeFormat(LOCALE, IS_EN
    ? { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }
    : { hour: "2-digit", minute: "2-digit", hour12: false }).format(d);
}

function fmtRelativeTime(ms) {
  return i18n.fmtRelative(ms);
}

// 条目“更新于 …”前缀与相对时间合并成一个可翻译串
function fmtUpdatedRelative(ms, withPrefix) {
  const rel = fmtRelativeTime(ms);
  return withPrefix ? t("rel.updatedAt", { time: rel }) : rel;
}

function failedSourceCount(status = state.sourceStatus) {
  const failedSites = Array.isArray(status?.failed_sites) ? status.failed_sites.length : 0;
  const rss = status?.rss_opml || {};
  const failedFeeds = Array.isArray(rss.failed_feeds) ? rss.failed_feeds.length : 0;
  return failedSites + failedFeeds;
}

function renderSourceStatusPill(errorMessage = "") {
  if (!sourceStatusPillEl) return;
  const status = state.sourceStatus;
  sourceStatusPillEl.className = "source-status-pill";
  if (!status) {
    sourceStatusPillEl.textContent = errorMessage || t("status.loading");
    if (errorMessage) sourceStatusPillEl.classList.add("bad");
    return;
  }
  const totalSites = Array.isArray(status.sites) ? status.sites.length : 0;
  const okSites = Number(status.successful_sites || 0);
  const failed = failedSourceCount(status);
  sourceStatusPillEl.textContent = failed
    ? t("status.okFailed", { ok: okSites, total: totalSites, failed })
    : t("status.ok", { ok: okSites, total: totalSites });
  if (failed) sourceStatusPillEl.classList.add("warn");
}

// 模式文案：精选（AI 相关合并事件池，纯时间序）/ 全量（原始条目池）
function modeLabelText() {
  return state.mode === "all" ? t("mode.all") : t("mode.selected");
}

function sourceKind(siteId) {
  return SOURCE_KINDS[siteId] || { label: t("common.source"), tone: "default" };
}

function sourceSignalTone(signal) {
  const text = String(signal || "").toLowerCase();
  if (text.includes("官方") || text.includes("official")) return "official";
  if (text.includes("ai hot") || text.includes("精选")) return "hot";
  if (text.includes("自媒体") || text.includes("tikhub") || text.includes("douyin") || text.includes("xiaohongshu") || text.includes("抖音") || text.includes("小红书")) return "creator";
  if (text.includes("builders") || text.includes("github") || text.includes("x")) return "builders";
  if (text.includes("aihub") || text.includes("aibase") || text.includes("媒体")) return "aihub";
  if (text.includes("hn") || text.includes("hacker") || text.includes("聚合")) return "aggregate";
  if (text.includes("opml") || text.includes("日报")) return "newsletter";
  return "default";
}

function sourceChip(label, tone = "default", className = "source-chip") {
  const chip = document.createElement("span");
  chip.className = `${className} kind-${tone}`.trim();
  const dot = document.createElement("span");
  dot.className = "source-dot";
  dot.setAttribute("aria-hidden", "true");
  const text = document.createElement("span");
  text.className = "source-chip-label";
  text.textContent = label || t("common.source");
  chip.append(dot, text);
  return chip;
}

function appendSourceChip(parent, label, tone = "default", className = "source-chip") {
  parent.appendChild(sourceChip(label, tone, className));
}

function siteRows() {
  return Array.isArray(state.sourceStatus?.sites) ? state.sourceStatus.sites : [];
}

function siteRow(siteId) {
  return siteRows().find((site) => site.site_id === siteId) || null;
}

function aiSiteStat(siteId) {
  const stats = safeAiSiteStats();
  return stats.find((site) => site.site_id === siteId) || null;
}

function safeAiSiteStats() {
  const visibleStats = computeSiteStats(safeItems(state.itemsAi));
  const visibleById = new Map(visibleStats.map((site) => [site.site_id, site]));
  const baseStats = Array.isArray(state.statsAi) && state.statsAi.length ? state.statsAi : visibleStats;
  return baseStats.map((site) => ({
    ...site,
    count: Number(visibleById.get(site.site_id)?.count || 0),
  }));
}

function siteAiPoolCount(siteId) {
  return Number(aiSiteStat(siteId)?.count || 0);
}

function activeAdjustmentCount() {
  return [
    Boolean(state.query.trim()),
    state.activeSection !== "all",
    Boolean(state.siteFilter || state.authorFilter),
    state.mode !== "selected",
    state.mode === "all" && !state.allDedup,
  ].filter(Boolean).length;
}

function renderClearFiltersButton() {
  if (!clearFiltersBtnEl) return;
  const count = activeAdjustmentCount();
  clearFiltersBtnEl.hidden = count === 0;
  clearFiltersBtnEl.textContent = count ? t("filters.clearN", { n: count }) : t("filters.clear");
}

// 数据同源指示：非空 dataBaseUrl 生效时提示当前数据源 + 提供一键恢复本地相对路径的入口。
function renderDataSourceIndicator() {
  if (!dataSourceIndicatorEl) return;
  const base = state.dataBaseUrl;
  dataSourceIndicatorEl.hidden = !base;
  if (base && dataSourceIndicatorTextEl) {
    dataSourceIndicatorTextEl.textContent = t("dataSource.label", { base });
  }
}

function clearAllFilters() {
  state.query = "";
  state.activeSection = "all";
  state.siteFilter = "";
  state.authorFilter = "";
  state.mode = "selected";
  state.allDedup = true;
  state.mainListVisibleCount = MAIN_LIST_PAGE_SIZE;
  state.waytoagiMode = "today";
  state.xAuthorsExpanded = false;
  if (searchInputEl) searchInputEl.value = "";
  if (siteSelectEl) siteSelectEl.value = "";
  rerenderCurrentView();
}

function computeSiteStats(items) {
  const m = new Map();
  items.forEach((item) => {
    if (!m.has(item.site_id)) {
      m.set(item.site_id, { site_id: item.site_id, site_name: item.site_name, count: 0, raw_count: 0 });
    }
    const row = m.get(item.site_id);
    row.count += 1;
    row.raw_count += 1;
  });
  return Array.from(m.values()).sort((a, b) => b.count - a.count || a.site_name.localeCompare(b.site_name, LOCALE));
}

// 具体来源下拉/站点 pill 的统计口径跟随当前模式：精选=AI 相关池，全量=原始条目池。
function currentSiteStats() {
  if (state.mode === "all") return computeSiteStats(effectiveAllItems());
  return safeAiSiteStats().filter((site) => site.count > 0);
}

function creatorHotScore(item) {
  return normalizedPercent(item?.creator_hot_score);
}

function highPriorityScore(item) {
  if (itemSourceGroup(item) === "creator" && creatorHotScore(item)) return creatorHotScore(item);
  return scorePercent(item);
}

function isHighPriorityItem(item) {
  return highPriorityScore(item) >= 75 || itemPriorityScore(item) >= 82 || item.site_id === "official_ai" || item.site_id === "aihot";
}

// tab 计数跟随当前模式的可见集合（忽略当前已选栏目本身，展示"如果点这个 tab 会有多少条"）
function sectionTabCount(sectionId) {
  if (state.mode === "all") {
    const pool = mainListRawItemsBase();
    return sectionId === "all" ? pool.length : pool.filter((item) => itemSection(item) === sectionId).length;
  }
  const pool = mainListStoriesBase();
  return sectionId === "all" ? pool.length : pool.filter((story) => storySectionOf(story) === sectionId).length;
}

function renderSectionTabs() {
  if (!sectionTabsEl) return;
  sectionTabsEl.innerHTML = "";
  SECTION_DEFS.forEach((section) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `section-tab ${state.activeSection === section.id ? "active" : ""}`;
    btn.setAttribute("role", "tab");
    btn.setAttribute("aria-selected", state.activeSection === section.id ? "true" : "false");
    btn.dataset.section = section.id;
    btn.innerHTML = `<span>${section.label}</span><strong>${fmtNumber(sectionTabCount(section.id))}</strong>`;
    btn.addEventListener("click", () => {
      if (state.activeSection === section.id) return;
      state.activeSection = section.id;
      state.mainListVisibleCount = MAIN_LIST_PAGE_SIZE;
      renderSectionTabs();
      renderModeSwitch();
      renderSiteFilters();
      renderHotBoard();
      if (state.waytoagiData) renderWaytoagi(state.waytoagiData);
      renderMainList();
    });
    sectionTabsEl.appendChild(btn);
  });
}


function siteRatioText(siteStats) {
  const count = Number(siteStats.count || 0);
  const raw = Number(siteStats.raw_count ?? siteStats.count ?? 0);
  if (!raw) {
    const scanned = Number(siteRow(siteStats.site_id)?.item_count || 0);
    if (!count && scanned) return t("site.scanned", { n: scanned });
    if (!count) return t("site.scannedZero");
    return t("count.items", { n: count });
  }
  if (raw === count) return t("count.items", { n: count });
  return t("site.ratio", { count, raw, pct: Math.round((count / raw) * 100) });
}

function renderSiteFilters() {
  const stats = currentSiteStats();

  siteSelectEl.innerHTML = `<option value="">${t("common.allSites")}</option>`;
  stats.forEach((s) => {
    const opt = document.createElement("option");
    opt.value = s.site_id;
    opt.textContent = `${s.site_name} (${siteRatioText(s)})`;
    siteSelectEl.appendChild(opt);
  });
  siteSelectEl.value = state.siteFilter;
}

// 全局 精选/全量 开关：热点排行区只在精选模式显示；主列表两种模式共用同一套时间序+日期分组模板。
function renderModeSwitch() {
  if (modeSelectedBtnEl) {
    modeSelectedBtnEl.classList.toggle("active", state.mode === "selected");
    modeSelectedBtnEl.setAttribute("aria-pressed", state.mode === "selected" ? "true" : "false");
  }
  if (modeAllBtnEl) {
    modeAllBtnEl.classList.toggle("active", state.mode === "all");
    modeAllBtnEl.setAttribute("aria-pressed", state.mode === "all" ? "true" : "false");
  }
  if (hotBoardWrapEl) hotBoardWrapEl.hidden = state.mode !== "selected";
  if (allDedupeWrapEl) allDedupeWrapEl.classList.toggle("show", state.mode === "all");
  if (allDedupeToggleEl) allDedupeToggleEl.checked = state.allDedup;
  if (allDedupeLabelEl) allDedupeLabelEl.textContent = state.allDedup ? t("mode.dedupOn") : t("mode.dedupOff");
  const count = mainListEntries().length;
  if (modeHintEl) {
    modeHintEl.textContent = t("mode.hint", { mode: modeLabelText(), n: count });
    modeHintEl.setAttribute("aria-label", t("mode.hintAria", { mode: modeLabelText(), n: count }));
  }
  if (listTitleEl) listTitleEl.textContent = listTitleText();
  renderClearFiltersButton();
}

function listTitleText() {
  const section = state.activeSection !== "all" ? SECTION_BY_ID[state.activeSection] : null;
  const label = modeLabelText();
  return section ? `${section.label} · ${label}` : label;
}

// 全量模式条目池：去重开=itemsAll（已去重），去重关=itemsAllRaw（原始单条池）
function effectiveAllItems() {
  return safeItems(state.allDedup ? state.itemsAll : state.itemsAllRaw);
}

function repairDisplayedTitle(original, translated) {
  let result = String(translated || "").trim();
  const source = String(original || "");
  if (/\bCodex\b/i.test(source)) result = result.replaceAll("法典", "Codex");
  if (/\bBug Bounty\b/i.test(source)) result = result.replaceAll("错误赏金", "漏洞悬赏").replaceAll("Bug 赏金", "漏洞悬赏");
  if (/\bBio Bug Bounty\b/i.test(source)) result = result.replaceAll("生物漏洞悬赏", "生物安全漏洞悬赏");
  if (/\brepositor(?:y|ies)\b/i.test(source)) result = result.replaceAll("存储库", "代码仓库");
  if (/\bdesktop app\b/i.test(source)) result = result.replaceAll("桌面应用程序", "桌面应用");
  return result;
}

function isMostlyEnglishTitle(text) {
  const value = String(text || "").trim();
  const latin = (value.match(/[A-Za-z]/g) || []).length;
  const cjk = (value.match(/[㐀-鿿]/g) || []).length;
  return latin >= 4 && latin > cjk * 2;
}

// 英文版标题：en.title → title_en（多数英文时）→ title_original → title（双语标题取英文段）。
// record 是条目或故事的 primary_item；fallbackTitle 用于 primary_item 没有 title 时回退故事标题。
function englishTitleText(record, fallbackTitle = "") {
  const translated = String(record?.en?.title || "").trim();
  if (translated) return translated;
  const titleEn = String(record?.title_en || "").trim();
  if (isMostlyEnglishTitle(titleEn)) return titleEn;
  const original = String(record?.title_original || "").trim();
  if (original) return original;
  const title = String(record?.title || fallbackTitle || "").trim();
  if (title.includes(" / ")) {
    const english = title.split(" / ").map((part) => part.trim()).find((part) => isMostlyEnglishTitle(part));
    if (english) return english;
  }
  return title || t("common.untitled");
}

function itemTitleText(item) {
  return IS_EN ? englishTitleText(item) : itemTitleTextZh(item);
}

function itemTitleTextZh(item) {
  const zhTitle = item.title_enhanced_zh || item.title_zh || "";
  const preferred = (zhTitle || item.title || item.title_en || t("common.untitled")).trim();
  const titleParts = preferred.includes(" / ") ? preferred.split(" / ") : [];
  const display = !zhTitle && titleParts.length ? titleParts[0].trim() : preferred;
  const original = item.title_en || item.title_original || (titleParts.length > 1 ? titleParts.slice(1).join(" / ") : "");
  return repairDisplayedTitle(original, display);
}

function itemOriginalTitleText(item) {
  // 英文版标题本身已是英文，不再出副标题
  if (IS_EN) return "";
  const explicit = String(item?.title_en || "").trim();
  if (isMostlyEnglishTitle(explicit) && explicit !== itemTitleTextZh(item)) return explicit;
  const bilingual = String(item?.title || item?.title_bilingual || "").trim();
  if (bilingual.includes(" / ")) {
    const [, ...rest] = bilingual.split(" / ");
    const original = rest.join(" / ").trim();
    if (isMostlyEnglishTitle(original) && original !== itemTitleTextZh(item)) return original;
  }
  const original = String(item?.title_original || "").trim();
  if (isMostlyEnglishTitle(original) && original !== itemTitleTextZh(item)) return original;
  return "";
}

function itemSummaryText(item, maxLength = 180) {
  const raw = IS_EN ? (item?.en?.summary || item?.summary) : item?.summary;
  const text = String(raw || "").replace(/\s+/g, " ").trim();
  if (!text) return "";
  return text.length > maxLength ? `${text.slice(0, maxLength - 1).trim()}…` : text;
}

function scorePercent(item) {
  const score = Number(item.ai_score ?? item.score ?? 0);
  if (!Number.isFinite(score) || score <= 0) return 0;
  return Math.round(score <= 1 ? score * 100 : score);
}

function normalizedPercent(value) {
  const score = Number(value);
  if (!Number.isFinite(score) || score <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round(score <= 1 ? score * 100 : score)));
}

function scoreTone(score) {
  if (score >= 90) return "hot";
  if (score >= 75) return "strong";
  return "watch";
}

function itemLabelTone(item) {
  const label = item.ai_label || "";
  if (item.site_id === "official_ai") return "official";
  if (item.site_id === "aihot" || label === "curated_hotlist") return "hot";
  if (itemSourceGroup(item) === "creator") return "creator";
  if (label === "model_release") return "models";
  if (label === "developer_tool" || label === "developer_tooling" || label === "infrastructure" || label === "infra_compute") return "devtools";
  if (label === "research_paper") return "research";
  if (label === "industry_business") return "industry";
  if (label === "ai_product_update" || label === "agent_workflow" || label === "robotics") return "products";
  return "default";
}

function itemTagTone(label) {
  const text = String(label || "");
  if (text.includes("多源")) return "strong";
  if (text.includes("官方")) return "official";
  if (text.includes("精选") || text.includes("热点")) return "hot";
  if (text.includes("HN")) return "aggregate";
  if (text.includes("模型")) return "models";
  if (text.includes("开发")) return "devtools";
  if (text.includes("研究")) return "research";
  if (text.includes("自媒体")) return "creator";
  if (text.includes("社区")) return "community";
  if (text.includes("产品")) return "products";
  if (text.includes("行业")) return "industry";
  return "default";
}

// 栏目 chip 的色调按栏目 id 取（与原先对中文短标签嗅探的结果一致），不随语言变化。
const SECTION_TAG_TONES = {
  all: "default",
  models: "models",
  products: "products",
  devtools: "devtools",
  industry: "industry",
  research: "default",
  community: "community",
  creator: "creator",
};

function itemTagChip(label, tone = itemTagTone(label)) {
  const tag = document.createElement("span");
  tag.className = `signal-tag tone-${tone}`;
  tag.textContent = label;
  return tag;
}

function setSourceBadge(el, label, tone = "default", title = "") {
  el.className = `source source-chip kind-${tone}`;
  el.innerHTML = "";
  if (title) el.title = title;
  const dot = document.createElement("span");
  dot.className = "source-dot";
  dot.setAttribute("aria-hidden", "true");
  const text = document.createElement("span");
  text.className = "source-chip-label";
  text.textContent = label || t("common.source");
  el.append(dot, text);
}

function sourceTierPercent(item) {
  if (item.site_id === "official_ai") return 100;
  if (item.site_id === "aihot") return 90;
  const rank = Number(item.source_tier_rank);
  if (!Number.isFinite(rank)) return 38;
  return Math.max(28, Math.min(86, 86 - rank * 9));
}

function editorialPercent(item) {
  const aihotScore = normalizedPercent(item.aihot_score);
  if (aihotScore) return aihotScore;
  if (item.site_id === "official_ai") return 90;
  if (item.site_id === "aihot") return 78;
  const internal = scorePercent(item);
  return internal ? Math.max(45, Math.round(internal * 0.72)) : 36;
}

function freshnessPercent(item, halfLifeHours = 48) {
  const ageMs = Date.now() - timelineMs(item);
  if (!Number.isFinite(ageMs) || ageMs < 0) return 100;
  const ageHours = ageMs / 3600000;
  return Math.max(0, Math.min(100, Math.round(100 * Math.pow(0.5, ageHours / halfLifeHours))));
}

function itemPriorityScore(item) {
  const creatorScore = creatorHotScore(item);
  if (creatorScore && itemSourceGroup(item) === "creator") return creatorScore;
  const internal = scorePercent(item);
  const editorial = editorialPercent(item);
  const source = sourceTierPercent(item);
  const freshness = freshnessPercent(item);
  const signal = Array.isArray(item.ai_signals) ? Math.min(100, item.ai_signals.length * 18) : 0;
  return Math.round((editorial * 0.3) + (source * 0.22) + (internal * 0.2) + (freshness * 0.18) + (signal * 0.1));
}

function labelText(item) {
  const key = `aiLabel.${item.ai_label}`;
  return (item.ai_label && i18n.has(key) ? t(key) : "") || item.ai_label || t("aiLabel.fallback");
}

// 故事的 importance_label 由 update_news.py 写成中文；按中文原文映射到 i18n（当前页面未渲染该字段，供复用）。
const IMPORTANCE_LABEL_KEYS = {
  "官方更新": "importance.official",
  "多源热议": "importance.multi_source",
  "行业动态": "importance.industry",
  "值得关注": "importance.watch",
};

function importanceLabelText(label) {
  const key = IMPORTANCE_LABEL_KEYS[label];
  return key ? t(key) : String(label || "");
}

function itemHaystack(item) {
  return [
    item.title,
    item.title_zh,
    item.title_en,
    item.title_original,
    item.source,
    item.site_name,
    item.site_id,
    item.ai_label,
    ...(Array.isArray(item.ai_signals) ? item.ai_signals : []),
  ].filter(Boolean).join(" ").toLowerCase();
}

function matchesAny(text, patterns) {
  return patterns.some((pattern) => pattern.test(text));
}

// 主题分类：优先用后端 ai_label，泛化标签走正则优先级（首个命中即停）
const AI_LABEL_SECTION_MAP = {
  model_release: "models",
  ai_product_update: "products",
  agent_workflow: "products",
  robotics: "products",
  developer_tool: "devtools",
  developer_tooling: "devtools",
  infra_compute: "devtools",
  research_paper: "research",
  industry_business: "industry",
};

const SECTION_FALLBACK_RULES = [
  ["research", [
    /paper|arxiv|research|benchmark|eval|dataset|lmsys|rdi|berkeley|huggingface daily papers|论文|研究|基准|评测|数据集|训练|k-means|speculative decoding/,
  ]],
  ["models", [
    /gpt[-\s]?\d|claude|gemini|grok|llama|qwen|deepseek|mistral|kimi\s?k\d|glm|gemma|模型|model|weights|权重|多模态|视频生成|diffusion|sora|seedance|llm|大模型/,
  ]],
  ["devtools", [
    /github|cursor|codex|copilot|openrouter|api|sdk|mcp|cli|framework|inference|推理|开发者|开源|代码|编程|算力|芯片|nvidia|cloud|部署|benchmarking|token/,
  ]],
  ["products", [
    /app|product|agent|workflow|siri|copilot|chatgpt|perplexity|runway|suno|支付宝|产品|应用|智能体|机器人|浏览器|搜索|助手|生成工具|办公|教育/,
  ]],
  ["industry", [
    /funding|raised|ipo|acquire|acquisition|lawsuit|regulation|policy|white house|pentagon|nvidia|salesforce|meta|microsoft|融资|收购|上市|监管|政策|裁员|估值|债券|芯片|公司|行业|政府|五角大楼|白宫/,
  ]],
];

// AIHOT 聚合器条目按原始平台粗分类（从 item.source 字符串推断），
// 供社区/自媒体归类与卡片小标签复用；无法识别时返回 null，不影响原有主题分类兜底。
function aihotSubSource(item) {
  if (!item || item.site_id !== "aihot") return null;
  const source = String(item.source || "");
  if (source.includes("公众号")) return "wechat";
  if (/^X[:：]/.test(source)) return "x";
  if (source.includes("Hacker News")) return "hn";
  if (/（RSS）\s*$/.test(source) || /\(RSS\)\s*$/.test(source)) return "rss";
  return null;
}

// X 作者身份统一：canonical identity = @handle（大小写不敏感提取，用于筛选/去重比较）。
// socialdata_x 的 source 本身就是裸 handle；aihot 转发的 X 帖子 source 形如 "X：Name (@handle)"。
function itemXAuthorSource(item) {
  if (!item) return null;
  if (item.site_id === "socialdata_x") return String(item.source || "").trim() || null;
  if (aihotSubSource(item) === "x") return String(item.source || "").trim() || null;
  return null;
}

function itemXAuthor(item) {
  const source = itemXAuthorSource(item);
  if (!source) return null;
  const match = source.match(/@([A-Za-z0-9_]+)/);
  return match ? `@${match[1]}` : null;
}

// 展示名：socialdata_x 只有裸 handle；aihot 去掉 "X：" 前缀后是更丰富的 "Name (@handle)"。
function itemXAuthorDisplay(item) {
  if (item?.site_id === "socialdata_x") {
    return String(item.source || "").trim() || null;
  }
  if (aihotSubSource(item) === "x") {
    return String(item.source || "").replace(/^X[:：]\s*/, "").trim() || null;
  }
  return null;
}

// 来源形态归类：自媒体 / 社区（HN + 中文技术社区），只看来源字段，不看标题内容
function itemSourceGroup(item) {
  const siteId = item.site_id || "";
  const aihotSub = aihotSubSource(item);
  if (aihotSub === "wechat") return "creator";
  if (aihotSub === "hn") return "community";
  const source = `${item.source || ""} ${item.site_name || ""}`.toLowerCase();
  if (
    siteId === "tikhub_douyin" ||
    siteId === "tikhub_xiaohongshu" ||
    source.includes("douyin") ||
    source.includes("xiaohongshu") ||
    source.includes("小红书") ||
    source.includes("抖音")
  ) return "creator";
  if (
    siteId === "hackernews" ||
    siteId === "zeli" ||
    siteId === "waytoagi" ||
    siteId === "followbuilders" ||
    siteId === "aibase" ||
    source.includes("hacker news") ||
    source.includes("hackernews") ||
    source.includes("hn algolia") ||
    source.includes("it之家") ||
    source.includes("36氪") ||
    source.includes("掘金") ||
    source.includes("readhub") ||
    source.includes("aibase") ||
    source.includes("公众号") ||
    source.includes("宝玉") ||
    source.includes("小互")
  ) return "community";
  return "other";
}

// 唯一分类入口：自媒体源 → 社区源 → 主题分类（AI_LABEL_SECTION_MAP/SECTION_FALLBACK_RULES）→ 兜底"全部"
// 每条 item 只落一个 tag；无法归入任何具体栏目的条目只在"全部"里可见，不强行塞进"行业"。
function itemSection(item) {
  const group = itemSourceGroup(item);
  if (group === "creator") return "creator";
  if (group === "community") return "community";
  const label = item.ai_label || "";
  const mapped = AI_LABEL_SECTION_MAP[label];
  if (mapped) return mapped;
  const hay = itemHaystack(item);
  for (const [sectionId, patterns] of SECTION_FALLBACK_RULES) {
    if (matchesAny(hay, patterns)) return sectionId;
  }
  return "all";
}

function itemMatchesSection(item, sectionId = state.activeSection) {
  return !sectionId || sectionId === "all" || itemSection(item) === sectionId;
}

function sectionBadgeLabel(sectionId) {
  return SECTION_BY_ID[sectionId]?.short || t("section.fallback");
}

// ---- 故事级辅助：按 primary_item（无则第一个 source）判定 ----
function storyRepresentativeItem(story) {
  if (!story) return null;
  if (story.primary_item && (story.primary_item.title || story.primary_item.url)) {
    const primary = story.primary_item;
    // primary_item 常缺 site_id/site_name：从 sources 里找同 url 的补全
    if (!primary.site_id && Array.isArray(story.sources)) {
      const match = story.sources.find((src) => src.url && src.url === primary.url) || story.sources[0];
      if (match) return { ...match, ...primary, site_id: match.site_id, site_name: match.site_name || match.source_name };
    }
    return primary;
  }
  if (Array.isArray(story.sources) && story.sources.length) return story.sources[0];
  return story;
}

function storySectionOf(story) {
  const rep = storyRepresentativeItem(story);
  return rep ? itemSection(rep) : "all";
}

function storyMatchesSection(story, sectionId = state.activeSection) {
  return !sectionId || sectionId === "all" || storySectionOf(story) === sectionId;
}

function storyMatchesQuery(story, query = state.query.trim().toLowerCase()) {
  if (!query) return true;
  const refs = [
    story,
    story.primary_item,
    ...(Array.isArray(story.sources) ? story.sources : []),
  ].filter(Boolean);
  return refs.some((ref) => {
    const hay = `${ref.title || ""} ${ref.title_zh || ""} ${ref.title_en || ""} ${ref.source || ""} ${ref.source_name || ""} ${ref.site_name || ""}`.toLowerCase();
    return hay.includes(query);
  });
}

// 站点等条目级筛选映射到故事：任意 source 命中即可
function storyMatchesSiteFilter(story) {
  if (!state.siteFilter && !state.authorFilter) return true;
  const refs = [
    storyRepresentativeItem(story),
    ...(Array.isArray(story.sources) ? story.sources : []),
  ].filter(Boolean);
  return refs.some((ref) => {
    if (state.siteFilter && ref.site_id !== state.siteFilter) return false;
    if (state.authorFilter && itemXAuthor(ref) !== state.authorFilter) return false;
    return true;
  });
}

function reasonText(item) {
  const creatorScore = creatorHotScore(item);
  if (creatorScore && itemSourceGroup(item) === "creator") {
    const metrics = item.creator_metrics || {};
    const parts = [
      t("reason.likes", { n: Number(metrics.likes) || 0 }),
      t("reason.collects", { n: Number(metrics.collects) || 0 }),
      t("reason.comments", { n: Number(metrics.comments) || 0 }),
      t("reason.shares", { n: Number(metrics.shares) || 0 }),
    ];
    if (Number(item.creator_freshness_bonus || 0) > 0) parts.push(t("reason.freshBonus"));
    return t("reason.creatorEngagement", { parts: parts.join(" · ") });
  }
  // 英文版只认 en.reason，不回退中文推荐语
  const recommendReason = String(IS_EN ? (item?.en?.reason || "") : (item?.recommend_reason_zh || "")).trim();
  if (recommendReason) return recommendReason;
  const signals = Array.isArray(item.ai_signals) ? item.ai_signals.filter(Boolean).slice(0, 3) : [];
  if (signals.length) return `${t("reason.signalsPrefix")}${signals.join(" / ")}`;
  if (item.ai_relevance_reason) return String(item.ai_relevance_reason).replaceAll("_", " ");
  return t("reason.default");
}

function timelineIso(item) {
  if (item.site_id === "producthunt" && item.recency_basis === "updated_at") return item.updated_at || "";
  const published = item.published_at || "";
  const seen = item.first_seen_at || "";
  const generated = state.generatedAt || "";
  if (published && generated) {
    const publishedMs = new Date(published).getTime();
    const generatedMs = new Date(generated).getTime();
    if (Number.isFinite(publishedMs) && Number.isFinite(generatedMs) && publishedMs > generatedMs + 10 * 60 * 1000) {
      return seen || published;
    }
  }
  return published || seen;
}

function timelineMs(item) {
  const d = new Date(timelineIso(item));
  return Number.isNaN(d.getTime()) ? 0 : d.getTime();
}

function normalizedEventText(text) {
  return String(text || "")
    .toLowerCase()
    .replace(/https?:\/\/\S+/g, "")
    .replace(/[\s　]+/g, "")
    .replace(/[，。、“”‘’：:；;！!？?（）()\[\]【】《》<>·.,/\\|_-]/g, "");
}

function eventKey(item) {
  // 事件去重键与语言无关，始终用中文站的标题取法，英文版切换标题不会改变合并结果
  const raw = itemTitleTextZh(item);
  const bracket = raw.match(/《([^》]{4,40})》/);
  if (bracket) return `book:${normalizedEventText(bracket[1]).slice(0, 36)}`;

  const normalized = normalizedEventText(raw);
  const model = normalized.match(/(bitcpmcann|deepseekv\d+(?:pro)?|grokv\d+(?:medium)?|gemini\d+(?:\.\d+)?(?:flash|pro)?|gpt\d+(?:\.\d+)?|llama\d+)/);
  if (model) return `entity:${model[1]}`;

  return `title:${normalized.slice(0, 34)}`;
}

function itemIdentityKeys(item) {
  const keys = new Set();
  if (!item) return keys;
  const url = item.url || item.primary_url;
  if (url) keys.add(`url:${url}`);
  if (item.id) keys.add(`id:${item.id}`);
  const title = item.title_zh || item.title || item.title_en || item.title_original;
  if (title) {
    keys.add(`event:${eventKey({ ...item, title, title_zh: item.title_zh || title })}`);
    keys.add(`title:${normalizedEventText(title).slice(0, 34)}`);
  }
  return keys;
}

function storyIdentityKeys(story) {
  const keys = new Set();
  if (!story) return keys;
  const refs = [
    { id: story.story_id, title: story.title, url: story.primary_url || story.url },
    story.primary_item,
    ...(Array.isArray(story.sources) ? story.sources : []),
    ...(Array.isArray(story.items) ? story.items : []),
  ].filter(Boolean);
  refs.forEach((ref) => {
    itemIdentityKeys(ref).forEach((key) => keys.add(key));
  });
  return keys;
}

function storyHasAnyKey(story, keys) {
  if (!keys || !keys.size) return false;
  for (const key of storyIdentityKeys(story)) {
    if (keys.has(key)) return true;
  }
  return false;
}

// sourceSignal 返回的是内部规范串（中文，供 sourceSignalTone 嗅探色调、去重用）；
// 展示时再经 sourceSignalLabel 翻译，保证语气色调逻辑不随语言变化。
const SOURCE_SIGNAL_KEYS = {
  "AI HOT精选": "signal.aihot",
  "HN热议": "signal.hn",
  "GitHub趋势": "signal.github",
  "官方更新": "signal.official",
  "抖音自媒体": "signal.douyin",
  "小红书自媒体": "signal.xiaohongshu",
  "来源": "common.source",
};

function sourceSignalLabel(signal) {
  const key = SOURCE_SIGNAL_KEYS[signal];
  return key ? t(key) : signal;
}

function sourceSignal(item) {
  const site = item.site_name || "";
  const source = item.source || "";
  const hay = `${site} ${source}`.toLowerCase();
  if (site === "AI HOT") return "AI HOT精选";
  if (hay.includes("hackernews") || hay.includes("hacker news")) return "HN热议";
  if (source.includes("GitHub · Trending Today") || hay.includes("github")) return "GitHub趋势";
  if (site === "Official AI Updates") return "官方更新";
  if (site === "Follow Builders") return "Builders";
  if (site === "TikHub Douyin" || hay.includes("tikhub douyin")) return "抖音自媒体";
  if (site === "TikHub Xiaohongshu" || hay.includes("tikhub xiaohongshu")) return "小红书自媒体";
  if (site === "AIbase") return "AIbase";
  if (site === "OPML RSS") return "OPML";
  return site || "来源";
}

function storyTimeMs(story, key) {
  const iso = story && story[key];
  if (!iso) return 0;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? 0 : d.getTime();
}

function storyScore(story) {
  const raw = (story && (story.importance_score ?? story.score ?? story.importance)) || 0;
  const score = Number(raw);
  if (!Number.isFinite(score) || score <= 0) return 0;
  return Math.round(score <= 1 ? score * 100 : score);
}

function storyPrimaryTitleText(story) {
  if (IS_EN) return englishTitleText((story && story.primary_item) || {}, story && story.title);
  const primary = (story && story.primary_item) || {};
  const explicit = String(primary.title_enhanced_zh || primary.title_zh || "").trim();
  const explicitOriginal = String(primary.title_en || primary.title_original || "").trim();
  if (explicit) return repairDisplayedTitle(explicitOriginal, explicit);
  const bilingual = String(primary.title || (story && story.title) || "").trim();
  if (bilingual.includes(" / ")) {
    const [zh, en] = bilingual.split(" / ");
    return repairDisplayedTitle(explicitOriginal || en, (zh || en || bilingual).trim());
  }
  return bilingual || t("common.untitled");
}

function storyPrimaryEnText(story) {
  if (IS_EN) return "";
  const primary = (story && story.primary_item) || {};
  const explicit = String(primary.title_en || primary.title_original || "").trim();
  if (isMostlyEnglishTitle(explicit) && explicit !== storyPrimaryTitleText(story)) return explicit;
  const bilingual = String(primary.title || (story && story.title) || "").trim();
  if (bilingual.includes(" / ")) {
    const [, en] = bilingual.split(" / ");
    const original = (en || "").trim();
    return isMostlyEnglishTitle(original) ? original : "";
  }
  return "";
}

function storySourceCount(story) {
  const sources = Array.isArray(story && story.sources) ? story.sources : [];
  const explicit = Number(story && story.duplicate_count);
  if (Number.isFinite(explicit) && explicit > 0) return explicit;
  return Math.max(1, sources.length);
}

// 同一事件展开：source_count>=2 的故事可以展开看每家独立报道（标题+来源+相对时间）。
// 去重：跳过 url 与主条目重复的信源（已经在卡片主体展示过），除非去重后一条不剩——
// 那种情况说明所有信源 url 都和主条目一致，只能保留原始 sources 列表兜底展示。
function dedupedStorySources(row) {
  const story = row && row.story;
  if (!story) return [];
  const sources = Array.isArray(story.sources) ? story.sources : [];
  const primaryUrl = (row.item && row.item.url) || story.primary_url || story.url || "";
  const filtered = primaryUrl ? sources.filter((src) => src && src.url !== primaryUrl) : sources;
  return filtered.length ? filtered : sources;
}

function buildEventSourceRow(source) {
  const row = document.createElement("div");
  row.className = "event-source-row";

  const titleLink = document.createElement("a");
  titleLink.className = "event-source-title";
  titleLink.href = source.url || "#";
  titleLink.target = "_blank";
  titleLink.rel = "noopener noreferrer";
  titleLink.textContent = itemTitleText(source);

  const nameEl = document.createElement("span");
  nameEl.className = "event-source-name";
  nameEl.textContent = source.source_name || source.site_name || source.source || t("common.source");

  const timeEl = document.createElement("span");
  timeEl.className = "event-source-time";
  timeEl.textContent = fmtUpdatedRelative(timelineMs(source), source.site_id === "producthunt" && source.recency_basis === "updated_at");

  row.append(titleLink, nameEl, timeEl);
  return row;
}

function buildEventSourceList(row) {
  const sources = dedupedStorySources(row);
  if (!sources.length) return null;
  const list = document.createElement("div");
  list.className = "event-expand-list";
  sources.forEach((source) => list.appendChild(buildEventSourceRow(source)));
  return list;
}

const PERSONA_NAMES = { pragmatic: t("persona.pragmatic"), cynic: t("persona.cynic"), "paper-police": t("persona.paperPolice") };

// 三口味 persona 的网页展示暂时下线（2026-07-15 归档，样式待重设计，见 docs/ROADMAP.md）。
// 数据管线（persona_score.py）与 Skill 端不受影响；置回 true 即恢复 TOP3 板块与卡片锐评行。
const PERSONA_UI_ENABLED = false;

// 锐评字段（persona_review/persona_id）由 persona_score.py 只写进 daily-brief.json；
// 主列表/热点榜的 story 对象来自 stories-merged.json，天然没有这两个字段，
// 必须按 story_id 回查每日精选才能拿到锐评。
let _briefByIdCache = null;
function briefStoryById(storyId) {
  if (!storyId) return null;
  if (!_briefByIdCache) {
    _briefByIdCache = new Map();
    briefStories().forEach((s) => {
      if (s && s.story_id) _briefByIdCache.set(s.story_id, s);
    });
  }
  return _briefByIdCache.get(storyId) || null;
}

function buildStoryPersonaLine(story) {
  let source = story;
  let reviewText = typeof story?.persona_review === "string" ? story.persona_review.trim() : "";
  if (!reviewText) {
    source = briefStoryById(story?.story_id);
    reviewText = typeof source?.persona_review === "string" ? source.persona_review.trim() : "";
  }
  if (!reviewText) return null;
  const line = document.createElement("div");
  line.className = "story-persona";
  const label = document.createElement("span");
  label.className = "story-persona-label";
  label.textContent = PERSONA_NAMES[source?.persona_id] || PERSONA_NAMES.pragmatic;
  const text = document.createElement("span");
  text.className = "story-persona-text";
  text.textContent = reviewText;
  line.append(label, text);
  return line;
}

function findTop3PersonaEntry(storyId) {
  if (!storyId) return null;
  const items = state.top3Personas?.items;
  if (!Array.isArray(items) || !items.length) return null;
  return items.find((entry) => entry && entry.story_id === storyId) || null;
}

function buildPersonaPanel(entry) {
  const reviews = entry?.reviews;
  if (!reviews || typeof reviews !== "object") return null;
  const panel = document.createElement("div");
  panel.className = "persona-panel";
  let cols = 0;
  Object.keys(PERSONA_NAMES).forEach((personaId) => {
    const review = reviews[personaId];
    if (!review || typeof review.review !== "string" || !review.review.trim()) return;
    const col = document.createElement("div");
    col.className = "persona-col";
    col.dataset.persona = personaId;
    const name = document.createElement("span");
    name.className = "persona-name";
    name.textContent = PERSONA_NAMES[personaId];
    const score = document.createElement("strong");
    score.className = "persona-score";
    score.textContent = Number.isFinite(Number(review.score)) ? String(review.score) : "-";
    const text = document.createElement("p");
    text.className = "persona-review";
    text.textContent = review.review.trim();
    col.append(name, score, text);
    panel.appendChild(col);
    cols += 1;
  });
  return cols > 0 ? panel : null;
}

const HOT_DECAY_HOURS = 12;
const HOT_SCORE_SCALE = 60;

function storyHotness(story) {
  const sources = storySourceCount(story);
  if (sources < 2) return 0;
  const latest = storyTimeMs(story, "latest_at") || storyTimeMs(story, "earliest_at");
  const ageHours = latest ? Math.max(0, (Date.now() - latest) / 3600000) : 24;
  return (sources - 1) * Math.exp(-ageHours / HOT_DECAY_HOURS);
}

function storyHotScore(story) {
  const raw = storyHotness(story);
  if (raw <= 0) return 0;
  return Math.max(1, Math.min(100, Math.round(raw * HOT_SCORE_SCALE)));
}

function hotStories(stories) {
  return stories
    .filter((story) => storyHotness(story) > 0)
    .sort((a, b) => {
      const byHotScore = storyHotScore(b) - storyHotScore(a);
      if (byHotScore !== 0) return byHotScore;
      const byHotRaw = storyHotness(b) - storyHotness(a);
      if (byHotRaw !== 0) return byHotRaw;
      const byEditorial = storyScore(b) - storyScore(a);
      if (byEditorial !== 0) return byEditorial;
      return storyTimeMs(b, "latest_at") - storyTimeMs(a, "latest_at");
    });
}

const HOT_BOARD_LIMIT = 20;

function briefStories() {
  return (Array.isArray(state.dailyBrief?.items) ? state.dailyBrief.items : []).filter((story) => !isUnsafeStory(story) && !isLocaleHiddenStory(story));
}

function mergedStories() {
  return (Array.isArray(state.storiesMerged?.stories) ? state.storiesMerged.stories : []).filter((story) => !isUnsafeStory(story) && !isLocaleHiddenStory(story));
}

// 精选徽章：故事命中每日精选（daily-brief.json）即视为"精选"来源，与分数徽章分开显示
let _briefIdentityKeyCache = null;
function briefIdentityKeySet() {
  if (_briefIdentityKeyCache) return _briefIdentityKeyCache;
  const keys = new Set();
  briefStories().forEach((story) => storyIdentityKeys(story).forEach((key) => keys.add(key)));
  _briefIdentityKeyCache = keys;
  return keys;
}
function isStoryCurated(story) {
  return storyHasAnyKey(story, briefIdentityKeySet());
}
function isCuratedSourceRef(ref) {
  if (!ref) return false;
  return ref.site_id === "official_ai" || ref.site_id === "aihot" || ref.source_tier === "official" || ref.source_tier === "curated";
}

// 热点排行区候选池：stories-merged 中 source_count>=2，按热度降序（不含栏目过滤，供 tab 计数复用）
function hotBoardStories() {
  return hotStories(mergedStories().filter((story) =>
    storySourceCount(story) >= 2 &&
    storyMatchesSiteFilter(story) &&
    storyMatchesQuery(story)));
}

function hotBoardEntries() {
  if (state.mode !== "selected") return [];
  return hotBoardStories()
    .filter((story) => storyMatchesSection(story))
    .slice(0, HOT_BOARD_LIMIT)
    .map((story, index) => storyToRow(story, index));
}

// ---- 主列表数据池：精选模式=mergedStories() 全量（纯时间倒序），全量模式=原始条目池 ----

function mainListStoriesBase() {
  return mergedStories().filter((story) => storyMatchesSiteFilter(story) && storyMatchesQuery(story));
}

function mainListRawItemsBase() {
  const q = state.query.trim().toLowerCase();
  return effectiveAllItems().filter((item) => {
    if (state.siteFilter && item.site_id !== state.siteFilter) return false;
    if (state.authorFilter && itemXAuthor(item) !== state.authorFilter) return false;
    if (!q) return true;
    return itemHaystack(item).includes(q);
  });
}

function mainListStories() {
  return mainListStoriesBase().filter((story) => storyMatchesSection(story));
}

function mainListRawItems() {
  return mainListRawItemsBase().filter((item) => itemMatchesSection(item));
}

// 故事 → 统一行模型（供 renderItemNode 消费）：代表条目 + 全部信源信号 + 故事引用
function storyToRow(story, index = 0) {
  const enrichStoryItem = (entry) => ({
    ...entry,
    site_name: entry.site_name || entry.source_name || story.source_name || "",
  });
  const item = enrichStoryItem(storyRepresentativeItem(story) || story);
  const sourceItems = [
    item,
    ...(Array.isArray(story.sources) ? story.sources.map(enrichStoryItem) : []),
  ].filter(Boolean);
  const sourceSignals = Array.from(new Set(sourceItems.map(sourceSignal)));
  return {
    item,
    index,
    story,
    rows: sourceItems.map((sourceItem) => ({ item: sourceItem })),
    sourceSignals,
    sourceCount: storySourceCount(story),
    mergedCount: Math.max(1, Number(story.duplicate_count) || sourceItems.length),
    score: storyScore(story),
  };
}

// 原始条目 → 统一行模型：无故事引用，渲染时优雅降级（不展示精选徽章/分数/为什么重要）
function itemToRow(item, index = 0) {
  return {
    item,
    index,
    story: null,
    rows: [{ item }],
    sourceSignals: [sourceSignal(item)],
    sourceCount: 1,
    mergedCount: 1,
    score: 0,
  };
}

function mainListEntries() {
  if (state.mode === "all") {
    return mainListRawItems().map((item, index) => {
      const ms = timelineMs(item);
      return { row: itemToRow(item, index), timeMs: ms };
    }).sort((a, b) => b.timeMs - a.timeMs);
  }
  return mainListStories().map((story, index) => {
    const ms = storyTimeMs(story, "latest_at") || storyTimeMs(story, "earliest_at");
    return { row: storyToRow(story, index), timeMs: ms };
  }).sort((a, b) => b.timeMs - a.timeMs);
}

function dateGroupKey(ms) {
  if (!ms) return "unknown";
  const d = new Date(ms);
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

function dateGroupLabel(ms) {
  if (!ms) return t("common.unknownTime");
  const d = new Date(ms);
  const now = new Date();
  const sameYear = d.getFullYear() === now.getFullYear();
  return new Intl.DateTimeFormat(LOCALE, sameYear
    ? { month: "long", day: "numeric" }
    : { year: "numeric", month: "long", day: "numeric" }).format(d);
}

function dateGroupWeekday(ms) {
  if (!ms) return "";
  return new Intl.DateTimeFormat(LOCALE, { weekday: "long" }).format(new Date(ms));
}

function itemSourceRefs(item, row = null) {
  const refs = [];
  const seen = new Set();
  const add = (label, tone) => {
    const clean = String(label || "").trim();
    if (!clean) return;
    const key = `${tone}:${clean}`;
    if (seen.has(key)) return;
    seen.add(key);
    refs.push({ label: clean, tone });
  };

  if (row && Array.isArray(row.sourceSignals) && row.sourceSignals.length) {
    row.sourceSignals.forEach((signal) => add(signal, sourceSignalTone(signal)));
  } else if (row && Array.isArray(row.rows) && row.rows.length) {
    row.rows.forEach((entry) => {
      const sourceItem = entry.item || {};
      const kind = sourceKind(sourceItem.site_id);
      add(sourceItem.source || sourceItem.site_name || kind.label, kind.tone);
    });
  } else {
    const kind = sourceKind(item.site_id);
    add(item.source || item.site_name || kind.label, kind.tone);
  }

  return refs.length ? refs : [{ label: t("common.source"), tone: "default" }];
}

function rowSourceCount(row) {
  const item = row.item || {};
  const refs = itemSourceRefs(item, row);
  const storyCount = row.story ? storySourceCount(row.story) : 0;
  return Math.max(1, refs.length, Number(row.sourceCount || 0), Number(row.mergedCount || 0), storyCount);
}

function escapeRegExp(text) {
  return String(text).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function signalSummaryText(row) {
  const item = row.item || {};
  const story = row.story || {};
  const editorialSummary = itemSummaryText(item) || itemSummaryText(story.primary_item || {});
  if (editorialSummary) return editorialSummary;
  const reason = reasonText(item);
  if (reason && reason !== t("reason.default")) return reason.replace(new RegExp(`^${escapeRegExp(t("reason.signalsPrefix"))}`), t("reason.corePrefix"));
  return "";
}

// 只返回真实的、条目级别的推荐理由（item.recommend_reason_zh 或 story.primary_item.recommend_reason_zh）。
// 这类数据是预算受限的窄池，多数条目没有——没有真实理由时必须返回空字符串，
// 不再用分区/来源信号拼出通用模板句子（那类句子读起来像针对该条目的判断，实际是套话，参见调用方 renderItemNode 的隐藏逻辑）。
function whyImportantText(row) {
  const item = row.item || {};
  const story = row.story || {};
  // 英文版只认 en.reason，没有就返回空串（不显示 why-box），不回退中文
  const recommendReason = String(
    IS_EN
      ? (item.en?.reason || story.primary_item?.en?.reason || "")
      : (item.recommend_reason_zh || story.primary_item?.recommend_reason_zh || "")
  ).trim();
  return recommendReason;
}

function feedSummaryText(item) {
  const editorialSummary = itemSummaryText(item);
  if (editorialSummary) return editorialSummary;
  const signals = Array.isArray(item.ai_signals) ? item.ai_signals.filter(Boolean).slice(0, 2) : [];
  if (signals.length) return t("reason.clues", { signals: signals.join(" / ") });
  const reason = reasonText(item);
  if (reason && reason !== t("reason.default")) return reason.replace(new RegExp(`^${escapeRegExp(t("reason.signalsPrefix"))}`), t("reason.cluePrefix"));
  return "";
}

// 共享卡片组件：唯一渲染入口，主列表（精选/全量）共用同一基础变体。
// row.story 存在时展示精选徽章/分数/为什么重要/persona 面板；row.story 为空（全量原始条目）时优雅降级，跳过这些区块。
// 热点排行区改用 buildHotRow（单行行式渲染），不再走这个卡片模板。
function renderItemNode(row) {
  const node = itemTpl.content.firstElementChild.cloneNode(true);
  const item = row.item || {};

  const metaRow = node.querySelector(".meta-row");

  const curatedEl = node.querySelector(".curated-badge");
  const curatedRefs = [item, ...(row.story && Array.isArray(row.story.sources) ? row.story.sources : [])];
  const curated = (row.story && isStoryCurated(row.story)) || curatedRefs.some(isCuratedSourceRef);
  curatedEl.hidden = !curated;

  const siteEl = node.querySelector(".site");
  siteEl.textContent = item.source || item.site_name || "";

  const sourceEl = node.querySelector(".source");
  const sourceLabel = sourceSignal(item);
  setSourceBadge(sourceEl, sourceSignalLabel(sourceLabel), sourceSignalTone(sourceLabel), item.source ? t("item.sourceTitle", { source: item.source }) : "");
  if (rowSourceCount(row) > 1) {
    sourceEl.title = `${sourceEl.title || ""} · ${t("item.multiTotal", { n: rowSourceCount(row) })}`.replace(/^ · /, "");
  }

  // aihot 子来源 chip（X/公众号/HN/RSS）紧跟通道 chip（.source）之后，色调复用既有 .category.kind-* 规则，不新增样式。
  let metaAnchorEl = sourceEl;
  const aihotSub = aihotSubSource(item);
  if (aihotSub) {
    const subChip = document.createElement("span");
    subChip.className = `category kind-${AIHOT_SUB_TONES[aihotSub]}`;
    subChip.textContent = AIHOT_SUB_LABELS[aihotSub];
    metaAnchorEl.insertAdjacentElement("afterend", subChip);
    metaAnchorEl = subChip;
  }

  // 多源 chip：source_count>=2 时出现，紧跟通道/子来源 chip 之后，同时充当"同一事件"展开/收起触发器
  // （取代旧的独立 event-expand-toggle）。子列表挂在 news-card-body 末尾，首次点击才建 DOM，之后本地 toggle。
  if (row.story && storySourceCount(row.story) >= 2) {
    const bodyEl = node.querySelector(".news-card-body") || node;
    const eventCount = storySourceCount(row.story);
    const collapsedLabel = t("item.multiCollapsed", { n: eventCount });
    const expandedLabel = t("item.multiExpanded", { n: eventCount });
    const multiChip = document.createElement("button");
    multiChip.type = "button";
    multiChip.className = "multi-chip";
    multiChip.textContent = collapsedLabel;
    multiChip.setAttribute("aria-expanded", "false");
    let eventList = null;
    multiChip.addEventListener("click", () => {
      const expanded = multiChip.getAttribute("aria-expanded") === "true";
      if (expanded) {
        if (eventList) eventList.hidden = true;
        multiChip.setAttribute("aria-expanded", "false");
        multiChip.textContent = collapsedLabel;
        return;
      }
      if (!eventList) {
        eventList = buildEventSourceList(row);
        if (eventList) bodyEl.appendChild(eventList);
      }
      if (!eventList) return;
      eventList.hidden = false;
      multiChip.setAttribute("aria-expanded", "true");
      multiChip.textContent = expandedLabel;
    });
    metaAnchorEl.insertAdjacentElement("afterend", multiChip);
  }

  const scoreEl = node.querySelector(".score-badge");
  const displayScore = row.score;
  if (displayScore > 0) {
    scoreEl.hidden = false;
    scoreEl.textContent = t("item.score", { n: displayScore });
    scoreEl.className = `score-badge tone-${scoreTone(displayScore)}`;
  } else {
    scoreEl.hidden = true;
  }

  // 栏目 chip（行业/模型/产品...）是 meta-row 的最后一个 chip，appendChild 保证排在 score-badge 之后、
  // 在下面的"查看原文"链接（margin-left: auto 靠右）之前。
  const sectionId = itemSection(item);
  const sectionChip = itemTagChip(sectionBadgeLabel(sectionId), SECTION_TAG_TONES[sectionId] || "default");
  metaRow.appendChild(sectionChip);

  const titleEl = node.querySelector(".title");
  const displayTitle = row.story ? storyPrimaryTitleText(row.story) : itemTitleText(item);
  const originalTitle = row.story ? storyPrimaryEnText(row.story) : itemOriginalTitleText(item);
  titleEl.textContent = "";
  if (originalTitle) {
    const primary = document.createElement("span");
    primary.textContent = displayTitle;
    const sub = document.createElement("span");
    sub.className = "title-sub";
    sub.textContent = originalTitle;
    titleEl.appendChild(primary);
    titleEl.appendChild(sub);
  } else {
    titleEl.textContent = displayTitle;
  }
  titleEl.href = item.url || row.story?.primary_url || row.story?.url || "#";

  const summaryEl = node.querySelector(".news-summary");
  if (summaryEl) {
    const summaryText = row.story ? signalSummaryText(row) : feedSummaryText(item);
    summaryEl.textContent = summaryText;
    summaryEl.hidden = !summaryText;
  }

  const whyBox = node.querySelector(".why-box");
  const whyText = row.story ? whyImportantText(row) : "";
  if (whyText) {
    whyBox.hidden = false;
    node.querySelector(".why-text").textContent = whyText;
  } else {
    whyBox.hidden = true;
  }

  const personaSlot = node.querySelector(".persona-slot");
  if (row.story && PERSONA_UI_ENABLED) {
    const personaEntry = findTop3PersonaEntry(row.story.story_id);
    const personaPanel = buildPersonaPanel(personaEntry);
    if (personaPanel) {
      // TOP3 三口味面板已含默认口味整列，再显示单条锐评行就是原句重复
      personaSlot.appendChild(personaPanel);
    } else {
      const personaLine = buildStoryPersonaLine(row.story);
      if (personaLine) personaSlot.appendChild(personaLine);
    }
  }

  const originalLink = document.createElement("a");
  originalLink.className = "original-link original-action";
  originalLink.href = item.url || row.story?.primary_url || row.story?.url || "#";
  originalLink.target = "_blank";
  originalLink.rel = "noopener noreferrer";
  originalLink.textContent = t("item.original");
  metaRow.appendChild(originalLink);

  return node;
}

// 热点排行区：一行一条（rank + 标题链接 + 信源数 · 相对时间），不复用卡片模板——
// 避免和下方精选列表的完整卡片重复展示摘要/标签/为什么重要。
function buildHotRow(row, rank) {
  const item = row.item || {};
  const el = document.createElement("div");
  el.className = "hot-row";

  const rankEl = document.createElement("span");
  rankEl.className = "hot-row-rank";
  rankEl.textContent = `#${rank}`;

  const titleEl = document.createElement("a");
  titleEl.className = "hot-row-title";
  titleEl.target = "_blank";
  titleEl.rel = "noopener noreferrer";
  const displayTitle = row.story ? storyPrimaryTitleText(row.story) : itemTitleText(item);
  titleEl.textContent = displayTitle;
  titleEl.title = displayTitle;
  titleEl.href = item.url || row.story?.primary_url || row.story?.url || "#";

  const metaEl = document.createElement("span");
  metaEl.className = "hot-row-meta";
  const sourceCount = rowSourceCount(row);
  const relTime = fmtUpdatedRelative(
    timelineMs(item) || storyTimeMs(row.story, "latest_at"),
    item.site_id === "producthunt" && item.recency_basis === "updated_at",
  );

  // 同一事件展开：热点行的"N 个信源"变成可点击项，点击在 .hot-row 正下方插入/移除同一份子列表组件。
  const expandable = row.story && storySourceCount(row.story) >= 2;
  if (expandable) {
    const sourceToggle = document.createElement("button");
    sourceToggle.type = "button";
    sourceToggle.className = "hot-row-source-toggle";
    sourceToggle.textContent = t("hot.sources", { n: sourceCount });
    sourceToggle.setAttribute("aria-expanded", "false");
    let sourceList = null;
    sourceToggle.addEventListener("click", (evt) => {
      evt.preventDefault();
      evt.stopPropagation();
      if (sourceList) {
        sourceList.remove();
        sourceList = null;
        sourceToggle.setAttribute("aria-expanded", "false");
        return;
      }
      sourceList = buildEventSourceList(row);
      if (!sourceList) return;
      sourceList.classList.add("hot-row-source-list");
      sourceToggle.setAttribute("aria-expanded", "true");
      el.insertAdjacentElement("afterend", sourceList);
    });
    const sep = document.createElement("span");
    sep.textContent = " · ";
    const timeEl = document.createElement("span");
    timeEl.textContent = relTime;
    metaEl.append(sourceToggle, sep, timeEl);
  } else {
    metaEl.textContent = `${t("hot.sources", { n: sourceCount })} · ${relTime}`;
  }

  el.append(rankEl, titleEl, metaEl);
  return el;
}

function renderLoadingNotice(label, count) {
  const loading = document.createElement("div");
  loading.className = "list-loading";
  loading.textContent = t("list.loading", { label, n: count });
  newsListEl.appendChild(loading);
}

function addLoadMoreButton(parent, label, onClick) {
  const moreBtn = document.createElement("button");
  moreBtn.type = "button";
  moreBtn.className = "list-more-btn";
  moreBtn.textContent = label;
  moreBtn.addEventListener("click", onClick);
  parent.appendChild(moreBtn);
  return moreBtn;
}

// Mobile-safe async rendering: avoid blocking the main thread on large lists.
// requestAnimationFrame 在后台标签页不触发，hidden 时降级 setTimeout，避免列表卡在加载态。
function scheduleRender(cb) {
  if (document.hidden) {
    setTimeout(cb, 0);
  } else {
    requestAnimationFrame(cb);
  }
}
let _renderListToken = 0;
const MAIN_LIST_PAGE_SIZE = 60;
state.mainListVisibleCount = MAIN_LIST_PAGE_SIZE;

// 主列表：纯时间倒序 + 按日期分组渲染，精选/全量两种模式共用同一套模板。
function renderMainList() {
  const entries = mainListEntries();
  resultCountEl.textContent = t("count.items", { n: entries.length });
  renderClearFiltersButton();
  if (modeHintEl) {
    modeHintEl.textContent = t("mode.hint", { mode: modeLabelText(), n: entries.length });
    modeHintEl.setAttribute("aria-label", t("mode.hintAria", { mode: modeLabelText(), n: entries.length }));
  }

  newsListEl.innerHTML = "";
  _renderListToken += 1;
  const token = _renderListToken;

  if (!entries.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    const title = document.createElement("h3");
    title.textContent = t("list.emptyTitle");
    const message = document.createElement("p");
    message.textContent = t("list.emptyMessage");
    empty.append(title, message);
    if (activeAdjustmentCount()) {
      const reset = document.createElement("button");
      reset.type = "button";
      reset.className = "empty-reset-btn";
      reset.textContent = t("list.emptyReset");
      reset.addEventListener("click", clearAllFilters);
      empty.appendChild(reset);
    }
    newsListEl.appendChild(empty);
    return;
  }

  renderLoadingNotice(listTitleText(), entries.length);
  scheduleRender(() => {
    if (token !== _renderListToken) return;
    newsListEl.innerHTML = "";
    const visibleCount = Math.max(MAIN_LIST_PAGE_SIZE, state.mainListVisibleCount || MAIN_LIST_PAGE_SIZE);
    const visible = entries.slice(0, visibleCount);
    const dateGroupCounts = new Map();
    visible.forEach(({ timeMs }) => {
      const key = dateGroupKey(timeMs);
      dateGroupCounts.set(key, (dateGroupCounts.get(key) || 0) + 1);
    });
    let lastKey = null;
    const frag = document.createDocumentFragment();
    visible.forEach(({ row, timeMs }) => {
      const key = dateGroupKey(timeMs);
      if (key !== lastKey) {
        const header = document.createElement("div");
        header.className = "date-group-header";
        const dateLabel = document.createElement("span");
        dateLabel.textContent = dateGroupLabel(timeMs);
        header.appendChild(dateLabel);
        const weekday = dateGroupWeekday(timeMs);
        const count = dateGroupCounts.get(key) || 0;
        const meta = document.createElement("span");
        meta.className = "date-group-meta";
        meta.textContent = weekday ? `· ${weekday} · ${t("count.items", { n: count })}` : `· ${t("count.items", { n: count })}`;
        header.appendChild(meta);
        frag.appendChild(header);
        lastKey = key;
      }
      const timelineItem = document.createElement("div");
      timelineItem.className = "timeline-item";
      const rail = document.createElement("div");
      rail.className = "timeline-rail";
      const timeLabel = document.createElement("span");
      timeLabel.className = "timeline-time";
      timeLabel.textContent = fmtHHMM(timeMs);
      const dot = document.createElement("span");
      dot.className = "timeline-dot";
      rail.append(timeLabel, dot);
      timelineItem.appendChild(rail);
      timelineItem.appendChild(renderItemNode(row));
      frag.appendChild(timelineItem);
    });
    newsListEl.appendChild(frag);
    if (entries.length > visible.length) {
      addLoadMoreButton(
        newsListEl,
        t("list.more", { n: entries.length - visible.length }),
        () => {
          state.mainListVisibleCount = visibleCount + MAIN_LIST_PAGE_SIZE;
          renderMainList();
        },
      );
    }
    document.dispatchEvent(new CustomEvent("aiRadar:listRendered"));
  });
}

function top3BoardEntries() {
  if (state.mode !== "selected") return [];
  const t3 = state.top3Personas?.items;
  if (!Array.isArray(t3) || !t3.length) return [];
  const byId = new Map(mergedStories().map((s) => [s.story_id, s]));
  return t3
    .slice()
    .sort((a, b) => (Number(a.rank) || 0) - (Number(b.rank) || 0))
    .map((entry) => byId.get(entry?.story_id))
    .filter(Boolean)
    .map((story, index) => storyToRow(story, index));
}

// 今日 TOP3 板块：三口味并排锐评的固定展示入口。TOP3 卡片在主列表里按时间排序，
// 常沉在几屏之外（用户翻不到，面板等于隐身），所以命中 top3-personas.json 的故事在这里置顶再展示一次。
function renderTop3Board() {
  if (!top3BoardListEl) return;
  const rows = PERSONA_UI_ENABLED ? top3BoardEntries() : [];
  const show = rows.length > 0;
  if (top3BoardWrapEl) top3BoardWrapEl.hidden = !show;
  if (!show) return;
  if (top3BoardMetaEl) top3BoardMetaEl.textContent = Object.values(PERSONA_NAMES).join(" · ");
  top3BoardListEl.innerHTML = "";
  rows.forEach((row) => top3BoardListEl.appendChild(renderItemNode(row)));
}

// 热点排行区：不设固定条数，展示条数取决于当前有多少条满足多信源热度阈值（HOT_BOARD_LIMIT 只是技术兜底）。
function renderHotBoard() {
  renderTop3Board();
  if (!hotBoardListEl) return;
  const show = state.mode === "selected";
  if (hotBoardWrapEl) hotBoardWrapEl.hidden = !show;
  if (!show) return;
  hotBoardListEl.innerHTML = "";

  const rows = hotBoardEntries();
  if (hotBoardMetaEl) {
    hotBoardMetaEl.textContent = rows.length
      ? t("hot.meta", { n: rows.length })
      : t("hot.metaDefault");
  }

  if (!rows.length) {
    const empty = document.createElement("div");
    empty.className = "bole-empty";
    empty.textContent = t("hot.empty");
    hotBoardListEl.appendChild(empty);
    return;
  }

  rows.forEach((row, index) => {
    hotBoardListEl.appendChild(buildHotRow(row, index + 1));
  });
}

function rerenderCurrentView() {
  state.mainListVisibleCount = MAIN_LIST_PAGE_SIZE;
  renderSectionTabs();
  renderModeSwitch();
  renderSiteFilters();
  renderHotBoard();
  if (state.waytoagiData) renderWaytoagi(state.waytoagiData);
  renderMainList();
}

function waytoagiViews(waytoagi) {
  const updates7d = Array.isArray(waytoagi?.updates_7d) ? waytoagi.updates_7d : [];
  const latestDate = waytoagi?.latest_date || (updates7d.length ? updates7d[0].date : null);
  const updatesToday = Array.isArray(waytoagi?.updates_today) && waytoagi.updates_today.length
    ? waytoagi.updates_today
    : (latestDate ? updates7d.filter((u) => u.date === latestDate) : []);
  return { updates7d, updatesToday, latestDate };
}

function renderWaytoagi(waytoagi) {
  // 内容 tab 已收敛为单层：WaytoAGI 面板跟随「社区」tab 显示（合并了原来源形态 cn 分组）
  // 英文版不展示 WaytoAGI（中文原生社区内容，不翻译），与自媒体区块同口径
  if (IS_EN) {
    if (waytoagiWrapEl) waytoagiWrapEl.hidden = true;
    return;
  }
  if (waytoagiWrapEl) {
    waytoagiWrapEl.hidden = state.activeSection !== "community";
  }
  if (state.activeSection !== "community") return;
  const { updates7d, updatesToday, latestDate } = waytoagiViews(waytoagi);
  if (waytoagiTodayBtnEl) waytoagiTodayBtnEl.classList.toggle("active", state.waytoagiMode === "today");
  if (waytoagi7dBtnEl) waytoagi7dBtnEl.classList.toggle("active", state.waytoagiMode === "7d");
  if (waytoagiTodayBtnEl) waytoagiTodayBtnEl.setAttribute("aria-pressed", state.waytoagiMode === "today" ? "true" : "false");
  if (waytoagi7dBtnEl) waytoagi7dBtnEl.setAttribute("aria-pressed", state.waytoagiMode === "7d" ? "true" : "false");
  waytoagiUpdatedAtEl.textContent = t("waytoagi.updatedAt", { time: fmtTime(waytoagi.generated_at) });

  waytoagiMetaEl.innerHTML = "";
  const rootLink = document.createElement("a");
  rootLink.href = waytoagi.root_url || "#";
  rootLink.target = "_blank";
  rootLink.rel = "noopener noreferrer";
  rootLink.textContent = t("waytoagi.root");
  const historyLink = document.createElement("a");
  historyLink.href = waytoagi.history_url || "#";
  historyLink.target = "_blank";
  historyLink.rel = "noopener noreferrer";
  historyLink.textContent = t("waytoagi.history");
  const todayCount = document.createElement("span");
  todayCount.textContent = t("waytoagi.today", { date: latestDate || "--", n: waytoagi.count_today || updatesToday.length });
  const weekCount = document.createElement("span");
  weekCount.textContent = t("waytoagi.week", { n: waytoagi.count_7d || updates7d.length });
  [rootLink, "·", historyLink, "·", todayCount, "·", weekCount].forEach((part) => {
    if (typeof part === "string") {
      const sep = document.createElement("span");
      sep.textContent = part;
      waytoagiMetaEl.appendChild(sep);
    } else {
      waytoagiMetaEl.appendChild(part);
    }
  });

  waytoagiListEl.innerHTML = "";
  if (waytoagi.has_error) {
    const div = document.createElement("div");
    div.className = "waytoagi-error";
    div.textContent = waytoagi.error || t("waytoagi.error");
    waytoagiListEl.appendChild(div);
    return;
  }

  const updates = state.waytoagiMode === "today" ? updatesToday : updates7d;
  if (!updates.length) {
    const div = document.createElement("div");
    div.className = "waytoagi-empty";
    div.textContent = state.waytoagiMode === "today"
      ? t("waytoagi.emptyToday")
      : (waytoagi.warning || t("waytoagi.empty7d"));
    waytoagiListEl.appendChild(div);
    return;
  }

  updates.forEach((u) => {
    const row = document.createElement("a");
    row.className = "waytoagi-item";
    row.href = u.url || "#";
    row.target = "_blank";
    row.rel = "noopener noreferrer";
    const dateEl = document.createElement("span");
    dateEl.className = "d";
    dateEl.textContent = fmtDate(u.date);
    const titleEl = document.createElement("span");
    titleEl.className = "t";
    titleEl.textContent = u.title;
    row.append(dateEl, titleEl);
    waytoagiListEl.appendChild(row);
  });
}

// 按 @handle 去重后的 X 作者列表：{ handle, display }，display 优先取 aihot 的
// "Name (@handle)" 富格式，没有的话退回 socialdata_x 的裸 handle。
function socialdataAuthors() {
  const byHandle = new Map();
  state.itemsAi.forEach((item) => {
    const handle = itemXAuthor(item);
    if (!handle) return;
    const display = itemXAuthorDisplay(item);
    if (!display) return;
    const isRich = item.site_id === "aihot";
    const existing = byHandle.get(handle);
    if (!existing || (isRich && !existing.rich)) {
      byHandle.set(handle, { handle, display, rich: isRich });
    }
  });
  return Array.from(byHandle.values())
    .map(({ handle, display }) => ({ handle, display }))
    .sort((a, b) => a.display.localeCompare(b.display, "en"));
}

function selectSocialdataAuthor(author) {
  state.authorFilter = author;
  // 作者身份现在横跨 socialdata_x 与 aihot-x 两个 site_id（见 itemXAuthor），
  // 不能再锁死 siteFilter="socialdata_x"，否则会把该作者的 aihot 转发条目过滤掉。
  // authorFilter 本身已经是跨站点的精确匹配，siteFilter 留空即可。
  state.siteFilter = "";
  // 博主筛选是条目级过滤：切到全量模式浏览该博主的原始条目池，并清空栏目选择
  state.activeSection = "all";
  state.mode = "all";
  state.mainListVisibleCount = MAIN_LIST_PAGE_SIZE;
  state.xAuthorsExpanded = false;
  renderSectionTabs();
  renderModeSwitch();
  renderSiteFilters();
  renderHotBoard();
  renderMainList();
  renderSourceHealth();
  document.querySelector(".list-wrap")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderSocialdataAuthorList(authors, itemCount) {
  const panel = document.createElement("section");
  panel.className = "health-author-list";
  const heading = document.createElement("div");
  heading.className = "health-author-list-title";
  heading.textContent = t("authors.title");
  const meta = document.createElement("div");
  meta.className = "health-author-list-meta";
  meta.textContent = t("authors.meta", { authors: authors.length, items: itemCount });
  const list = document.createElement("div");
  list.className = "health-author-list-items";
  authors.forEach(({ handle, display }) => {
    const item = document.createElement("button");
    item.type = "button";
    item.textContent = display;
    item.title = t("authors.view", { name: display });
    item.addEventListener("click", () => selectSocialdataAuthor(handle));
    list.appendChild(item);
  });
  panel.append(heading, meta, list);
  return panel;
}

function renderSourceHealthSummaryNode(status, errorMessage = "") {
  const node = document.createElement("div");
  node.className = "source-health-summary";
  if (!status) {
    node.classList.add(errorMessage ? "bad" : "warn");
    node.innerHTML = `<strong>${errorMessage ? t("health.errorTitle") : t("health.missingTitle")}</strong><span>${errorMessage || t("health.waiting")}</span>`;
    return node;
  }
  const sites = Array.isArray(status.sites) ? status.sites : [];
  const okSites = Number(status.successful_sites || 0);
  const failed = failedSourceCount(status);
  // 与 renderSourceStatusTable 同口径：pooled = 全网抓取入池（去话题过滤前），
  // fetched = 原始抓取总量，aiRelevant = 24h AI 强相关合并池。
  const pooled = Number(status.items_before_topic_filter || state.totalAllMode || state.itemsAll.length || 0);
  const fetched = Number(status.fetched_raw_items || state.totalRaw || pooled || 0);
  const aiRelevant = safeItems(state.itemsAi).length;
  node.classList.toggle("warn", failed > 0);
  const segments = [];
  if (fetched) segments.push(t("health.collected", { n: fetched }));
  if (pooled) segments.push(t("health.pooled", { n: pooled }));
  if (aiRelevant) segments.push(t("health.relevant", { n: aiRelevant }));
  segments.push(failed > 0
    ? `<span class="source-health-fail-bad">${t("health.failed", { n: failed })}</span>`
    : t("health.failed", { n: failed }));
  node.innerHTML = `<strong>${t("status.ok", { ok: okSites, total: sites.length })}</strong><span>${segments.join(" · ")}</span>`;
  return node;
}

// Fallback tier ranks mirroring SOURCE_TIER_BY_SITE in scripts/update_news.py.
// Items carry source_tier_rank and that data-derived value wins; this table
// only covers sites with zero loaded items (rank otherwise unknowable).
const SITE_TIER_RANK_FALLBACK = {
  official_ai: 0,
  aibreakfast: 1,
  aihubtoday: 1,
  aibase: 1,
  aihot: 1,
  bestblogs: 1,
  curated_media: 2,
  waytoagi: 2,
  followbuilders: 2,
  opmlrss: 3,
  tikhub_douyin: 4,
  tikhub_xiaohongshu: 4,
  xapi: 4,
  socialdata_x: 4,
  techurls: 5,
  buzzing: 5,
  iris: 5,
  zeli: 5,
  hackernews: 5,
  newsnow: 5,
};

function siteTierRankMap() {
  // source_tier_rank ships on every pipeline item (items_ai / items_all);
  // aggregate one rank per site from whatever is loaded so the source table
  // can sort official tiers first without a duplicated constant table.
  const m = new Map();
  const pools = [safeItems(state.itemsAi), safeItems(state.itemsAll), safeItems(state.itemsAllRaw)];
  pools.forEach((items) => {
    items.forEach((item) => {
      if (!item || !item.site_id || m.has(item.site_id)) return;
      const rank = Number(item.source_tier_rank);
      if (Number.isFinite(rank)) m.set(item.site_id, rank);
    });
  });
  return m;
}

function renderSourceStatusTable(status) {
  if (!sourceStatusTableEl) return;
  sourceStatusTableEl.innerHTML = "";
  if (!status || !Array.isArray(status.sites) || !status.sites.length) return;

  const tierRanks = siteTierRankMap();
  const rows = status.sites
    .filter((site) => !(IS_EN && (site.site_id === "tikhub_douyin" || site.site_id === "tikhub_xiaohongshu")))
    .map((site) => {
      const ai = aiSiteStat(site.site_id);
      const aiCount = Number(ai?.count || 0);
      const rawCount = Number(ai?.raw_count ?? site.item_count ?? 0);
      const scanned = Number(site.item_count || rawCount || 0);
      const ratioBase = rawCount || scanned;
      const ratio = ratioBase ? Math.round((aiCount / ratioBase) * 100) : 0;
      const tierRank = tierRanks.has(site.site_id)
        ? tierRanks.get(site.site_id)
        : (SITE_TIER_RANK_FALLBACK[site.site_id] ?? 9);
      return { ...site, aiCount, rawCount: ratioBase, ratio, tierRank };
    })
    .sort((a, b) =>
      a.tierRank - b.tierRank
      || b.ratio - a.ratio
      || b.aiCount - a.aiCount
      || String(a.site_name).localeCompare(String(b.site_name), LOCALE));

  const table = document.createElement("div");
  table.className = "source-table";
  const header = document.createElement("div");
  header.className = "source-table-row source-table-head";
  header.innerHTML = `<span>${t("common.source")}</span><span>${t("table.aiRaw")}</span><span>${t("table.aiRatio")}</span><span>${t("table.status")}</span>`;
  table.appendChild(header);
  rows.forEach((site) => {
    const row = document.createElement("div");
    row.className = "source-table-row";
    const statusText = site.ok ? t("table.ok") : t("table.bad");
    row.innerHTML = `
      <span>${site.site_name || site.site_id}</span>
      <span>${fmtNumber(site.aiCount)} / ${fmtNumber(site.rawCount)}</span>
      <span>${fmtNumber(site.ratio)}%</span>
      <span class="${site.ok ? "ok" : "bad"}">${statusText}</span>
    `;
    table.appendChild(row);
  });
  const foot = document.createElement("div");
  foot.className = "source-table-row source-table-foot";
  foot.textContent = t("table.total", { n: rows.length });
  table.appendChild(foot);
  sourceStatusTableEl.appendChild(table);
}

// 可选接入未启用/未配置的提示行 + 替换/跳过 RSS 计数（非零才显示）。
// X 数据源已入池的数量在 source-table 的 SocialData X 行可见，这里不重复。
function sourceHealthHintNode(status) {
  const rss = status.rss_opml || {};
  const agentmail = status.agentmail || {};
  const replacedFeeds = Array.isArray(rss.replaced_feeds) ? rss.replaced_feeds : [];
  const skippedFeeds = Array.isArray(rss.skipped_feeds) ? rss.skipped_feeds : [];

  const optionalBits = [];
  if (!rss.enabled) optionalBits.push(t("hint.rssOff"));
  if (!agentmail.enabled) optionalBits.push(t("hint.agentmailOff"));

  const parts = [];
  if (optionalBits.length) parts.push(t("hint.optional", { items: optionalBits.join(" · ") }));
  if (replacedFeeds.length || skippedFeeds.length) {
    parts.push(t("hint.replaced", { a: replacedFeeds.length, b: skippedFeeds.length }));
  }
  if (!parts.length) return null;

  const node = document.createElement("div");
  node.className = "source-health-hint";
  node.textContent = parts.join(" · ");
  return node;
}

function renderSourceHealth(errorMessage = "") {
  if (!sourceHealthEl) return;
  sourceHealthEl.innerHTML = "";
  if (sourceHealthDetailsEl) sourceHealthDetailsEl.innerHTML = "";
  if (sourceStatusTableEl) sourceStatusTableEl.innerHTML = "";

  const status = state.sourceStatus;
  if (!status) {
    sourceHealthEl.appendChild(renderSourceHealthSummaryNode(null, errorMessage));
    renderSourceStatusPill(errorMessage);
    renderClearFiltersButton();
    return;
  }

  sourceHealthEl.appendChild(renderSourceHealthSummaryNode(status, errorMessage));
  const detailTarget = sourceHealthDetailsEl || sourceHealthEl;

  const hint = sourceHealthHintNode(status);
  if (hint) detailTarget.appendChild(hint);

  // X 博主展开列表：功能保留，从已删除的 mini-card 挪到提示行下方的小链接。
  const xAuthors = socialdataAuthors();
  if (xAuthors.length) {
    // 与 socialdataAuthors() 同口径的客户端计数：socialdata_x 原生条目 + aihot 转发的 X 条目
    const socialdataDisplayCount = state.itemsAi.filter((item) => itemXAuthor(item)).length;

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "source-health-authors-toggle";
    toggle.setAttribute("aria-expanded", String(Boolean(state.xAuthorsExpanded)));
    toggle.textContent = state.xAuthorsExpanded
      ? t("authors.collapse")
      : t("authors.expand", { n: xAuthors.length });
    toggle.addEventListener("click", () => {
      state.xAuthorsExpanded = !state.xAuthorsExpanded;
      renderSourceHealth();
    });
    detailTarget.appendChild(toggle);

    if (state.xAuthorsExpanded) {
      detailTarget.appendChild(renderSocialdataAuthorList(xAuthors, socialdataDisplayCount));
    }
  }

  renderSourceStatusTable(status);
  renderSourceStatusPill(errorMessage);
  renderClearFiltersButton();
}

async function loadNewsData() {
  const res = await fetch(`${dataUrl("data/latest-24h.json")}?t=${Date.now()}`);
  if (!res.ok) throw new Error(t("error.load", { file: "latest-24h.json", status: res.status }));
  return res.json();
}

async function loadAllModeData() {
  if (state.allDataLoaded) return;
  if (!state.allDataPromise) {
    state.allDataPromise = fetch(`${dataUrl(state.allDataUrl)}?t=${Date.now()}`)
      .then((res) => {
        if (!res.ok) throw new Error(t("error.load", { file: "latest-24h-all.json", status: res.status }));
        return res.json();
      })
      .then((payload) => {
        state.itemsAllRaw = payload.items_all_raw || payload.items_all || state.itemsAi;
        state.itemsAll = payload.items_all || state.itemsAi;
        state.totalRaw = payload.total_items_raw || state.itemsAllRaw.length;
        state.totalAllMode = payload.total_items_all_mode || state.itemsAll.length;
        state.allDataLoaded = true;
      })
      .catch((err) => {
        state.allDataPromise = null;
        throw err;
      });
  }
  return state.allDataPromise;
}

async function loadWaytoagiData() {
  const res = await fetch(`${dataUrl("data/waytoagi-7d.json")}?t=${Date.now()}`);
  if (!res.ok) throw new Error(t("error.load", { file: "waytoagi-7d.json", status: res.status }));
  return res.json();
}

async function loadSourceStatusData() {
  const res = await fetch(`${dataUrl("data/source-status.json")}?t=${Date.now()}`);
  if (!res.ok) throw new Error(t("error.load", { file: "source-status.json", status: res.status }));
  return res.json();
}

async function loadDailyBriefData() {
  const res = await fetch(`${dataUrl("data/daily-brief.json")}?t=${Date.now()}`);
  if (!res.ok) throw new Error(t("error.load", { file: "daily-brief.json", status: res.status }));
  return res.json();
}

async function loadTop3PersonasData() {
  const res = await fetch(`${dataUrl("data/top3-personas.json")}?t=${Date.now()}`);
  if (!res.ok) throw new Error(t("error.load", { file: "top3-personas.json", status: res.status }));
  return res.json();
}

async function loadStoriesData() {
  const res = await fetch(`${dataUrl(state.storiesDataUrl)}?t=${Date.now()}`);
  if (!res.ok) throw new Error(t("error.load", { file: "stories-merged.json", status: res.status }));
  return res.json();
}

async function init() {
  const [newsResult, waytoagiResult, statusResult, briefResult, storiesResult, personasResult] = await Promise.allSettled([
    loadNewsData(),
    IS_EN ? Promise.resolve(null) : loadWaytoagiData(),
    loadSourceStatusData(),
    loadDailyBriefData(),
    loadStoriesData(),
    loadTop3PersonasData(),
  ]);

  if (briefResult.status === "fulfilled") {
    state.dailyBrief = briefResult.value;
  } else {
    state.dailyBrief = null;
  }
  _briefIdentityKeyCache = null;

  // top3-personas.json 是可选增强数据：文件缺失、请求失败或 items 为空都静默降级。
  if (
    personasResult.status === "fulfilled" &&
    Array.isArray(personasResult.value?.items) &&
    personasResult.value.items.length > 0
  ) {
    state.top3Personas = personasResult.value;
  } else {
    state.top3Personas = null;
  }

  if (storiesResult.status === "fulfilled") {
    state.storiesMerged = storiesResult.value;
  } else {
    state.storiesMerged = null;
  }

  if (newsResult.status === "fulfilled") {
    const payload = newsResult.value;
    const loadedStoriesDataUrl = state.storiesDataUrl;
    state.itemsAi = payload.items_ai || payload.items || [];
    state.itemsAllRaw = payload.items_all_raw || payload.items_all || [];
    state.itemsAll = payload.items_all || [];
    state.creatorItemsAi = payload.creator_items_ai || [];
    state.creatorItemsAll = payload.creator_items_all || state.creatorItemsAi;
    state.creatorWindowDays = Number(payload.creator_window_days || 7);
    state.statsAi = payload.site_stats || [];
    state.totalAi = payload.total_items || state.itemsAi.length;
    state.totalRaw = payload.total_items_raw || state.itemsAllRaw.length;
    state.totalAllMode = payload.total_items_all_mode || state.itemsAll.length;
    state.allDataUrl = payload.all_mode_data_url || state.allDataUrl;
    state.storiesDataUrl = payload.stories_data_url || state.storiesDataUrl;
    if (state.storiesDataUrl !== loadedStoriesDataUrl) {
      try {
        state.storiesMerged = await loadStoriesData();
      } catch {
        state.storiesMerged = null;
      }
    }
    state.allDataLoaded = Boolean(payload.items_all || payload.items_all_raw);
    state.generatedAt = payload.generated_at;

    renderSectionTabs();
    renderModeSwitch();
    renderSiteFilters();
    renderHotBoard();
    renderMainList();
    updatedAtEl.textContent = fmtTime(state.generatedAt);
  } else {
    updatedAtEl.textContent = t("news.loadFailed");
    newsListEl.innerHTML = `<div class="empty">${newsResult.reason.message}</div>`;
  }

  if (statusResult.status === "fulfilled") {
    state.sourceStatus = statusResult.value;
    renderSourceHealth();
  } else {
    renderSourceHealth(statusResult.reason.message);
  }

  if (IS_EN) {
    if (waytoagiWrapEl) waytoagiWrapEl.hidden = true;
  } else if (waytoagiResult.status === "fulfilled") {
    state.waytoagiData = waytoagiResult.value;
    renderWaytoagi(state.waytoagiData);
  } else {
    if (waytoagiWrapEl) waytoagiWrapEl.hidden = state.activeSection !== "community";
    waytoagiUpdatedAtEl.textContent = t("common.loadFailed");
    waytoagiListEl.innerHTML = `<div class="waytoagi-error">${waytoagiResult.reason.message}</div>`;
  }

  document.dispatchEvent(new CustomEvent("aiRadar:ready"));
}

// 搜索：精选模式按故事标题/来源过滤（storyMatchesQuery），全量模式按条目过滤（itemHaystack）
searchInputEl.addEventListener("input", (e) => {
  state.query = e.target.value;
  state.mainListVisibleCount = MAIN_LIST_PAGE_SIZE;
  renderSectionTabs();
  renderModeSwitch();
  renderHotBoard();
  renderMainList();
});

if (clearFiltersBtnEl) {
  clearFiltersBtnEl.addEventListener("click", clearAllFilters);
}

siteSelectEl.addEventListener("change", (e) => {
  state.siteFilter = e.target.value;
  if (state.siteFilter !== "socialdata_x") state.authorFilter = "";
  state.mainListVisibleCount = MAIN_LIST_PAGE_SIZE;
  renderSiteFilters();
  renderHotBoard();
  renderMainList();
});

// 全局 精选/全量 开关：替代旧的三视图切换（精选/热点榜/时间线）
if (modeSelectedBtnEl) {
  modeSelectedBtnEl.addEventListener("click", () => {
    if (state.mode === "selected") return;
    state.mode = "selected";
    state.mainListVisibleCount = MAIN_LIST_PAGE_SIZE;
    rerenderCurrentView();
  });
}

if (modeAllBtnEl) {
  modeAllBtnEl.addEventListener("click", async () => {
    if (state.mode === "all") return;
    state.mode = "all";
    state.mainListVisibleCount = MAIN_LIST_PAGE_SIZE;
    renderModeSwitch();
    newsListEl.innerHTML = "";
    const loading = document.createElement("div");
    loading.className = "empty";
    loading.textContent = t("list.loadingAll");
    newsListEl.appendChild(loading);
    try {
      await loadAllModeData();
      rerenderCurrentView();
    } catch (err) {
      newsListEl.innerHTML = "";
      const failed = document.createElement("div");
      failed.className = "empty";
      failed.textContent = err.message;
      newsListEl.appendChild(failed);
    }
  });
}

if (allDedupeToggleEl) {
  allDedupeToggleEl.addEventListener("change", (e) => {
    state.allDedup = Boolean(e.target.checked);
    state.mainListVisibleCount = MAIN_LIST_PAGE_SIZE;
    rerenderCurrentView();
  });
}

if (waytoagiTodayBtnEl) {
  waytoagiTodayBtnEl.addEventListener("click", () => {
    state.waytoagiMode = "today";
    if (state.waytoagiData) renderWaytoagi(state.waytoagiData);
  });
}

if (waytoagi7dBtnEl) {
  waytoagi7dBtnEl.addEventListener("click", () => {
    state.waytoagiMode = "7d";
    if (state.waytoagiData) renderWaytoagi(state.waytoagiData);
  });
}

if (dataSourceResetBtnEl) {
  dataSourceResetBtnEl.addEventListener("click", () => {
    try { localStorage.removeItem("dataBaseUrl"); } catch {}
    window.location.href = window.location.pathname;
  });
}

renderDataSourceIndicator();
initTodayProjects();
init();
