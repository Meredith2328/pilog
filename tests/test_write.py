#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression checks for the mobile writer (tools/write.html served at /write):
autosave/restore, preview rendering, drafts, and that exported front matter is
read back correctly by pilog's own parser."""

from __future__ import annotations

import json
import pathlib
import shutil
import sys
import threading

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TMP = ROOT / ".write_tmp"

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
        b.close()
    shutil.rmtree(TMP, ignore_errors=True)
    srv.shutdown()
    print("ALL PASS" if ok else "SOME FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
