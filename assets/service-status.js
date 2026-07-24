(() => {
  const panel = document.getElementById("serviceStatusPanel");
  if (!panel) return;

  const STATUS_LABELS = {
    investigating: "调查中",
    identified: "已定位",
    monitoring: "恢复监控中",
  };

  function resolveDataBaseUrl() {
    try {
      const fromQuery = new URLSearchParams(window.location.search).get("data") || "";
      if (fromQuery) return fromQuery.trim().replace(/\/+$/, "");
      return (localStorage.getItem("dataBaseUrl") || "").trim().replace(/\/+$/, "");
    } catch {
      return "";
    }
  }

  function dataUrl(path) {
    const base = resolveDataBaseUrl();
    if (!base) return path;
    return `${base}/${String(path || "").split("/").pop()}`;
  }

  function formatTime(value) {
    const date = new Date(value || "");
    if (Number.isNaN(date.getTime())) return "";
    return new Intl.DateTimeFormat("zh-CN", {
      month: "numeric",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(date);
  }

  function providerLabel(incident) {
    const components = Array.isArray(incident?.affected_components)
      ? incident.affected_components
      : [];
    const signal = [incident?.title, incident?.title_zh, ...components]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    if (signal.includes("chatgpt")) return "ChatGPT";
    if (incident?.title === "Elevated Error Rates") return "ChatGPT / OpenAI";
    return incident?.provider || "OpenAI";
  }

  function incidentTitle(incident) {
    if (incident?.title === "Elevated Error Rates") {
      return "ChatGPT 等 OpenAI 服务错误率升高";
    }
    return incident?.title_zh || incident?.title || "服务异常";
  }

  function incidentNode(incident) {
    const row = document.createElement("article");
    row.className = `service-incident impact-${incident.impact || "none"}`;

    const main = document.createElement("div");
    main.className = "service-incident-main";

    const meta = document.createElement("div");
    meta.className = "service-incident-meta";

    const provider = document.createElement("span");
    provider.className = "service-provider";
    provider.textContent = providerLabel(incident);

    const phase = document.createElement("span");
    phase.className = "service-phase";
    phase.textContent = STATUS_LABELS[incident.status] || incident.status || "处理中";
    meta.append(provider, phase);

    const title = document.createElement("a");
    title.className = "service-incident-title";
    title.href = incident.url || "https://status.openai.com/";
    title.target = "_blank";
    title.rel = "noopener noreferrer";
    title.textContent = incidentTitle(incident);

    main.append(meta, title);

    const time = document.createElement("time");
    time.className = "service-incident-time";
    time.dateTime = incident.updated_at || "";
    time.textContent = formatTime(incident.updated_at);

    row.append(main, time);
    return row;
  }

  function render(payload) {
    const incidents = Array.isArray(payload?.incidents)
      ? payload.incidents.filter((incident) => incident && incident.status !== "resolved")
      : [];
    panel.replaceChildren();
    if (payload?.ok !== true || incidents.length === 0) {
      panel.hidden = true;
      return;
    }

    const heading = document.createElement("div");
    heading.className = "service-status-heading";

    const titleWrap = document.createElement("div");
    titleWrap.className = "service-status-title-wrap";
    const dot = document.createElement("span");
    dot.className = "service-status-dot";
    dot.setAttribute("aria-hidden", "true");
    const title = document.createElement("strong");
    title.textContent = "ChatGPT / OpenAI 服务状态";
    titleWrap.append(dot, title);

    const count = document.createElement("span");
    count.className = "service-status-count";
    count.textContent = `${incidents.length} 项官方故障`;
    heading.append(titleWrap, count);

    const list = document.createElement("div");
    list.className = "service-incident-list";
    incidents.slice(0, 3).forEach((incident) => list.appendChild(incidentNode(incident)));

    panel.append(heading, list);
    panel.classList.toggle(
      "has-major",
      incidents.some((incident) => ["major", "critical"].includes(incident.impact)),
    );
    panel.hidden = false;
    panel.setAttribute(
      "aria-label",
      `ChatGPT 与 OpenAI 服务状态：${incidents.length} 项故障正在处理`,
    );
  }

  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 8000);

  fetch(dataUrl("data/service-status.json"), {
    cache: "no-cache",
    headers: { Accept: "application/json" },
    signal: controller.signal,
  })
    .then((response) => {
      if (!response.ok) throw new Error(`service status ${response.status}`);
      return response.json();
    })
    .then(render)
    .catch(() => {
      panel.hidden = true;
    })
    .finally(() => {
      window.clearTimeout(timeout);
    });
})();
