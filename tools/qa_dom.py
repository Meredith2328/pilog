#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DOM/layout QA for the built site."""

from __future__ import annotations

import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image, ImageStat

ROOT = Path(__file__).resolve().parents[1]
PORT = 8132


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "site"), **kwargs)


def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + ("" if cond else f" — {detail}"))
    return cond


def img_stats(path: Path):
    img = Image.open(path).convert("L")
    stat = ImageStat.Stat(img)
    return round(stat.stddev[0], 1), img.size


def main() -> None:
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{PORT}"
    failures = []

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda e: failures.append("pageerror: " + str(e)))
        page.on("console", lambda m: failures.append(m.text) if m.type == "error" else None)
        page.goto(base + "/", wait_until="networkidle")

        ok = True
        ok &= check("card count >= 5", page.locator(".card").count() >= 5)
        first_title = page.locator(".card-title").first.inner_text()
        ok &= check("pinned post first", "pilog" in first_title and "像素" in first_title,
                    first_title[:30])
        ok &= check("pin badge shown", page.locator(".pin-badge").count() >= 1)
        ok &= check("highlight card shown", page.locator(".card.is-highlight").count() >= 1)
        body_font = page.evaluate("getComputedStyle(document.body).fontFamily")
        ok &= check("sans font stack", "Inter" in body_font or "Segoe" in body_font, body_font[:60])
        card_h = page.locator(".card").first.bounding_box()["height"]
        ok &= check("card height reasonable", 150 < card_h < 320, str(card_h))
        thumb_w = page.locator(".card-thumb img").first.bounding_box()["width"]
        ok &= check("thumb column ~132px", abs(thumb_w - 132) < 6, str(thumb_w))
        pre = page.locator(".card-preview").first.inner_text()
        ok &= check("manual preview shown", "轻量的静态博客框架" in pre, pre[:40])
        ok &= check("tag chips on cards", page.locator(".card .tag-chip").count() >= 4)

        # tree view
        page.click('[data-view="tree"]')
        ok &= check("tree files >= 5", page.locator(".tree-file").count() >= 5)
        ok &= check("tree folders >= 2", page.locator(".tree-folder").count() >= 2)
        ok &= check("tree highlight row", page.locator(".tree-file.is-highlight").count() >= 1)
        page.click("#tree-expand")
        page.click("#tree-collapse")
        ok &= check("tree collapse hides children", page.locator(".tree-folder").first.evaluate(
            "el => !el.classList.contains('is-open')"))

        # graph view
        page.click('[data-view="graph"]')
        page.wait_for_timeout(2000)
        node_count = page.locator(".graph-node").count()
        link_count = page.locator(".graph-link").count()
        ref_count = page.locator(".graph-link.ref").count()
        ok &= check("graph nodes >= 8", node_count >= 8, str(node_count))
        ok &= check("graph ref edges present", ref_count >= 2, str(ref_count))
        ok &= check("graph stats text", "篇文章" in page.locator("#graph-stats").inner_text())
        ok &= check("legend present", page.locator(".graph-legend .legend-item").count() == 5)
        ok &= check("graph highlight node",
                    page.locator('.graph-node rect[stroke="#fbbc04"]').count() >= 1)
        page.click("#graph-collapse-all")
        page.wait_for_timeout(400)
        ok &= check("graph collapse-all works",
                    page.locator(".graph-node").count() < node_count)
        page.click("#graph-expand-all")
        page.wait_for_timeout(400)
        ok &= check("graph expand-all works",
                    page.locator(".graph-node").count() == node_count)

        # search
        page.click('[data-view="cards"]')
        page.fill("#search-input", "速查")
        page.wait_for_timeout(700)
        ok &= check("search finds results", page.locator(".search-item").count() >= 1)
        page.fill("#search-input", "")

        # post page
        page.goto(base + "/posts/tech/pixel-blog.html", wait_until="networkidle")
        ok &= check("pygments highlight", page.locator(".highlight").count() >= 3)
        ok &= check("code token spans", page.locator(".highlight span.k, .highlight span.kd").count() >= 2)
        ok &= check("heading ids", page.locator("h2[id]").count() >= 3)
        ok &= check("wiki image resolved", page.locator('.post-body img[src*="cover-pixel"]').count() >= 1)
        ok &= check("dino iframe present", page.locator(".dino-frame").count() == 1)

        # dino widget
        page.click(".dino-toggle")
        page.wait_for_timeout(1200)
        iframe = page.frame_locator(".dino-frame")
        ok &= check("dino iframe loaded", iframe.locator("canvas").count() >= 1)

        # markdown cheatsheet: footnotes + task list + blockquote
        page.goto(base + "/posts/tech/markdown-cheatsheet.html", wait_until="networkidle")
        ok &= check("blockquote", page.locator("blockquote").count() >= 1)
        ok &= check("footnotes", page.locator(".footnote").count() >= 1)
        ok &= check("table rendered", page.locator("table").count() >= 1)
        ok &= check("task list", page.locator('li input[type="checkbox"]').count() >= 2)
        ok &= check("cross ref link to pixel-blog", page.locator('a[href*="pixel-blog"]').count() >= 1)

        # screenshots sanity
        for name in ["01-cards.png", "02-tree.png", "03-graph.png", "05-post.png", "06-mobile.png"]:
            path = ROOT / "output" / "playwright" / name
            if path.exists():
                std, size = img_stats(path)
                ok &= check(f"screenshot {name} not blank", std > 12, f"std={std} {size}")

        # view default behavior: returning home shows cards
        page.goto(base + "/posts/tech/pixel-blog.html", wait_until="networkidle")
        page.click(".back-link")
        page.wait_for_load_state("networkidle")
        ok &= check("home defaults to cards", page.locator("#view-cards").evaluate("el => !el.hidden"))

        # explicit deep links still work
        page.goto(base + "/index.html#view-tree", wait_until="networkidle")
        ok &= check("deep link #view-tree works", page.locator("#view-tree").evaluate("el => !el.hidden"))
        page.goto(base + "/index.html#view-graph", wait_until="networkidle")
        page.wait_for_timeout(1800)
        ok &= check("deep link #view-graph works", page.locator("#view-graph").evaluate("el => !el.hidden"))

        # stale localStorage must not override the default
        page.evaluate("localStorage.setItem('pilog.view', 'graph')")
        page.goto(base + "/index.html", wait_until="networkidle")
        ok &= check("home ignores stored view", page.locator("#view-cards").evaluate("el => !el.hidden"))

        browser.close()
    srv.shutdown()

    print()
    if failures:
        print("JS issues:")
        for f in failures[:10]:
            print("  -", f)
        ok = False
    if not ok:
        sys.exit(1)
    print("all QA checks passed")


if __name__ == "__main__":
    main()
