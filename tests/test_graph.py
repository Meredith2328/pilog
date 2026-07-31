#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression tests for the graph view (nodes, root, snake)."""

from __future__ import annotations

import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from util import block_external

ROOT = Path(__file__).resolve().parents[1]
PORT = 8140


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "site"), **kwargs)


def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + ("" if cond else f" — {detail}"))
    return cond


def main() -> None:
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{PORT}"
    failures = []

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        block_external(page)
        page.on("pageerror", lambda e: failures.append(str(e)))
        page.goto(base + "/", wait_until="networkidle")
        page.click('[data-view="graph"]')
        page.wait_for_timeout(2400)

        ok = True
        # 1. no JS errors
        ok &= check("no page errors", not failures, "; ".join(failures))

        # 1b. graph area must not select text while dragging
        user_select = page.evaluate(
            "getComputedStyle(document.querySelector('.graph-wrap')).userSelect")
        ok &= check("graph wrap blocks text selection", user_select == "none", user_select)
        center = page.evaluate("""
            () => {
              const g = document.querySelector('.graph-node[data-id^="posts/"]');
              const r = g.querySelector(':scope > rect').getBoundingClientRect();
              return {x: r.x + r.width / 2, y: r.y + r.height / 2};
            }
        """)
        page.mouse.move(center["x"], center["y"])
        page.mouse.down()
        page.mouse.move(center["x"] + 90, center["y"] + 40, steps=5)
        page.mouse.up()
        sel = page.evaluate("window.getSelection().toString().length")
        ok &= check("drag leaves no text selected", sel == 0, f"selected={sel} chars")

        # 2. bigger nodes: post rects wider than before (>110px)
        widths = page.eval_on_selector_all(
            ".graph-node[data-id^='posts/'] > rect",
            "els => els.map(e => parseFloat(e.getAttribute('width')))")
        ok &= check("post/dir nodes bigger", widths and all(w >= 110 for w in widths),
                    str(widths)[:120])

        # 3. long title truncated with '...'
        labels = page.eval_on_selector_all(".graph-node text", "els => els.map(e => e.textContent)")
        truncated = [t for t in labels if t.endswith("...")]
        ok &= check("long title truncated with ...", len(truncated) >= 1, str(truncated)[:120])

        # 4. root node is white with ink border (no solid black block)
        root_style = page.evaluate("""
            () => {
              const g = document.querySelector('.graph-node[data-id=""]');
              if (!g) return null;
              const r = g.querySelector(':scope > rect');
              return r ? {fill: r.getAttribute('fill'), stroke: r.getAttribute('stroke')} : null;
            }
        """)
        ok &= check(
            "root node not black",
            root_style and root_style["fill"] == "#ffffff" and root_style["stroke"] == "#3c4043",
            str(root_style))

        # 5. snake head moves over time
        def head_pos():
            return page.evaluate("""
                () => {
                  const r = document.querySelector('.graph-snake rect');
                  if (!r) return null;
                  const b = r.getBoundingClientRect();
                  return [Math.round(b.x), Math.round(b.y)];
                }
            """)

        h1 = head_pos()
        page.wait_for_timeout(700)
        h2 = head_pos()
        ok &= check("snake is moving", bool(h1 and h2 and h1 != h2), f"{h1} -> {h2}")

        # 6. snake keeps clearance from nodes (sample head rects)
        def nearest_gap():
            return page.evaluate("""
                () => {
                  const pts = [...document.querySelectorAll('.graph-snake rect')].map(r => {
                    const b = r.getBoundingClientRect();
                    return {x: b.x + b.width/2, y: b.y + b.height/2};
                  });
                  const nodes = [...document.querySelectorAll('.graph-node')].map(g => {
                    const r = g.querySelector('rect').getBoundingClientRect();
                    return {x: r.x + r.width/2, y: r.y + r.height/2, w: r.width, h: r.height};
                  });
                  let min = Infinity;
                  pts.forEach(p => nodes.forEach(n => {
                    const dx = Math.max(Math.abs(p.x - n.x) - n.w/2, 0);
                    const dy = Math.max(Math.abs(p.y - n.y) - n.h/2, 0);
                    min = Math.min(min, Math.hypot(dx, dy));
                  }));
                  return Math.round(min);
                }
            """)
        gap = nearest_gap()
        ok &= check("snake keeps gap from nodes", gap is not None and gap >= 8, f"gap={gap}px")

        # 7. toggle off/on
        page.click("#graph-snake")
        page.wait_for_timeout(300)
        off_visible = page.locator(".graph-snake rect").count()
        ok &= check("snake toggle hides", off_visible == 0, str(off_visible))
        page.click("#graph-snake")
        page.wait_for_timeout(700)
        on_visible = page.locator(".graph-snake rect").count()
        ok &= check("snake toggle shows", on_visible >= 5, str(on_visible))

        # 8. single-click a dir node toggles its subtree
        total_before = page.locator(".graph-node").count()
        center = page.evaluate("""
            () => {
              const g = document.querySelector('.graph-node[data-id="posts"]');
              const r = g.querySelector(':scope > rect').getBoundingClientRect();
              return {x: r.x + r.width / 2, y: r.y + r.height / 2};
            }
        """)
        page.mouse.click(center["x"], center["y"])
        page.wait_for_timeout(400)
        after_collapse = page.locator(".graph-node").count()
        ok &= check("dir single-click collapses", after_collapse < total_before,
                    f"{total_before} -> {after_collapse}")
        page.mouse.click(center["x"], center["y"])
        page.wait_for_timeout(400)
        ok &= check("dir single-click expands",
                    page.locator(".graph-node").count() == total_before)

        # 9. drag a node near the snake does not crash it and it keeps moving
        page.evaluate("""
            () => {
              const n = document.querySelector('.graph-node[data-id^="posts"]');
              const r = n.querySelector('rect').getBoundingClientRect();
              const head = document.querySelector('.graph-snake rect').getBoundingClientRect();
              n.dispatchEvent(new PointerEvent('pointerdown', {
                clientX: r.x + 10, clientY: r.y + 10, bubbles: true, pointerId: 1
              }));
              // move node onto the snake head
              document.querySelector('svg').dispatchEvent(new PointerEvent('pointermove', {
                clientX: head.x + 4, clientY: head.y + 4, bubbles: true, pointerId: 1
              }));
              document.querySelector('svg').dispatchEvent(new PointerEvent('pointerup', {
                clientX: head.x + 4, clientY: head.y + 4, bubbles: true, pointerId: 1
              }));
            }
        """)
        page.wait_for_timeout(1200)
        h3 = head_pos()
        page_errors_after = len(failures)
        ok &= check("snake survives node drop-in", h3 is not None and page_errors_after == len(failures), f"head={h3}")
        gap2 = nearest_gap()
        ok &= check("snake escaped dragged node", gap2 is not None and gap2 >= 8, f"gap={gap2}px")

        browser.close()
    srv.shutdown()

    print()
    if not ok:
        sys.exit(1)
    print("all graph checks passed")


if __name__ == "__main__":
    main()
