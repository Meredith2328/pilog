#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression checks for the mobile writer (tools/write.html served at /write):
autosave/restore, preview rendering, drafts, and that exported front matter is
read back correctly by pilog's own parser."""

from __future__ import annotations

import base64
import json
import pathlib
import shutil
import sys
import threading

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TMP = ROOT / ".write_tmp"
WRITE = ROOT / "tools" / "write.html"

from util import block_external  # noqa: E402

import serve  # noqa: E402
from generator.content import split_front_matter  # noqa: E402

PORT = 8197
srv = serve.ThreadingHTTPServer(("127.0.0.1", PORT), serve.Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()

from playwright.sync_api import sync_playwright  # noqa: E402

ok = True


def check(name, cond, detail=""):
    global ok
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + ("" if cond else f" — {detail}"))
    ok = ok and cond


BODY = """## 小标题

一段 **加粗**、`code` 与 [链接](https://example.com)，还有 [[pilog-blog|站内]]。
- 列表一
  - 两空格（pilog 不嵌套）
- 列表二
    - 四空格嵌套
- [x] 完成

> [!tip] 提示标题
> 提示内容

```python
print("hi")
```

| a | b |
| --- | --- |
| 1 | 2 |

![封面](assets/cover-pixel.png)
"""

TRICKY = ["标题: 带冒号", "#井号开头", "true", "2026-01-01", '引号 "内" 容', "- 横线开头", "普通标题"]

FAKE_TOKEN = "github_pat_FAKE0000TEST0000ONLY0000xyzw"
REPO = "/repos/Meredith2328/pilog"

# In-page stand-in for api.github.com: replaces window.fetch before the page
# script runs, keeps branches/files/PRs in memory and records every call.
GH_MOCK = r"""
(() => {
  const real = window.fetch.bind(window);
  const S = window.__gh = { calls: [], fail: [], offline: false, n: 0, pulls: [],
    repo: { full_name: "Meredith2328/pilog", permissions: { admin: true, push: true, pull: true } },
    refs: { pilog: "base000" }, files: {} };
  const out = (status, body) => Promise.resolve(new Response(body == null ? "" : JSON.stringify(body),
    { status, headers: { "Content-Type": "application/json" } }));
  window.fetch = function (url, init) {
    url = String(url);
    if (!url.startsWith("https://api.github.com/")) return real(url, init);
    init = init || {};
    const u = new URL(url), method = (init.method || "GET").toUpperCase();
    const body = init.body ? JSON.parse(init.body) : null;
    S.calls.push({ method, path: decodeURIComponent(u.pathname), query: Object.fromEntries(u.searchParams),
      auth: (init.headers || {}).Authorization || "", credentials: init.credentials, body });
    if (S.offline) return Promise.reject(new TypeError("Failed to fetch"));
    const sig = method + " " + decodeURIComponent(u.pathname);
    const f = S.fail.find(x => sig.startsWith(x.sig));
    if (f) return out(f.status, { message: f.message });
    const pre = "/repos/Meredith2328/pilog";
    if (!u.pathname.startsWith(pre)) return out(404, { message: "Not Found" });
    const p = decodeURIComponent(u.pathname.slice(pre.length));
    if (p === "" && method === "GET") return out(200, S.repo);
    if (p.startsWith("/git/ref/heads/") && method === "GET") {
      const b = p.slice(15);
      return b in S.refs ? out(200, { ref: "refs/heads/" + b, object: { sha: S.refs[b] } }) : out(404, { message: "Not Found" });
    }
    if (p === "/git/refs" && method === "POST") {
      const b = body.ref.replace("refs/heads/", "");
      if (b in S.refs) return out(422, { message: "Reference already exists" });
      S.refs[b] = body.sha;
      for (const k of Object.keys(S.files)) if (k.startsWith("pilog|")) S.files[b + k.slice(5)] = S.files[k];
      return out(201, { ref: body.ref, object: { sha: body.sha } });
    }
    if (p.startsWith("/contents/")) {
      const path = p.slice(10), ref = u.searchParams.get("ref") || (body && body.branch), k = ref + "|" + path, ex = S.files[k];
      if (method === "GET") return ex ? out(200, { type: "file", path, sha: ex.sha, content: ex.content.replace(/(.{60})/g, "$1\n") })
        : out(404, { message: "Not Found" });
      if (method === "PUT") {
        if (!(body.branch in S.refs)) return out(404, { message: "Branch not found" });
        if (ex && !body.sha) return out(422, { message: "\"sha\" wasn't supplied." });
        if (ex && body.sha !== ex.sha) return out(409, { message: "does not match" });
        const sha = "blob" + (++S.n);
        S.files[k] = { content: body.content, sha };
        return out(ex ? 200 : 201, { content: { path, sha } });
      }
    }
    if (p === "/pulls" && method === "GET") {
      const q = u.searchParams;
      return out(200, S.pulls.filter(x => x.state === "open" && q.get("head") === "Meredith2328:" + x.head && q.get("base") === x.base));
    }
    if (p === "/pulls" && method === "POST") {
      const pr = { number: 10 + S.pulls.length, state: "open", head: body.head, base: body.base, title: body.title, body: body.body };
      pr.html_url = "https://github.com/Meredith2328/pilog/pull/" + pr.number;
      S.pulls.push(pr);
      return out(201, pr);
    }
    return out(404, { message: "Not Found (mock)" });
  };
})();
"""


def gh(pg, expr="S"):
    return pg.evaluate(f"(() => {{ const S = window.__gh; return {expr}; }})()")


def publish_checks(b) -> None:
    ctx = b.new_context(viewport={"width": 412, "height": 860}, is_mobile=True, has_touch=True)
    ctx.add_init_script(GH_MOCK)
    pg = ctx.new_page()
    block_external(pg)
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{PORT}/tools/write.html", wait_until="domcontentloaded")
    pg.wait_for_function("!!window.__pilogWrite")

    pg.fill("#f-title", "手机开 PR")
    pg.fill("#f-body", "## 你好\n\n从手机发布的一篇测试文章，正文足够长。\n")
    pg.click(".tab[data-view=meta]")
    pg.fill("#f-slug", "phone-pr-demo")
    pg.fill("#tag-in", "工具，手机")
    pg.click(".tab[data-view=write]")
    pg.wait_for_timeout(500)

    # ---- locked without a token ----
    pg.click(".cta")
    locked = pg.evaluate("""() => ({ dis: document.querySelector('#btn-publish').disabled,
        badge: document.querySelector('#pub-badge').textContent, lock: !document.querySelector('#pub-lock').hidden,
        row: document.querySelector('#tok-row-t').textContent })""")
    check("publish: locked without token", locked["dis"] and locked["badge"] == "LOCKED" and locked["lock"]
          and "未设置" in locked["row"], repr(locked))
    r = pg.evaluate("window.__pilogWrite.publish()")
    check("publish: no token → no GitHub request", r["reason"] == "locked" and gh(pg, "S.calls.length") == 0, repr(r))

    # ---- assembly / validation ----
    plan = pg.evaluate("window.__pilogWrite.plan()")
    date = pg.evaluate("window.__pilogWrite.current().date")
    fm, body = split_front_matter(plan["file"])
    check("plan: path / branch / file",
          plan["path"] == "blogs/posts/toy/phone-pr-demo.md" and plan["branch"] == f"write/{date}-phone-pr-demo"
          and plan["file"] == pg.evaluate("window.__pilogWrite.build()") and fm.get("title") == "手机开 PR"
          and fm.get("tags") == ["工具", "手机"] and body.lstrip().startswith("## 你好") and not plan["errors"], repr(plan)[:400])
    check("plan: Chinese PR title/body", plan["prTitle"] == "新文章：手机开 PR" and "`blogs/posts/toy/phone-pr-demo.md`" in plan["prBody"]
          and "手动合并" in plan["prBody"], plan["prTitle"])
    bad = pg.evaluate("""() => { const w = window.__pilogWrite, d = w.current(), keep = Object.assign({}, d), out = {};
        d.category = "../../.github/workflows"; out.dots = w.plan().errors.length;
        Object.assign(d, keep); d.body = "  "; out.empty = w.plan().errors.length;
        Object.assign(d, keep); d.extra = "x: 1\\n---"; out.fence = w.plan().errors.length;
        Object.assign(d, keep); d.title = "中文标题 带空格"; d.slug = "中文"; out.branch = w.plan().branch;
        Object.assign(d, keep); return out; }""")
    check("plan: rejects unsafe path / empty body / stray ---",
          bad["dots"] > 0 and bad["empty"] > 0 and bad["fence"] > 0, repr(bad))
    check("plan: branch name stays ASCII", bad["branch"].startswith(f"write/{date}-post-") and bad["branch"].isascii(), bad["branch"])
    r = pg.evaluate("""() => { const d = window.__pilogWrite.current(), keep = d.body; d.body = "";
        return window.__pilogWrite.publish().then(x => { d.body = keep; return x; }); }""")
    check("publish: invalid draft stops before any request", r["reason"] == "invalid" and gh(pg, "S.calls.length") == 0, repr(r))

    # ---- token settings (session only by default) ----
    pg.click("#tok-row [data-open=token]")
    pg.fill("#tok-in", FAKE_TOKEN)
    pg.click("#btn-tok-save")
    pg.wait_for_selector("#tok-msg .note.ok")
    st = pg.evaluate("""() => ({ s: sessionStorage.getItem('pilog.write.ghToken'), l: localStorage.getItem('pilog.write.ghToken'),
        shown: document.querySelector('#sheet-token').innerText, input: document.querySelector('#tok-in').value })""")
    check("token: saved to sessionStorage only, masked in UI",
          st["s"] == FAKE_TOKEN and st["l"] is None and FAKE_TOKEN not in st["shown"] and "github_pat_…xyzw" in st["shown"]
          and st["input"] == "", repr({k: v for k, v in st.items() if k != "shown"}))
    first = gh(pg, "S.calls[0]")
    check("token: verified with one GET to the repo", first["method"] == "GET" and first["path"] == REPO
          and first["auth"] == "Bearer " + FAKE_TOKEN and first["credentials"] == "omit", repr(first))
    pg.check("#tok-remember", force=True)
    pg.click("#btn-tok-save")
    pg.wait_for_selector("#tok-msg .note.ok")
    st = pg.evaluate("[sessionStorage.getItem('pilog.write.ghToken'), localStorage.getItem('pilog.write.ghToken')]")
    check("token: 'remember' moves it to localStorage", st == [None, FAKE_TOKEN], repr(st))
    pg.click("#sheet-token [data-close]")
    pg.wait_for_timeout(250)

    # ---- happy path through the UI ----
    pg.evaluate("window.__gh.calls = []")
    pg.click(".cta")
    check("publish: unlocked with token", pg.evaluate("!document.querySelector('#btn-publish').disabled"))
    pg.click("#btn-publish")
    pg.wait_for_selector("#pub-out .pub-box.is-ok")
    calls = gh(pg, "S.calls")
    sig = [(c["method"], c["path"].replace(REPO, "")) for c in calls]
    br = plan["branch"]
    want = [("GET", ""), ("GET", "/contents/" + plan["path"]), ("GET", "/git/ref/heads/" + br), ("GET", "/git/ref/heads/pilog"),
            ("POST", "/git/refs"), ("GET", "/contents/" + plan["path"]), ("PUT", "/contents/" + plan["path"]),
            ("GET", "/pulls"), ("POST", "/pulls")]
    check("publish: branch → file → PR call sequence", sig == want, repr(sig))
    check("publish: every call is to Meredith2328/pilog with the device token",
          all(c["path"].startswith(REPO) and c["auth"] == "Bearer " + FAKE_TOKEN and c["credentials"] == "omit" for c in calls))
    check("publish: never merges or pushes pilog directly",
          not any("/merge" in c["path"] or (c["body"] or {}).get("branch") == "pilog" for c in calls)
          and gh(pg, "S.refs.pilog") == "base000")
    put = next(c for c in calls if c["method"] == "PUT")
    post_ref = next(c for c in calls if c["path"].endswith("/git/refs"))
    check("publish: branch created from latest pilog", post_ref["body"] == {"ref": "refs/heads/" + br, "sha": "base000"}, repr(post_ref["body"]))
    check("publish: file content is the assembled markdown",
          put["body"]["branch"] == br and "sha" not in put["body"]
          and base64.b64decode(put["body"]["content"]).decode("utf-8") == plan["file"], repr(put["body"])[:200])
    pr = gh(pg, "S.pulls[0]")
    check("publish: PR into pilog with Chinese title", pr["base"] == "pilog" and pr["head"] == br and pr["title"] == "新文章：手机开 PR"
          and "手动合并" in pr["body"], repr(pr)[:300])
    shown = pg.evaluate("[document.querySelector('#pub-url').href, document.querySelector('#pub-out').innerText]")
    check("publish: shows PR URL + copy/open", shown[0] == pr["html_url"] and "复制链接" in shown[1] and "打开 PR" in shown[1], repr(shown))
    saved = pg.evaluate("window.__pilogWrite.current().pub")
    check("publish: PR remembered on the draft", saved and saved["number"] == pr["number"] and saved["branch"] == br, repr(saved))
    blob = pg.evaluate("JSON.stringify(Object.keys(localStorage).filter(k => k !== 'pilog.write.ghToken').map(k => localStorage.getItem(k)))")
    check("publish: token not stored with drafts / prefs", FAKE_TOKEN not in blob and FAKE_TOKEN not in pg.evaluate("window.__pilogWrite.build()"))

    # ---- republish: branch exists → offer update / new ----
    pg.click("#sheet-export [data-close]")
    pg.wait_for_timeout(250)
    pg.fill("#f-body", "## 你好\n\n改过的正文，足够长的一句话。\n")
    pg.wait_for_timeout(300)
    pg.click(".cta")
    pg.evaluate("window.__gh.calls = []")
    pg.click("#btn-publish")
    pg.wait_for_selector("#pub-out .pub-box.is-warn [data-pub=update]")
    check("republish: asks before touching an existing branch", not any(c["method"] != "GET" for c in gh(pg, "S.calls")))
    pg.click("#pub-out [data-pub=update]")
    pg.wait_for_selector("#pub-out .pub-box.is-ok")
    calls = gh(pg, "S.calls")
    put = [c for c in calls if c["method"] == "PUT"]
    check("republish/update: commits on same branch with sha, reuses PR",
          len(put) == 1 and put[0]["body"]["branch"] == br and put[0]["body"].get("sha")
          and gh(pg, "S.pulls.length") == 1 and "已更新" in pg.inner_text("#pub-out .h")
          and not any(c["method"] == "POST" for c in calls), repr([(c["method"], c["path"]) for c in calls]))
    pg.click("#btn-publish")
    pg.wait_for_selector("#pub-out [data-pub=new]")
    pg.click("#pub-out [data-pub=new]")
    pg.wait_for_selector("#pub-out .pub-box.is-ok")
    check("republish/new: opens a second PR on a fresh branch",
          gh(pg, "S.pulls.length") == 2 and gh(pg, "S.pulls[1].head") == br + "-2", repr(gh(pg, "S.pulls.map(p => p.head)")))

    # ---- file already on pilog (another draft) → overwrite as update ----
    pg.evaluate("""() => { const S = window.__gh; S.files['pilog|blogs/posts/toy/existing.md'] = { content: btoa('old'), sha: 'old1' }; }""")
    pg.click("#sheet-export [data-close]")
    pg.click("#btn-drafts")
    pg.click("#btn-new")
    pg.fill("#f-title", "已有文章")
    pg.fill("#f-body", "新的正文内容，覆盖旧版本。\n")
    pg.click(".tab[data-view=meta]")
    pg.fill("#f-slug", "existing")
    pg.click(".tab[data-view=write]")
    pg.wait_for_timeout(300)
    pg.click(".cta")
    pg.click("#btn-publish")
    pg.wait_for_selector("#pub-out [data-pub=overwrite]")
    check("existing file: warns before overwriting", "已经有" in pg.inner_text("#pub-out") and gh(pg, "S.pulls.length") == 2)
    pg.click("#pub-out [data-pub=overwrite]")
    pg.wait_for_selector("#pub-out .pub-box.is-ok")
    last = gh(pg, "S.pulls[S.pulls.length - 1]")
    put = gh(pg, "S.calls.filter(c => c.method === 'PUT').pop()")
    check("existing file: PR titled as update, PUT carries sha", last["title"] == "更新文章：已有文章"
          and put["body"]["sha"] == "old1", repr((last["title"], put["body"].get("sha"))))

    # ---- failure paths ----
    cases = [0]

    def fail_case(name, setup, expect_text, locks):
        cases[0] += 1
        pg.evaluate("() => { const S = window.__gh; S.fail = []; S.offline = false; S.calls = []; }")
        pg.evaluate(setup)
        r = pg.evaluate(f"window.__pilogWrite.publish({{ branch: 'write/fail-{cases[0]}', overwrite: true }})")
        row = pg.get_attribute("#tok-row", "class")
        text = pg.inner_text("#pub-out")
        dis = pg.evaluate("document.querySelector('#btn-publish').disabled")
        check(f"error: {name}", r["ok"] is False and expect_text in text and dis == locks
              and ("is-bad" in row) == locks, repr((r, text[:160], dis, row)))
        pg.evaluate("() => { const S = window.__gh; S.fail = []; S.offline = false; S.repo.permissions.push = true; }")
        if locks:  # re-saving the token clears the lock
            pg.click("#tok-row [data-open=token]")
            pg.click("#btn-tok-save")
            pg.wait_for_selector("#tok-msg .note.ok")
            pg.click("#sheet-token [data-close]")
            pg.wait_for_timeout(250)
            pg.click(".cta")

    fail_case("401 locks publish", "window.__gh.fail = [{ sig: 'GET " + REPO + "', status: 401, message: 'Bad credentials' }]",
              "401", True)
    fail_case("403 missing permission locks publish",
              "window.__gh.fail = [{ sig: 'PUT', status: 403, message: 'Resource not accessible by personal access token' }]",
              "Pull requests", True)
    fail_case("account without push is refused", "window.__gh.repo.permissions.push = false", "没有写权限", True)
    fail_case("404 repo not granted", "window.__gh.fail = [{ sig: 'GET " + REPO + "', status: 404, message: 'Not Found' }]",
              "404", True)
    fail_case("rate limit keeps token usable", "window.__gh.fail = [{ sig: 'POST " + REPO + "/pulls', status: 403, message: 'API rate limit exceeded' }]",
              "速率限制", False)
    fail_case("network failure", "window.__gh.offline = true", "网络不可用", False)
    ctx.set_offline(True)
    pg.evaluate("window.__gh.calls = []")
    r = pg.evaluate("window.__pilogWrite.publish()")
    check("error: browser offline → no request, draft kept", r["ok"] is False and gh(pg, "S.calls.length") == 0
          and "网络不可用" in pg.inner_text("#pub-out"), repr(r))
    ctx.set_offline(False)

    pg.click("#sheet-export [data-close]")
    pg.click("#btn-drafts")
    pg.click("#sheet-drafts [data-open=token]")
    pg.click("#btn-tok-clear")
    st = pg.evaluate("[sessionStorage.getItem('pilog.write.ghToken'), localStorage.getItem('pilog.write.ghToken')]")
    check("token: clear removes it everywhere", st == [None, None], repr(st))
    check("publish page: no page errors", not errs, "; ".join(errs))
    ctx.close()


def static_security_checks() -> None:
    html = WRITE.read_text(encoding="utf-8")
    import re
    check("security: no token literals in write.html",
          not re.search(r"(github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,})", html))
    csp = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', html)
    check("security: CSP limits connect-src to self + api.github.com",
          bool(csp) and "connect-src 'self' https://api.github.com;" in csp.group(1), csp and csp.group(1))
    hosts = set(re.findall(r"fetch\(\s*[\"']([a-z]+://[^\"'/]+)", html)) | set(re.findall(r'api:\s*"([^"]+)"', html))
    check("security: only api.github.com is contacted", hosts == {"https://api.github.com"}, repr(hosts))


def main() -> None:
    shutil.rmtree(TMP, ignore_errors=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(
            viewport={"width": 412, "height": 860}, is_mobile=True, has_touch=True,
            accept_downloads=True,
        )
        pg = ctx.new_page()
        block_external(pg)
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(f"http://127.0.0.1:{PORT}/write", wait_until="domcontentloaded")
        pg.wait_for_function("!!window.__pilogWrite")
        check("page loads at /write", pg.title().startswith("pilog"), pg.title())

        pg.fill("#f-title", "手机写作: 测试")
        pg.fill("#f-body", BODY)
        pg.click(".tab[data-view=meta]")
        pg.click("#cats [data-cat='notes/tools']")
        pg.fill("#tag-in", "工具，手机")
        pg.check("input[data-f=draft]", force=True)
        pg.wait_for_timeout(700)
        pg.reload(wait_until="domcontentloaded")
        pg.wait_for_function("!!window.__pilogWrite")
        cur = pg.evaluate("window.__pilogWrite.current()")
        check("autosave + restore after reload",
              cur["title"] == "手机写作: 测试" and cur["body"] == BODY
              and cur["category"] == "notes/tools" and cur["tags"] == ["工具", "手机"] and cur["draft"],
              json.dumps(cur, ensure_ascii=False)[:300])

        pg.click(".tab[data-view=preview]")
        md = pg.inner_html("#pv-out .md")
        check("preview: h2 / strong / code", '<h2 id="小标题">' in md and "<strong>加粗</strong>" in md and "<code>code</code>" in md, md[:300])
        check("preview: external link opens in new tab", 'href="https://example.com" target="_blank"' in md, md[:500])
        check("preview: wiki link", 'class="wikilink"' in md and ">站内<" in md)
        check("preview: callout", 'class="callout callout-tip"' in md and "提示标题" in md)
        check("preview: code block with lang tab", 'class="code-lang">python<' in md)
        check("preview: table", "<table>" in md and "<th>a</th>" in md)
        check("preview: repo image becomes placeholder", 'class="img-ph"' in md and "assets/cover-pixel.png" in md)
        check("preview: task item", 'class="task"' in md and "checked" in md)
        check("preview: 2-space item is a sibling, 4-space nests (pilog parity)",
              md.count("<ul>") == 2 and "<li>两空格（pilog 不嵌套）</li>" in md, md)

        pg.click(".cta")
        with pg.expect_download() as dl:
            pg.click("#btn-download")
        d = dl.value
        text = pathlib.Path(d.path()).read_text(encoding="utf-8")
        fm, body = split_front_matter(text)
        check("export: file name from title", d.suggested_filename.endswith(".md"), d.suggested_filename)
        check("export: front matter parsed by pilog",
              fm.get("title") == "手机写作: 测试" and fm.get("tags") == ["工具", "手机"] and fm.get("draft") is True
              and str(fm.get("date", "")).startswith(cur["date"]), repr(fm))
        check("export: body preserved", body.strip() == BODY.strip())
        pg.click("#sheet-export [data-close]")

        bad = []
        for t in TRICKY:
            out = pg.evaluate(
                "t => { const w = window.__pilogWrite, d = w.current(); const old = d.title;"
                " d.title = t; const s = w.build(); d.title = old; return s; }", t)
            got = split_front_matter(out)[0].get("title")
            if got != t:
                bad.append((t, got))
        check("export: tricky titles survive YAML", not bad, repr(bad))

        src = (ROOT / "blogs/posts/toy/anothertodo.md").read_text(encoding="utf-8")
        rt = pg.evaluate("s => { const w = window.__pilogWrite, d = w.parse(s, 'anothertodo.md');"
                         " return {slug: d.slug, file: (function(){ const c = w.current(); const keep = Object.assign({}, c);"
                         " Object.assign(c, d); const f = w.build(); Object.assign(c, keep); return f; })()}; }", src)
        a, _ = split_front_matter(src)
        b2, _ = split_front_matter(rt["file"])
        keys = ("title", "tags", "preview_image", "published", "hideInList")
        check("import → export round trip keeps front matter",
              rt["slug"] == "anothertodo" and all(a.get(k) == b2.get(k) for k in keys)
              and str(a.get("date")) == str(b2.get("date")),
              repr({k: (a.get(k), b2.get(k)) for k in keys + ("date",)}))

        blog = TMP / "blogs" / "posts" / "notes" / "tools"
        blog.mkdir(parents=True)
        (blog / "demo.md").write_text(text.replace("draft: true\n", ""), encoding="utf-8")
        from generator.assets import AssetMap
        from generator.content import scan_posts
        from generator.markdownx import MarkdownContext
        root = TMP / "blogs"
        posts = scan_posts(root, MarkdownContext(blog_root=root, assets=AssetMap(blog_root=root, out_root=TMP / "out")))
        check("exported file is picked up by scan_posts",
              len(posts) == 1 and posts[0].title == "手机写作: 测试" and posts[0].tags == ["工具", "手机"],
              repr([(x.title, x.tags) for x in posts]))

        pg.click("#btn-drafts")
        pg.click("#btn-new")
        pg.wait_for_timeout(300)
        n = pg.evaluate("JSON.parse(localStorage.getItem('pilog.write.index')).ids.length")
        check("new draft adds to the list", n == 2, n)
        pg.click("#btn-drafts")
        pg.click("#draft-list .drow:not(.is-active) [data-act=open]")
        pg.wait_for_timeout(200)
        check("switching drafts restores content", pg.input_value("#f-title") == "手机写作: 测试")
        n = pg.evaluate("JSON.parse(localStorage.getItem('pilog.write.index')).ids.length")
        check("blank draft is discarded when leaving it", n == 1, n)

        check("no page errors", not errs, "; ".join(errs))
        publish_checks(b)
        static_security_checks()
        b.close()
    shutil.rmtree(TMP, ignore_errors=True)
    srv.shutdown()
    print("ALL PASS" if ok else "SOME FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
