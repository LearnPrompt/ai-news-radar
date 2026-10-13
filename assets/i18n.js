// i18n：按 <html lang> 选择 zh / en 词典（assets/i18n/zh.js、en.js 由 scripts/build_i18n.mjs 从 JSON 生成，先于本文件加载）。
// 经典脚本，不用模块；对外只有 window.AINewsRadarI18n。
(function () {
  "use strict";

  const root = typeof window !== "undefined" ? window : globalThis;
  const doc = typeof document !== "undefined" ? document : root.document;
  const htmlLang = String((doc && doc.documentElement && doc.documentElement.lang) || "");
  const LANG = /^en/i.test(htmlLang) ? "en" : "zh";
  const LOCALE = LANG === "en" ? "en-US" : "zh-CN";
  const messages = (root.__I18N && typeof root.__I18N === "object") ? root.__I18N : {};

  const numberFormat = new Intl.NumberFormat(LOCALE);
  const pluralRules = new Intl.PluralRules(LOCALE);
  const collator = new Intl.Collator(LOCALE);

  function fmtNumber(n) {
    return numberFormat.format(n || 0);
  }

  function fmtDate(d, opts) {
    const date = d instanceof Date ? d : new Date(d);
    if (Number.isNaN(date.getTime())) return "";
    return new Intl.DateTimeFormat(LOCALE, opts).format(date);
  }

  function has(key) {
    return Object.prototype.hasOwnProperty.call(messages, key);
  }

  // {name} 占位符插值；数字参数按当前语言做千分位，字符串原样放入；缺参数保留占位符。
  function interpolate(template, params) {
    if (!params) return template;
    return template.replace(/\{(\w+)\}/g, (whole, name) => {
      if (!Object.prototype.hasOwnProperty.call(params, name)) return whole;
      const value = params[name];
      if (value === null || value === undefined) return "";
      return typeof value === "number" ? fmtNumber(value) : String(value);
    });
  }

  // 复数条目是 {one, other, ...}，按 params.n 选类别；zh 的 PluralRules 恒为 other。
  function t(key, params) {
    if (!has(key)) return key;
    let entry = messages[key];
    if (entry && typeof entry === "object") {
      const n = Number(params && params.n);
      const category = pluralRules.select(Number.isFinite(n) ? n : 0);
      entry = entry[category] !== undefined ? entry[category] : (entry.other !== undefined ? entry.other : entry.one);
      if (entry === undefined) return key;
    }
    return interpolate(String(entry), params);
  }

  // 相对时间：ms 为毫秒时间戳，缺失/非法返回“时间未知”。
  function fmtRelative(ms, now) {
    if (!ms) return t("common.unknownTime");
    const diff = (now === undefined ? Date.now() : now) - ms;
    if (diff < 0) return t("rel.justNow");
    const minutes = Math.round(diff / 60000);
    if (minutes < 60) return t("rel.minutes", { n: Math.max(1, minutes) });
    const hours = Math.round(minutes / 60);
    if (hours < 48) return t("rel.hours", { n: hours });
    return t("rel.days", { n: Math.round(hours / 24) });
  }

  root.AINewsRadarI18n = {
    LANG,
    locale: LOCALE,
    isEN: LANG === "en",
    t,
    has,
    fmtNumber,
    fmtDate,
    fmtRelative,
    collator,
  };
})();
