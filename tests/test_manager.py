#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression checks for the WYSIWYG local manager (needs a fresh blogs/)."""

from __future__ import annotations

import json
import pathlib
import sys
import threading

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
STRESS = ROOT / ".stress"

from util import block_external  # noqa: E402

import serve  # noqa: E402

srv = serve.ThreadingHTTPServer(("127.0.0.1", 8195), serve.Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()

from playwright.sync_api import sync_playwright  # noqa: E402

ok = True


def check(name, cond, detail=""):
    global ok
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + ("" if cond else f" — {detail}"))
    ok = ok and cond


def main() -> None:
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1440, "height": 1000})
        block_external(pg)
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("dialog", lambda d: d.accept())
        pg.goto("http://127.0.0.1:8195/manager", wait_until="networkidle")
        # wait until the manager has actually loaded posts/preview (with many
        # posts this can take several seconds)
        pg.wait_for_function(
            "document.querySelector('#pv-title') && "
            "document.querySelector('#pv-title').textContent.length > 0",
            timeout=30000,
        )

        check("logo preview uses assets path (not blogs/)",
              "blogs/assets" not in pg.locator("#pv-logo-img").get_attribute("src"))

        # logo upload -> preview loads
        with pg.expect_file_chooser() as fc:
            pg.click("#pv-logo")
        fc.value.set_files(str(ROOT / "blogs" / "assets" / "cover-pixel.png"))
        pg.wait_for_timeout(700)
        check("logo upload updates preview",
              pg.evaluate("() => { const i = document.querySelector('#pv-logo-img'); "
                          "return i.complete && i.naturalWidth > 0; }"))

        # tree preview
        pg.click('.pv-tab[data-pvview="tree"]')
        pg.wait_for_timeout(400)
        check("tree preview rows", pg.locator("#pv-tree .file").count() >= 5)

        # graph preview
        pg.click('.pv-tab[data-pvview="graph"]')
        pg.wait_for_function(
            "document.querySelectorAll('#pv-pane-graph .graph-node').length >= 8",
            timeout=40000,
        )
        check("graph preview renders", pg.locator("#pv-pane-graph .graph-node").count() >= 8)

        # drawer open/close
        pg.click("#btn-log")
        pg.wait_for_timeout(300)
        pg.click("#drawer-mask", position={"x": 80, "y": 80})
        pg.wait_for_timeout(300)
        check("drawer closes", not pg.locator("#drawer").evaluate(
            "el => el.classList.contains('open')"))

        # ctrl+s saves config
        pg.click('.tab[data-tab="config"]')
        pg.fill("#cfg-grid .cfg-panel .body input[type=text]", "TEMP TITLE")
        pg.keyboard.press("Control+s")
        pg.wait_for_timeout(600)
        cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        check("ctrl+s saves config", cfg["site"]["title"] == "TEMP TITLE")
        pg.click("#btn-undo")
        pg.wait_for_timeout(500)

        # config reset restores defaults
        pg.fill("#cfg-grid .cfg-panel .body input[type=text]", "TEMP TITLE")
        pg.click("#cfg-save")
        pg.wait_for_timeout(500)
        pg.click("#cfg-reset")
        pg.wait_for_timeout(500)
        cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        check("config reset restores defaults", cfg["site"]["title"] == "MEREDITH'S LOG")
        pg.click("#btn-undo")
        pg.wait_for_timeout(400)
        pg.click("#btn-undo")
        pg.wait_for_timeout(400)

        # default view setting: config UI -> config.json -> homepage
        pg.click('.tab[data-tab="config"]')
        pg.select_option("#cfg-grid select", "tree")
        pg.click("#cfg-save")
        pg.wait_for_timeout(500)
        cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        check("default view saved to config", cfg["site"]["default_view"] == "tree")
        pg.click("#btn-rebuild")
        # wait for the rebuild to start and finish (can take ~6s+ with many posts)
        pg.wait_for_function(
            "document.querySelector('#btn-rebuild').disabled", timeout=10000
        )
        pg.wait_for_function(
            "!document.querySelector('#btn-rebuild').disabled", timeout=60000
        )
        pg.goto("http://127.0.0.1:8195/", wait_until="networkidle")
        pg.wait_for_selector("#view-tree", state="visible", timeout=15000)
        check("homepage honors default view",
              pg.locator("#view-tree").evaluate("el => !el.hidden"))
        pg.goto("http://127.0.0.1:8195/manager", wait_until="networkidle")
        pg.wait_for_timeout(600)

        # nav child add / delete with confirm
        pg.click('.tab[data-tab="preview"]')
        pg.hover(".pv-nav-item")
        pg.click('.pv-nav-item [data-act="child"]')
        pg.wait_for_timeout(500)
        nav = (ROOT / "blogs" / "nav.md").read_text(encoding="utf-8")
        check("nav child added", "子项" in nav)
        pg.hover(".pv-nav-item")
        pg.click('.pv-nav-item [data-act="child-del"]')
        pg.wait_for_timeout(500)
        nav = (ROOT / "blogs" / "nav.md").read_text(encoding="utf-8")
        check("nav child deleted after confirm", "子项" not in nav)

        # markdown import via file input (analysis dialog -> confirm)
        STRESS.mkdir(exist_ok=True)
        sample = STRESS / "import-sample.md"
        sample.write_text(
            "# 导入样例\n\n![[missing-img.png]]\n\n参考 [[pixel-blog]] 和 [[不存在文章]]。\n",
            encoding="utf-8",
        )
        pg.click('.tab[data-tab="files"]')
        pg.click('.folder-item[data-path=""]')
        pg.wait_for_timeout(400)
        pg.set_input_files("#file-input", str(sample))
        pg.wait_for_timeout(1200)
        check("import analysis dialog", pg.locator("#import-modal").evaluate(
            "el => el.classList.contains('open')"))
        text = pg.locator("#import-body").inner_text()
        check("analysis flags missing refs", "图片缺失" in text and "引用的文章未找到" in text)
        pg.click("#import-confirm")
        pg.wait_for_timeout(1000)
        imported = ROOT / "blogs" / "import-sample.md"
        check("markdown imported", imported.exists())
        if imported.exists():
            content = imported.read_text(encoding="utf-8")
            check("imported content kept", "导入样例" in content and "missing-img" in content)

        check("no page errors", not errs, "; ".join(errs))
        b.close()

    # 404 page: custom content + countdown + auto redirect home
    with sync_playwright() as p2:
        b2 = p2.chromium.launch()
        pg2 = b2.new_page(viewport={"width": 1200, "height": 800})
        block_external(pg2)
        resp = pg2.goto("http://127.0.0.1:8195/definitely-missing.html",
                        wait_until="domcontentloaded")
        check("missing page returns 404", resp.status == 404)
        pg2.wait_for_timeout(300)
        check("custom 404 page shown", pg2.locator(".notfound-art").count() == 1)
        check("404 countdown present", "自动返回首页" in pg2.locator("#notfound-count").inner_text())
        pg2.wait_for_timeout(5600)
        check("404 auto redirects home",
              pg2.url.replace("/index.html", "").rstrip("/").endswith("8195"))
        b2.close()

    # cleanup: undo remaining ops + remove leftovers
    import urllib.request

    while True:
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:8195/api/undo", data=b"", method="POST")
            resp = json.loads(urllib.request.urlopen(req).read())
            if not resp.get("files"):
                break
        except Exception:
            break
    for p in [ROOT / "blogs" / "assets" / "logo.png", imported]:
        if p.exists():
            p.unlink()
    import shutil

    if STRESS.exists():
        shutil.rmtree(STRESS)
    srv.shutdown()

    if not ok:
        sys.exit(1)
    print("all manager checks passed")


if __name__ == "__main__":
    main()
