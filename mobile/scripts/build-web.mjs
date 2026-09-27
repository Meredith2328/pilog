#!/usr/bin/env node
// Builds mobile/www from the repo's tools/write.html (the single source of the
// write UI) plus the site's self-hosted fonts and the native bridge in web/.
// write.html is never forked: only the small, asserted patches below are
// applied, so upstream edits to write.html flow into the app on the next build.
import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const mobile = join(here, "..");
const repo = join(mobile, "..");
const out = join(mobile, "www");
const src = join(repo, "tools", "write.html");

if (!existsSync(src)) {
  console.error("tools/write.html not found — build from a branch that has the write page.");
  process.exit(1);
}
let html = readFileSync(src, "utf8");

// Structural patches must apply exactly once or the build fails.
function must(label, from, to) {
  const n = html.split(from).length - 1;
  if (n !== 1) throw new Error(`patch "${label}": expected 1 match, found ${n}`);
  html = html.replace(from, () => to);
}
// Copy tweaks are best-effort: a miss only means upstream reworded the text.
function soft(label, from, to) {
  if (html.includes(from)) html = html.replace(from, () => to);
  else console.warn(`  (skipped copy tweak "${label}")`);
}

must("csp: allow bundled scripts", "script-src 'unsafe-inline'", "script-src 'self' 'unsafe-inline'");
must("fonts: relative path + native bridge",
  '<link rel="stylesheet" href="/css/fonts.css">',
  '<link rel="stylesheet" href="css/fonts.css">\n<link rel="stylesheet" href="native.css">\n<script src="native.js"></script>');
must("defer boot until the bridge is ready",
  '<script>\n(function () {\n  "use strict";',
  '<script>\nwindow.__pilogMain = function () {\n  "use strict";');
must("close deferred boot", "})();\n</script>\n</body>", "};\n</script>\n</body>");
must("expose draft hooks to the bridge",
  "buildOf: buildFile, pathOf: pathOf",
  "buildOf: buildFile, pathOf: pathOf, markExported: markExported,\n" +
  "    open: function (id) { var d = loadDraft(id); if (d) { openDraft(d, true); dirty = true; saveNow(); hideSheet(false); setView(\"write\"); } return d; }");

soft("token storage copy", "保存在本设备（localStorage）", "保存在本设备（Android Keystore 加密）");
soft("token remember copy", "开：存 <code>localStorage</code>，直到你手动清除。", "开：用 Android Keystore 加密保存，直到你手动清除。");
soft("drafts storage copy",
  "稿件只存在这台设备的浏览器里（localStorage）。换浏览器、清除网站数据或换打开方式都会看不到，重要内容记得导出。",
  '稿件保存在 App 内，并同步为 <code id="app-mirror-dir">Documents/pilog/</code> 下的 .md 文件（私密库除外）。卸载 App 前请先导出或备份该文件夹。');
soft("download button", "下载 .md 文件</button>", "分享 / 导出 .md</button>");

rmSync(out, { recursive: true, force: true });
mkdirSync(join(out, "css"), { recursive: true });
writeFileSync(join(out, "index.html"), html);
cpSync(join(repo, "generator", "static", "css", "fonts.css"), join(out, "css", "fonts.css"));
cpSync(join(repo, "generator", "static", "fonts"), join(out, "fonts"), { recursive: true });
cpSync(join(mobile, "web"), out, { recursive: true });
console.log(`www/ built from tools/write.html (${html.length} chars)`);
