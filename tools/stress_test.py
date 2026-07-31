#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stress test: 100 posts across all three views (build + render metrics)."""

from __future__ import annotations

import shutil
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
STRESS = ROOT / ".stress"
BLOGS = STRESS / "blogs"
OUT = STRESS / "site"


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(OUT), **kwargs)


TAGS = ["pilog", "markdown", "obsidian", "css", "graph", "snake", "dino", "rss"]


def make_post(i: int) -> str:
    folder = f"posts/topic{(i % 10) + 1:02d}"
    stem = f"post-{i:03d}"
    title = f"文章 {i:03d}：一篇用于压力测试的相对较长的示例标题"
    tags = ", ".join([TAGS[i % len(TAGS)], TAGS[(i + 3) % len(TAGS)]])
    preview = "手动预览：这篇是压力测试文章，用来检验大内容量下各视图的表现。"
    preview_image = "assets/cover-pixel.png" if i % 4 == 0 else None
    extra_fm = f"preview_image: {preview_image}\n" if preview_image else ""
    link = ""
    if i % 3 == 0:
        link = f"\n相关阅读：[[post-{(i + 1) % 100:03d}]]。\n"
    return f"""---
title: {title}
date: 2026-01-{(i % 28) + 1:02d}
tags: [{tags}]
preview: {preview}
{extra_fm}---

# {title}

这是第 {i} 篇文章的正文段落，用来模拟真实文章的正文长度，并验证预览摘要的自动提取是否稳定。

## 小节

- 列表项一：介绍背景
- 列表项二：说明细节
- 列表项三：总结结论

```python
def greet(name: str) -> str:
    return f"hello, {{name}}"
```

> 一段引用文字，增加正文的多样性。
{link}
"""


def build_corpus() -> None:
    if STRESS.exists():
        shutil.rmtree(STRESS)
    (BLOGS / "assets").mkdir(parents=True)
    (BLOGS / "posts").mkdir()
    (BLOGS / "nav.md").write_text(
        "# 导航\n\n- [首页](/) \n- [关于](about.md)\n",
        encoding="utf-8",
    )
    (BLOGS / "about.md").write_text(
        "---\ntitle: 关于\ndate: 2026-01-01\n---\n\n# 关于\n\n压力测试用。\n",
        encoding="utf-8",
    )
    cover = ROOT / "blogs" / "assets" / "cover-pixel.png"
    if cover.exists():
        shutil.copy2(cover, BLOGS / "assets" / "cover-pixel.png")
    for i in range(100):
        folder = BLOGS / f"posts/topic{(i % 10) + 1:02d}"
        folder.mkdir(exist_ok=True)
        (folder / f"post-{i:03d}.md").write_text(make_post(i), encoding="utf-8")


def main() -> None:
    print("generating 100-post corpus…")
    build_corpus()

    from build import build_site

    t0 = time.perf_counter()
    build_site(config_path=ROOT / "config.json", blog_dir=str(BLOGS), out_dir=str(OUT))
    build_s = time.perf_counter() - t0
    print(f"build time: {build_s:.2f}s")

    total = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file())
    index_size = (OUT / "index.html").stat().st_size
    print(f"site size: {total / 1024:.0f} KB, index.html: {index_size / 1024:.0f} KB")

    srv = ThreadingHTTPServer(("127.0.0.1", 8170), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:8170"

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        t0 = time.perf_counter()
        page.goto(base + "/", wait_until="load")
        load_s = time.perf_counter() - t0
        cards = page.locator(".card").count()
        dom = page.evaluate("document.querySelectorAll('*').length")
        print(f"cards view: {cards} cards, {dom} DOM nodes, load {load_s:.2f}s")
        pager_info = page.locator(".pager-info").inner_text() if page.locator(".pager").count() else "no pager"
        print("cards pager:", pager_info)
        first_card = page.locator(".card-title").first.inner_text()
        page.goto(base + "/page/2.html", wait_until="load")
        second_first = page.locator(".card-title").first.inner_text()
        print(f"page2 first card different: {first_card[:20]} != {second_first[:20]} "
              f"-> {first_card != second_first}")
        page.goto(base + "/", wait_until="load")

        page.click('[data-view="tree"]')
        files = page.locator(".tree-file").count()
        collapsed_dirs = page.locator(".tree-folder:not(.is-open)").count()
        print(f"tree default collapsed folders: {collapsed_dirs}")
        t0 = time.perf_counter()
        page.click("#tree-expand")
        expand_s = time.perf_counter() - t0
        print(f"tree view: {files} files, expand-all {expand_s * 1000:.0f}ms")

        page.evaluate("window.__g0 = performance.now()")
        page.click('[data-view="graph"]')
        page.wait_for_function(
            "document.querySelector('#graph-stats').textContent.includes('篇文章')")
        warm_s = page.evaluate("performance.now() - window.__g0")
        nodes = page.locator(".graph-node").count()
        links = page.locator(".graph-link").count()
        refs = page.locator(".graph-link.ref").count()
        zoom = page.evaluate("""
            () => {
              const m = document.querySelector('#graph-svg g')
                .getAttribute('transform').match(/scale\\(([\\d.]+)\\)/);
              return m ? parseFloat(m[1]) : 1;
            }
        """)
        print(f"graph view: {nodes} nodes, {links} links ({refs} ref), "
              f"layout+warmup {warm_s:.0f}ms, fit zoom {zoom:.2f}")
        viewport = page.evaluate("""
            () => {
              const wrap = document.querySelector('#graph-wrap').getBoundingClientRect();
              const vp = document.querySelector('#graph-svg g').getAttribute('transform');
              const m = vp.match(/translate\\(([\\d.-]+),([\\d.-]+)\\) scale\\(([\\d.]+)\\)/);
              const ox = parseFloat(m[1]), oy = parseFloat(m[2]), z = parseFloat(m[3]);
              const gs = [...document.querySelectorAll('.graph-node')].map(g => {
                const r = g.querySelector(':scope > rect');
                const t = g.getAttribute('transform').match(
                  /translate\\(([\\d.-]+),([\\d.-]+)\\)/);
                return {x: parseFloat(t[1]), y: parseFloat(t[2]),
                        w: parseFloat(r.getAttribute('width')),
                        h: parseFloat(r.getAttribute('height'))};
              });
              const visible = gs.filter(n => {
                const sx = ox + n.x * z, sy = oy + n.y * z;
                return sx + n.w * z > 0 && sx < wrap.width &&
                       sy + n.h * z > 0 && sy < wrap.height;
              }).length;
              const xs = gs.map(n => n.x), ys = gs.map(n => n.y);
              return {visible: visible + "/" + gs.length,
                      spanX: Math.round(Math.max(...xs) - Math.min(...xs)),
                      spanY: Math.round(Math.max(...ys) - Math.min(...ys))};
            }
        """)
        print("graph initial viewport:", viewport)
        page.wait_for_timeout(1000)
        page.screenshot(path=str(ROOT / "output" / "playwright" / "09-stress-graph.png"))

        fps = page.evaluate("""
            () => new Promise(res => {
              let n = 0;
              const t0 = performance.now();
              function tick() {
                n++;
                const dt = performance.now() - t0;
                if (dt >= 1500) res(Math.round(n * 1000 / dt));
                else requestAnimationFrame(tick);
              }
              requestAnimationFrame(tick);
            })
        """)
        print(f"graph fps while snake runs: {fps}")

        overlap = page.evaluate("""
            () => {
              const gs = [...document.querySelectorAll('.graph-node')].map(g => {
                const r = g.querySelector(':scope > rect');
                const t = g.getAttribute('transform').match(
                  /translate\\(([\\d.-]+),([\\d.-]+)\\)/);
                const w = parseFloat(r.getAttribute('width'));
                const h = parseFloat(r.getAttribute('height'));
                return {x: parseFloat(t[1]), y: parseFloat(t[2]), w, h};
              });
              let pairs = 0, hits = 0;
              for (let i = 0; i < gs.length; i++) {
                for (let j = i + 1; j < gs.length; j++) {
                  pairs++;
                  const a = gs[i], b = gs[j];
                  if (Math.abs(a.x - b.x) * 2 < a.w + b.w &&
                      Math.abs(a.y - b.y) * 2 < a.h + b.h) hits++;
                }
              }
              return {pairs, hits};
            }
        """)
        print(f"graph node overlap: {overlap['hits']}/{overlap['pairs']} pairs "
              f"({100 * overlap['hits'] / max(overlap['pairs'], 1):.1f}%)")

        stats = page.locator("#graph-stats").inner_text()
        print("graph stats:", stats)
        print("graph default collapse:", "已折叠" in stats)

        # search over 100 posts
        page.click('[data-view="cards"]')
        page.fill("#search-input", "压力测试")
        page.wait_for_timeout(900)
        found = page.locator(".search-item").count()
        print("search results for 压力测试:", found)
        page.fill("#search-input", "")
        print("page errors:", errors if errors else "none")
        browser.close()
    srv.shutdown()

    shutil.rmtree(STRESS)
    print("cleaned up .stress/")


if __name__ == "__main__":
    main()
