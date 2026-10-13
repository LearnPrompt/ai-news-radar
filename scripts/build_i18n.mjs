// 从 assets/i18n/{zh,en}.json 生成浏览器可直接加载的 assets/i18n/{zh,en}.js（window.__I18N = {...}）。
// 用法：node scripts/build_i18n.mjs          写文件
//       node scripts/build_i18n.mjs --check  只校验已提交的生成文件与 JSON 同步，不同步则退出码 1
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const dir = new URL("../assets/i18n/", import.meta.url);
const LANGS = ["zh", "en"];
const check = process.argv.includes("--check");
let stale = 0;

export function render(lang) {
  const data = JSON.parse(readFileSync(new URL(`${lang}.json`, dir), "utf8"));
  return `// 由 scripts/build_i18n.mjs 从 ${lang}.json 生成，勿手改。\nwindow.__I18N = ${JSON.stringify(data, null, 2)};\n`;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  for (const lang of LANGS) {
    const out = new URL(`${lang}.js`, dir);
    const next = render(lang);
    if (check) {
      let current = "";
      try { current = readFileSync(out, "utf8"); } catch { /* 缺文件视为未同步 */ }
      if (current !== next) {
        console.error(`assets/i18n/${lang}.js 与 ${lang}.json 不同步，请运行 node scripts/build_i18n.mjs`);
        stale += 1;
      }
    } else {
      writeFileSync(out, next);
    }
  }
  if (stale) process.exit(1);
}
