const state = {
  itemsAi: [],
  itemsAll: [],
  itemsAllRaw: [],
  statsAi: [],
  totalAi: 0,
  totalRaw: 0,
  totalAllMode: 0,
  allDedup: true,
  siteFilter: "",
  query: "",
  mode: "ai",
  waytoagiMode: "today",
  waytoagiData: null,
  generatedAt: null,
  sourcesStatus: null,
  sourcesStatusExpanded: true,
  sourcesFilter: "all", // all, enabled, disabled, error
};

const statsEl = document.getElementById("stats");
const siteSelectEl = document.getElementById("siteSelect");
const sitePillsEl = document.getElementById("sitePills");
const newsListEl = document.getElementById("newsList");
const updatedAtEl = document.getElementById("updatedAt");
const searchInputEl = document.getElementById("searchInput");
const resultCountEl = document.getElementById("resultCount");
const itemTpl = document.getElementById("itemTpl");
const modeAiBtnEl = document.getElementById("modeAiBtn");
const modeAllBtnEl = document.getElementById("modeAllBtn");
const modeHintEl = document.getElementById("modeHint");
const allDedupeWrapEl = document.getElementById("allDedupeWrap");
const allDedupeToggleEl = document.getElementById("allDedupeToggle");
const allDedupeLabelEl = document.getElementById("allDedupeLabel");

const sourcesStatusWrapEl = document.getElementById("sourcesStatusWrap");
const sourcesToggleBtnEl = document.getElementById("sourcesToggleBtn");
const sourcesStatsEl = document.getElementById("sourcesStats");
const sourcesListEl = document.getElementById("sourcesList");
const sourceStatusTpl = document.getElementById("sourceStatusTpl");

const waytoagiUpdatedAtEl = document.getElementById("waytoagiUpdatedAt");
const waytoagiMetaEl = document.getElementById("waytoagiMeta");
const waytoagiListEl = document.getElementById("waytoagiList");
const waytoagiTodayBtnEl = document.getElementById("waytoagiTodayBtn");
const waytoagi7dBtnEl = document.getElementById("waytoagi7dBtn");

function fmtNumber(n) {
  return new Intl.NumberFormat("zh-CN").format(n || 0);
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

function fmtDuration(ms) {
  if (!ms) return "0ms";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function setStats(payload) {
  const cards = [
    ["24h AI", fmtNumber(payload.total_items)],
    ["24h 全量", fmtNumber(payload.total_items_raw || payload.total_items)],
    ["全量去重后", fmtNumber(payload.total_items_all_mode || payload.total_items_raw || payload.total_items)],
    ["站点数", fmtNumber(payload.site_count)],
    ["来源分组", fmtNumber(payload.source_count)],
    ["归档总量", fmtNumber(payload.archive_total || 0)]
  ];

  statsEl.innerHTML = "";
  cards.forEach(([k, v]) => {
    const node = document.createElement("div");
    node.className = "stat";
    node.innerHTML = `<div class="k">${k}</div><div class="v">${v}</div>`;
    statsEl.appendChild(node);
  });
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

function currentSiteStats() {
  if (state.mode === "ai") return state.statsAi || [];
  return computeSiteStats(state.allDedup ? (state.itemsAll || []) : (state.itemsAllRaw || []));
}

function renderSiteFilters() {
  const stats = currentSiteStats();

  siteSelectEl.innerHTML = '<option value="">全部站点</option>';
  stats.forEach((s) => {
    const opt = document.createElement("option");
    opt.value = s.site_id;
    const raw = s.raw_count ?? s.count;
    opt.textContent = `${s.site_name} (${s.count}/${raw})`;
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
    renderList();
  };
  sitePillsEl.appendChild(allPill);

  stats.forEach((s) => {
    const btn = document.createElement("button");
    btn.className = `pill ${state.siteFilter === s.site_id ? "active" : ""}`;
    const raw = s.raw_count ?? s.count;
    btn.textContent = `${s.site_name} ${s.count}/${raw}`;
    btn.onclick = () => {
      state.siteFilter = s.site_id;
      renderSiteFilters();
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
    modeHintEl.textContent = `当前视图：AI强相关（${fmtNumber(state.totalAi)} 条）`;
  } else {
    const allCount = state.allDedup
      ? (state.totalAllMode || state.itemsAll.length)
      : (state.totalRaw || state.itemsAllRaw.length);
    modeHintEl.textContent = `当前视图：全量（${state.allDedup ? "去重开" : "去重关"}，${fmtNumber(allCount)} 条）`;
  }
}

function effectiveAllItems() {
  return state.allDedup ? state.itemsAll : state.itemsAllRaw;
}

function modeItems() {
  return state.mode === "all" ? effectiveAllItems() : state.itemsAi;
}

function getFilteredItems() {
  const q = state.query.trim().toLowerCase();
  return modeItems().filter((item) => {
    if (state.siteFilter && item.site_id !== state.siteFilter) return false;
    if (!q) return true;
    const hay = `${item.title || ""} ${item.title_zh || ""} ${item.title_en || ""} ${item.site_name || ""} ${item.source || ""}`.toLowerCase();
    return hay.includes(q);
  });
}

function renderItemNode(item) {
  const node = itemTpl.content.firstElementChild.cloneNode(true);
  node.querySelector(".site").textContent = item.site_name;
  node.querySelector(".source").textContent = `分区: ${item.source}`;
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
  return node;
}

function buildSourceGroupNode(source, items) {
  const section = document.createElement("section");
  section.className = "source-group";
  section.innerHTML = `
    <header class="source-group-head">
      <h3>${source}</h3>
      <span>${fmtNumber(items.length)} 条</span>
    </header>
    <div class="source-group-list"></div>
  `;
  const listEl = section.querySelector(".source-group-list");
  items.forEach((item) => listEl.appendChild(renderItemNode(item)));
  return section;
}

function groupBySource(items) {
  const groupMap = new Map();
  items.forEach((item) => {
    const key = item.source || "未分区";
    if (!groupMap.has(key)) {
      groupMap.set(key, []);
    }
    groupMap.get(key).push(item);
  });

  return Array.from(groupMap.entries()).sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0], "zh-CN"));
}

function renderGroupedBySource(items) {
  const groups = groupBySource(items);
  const frag = document.createDocumentFragment();

  groups.forEach(([source, groupItems]) => {
    frag.appendChild(buildSourceGroupNode(source, groupItems));
  });

  newsListEl.appendChild(frag);
}

function renderGroupedBySiteAndSource(items) {
  const siteMap = new Map();
  items.forEach((item) => {
    if (!siteMap.has(item.site_id)) {
      siteMap.set(item.site_id, {
        siteName: item.site_name || item.site_id,
        items: [],
      });
    }
    siteMap.get(item.site_id).items.push(item);
  });

  const sites = Array.from(siteMap.entries()).sort((a, b) => {
    const byCount = b[1].items.length - a[1].items.length;
    if (byCount !== 0) return byCount;
    return a[1].siteName.localeCompare(b[1].siteName, "zh-CN");
  });

  const frag = document.createDocumentFragment();
  sites.forEach(([, site]) => {
    const siteSection = document.createElement("section");
    siteSection.className = "site-group";
    siteSection.innerHTML = `
      <header class="site-group-head">
        <h3>${site.siteName}</h3>
        <span>${fmtNumber(site.items.length)} 条</span>
      </header>
      <div class="site-group-list"></div>
    `;

    const siteListEl = siteSection.querySelector(".site-group-list");
    const sourceGroups = groupBySource(site.items);
    sourceGroups.forEach(([source, groupItems]) => {
      siteListEl.appendChild(buildSourceGroupNode(source, groupItems));
    });
    frag.appendChild(siteSection);
  });

  newsListEl.appendChild(frag);
}

function renderList() {
  const filtered = getFilteredItems();
  resultCountEl.textContent = `${fmtNumber(filtered.length)} 条`;

  newsListEl.innerHTML = "";

  if (!filtered.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "当前筛选条件下没有结果。";
    newsListEl.appendChild(empty);
    return;
  }

  if (state.siteFilter) {
    renderGroupedBySource(filtered);
    return;
  }

  renderGroupedBySiteAndSource(filtered);
}

// ============================================================================
// Sources Status
// ============================================================================

async function loadSourcesStatus() {
  try {
    const res = await fetch(`./data/sources-status.json?t=${Date.now()}`);
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

function renderSourcesStats(status) {
  if (!status) {
    sourcesStatsEl.innerHTML = '<div class="sources-stats-empty">加载中...</div>';
    return;
  }

  const total = status.total_sources || status.sources?.length || 0;
  const enabled = status.enabled_sources || status.sources?.filter(s => s.enabled).length || 0;
  const disabled = status.disabled_sources || status.sources?.filter(s => !s.enabled).length || 0;
  const success = status.sources?.filter(s => s.status === "success").length || 0;
  const error = status.sources?.filter(s => s.status === "error").length || 0;
  const totalItems = status.sources?.reduce((sum, s) => sum + (s.item_count || 0), 0) || 0;

  sourcesStatsEl.innerHTML = `
    <div class="sources-stat-item">
      <span class="sources-stat-label">总源数</span>
      <span class="sources-stat-value">${total}</span>
    </div>
    <div class="sources-stat-item">
      <span class="sources-stat-label">已启用</span>
      <span class="sources-stat-value success">${enabled}</span>
    </div>
    <div class="sources-stat-item">
      <span class="sources-stat-label">正常</span>
      <span class="sources-stat-value success">${success}</span>
    </div>
    <div class="sources-stat-item">
      <span class="sources-stat-label">异常</span>
      <span class="sources-stat-value ${error > 0 ? 'error' : ''}">${error}</span>
    </div>
    <div class="sources-stat-item">
      <span class="sources-stat-label">总条目</span>
      <span class="sources-stat-value">${fmtNumber(totalItems)}</span>
    </div>
  `;
}

function renderSourceStatusItem(source) {
  const node = sourceStatusTpl.content.firstElementChild.cloneNode(true);

  // Status indicator
  const indicator = node.querySelector(".source-status-indicator");
  indicator.className = `source-status-indicator status-${source.status}`;

  // Name and category
  node.querySelector(".source-status-name").textContent = source.name;
  const categoryEl = node.querySelector(".source-status-category");
  categoryEl.textContent = source.category || "general";

  // Auth badge
  if (source.auth_required) {
    const authEl = node.querySelector(".source-status-auth");
    authEl.style.display = "";
    if (source.status === "disabled" && source.missing_creds?.length) {
      authEl.title = `需要授权，缺少: ${source.missing_creds.join(", ")}`;
      authEl.className = "source-status-auth warning";
    } else {
      authEl.title = "需要授权";
    }
  }

  // Stats
  node.querySelector(".source-stat[data-stat='items']").textContent = `${fmtNumber(source.item_count)} 条`;
  node.querySelector(".source-stat[data-stat='time']").textContent = fmtDuration(source.fetch_time_ms);

  // Tags
  const metaEl = node.querySelector(".source-status-meta");
  if (source.tags?.length) {
    metaEl.innerHTML = source.tags.slice(0, 3).map(t => `<span class="source-tag">${t}</span>`).join("");
  }

  // Error message
  if (source.status === "error" && source.error) {
    const errorEl = node.querySelector(".source-status-error");
    errorEl.style.display = "";
    errorEl.textContent = source.error;
  } else if (source.status === "disabled" && !source.enabled) {
    const errorEl = node.querySelector(".source-status-error");
    errorEl.style.display = "";
    errorEl.className = "source-status-error info";
    errorEl.textContent = "已禁用";
  }

  // URL
  const urlEl = node.querySelector(".source-status-url");
  urlEl.href = source.url;
  urlEl.textContent = source.url.replace(/^https?:\/\//, "").replace(/\/$/, "");

  // Updated time
  const updatedEl = node.querySelector(".source-status-updated");
  if (source.last_fetch) {
    updatedEl.textContent = fmtTime(source.last_fetch);
  } else {
    updatedEl.textContent = "未获取";
  }

  return node;
}

function renderSourcesList(status, filter = "all") {
  if (!status || !status.sources) {
    sourcesListEl.innerHTML = '<div class="sources-list-empty">加载中...</div>';
    return;
  }

  let sources = [...status.sources];

  // Apply filter
  if (filter === "enabled") {
    sources = sources.filter(s => s.enabled);
  } else if (filter === "disabled") {
    sources = sources.filter(s => !s.enabled);
  } else if (filter === "error") {
    sources = sources.filter(s => s.status === "error");
  }

  // Sort: enabled first, then by status, then by name
  sources.sort((a, b) => {
    if (a.enabled !== b.enabled) return b.enabled - a.enabled;
    const statusOrder = { success: 0, partial: 1, error: 2, disabled: 3 };
    const sa = statusOrder[a.status] ?? 4;
    const sb = statusOrder[b.status] ?? 4;
    if (sa !== sb) return sa - sb;
    return a.name.localeCompare(b.name, "zh-CN");
  });

  sourcesListEl.innerHTML = "";
  const frag = document.createDocumentFragment();

  sources.forEach(source => {
    frag.appendChild(renderSourceStatusItem(source));
  });

  sourcesListEl.appendChild(frag);

  if (sources.length === 0) {
    sourcesListEl.innerHTML = '<div class="sources-list-empty">没有匹配的信息源</div>';
  }
}

function renderSourcesStatus(status) {
  state.sourcesStatus = status;
  renderSourcesStats(status);
  renderSourcesList(status, state.sourcesFilter);

  // Update toggle button icon
  if (sourcesToggleBtnEl) {
    sourcesToggleBtnEl.querySelector(".icon").textContent = state.sourcesStatusExpanded ? "▾" : "▴";
  }

  // Show/hide content
  if (sourcesStatusWrapEl) {
    const content = sourcesStatusWrapEl.querySelector(".sources-status-content");
    if (content) {
      content.style.display = state.sourcesStatusExpanded ? "block" : "none";
    }
  }
}

function toggleSourcesStatus() {
  state.sourcesStatusExpanded = !state.sourcesStatusExpanded;
  if (state.sourcesStatus) {
    renderSourcesStatus(state.sourcesStatus);
  }
}

function setSourcesFilter(filter) {
  state.sourcesFilter = filter;
  if (state.sourcesStatus) {
    renderSourcesList(state.sourcesStatus, filter);
  }
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
  const { updates7d, updatesToday, latestDate } = waytoagiViews(waytoagi);
  if (waytoagiTodayBtnEl) waytoagiTodayBtnEl.classList.toggle("active", state.waytoagiMode === "today");
  if (waytoagi7dBtnEl) waytoagi7dBtnEl.classList.toggle("active", state.waytoagiMode === "7d");
  waytoagiUpdatedAtEl.textContent = `更新时间：${fmtTime(waytoagi.generated_at)}`;

  waytoagiMetaEl.innerHTML = `
    <a href="${waytoagi.root_url || "#"}" target="_blank" rel="noopener noreferrer">主页面</a>
    <span>·</span>
    <a href="${waytoagi.history_url || "#"}" target="_blank" rel="noopener noreferrer">历史更新页</a>
    <span>·</span>
    <span>当天(${latestDate || "--"})：${fmtNumber(waytoagi.count_today || updatesToday.length)} 条</span>
    <span>·</span>
    <span>近 7 日：${fmtNumber(waytoagi.count_7d || updates7d.length)} 条</span>
  `;

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
      ? "当天没有更新，可切换到近7日查看。"
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
    row.innerHTML = `<span class="d">${fmtDate(u.date)}</span><span class="t">${u.title}</span>`;
    waytoagiListEl.appendChild(row);
  });
}

async function loadNewsData() {
  const res = await fetch(`./data/latest-24h.json?t=${Date.now()}`);
  if (!res.ok) throw new Error(`加载 latest-24h.json 失败: ${res.status}`);
  return res.json();
}

async function loadWaytoagiData() {
  const res = await fetch(`./data/waytoagi-7d.json?t=${Date.now()}`);
  if (!res.ok) throw new Error(`加载 waytoagi-7d.json 失败: ${res.status}`);
  return res.json();
}

async function init() {
  const [newsResult, waytoagiResult, sourcesStatusResult] = await Promise.allSettled([
    loadNewsData(),
    loadWaytoagiData(),
    loadSourcesStatus(),
  ]);

  if (newsResult.status === "fulfilled") {
    const payload = newsResult.value;
    state.itemsAi = payload.items_ai || payload.items || [];
    state.itemsAllRaw = payload.items_all_raw || payload.items_all || payload.items || [];
    state.itemsAll = payload.items_all || payload.items || [];
    state.statsAi = payload.site_stats || [];
    state.totalAi = payload.total_items || state.itemsAi.length;
    state.totalRaw = payload.total_items_raw || state.itemsAllRaw.length;
    state.totalAllMode = payload.total_items_all_mode || state.itemsAll.length;
    state.generatedAt = payload.generated_at;

    setStats(payload);
    renderModeSwitch();
    renderSiteFilters();
    renderList();
    updatedAtEl.textContent = `更新时间：${fmtTime(state.generatedAt)}`;
  } else {
    updatedAtEl.textContent = "新闻数据加载失败";
    newsListEl.innerHTML = `<div class="empty">${newsResult.reason.message}</div>`;
  }

  if (waytoagiResult.status === "fulfilled") {
    state.waytoagiData = waytoagiResult.value;
    renderWaytoagi(state.waytoagiData);
  } else {
    waytoagiUpdatedAtEl.textContent = "加载失败";
    waytoagiListEl.innerHTML = `<div class="waytoagi-error">${waytoagiResult.reason.message}</div>`;
  }

  if (sourcesStatusResult.status === "fulfilled") {
    renderSourcesStatus(sourcesStatusResult.value);
  } else {
    renderSourcesStatus(null);
  }
}

searchInputEl.addEventListener("input", (e) => {
  state.query = e.target.value;
  renderList();
});

siteSelectEl.addEventListener("change", (e) => {
  state.siteFilter = e.target.value;
  renderSiteFilters();
  renderList();
});

modeAiBtnEl.addEventListener("click", () => {
  state.mode = "ai";
  renderModeSwitch();
  renderSiteFilters();
  renderList();
});

modeAllBtnEl.addEventListener("click", () => {
  state.mode = "all";
  renderModeSwitch();
  renderSiteFilters();
  renderList();
});

if (allDedupeToggleEl) {
  allDedupeToggleEl.addEventListener("change", (e) => {
    state.allDedup = Boolean(e.target.checked);
    renderModeSwitch();
    renderSiteFilters();
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

// Sources status toggle
if (sourcesToggleBtnEl) {
  sourcesToggleBtnEl.addEventListener("click", toggleSourcesStatus);
}

init();
