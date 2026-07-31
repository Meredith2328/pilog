import threading
from playwright.sync_api import sync_playwright

BASE = "https://meredith2328.github.io/pilog"

ok = True


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
    resp = pg.goto(BASE + "/", wait_until="networkidle")
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
    check("post under /pilog", pg.url.startswith(BASE + "/posts/"))
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
    check("nav home from subpage -> /pilog",
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
        check("giscus repo matches", giscus.get_attribute("data-repo") == "Meredith2328/pilog")
        check("giscus has ids", bool(giscus.get_attribute("data-repo-id"))
              and bool(giscus.get_attribute("data-category-id")))

    # 404 custom page
    resp = pg.goto(BASE + "/definitely-missing.html", wait_until="domcontentloaded")
    check("404 status", resp.status == 404)
    check("custom 404", pg.locator(".notfound-art").count() == 1)
    print("404 link href:", pg.locator("#notfound-link").get_attribute("href"))
    check("404 home link points to /pilog/index.html",
          pg.locator("#notfound-link").get_attribute("href") == "/pilog/index.html")

    check("no page errors", not errs, "; ".join(errs))
    pg.screenshot(path="output/playwright/16-live-home.png")
    b.close()

print("ALL LIVE CHECKS PASSED" if ok else "LIVE CHECKS FAILED")
