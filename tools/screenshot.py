#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Take design screenshots of the built site (dev tool)."""

from __future__ import annotations

import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "output" / "playwright"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "site"), **kwargs)


def main() -> None:
    site = ROOT / "site"
    if not (site / "index.html").exists():
        print("build first: python build.py")
        sys.exit(1)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    server = ThreadingHTTPServer(("127.0.0.1", 8123), QuietHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:8123"

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()

        def snap(page, name, full=False):
            page.wait_for_timeout(700)
            path = OUT_DIR / name
            page.screenshot(path=str(path), full_page=full)
            print("saved", path)

        # desktop cards
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.goto(base + "/", wait_until="networkidle")
        snap(page, "01-cards.png")

        # tree view
        page.click('[data-view="tree"]')
        snap(page, "02-tree.png")

        # graph view
        page.click('[data-view="graph"]')
        page.wait_for_timeout(2200)
        snap(page, "03-graph.png")

        # graph view without snake
        page.click("#graph-snake")
        page.wait_for_timeout(400)
        snap(page, "07-graph-no-snake.png")
        page.click("#graph-snake")

        # dino widget open
        page.click(".dino-toggle")
        page.wait_for_timeout(1200)
        dino_frame = next(
            f for f in page.frames if f.url.rstrip("/").endswith("dino/index.html")
        )
        dino_frame.click("#runner-canvas", position={"x": 300, "y": 100})
        page.keyboard.press(" ")
        page.wait_for_timeout(1600)
        snap(page, "04-dino.png")
        page.close()

        # post page
        page2 = browser.new_page(viewport={"width": 1440, "height": 1000})
        page2.goto(base + "/posts/tech/pixel-blog.html", wait_until="networkidle")
        snap(page2, "05-post.png", full=True)
        page2.close()

        # mobile cards
        page3 = browser.new_page(viewport={"width": 390, "height": 844})
        page3.goto(base + "/", wait_until="networkidle")
        snap(page3, "06-mobile.png")
        page3.close()

        browser.close()
    server.shutdown()


if __name__ == "__main__":
    main()
