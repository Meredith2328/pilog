#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression checks for the writer's local image manager (tools/write.html):
entry points, the IndexedDB gallery, import/crop/rotate/flip/save, inline
rename + reference rewriting, two-step delete, inserting references into the
draft (preview / card / export), publishing images as PR assets, vault hiding
and the 360px layout.

Images are generated with PIL into .write_images_tmp. GitHub publish checks use
an in-page fetch mock (like tests/test_write.py), so nothing leaves the machine.
"""

from __future__ import annotations

import base64
import json
import pathlib
import re
import shutil
import sys
import threading

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TMP = ROOT / ".write_images_tmp"
IMG = TMP / "img"

from util import block_external  # noqa: E402

import serve  # noqa: E402

PORT = 8292
srv = serve.ThreadingHTTPServer(("127.0.0.1", PORT), serve.Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()

from PIL import Image  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

ok = True

NAME_RE = re.compile(r"^img-\d{8}-\d{6}-[a-z0-9]{4}\.(png|jpg)$")
GH_MOCK = r"""
(() => {
  const real = window.fetch.bind(window);
  const S = window.__gh = { calls: [], files: {}, refs: { pilog: "base000" }, n: 0, pulls: [],
    repo: { full_name: "Meredith2328/pilog", permissions: { admin: true, push: true, pull: true } } };
  const out = (status, body) => Promise.resolve(new Response(body == null ? "" : JSON.stringify(body),
    { status, headers: { "Content-Type": "application/json" } }));
  window.fetch = function (url, init) {
    url = String(url);
    if (!url.startsWith("https://api.github.com/")) return real(url, init);
    init = init || {};
    const u = new URL(url), method = (init.method || "GET").toUpperCase();
    const body = init.body ? JSON.parse(init.body) : null;
    S.calls.push({ method, path: decodeURIComponent(u.pathname), query: Object.fromEntries(u.searchParams),
      auth: (init.headers || {}).Authorization || "", body });
    const pre = "/repos/Meredith2328/pilog";
    if (!u.pathname.startsWith(pre)) return out(404, { message: "Not Found" });
    const p = decodeURIComponent(u.pathname.slice(pre.length));
    if (p === "" && method === "GET") return out(200, S.repo);
    if (p.startsWith("/git/ref/heads/") && method === "GET") {
      const b = p.slice(15);
      return b in S.refs ? out(200, { ref: "refs/heads/" + b, object: { sha: S.refs[b] } }) : out(404, { message: "Not Found" });
    }
    if (p === "/git/refs" && method === "POST") {
      S.refs[body.ref.replace("refs/heads/", "")] = body.sha;
      return out(201, { ref: body.ref, object: { sha: body.sha } });
    }
    if (p.startsWith("/contents/")) {
      const path = p.slice(10), ref = u.searchParams.get("ref") || (body && body.branch);
      const k = ref + "|" + path, ex = S.files[k];
      if (method === "GET" && ex) return out(200, { type: "file", path, sha: ex.sha, content: ex.content });
      if (method === "GET") return out(404, { message: "Not Found" });
      if (method === "PUT") {
        const sha = "blob" + (++S.n);
        S.files[k] = { content: body.content, sha };
        return out(ex ? 200 : 201, { content: { path, sha } });
      }
    }
    if (p === "/pulls" && method === "GET") return out(200, []);
    if (p === "/pulls" && method === "POST") {
      const pr = { number: 1, state: "open", head: body.head, base: body.base, title: body.title,
        body: body.body, html_url: "https://github.com/Meredith2328/pilog/pull/1" };
      S.pulls.push(pr);
      return out(201, pr);
    }
    return out(404, { message: "mock 404" });
  };
})();
"""
FAKE_TOKEN = "github_pat_FAKE0000TEST0000ONLY0000xyzw"
TRACK_CALLS = r"""
window.__promptCalls = [];
window.prompt = function () { window.__promptCalls.push(arguments[0] || ""); return ""; };
window.__confirmCalls = [];
window.confirm = function () { window.__confirmCalls.push(arguments[0] || ""); return true; };
"""


def check(name, cond, detail=""):
    global ok
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + ("" if cond else f" — {detail}"))
    ok = ok and cond


# ---------------------------------------------------------------------------
# page helpers
# ---------------------------------------------------------------------------


def wait_js(pg, expr, timeout_ms=12000):
    """Poll with page.evaluate; the writer's CSP blocks wait_for_function."""
    for _ in range(max(1, timeout_ms // 50)):
        try:
            if pg.evaluate(expr):
                return True
        except Exception:
            pass
        pg.wait_for_timeout(50)
    raise AssertionError("timed out waiting for: " + expr)


def new_page(b, mobile=True, width=412, gh=False):
    ctx = b.new_context(viewport={"width": width, "height": 860},
                        is_mobile=mobile, has_touch=mobile, accept_downloads=True)
    ctx.add_init_script(TRACK_CALLS)
    if gh:
        ctx.add_init_script(GH_MOCK)
        ctx.add_init_script(
            "try { sessionStorage.setItem('pilog.write.ghToken', %s); } catch (e) {}"
            % json.dumps(FAKE_TOKEN))
    pg = ctx.new_page()
    block_external(pg)
    pg.route("**/api/tree", lambda r: r.fulfill(
        status=200, content_type="application/json", body='{"ok": true, "dirs": []}'))
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{PORT}/tools/write.html", wait_until="domcontentloaded")
    wait_js(pg, "!!window.__pilogWrite")
    return ctx, pg, errs


def no_errors(label, errs):
    check(f"{label}: no page errors", not errs, "; ".join(errs))


def images_ready(pg):
    wait_js(pg, "window.__pilogWrite.images.ready()")


def img_list(pg):
    return pg.evaluate("window.__pilogWrite.images.list()")


def img_names(pg):
    return [x["name"] for x in img_list(pg)]


def editor(pg):
    return pg.evaluate("window.__pilogWrite.images.editor()")


def open_images_desktop(pg):
    if pg.evaluate("document.querySelector('#app').dataset.view") != "write":
        pg.click('.tab[data-view=write]')
        pg.wait_for_timeout(150)
    pg.click('[data-k="img"]')
    wait_js(pg, "document.querySelector('#sheet-images').classList.contains('is-open')")
    pg.wait_for_timeout(150)


def open_images_mobile(pg):
    pg.click("#btn-drafts")
    wait_js(pg, "document.querySelector('#sheet-drafts').classList.contains('is-open')")
    pg.wait_for_timeout(200)
    pg.click("#d-menu")
    wait_js(pg, "!document.querySelector('#d-menu-pop').hidden")
    pg.click("#d-menu-pop #d-images")
    wait_js(pg, "document.querySelector('#sheet-images').classList.contains('is-open')")
    pg.wait_for_timeout(150)


def close_images(pg):
    if pg.evaluate("document.querySelector('#sheet-images').classList.contains('is-open')"):
        pg.click("#sheet-images .sheet-h [data-close]")
        pg.wait_for_timeout(150)


def import_images(pg, *paths):
    before = len(img_list(pg))
    pg.set_input_files("#img-file", [str(p) for p in paths])
    wait_js(pg, f"window.__pilogWrite.images.list().length >= {before + len(paths)}")
    pg.wait_for_timeout(350)


def open_editor(pg, name):
    if pg.locator("#img-grid").is_hidden():
        pg.click("#img-back")
        pg.wait_for_timeout(220)
    pg.click(f'#img-grid .img-cell[data-img-name="{name}"]')
    wait_js(pg, "!!window.__pilogWrite.images.editor()")
    pg.wait_for_timeout(200)


def storage_drafts(pg):
    return pg.evaluate("""() => {
      const idx = JSON.parse(localStorage.getItem('pilog.write.index') || '{}');
      const out = {};
      (idx.ids || []).forEach(function (id) {
        out[id] = JSON.parse(localStorage.getItem('pilog.write.d.' + id) || 'null');
      });
      return out;
    }""")


def draft_seed_js(draft_list):
    payload = {"drafts": draft_list,
               "index": {"active": draft_list[0]["id"],
                         "ids": [d["id"] for d in draft_list]},
               "prefs": {"sort": "updated", "filter": "all", "cat": "toy", "pv": "post"}}
    return """((seed) => {
      try {
        seed.drafts.forEach(function (d) {
          localStorage.setItem('pilog.write.d.' + d.id, JSON.stringify(d));
        });
        localStorage.setItem('pilog.write.index', JSON.stringify(seed.index));
        localStorage.setItem('pilog.write.prefs', JSON.stringify(seed.prefs));
      } catch (e) {}
    })(%s);""" % json.dumps(payload, ensure_ascii=False)


def make_draft(did, title, **kw):
    d = {
        "id": did, "created": 1760000000000, "updated": 1760000000000, "exported": 0,
        "title": title, "body": "正文 " + title, "category": "toy", "slug": "",
        "filenameSuffix": "123456", "date": "2026-01-01", "time": "10:00",
        "sec": "", "tags": [], "preview": "", "draft": False, "previewImage": "",
        "featureMode": "off", "featurePath": "", "pin": False, "highlight": False,
        "hidden": False, "order": "", "chapters": "", "extra": "", "caret": 0,
        "pub": None, "src": None, "pinned": False, "archived": False, "sortRank": 0,
    }
    d.update(kw)
    return d


# ---------------------------------------------------------------------------
# scenarios
# ---------------------------------------------------------------------------


def entry_checks(b):
    print("\n== entry points ==")
    # desktop: the format toolbar button
    ctx, pg, errs = new_page(b, mobile=False)
    check("desktop: [data-k=img] toolbar entry is visible",
          pg.locator('[data-k="img"]').is_visible())
    check("desktop: image entry is the icon button, not the old ![] text",
          pg.get_attribute('[data-k="img"]', "id") == "btn-fmt-img"
          and pg.get_attribute('[data-k="img"]', "aria-label") == "插入图片"
          and pg.locator("#btn-fmt-img .pix svg").count() == 1
          and "![]" not in pg.inner_text("#fmt-keys"))
    pos = pg.evaluate("""() => {
      const b = document.querySelector('#btn-fmt-img').getBoundingClientRect();
      const f = document.querySelector('#fmt').getBoundingClientRect();
      const keys = document.querySelector('#fmt-keys').getBoundingClientRect();
      return {
        right: b.right, fmtRight: f.right, left: b.left, keysRight: keys.right,
        insideKeys: !!document.querySelector('#fmt-keys #btn-fmt-img')
      };
    }""")
    check("desktop: image icon sits at the right edge, outside the scrollable keys",
          abs(pos["right"] - pos["fmtRight"]) < 2
          and not pos["insideKeys"] and pos["left"] >= pos["keysRight"] - 1, repr(pos))
    open_images_desktop(pg)
    check("desktop: [data-k=img] opens #sheet-images",
          pg.evaluate("document.querySelector('#sheet-images').classList.contains('is-open')")
          and pg.inner_text("#sh-images-t").strip() == "图片")
    images_ready(pg)
    check("images API is ready on boot", img_list(pg) == [], repr(img_list(pg)))
    no_errors("desktop entry", errs)
    ctx.close()

    # mobile: drafts ⋯ → 图片库
    ctx, pg, errs = new_page(b)
    check("mobile: format toolbar is hidden", not pg.locator('[data-k="img"]').is_visible())
    pg.click("#btn-drafts")
    wait_js(pg, "document.querySelector('#sheet-drafts').classList.contains('is-open')")
    pg.wait_for_timeout(200)
    pg.click("#d-menu")
    wait_js(pg, "!document.querySelector('#d-menu-pop').hidden")
    items = pg.evaluate("""() => Array.from(document.querySelectorAll('#d-menu-pop button')).map(function (b) {
      return { id: b.id, open: b.dataset.open || '', text: b.textContent.trim() };
    })""")
    check("drafts ⋯ menu now has 4 items with 图片库 in second place",
          len(items) == 4
          and items[0]["open"] == "remote" and "编辑线上文章" in items[0]["text"]
          and items[1]["id"] == "d-images" and "图片库" in items[1]["text"]
          and items[2]["id"] == "d-archived"
          and items[3]["open"] == "more", repr(items))
    pg.click("#d-menu-pop #d-images")
    wait_js(pg, "document.querySelector('#sheet-images').classList.contains('is-open')")
    check("mobile: ⋯ → 图片库 opens #sheet-images and closes the drafts sheet",
          pg.evaluate("document.querySelector('#sheet-images').classList.contains('is-open')")
          and not pg.evaluate("document.querySelector('#sheet-drafts').classList.contains('is-open')"))
    no_errors("mobile entry", errs)
    ctx.close()


def api_checks(b):
    print("\n== window.__pilogWrite.images API ==")
    ctx, pg, errs = new_page(b, mobile=False)
    pg.evaluate("window.__pilogWrite.images.open()")
    wait_js(pg, "document.querySelector('#sheet-images').classList.contains('is-open')")
    import_images(pg, IMG / "plain.png", IMG / "photo.jpg")
    images_ready(pg)
    meta = img_list(pg)
    check("list() returns serializable meta only",
          len(meta) == 2
          and all(set(x) == {"name", "w", "h", "bytes", "type"} for x in meta),
          repr(meta))
    check("list() meta carries real dimensions and mime types",
          sorted((x["type"], x["w"], x["h"]) for x in meta)
          == [("image/jpeg", 300, 200), ("image/png", 320, 240)], repr(meta))
    check("names match img-YYYYMMDD-HHMMSS-xxxx.(png|jpg)",
          all(NAME_RE.match(x["name"]) for x in meta), repr([x["name"] for x in meta]))
    serial = pg.evaluate("() => { try { JSON.stringify(window.__pilogWrite.images.list()); return true; } catch (e) { return false; } }")
    check("list() is JSON-serializable (no blobs leak)", serial is True)
    first_name = img_list(pg)[0]["name"]
    scan = pg.evaluate("""([wiki, md, missing, plain]) => ({
      wiki: window.__pilogWrite.images.scan(wiki),
      md: window.__pilogWrite.images.scan(md),
      missing: window.__pilogWrite.images.scan(missing),
      empty: window.__pilogWrite.images.scan(plain),
    })""", [
        f"a ![[{first_name}]] b",
        f"![alt](../assets/{first_name})",
        "![[missing.png]] ![](nope.jpg)",
        "plain text",
    ])
    check("scan() finds existing refs in both wikilink and markdown syntax",
          scan["wiki"] == [first_name] and scan["md"] == [first_name],
          repr(scan))
    check("scan() ignores missing names and plain text",
          scan["missing"] == [] and scan["empty"] == [], repr(scan))
    check("editor() is null in the gallery", editor(pg) is None, repr(editor(pg)))
    open_editor(pg, meta[0]["name"])
    ed = editor(pg)
    check("editor() reports {name,w,h,dirty} after opening a cell",
          ed is not None and set(ed) == {"name", "w", "h", "dirty"}
          and ed["name"] == meta[0]["name"] and ed["dirty"] is False, repr(ed))
    no_errors("images API", errs)
    ctx.close()


def import_checks(b):
    print("\n== import ==")
    ctx, pg, errs = new_page(b, mobile=False)
    open_images_desktop(pg)
    images_ready(pg)
    check("empty library shows #img-empty and a 本机图片 counter",
          pg.locator("#img-empty").is_visible()
          and pg.inner_text("#images-sub").strip() == "本机图片",
          f"{pg.inner_text('#images-sub')} / empty={pg.locator('#img-empty').is_visible()}")

    import_images(pg, IMG / "plain.png")
    wait_js(pg, "!!window.__pilogWrite.images.editor()")
    names = img_names(pg)
    check("single PNG import keeps .png and auto-opens the editor",
          len(names) == 1 and names[0].endswith(".png")
          and img_list(pg)[0]["type"] == "image/png"
          and pg.locator("#img-editor").is_visible(),
          repr(img_list(pg)))
    check("gallery counter and empty state update",
          pg.inner_text("#images-sub").strip() == "1 张"
          and not pg.locator("#img-empty").is_visible())
    pg.click("#img-back")
    pg.wait_for_timeout(200)
    check("gallery renders .img-cell[data-img-name] cards",
          pg.locator(f'#img-grid .img-cell[data-img-name="{names[0]}"]').count() == 1)

    import_images(pg, IMG / "big.png", IMG / "photo.jpg")
    wait_js(pg, "window.__pilogWrite.images.list().length === 3")
    pg.wait_for_timeout(300)
    names = img_names(pg)
    big = next(x for x in img_list(pg) if x["w"] == 2000 or x["h"] == 2000)
    jpg = next(x for x in img_list(pg) if x["type"] == "image/jpeg")
    check("JPEG import keeps .jpg and image/jpeg", jpg["name"].endswith(".jpg"), repr(jpg))
    check("long edge > 2000 is downscaled to 2000 on import",
          (big["w"], big["h"]) == (2000, 1000), repr(big))
    check("multi-file import stays in the gallery (no editor)",
          editor(pg) is None and pg.locator("#img-editor").is_hidden()
          and pg.locator("#img-grid").is_visible(), repr(editor(pg)))
    check("every imported name is unique and well formed",
          len(set(names)) == 3 and all(NAME_RE.match(n) for n in names), repr(names))
    check("gallery shows all three cells", pg.locator("#img-grid .img-cell").count() == 3)
    no_errors("import", errs)
    ctx.close()


def edit_checks(b):
    print("\n== editor: rotate / reset / long edge / persistence ==")
    ctx, pg, errs = new_page(b, mobile=False)
    open_images_desktop(pg)
    import_images(pg, IMG / "plain.png")
    wait_js(pg, "!!window.__pilogWrite.images.editor()")
    name = img_names(pg)[0]
    ed = editor(pg)
    check("editor reports the original 320x240 image",
          (ed["w"], ed["h"]) == (320, 240) and ed["dirty"] is False, repr(ed))
    check("#img-info shows dimensions", "320×240" in pg.inner_text("#img-info"),
          pg.inner_text("#img-info"))

    pg.click('[data-img="rotr"]')
    pg.wait_for_timeout(200)
    ed = editor(pg)
    check("rotate 90° swaps width and height and marks 未保存",
          (ed["w"], ed["h"]) == (240, 320) and ed["dirty"] is True
          and "未保存" in pg.inner_text("#img-info"), repr(ed))
    pg.click("#img-reset")
    pg.wait_for_timeout(400)
    ed = editor(pg)
    check("#img-reset restores the last saved image",
          (ed["w"], ed["h"]) == (320, 240) and ed["dirty"] is False, repr(ed))
    pg.click('[data-img="fliph"]')
    pg.wait_for_timeout(150)
    check("horizontal flip marks the image dirty", editor(pg)["dirty"] is True)

    pg.click('[data-img="rotr"]')
    pg.wait_for_timeout(150)
    rotated = editor(pg)
    pg.click("#img-apply")
    wait_js(pg, "(() => { const e = window.__pilogWrite.images.editor();"
                f" return e && e.w === {rotated['w']} && e.h === {rotated['h']} && e.dirty === false; }})()")
    saved = next(x for x in img_list(pg) if x["name"] == name)
    check("保存修改 persists the rotated dimensions",
          (saved["w"], saved["h"]) == (rotated["w"], rotated["h"]), repr(saved))

    pg.reload(wait_until="domcontentloaded")
    wait_js(pg, "!!window.__pilogWrite")
    images_ready(pg)
    after = next(x for x in img_list(pg) if x["name"] == name)
    check("saved dimensions survive a reload", (after["w"], after["h"]) == (saved["w"], saved["h"]),
          f"{saved} -> {after}")

    # long-edge downscale on save
    open_images_desktop(pg)
    import_images(pg, IMG / "big.png")
    wait_js(pg, "!!window.__pilogWrite.images.editor()")
    big_name = editor(pg)["name"]
    opts = pg.eval_on_selector_all("#img-long option", "els => els.map(e => e.value)")
    check("#img-long offers 0/2000/1600/1200/800",
          opts == ["0", "2000", "1600", "1200", "800"], repr(opts))
    pg.select_option("#img-long", "800")
    pg.click("#img-apply")
    wait_js(pg, "(() => { const e = window.__pilogWrite.images.editor();"
                " return e && Math.max(e.w, e.h) === 800 && e.dirty === false; })()")
    down = next(x for x in img_list(pg) if x["name"] == big_name)
    check("长边 800 downscales the image on save",
          max(down["w"], down["h"]) == 800 and (down["w"], down["h"]) == (800, 400), repr(down))
    no_errors("editor", errs)
    ctx.close()


def crop_checks(b):
    print("\n== crop ==")
    ctx, pg, errs = new_page(b, mobile=False)
    open_images_desktop(pg)
    import_images(pg, IMG / "edit.png")
    wait_js(pg, "!!window.__pilogWrite.images.editor()")
    name = editor(pg)["name"]
    pg.click("#img-crop-tool")
    pg.wait_for_timeout(150)
    check("裁剪 toggles the crop tool on", "on" in (pg.get_attribute("#img-crop-tool", "class") or ""))
    bb = pg.locator("#img-canvas").bounding_box()
    pg.mouse.move(bb["x"] + bb["width"] * 0.2, bb["y"] + bb["height"] * 0.2)
    pg.mouse.down()
    pg.mouse.move(bb["x"] + bb["width"] * 0.7, bb["y"] + bb["height"] * 0.75, steps=8)
    pg.mouse.up()
    pg.wait_for_timeout(250)
    check("dragging on #img-canvas shows the crop overlay and 应用裁剪",
          pg.locator("#img-crop").is_visible()
          and pg.locator("#img-crop-apply").is_visible())
    pg.click("#img-crop-apply")
    pg.wait_for_timeout(250)
    cropped = editor(pg)
    check("applying a crop reduces dimensions and marks 未保存",
          cropped["w"] < 400 and cropped["h"] < 300 and cropped["dirty"] is True
          and "未保存" in pg.inner_text("#img-info"), repr(cropped))
    pg.click("#img-apply")
    wait_js(pg, "(() => { const e = window.__pilogWrite.images.editor();"
                f" return e && e.w === {cropped['w']} && e.h === {cropped['h']} && e.dirty === false; }})()")
    saved = next(x for x in img_list(pg) if x["name"] == name)
    check("saving the crop persists the new dimensions",
          (saved["w"], saved["h"]) == (cropped["w"], cropped["h"]), repr(saved))
    pg.reload(wait_until="domcontentloaded")
    wait_js(pg, "!!window.__pilogWrite")
    images_ready(pg)
    after = next(x for x in img_list(pg) if x["name"] == name)
    check("cropped dimensions survive a reload", (after["w"], after["h"]) == (saved["w"], saved["h"]),
          f"{saved} -> {after}")
    no_errors("crop", errs)
    ctx.close()


def rename_checks(b):
    print("\n== rename + reference rewrite ==")
    ctx, pg, errs = new_page(b, mobile=False)
    open_images_desktop(pg)
    import_images(pg, IMG / "plain.png")
    wait_js(pg, "!!window.__pilogWrite.images.editor()")
    old = img_names(pg)[0]
    close_images(pg)
    drafts = [
        make_draft("r1", "带图稿",
                   body=f"## 图\n\n![[{old}]] 和文本", slug="with-image",
                   preview=f"pre {old}", previewImage=f"assets/{old}",
                   featureMode="path", featurePath=f"assets/{old}"),
        make_draft("r2", "第二篇", body=f"正文引用 {old} 一次", slug="second",
                   updated=1759999999000, sortRank=1),
    ]
    pg.evaluate(draft_seed_js(drafts))
    pg.reload(wait_until="domcontentloaded")
    wait_js(pg, "!!window.__pilogWrite")
    images_ready(pg)
    open_images_desktop(pg)
    open_editor(pg, old)
    pg.click("#img-rename")
    pg.wait_for_timeout(150)
    check("重命名 opens an inline input row (no prompt)",
          pg.locator("#img-rename-row").is_visible()
          and pg.input_value("#img-rename-in") == old
          and pg.evaluate("window.__promptCalls.length") == 0)
    pg.fill("#img-rename-in", "renamed-shot")
    pg.click("#img-rename-ok")
    wait_js(pg, "window.__pilogWrite.images.list().some(x => x.name === 'renamed-shot.png')")
    pg.wait_for_timeout(450)
    names = img_names(pg)
    check("rename keeps the extension when none is typed",
          names == ["renamed-shot.png"], repr(names))
    stored = storage_drafts(pg)
    check("rename rewrites body/preview/previewImage/featurePath in every draft",
          stored["r1"]["body"].count("renamed-shot.png") == 1
          and old not in stored["r1"]["body"]
          and stored["r1"]["preview"] == "pre renamed-shot.png"
          and stored["r1"]["previewImage"] == "assets/renamed-shot.png"
          and stored["r1"]["featurePath"] == "assets/renamed-shot.png"
          and stored["r2"]["body"] == "正文引用 renamed-shot.png 一次",
          repr({k: {f: stored[k][f] for f in ("body", "preview", "previewImage", "featurePath")}
                for k in ("r1", "r2")}))
    check("rename updated the current draft body in the editor",
          "renamed-shot.png" in pg.input_value("#f-body")
          and old not in pg.input_value("#f-body"), pg.input_value("#f-body")[:80])
    check("rename toast reports rewritten drafts", "已重命名" in pg.inner_text("#toast"),
          pg.inner_text("#toast"))
    check("rename never calls window.prompt", pg.evaluate("window.__promptCalls.length") == 0)

    # collision with an existing name
    pg.click("#img-back")
    pg.wait_for_timeout(200)
    import_images(pg, IMG / "photo.jpg")
    wait_js(pg, "window.__pilogWrite.images.list().length === 2")
    pg.wait_for_timeout(250)
    other = next(x["name"] for x in img_list(pg) if x["name"] != "renamed-shot.png")
    open_editor(pg, "renamed-shot.png")
    pg.click("#img-rename")
    pg.fill("#img-rename-in", other)
    pg.click("#img-rename-ok")
    pg.wait_for_timeout(500)
    check("renaming onto an existing name is rejected",
          "已经有同名图片" in pg.inner_text("#toast")
          and sorted(img_names(pg)) == sorted(["renamed-shot.png", other]),
          f"{img_names(pg)} / {pg.inner_text('#toast')}")
    no_errors("rename", errs)
    ctx.close()


def delete_checks(b):
    print("\n== delete (two-step) ==")
    ctx, pg, errs = new_page(b, mobile=False)
    open_images_desktop(pg)
    import_images(pg, IMG / "plain.png", IMG / "extra.png")
    wait_js(pg, "window.__pilogWrite.images.list().length === 2")
    pg.wait_for_timeout(300)
    names = img_names(pg)
    doomed = names[0]
    keep = names[1]
    # make the current draft reference the doomed image so the toast mentions it
    pg.evaluate("""(name) => {
      const d = window.__pilogWrite.current();
      d.body = '![' + '[' + name + ']' + ']';
      localStorage.setItem('pilog.write.d.' + d.id, JSON.stringify(d));
    }""", doomed)
    open_editor(pg, doomed)
    pg.click("#img-del")
    pg.wait_for_timeout(200)
    check("first 删除 click asks for confirmation without deleting",
          pg.inner_text("#img-del").strip() == "再点一次删除"
          and len(img_names(pg)) == 2 and editor(pg) is not None,
          f"{pg.inner_text('#img-del')} / {img_names(pg)}")
    check("delete warns that drafts reference the image",
          "引用" in pg.inner_text("#toast"), pg.inner_text("#toast"))
    pg.click("#img-del")
    wait_js(pg, f"window.__pilogWrite.images.list().length === 1")
    pg.wait_for_timeout(400)
    check("second 删除 click deletes the image and returns to the gallery",
          img_names(pg) == [keep] and editor(pg) is None
          and pg.locator("#img-grid").is_visible(), f"{img_names(pg)} / {editor(pg)}")
    check("delete never calls window.confirm",
          pg.evaluate("window.__confirmCalls.length") == 0)
    pg.reload(wait_until="domcontentloaded")
    wait_js(pg, "!!window.__pilogWrite")
    images_ready(pg)
    check("deleted image stays gone after a reload", img_names(pg) == [keep], repr(img_names(pg)))
    no_errors("delete", errs)
    ctx.close()


def insert_preview_export_checks(b):
    print("\n== insert → preview / card / export ==")
    ctx, pg, errs = new_page(b, mobile=False)
    pg.fill("#f-body", "hello world")
    pg.evaluate("() => { const t = document.querySelector('#f-body'); t.focus(); t.setSelectionRange(t.value.length, t.value.length); }")
    open_images_desktop(pg)
    import_images(pg, IMG / "plain.png")
    wait_js(pg, "!!window.__pilogWrite.images.editor()")
    name = img_names(pg)[0]
    pg.click("#img-insert")
    wait_js(pg, "!document.querySelector('#sheet-images').classList.contains('is-open')")
    pg.wait_for_timeout(300)
    body_val = pg.input_value("#f-body")
    check("插入正文 inserts ![[name]] at the caret and closes the sheet",
          f"![[{name}]]" in body_val and body_val.startswith("hello world"), body_val[:120])

    pg.click('.tab[data-view=preview]')
    pg.wait_for_timeout(350)
    prev = pg.evaluate("""() => {
      const im = document.querySelector('#pv-out .md img');
      return im ? { src: im.getAttribute('src'), dataSrc: im.dataset.src, alt: im.alt } : null;
    }""")
    check("preview renders a blob: image with data-src = name",
          prev is not None and prev["src"].startswith("blob:")
          and prev["dataSrc"] == name, repr(prev))

    pg.evaluate("(name) => { window.__pilogWrite.current().previewImage = name; }", name)
    pg.click('#pv-seg [data-v=post]')
    pg.wait_for_timeout(120)
    pg.click('#pv-seg [data-v=card]')
    pg.wait_for_timeout(300)
    card_src = pg.evaluate("() => { const im = document.querySelector('.card-img img'); return im ? im.getAttribute('src') : null; }")
    check("card preview resolves a local preview_image to a blob: <img>",
          bool(card_src) and card_src.startswith("blob:"), repr(card_src))

    pg.click(".cta")
    wait_js(pg, "document.querySelector('#sheet-export').classList.contains('is-open')")
    pg.wait_for_timeout(250)
    ex = pg.evaluate("""() => ({
      cells: document.querySelectorAll('#ex-images .ex-img').length,
      dl: Array.from(document.querySelectorAll('#ex-images [data-img-dl]')).map(function (b) { return b.dataset.imgDl; }),
      thumb: (function () { const i = document.querySelector('#ex-images .ex-img img'); return i ? i.getAttribute('src') : ''; })(),
    })""")
    check("export sheet lists the referenced image with a download button",
          ex["cells"] == 1 and ex["dl"] == [name]
          and ex["thumb"].startswith("blob:"), repr(ex))
    pg.click("#sheet-export [data-close]")
    pg.wait_for_timeout(150)

    open_images_desktop(pg)
    import_images(pg, IMG / "extra.png")
    wait_js(pg, "window.__pilogWrite.images.list().length === 2")
    pg.wait_for_timeout(250)
    close_images(pg)
    pg.click(".cta")
    wait_js(pg, "document.querySelector('#sheet-export').classList.contains('is-open')")
    pg.wait_for_timeout(250)
    check("export lists only images referenced by the draft",
          pg.evaluate("document.querySelectorAll('#ex-images .ex-img').length") == 1)
    no_errors("insert/preview/export", errs)
    ctx.close()


def publish_checks(b):
    print("\n== publish images as PR assets ==")
    # --- with an inserted image ---
    ctx, pg, errs = new_page(b, mobile=False, gh=True)
    open_images_desktop(pg)
    import_images(pg, IMG / "plain.png")
    wait_js(pg, "!!window.__pilogWrite.images.editor()")
    name = img_names(pg)[0]
    close_images(pg)
    pg.evaluate("""(name) => {
      const d = window.__pilogWrite.current();
      d.title = '图片测试'; d.slug = 'img-test'; d.date = '2026-10-27'; d.tags = [];
      d.body = '![[' + name + ']]\\n\\n正文';
    }""", name)
    plan = pg.evaluate("() => { const p = window.__pilogWrite.plan(); return { path: p.path, branch: p.branch, assets: p.assets, errors: p.errors }; }")
    check("publish plan lists the referenced image asset",
          plan["errors"] == [] and len(plan["assets"]) == 1
          and plan["assets"][0]["name"] == name, repr(plan))
    pg.click(".cta")
    wait_js(pg, "document.querySelector('#sheet-export').classList.contains('is-open')")
    wait_js(pg, "!document.querySelector('#btn-publish').disabled")
    pg.click("#btn-publish")
    wait_js(pg, "!!document.querySelector('#pub-out .pub-box.is-ok')", 20000)
    steps = pg.evaluate("""() => Array.from(document.querySelectorAll('#pub-steps li')).map(function (li) {
      return { text: li.textContent.trim(), cls: li.className };
    })""")
    check("publish steps include 上传图片 and all finish ok",
          len(steps) == 5 and steps[2]["text"] == "上传图片"
          and all("is-ok" in s["cls"] for s in steps), repr(steps))
    calls = pg.evaluate("window.__gh.calls.map(function (c) { return { m: c.method, p: c.path, body: c.body }; })")
    puts = [c for c in calls if c["m"] == "PUT"]
    asset_puts = [c for c in puts if "blogs/assets/" in c["p"]]
    md_puts = [c for c in puts if c["p"].endswith(".md")]
    check("asset PUT happens before the markdown PUT",
          len(asset_puts) == 1 and len(md_puts) == 1
          and puts.index(asset_puts[0]) < puts.index(md_puts[0]), repr([c["p"] for c in puts]))
    check("asset is uploaded to blogs/assets/<name>",
          asset_puts[0]["p"].endswith("blogs/assets/" + name), repr(asset_puts[0]["p"]))
    raw = base64.b64decode(asset_puts[0]["body"]["content"])
    check("asset content is base64 for a real PNG",
          raw[:8] == b"\x89PNG\r\n\x1a\n" and len(raw) > 100, repr(raw[:8]))
    check("asset upload bytes match the gallery meta",
          len(raw) == plan["assets"][0]["bytes"], f"{len(raw)} vs {plan['assets'][0]['bytes']}")
    pr = pg.evaluate("window.__gh.pulls[0]")
    check("PR body mentions the uploaded image path",
          pr is not None and ("blogs/assets/" + name) in pr["body"], repr(pr)[:300])
    no_errors("publish image", errs)
    ctx.close()

    # --- no image referenced: no asset upload ---
    ctx, pg, errs = new_page(b, mobile=False, gh=True)
    pg.evaluate("""() => {
      const d = window.__pilogWrite.current();
      d.title = '无图文章'; d.slug = 'no-image'; d.date = '2026-10-27'; d.tags = [];
      d.body = '只有文字。';
    }""")
    pg.click(".cta")
    wait_js(pg, "document.querySelector('#sheet-export').classList.contains('is-open')")
    wait_js(pg, "!document.querySelector('#btn-publish').disabled")
    pg.click("#btn-publish")
    wait_js(pg, "!!document.querySelector('#pub-out .pub-box.is-ok')", 20000)
    calls = pg.evaluate("window.__gh.calls.map(function (c) { return { m: c.method, p: c.path }; })")
    check("no-image publish makes no blogs/assets PUT",
          not any(c["m"] == "PUT" and "blogs/assets/" in c["p"] for c in calls),
          repr([c["p"] for c in calls if c["m"] == "PUT"]))
    pr = pg.evaluate("window.__gh.pulls[0]")
    check("no-image PR body omits the 图片 line",
          pr is not None and "图片：" not in pr["body"], repr(pr)[:300])
    no_errors("publish no-image", errs)
    ctx.close()

    # --- same bytes already on the branch: skip the asset PUT ---
    ctx, pg, errs = new_page(b, mobile=False, gh=True)
    open_images_desktop(pg)
    import_images(pg, IMG / "plain.png")
    wait_js(pg, "!!window.__pilogWrite.images.editor()")
    name = img_names(pg)[0]
    close_images(pg)
    pg.evaluate("""(name) => {
      const d = window.__pilogWrite.current();
      d.title = '同图'; d.slug = 'same-img'; d.date = '2026-10-27'; d.tags = [];
      d.body = '![[' + name + ']]';
    }""", name)
    seeded = pg.evaluate("""async (name) => {
      const plan = window.__pilogWrite.plan();
      const rec = await new Promise(function (res) {
        const r = indexedDB.open('pilog-write-assets', 1);
        r.onsuccess = function () {
          const q = r.result.transaction('assets', 'readonly').objectStore('assets').get(name);
          q.onsuccess = function () { res(q.result); };
        };
      });
      const buf = await rec.blob.arrayBuffer();
      const bytes = new Uint8Array(buf);
      let bin = '';
      for (let i = 0; i < bytes.length; i += 0x8000) {
        bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
      }
      const b64 = btoa(bin);
      window.__gh.files[plan.branch + '|blogs/assets/' + name] = { content: b64, sha: 'asset1' };
      return { branch: plan.branch, len: b64.length };
    }""", name)
    check("pre-seeded mock asset content for the same-content check",
          seeded["len"] > 100, repr(seeded))
    pg.click(".cta")
    wait_js(pg, "document.querySelector('#sheet-export').classList.contains('is-open')")
    wait_js(pg, "!document.querySelector('#btn-publish').disabled")
    pg.click("#btn-publish")
    wait_js(pg, "!!document.querySelector('#pub-out .pub-box.is-ok')", 20000)
    puts = [c for c in pg.evaluate("window.__gh.calls.map(function (c) { return { m: c.method, p: c.path }; })")
            if c["m"] == "PUT"]
    check("unchanged existing asset is not re-uploaded",
          not any("blogs/assets/" in c["p"] for c in puts)
          and any(c["p"].endswith(".md") for c in puts), repr([c["p"] for c in puts]))
    no_errors("publish same-content", errs)
    ctx.close()


def vault_narrow_checks(b):
    print("\n== vault hiding + 360px layout ==")
    ctx, pg, errs = new_page(b)
    pg.evaluate("document.documentElement.classList.add('is-vault')")
    check("vault hides the [data-k=img] toolbar entry",
          pg.evaluate("getComputedStyle(document.querySelector('[data-k=img]')).display") == "none")
    pg.evaluate("window.__pilogWrite.images.open()")
    pg.wait_for_timeout(250)
    check("vault images.open() shows a toast and never opens the sheet",
          "私密库" in pg.inner_text("#toast")
          and not pg.evaluate("document.querySelector('#sheet-images').classList.contains('is-open')"),
          f"{pg.inner_text('#toast')}")
    no_errors("vault", errs)
    ctx.close()

    ctx, pg, errs = new_page(b, width=360)
    pg.evaluate("window.__pilogWrite.images.open()")
    wait_js(pg, "document.querySelector('#sheet-images').classList.contains('is-open')")
    import_images(pg, IMG / "plain.png")
    wait_js(pg, "!!window.__pilogWrite.images.editor()")
    pg.wait_for_timeout(300)
    geom = pg.evaluate("""() => {
      const s = document.querySelector('#sheet-images');
      return { sw: s.scrollWidth, cw: s.clientWidth,
               open: s.classList.contains('is-open'),
               editor: !document.querySelector('#img-editor').hidden };
    }""")
    check("360px: image sheet does not overflow in the editor view",
          geom["sw"] <= geom["cw"] + 1 and geom["editor"] is True, repr(geom))
    pg.click("#img-back")
    pg.wait_for_timeout(250)
    geom = pg.evaluate("() => { const s = document.querySelector('#sheet-images'); return { sw: s.scrollWidth, cw: s.clientWidth }; }")
    check("360px: image sheet does not overflow in the gallery view",
          geom["sw"] <= geom["cw"] + 1, repr(geom))
    no_errors("360px", errs)
    ctx.close()


# ---------------------------------------------------------------------------
# fixtures + main
# ---------------------------------------------------------------------------


def make_images():
    shutil.rmtree(TMP, ignore_errors=True)
    IMG.mkdir(parents=True)

    def gradient(path, w, h, fmt="PNG"):
        im = Image.new("RGB", (w, h), (32, 48, 96))
        px = im.load()
        for x in range(w):
            for y in range(h):
                px[x, y] = ((x * 7) % 256, (y * 11) % 256, (x + y) % 256)
        im.save(path, fmt, quality=90)

    gradient(IMG / "plain.png", 320, 240)
    gradient(IMG / "big.png", 2400, 1200)
    gradient(IMG / "edit.png", 400, 300)
    gradient(IMG / "extra.png", 200, 150)
    gradient(IMG / "photo.jpg", 300, 200, fmt="JPEG")


def main() -> None:
    make_images()
    with sync_playwright() as p:
        b = p.chromium.launch(downloads_path=str(TMP))
        try:
            entry_checks(b)
            api_checks(b)
            import_checks(b)
            edit_checks(b)
            crop_checks(b)
            rename_checks(b)
            delete_checks(b)
            insert_preview_export_checks(b)
            publish_checks(b)
            vault_narrow_checks(b)
        finally:
            b.close()
    shutil.rmtree(TMP, ignore_errors=True)
    srv.shutdown()
    print("ALL PASS" if ok else "SOME FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
