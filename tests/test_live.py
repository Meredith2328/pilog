import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
BASE = cfg["site"].get("site_url", "").rstrip("/")

ok = True


def goto_retry(pg, url, wait="networkidle", attempts=4, delay=4):
    import time

    for i in range(attempts):
        try:
            return pg.goto(url, wait_until=wait)
        except Exception:
            if i < attempts - 1:
                time.sleep(delay)
    return pg.goto(url, wait_until=wait)


def check(name, cond, detail=""):
    global ok
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + ("" if cond else f" — {detail}"))
    ok = ok and cond


with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1440, "height": 1000})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))

    # home
    resp = goto_retry(pg, BASE + "/")
    check("home 200", resp.status == 200)
    check("home title", "MEREDITH" in pg.title())
    check("cards render", pg.locator(".card").count() >= 5)
    check("banner svg loads", pg.locator(".header-banner").evaluate(
        "el => getComputedStyle(el).backgroundImage.includes('banner-default.svg')"))
    check("css loads", pg.locator("link[href$='style.css']").count() == 1)
    check("favicon loads", pg.locator("link[rel=icon]").get_attribute("href") == "favicon.png")

    nav_home = pg.locator(".site-nav a", has_text="首页").get_attribute("href")
    check("nav home is page-relative", nav_home and not nav_home.startswith("/"), nav_home)

    # post page + back link (the classic subdirectory pitfall)
    pg.click(".card-link")
    pg.wait_for_load_state("networkidle")
    check("post URL stays under site root", pg.url.startswith(BASE + "/posts/"))
    check("post css relative", pg.locator("link[href$='style.css']").get_attribute("href")
          == "../../css/style.css")
    pg.click(".back-link")
    pg.wait_for_load_state("networkidle")
    check("back link returns to /pilog (not root)",
          pg.url.replace("/index.html", "").rstrip("/") == BASE)

    # nav 首页 from a subpage
    pg.click(".card-link")
    pg.wait_for_load_state("networkidle")
    pg.locator(".site-nav a", has_text="首页").click()
    pg.wait_for_load_state("networkidle")
    check("nav home from subpage -> site root",
          pg.url.replace("/index.html", "").rstrip("/") == BASE)

    # views
    pg.click('[data-view="tree"]')
    check("tree renders", pg.locator(".tree-file").count() >= 5)
    pg.click('[data-view="graph"]')
    pg.wait_for_timeout(2500)
    check("graph renders", pg.locator(".graph-node").count() >= 8)

    # dino page + widget
    pg.goto(BASE + "/dino/index.html", wait_until="networkidle")
    check("dino page loads", pg.locator("#runner-canvas").count() == 1)
    pg.goto(BASE + "/", wait_until="networkidle")
    pg.click(".dino-toggle")
    pg.wait_for_timeout(1500)
    check("dino widget works", pg.frame_locator(".dino-frame").locator("canvas").count() == 1)

    # rss
    resp = pg.request.get(BASE + "/rss.xml")
    check("rss 200", resp.status == 200)

    # giscus config present on post pages
    pg.goto(BASE + "/posts/tech/pixel-blog.html", wait_until="domcontentloaded")
    giscus = pg.locator('script[src*="giscus.app/client.js"]')
    check("giscus script present", giscus.count() == 1)
    if giscus.count():
        giscus_repo = cfg.get("giscus", {}).get("repo", "")
        check("giscus repo matches", giscus.get_attribute("data-repo") == giscus_repo)
        check("giscus has ids", bool(giscus.get_attribute("data-repo-id"))
              and bool(giscus.get_attribute("data-category-id")))
        pg.wait_for_timeout(6000)
        giscus_frames = [f for f in pg.frames if "giscus.app" in f.url]
        check("giscus widget mounts", len(giscus_frames) >= 1)
        if giscus_frames:
            try:
                widget_text = giscus_frames[0].locator("body").inner_text(timeout=9000)
                check("giscus shows comment UI",
                      "评论" in widget_text or "登录" in widget_text, widget_text[:80])
            except Exception:
                check("giscus shows comment UI", False, "iframe unreadable")

    # 404 custom page
    resp = goto_retry(pg, BASE + "/definitely-missing.html", wait="domcontentloaded")
    check("404 status", resp.status == 404)
    check("custom 404", pg.locator(".notfound-art").count() == 1)
    print("404 link href:", pg.locator("#notfound-link").get_attribute("href"))
    from urllib.parse import urlparse

    expected_404 = urlparse(BASE).path.rstrip("/") + "/index.html"
    check("404 home link points to site root index",
          pg.locator("#notfound-link").get_attribute("href") == expected_404,
          expected_404)

    check("no page errors", not errs, "; ".join(errs))
    pg.screenshot(path="output/playwright/16-live-home.png")
    b.close()

print("ALL LIVE CHECKS PASSED" if ok else "LIVE CHECKS FAILED")
