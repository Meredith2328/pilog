#!/usr/bin/env node
// Browser smoke test for the app bundle: serves www/ and runs it under a fake
// Capacitor runtime (in-memory Filesystem / Share / PilogSecure) to check the
// .md mirror, rename/delete, Keystore token routing, vault encryption + lock,
// move-into-vault and native export. Needs `npm run web` first and Playwright
// (`npm i -D playwright && npx playwright install chromium`).
import { createServer } from "node:http";
import { readFileSync, existsSync } from "node:fs";
import { dirname, extname, join } from "node:path";
import { fileURLToPath } from "node:url";

let chromium;
try { ({ chromium } = await import("playwright")); } catch {
  console.error("playwright is not installed: npm i -D playwright && npx playwright install chromium");
  process.exit(2);
}

const www = join(dirname(fileURLToPath(import.meta.url)), "..", "www");
const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".woff2": "font/woff2" };
const server = createServer((req, res) => {
  const p = join(www, decodeURIComponent(req.url.split("?")[0]).replace(/\/$/, "/index.html"));
  if (!p.startsWith(www) || !existsSync(p)) { res.writeHead(404); res.end(); return; }
  res.writeHead(200, { "Content-Type": types[extname(p)] || "application/octet-stream" });
  res.end(readFileSync(p));
}).listen(0);
const url = `http://127.0.0.1:${server.address().port}/`;

const fakeCapacitor = () => {
  const K = "__mock.";
  const load = (n) => JSON.parse(Storage.prototype.getItem.call(localStorage, K + n) || "{}");
  const save = (n, v) => Storage.prototype.setItem.call(localStorage, K + n, JSON.stringify(v));
  const key = (o) => (o.directory || "") + ":" + o.path;
  const fs = {
    writeFile: async (o) => { const f = load("fs"); f[key(o)] = o.data; save("fs", f); return { uri: "file://" + key(o) }; },
    readFile: async (o) => { const f = load("fs"); if (!(key(o) in f)) throw new Error("File does not exist"); return { data: f[key(o)] }; },
    deleteFile: async (o) => { const f = load("fs"); if (!(key(o) in f)) throw new Error("File does not exist"); delete f[key(o)]; save("fs", f); },
    rename: async (o) => {
      const f = load("fs"), a = o.directory + ":" + o.from, b = (o.toDirectory || o.directory) + ":" + o.to;
      f[b] = f[a]; delete f[a]; save("fs", f);
    },
    getUri: async (o) => ({ uri: "file://" + key(o) })
  };
  const sec = {
    get: async (o) => ({ value: load("sec")[o.key] || "" }),
    set: async (o) => { const s = load("sec"); s[o.key] = o.value; save("sec", s); },
    remove: async (o) => { const s = load("sec"); delete s[o.key]; save("sec", s); },
    bioStatus: async () => ({ available: false, enrolled: false }),
    setSecure: async () => {},
    setTheme: async (o) => { window.__nativeTheme = o.dark ? "dark" : "light"; },
    ready: async () => { window.__nativeReady = (window.__nativeReady || 0) + 1; }
  };
  window.__shared = [];
  window.Capacitor = {
    isNativePlatform: () => true,
    Plugins: { Filesystem: fs, PilogSecure: sec, Share: { share: async (o) => { window.__shared.push(o); } } }
  };
};

let ok = true;
const check = (name, cond, detail = "") => {
  console.log(`  [${cond ? "PASS" : "FAIL"}] ${name}${cond ? "" : " — " + detail}`);
  ok = ok && !!cond;
};

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 390, height: 800 }, hasTouch: true, isMobile: true });
const gh = { online: false, calls: [] };
await ctx.route(/api\.github\.com/, (r) => {
  const q = r.request(), u = new URL(q.url()), m = q.method(), p = u.pathname.replace("/repos/Meredith2328/pilog", "");
  if (!gh.online) return r.abort();
  gh.calls.push({ m, p, auth: q.headers().authorization, body: q.postDataJSON && q.method() !== "GET" ? q.postDataJSON() : null });
  const json = (status, body) => r.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  if (m === "GET" && p === "") return json(200, { permissions: { push: true } });
  if (m === "GET" && p === "/git/ref/heads/pilog") return json(200, { object: { sha: "base123" } });
  if (m === "GET" && (p.startsWith("/contents/") || p.startsWith("/git/ref/"))) return json(404, { message: "Not Found" });
  if (m === "POST" && p === "/git/refs") return json(201, {});
  if (m === "PUT" && p.startsWith("/contents/")) return json(201, {});
  if (m === "GET" && p === "/pulls") return json(200, []);
  if (m === "POST" && p === "/pulls") return json(201, { html_url: "https://github.com/Meredith2328/pilog/pull/99", number: 99 });
  return json(500, { message: "unexpected " + m + " " + p });
});
await ctx.addInitScript(fakeCapacitor);
const page = await ctx.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));

const fsState = () => page.evaluate(() => JSON.parse(Storage.prototype.getItem.call(localStorage, "__mock.fs") || "{}"));
const settle = () => page.waitForTimeout(900);
const shot = (name) => process.env.SHOTS ? page.screenshot({ path: join(process.env.SHOTS, name + ".png") }) : null;
const openDrafts = async () => { await page.click("#btn-drafts"); await page.waitForTimeout(250); };

console.log("notes space");
await page.goto(url);
await page.waitForSelector("#f-body");
await page.fill("#f-title", "Hello Pilog App");
await page.fill("#f-body", "## 小标题\n\n正文 **加粗**。");
await settle();
await shot("1-notes-editor");
check("splash released after first paint", await page.evaluate(() => window.__nativeReady >= 1));
let files = await fsState();
const first = "DOCUMENTS:pilog/posts/toy/hello-pilog-app.md";
check("draft mirrored to Documents/pilog/posts/<cat>/<slug>.md", first in files, Object.keys(files).join(", "));
check("mirrored file has pilog front matter", /^---\ntitle: Hello Pilog App\ndate: \d{4}-\d\d-\d\d/.test(files[first] || ""), files[first]);

await page.click('.tab[data-view="meta"]');
await page.fill("#f-slug", "renamed-note");
await settle();
files = await fsState();
check("rename moves the .md file", "DOCUMENTS:pilog/posts/toy/renamed-note.md" in files && !(first in files), Object.keys(files).join(", "));

await page.click('.tab[data-view="write"]');
await page.click(".cta");
await page.waitForTimeout(250);
await shot("2-export-sheet");
await page.click("#btn-download");
await page.waitForTimeout(400);
const shared = await page.evaluate(() => window.__shared);
check("export goes through the native share sheet", shared.length === 1 && /export\/renamed-note\.md$/.test(shared[0].files[0]), JSON.stringify(shared));
await page.click("#sheet-export [data-close]");

await openDrafts();
await page.click("#btn-new");
await page.fill("#f-title", "Second note");
await page.fill("#f-body", "to be moved into the vault");
await settle();
check("second draft mirrored", "DOCUMENTS:pilog/posts/toy/second-note.md" in (await fsState()));

await openDrafts();
await page.click('#sheet-drafts [data-open="token"]');
await page.fill("#tok-in", "github_pat_" + "x".repeat(40));
await page.check("#tok-remember");
await page.click("#btn-tok-save");
await page.waitForTimeout(400);
const sec = await page.evaluate(() => JSON.parse(Storage.prototype.getItem.call(localStorage, "__mock.sec") || "{}"));
check("token stored via PilogSecure, not in WebView localStorage",
  /^github_pat_/.test(sec["pilog.write.ghToken"] || "") && !(await page.evaluate(() => Object.keys(localStorage).includes("pilog.write.ghToken"))),
  JSON.stringify({ sec, session: await page.evaluate(() => sessionStorage.getItem("pilog.write.ghToken")), msg: await page.textContent("#tok-msg") }));
await page.click("#sheet-token [data-close]");

gh.online = true;
await openDrafts();
await page.click('#draft-list .drow:has-text("Hello Pilog App") [data-act="open"]');
await page.click(".cta");
await page.waitForTimeout(250);
await page.click("#btn-publish");
await page.waitForSelector("#pub-out .pub-box.is-ok", { timeout: 5000 }).catch(() => {});
const put = gh.calls.find((c) => c.m === "PUT");
const pr = gh.calls.find((c) => c.m === "POST" && c.p === "/pulls");
check("publish sends the Keystore token to api.github.com", gh.calls.length > 0 && gh.calls.every((c) => /^Bearer github_pat_x+$/.test(c.auth || "")));
check("publish writes blogs/posts/<cat>/<slug>.md on a write/ branch",
  put && put.p === "/contents/blogs/posts/toy/renamed-note.md" && /^write\//.test(put.body.branch), JSON.stringify(put));
check("publish opens a PR into pilog", pr && pr.body.base === "pilog" && (await page.textContent("#pub-out")).includes("#99"), JSON.stringify(pr));
gh.online = false;
await page.click("#sheet-export [data-close]");

console.log("vault space");
await openDrafts();
await shot("3-drafts-sheet");
await page.click("#app-vault");
await page.waitForSelector(".vgate");
check("editor stays hidden behind the vault gate", await page.$eval("#app", (a) => getComputedStyle(a).visibility === "hidden"));
await shot("4-vault-create");
await page.fill("#vg-pw", "correct horse");
await page.fill("#vg-pw2", "correct horse");
await page.click("#vg-go");
await page.waitForSelector(".vgate", { state: "detached" });
check("vault opens with its own empty draft list", (await page.inputValue("#f-body")) === "");
await page.fill("#f-title", "Secret diary");
await page.fill("#f-body", "SECRET-PLAINTEXT-42");
await settle();
await shot("5-vault-editor");
files = await fsState();
const blob = files["DATA:vault/vault.json"] || "";
check("vault persisted as an encrypted blob", blob.length > 0 && !blob.includes("SECRET-PLAINTEXT-42") && !blob.includes("Secret diary"));
check("vault note never reaches WebView storage or Documents",
  !(await page.evaluate(() => Object.keys(localStorage).some((k) => (localStorage[k] || "").includes("SECRET-PLAINTEXT-42")))) &&
  !Object.keys(files).some((k) => k.startsWith("DOCUMENTS:") && files[k].includes("SECRET")));
check("no password material stored", !blob.includes("correct horse"));

await openDrafts();
await page.click("#app-move");
await page.click('#app-move-list .drow:has-text("Second note") [data-move]');
await settle();
files = await fsState();
check("move into vault deletes the plain .md", !("DOCUMENTS:pilog/posts/toy/second-note.md" in files), Object.keys(files).join(", "));
check("moved note is open in the vault", (await page.inputValue("#f-body")) === "to be moved into the vault");

await page.click("#app-lock");
await page.waitForSelector(".vgate");
await page.fill("#vg-pw", "wrong password");
await page.click("#vg-go");
await page.waitForTimeout(1500);
check("wrong password is rejected", (await page.textContent("#vg-msg")).includes("不对"));
await page.fill("#vg-pw", "correct horse");
await page.click("#vg-go");
await page.waitForSelector(".vgate", { state: "detached" });
await openDrafts();
const titles = await page.$$eval("#draft-list .drow-t", (n) => n.map((x) => x.textContent));
check("unlock restores both vault notes", titles.includes("Secret diary") && titles.includes("Second note"), titles.join(" | "));

await page.click("#app-leave");
await page.waitForSelector("#f-body");
await openDrafts();
const plain = await page.$$eval("#draft-list .drow-t", (n) => n.map((x) => x.textContent));
check("notes space shows only the non-vault note", plain.length === 1 && plain[0] === "Hello Pilog App", plain.join(" | "));
const del = page.locator('#draft-list .drow:has-text("Hello Pilog App") [data-act="del"]');
await del.click(); await del.click();
await settle();
check("deleting a draft deletes its .md", !("DOCUMENTS:pilog/posts/toy/renamed-note.md" in (await fsState())));
await page.click("#btn-theme");
await page.waitForTimeout(200);
check("system bars follow the in-app theme toggle", (await page.evaluate(() => window.__nativeTheme)) === "dark");
await page.click("#sheet-drafts [data-close]");
await page.waitForTimeout(300);
await shot("6-dark-editor");
check("piwiki target is present but disabled", await page.$eval("#app-piwiki", (b) => b.disabled));
check("no page errors", errors.length === 0, errors.join("\n"));

await browser.close();
server.close();
console.log(ok ? "ALL PASS" : "FAILURES");
process.exit(ok ? 0 : 1);
