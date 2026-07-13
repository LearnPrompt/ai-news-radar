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
  mode: "ai",
  waytoagiMode: "today",
  waytoagiData: null,
  sourceStatus: null,
  generatedAt: null,
  dailyBrief: null,
  storiesMerged: null,
  storiesDataUrl: "data/stories-merged.json",
  activeSection: "hot",
  boleView: "timeline",
  boleExpanded: false,
  listSort: "priority",
  sourceTypeFilter: "",
  signalLevelFilter: "",
  siteGroupsExpanded: false,
  xAuthorsExpanded: false,
};

// Keep both UI surfaces on the same snapshot. The query/local-storage contract
// mirrors the current mobile UI so switching views never silently falls back to
// another data directory.
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

function dataUrl(path) {
  const base = state.dataBaseUrl;
  if (!base) return path;
  const file = String(path || "").split("/").pop();
  return `${base}/${file}`;
}

const statsEl = document.getElementById("stats");
const siteSelectEl = document.getElementById("siteSelect");
const sitePillsEl = document.getElementById("sitePills");
const newsListEl = document.getElementById("newsList");
const updatedAtEl = document.getElementById("updatedAt");
const sourceStatusPillEl = document.getElementById("sourceStatusPill");
const stickySummaryTextEl = document.getElementById("stickySummaryText");
const searchInputEl = document.getElementById("searchInput");
const resultCountEl = document.getElementById("resultCount");
const listTitleEl = document.getElementById("listTitle");
const itemTpl = document.getElementById("itemTpl");
const modeAiBtnEl = document.getElementById("modeAiBtn");
const modeAllBtnEl = document.getElementById("modeAllBtn");
const modeHintEl = document.getElementById("modeHint");
const allDedupeWrapEl = document.getElementById("allDedupeWrap");
const allDedupeToggleEl = document.getElementById("allDedupeToggle");
const allDedupeLabelEl = document.getElementById("allDedupeLabel");
const advancedSummaryEl = document.getElementById("advancedSummary");
const sourceHealthEl = document.getElementById("sourceHealth");
const sourceHealthDetailsEl = document.getElementById("sourceHealthDetails");
const sourceStatusTableEl = document.getElementById("sourceStatusTable");
const sectionSelectEl = document.getElementById("sectionSelect");
const sourceTypeSelectEl = document.getElementById("sourceTypeSelect");
const signalLevelSelectEl = document.getElementById("signalLevelSelect");
const dataSourceIndicatorEl = document.getElementById("dataSourceIndicator");
const dataSourceIndicatorTextEl = document.getElementById("dataSourceIndicatorText");
const dataSourceResetBtnEl = document.getElementById("dataSourceResetBtn");

const waytoagiWrapEl = document.querySelector(".waytoagi-wrap");
const waytoagiUpdatedAtEl = document.getElementById("waytoagiUpdatedAt");
const waytoagiMetaEl = document.getElementById("waytoagiMeta");
const waytoagiListEl = document.getElementById("waytoagiList");
const waytoagiTodayBtnEl = document.getElementById("waytoagiTodayBtn");
const waytoagi7dBtnEl = document.getElementById("waytoagi7dBtn");
const coverageStripEl = document.getElementById("coverageStrip");
const bolePicksListEl = document.getElementById("bolePicksList");
const bolePicksMetaEl = document.getElementById("bolePicksMeta");
const bolePicksWrapEl = document.getElementById("bolePicksWrap");
const boleViewToggleEl = document.getElementById("boleViewToggle");
const boleHotBtnEl = document.getElementById("boleHotBtn");
const boleTimelineBtnEl = document.getElementById("boleTimelineBtn");
const sectionTabsEl = document.getElementById("sectionTabs");
const sectionSummaryEl = document.getElementById("sectionSummary");
const topStoriesTitleEl = document.getElementById("topStoriesTitle");
const listSortToolsEl = document.getElementById("listSortTools");

const SOURCE_KINDS = {
  official_ai: { label: "官方", tone: "official" },
  curated_media: { label: "精选媒体", tone: "aihub" },
  aihot: { label: "AI HOT", tone: "hot" },
  aibreakfast: { label: "日报", tone: "newsletter" },
  followbuilders: { label: "Builders/X", tone: "builders" },
  xapi: { label: "X API", tone: "builders" },
  socialdata_x: { label: "X 搜索", tone: "builders" },
  tikhub_douyin: { label: "抖音", tone: "creator" },
  tikhub_xiaohongshu: { label: "小红书", tone: "creator" },
  techurls: { label: "聚合", tone: "aggregate" },
  buzzing: { label: "聚合", tone: "aggregate" },
  iris: { label: "聚合", tone: "aggregate" },
  bestblogs: { label: "博客", tone: "blogs" },
  tophub: { label: "聚合", tone: "aggregate" },
  zeli: { label: "聚合", tone: "aggregate" },
  hackernews: { label: "HN", tone: "aggregate" },
  aihubtoday: { label: "AI站点", tone: "aihub" },
  aibase: { label: "AI站点", tone: "aihub" },
  waytoagi: { label: "社区", tone: "builders" },
  newsnow: { label: "聚合", tone: "aggregate" },
  opmlrss: { label: "OPML", tone: "newsletter" },
};

const SECTION_DEFS = [
  { id: "hot", label: "热点", short: "热点", description: "跨来源聚合后的优先阅读列表" },
  { id: "models", label: "模型", short: "模型", description: "模型发布、能力升级、评测与开源权重" },
  { id: "products", label: "产品", short: "产品", description: "AI 应用、Agent、生成工具和用户产品更新" },
  { id: "devtools", label: "开发者", short: "开发者", description: "编程工具、API、开源项目、推理与工程实践" },
  { id: "hn", label: "HN热议", short: "HN", description: "Hacker News 过去 24 小时的 AI 关键词讨论与高互动 story" },
  { id: "industry", label: "行业", short: "行业", description: "公司战略、融资收购、监管、芯片与产业变化" },
  { id: "research", label: "研究", short: "研究", description: "论文、基准、方法、数据集与研究团队动态" },
  { id: "creator", label: "自媒体", short: "自媒体", description: "一周内互动热度优先，24 小时新内容额外加分" },
  { id: "community", label: "社区", short: "社区", description: "WaytoAGI、中文社区、AIbase、公众号和 Builders/X 信号" },
];

const SECTION_BY_ID = Object.fromEntries(SECTION_DEFS.map((section) => [section.id, section]));

const LIST_SORT_DEFS = [
  { id: "priority", label: "综合" },
  { id: "latest", label: "最新" },
  { id: "ai", label: "高分" },
  { id: "source", label: "来源" },
];

function fmtNumber(n) {
  return new Intl.NumberFormat("zh-CN").format(n || 0);
}

// The classic and mobile surfaces must apply the same last-mile safety gate.
// This protects the public page if an upstream source bypasses pipeline filters.
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

function safeItems(items) {
  return (Array.isArray(items) ? items : []).filter((item) => !isUnsafeContent(item));
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

function fmtTime(iso) {
  if (!iso) return "时间未知";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "时间未知";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(d);
}

function fmtDate(iso) {
  if (!iso) return "未知日期";
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
  }).format(d);
}

function setStats() {
  statsEl.innerHTML = "";
  const items = safeItems(state.itemsAi);
  const highCount = items.filter((item) => isHighPriorityItem(item)).length;
  const curatedCount = briefStories().length || Math.min(20, mergedStories().filter((story) => storyScore(story) >= 75).length);
  const status = state.sourceStatus;
  const totalSites = Array.isArray(status?.sites) ? status.sites.length : 0;
  const okSites = Number(status?.successful_sites || 0);
  const health = totalSites ? `${fmtNumber(okSites)}/${fmtNumber(totalSites)}正常` : "加载中";
  const cards = [
    ["AI", `${fmtNumber(items.length)}条`],
    ["高优", `${fmtNumber(highCount)}条`],
    ["精选", `${fmtNumber(curatedCount)}条`],
    ["源", health],
  ];
  statsEl.setAttribute(
    "aria-label",
    `过去 24 小时：AI 信号 ${fmtNumber(items.length)} 条，高优先级 ${fmtNumber(highCount)} 条，精选 ${fmtNumber(curatedCount)} 条，源状态 ${totalSites ? `${fmtNumber(okSites)}/${fmtNumber(totalSites)} 源正常` : "加载中"}`,
  );

  const prefix = document.createElement("div");
  prefix.className = "stat-prefix";
  prefix.textContent = "过去 24 小时：";
  statsEl.appendChild(prefix);

  cards.forEach(([k, v]) => {
    const node = document.createElement("div");
    node.className = "stat";
    node.innerHTML = `<div class="k">${k}</div><div class="v">${v}</div>`;
    statsEl.appendChild(node);
  });
  renderStickySummary();
  renderSourceStatusPill();
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
    sourceStatusPillEl.textContent = errorMessage || "源状态加载中";
    if (errorMessage) sourceStatusPillEl.classList.add("bad");
    return;
  }
  const totalSites = Array.isArray(status.sites) ? status.sites.length : 0;
  const okSites = Number(status.successful_sites || 0);
  const failed = failedSourceCount(status);
  sourceStatusPillEl.textContent = failed
    ? `${fmtNumber(okSites)}/${fmtNumber(totalSites)} 源正常 · 失败 ${fmtNumber(failed)}`
    : `${fmtNumber(okSites)}/${fmtNumber(totalSites)} 源正常`;
  if (failed) sourceStatusPillEl.classList.add("warn");
}

function renderStickySummary() {
  if (!stickySummaryTextEl) return;
  const filteredCount = getFilteredItems().length;
  const section = SECTION_BY_ID[state.activeSection] || SECTION_BY_ID.hot;
  const query = state.query.trim();
  const site = state.siteFilter
    ? (currentSiteStats().find((row) => row.site_id === state.siteFilter)?.site_name || state.siteFilter)
    : "";
  const sourceType = sourceTypeSelectEl?.selectedOptions?.[0]?.textContent || "";
  const signalLevel = signalLevelSelectEl?.selectedOptions?.[0]?.textContent || "";
  const filters = [
    state.activeSection === "hot" ? "" : section.label,
    site,
    state.sourceTypeFilter ? sourceType : "",
    state.signalLevelFilter ? signalLevel : "",
    query ? `搜索“${query}”` : "",
  ].filter(Boolean);
  const mode = state.mode === "all" ? "全量" : "AI强相关";
  stickySummaryTextEl.textContent = `${fmtNumber(filteredCount)} 条 · ${mode}${filters.length ? ` · ${filters.join(" · ")}` : ""}`;
}

function sourceKind(siteId) {
  return SOURCE_KINDS[siteId] || { label: "来源", tone: "default" };
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
  text.textContent = label || "来源";
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
  const stats = Array.isArray(state.statsAi) && state.statsAi.length
    ? state.statsAi
    : computeSiteStats(state.itemsAi || []);
  return stats.find((site) => site.site_id === siteId) || null;
}

function siteAiPoolCount(siteId) {
  return Number(aiSiteStat(siteId)?.count || 0);
}

function siteRawPoolCount(siteId) {
  const stat = aiSiteStat(siteId);
  return Number(stat?.raw_count ?? stat?.count ?? 0);
}

function sourcePoolMeta(aiCount, rawCount, fallback) {
  if (rawCount && rawCount !== aiCount) return `AI强相关 · 原始 ${fmtNumber(rawCount)} 条`;
  return fallback;
}

function paidSourceLabel(status, poolCount, activeLabel, idleLabel) {
  const connected = Boolean(status?.enabled);
  const liveCount = Number(status?.item_count || 0);
  const displayCount = liveCount || Number(poolCount || 0);
  if (connected) {
    if (displayCount) return `${activeLabel} ${fmtNumber(displayCount)}条`;
    return `${activeLabel} ${status?.skipped ? "待窗口" : "已连接暂无匹配"}`;
  }
  if (displayCount) return `${activeLabel} ${fmtNumber(displayCount)}条`;
  return idleLabel;
}

function renderCoverageCard(label, value, meta, tone = "") {
  const node = document.createElement("div");
  node.className = `coverage-card ${tone}`.trim();
  const labelEl = document.createElement("span");
  labelEl.className = "coverage-label";
  labelEl.textContent = label;
  const valueEl = document.createElement("strong");
  valueEl.textContent = value;
  const metaEl = document.createElement("span");
  metaEl.className = "coverage-meta";
  metaEl.textContent = meta;
  node.append(labelEl, valueEl, metaEl);
  return node;
}

function renderCoverageStrip(errorMessage = "") {
  if (!coverageStripEl) return;
  coverageStripEl.innerHTML = "";

  const rows = siteRows();
  const failedSites = Array.isArray(state.sourceStatus?.failed_sites) ? state.sourceStatus.failed_sites : [];
  const rss = state.sourceStatus?.rss_opml || {};
  const agentmail = state.sourceStatus?.agentmail || {};
  const xApi = state.sourceStatus?.x_api || {};
  const socialdata = state.sourceStatus?.socialdata || {};
  const allCount = Number(state.sourceStatus?.items_before_topic_filter || state.totalAllMode || state.itemsAll.length || 0);
  const coverageCount = Number(state.sourceStatus?.fetched_raw_items || state.totalRaw || allCount || 0);
  const officialCount = Number(siteRow("official_ai")?.item_count || 0);
  const newsletterCount = Number(siteRow("aibreakfast")?.item_count || 0);
  const curatedMediaCount = Number(siteRow("curated_media")?.item_count || 0);
  const buildersCount = Number(siteRow("followbuilders")?.item_count || 0);
  const creatorCount = state.creatorItemsAi.length || (siteAiPoolCount("tikhub_douyin") + siteAiPoolCount("tikhub_xiaohongshu"));
  const creatorRawCount = state.creatorItemsAll.length || (siteRawPoolCount("tikhub_douyin") + siteRawPoolCount("tikhub_xiaohongshu"));
  const socialdataPoolCount = siteAiPoolCount("socialdata_x");
  const xApiPoolCount = siteAiPoolCount("xapi");
  const xPoolCount = socialdataPoolCount + xApiPoolCount;
  const mailCount = Number(agentmail.item_count || 0);
  const totalSites = rows.length;
  const okSites = Number(state.sourceStatus?.successful_sites || 0);
  const opmlValue = rss.enabled ? `${fmtNumber(rss.ok_feeds || 0)}/${fmtNumber(rss.effective_feed_total || 0)}` : "OPML";
  const opmlMeta = rss.enabled ? "RSS示例/自定义订阅已接入" : "可用OPML批量接入RSS";
  const socialdataLabel = paidSourceLabel(socialdata, socialdataPoolCount, "SocialData", "");
  const xApiLabel = paidSourceLabel(xApi, xApiPoolCount, "X API", "");
  const xSourceLabel = socialdataLabel || xApiLabel || "X待配置";
  const mailLabel = agentmail.enabled ? `Mail ${fmtNumber(mailCount)}` : "Mail待配置";
  const advancedValue = xPoolCount || mailCount
    ? `${xPoolCount ? `X ${fmtNumber(xPoolCount)}` : "X"} / ${mailCount ? `Mail ${fmtNumber(mailCount)}` : "Mail"}`
    : "X / Mail";
  const advancedMeta = socialdata.enabled || xApi.enabled || agentmail.enabled || xPoolCount
    ? `额度保护 · ${xSourceLabel} / ${mailLabel}`
    : "X API 与 AgentMail 默认关闭";

  const cards = [
    ["源健康", totalSites ? `${fmtNumber(okSites)}/${fmtNumber(totalSites)}` : "加载中", failedSites.length ? `${fmtNumber(failedSites.length)} 个失败源` : (errorMessage || "内置源正常"), failedSites.length ? "warn" : "ok"],
    ["今日覆盖池", `${fmtNumber(coverageCount)} 条`, allCount ? `全网抓取原始信号 · ${fmtNumber(allCount)} 条入池` : "全网抓取原始信号", "signal"],
    ["AI强相关", `${fmtNumber(safeItems(state.itemsAi).length)} 条`, "24小时强相关信号", "signal"],
    ["官方/日报源池", `${fmtNumber(officialCount + newsletterCount)} 条`, "官方节点 + AI Breakfast", "official"],
    ["精选媒体源池", `${fmtNumber(curatedMediaCount)} 条`, "The Decoder / TC / Verge / MTP 等", "signal"],
    ["Builders/X源池", `${fmtNumber(buildersCount)} 条`, "Follow Builders公开feed", "builders"],
    ["自媒体源池", `${fmtNumber(creatorCount)} 条`, sourcePoolMeta(creatorCount, creatorRawCount, "TikHub · 抖音 + 小红书"), "creator"],
    ["RSS/OPML扩展", opmlValue, opmlMeta, "private"],
    ["高级源", advancedValue, advancedMeta, "private"],
  ];

  cards.forEach(([label, value, meta, tone]) => {
    coverageStripEl.appendChild(renderCoverageCard(label, value, meta, tone));
  });
}

function renderAdvancedSummary() {
  if (!advancedSummaryEl) return;
  const status = state.sourceStatus;
  const filteredCount = getFilteredItems().length;
  if (!status) {
    advancedSummaryEl.textContent = `${fmtNumber(filteredCount)} 条结果`;
    return;
  }
  const sites = Array.isArray(status.sites) ? status.sites : [];
  const totalSites = sites.length;
  const okSites = Number(status.successful_sites || 0);
  const failed = failedSourceCount(status);
  advancedSummaryEl.textContent = `${fmtNumber(filteredCount)} 条结果 · ${fmtNumber(okSites)}/${fmtNumber(totalSites)} 源正常${failed ? ` · 失败 ${fmtNumber(failed)}` : ""}`;
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
  return Array.from(m.values()).sort((a, b) => b.count - a.count || a.site_name.localeCompare(b.site_name, "zh-CN"));
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

function currentSiteStats() {
  if (state.activeSection === "creator") {
    return computeSiteStats(safeItems(state.mode === "all" ? state.creatorItemsAll : state.creatorItemsAi));
  }
  if (state.mode === "ai") return safeAiSiteStats();
  return computeSiteStats(safeItems(state.allDedup ? state.itemsAll : state.itemsAllRaw));
}

function creatorHotScore(item) {
  return normalizedPercent(item?.creator_hot_score);
}

function highPriorityScore(item) {
  if (itemSections(item).has("creator") && creatorHotScore(item)) return creatorHotScore(item);
  return scorePercent(item);
}

function isHighPriorityItem(item) {
  return highPriorityScore(item) >= 75 || itemPriorityScore(item) >= 82 || item.site_id === "official_ai" || item.site_id === "aihot";
}

function isCuratedItem(item) {
  return item.site_id === "official_ai" || item.site_id === "aihot" || item.source_tier === "official" || item.source_tier === "curated";
}

function itemSourceType(item) {
  const siteId = item.site_id || "";
  const tier = item.source_tier || "";
  if (siteId === "official_ai" || tier === "official") return "official";
  if (siteId === "curated_media" || siteId === "aibreakfast" || siteId === "aihot") return "media";
  if (siteId === "opmlrss" || tier === "user_opml") return "rss";
  if (siteId === "waytoagi" || siteId === "followbuilders" || siteId === "hackernews" || siteId === "zeli" || siteId === "aibase") return "community";
  if (siteId === "tikhub_douyin" || siteId === "tikhub_xiaohongshu") return "creator";
  if (siteId === "socialdata_x" || siteId === "xapi" || siteId === "agentmail") return "advanced";
  return "aggregate";
}

function multiSourceEventKeys(items) {
  const map = new Map();
  (items || []).forEach((item) => {
    const key = eventKey(item);
    if (!map.has(key)) map.set(key, new Set());
    map.get(key).add(sourceSignal(item));
  });
  return new Set(Array.from(map.entries())
    .filter(([, sources]) => sources.size > 1)
    .map(([key]) => key));
}

function itemMatchesSignalLevel(item, multiSourceKeys = new Set()) {
  if (!state.signalLevelFilter) return true;
  if (state.signalLevelFilter === "high") return isHighPriorityItem(item);
  if (state.signalLevelFilter === "curated") return isCuratedItem(item);
  if (state.signalLevelFilter === "multi") return multiSourceKeys.has(eventKey(item));
  return true;
}

function sectionStats(sectionId) {
  const items = sectionItems(modeItems(), sectionId);
  const highCount = items.filter((item) => isHighPriorityItem(item)).length;
  const sourceSet = new Set(items.map((item) => item.source || item.site_name || item.site_id).filter(Boolean));
  return { items, count: items.length, highCount, sourceCount: sourceSet.size };
}

function renderSectionTabs() {
  if (!sectionTabsEl) return;
  sectionTabsEl.innerHTML = "";
  SECTION_DEFS.forEach((section) => {
    const stats = sectionStats(section.id);
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `section-tab ${state.activeSection === section.id ? "active" : ""}`;
    btn.setAttribute("role", "tab");
    btn.setAttribute("aria-selected", state.activeSection === section.id ? "true" : "false");
    btn.dataset.section = section.id;
    btn.innerHTML = `<span>${section.label}</span><strong>${fmtNumber(stats.count)}</strong>`;
    btn.addEventListener("click", () => {
      state.activeSection = section.id;
      state.boleExpanded = false;
      renderSectionTabs();
      renderModeSwitch();
      renderSiteFilters();
      renderBolePicks();
      if (state.waytoagiData) renderWaytoagi(state.waytoagiData);
      renderList();
    });
    sectionTabsEl.appendChild(btn);
  });
  renderSectionFilterSelect();
}

function renderSectionFilterSelect() {
  if (!sectionSelectEl) return;
  if (!sectionSelectEl.options.length) {
    SECTION_DEFS.forEach((section) => {
      const option = document.createElement("option");
      option.value = section.id;
      option.textContent = section.label;
      sectionSelectEl.appendChild(option);
    });
  }
  sectionSelectEl.value = state.activeSection;
}

function renderSectionSummary(filteredItems = null) {
  if (!sectionSummaryEl) return;
  const section = SECTION_BY_ID[state.activeSection] || SECTION_BY_ID.hot;
  const items = filteredItems || getFilteredItems();
  const highCount = items.filter((item) => isHighPriorityItem(item)).length;
  const sources = new Set(items.map((item) => item.source || item.site_name || item.site_id).filter(Boolean));
  const modeText = state.mode === "all" ? (state.allDedup ? "全量去重" : "全量原始") : "AI强相关";
  const windowText = state.activeSection === "creator" ? `过去 ${fmtNumber(state.creatorWindowDays)} 天 · 热度优先` : "过去 24 小时";
  sectionSummaryEl.textContent = `${windowText} · ${fmtNumber(items.length)} 条${section.id === "hot" ? "" : ` ${section.label}`}信号 · ${fmtNumber(highCount)} 条高优先级 · ${fmtNumber(sources.size)} 个来源 · ${modeText}`;
  renderStickySummary();
}

function siteRatioText(siteStats) {
  const count = Number(siteStats.count || 0);
  const raw = Number(siteStats.raw_count ?? siteStats.count ?? 0);
  if (!raw) {
    const scanned = Number(siteRow(siteStats.site_id)?.item_count || 0);
    if (!count && scanned) return `24h 0 · 已扫 ${fmtNumber(scanned)}`;
    if (!count) return "已扫 0";
    return `${fmtNumber(count)} 条`;
  }
  if (raw === count) return `${fmtNumber(count)} 条`;
  return `${fmtNumber(count)}/${fmtNumber(raw)} · ${Math.round((count / raw) * 100)}%AI`;
}

function renderSiteFilters() {
  const stats = currentSiteStats();

  siteSelectEl.innerHTML = '<option value="">全部站点</option>';
  stats.forEach((s) => {
    const opt = document.createElement("option");
    opt.value = s.site_id;
    opt.textContent = `${s.site_name} (${siteRatioText(s)})`;
    siteSelectEl.appendChild(opt);
  });
  siteSelectEl.value = state.siteFilter;

  sitePillsEl.innerHTML = "";
  const allPill = document.createElement("button");
  allPill.className = `pill ${state.siteFilter === "" ? "active" : ""}`;
  allPill.textContent = "全部";
  allPill.onclick = () => {
    state.siteFilter = "";
    renderSiteFilters();
    renderBolePicks();
    renderList();
  };
  sitePillsEl.appendChild(allPill);

  if (state.authorFilter) {
    const authorPill = document.createElement("button");
    authorPill.type = "button";
    authorPill.className = "pill active author-filter-pill";
    authorPill.textContent = `X 博主 ${state.authorFilter} ×`;
    authorPill.title = "清除博主筛选";
    authorPill.onclick = () => {
      state.authorFilter = "";
      state.siteFilter = "";
      state.siteGroupsExpanded = false;
      renderSiteFilters();
      renderBolePicks();
      renderList();
    };
    sitePillsEl.appendChild(authorPill);
  }

  stats.forEach((s) => {
    const btn = document.createElement("button");
    btn.className = `pill ${state.siteFilter === s.site_id ? "active" : ""}`;
    btn.textContent = `${s.site_name} ${siteRatioText(s)}`;
    btn.onclick = () => {
      state.siteFilter = s.site_id;
      if (s.site_id !== "socialdata_x") state.authorFilter = "";
      renderSiteFilters();
      renderBolePicks();
      renderList();
    };
    sitePillsEl.appendChild(btn);
  });
}

function renderModeSwitch() {
  modeAiBtnEl.classList.toggle("active", state.mode === "ai");
  modeAllBtnEl.classList.toggle("active", state.mode === "all");
  if (allDedupeWrapEl) allDedupeWrapEl.classList.toggle("show", state.mode === "all");
  if (allDedupeToggleEl) allDedupeToggleEl.checked = state.allDedup;
  if (allDedupeLabelEl) allDedupeLabelEl.textContent = state.allDedup ? "去重开" : "去重关";
  if (state.mode === "ai") {
    modeHintEl.textContent = `AI强相关 · ${fmtNumber(safeItems(state.itemsAi).length)} 条`;
  } else {
    const allCount = effectiveAllItems().length;
    modeHintEl.textContent = `全量 · ${state.allDedup ? "去重开" : "去重关"} · ${fmtNumber(allCount)} 条`;
  }
  if (listTitleEl) {
    listTitleEl.textContent = listTitleText();
  }
  renderAdvancedSummary();
  renderSectionSummary();
}

function listTitleText() {
  const section = SECTION_BY_ID[state.activeSection] || SECTION_BY_ID.hot;
  const pool = state.mode === "all"
    ? (state.allDedup ? "情报流 · 全量去重" : "情报流 · 全量原始")
    : "情报流";
  return state.activeSection === "hot" ? pool : `${section.label} · ${pool}`;
}

function renderListSortTools() {
  if (!listSortToolsEl) return;
  const validSort = LIST_SORT_DEFS.some((item) => item.id === state.listSort);
  if (!validSort) state.listSort = "priority";
  listSortToolsEl.querySelectorAll("[data-sort]").forEach((button) => {
    const active = button.dataset.sort === state.listSort;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
}

function itemSourceSortKey(item) {
  return [
    sourceSignal(item),
    item.site_name || item.site_id || "",
    item.source || "",
  ].join(" ").trim() || "来源";
}

function sortItemsForList(items) {
  const sorted = [...items];
  if (state.listSort === "latest") {
    return sorted.sort((a, b) => timelineMs(b) - timelineMs(a) || itemPriorityScore(b) - itemPriorityScore(a));
  }
  if (state.listSort === "ai") {
    return sorted.sort((a, b) => scorePercent(b) - scorePercent(a) || itemPriorityScore(b) - itemPriorityScore(a) || timelineMs(b) - timelineMs(a));
  }
  if (state.listSort === "source") {
    const counts = new Map();
    sorted.forEach((item) => {
      const key = itemSourceSortKey(item);
      counts.set(key, (counts.get(key) || 0) + 1);
    });
    return sorted.sort((a, b) => {
      const aKey = itemSourceSortKey(a);
      const bKey = itemSourceSortKey(b);
      const byCount = (counts.get(bKey) || 0) - (counts.get(aKey) || 0);
      if (byCount !== 0) return byCount;
      const bySource = aKey.localeCompare(bKey, "zh-CN");
      if (bySource !== 0) return bySource;
      return itemPriorityScore(b) - itemPriorityScore(a) || timelineMs(b) - timelineMs(a);
    });
  }
  return sorted.sort((a, b) => itemPriorityScore(b) - itemPriorityScore(a) || timelineMs(b) - timelineMs(a));
}

function effectiveAllItems() {
  return safeItems(state.allDedup ? state.itemsAll : state.itemsAllRaw);
}

function modeItems() {
  return state.mode === "all" ? effectiveAllItems() : safeItems(state.itemsAi);
}

function sectionItems(items = modeItems(), sectionId = state.activeSection) {
  if (sectionId === "creator") {
    const creatorSource = state.mode === "all" ? state.creatorItemsAll : state.creatorItemsAi;
    return safeItems(creatorSource).sort((a, b) => creatorHotScore(b) - creatorHotScore(a) || timelineMs(b) - timelineMs(a));
  }
  const source = Array.isArray(items) ? items : [];
  if (sectionId === "hot") {
    return [...source].sort((a, b) => itemPriorityScore(b) - itemPriorityScore(a) || timelineMs(b) - timelineMs(a));
  }
  return source.filter((item) => itemMatchesSection(item, sectionId));
}

function getFilteredItems() {
  const q = state.query.trim().toLowerCase();
  const preliminary = sectionItems().filter((item) => {
    if (state.siteFilter && item.site_id !== state.siteFilter) return false;
    if (state.authorFilter && (item.site_id !== "socialdata_x" || item.source !== state.authorFilter)) return false;
    if (state.sourceTypeFilter && itemSourceType(item) !== state.sourceTypeFilter) return false;
    if (!q) return true;
    const hay = `${item.title || ""} ${item.title_zh || ""} ${item.title_en || ""} ${item.site_name || ""} ${item.source || ""}`.toLowerCase();
    return hay.includes(q);
  });
  const multiKeys = multiSourceEventKeys(preliminary);
  return preliminary.filter((item) => itemMatchesSignalLevel(item, multiKeys));
}

function itemTitleText(item) {
  return (item.title_zh || item.title || item.title_en || "未命名更新").trim();
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
  if (itemSections(item).has("creator")) return "creator";
  if (label === "model_release") return "models";
  if (label === "developer_tool" || label === "developer_tooling" || label === "infrastructure" || label === "infra_compute") return "devtools";
  if (label === "research_paper") return "research";
  if (label === "industry_business") return "industry";
  if (label === "ai_product_update" || label === "agent_workflow" || label === "robotics") return "products";
  if (itemSections(item).has("community")) return "community";
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

function itemTagChip(label) {
  const tag = document.createElement("span");
  tag.className = `signal-tag tone-${itemTagTone(label)}`;
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
  text.textContent = label || "来源";
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
  if (creatorScore && itemSections(item).has("creator")) return creatorScore;
  const internal = scorePercent(item);
  const editorial = editorialPercent(item);
  const source = sourceTierPercent(item);
  const freshness = freshnessPercent(item);
  const signal = Array.isArray(item.ai_signals) ? Math.min(100, item.ai_signals.length * 18) : 0;
  return Math.round((editorial * 0.3) + (source * 0.22) + (internal * 0.2) + (freshness * 0.18) + (signal * 0.1));
}

function labelText(item) {
  const labels = {
    ai_general: "AI信号",
    model_release: "模型发布",
    agent_workflow: "Agent工作流",
    ai_product_update: "产品更新",
    developer_tooling: "开发工具",
    developer_tool: "开发工具",
    infrastructure: "基础设施",
    infra_compute: "基础设施",
    industry_business: "行业动态",
    research_paper: "研究论文",
    robotics: "机器人",
    curated_hotlist: "热点",
    ai_tech: "技术趋势",
  };
  return labels[item.ai_label] || item.ai_label || "精选信号";
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

function itemSections(item) {
  const hay = itemHaystack(item);
  const contentHay = [
    item.title,
    item.title_zh,
    item.title_en,
    item.title_original,
    item.source,
    item.site_name,
    item.site_id,
    ...(Array.isArray(item.ai_signals) ? item.ai_signals : []),
  ].filter(Boolean).join(" ").toLowerCase();
  const sections = new Set();
  const label = item.ai_label || "";
  const source = `${item.source || ""} ${item.site_name || ""}`.toLowerCase();
  const hasExplicitModelTerm = matchesAny(contentHay, [
    /gpt[-\s]?\d|claude|gemini|grok|llama|qwen|deepseek|mistral|kimi\s?k\d|glm|gemma|模型|model|weights|权重|多模态|视频生成|diffusion|sora|seedance|llm|大模型/,
  ]);
  const looksLikeToolOrProduct = matchesAny(hay, [
    /skill|copilot|codex|cli|api|sdk|dashboard|workflow|tool|工具|助手|应用|插件|工作流|支付宝|浏览器|搜索/,
  ]);

  if (
    hasExplicitModelTerm ||
    (label === "model_release" && !looksLikeToolOrProduct)
  ) sections.add("models");

  if (
    label === "ai_product_update" ||
    label === "agent_workflow" ||
    label === "robotics" ||
    matchesAny(hay, [
      /app|product|agent|workflow|siri|copilot|chatgpt|perplexity|runway|suno|支付宝|产品|应用|智能体|机器人|浏览器|搜索|助手|生成工具|办公|教育/,
    ])
  ) sections.add("products");

  if (
    label === "developer_tool" ||
    label === "developer_tooling" ||
    label === "infra_compute" ||
    matchesAny(hay, [
      /github|cursor|codex|copilot|openrouter|api|sdk|mcp|cli|framework|inference|推理|开发者|开源|代码|编程|算力|芯片|nvidia|cloud|部署|benchmarking|token/,
    ])
  ) sections.add("devtools");

  if (
    item.site_id === "hackernews" ||
    item.site_id === "zeli" ||
    source.includes("hacker news") ||
    source.includes("hackernews") ||
    source.includes("hn algolia")
  ) sections.add("hn");

  if (
    label === "industry_business" ||
    matchesAny(hay, [
      /funding|raised|ipo|acquire|acquisition|lawsuit|regulation|policy|white house|pentagon|nvidia|salesforce|meta|microsoft|融资|收购|上市|监管|政策|裁员|估值|债券|芯片|公司|行业|政府|五角大楼|白宫/,
    ])
  ) sections.add("industry");

  if (
    label === "research_paper" ||
    matchesAny(hay, [
      /paper|arxiv|research|benchmark|eval|dataset|lmsys|rdi|berkeley|huggingface daily papers|论文|研究|基准|评测|数据集|训练|k-means|speculative decoding/,
    ])
  ) sections.add("research");

  if (
    item.site_id === "tikhub_douyin" ||
    item.site_id === "tikhub_xiaohongshu" ||
    source.includes("douyin") ||
    source.includes("xiaohongshu") ||
    source.includes("小红书") ||
    source.includes("抖音")
  ) sections.add("creator");

  if (
    item.site_id === "waytoagi" ||
    item.site_id === "followbuilders" ||
    item.site_id === "aibase" ||
    source.includes("it之家") ||
    source.includes("36氪") ||
    source.includes("掘金") ||
    source.includes("readhub") ||
    source.includes("aibase") ||
    source.includes("公众号") ||
    source.includes("宝玉") ||
    source.includes("小互") ||
    source.includes("ayi") ||
    matchesAny(hay, [
      /waytoagi|社区|公众号|阿里|通义|千问|智谱|kimi|月之暗面|minimax|字节|火山|百度|腾讯|华为|蚂蚁|讯飞|国内|中文|开源中国|少数派|虎嗅/,
    ])
  ) sections.add("community");

  if (!sections.size) sections.add("industry");
  return sections;
}

function itemMatchesSection(item, sectionId) {
  return sectionId === "hot" || itemSections(item).has(sectionId);
}

function sectionBadgeLabel(sectionId) {
  return SECTION_BY_ID[sectionId]?.short || "栏目";
}

function reasonText(item) {
  const creatorScore = creatorHotScore(item);
  if (creatorScore && itemSections(item).has("creator")) {
    const metrics = item.creator_metrics || {};
    const parts = [
      `赞 ${fmtNumber(metrics.likes)}`,
      `藏 ${fmtNumber(metrics.collects)}`,
      `评 ${fmtNumber(metrics.comments)}`,
      `转 ${fmtNumber(metrics.shares)}`,
    ];
    if (Number(item.creator_freshness_bonus || 0) > 0) parts.push("24h 加分");
    return `一周互动：${parts.join(" · ")}`;
  }
  const signals = Array.isArray(item.ai_signals) ? item.ai_signals.filter(Boolean).slice(0, 3) : [];
  if (signals.length) return `命中方向：${signals.join(" / ")}`;
  if (item.ai_relevance_reason) return String(item.ai_relevance_reason).replaceAll("_", " ");
  return "来源与标题信号通过筛选";
}

function timelineIso(item) {
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
    .replace(/[\s\u3000]+/g, "")
    .replace(/[，。、“”‘’：:；;！!？?（）()\[\]【】《》<>·.,/\\|_-]/g, "");
}

function eventKey(item) {
  const raw = itemTitleText(item);
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

function headlineRowIdentityKeys(row) {
  const keys = new Set();
  if (!row) return keys;
  const refs = [
    row.item,
    ...(Array.isArray(row.rows) ? row.rows.map((entry) => entry.item).filter(Boolean) : []),
  ].filter(Boolean);
  refs.forEach((ref) => {
    itemIdentityKeys(ref).forEach((key) => keys.add(key));
  });
  return keys;
}

function excludedStoryKeySet(rows) {
  const keys = new Set();
  rows.forEach((row) => {
    headlineRowIdentityKeys(row).forEach((key) => keys.add(key));
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

function sourcePriority(item) {
  const signal = sourceSignal(item);
  if (signal === "官方更新") return 100;
  if (signal === "AI HOT精选") return 90;
  if (signal === "AIbase") return 82;
  if (signal === "Builders") return 74;
  if (signal === "抖音自媒体" || signal === "小红书自媒体") return 70;
  if (signal === "OPML") return 68;
  if (signal === "HN热议" || signal === "GitHub趋势") return 62;
  return 50;
}

function clusterBoleEvents(rows) {
  const clusters = new Map();
  rows.forEach((row) => {
    const key = eventKey(row.item);
    if (!clusters.has(key)) clusters.set(key, { key, rows: [], signals: new Set(), score: 0, primary: row });
    const cluster = clusters.get(key);
    cluster.rows.push(row);
    cluster.signals.add(sourceSignal(row.item));
    const currentPrimary = cluster.primary;
    const betterPrimary = sourcePriority(row.item) - sourcePriority(currentPrimary.item)
      || row.score - currentPrimary.score
      || timelineMs(row.item) - timelineMs(currentPrimary.item);
    if (betterPrimary > 0) cluster.primary = row;
  });
  return Array.from(clusters.values()).map((cluster) => {
    const signals = Array.from(cluster.signals);
    const maxScore = Math.max(...cluster.rows.map((row) => row.score));
    const sourceBonus = Math.min(12, Math.max(0, signals.length - 1) * 6);
    const candidateBonus = signals.some((s) => s === "AI HOT精选") ? 8
      : signals.some((s) => s === "HN热议" || s === "GitHub趋势") ? 6
      : signals.some((s) => s === "官方更新") ? 5
      : 0;
    return {
      item: cluster.primary.item,
      index: cluster.primary.index,
      rows: cluster.rows,
      sourceSignals: signals,
      sourceCount: signals.length,
      mergedCount: cluster.rows.length,
      score: Math.min(100, Math.round(maxScore + sourceBonus + candidateBonus)),
    };
  });
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

function storyImportanceTone(label) {
  if (!label) return "watch";
  if (label.includes("重大")) return "hot";
  if (label.includes("官方")) return "official";
  if (label.includes("多源")) return "strong";
  if (label.includes("行业")) return "watch";
  return "watch";
}

function storyPrimaryTitleText(story) {
  const primary = (story && story.primary_item) || {};
  const bilingual = String(primary.title || (story && story.title) || "").trim();
  if (bilingual.includes(" / ")) {
    const [zh, en] = bilingual.split(" / ");
    return (zh || en || bilingual).trim();
  }
  return bilingual || "未命名更新";
}

function storyPrimaryEnText(story) {
  const primary = (story && story.primary_item) || {};
  const bilingual = String(primary.title || (story && story.title) || "").trim();
  if (bilingual.includes(" / ")) {
    const [, en] = bilingual.split(" / ");
    return (en || "").trim();
  }
  return "";
}

function storySourceCount(story) {
  const sources = Array.isArray(story && story.sources) ? story.sources : [];
  const explicit = Number(story && story.duplicate_count);
  if (Number.isFinite(explicit) && explicit > 0) return explicit;
  return Math.max(1, sources.length);
}

function storyDurationLabel(earliest, latest) {
  if (!earliest || !latest || earliest === latest) return "";
  const start = new Date(earliest).getTime();
  const end = new Date(latest).getTime();
  if (!Number.isFinite(start) || !Number.isFinite(end)) return "";
  const minutes = Math.round(Math.abs(end - start) / 60000);
  if (minutes < 20) return "短时集中";
  if (minutes < 60) return `发酵 ${minutes} 分钟`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `发酵 ${hours}小时${rest}分` : `发酵 ${hours}小时`;
}

function formatStoryTime(story) {
  const earliest = story.earliest_at;
  const latest = story.latest_at;
  if (latest && earliest && latest !== earliest) {
    return { latest, rangeLabel: storyDurationLabel(earliest, latest) };
  }
  return { latest: latest || earliest, rangeLabel: "" };
}

function pickBoleItems(items) {
  const ranked = [...items]
    .map((item, index) => ({ item, index, score: scorePercent(item) }))
    .filter((row) => row.score > 0)
    .sort((a, b) => {
      const byScore = b.score - a.score;
      if (byScore !== 0) return byScore;
      return timelineMs(b.item) - timelineMs(a.item) || a.index - b.index;
    });

  const sorted = clusterBoleEvents(ranked).sort((a, b) => {
    const byMultiSource = b.sourceCount - a.sourceCount;
    const byScore = b.score - a.score;
    return byMultiSource || byScore || timelineMs(b.item) - timelineMs(a.item) || a.index - b.index;
  });

  const picked = [];
  const addPick = (cluster) => {
    if (cluster && !picked.includes(cluster) && picked.length < 8) picked.push(cluster);
  };
  ["AI HOT精选", "HN热议", "GitHub趋势"].forEach((signal) => {
    addPick(sorted.find((cluster) => cluster.sourceSignals.includes(signal)));
  });
  sorted.forEach(addPick);
  return picked;
}

function boleReasonText(row) {
  const signals = row.sourceSignals || [];
  const sourceText = signals.length ? `来源命中：${signals.join(" / ")}` : "来源命中：单源";
  const mergeText = row.mergedCount > 1 ? `合并${row.mergedCount}条同事件` : "单条事件";
  return `${sourceText} · ${mergeText} · ${reasonText(row.item)}`;
}

function buildBoleLead(row) {
  const { item, score } = row;
  const lead = document.createElement("a");
  lead.className = "bole-lead-card";
  lead.href = item.url || "#";
  lead.target = "_blank";
  lead.rel = "noopener noreferrer";

  const top = document.createElement("div");
  top.className = "bole-lead-top";
  const kicker = document.createElement("span");
  kicker.className = "bole-kicker";
  kicker.textContent = `${labelText(item)} · ${fmtTime(timelineIso(item))}`;
  const scoreEl = document.createElement("strong");
  scoreEl.className = `bole-score-orb ${scoreTone(score)}`;
  scoreEl.innerHTML = `<span>${score}</span><small>分</small>`;
  top.append(kicker, scoreEl);

  const title = document.createElement("div");
  title.className = "bole-lead-title";
  title.textContent = itemTitleText(item);

  const reason = document.createElement("div");
  reason.className = "bole-lead-reason";
  reason.textContent = reasonText(item);

  const foot = document.createElement("div");
  foot.className = "bole-lead-foot";
  foot.innerHTML = `<span>${item.site_name || "来源"}</span><span>${item.source || "未分区"}</span>`;

  lead.append(top, title, reason, foot);
  return lead;
}

function buildBoleTimelineRow(row, rank) {
  const { item, score } = row;
  const link = document.createElement("a");
  link.className = "bole-row";
  link.href = item.url || "#";
  link.target = "_blank";
  link.rel = "noopener noreferrer";

  const time = document.createElement("time");
  time.className = "bole-row-time";
  time.textContent = fmtTime(timelineIso(item));

  const body = document.createElement("div");
  body.className = "bole-row-body";
  const meta = document.createElement("div");
  meta.className = "bole-row-meta";
  meta.innerHTML = `<span>#${rank}</span><span>${item.site_name || "来源"}</span><strong>${score}分</strong>`;
  (row.sourceSignals || []).slice(0, 4).forEach((signal) => {
    appendSourceChip(meta, signal, sourceSignalTone(signal), "source-chip source-hit");
  });
  const title = document.createElement("div");
  title.className = "bole-row-title";
  title.textContent = itemTitleText(item);
  const reason = document.createElement("div");
  reason.className = "bole-row-reason";
  reason.textContent = boleReasonText(row);
  body.append(meta, title, reason);

  link.append(time, body);
  return link;
}

function buildStoryCard(story, rank) {
  const link = document.createElement("a");
  link.className = "story-row";
  const primary = story.primary_item || {};
  link.href = primary.url || story.primary_url || story.url || "#";
  link.target = "_blank";
  link.rel = "noopener noreferrer";

  const time = document.createElement("div");
  time.className = "story-time";
  const { latest, rangeLabel } = formatStoryTime(story);
  const labelEl = document.createElement("span");
  labelEl.className = "story-time-label";
  labelEl.textContent = "最新";
  const latestEl = document.createElement("span");
  latestEl.className = "story-time-latest";
  latestEl.textContent = fmtTime(latest);
  time.append(labelEl, latestEl);
  if (rangeLabel) {
    const rangeEl = document.createElement("span");
    rangeEl.className = "story-time-range";
    rangeEl.textContent = rangeLabel;
    rangeEl.title = "最早来源到最新来源的时间差，不是距离现在多久。";
    time.appendChild(rangeEl);
  }

  const body = document.createElement("div");
  body.className = "story-body";

  const meta = document.createElement("div");
  meta.className = "story-meta";
  const rankEl = document.createElement("span");
  rankEl.className = "story-rank";
  rankEl.textContent = `#${rank}`;
  meta.appendChild(rankEl);
  if (story.importance_label) {
    const imp = document.createElement("span");
    imp.className = `story-importance ${storyImportanceTone(story.importance_label)}`;
    imp.textContent = story.importance_label;
    meta.appendChild(imp);
  }
  const sourceCount = storySourceCount(story);
  const countEl = document.createElement("span");
  countEl.className = "story-count";
  countEl.textContent = `${sourceCount} 个来源`;
  meta.appendChild(countEl);
  const displayScore = storySortScore(story);
  if (displayScore > 0) {
    const scoreEl = document.createElement("strong");
    scoreEl.className = `story-score ${state.boleView === "hot" ? "heat" : ""}`.trim();
    scoreEl.title = state.boleView === "hot"
      ? "热度分 = 多源强度 × 时间衰减"
      : "编辑重要性分";
    scoreEl.innerHTML = `<span>${displayScore}</span><small>${state.boleView === "hot" ? "热度" : "分"}</small>`;
    meta.appendChild(scoreEl);
  }
  body.appendChild(meta);

  const sources = Array.isArray(story.sources) ? story.sources : [];
  if (sources.length) {
    const sourcesEl = document.createElement("div");
    sourcesEl.className = "story-sources";
    sources.slice(0, 6).forEach((src) => {
      const kind = sourceKind(src.site_id);
      const label = src.source || src.source_name || "来源";
      const tag = sourceChip(label, kind.tone, "story-source-chip source-chip");
      sourcesEl.appendChild(tag);
    });
    if (sources.length > 6) {
      const more = document.createElement("span");
      more.className = "story-source-more";
      more.textContent = `+${sources.length - 6}`;
      sourcesEl.appendChild(more);
    }
    body.appendChild(sourcesEl);
  }

  const title = document.createElement("div");
  title.className = "story-title";
  const primaryTitle = storyPrimaryTitleText(story);
  const enTitle = storyPrimaryEnText(story);
  if (enTitle && enTitle !== primaryTitle) {
    const zh = document.createElement("span");
    zh.className = "story-title-zh";
    zh.textContent = primaryTitle;
    const sub = document.createElement("span");
    sub.className = "story-title-en";
    sub.textContent = enTitle;
    title.append(zh, sub);
  } else {
    title.textContent = primaryTitle;
  }
  body.appendChild(title);

  link.append(time, body);
  return link;
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

function storySortScore(story) {
  return state.boleView === "hot" ? storyHotScore(story) : storyScore(story);
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

function renderBoleBrief(stories) {
  bolePicksListEl.innerHTML = "";
  bolePicksListEl.className = "bole-board";

  const hot = hotStories(stories);
  const hotAvailable = hot.length >= 2;
  // 宁缺毋滥: the hot view only exists when there is real multi-source heat.
  if (boleViewToggleEl) boleViewToggleEl.hidden = !hotAvailable;
  if (!hotAvailable) state.boleView = "timeline";
  if (boleHotBtnEl) boleHotBtnEl.classList.toggle("active", state.boleView === "hot");
  if (boleTimelineBtnEl) boleTimelineBtnEl.classList.toggle("active", state.boleView !== "hot");

  let sorted;
  let metaLabel;
  if (state.boleView === "hot") {
    sorted = hot;
    metaLabel = `当前热点 · ${fmtNumber(sorted.length)} 簇 · 按热度分排序`;
  } else {
    sorted = [...stories].sort((a, b) => {
      const aLatest = storyTimeMs(a, "latest_at") || storyTimeMs(a, "earliest_at");
      const bLatest = storyTimeMs(b, "latest_at") || storyTimeMs(b, "earliest_at");
      if (aLatest !== bLatest) return bLatest - aLatest;
      return storyScore(b) - storyScore(a);
    });
    const topScore = Math.max(...sorted.map((s) => storyScore(s)));
    metaLabel = topScore > 0
      ? `故事时间线 · ${fmtNumber(sorted.length)} 条 · 最高 ${topScore} 分`
      : `故事时间线 · ${fmtNumber(sorted.length)} 条`;
  }

  const list = document.createElement("div");
  list.className = "bole-compact-list bole-timeline";
  const defaultLimit = state.boleView === "hot" ? BOLE_HOT_LIMIT : BOLE_TIMELINE_LIMIT;
  const visibleStories = state.boleExpanded ? sorted : sorted.slice(0, defaultLimit);
  visibleStories.forEach((story, index) => {
    list.appendChild(buildStoryCard(story, index + 1));
  });
  bolePicksListEl.appendChild(list);

  if (sorted.length > defaultLimit) {
    const moreBtn = document.createElement("button");
    moreBtn.type = "button";
    moreBtn.className = "bole-more-btn";
    moreBtn.textContent = state.boleExpanded
      ? "收起"
      : (state.boleView === "hot" ? "展开全部热点" : "展开完整时间线");
    moreBtn.addEventListener("click", () => {
      state.boleExpanded = !state.boleExpanded;
      renderBolePicks();
    });
    bolePicksListEl.appendChild(moreBtn);
  }

  const generatedAt = state.dailyBrief && state.dailyBrief.generated_at;
  bolePicksMetaEl.textContent = generatedAt ? `${metaLabel} · ${fmtTime(generatedAt)}` : metaLabel;
  document.dispatchEvent(new CustomEvent("aiRadar:briefRendered"));
}

function renderBoleFallback(picks) {
  bolePicksListEl.innerHTML = "";
  bolePicksListEl.className = "bole-board";

  const note = document.createElement("div");
  note.className = "bole-fallback-note";
  note.textContent = "故事合并数据暂未生成，先展示伯乐候选信号。";
  bolePicksListEl.appendChild(note);

  if (!picks.length) {
    const empty = document.createElement("div");
    empty.className = "bole-empty";
    empty.textContent = "当前数据里没有可展示的评分字段。";
    bolePicksListEl.appendChild(empty);
    return;
  }

  const timelinePicks = [...picks].sort((a, b) => {
    const byTime = timelineMs(b.item) - timelineMs(a.item);
    if (byTime !== 0) return byTime;
    return b.score - a.score || a.index - b.index;
  });
  const list = document.createElement("div");
  list.className = "bole-compact-list";
  const visiblePicks = state.boleExpanded ? timelinePicks : timelinePicks.slice(0, BOLE_TIMELINE_LIMIT);
  visiblePicks.forEach((row, index) => {
    list.appendChild(buildBoleTimelineRow(row, index + 1));
  });
  bolePicksListEl.appendChild(list);
  if (timelinePicks.length > BOLE_TIMELINE_LIMIT) {
    const moreBtn = document.createElement("button");
    moreBtn.type = "button";
    moreBtn.className = "bole-more-btn";
    moreBtn.textContent = state.boleExpanded ? "收起" : "展开完整时间线";
    moreBtn.addEventListener("click", () => {
      state.boleExpanded = !state.boleExpanded;
      renderBolePicks();
    });
    bolePicksListEl.appendChild(moreBtn);
  }
  document.dispatchEvent(new CustomEvent("aiRadar:briefRendered"));
}

function storyMatchesFilteredItems(story, filteredItems) {
  if (
    state.activeSection === "hot" &&
    !state.siteFilter &&
    !state.authorFilter &&
    !state.sourceTypeFilter &&
    !state.signalLevelFilter &&
    !state.query.trim()
  ) return true;
  const urls = new Set(filteredItems.map((item) => item.url).filter(Boolean));
  const ids = new Set(filteredItems.map((item) => item.id).filter(Boolean));
  const storyRefs = [
    story.primary_item,
    ...(Array.isArray(story.sources) ? story.sources : []),
    ...(Array.isArray(story.items) ? story.items : []),
  ].filter(Boolean);
  return storyRefs.some((ref) => (ref.url && urls.has(ref.url)) || (ref.id && ids.has(ref.id)));
}

function briefStories() {
  return (Array.isArray(state.dailyBrief?.items) ? state.dailyBrief.items : []).filter((story) => !isUnsafeStory(story));
}

function mergedStories() {
  return (Array.isArray(state.storiesMerged?.stories) ? state.storiesMerged.stories : []).filter((story) => !isUnsafeStory(story));
}

function storyStableKey(story) {
  if (!story) return "";
  return story.story_id || story.primary_url || story.url || story.primary_item?.url || story.title || "";
}

function uniqueStories(stories, excludeKeys = new Set(), excludeIdentityKeys = new Set()) {
  const seen = new Set(excludeKeys);
  return stories.filter((story) => {
    const key = storyStableKey(story);
    if (key && seen.has(key)) return false;
    if (storyHasAnyKey(story, excludeIdentityKeys)) return false;
    if (key) seen.add(key);
    return true;
  });
}

function currentStoryPools(filteredItems) {
  if (state.activeSection === "creator") return { brief: [], merged: [], followup: [] };
  const brief = briefStories().filter((story) => storyMatchesFilteredItems(story, filteredItems));
  const merged = mergedStories().filter((story) => storyMatchesFilteredItems(story, filteredItems));
  const briefKeys = new Set(brief.map(storyStableKey).filter(Boolean));
  const briefIdentityKeys = new Set();
  brief.forEach((story) => storyIdentityKeys(story).forEach((key) => briefIdentityKeys.add(key)));
  return {
    brief,
    merged,
    followup: uniqueStories(merged, briefKeys, briefIdentityKeys),
  };
}

function storyRowsForPool(stories) {
  const source = Array.isArray(stories) ? stories : [];
  const pool = state.boleView === "hot"
    ? hotStories(source).slice(0, BOLE_HOT_LIMIT)
    : latestStories(source).slice(0, BOLE_TIMELINE_LIMIT);
  return pool.map(storyToBoleRow);
}

function storyCandidateCounts(stories) {
  const source = Array.isArray(stories) ? stories : [];
  const hotTotal = hotStories(source).length;
  const timelineTotal = source.length;
  return {
    hot: Math.min(BOLE_HOT_LIMIT, hotTotal),
    timeline: Math.min(BOLE_TIMELINE_LIMIT, timelineTotal),
    hotTotal,
    timelineTotal,
  };
}

function latestStories(stories) {
  return [...(Array.isArray(stories) ? stories : [])].sort((a, b) => {
    const aLatest = storyTimeMs(a, "latest_at") || storyTimeMs(a, "earliest_at");
    const bLatest = storyTimeMs(b, "latest_at") || storyTimeMs(b, "earliest_at");
    if (aLatest !== bLatest) return bLatest - aLatest;
    return storyScore(b) - storyScore(a);
  });
}

function renderStoryViewPanel(stories, excludedRows = []) {
  const panel = document.createElement("div");
  panel.className = "bole-story-panel";

  const hot = hotStories(stories);
  let baseSorted;
  let metaLabel;
  if (state.boleView === "hot") {
    baseSorted = hot;
    metaLabel = hot.length
      ? `当前热点 · ${fmtNumber(hot.length)} 簇 · 按热度分排序`
      : "当前热点 · 暂无多源聚簇";
  } else {
    baseSorted = [...stories].sort((a, b) => {
      const aLatest = storyTimeMs(a, "latest_at") || storyTimeMs(a, "earliest_at");
      const bLatest = storyTimeMs(b, "latest_at") || storyTimeMs(b, "earliest_at");
      if (aLatest !== bLatest) return bLatest - aLatest;
      return storyScore(b) - storyScore(a);
    });
    metaLabel = `故事时间线 · ${fmtNumber(baseSorted.length)} 条 · 最新优先`;
  }

  const excludeKeys = excludedStoryKeySet(excludedRows);
  const sorted = excludeKeys.size
    ? baseSorted.filter((story) => !storyHasAnyKey(story, excludeKeys))
    : baseSorted;
  const skippedCount = baseSorted.length - sorted.length;
  const rankOffset = skippedCount > 0 ? excludedRows.length : 0;
  if (skippedCount > 0) {
    metaLabel = state.boleView === "hot"
      ? `当前热点 · ${fmtNumber(baseSorted.length)} 簇 · 续看 #${rankOffset + 1} 起`
      : `故事时间线 · ${fmtNumber(baseSorted.length)} 条 · Top3 后续`;
  }

  if (boleViewToggleEl) {
    boleViewToggleEl.hidden = false;
    if (boleHotBtnEl) boleHotBtnEl.classList.toggle("active", state.boleView === "hot");
    if (boleTimelineBtnEl) boleTimelineBtnEl.classList.toggle("active", state.boleView !== "hot");
  }

  const heading = document.createElement("div");
  heading.className = "bole-story-panel-head";
  heading.textContent = metaLabel;
  panel.appendChild(heading);

  if (!sorted.length) {
    const empty = document.createElement("div");
    empty.className = "bole-empty";
    empty.textContent = skippedCount > 0
      ? "Top3 已覆盖当前筛选下的故事，可切换筛选或时间线继续查看。"
      : state.boleView === "hot"
      ? "当前筛选下没有多源热点，可切换到时间线查看最新故事。"
      : "当前筛选下没有可展示的故事时间线。";
    panel.appendChild(empty);
    return panel;
  }

  const list = document.createElement("div");
  list.className = "bole-compact-list bole-timeline";
  const defaultLimit = state.boleView === "hot" ? BOLE_HOT_LIMIT : BOLE_TIMELINE_LIMIT;
  const visibleStories = state.boleExpanded ? sorted : sorted.slice(0, defaultLimit);
  visibleStories.forEach((story, index) => {
    list.appendChild(buildStoryCard(story, rankOffset + index + 1));
  });
  panel.appendChild(list);

  if (sorted.length > defaultLimit) {
    const moreBtn = document.createElement("button");
    moreBtn.type = "button";
    moreBtn.className = "bole-more-btn";
    moreBtn.textContent = state.boleExpanded
      ? "收起"
      : (skippedCount > 0
        ? (state.boleView === "hot" ? "展开后续热点" : "展开后续时间线")
        : (state.boleView === "hot" ? "展开全部热点" : "展开完整时间线"));
    moreBtn.addEventListener("click", () => {
      state.boleExpanded = !state.boleExpanded;
      renderBolePicks();
    });
    panel.appendChild(moreBtn);
  }

  return panel;
}

function storyToBoleRow(story, index) {
  const enrichStoryItem = (entry) => ({
    ...entry,
    site_name: entry.site_name || entry.source_name || story.source_name || "",
  });
  const item = enrichStoryItem(story.primary_item || story);
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
    score: storySortScore(story),
  };
}

function rankedBriefRows(stories) {
  const sorted = [...stories].sort((a, b) => {
    const aLatest = storyTimeMs(a, "latest_at") || storyTimeMs(a, "earliest_at");
    const bLatest = storyTimeMs(b, "latest_at") || storyTimeMs(b, "earliest_at");
    if (state.boleView === "hot") {
      const byHeat = storyHotScore(b) - storyHotScore(a);
      if (byHeat !== 0) return byHeat;
      const byScore = storyScore(b) - storyScore(a);
      if (byScore !== 0) return byScore;
      return bLatest - aLatest;
    }
    const byScore = storyScore(b) - storyScore(a);
    if (byScore !== 0) return byScore;
    return bLatest - aLatest;
  });
  return sorted.map(storyToBoleRow);
}

function rankedFallbackRows(items) {
  const rows = rankedClustersForItems(items);
  return state.boleView === "hot"
    ? rows.sort((a, b) => b.sourceCount - a.sourceCount || b.score - a.score || timelineMs(b.item) - timelineMs(a.item))
    : rows.sort((a, b) => timelineMs(b.item) - timelineMs(a.item) || b.score - a.score);
}

function buildBoleFollowupPanel(rows, topCount, usesStories) {
  const remaining = rows.slice(topCount);
  if (!remaining.length) return null;

  const panel = document.createElement("div");
  panel.className = "bole-story-panel";
  const heading = document.createElement("div");
  heading.className = "bole-story-panel-head";
  const viewLabel = state.boleView === "hot" ? "当前热点" : "故事时间线";
  heading.textContent = `${viewLabel} · ${fmtNumber(rows.length)} 条${usesStories ? "故事" : "候选"} · Top${topCount} 后续`;
  panel.appendChild(heading);

  const list = document.createElement("div");
  list.className = "bole-compact-list bole-timeline";
  const followupLimit = 2;
  const visibleRows = state.boleExpanded ? remaining : remaining.slice(0, followupLimit);
  visibleRows.forEach((row, index) => {
    const rank = topCount + index + 1;
    list.appendChild(row.story
      ? buildStoryCard(row.story, rank)
      : buildBoleTimelineRow(row, rank));
  });
  panel.appendChild(list);

  if (remaining.length > followupLimit) {
    const moreBtn = document.createElement("button");
    moreBtn.type = "button";
    moreBtn.className = "bole-more-btn";
    moreBtn.textContent = state.boleExpanded
      ? "收起后续"
      : `展开后续 ${fmtNumber(remaining.length - followupLimit)} 条`;
    moreBtn.addEventListener("click", () => {
      state.boleExpanded = !state.boleExpanded;
      renderBolePicks();
    });
    panel.appendChild(moreBtn);
  }
  return panel;
}

function renderBolePicks() {
  if (!bolePicksListEl || !bolePicksMetaEl) return;
  bolePicksListEl.innerHTML = "";
  bolePicksListEl.className = "top-stories-grid";
  if (boleViewToggleEl) boleViewToggleEl.hidden = true;
  if (bolePicksWrapEl) bolePicksWrapEl.hidden = false;

  const section = SECTION_BY_ID[state.activeSection] || SECTION_BY_ID.hot;
  const filtered = getFilteredItems();
  const storyPools = currentStoryPools(filtered);
  const availableStoryPool = storyPools.brief.length
    ? [...storyPools.brief, ...storyPools.followup]
    : storyPools.merged;
  const usesStories = availableStoryPool.length > 0;
  const candidateCounts = storyCandidateCounts(availableStoryPool);
  const hotAvailable = usesStories && candidateCounts.hot >= 2;
  if (usesStories && !hotAvailable && state.boleView === "hot") {
    state.boleView = "timeline";
  }
  const defaultLimit = state.boleView === "hot" ? BOLE_HOT_LIMIT : BOLE_TIMELINE_LIMIT;
  const rows = usesStories
    ? storyRowsForPool(availableStoryPool)
    : rankedFallbackRows(filtered).slice(0, defaultLimit);
  const top = rows.slice(0, 3);
  const remainingCount = Math.max(0, rows.length - top.length);
  if (topStoriesTitleEl) topStoriesTitleEl.textContent = state.activeSection === "hot" ? "今日重点信号" : `${section.label}重点信号`;
  const storyMeta = usesStories
    ? `展示池：热点 ${fmtNumber(candidateCounts.hot)}/${fmtNumber(candidateCounts.hotTotal)} · 时间线 ${fmtNumber(candidateCounts.timeline)}/${fmtNumber(candidateCounts.timelineTotal)}`
    : `展示池：${fmtNumber(rows.length)} 条`;
  bolePicksMetaEl.textContent = storyMeta;
  if (boleViewToggleEl) {
    boleViewToggleEl.hidden = usesStories ? !hotAvailable : true;
    if (boleHotBtnEl) boleHotBtnEl.classList.toggle("active", state.boleView === "hot");
    if (boleTimelineBtnEl) boleTimelineBtnEl.classList.toggle("active", state.boleView === "timeline");
    if (boleHotBtnEl) boleHotBtnEl.textContent = `当前热点 ${fmtNumber(candidateCounts.hot)}`;
    if (boleTimelineBtnEl) boleTimelineBtnEl.textContent = `时间线 ${fmtNumber(candidateCounts.timeline)}`;
  }

  if (!top.length) {
    const empty = document.createElement("div");
    empty.className = "bole-empty";
    empty.textContent = "当前栏目和筛选条件下没有可展示的 Top 3。";
    bolePicksListEl.appendChild(empty);
  } else {
    top.forEach((row, index) => {
      bolePicksListEl.appendChild(buildTopStoryCard(row, index + 1));
    });
  }

  const followup = buildBoleFollowupPanel(rows, top.length, usesStories);
  if (followup) {
    bolePicksListEl.appendChild(followup);
  }
  document.dispatchEvent(new CustomEvent("aiRadar:briefRendered"));
}

function rankedClustersForItems(items) {
  const rows = [...items]
    .map((item, index) => ({
      item,
      index,
      score: state.activeSection === "creator"
        ? creatorHotScore(item)
        : (scorePercent(item) || Math.round(itemPriorityScore(item))),
    }))
    .filter((row) => row.item && (row.score > 0 || row.item.title))
    .sort((a, b) => itemPriorityScore(b.item) - itemPriorityScore(a.item) || timelineMs(b.item) - timelineMs(a.item));

  return clusterBoleEvents(rows).sort((a, b) => {
    const byHeadlineScore = headlineClusterScore(b) - headlineClusterScore(a);
    if (byHeadlineScore !== 0) return byHeadlineScore;
    return timelineMs(b.item) - timelineMs(a.item) || a.index - b.index;
  });
}

function headlineClusterScore(cluster) {
  const base = itemPriorityScore(cluster.item);
  const sourceBoost = Math.min(18, Math.max(0, cluster.sourceCount - 1) * 9);
  const mergeBoost = Math.min(8, Math.max(0, cluster.mergedCount - 1) * 4);
  return Math.min(100, Math.round(base + sourceBoost + mergeBoost));
}

function pickTopHeadlineClusters(clusters, limit = 3) {
  return [...clusters]
    .sort((a, b) => headlineClusterScore(b) - headlineClusterScore(a) || timelineMs(b.item) - timelineMs(a.item) || a.index - b.index)
    .slice(0, limit)
    .map((cluster) => ({ ...cluster, score: headlineClusterScore(cluster) }));
}

function itemTagLabels(item, row = null) {
  const tags = [];
  const sections = itemSections(item);
  if (state.activeSection !== "hot") tags.push(sectionBadgeLabel(state.activeSection));
  if (row && (row.sourceCount > 1 || row.mergedCount > 1)) tags.push("多源验证");
  if (item.site_id === "official_ai") tags.push("官方");
  if (item.site_id === "aihot") tags.push("AI HOT");
  if (sections.has("models")) tags.push("模型发布");
  if (sections.has("devtools")) tags.push("开发者");
  if (sections.has("hn")) tags.push("社区热议");
  if (sections.has("research")) tags.push("研究");
  if (sections.has("creator")) tags.push("自媒体");
  if (sections.has("community")) tags.push("社区");
  return Array.from(new Set(tags)).slice(0, 3);
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

  return refs.length ? refs : [{ label: "来源", tone: "default" }];
}

function priorityGrade(score) {
  if (score >= 92) return "A+";
  if (score >= 82) return "A";
  if (score >= 70) return "B";
  return "C";
}

function rowSourceCount(row) {
  const item = row.item || {};
  const refs = itemSourceRefs(item, row);
  const storyCount = row.story ? storySourceCount(row.story) : 0;
  return Math.max(1, refs.length, Number(row.sourceCount || 0), Number(row.mergedCount || 0), storyCount);
}

function signalSummaryText(row) {
  const item = row.item || {};
  const story = row.story || {};
  const label = story.importance_label || labelText(item);
  const sourceCount = rowSourceCount(row);
  const multi = row.sourceCount > 1 || row.mergedCount > 1;
  if (multi && label) return `${label}信号，已被 ${fmtNumber(sourceCount)} 个来源验证，适合优先判断是否继续深挖。`;
  const reason = reasonText(item);
  if (reason && !reason.startsWith("来源与标题")) return reason.replace(/^命中方向：/, "核心方向：");
  return `${label}方向的新近更新，已进入 24 小时 AI 强相关池。`;
}

function whyImportantText(row) {
  const item = row.item || {};
  const story = row.story || {};
  const sections = itemSections(item);
  const reasons = Array.isArray(story.reasons) ? story.reasons : [];
  if (reasons.includes("official_source") && reasons.includes("multi_source")) {
    return "一手来源和聚合来源同时出现，说明它既有事实起点，也正在被外部信息流放大。";
  }
  if (sections.has("models")) {
    return "模型能力或训练/推理方式变化会影响后续产品路线、开发者选型和评测基准。";
  }
  if (sections.has("devtools")) {
    return "开发者工具和基础设施变化通常会很快传导到团队工作流、成本和可实现能力。";
  }
  if (sections.has("industry")) {
    return "公司、监管、芯片或资本动态会改变 AI 生态的资源分配和落地节奏。";
  }
  if (sections.has("research")) {
    return "研究信号可能还没产品化，但会提示下一轮模型、数据或方法的技术方向。";
  }
  if (sections.has("community") || sections.has("hn")) {
    return "社区集中讨论代表开发者和早期用户正在形成共识，适合作为趋势验证入口。";
  }
  return "它在当前 24 小时窗口里同时具备相关度、新鲜度和来源权重，值得先读原文确认。";
}

function impactLabels(item) {
  const sections = itemSections(item);
  const labels = [];
  if (sections.has("devtools")) labels.push("开发者");
  if (sections.has("products")) labels.push("产品");
  if (sections.has("industry")) labels.push("企业 / 投资");
  if (sections.has("research")) labels.push("研究");
  if (sections.has("models")) labels.push("模型团队");
  if (sections.has("community") || sections.has("hn")) labels.push("社区");
  return labels.slice(0, 3).length ? labels.slice(0, 3) : ["AI 观察者"];
}

function buildTopStoryCard(row, rank) {
  const item = row.item;
  const link = document.createElement("a");
  link.className = `top-story-card ${rank === 1 ? "lead" : "secondary"}`;
  link.href = item.url || "#";
  link.target = "_blank";
  link.rel = "noopener noreferrer";

  const rankEl = document.createElement("span");
  rankEl.className = "top-rank";
  rankEl.textContent = `#${rank}`;

  const meta = document.createElement("div");
  meta.className = "intel-meta";
  const time = document.createElement("time");
  // Brief stories keep their timeline on the story object rather than repeating
  // it on primary_item. Fall back to that aggregate time so Top 3 never shows
  // "时间未知" when the story itself has a verified latest/earliest timestamp.
  const storyTimeline = row.story?.latest_at || row.story?.earliest_at || "";
  time.textContent = fmtTime(timelineIso(item) || storyTimeline);
  const primarySource = itemSourceRefs(item, row)[0];
  const score = document.createElement("strong");
  const displayScore = row.story
    ? Math.max(row.score || 0, storyScore(row.story))
    : Math.max(row.score || 0, headlineClusterScore(row));
  score.className = `intel-score ${scoreTone(displayScore)}`;
  score.textContent = `优先级 ${priorityGrade(displayScore)}`;
  const sourceCount = document.createElement("span");
  sourceCount.className = "source-count";
  sourceCount.textContent = `${fmtNumber(rowSourceCount(row))} 个来源`;
  meta.append(rankEl, sourceChip(primarySource.label, primarySource.tone, "source-chip intel-source"), sourceCount, score, time);

  const title = document.createElement("div");
  title.className = "top-story-title";
  title.textContent = itemTitleText(item);

  const summary = document.createElement("p");
  summary.className = "top-story-summary";
  summary.textContent = signalSummaryText(row);

  const why = document.createElement("div");
  why.className = "top-story-why";
  const whyLabel = document.createElement("span");
  whyLabel.textContent = "为什么重要";
  const whyText = document.createElement("p");
  whyText.textContent = whyImportantText(row);
  why.append(whyLabel, whyText);

  const tags = document.createElement("div");
  tags.className = "intel-tags";
  itemTagLabels(item, row).forEach((label) => {
    tags.appendChild(itemTagChip(label));
  });

  const impact = document.createElement("div");
  impact.className = "impact-row";
  impactLabels(item).forEach((label) => {
    const chip = document.createElement("span");
    chip.textContent = label;
    impact.appendChild(chip);
  });

  link.append(meta, title, summary, why, tags, impact);
  return link;
}

function buildIntelCard(item, rank) {
  const card = document.createElement("article");
  card.className = "intel-card";

  const meta = document.createElement("div");
  meta.className = "intel-card-meta";
  const rankEl = document.createElement("span");
  rankEl.className = "intel-card-rank";
  rankEl.textContent = `#${rank}`;
  const time = document.createElement("time");
  time.textContent = fmtTime(timelineIso(item));
  const score = scorePercent(item);
  const scoreEl = document.createElement("strong");
  scoreEl.className = `intel-score ${scoreTone(score)}`;
  scoreEl.textContent = score ? `AI ${score}分` : "AI观察";
  meta.append(rankEl, time, scoreEl);

  const title = document.createElement("a");
  title.className = "intel-title";
  title.href = item.url || "#";
  title.target = "_blank";
  title.rel = "noopener noreferrer";
  title.textContent = itemTitleText(item);

  const reason = document.createElement("p");
  reason.className = "intel-reason";
  reason.textContent = reasonText(item);

  const tags = document.createElement("div");
  tags.className = "intel-tags";
  itemTagLabels(item).forEach((label) => {
    tags.appendChild(itemTagChip(label));
  });

  const sources = document.createElement("div");
  sources.className = "intel-card-sources";
  const refs = itemSourceRefs(item);
  const count = document.createElement("strong");
  count.textContent = `${fmtNumber(refs.length)} 个来源`;
  sources.appendChild(count);
  refs.slice(0, 3).forEach((ref) => {
    sources.appendChild(sourceChip(ref.label, ref.tone, "source-chip"));
  });

  card.append(meta, title, reason, tags, sources);
  return card;
}

function feedSummaryText(item) {
  const signals = Array.isArray(item.ai_signals) ? item.ai_signals.filter(Boolean).slice(0, 2) : [];
  if (signals.length) return `相关线索：${signals.join(" / ")}。`;
  const reason = reasonText(item);
  if (reason && !reason.startsWith("来源与标题")) return reason.replace(/^命中方向：/, "相关线索：");
  return `${labelText(item)} · AI 相关度 ${scorePercent(item) || "待评估"}。`;
}

function renderItemNode(item, context = {}) {
  const node = itemTpl.content.firstElementChild.cloneNode(true);
  const metaRow = node.querySelector(".meta-row");
  const siteEl = node.querySelector(".site");
  siteEl.textContent = item.source || item.site_name;
  if (context.source && context.source === item.source) {
    siteEl.hidden = true;
  }
  const kind = sourceKind(item.site_id);
  const categoryEl = node.querySelector(".category");
  categoryEl.textContent = kind.label;
  categoryEl.classList.add(`kind-${kind.tone}`);
  const score = scorePercent(item);
  const creatorScore = creatorHotScore(item);
  const tagEl = document.createElement("span");
  tagEl.className = `ai-tag tone-${itemLabelTone(item)}`;
  tagEl.textContent = creatorScore && itemSections(item).has("creator")
    ? `自媒体热度 · ${creatorScore}分`
    : `${labelText(item)} · ${score || "?"}分`;
  categoryEl.insertAdjacentElement("afterend", tagEl);

  const sourceEl = node.querySelector(".source");
  const sourceLabel = sourceSignal(item);
  setSourceBadge(sourceEl, sourceLabel, sourceSignalTone(sourceLabel), item.source ? `分区: ${item.source}` : "");
  if (context.source && context.source === item.source) {
    sourceEl.hidden = true;
  }

  const primaryLabel = labelText(item);
  itemTagLabels(item)
    .filter((label) => label !== primaryLabel)
    .slice(0, 3)
    .forEach((label) => {
      metaRow.insertBefore(itemTagChip(label), sourceEl);
    });

  node.querySelector(".time").textContent = fmtTime(item.published_at || item.first_seen_at);

  const titleEl = node.querySelector(".title");
  const zh = (item.title_zh || "").trim();
  const en = (item.title_en || "").trim();
  titleEl.textContent = "";
  if (zh && en && zh !== en) {
    const primary = document.createElement("span");
    primary.textContent = zh;
    const sub = document.createElement("span");
    sub.className = "title-sub";
    sub.textContent = en;
    titleEl.appendChild(primary);
    titleEl.appendChild(sub);
  } else {
    titleEl.textContent = item.title || zh || en;
  }
  titleEl.href = item.url;
  const summaryEl = node.querySelector(".news-summary");
  if (summaryEl) summaryEl.textContent = feedSummaryText(item);
  return node;
}

const SOURCE_ITEM_INITIAL_LIMIT = 3;
const SITE_GROUP_INITIAL_LIMIT = 4;
const SITE_GROUP_LOAD_STEP = 4;
const SITE_SOURCE_GROUP_INITIAL_LIMIT = 4;
const SITE_SOURCE_GROUP_LOAD_STEP = 4;
const SOURCE_GROUP_INITIAL_LIMIT = 8;
const SOURCE_GROUP_LOAD_STEP = 8;
const BOLE_HOT_LIMIT = 10;
const BOLE_TIMELINE_LIMIT = 20;

function buildSourceGroupNode(source, items, rawCount = items.length) {
  const section = document.createElement("section");
  section.className = "source-group";
  const header = document.createElement("header");
  header.className = "source-group-head";
  const title = document.createElement("h3");
  title.textContent = source;
  const count = document.createElement("span");
  count.className = "group-summary";
  count.textContent = subgroupSummary(items, rawCount);
  const listEl = document.createElement("div");
  listEl.className = "source-group-list";
  header.append(title, count);
  section.append(header, listEl);

  let expanded = false;
  if (items.length > SOURCE_ITEM_INITIAL_LIMIT) {
    const moreBtn = document.createElement("button");
    moreBtn.type = "button";
    moreBtn.className = "group-more-btn";
    const renderItems = () => {
      listEl.innerHTML = "";
      const visibleItems = expanded ? items : items.slice(0, SOURCE_ITEM_INITIAL_LIMIT);
      visibleItems.forEach((item) => listEl.appendChild(renderItemNode(item, { source })));
      moreBtn.textContent = expanded
        ? `收起，仅看前 ${SOURCE_ITEM_INITIAL_LIMIT} 条`
        : `展开剩余 ${fmtNumber(items.length - SOURCE_ITEM_INITIAL_LIMIT)} 条`;
    };
    moreBtn.addEventListener("click", () => {
      expanded = !expanded;
      renderItems();
    });
    renderItems();
    section.append(moreBtn);
  } else {
    items.forEach((item) => listEl.appendChild(renderItemNode(item, { source })));
  }
  return section;
}

function displayDedupeKey(item) {
  const title = normalizedEventText(itemTitleText(item));
  // Short social-post titles such as "AI小狗" still identify the same visible
  // post within one creator subgroup; URL query strings often only carry a
  // rotating access token and must not defeat that deduplication.
  if (title) return `title:${title}`;
  try {
    const url = new URL(item.url || "");
    return `url:${url.origin}${url.pathname}`;
  } catch {
    return `url:${item.url || item.id || "untitled"}`;
  }
}

function dedupeSubgroupItems(items) {
  const seen = new Set();
  return sortItemsForList(items).filter((item) => {
    const key = displayDedupeKey(item);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function subgroupSortValue(items) {
  if (!items.length) return 0;
  if (state.listSort === "latest") return Math.max(...items.map(timelineMs));
  if (state.listSort === "ai") return Math.max(...items.map(scorePercent));
  if (state.listSort === "source") return items.length;
  const leading = [...items]
    .sort((a, b) => itemPriorityScore(b) - itemPriorityScore(a))
    .slice(0, 3);
  return Math.round(leading.reduce((sum, item) => sum + itemPriorityScore(item), 0) / leading.length);
}

function subgroupSummary(items, rawCount = items.length) {
  const count = `${fmtNumber(items.length)} 条`;
  const merged = rawCount - items.length;
  let ranking = "";
  if (state.listSort === "priority") ranking = `综合 ${subgroupSortValue(items)}`;
  if (state.listSort === "latest") ranking = `最新 ${fmtTime(timelineIso(items[0]))}`;
  if (state.listSort === "ai") ranking = `最高 AI ${subgroupSortValue(items)}分`;
  const mergedLabel = merged > 0 ? `合并 ${fmtNumber(merged)} 条重复` : "";
  return [count, ranking, mergedLabel].filter(Boolean).join(" · ");
}

function sourceGroupEntries(items) {
  const groupMap = new Map();
  items.forEach((item) => {
    const key = item.source || "未分区";
    if (!groupMap.has(key)) {
      groupMap.set(key, []);
    }
    groupMap.get(key).push(item);
  });

  return Array.from(groupMap.entries())
    .map(([source, rawItems]) => ({
      source,
      rawCount: rawItems.length,
      items: dedupeSubgroupItems(rawItems),
    }))
    .filter((group) => group.items.length)
    .sort((a, b) => {
      const byScore = subgroupSortValue(b.items) - subgroupSortValue(a.items);
      if (byScore !== 0) return byScore;
      const byCount = b.items.length - a.items.length;
      if (byCount !== 0) return byCount;
      return a.source.localeCompare(b.source, "zh-CN");
    });
}

// Mobile-safe async rendering: avoid blocking the main thread on large lists.
// We chunk site-groups and yield between each chunk so the browser can paint
// and respond to touch events while the list is being built.
let _renderListToken = 0;

function buildSiteGroupNode(site) {
  const siteSection = document.createElement("section");
  siteSection.className = "site-group";
  const header = document.createElement("header");
  header.className = "site-group-head";
  const title = document.createElement("h3");
  title.textContent = site.siteName;
  const count = document.createElement("span");
  count.className = "group-summary";
  count.textContent = subgroupSummary(site.items, site.rawCount);
  const siteListEl = document.createElement("div");
  siteListEl.className = "site-group-list";
  header.append(title, count);
  siteSection.append(header, siteListEl);

  const sourceGroups = site.sourceGroups;
  let expanded = false;
  let moreBtn = null;
  const renderSourceGroups = () => {
    siteListEl.innerHTML = "";
    if (moreBtn) moreBtn.remove();
    const visibleGroups = expanded
      ? sourceGroups
      : sourceGroups.slice(0, SITE_SOURCE_GROUP_INITIAL_LIMIT);
    const frag = document.createDocumentFragment();
    visibleGroups.forEach((group) => {
      frag.appendChild(buildSourceGroupNode(group.source, group.items, group.rawCount));
    });
    siteListEl.appendChild(frag);
    if (sourceGroups.length > SITE_SOURCE_GROUP_INITIAL_LIMIT) {
      const hiddenCount = sourceGroups.length - SITE_SOURCE_GROUP_INITIAL_LIMIT;
      moreBtn = addLoadMoreButton(
        siteSection,
        expanded
          ? `收起，仅看前 ${SITE_SOURCE_GROUP_INITIAL_LIMIT} 个分区`
          : `展开其余 ${fmtNumber(hiddenCount)} 个分区`,
        () => {
          expanded = !expanded;
          renderSourceGroups();
        },
      );
    }
  };
  renderSourceGroups();
  return siteSection;
}

function renderLoadingNotice(label, count) {
  const loading = document.createElement("div");
  loading.className = "list-loading";
  loading.textContent = `正在整理 ${label} · ${fmtNumber(count)} 条`;
  newsListEl.appendChild(loading);
}

function currentFilterLabel(filtered) {
  if (state.authorFilter) return `${listTitleText()} · X 博主 ${state.authorFilter}`;
  if (state.siteFilter) {
    const item = filtered[0];
    const stat = currentSiteStats().find((s) => s.site_id === state.siteFilter);
    return `${listTitleText()} · ${item?.site_name || stat?.site_name || state.siteFilter}`;
  }
  return listTitleText();
}

function groupedSites(items) {
  const siteMap = new Map();
  items.forEach((item) => {
    if (!siteMap.has(item.site_id)) {
      siteMap.set(item.site_id, { siteName: item.site_name || item.site_id, rawItems: [] });
    }
    siteMap.get(item.site_id).rawItems.push(item);
  });

  return Array.from(siteMap.entries())
    .map(([siteId, site]) => {
      const sourceGroups = sourceGroupEntries(site.rawItems);
      return [siteId, {
        siteName: site.siteName,
        rawCount: site.rawItems.length,
        sourceGroups,
        items: sourceGroups.flatMap((group) => group.items),
      }];
    })
    .filter(([, site]) => site.items.length)
    .sort((a, b) => {
      const byScore = subgroupSortValue(b[1].items) - subgroupSortValue(a[1].items);
      if (byScore !== 0) return byScore;
      const byCount = b[1].items.length - a[1].items.length;
      if (byCount !== 0) return byCount;
      return a[1].siteName.localeCompare(b[1].siteName, "zh-CN");
    });
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

function renderSiteGroups(items) {
  const groups = groupedSites(items);
  const visibleGroups = state.siteGroupsExpanded
    ? groups
    : groups.slice(0, SITE_GROUP_INITIAL_LIMIT);
  visibleGroups.forEach(([, site]) => {
    newsListEl.appendChild(buildSiteGroupNode(site));
  });

  if (groups.length > SITE_GROUP_INITIAL_LIMIT) {
    const hiddenCount = groups.length - SITE_GROUP_INITIAL_LIMIT;
    addLoadMoreButton(
      newsListEl,
      state.siteGroupsExpanded
        ? `收起，仅看前 ${SITE_GROUP_INITIAL_LIMIT} 个来源`
        : `展开其余 ${fmtNumber(hiddenCount)} 个来源`,
      () => {
        state.siteGroupsExpanded = !state.siteGroupsExpanded;
        renderList();
      },
    );
  }
  document.dispatchEvent(new CustomEvent("aiRadar:listRendered"));
}

function renderList() {
  const filtered = getFilteredItems();
  renderListSortTools();
  resultCountEl.textContent = `${fmtNumber(filtered.length)} 条`;
  renderSectionSummary(filtered);

  newsListEl.innerHTML = "";
  _renderListToken += 1;           // invalidate any in-flight render
  const token = _renderListToken;

  if (!filtered.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "当前筛选条件下没有结果。";
    newsListEl.appendChild(empty);
    return;
  }

  renderLoadingNotice(currentFilterLabel(filtered), filtered.length);
  requestAnimationFrame(() => {
    if (token !== _renderListToken) return;   // stale render, abort
    const sorted = sortItemsForList(filtered);
    newsListEl.innerHTML = "";
    renderSiteGroups(sorted);
  });
}

function rerenderCurrentView() {
  state.boleExpanded = false;
  state.siteGroupsExpanded = false;
  renderSectionTabs();
  renderModeSwitch();
  renderSiteFilters();
  renderBolePicks();
  if (state.waytoagiData) renderWaytoagi(state.waytoagiData);
  renderList();
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
  if (waytoagiWrapEl) {
    waytoagiWrapEl.hidden = state.activeSection !== "community";
  }
  if (state.activeSection !== "community") return;
  const { updates7d, updatesToday, latestDate } = waytoagiViews(waytoagi);
  if (waytoagiTodayBtnEl) waytoagiTodayBtnEl.classList.toggle("active", state.waytoagiMode === "today");
  if (waytoagi7dBtnEl) waytoagi7dBtnEl.classList.toggle("active", state.waytoagiMode === "7d");
  waytoagiUpdatedAtEl.textContent = `更新时间：${fmtTime(waytoagi.generated_at)}`;

  waytoagiMetaEl.innerHTML = "";
  const rootLink = document.createElement("a");
  rootLink.href = waytoagi.root_url || "#";
  rootLink.target = "_blank";
  rootLink.rel = "noopener noreferrer";
  rootLink.textContent = "主页面";
  const historyLink = document.createElement("a");
  historyLink.href = waytoagi.history_url || "#";
  historyLink.target = "_blank";
  historyLink.rel = "noopener noreferrer";
  historyLink.textContent = "历史更新页";
  const todayCount = document.createElement("span");
  todayCount.textContent = `最近更新日(${latestDate || "--"})：${fmtNumber(waytoagi.count_today || updatesToday.length)} 条`;
  const weekCount = document.createElement("span");
  weekCount.textContent = `近 7 日：${fmtNumber(waytoagi.count_7d || updates7d.length)} 条`;
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
    div.textContent = waytoagi.error || "WaytoAGI 数据加载失败";
    waytoagiListEl.appendChild(div);
    return;
  }

  const updates = state.waytoagiMode === "today" ? updatesToday : updates7d;
  if (!updates.length) {
    const div = document.createElement("div");
    div.className = "waytoagi-empty";
    div.textContent = state.waytoagiMode === "today"
      ? "最近更新日没有更新，可切换到近7日查看。"
      : (waytoagi.warning || "近 7 日没有更新");
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

function renderMetric(label, value, tone = "", options = {}) {
  const interactive = typeof options.onClick === "function";
  const node = document.createElement(interactive ? "button" : "div");
  node.className = `health-metric ${interactive ? "health-metric-button" : ""} ${tone}`.trim();
  if (interactive) {
    node.type = "button";
    node.title = options.title || "查看详情";
    node.setAttribute("aria-expanded", String(Boolean(options.expanded)));
    node.addEventListener("click", options.onClick);
  }
  const labelEl = document.createElement("span");
  labelEl.className = "health-label";
  labelEl.textContent = label;
  const valueEl = document.createElement("strong");
  valueEl.textContent = value;
  node.append(labelEl, valueEl);
  return node;
}

function socialdataAuthors() {
  return Array.from(new Set(
    state.itemsAi
      .filter((item) => item.site_id === "socialdata_x")
      .map((item) => String(item.source || "").trim())
      .filter(Boolean),
  )).sort((a, b) => a.localeCompare(b, "en"));
}

function selectSocialdataAuthor(author) {
  state.authorFilter = author;
  state.siteFilter = "socialdata_x";
  state.activeSection = "hot";
  state.boleExpanded = false;
  state.siteGroupsExpanded = false;
  state.xAuthorsExpanded = false;
  renderSectionTabs();
  renderModeSwitch();
  renderSiteFilters();
  renderBolePicks();
  renderList();
  renderSourceHealth();
  document.querySelector(".list-wrap")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderSocialdataAuthorList(authors, itemCount) {
  const panel = document.createElement("section");
  panel.className = "health-author-list";
  const heading = document.createElement("div");
  heading.className = "health-author-list-title";
  heading.textContent = "本轮 X 扫到的博主";
  const meta = document.createElement("div");
  meta.className = "health-author-list-meta";
  meta.textContent = `${fmtNumber(authors.length)} 位博主 · ${fmtNumber(itemCount)} 条入池内容`;
  const list = document.createElement("div");
  list.className = "health-author-list-items";
  authors.forEach((author) => {
    const item = document.createElement("button");
    item.type = "button";
    item.textContent = author;
    item.title = `查看 ${author} 的 X 内容`;
    item.addEventListener("click", () => selectSocialdataAuthor(author));
    list.appendChild(item);
  });
  panel.append(heading, meta, list);
  return panel;
}

function renderIssueList(title, items) {
  const wrap = document.createElement("div");
  wrap.className = "health-issue";
  const titleEl = document.createElement("div");
  titleEl.className = "health-issue-title";
  titleEl.textContent = title;
  const list = document.createElement("ul");
  items.slice(0, 6).forEach((item) => {
    const li = document.createElement("li");
    li.textContent = typeof item === "string" ? item : JSON.stringify(item);
    list.appendChild(li);
  });
  if (items.length > 6) {
    const li = document.createElement("li");
    li.textContent = `另有 ${fmtNumber(items.length - 6)} 项`;
    list.appendChild(li);
  }
  wrap.append(titleEl, list);
  return wrap;
}

function renderSourceHealthSummaryNode(status, errorMessage = "") {
  const node = document.createElement("div");
  node.className = "source-health-summary";
  if (!status) {
    node.classList.add(errorMessage ? "bad" : "warn");
    node.innerHTML = `<strong>${errorMessage ? "源状态异常" : "源状态未生成"}</strong><span>${errorMessage || "等待 source-status.json"}</span>`;
    return node;
  }
  const sites = Array.isArray(status.sites) ? status.sites : [];
  const okSites = Number(status.successful_sites || 0);
  const failed = failedSourceCount(status);
  const fetched = Number(status.fetched_raw_items || state.totalRaw || status.items_before_topic_filter || 0);
  node.classList.toggle("warn", failed > 0);
  node.innerHTML = `<strong>${fmtNumber(okSites)}/${fmtNumber(sites.length)} 源正常</strong><span>今日采集 ${fmtNumber(fetched)} 条 · 失败 ${fmtNumber(failed)}</span>`;
  return node;
}

function renderSourceStatusTable(status) {
  if (!sourceStatusTableEl) return;
  sourceStatusTableEl.innerHTML = "";
  if (!status || !Array.isArray(status.sites) || !status.sites.length) return;

  const rows = status.sites
    .map((site) => {
      const ai = aiSiteStat(site.site_id);
      const aiCount = Number(ai?.count || 0);
      const rawCount = Number(ai?.raw_count ?? site.item_count ?? 0);
      const scanned = Number(site.item_count || rawCount || 0);
      const ratioBase = rawCount || scanned;
      const ratio = ratioBase ? Math.round((aiCount / ratioBase) * 100) : 0;
      return { ...site, aiCount, rawCount: ratioBase, ratio };
    })
    .sort((a, b) => b.aiCount - a.aiCount || b.rawCount - a.rawCount || String(a.site_name).localeCompare(String(b.site_name), "zh-CN"))
    .slice(0, 12);

  const table = document.createElement("div");
  table.className = "source-table";
  const header = document.createElement("div");
  header.className = "source-table-row source-table-head";
  header.innerHTML = "<span>来源</span><span>AI / 原始</span><span>AI占比</span><span>状态</span>";
  table.appendChild(header);
  rows.forEach((site) => {
    const row = document.createElement("div");
    row.className = "source-table-row";
    const statusText = site.ok ? "正常" : "异常";
    row.innerHTML = `
      <span>${site.site_name || site.site_id}</span>
      <span>${fmtNumber(site.aiCount)} / ${fmtNumber(site.rawCount)}</span>
      <span>${fmtNumber(site.ratio)}%</span>
      <span class="${site.ok ? "ok" : "bad"}">${statusText}</span>
    `;
    table.appendChild(row);
  });
  sourceStatusTableEl.appendChild(table);
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
    renderAdvancedSummary();
    setStats();
    return;
  }

  const sites = Array.isArray(status.sites) ? status.sites : [];
  const failedSites = Array.isArray(status.failed_sites) ? status.failed_sites : [];
  const zeroSites = Array.isArray(status.zero_item_sites) ? status.zero_item_sites : [];
  const rss = status.rss_opml || {};
  const agentmail = status.agentmail || {};
  const xApi = status.x_api || {};
  const socialdata = status.socialdata || {};
  const emptyAdvanced = Array.isArray(status.empty_advanced_sources) ? status.empty_advanced_sources : [];
  const failedFeeds = Array.isArray(rss.failed_feeds) ? rss.failed_feeds : [];
  const skippedFeeds = Array.isArray(rss.skipped_feeds) ? rss.skipped_feeds : [];
  const replacedFeeds = Array.isArray(rss.replaced_feeds) ? rss.replaced_feeds : [];
  // Paid sources run on a protected interval. A skipped refresh can still have
  // usable records from the last successful run in today's data pool, so don't
  // hide them behind a misleading "待窗口" status.
  const socialdataLiveCount = Number(socialdata.item_count || 0);
  const socialdataPoolCount = siteAiPoolCount("socialdata_x");
  const socialdataDisplayCount = socialdataLiveCount || socialdataPoolCount;
  const xApiLiveCount = Number(xApi.item_count || 0);
  const xApiPoolCount = siteAiPoolCount("xapi");
  const xApiDisplayCount = xApiLiveCount || xApiPoolCount;
  const xDisplayCount = socialdataDisplayCount + xApiDisplayCount;
  const xAuthors = socialdataAuthors();

  const xMetricValue = xDisplayCount
    ? `已入池 ${fmtNumber(xDisplayCount)}条`
    : socialdata.enabled
    ? (socialdataDisplayCount
      ? "成功"
      : (socialdata.skipped ? "待窗口" : "已连接，暂无匹配"))
    : (xApi.enabled
      ? (xApiDisplayCount
        ? "成功"
        : (xApi.skipped ? "待窗口" : "已连接，暂无匹配"))
      : "未启用");
  const xMetricTone = socialdata.error || xApi.error ? "bad" : (xDisplayCount ? "ok" : (emptyAdvanced.length ? "warn" : ""));

  const metricGrid = document.createElement("div");
  metricGrid.className = "health-grid";
  metricGrid.append(
    renderMetric("内置源", `${fmtNumber(status.successful_sites || 0)}/${fmtNumber(sites.length)}`, failedSites.length ? "warn" : "ok"),
    renderMetric("RSS", rss.enabled ? `${fmtNumber(rss.ok_feeds || 0)}/${fmtNumber(rss.effective_feed_total || 0)}` : "未启用"),
    renderMetric("X数据源", xMetricValue, xMetricTone, xAuthors.length ? {
      expanded: state.xAuthorsExpanded,
      title: "查看本轮扫描到的 X 博主",
      onClick: () => {
        state.xAuthorsExpanded = !state.xAuthorsExpanded;
        renderSourceHealth();
      },
    } : {}),
    renderMetric("AgentMail", agentmail.enabled ? `${fmtNumber(agentmail.item_count || 0)}封` : "未启用", agentmail.error ? "bad" : ""),
    renderMetric("失败源", fmtNumber(failedSites.length + failedFeeds.length), failedSites.length || failedFeeds.length ? "bad" : "ok"),
    renderMetric("替换/跳过", `${fmtNumber(replacedFeeds.length)}/${fmtNumber(skippedFeeds.length)}`)
  );
  sourceHealthEl.appendChild(renderSourceHealthSummaryNode(status, errorMessage));
  const detailTarget = sourceHealthDetailsEl || sourceHealthEl;
  detailTarget.appendChild(metricGrid);
  if (state.xAuthorsExpanded && xAuthors.length) {
    detailTarget.appendChild(renderSocialdataAuthorList(xAuthors, socialdataDisplayCount));
  }

  const issues = document.createElement("div");
  issues.className = "health-issues";
  if (failedSites.length) issues.appendChild(renderIssueList("失败站点", failedSites));
  if (zeroSites.length) issues.appendChild(renderIssueList("零结果站点", zeroSites));
  if (emptyAdvanced.length) {
    issues.appendChild(renderIssueList("高级源暂无匹配", emptyAdvanced.map((item) => `${item.site_name || item.site_id} · 已连接，暂无匹配结果`)));
  }
  if (failedFeeds.length) issues.appendChild(renderIssueList("失败 RSS", failedFeeds));
  if (skippedFeeds.length) {
    issues.appendChild(renderIssueList("跳过 RSS", skippedFeeds.map((item) => `${item.feed_url} · ${item.reason || "skipped"}`)));
  }

  if (issues.childElementCount) {
    detailTarget.appendChild(issues);
  } else {
    const ok = document.createElement("div");
    ok.className = "health-ok";
    ok.textContent = "详细源状态正常";
    detailTarget.appendChild(ok);
  }
  renderSourceStatusTable(status);
  renderSourceStatusPill(errorMessage);
  renderAdvancedSummary();
  setStats();
}

async function loadNewsData() {
  const res = await fetch(`${dataUrl("data/latest-24h.json")}?t=${Date.now()}`);
  if (!res.ok) throw new Error(`加载 latest-24h.json 失败: ${res.status}`);
  return res.json();
}

async function loadAllModeData() {
  if (state.allDataLoaded) return;
  if (!state.allDataPromise) {
    state.allDataPromise = fetch(`${dataUrl(state.allDataUrl)}?t=${Date.now()}`)
      .then((res) => {
        if (!res.ok) throw new Error(`加载 latest-24h-all.json 失败: ${res.status}`);
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
  if (!res.ok) throw new Error(`加载 waytoagi-7d.json 失败: ${res.status}`);
  return res.json();
}

async function loadSourceStatusData() {
  const res = await fetch(`${dataUrl("data/source-status.json")}?t=${Date.now()}`);
  if (!res.ok) throw new Error(`加载 source-status.json 失败: ${res.status}`);
  return res.json();
}

async function loadDailyBriefData() {
  const res = await fetch(`${dataUrl("data/daily-brief.json")}?t=${Date.now()}`);
  if (!res.ok) throw new Error(`加载 daily-brief.json 失败: ${res.status}`);
  return res.json();
}

async function loadStoriesData() {
  const res = await fetch(`${dataUrl(state.storiesDataUrl)}?t=${Date.now()}`);
  if (!res.ok) throw new Error(`加载 stories-merged.json 失败: ${res.status}`);
  return res.json();
}

async function init() {
  const [newsResult, waytoagiResult, statusResult, briefResult, storiesResult] = await Promise.allSettled([
    loadNewsData(),
    loadWaytoagiData(),
    loadSourceStatusData(),
    loadDailyBriefData(),
    loadStoriesData(),
  ]);

  if (briefResult.status === "fulfilled") {
    state.dailyBrief = briefResult.value;
  } else {
    state.dailyBrief = null;
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

    setStats();
    renderSectionTabs();
    renderModeSwitch();
    renderListSortTools();
    renderCoverageStrip();
    renderSiteFilters();
    renderBolePicks();
    renderList();
    updatedAtEl.textContent = fmtTime(state.generatedAt);
  } else {
    updatedAtEl.textContent = "新闻数据加载失败";
    newsListEl.innerHTML = `<div class="empty">${newsResult.reason.message}</div>`;
    renderCoverageStrip(newsResult.reason.message);
  }

  if (statusResult.status === "fulfilled") {
    state.sourceStatus = statusResult.value;
    renderSourceHealth();
    renderCoverageStrip();
  } else {
    renderSourceHealth(statusResult.reason.message);
    renderCoverageStrip(statusResult.reason.message);
  }

  if (waytoagiResult.status === "fulfilled") {
    state.waytoagiData = waytoagiResult.value;
    renderWaytoagi(state.waytoagiData);
  } else {
    if (waytoagiWrapEl) waytoagiWrapEl.hidden = state.activeSection !== "community";
    waytoagiUpdatedAtEl.textContent = "加载失败";
    waytoagiListEl.innerHTML = `<div class="waytoagi-error">${waytoagiResult.reason.message}</div>`;
  }

  document.dispatchEvent(new CustomEvent("aiRadar:ready"));
}

searchInputEl.addEventListener("input", (e) => {
  state.query = e.target.value;
  renderBolePicks();
  renderList();
});

siteSelectEl.addEventListener("change", (e) => {
  state.siteFilter = e.target.value;
  if (state.siteFilter !== "socialdata_x") state.authorFilter = "";
  state.siteGroupsExpanded = false;
  renderSiteFilters();
  renderBolePicks();
  renderList();
});

if (sectionSelectEl) {
  sectionSelectEl.addEventListener("change", (e) => {
    state.activeSection = e.target.value || "hot";
    rerenderCurrentView();
  });
}

if (sourceTypeSelectEl) {
  sourceTypeSelectEl.addEventListener("change", (e) => {
    state.sourceTypeFilter = e.target.value;
    state.siteFilter = "";
    state.authorFilter = "";
    rerenderCurrentView();
  });
}

if (signalLevelSelectEl) {
  signalLevelSelectEl.addEventListener("change", (e) => {
    state.signalLevelFilter = e.target.value;
    rerenderCurrentView();
  });
}

modeAiBtnEl.addEventListener("click", () => {
  state.mode = "ai";
  rerenderCurrentView();
});

modeAllBtnEl.addEventListener("click", async () => {
  state.mode = "all";
  renderModeSwitch();
  newsListEl.innerHTML = "";
  const loading = document.createElement("div");
  loading.className = "empty";
  loading.textContent = "正在加载全量更新...";
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

if (allDedupeToggleEl) {
  allDedupeToggleEl.addEventListener("change", (e) => {
    state.allDedup = Boolean(e.target.checked);
    rerenderCurrentView();
  });
}

if (listSortToolsEl) {
  listSortToolsEl.addEventListener("click", (event) => {
    const target = event.target;
    const button = target instanceof Element ? target.closest("[data-sort]") : null;
    if (!button || !listSortToolsEl.contains(button)) return;
    const nextSort = button.dataset.sort;
    if (!LIST_SORT_DEFS.some((item) => item.id === nextSort) || nextSort === state.listSort) return;
    state.listSort = nextSort;
    renderListSortTools();
    renderList();
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

if (boleHotBtnEl) {
  boleHotBtnEl.addEventListener("click", () => {
    state.boleView = "hot";
    state.boleExpanded = false;
    renderBolePicks();
  });
}

if (boleTimelineBtnEl) {
  boleTimelineBtnEl.addEventListener("click", () => {
    state.boleView = "timeline";
    state.boleExpanded = false;
    renderBolePicks();
  });
}

if (dataSourceResetBtnEl) {
  dataSourceResetBtnEl.addEventListener("click", () => {
    try { localStorage.removeItem("dataBaseUrl"); } catch {}
    window.location.href = window.location.pathname;
  });
}

function renderDataSourceIndicator() {
  if (!dataSourceIndicatorEl) return;
  const base = state.dataBaseUrl;
  dataSourceIndicatorEl.hidden = !base;
  if (base && dataSourceIndicatorTextEl) {
    dataSourceIndicatorTextEl.textContent = `数据源:${base}`;
  }
}

renderDataSourceIndicator();
init();
