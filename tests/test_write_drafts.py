#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression checks for the writer uplift in tools/write.html:

* touch gestures: horizontal swipes switch 信息 / 写作 / 预览 (left = next,
  right = previous), vertical drags and swipes starting on fields or an open
  sheet are ignored, a downward swipe on a sheet title bar closes the sheet;
* 稿件 sheet (flat version): dark header, a one-line toolbar (新建 / short
  84px sort select / search box / ⋯ menu with a ← back arrow in archive view),
  per-row 置顶 / 归档 buttons, archive view (title 归档, 恢复 / 删除 with
  two-step confirm), #drafts-sub counts and empty states;
* search: title mode by default (#d-search-full 全文 toggle switches to
  title + body + tags + category), case-insensitive multi-term matching,
  "N 个结果" counter, no-result hint, clear/Esc behavior, reset when reopening
  the sheet or switching normal/archive view, and full-text result snippets
  (.drow-snip) with <mark> highlights only for body matches;
* the toolbar + search box still fit at 360px with 全文 and clear shown;
* manual sorting: 手动排序 then long-press + vertical drag, sortRank persisted
  across reloads, dragging disabled in the archive view, no 上移/下移 buttons;
* pinned rows use the highlight outline, and 更多设置 ships token / theme /
  #draft-app-slot / help rows;
* PixelCJK is loaded and wired into the mono UI stack;
* the removed 清空本机全部稿件 button.

Drafts are seeded through localStorage from an init script, so every run starts
from a deterministic store. The suite binds port 8291 (tests/test_write.py owns
8197) and keeps browser downloads in .write_drafts_tmp.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import sys
import threading

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TMP = ROOT / ".write_drafts_tmp"

from util import block_external  # noqa: E402

import serve  # noqa: E402

PORT = 8291
srv = serve.ThreadingHTTPServer(("127.0.0.1", PORT), serve.Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()

from playwright.sync_api import sync_playwright  # noqa: E402

ok = True

BASE_TS = 1_760_000_000_000


def check(name, cond, detail=""):
    global ok
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + ("" if cond else f" — {detail}"))
    ok = ok and cond


# ---------------------------------------------------------------------------
# seeding
# ---------------------------------------------------------------------------


def draft(did, title, **kw):
    """A full draft record, with the pinned/archived/sortRank fields."""
    d = {
        "id": did, "created": BASE_TS, "updated": BASE_TS, "exported": 0,
        "title": title, "body": "正文 " + title, "category": "toy", "slug": "",
        "filenameSuffix": "123456", "date": "2026-01-01", "time": "10:00",
        "sec": "", "tags": [], "preview": "", "draft": False, "previewImage": "",
        "featureMode": "off", "featurePath": "", "pin": False,
        "highlight": False, "hidden": False, "order": "", "chapters": "",
        "extra": "", "caret": 0, "pub": None, "src": None,
        "pinned": False, "archived": False, "sortRank": 0,
    }
    d.update(kw)
    return d


def seed_js(drafts, prefs=None, active=None):
    ids = [d["id"] for d in drafts]
    index = {"active": ids[0] if active is None and ids else active, "ids": ids}
    p = {"sort": "updated", "filter": "all", "cat": "toy", "pv": "post"}
    p.update(prefs or {})
    payload = {"drafts": drafts, "index": index, "prefs": p}
    # Seed only once per browser context: a reload must keep the edits made by
    # the test instead of restoring the seed.
    return """(() => {
      const seed = %s;
      try {
        if (!localStorage.getItem("pilog.write.index")) {
          seed.drafts.forEach(function (d) {
            localStorage.setItem("pilog.write.d." + d.id, JSON.stringify(d));
          });
          localStorage.setItem("pilog.write.index", JSON.stringify(seed.index));
          localStorage.setItem("pilog.write.prefs", JSON.stringify(seed.prefs));
        }
      } catch (e) { /* storage disabled */ }
    })();""" % json.dumps(payload, ensure_ascii=False)


def new_page(b, drafts=None, prefs=None, active=None, width=412, height=860):
    ctx = b.new_context(
        viewport={"width": width, "height": height}, is_mobile=True, has_touch=True,
        accept_downloads=True,
    )
    if drafts is not None:
        ctx.add_init_script(seed_js(drafts, prefs, active))
    pg = ctx.new_page()
    cdp = ctx.new_cdp_session(pg)
    block_external(pg)
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{PORT}/tools/write.html", wait_until="domcontentloaded")
    pg.wait_for_function("!!window.__pilogWrite")
    return ctx, pg, cdp, errs


def no_errors(label, errs):
    check(f"{label}: no page errors", not errs, "; ".join(errs))


# ---------------------------------------------------------------------------
# page inspection helpers
# ---------------------------------------------------------------------------


def open_drafts(pg):
    if not pg.evaluate("document.querySelector('#sheet-drafts').classList.contains('is-open')"):
        pg.click("#btn-drafts")
    pg.wait_for_function(
        "document.querySelector('#sheet-drafts').classList.contains('is-open')")
    pg.wait_for_timeout(260)  # sheet slide-in transition


def close_drafts(pg):
    pg.click("#sheet-drafts .sheet-h [data-close]")
    pg.wait_for_function(
        "!document.querySelector('#sheet-drafts').classList.contains('is-open')")
    pg.wait_for_timeout(120)


def menu_state(pg):
    return pg.evaluate("""() => ({
      hidden: document.querySelector('#d-menu-pop').hidden,
      expanded: document.querySelector('#d-menu').getAttribute('aria-expanded'),
    })""")


def open_menu(pg):
    if menu_state(pg)["hidden"]:
        pg.click("#d-menu")
        pg.wait_for_function("!document.querySelector('#d-menu-pop').hidden")
        pg.wait_for_timeout(80)


def close_menu(pg):
    if not menu_state(pg)["hidden"]:
        pg.click("#sh-drafts-t")
        pg.wait_for_timeout(80)


def menu_items(pg):
    return pg.evaluate("""() => Array.from(document.querySelectorAll('#d-menu-pop button')).map(function (b) {
      return { id: b.id, open: b.dataset.open || '', text: b.textContent.trim() };
    })""")


def enter_archive(pg):
    open_menu(pg)
    pg.click("#d-archived")
    pg.wait_for_timeout(200)


def leave_archive(pg):
    pg.click("#d-back")
    pg.wait_for_timeout(200)


def search(pg, text):
    pg.fill("#d-search", text)
    pg.wait_for_timeout(240)  # input event is debounced by 140ms


def search_state(pg):
    return pg.evaluate("""() => ({
      value: document.querySelector('#d-search').value,
      placeholder: document.querySelector('#d-search').placeholder,
      mode: document.querySelector('#d-search-full').getAttribute('aria-pressed'),
      clearHidden: document.querySelector('#d-search-clear').hidden,
      rows: Array.from(document.querySelectorAll('#sheet-drafts .drow')).map(function (r) { return r.dataset.id; }),
      snippets: Array.from(document.querySelectorAll('#sheet-drafts .drow')).map(function (r) {
        const s = r.querySelector('.drow-snip');
        return s ? {
          id: r.dataset.id,
          text: s.textContent,
          html: s.innerHTML,
          marks: Array.from(s.querySelectorAll('mark')).map(function (m) { return m.textContent; }),
          inMain: !!s.closest('.drow-main'),
        } : null;
      }).filter(Boolean),
      sheetOpen: document.querySelector('#sheet-drafts').classList.contains('is-open'),
      sub: document.querySelector('#drafts-sub').textContent,
      note: document.querySelector('#draft-list .note')
        ? document.querySelector('#draft-list .note').textContent : null,
    })""")


def open_more(pg):
    open_menu(pg)
    pg.click("#d-menu-pop [data-open=more]")
    pg.wait_for_function("document.querySelector('#sheet-more').classList.contains('is-open')")
    pg.wait_for_timeout(260)


def sheet_rows(pg):
    return pg.evaluate("""() => Array.from(document.querySelectorAll('#sheet-drafts .drow')).map(function (r) {
      const t = r.querySelector('.drow-t');
      const m = r.querySelector('.drow-m span');
      return {
        id: r.dataset.id,
        title: t ? t.textContent : '',
        cat: m ? m.textContent : '',
        badges: Array.from(r.querySelectorAll('.badge')).map(function (b) { return b.textContent.trim(); }),
        active: r.classList.contains('is-active'),
        pinned: r.classList.contains('is-pinned'),
        main: !!r.querySelector('.drow-main[data-act=open]'),
        actions: Array.from(r.querySelectorAll('button[data-act]'))
          .filter(function (b) { return b.dataset.act !== 'open'; })
          .map(function (b) {
            return { act: b.dataset.act, text: b.textContent.trim(),
                     cls: b.className, disabled: !!b.disabled,
                     aria: b.getAttribute('aria-label') || '' };
          }),
      };
    })""")


def row_ids(pg):
    return [r["id"] for r in sheet_rows(pg)]


def row_titles(pg):
    return [r["title"] for r in sheet_rows(pg)]


def row_actions(pg, rid):
    row = next((r for r in sheet_rows(pg) if r["id"] == rid), None)
    return row["actions"] if row else []


def row_boxes(pg):
    return pg.evaluate("""() => Array.from(document.querySelectorAll('#sheet-drafts .drow')).map(function (r) {
      const b = r.getBoundingClientRect();
      return { id: r.dataset.id, top: b.top, height: b.height,
               cy: b.top + b.height / 2, cx: b.left + b.width / 2 };
    })""")


def storage(pg):
    return pg.evaluate("""() => {
      function load(k) { try { return JSON.parse(localStorage.getItem(k)); } catch (e) { return null; } }
      const idx = load('pilog.write.index'), drafts = {};
      ((idx && idx.ids) || []).forEach(function (id) { drafts[id] = load('pilog.write.d.' + id); });
      return { index: idx, prefs: load('pilog.write.prefs'), drafts: drafts };
    }""")


def prefs(pg):
    return storage(pg)["prefs"] or {}


def sub_text(pg):
    return pg.inner_text("#drafts-sub")


# ---------------------------------------------------------------------------
# synthetic touch input (trusted events through CDP)
# ---------------------------------------------------------------------------


def swipe_xy(pg, cdp, x1, y1, x2, y2, steps=10, hold_ms=10):
    cdp.send("Input.dispatchTouchEvent",
             {"type": "touchStart", "touchPoints": [{"x": x1, "y": y1, "id": 1}]})
    for i in range(1, steps + 1):
        cdp.send("Input.dispatchTouchEvent", {
            "type": "touchMove",
            "touchPoints": [{
                "x": x1 + (x2 - x1) * i / steps,
                "y": y1 + (y2 - y1) * i / steps,
                "id": 1,
            }],
        })
        pg.wait_for_timeout(hold_ms)
    cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    pg.wait_for_timeout(170)


def swipe(pg, cdp, selector, direction, dist=220):
    bb = pg.locator(selector).first.bounding_box()
    if not bb:
        raise AssertionError(f"cannot swipe: {selector} is not visible")
    if direction in ("left", "right"):
        y = bb["y"] + bb["height"] * 0.5
        if not 4 <= y <= 856:
            raise AssertionError(f"cannot swipe: {selector} centre is off-screen ({y})")
        if direction == "left":
            x1 = min(bb["x"] + bb["width"] - 24, 400.0)
            x2 = max(x1 - dist, 10.0)
        else:
            x1 = max(bb["x"] + 24, 10.0)
            x2 = min(x1 + dist, 402.0)
        swipe_xy(pg, cdp, x1, y, x2, y)
    elif direction in ("up", "down"):
        x = bb["x"] + bb["width"] * 0.5
        if direction == "down":
            y1 = bb["y"] + min(bb["height"] * 0.5, 20)
            y2 = min(y1 + dist, 850.0)
        else:
            y1 = bb["y"] + bb["height"] * 0.75
            y2 = max(y1 - dist, 10.0)
        if not 4 <= x <= 408:
            raise AssertionError(f"cannot swipe: {selector} centre is off-screen ({x})")
        swipe_xy(pg, cdp, x, y1, x, y2)
    else:
        raise AssertionError(f"unknown swipe direction: {direction}")


def drag_target_y(pg, rid, target_index):
    """A y coordinate whose row-index (count of other row centres above it) is
    target_index, i.e. where reorderDrafts will drop the dragged row."""
    boxes = row_boxes(pg)
    me = next((b for b in boxes if b["id"] == rid), None)
    if me is None:
        raise AssertionError(f"row not visible for drag: {rid}")
    others = [b for b in boxes if b["id"] != rid]
    if not others:
        return me["cy"]
    if target_index <= 0:
        return max(4.0, others[0]["cy"] - others[0]["height"] * 0.45)
    if target_index >= len(others):
        last = others[-1]
        return min(852.0, last["cy"] + last["height"] * 0.45)
    return (others[target_index - 1]["cy"] + others[target_index]["cy"]) / 2.0


def long_press_drag(pg, cdp, rid, y_to, hold_ms=400, steps=10):
    """Manual-sort gesture: touchStart, hold past the 260ms long-press timer,
    drag vertically, then release."""
    bb = pg.locator(f"#sheet-drafts .drow[data-id='{rid}']").bounding_box()
    if not bb:
        raise AssertionError(f"row not visible for drag: {rid}")
    x = bb["x"] + bb["width"] * 0.5
    y0 = bb["y"] + bb["height"] * 0.5
    cdp.send("Input.dispatchTouchEvent",
             {"type": "touchStart", "touchPoints": [{"x": x, "y": y0, "id": 1}]})
    pg.wait_for_timeout(hold_ms)
    for i in range(1, steps + 1):
        cdp.send("Input.dispatchTouchEvent", {
            "type": "touchMove",
            "touchPoints": [{"x": x, "y": y0 + (y_to - y0) * i / steps, "id": 1}],
        })
        pg.wait_for_timeout(15)
    pg.wait_for_timeout(60)
    cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    pg.wait_for_timeout(320)


def view_state(pg):
    return pg.evaluate("""() => {
      const t = document.querySelector('.tab[aria-selected="true"]');
      return { view: document.querySelector('#app').dataset.view, tab: t ? t.dataset.view : null };
    }""")


def check_view(pg, expected, label):
    state = view_state(pg)
    check(label, state["view"] == expected and state["tab"] == expected, repr(state))


# ---------------------------------------------------------------------------
# scenarios
# ---------------------------------------------------------------------------


def dom_contract_checks(b):
    print("\n== DOM contract: flat toolbar + menu + 更多设置 ==")
    ctx, pg, _cdp, errs = new_page(b)
    check("no #btn-wipe element", pg.locator("#btn-wipe").count() == 0)
    check("清空本机全部稿件 button/copy is gone",
          "清空本机全部稿件" not in pg.inner_text("#sheet-drafts"))
    stale = {sel: pg.locator(sel).count() for sel in
             ("#d-panel", "#d-filter", "#d-group", ".dfold", ".dfoot", ".dact")}
    check("grouped/filtered UI is gone (#d-panel/#d-filter/#d-group/.dfold/.dfoot)",
          all(v == 0 for v in stale.values()), repr(stale))
    check("#draft-app-slot lives in #sheet-more only",
          pg.locator("#sheet-more #draft-app-slot").count() == 1
          and pg.locator("#sheet-drafts #draft-app-slot").count() == 0)
    check("writer boots into 写作 view", view_state(pg)["view"] == "write", repr(view_state(pg)))

    open_drafts(pg)
    header = pg.evaluate("""() => {
      const head = getComputedStyle(document.querySelector('#sheet-drafts .sheet-h'));
      const ink = getComputedStyle(document.querySelector('#d-menu'));
      return { head: head.backgroundColor, ink: ink.color };
    }""")
    check("稿件 header uses the dark ink bar",
          header["head"] == header["ink"] and header["head"] not in ("", "rgba(0, 0, 0, 0)"),
          repr(header))
    check("toolbar has 新建 / short sort / search / ⋯ menu (with hidden ←)",
          pg.locator("#sheet-drafts .dtools-row #btn-new").count() == 1
          and pg.inner_text("#btn-new").strip() == "新建"
          and pg.locator("#sheet-drafts .dtools-row .dsort #d-sort").count() == 1
          and pg.locator("#sheet-drafts .dtools-row .dsearch #d-search").count() == 1
          and pg.locator("#sheet-drafts .dtools-row .dmenu #d-menu").count() == 1,
          pg.inner_text("#sheet-drafts .dtools-row").replace("\n", " | "))
    tools = pg.evaluate("""() => {
      const row = document.querySelector('#sheet-drafts .dtools-row');
      return {
        order: Array.from(row.children).map(function (e) {
          return e.id || e.className.split(' ')[0];
        }),
        sortWidth: row.querySelector('.dsort').getBoundingClientRect().width,
        sr: (function () {
          const s = row.querySelector('.dsort .sr');
          const b = s.getBoundingClientRect();
          const cs = getComputedStyle(s);
          return { w: b.width, h: b.height, pos: cs.position, overflow: cs.overflow };
        })(),
        sortAria: row.querySelector('#d-sort').getAttribute('aria-label'),
        search: {
          type: row.querySelector('#d-search').type,
          placeholder: row.querySelector('#d-search').placeholder,
          aria: row.querySelector('#d-search').getAttribute('aria-label'),
          clearHidden: row.querySelector('#d-search-clear').hidden,
          clearAria: row.querySelector('#d-search-clear').getAttribute('aria-label'),
          fullText: row.querySelector('#d-search-full').textContent.trim(),
          fullPressed: row.querySelector('#d-search-full').getAttribute('aria-pressed'),
          fullAria: row.querySelector('#d-search-full').getAttribute('aria-label'),
          order: Array.from(row.querySelector('.dsearch').children).map(function (e) { return e.id; }),
          fullInside: (function () {
            const wrap = row.querySelector('.dsearch').getBoundingClientRect();
            const inp = row.querySelector('#d-search').getBoundingClientRect();
            const fb = row.querySelector('#d-search-full').getBoundingClientRect();
            return fb.left >= inp.left && fb.right <= wrap.right + 0.5;
          })(),
        },
        menuHidden: row.querySelector('#d-menu').hidden,
        backHidden: row.querySelector('#d-back').hidden,
        backAria: row.querySelector('#d-back').getAttribute('aria-label'),
      };
    }""")
    check("toolbar order is 新建 → 排序 → 搜索 → ⋯",
          tools["order"][0] == "btn-new" and tools["order"][1] == "dsort"
          and tools["order"][2] == "dsearch" and tools["order"][3] == "dmenu",
          repr(tools["order"]))
    check("sort control is the short 84px select (no visible 排序 label)",
          round(tools["sortWidth"]) == 84 and tools["sortAria"] == "排序方式"
          and tools["sr"]["w"] <= 1 and tools["sr"]["h"] <= 1
          and tools["sr"]["pos"] == "absolute" and tools["sr"]["overflow"] == "hidden",
          repr({k: tools[k] for k in ("sortWidth", "sr", "sortAria")}))
    check("search box: type=search, placeholder 搜索标题, 全文 toggle at its right edge",
          tools["search"] == {
              "type": "search", "placeholder": "搜索标题", "aria": "搜索稿件",
              "clearHidden": True, "clearAria": "清除搜索",
              "fullText": "全文", "fullPressed": "false", "fullAria": "搜索全文",
              "order": ["d-search", "d-search-full", "d-search-clear"],
              "fullInside": True},
          repr(tools["search"]))
    check("normal view shows ⋯ and hides the ← back arrow",
          tools["menuHidden"] is False and tools["backHidden"] is True
          and tools["backAria"] == "返回全部稿件", repr(tools))
    fonts_css = ROOT / "generator" / "static" / "css" / "fonts.css"
    font_file = ROOT / "generator" / "static" / "fonts" / "PixelCJK-12-zh_hans.woff2"
    css_text = fonts_css.read_text(encoding="utf-8") if fonts_css.is_file() else ""
    check("PixelCJK assets exist in the repo and fonts.css declares them",
          fonts_css.is_file() and "'PixelCJK'" in css_text
          and "PixelCJK-12-zh_hans.woff2" in css_text
          and font_file.is_file() and font_file.stat().st_size > 0,
          f"{fonts_css} exists={fonts_css.is_file()} / "
          f"{font_file} exists={font_file.is_file()}")
    # The dev server serves /css from the built docs/, so a clean clone without
    # a build has no webfonts. The stack/usage assertions below always run; the
    # actual load check only runs when the font really is served.
    fonts = pg.evaluate("""async () => {
      const root = getComputedStyle(document.documentElement);
      const fam = function (sel) {
        const el = document.querySelector(sel);
        return el ? getComputedStyle(el).fontFamily : '';
      };
      let served = false, loaded = null;
      try {
        const resp = await fetch('/fonts/PixelCJK-12-zh_hans.woff2');
        served = !!(resp && resp.ok);
      } catch (e) { served = false; }
      if (served) {
        try {
          await document.fonts.load('12px PixelCJK');
          await document.fonts.ready;
          loaded = document.fonts.check('12px PixelCJK');
        } catch (e) { loaded = false; }
      }
      return {
        served: served,
        loaded: loaded,
        faces: Array.from(document.fonts).map(function (f) { return f.family.replace(/["']/g, ''); }),
        mono: root.getPropertyValue('--mono'),
        sans: root.getPropertyValue('--sans'),
        write: root.getPropertyValue('--write'),
        dbtn: fam('.dbtn'),
        menuBtn: fam('#d-menu-pop button'),
      };
    }""")
    check("--mono stack includes PixelCJK while --sans/--write do not",
          "PixelCJK" in fonts["mono"] and "PixelCJK" not in fonts["sans"]
          and "PixelCJK" not in fonts["write"],
          repr({k: fonts[k] for k in ("mono", "sans", "write")}))
    check("mono UI uses PixelCJK (.dbtn and menu rows)",
          "PixelCJK" in fonts["dbtn"] and "PixelCJK" in fonts["menuBtn"],
          repr({k: fonts[k] for k in ("dbtn", "menuBtn")}))
    if fonts["served"]:
        check("PixelCJK webfont loads from the dev server",
              fonts["loaded"] is True and "PixelCJK" in fonts["faces"],
              repr({k: fonts[k] for k in ("loaded", "faces")}))
    else:
        print("  [SKIP] PixelCJK woff2 not served (docs/ not built) — "
              "font load check skipped; repo asset + stack checks still ran")
    opts = pg.eval_on_selector_all(
        "#d-sort option", "els => els.map(e => [e.value, e.textContent.trim()])")
    check("sort select offers 编辑时间/创建时间/名称拼音/手动排序",
          opts == [["updated", "编辑时间"], ["created", "创建时间"],
                   ["title", "名称拼音"], ["manual", "手动排序"]], repr(opts))
    check("#d-menu-pop starts hidden with aria-expanded=false",
          menu_state(pg) == {"hidden": True, "expanded": "false"}, repr(menu_state(pg)))

    rows = sheet_rows(pg)
    check("flat list: first-run blank draft is 无标题稿件",
          len(rows) == 1 and rows[0]["title"] == "无标题稿件", repr(rows))
    check("rows are direct children of #draft-list (no group wrappers)",
          pg.evaluate("document.querySelectorAll('#draft-list > .drow').length") == len(rows))
    if rows:
        row = rows[0]
        acts = [(a["act"], a["text"]) for a in row["actions"]]
        check("row exposes .drow-main[data-act=open] / .drow-t / .drow-m",
              row["main"] and bool(row["title"]) and bool(row["cat"]), repr(row))
        check("normal row has exactly 置顶 + 归档 action buttons",
              acts == [("pin", "置顶"), ("archive", "归档")], repr(acts))
        check("no delete / restore buttons in the normal list",
              pg.locator("#sheet-drafts [data-act=del]").count() == 0
              and pg.locator("#sheet-drafts [data-act=restore]").count() == 0)
        check("no 上移/下移 buttons anywhere",
              pg.locator("#sheet-drafts [data-act=up], #sheet-drafts [data-act=down]").count() == 0)

        pg.click(f"#sheet-drafts .drow[data-id='{row['id']}'] .drow-pin")
        pg.wait_for_timeout(150)
        pinned = sheet_rows(pg)[0]
        check("row 置顶 toggles to 取消置顶 and marks the row pinned",
              pinned["pinned"] and row_actions(pg, row["id"])[0]["text"] == "取消置顶"
              and row_actions(pg, row["id"])[0]["aria"] == "取消置顶", repr(pinned))
        check("#drafts-sub reports the pinned count", "置顶 1" in sub_text(pg), sub_text(pg))
        check("pinned flag is stored on the draft",
              (storage(pg)["drafts"][row["id"]] or {}).get("pinned") is True)
        outline = pg.evaluate("""() => {
          const r = document.querySelector('#sheet-drafts .drow.is-pinned');
          const s = getComputedStyle(r);
          const probe = document.createElement('span');
          probe.style.color = 'var(--highlight)';
          document.body.appendChild(probe);
          const want = getComputedStyle(probe).color;
          probe.remove();
          return { color: s.outlineColor, want: want, style: s.outlineStyle,
                   width: s.outlineWidth, offset: s.outlineOffset };
        }""")
        check("pinned row draws a 2px highlight outline inside its box",
              outline["color"] == outline["want"]
              and outline["style"] == "solid"
              and outline["width"] == "2px"
              and outline["offset"] == "-2px", repr(outline))
        pg.click(f"#sheet-drafts .drow[data-id='{row['id']}'] .drow-pin")
        pg.wait_for_timeout(150)
        unpinned = sheet_rows(pg)[0]
        check("置顶 toggles back off",
              not unpinned["pinned"]
              and row_actions(pg, row["id"])[0]["text"] == "置顶"
              and "置顶" not in sub_text(pg), repr(unpinned))

    open_menu(pg)
    check("#d-menu opens #d-menu-pop and syncs aria-expanded",
          menu_state(pg) == {"hidden": False, "expanded": "true"}, repr(menu_state(pg)))
    items = menu_items(pg)
    check("menu has 编辑线上文章 / 图片库 / 查看归档文章 / 更多设置",
          len(items) == 4
          and items[0]["open"] == "remote" and "编辑线上文章" in items[0]["text"]
          and items[1]["id"] == "d-images" and "图片库" in items[1]["text"]
          and items[2]["id"] == "d-archived" and "查看归档文章" in items[2]["text"]
          and items[3]["open"] == "more" and "更多设置" in items[3]["text"], repr(items))
    pg.click("#sh-drafts-t")
    pg.wait_for_timeout(80)
    check("clicking outside closes the menu",
          menu_state(pg) == {"hidden": True, "expanded": "false"}, repr(menu_state(pg)))
    open_menu(pg)
    pg.click("#d-menu")
    pg.wait_for_timeout(80)
    check("⋯ toggles the menu closed again",
          menu_state(pg) == {"hidden": True, "expanded": "false"}, repr(menu_state(pg)))

    open_more(pg)
    check("更多设置 opens from the ⋯ menu and closes it",
          pg.locator("#sheet-more.is-open").count() == 1
          and menu_state(pg) == {"hidden": True, "expanded": "false"},
          repr(menu_state(pg)))
    check("#sheet-more is titled 更多设置", pg.inner_text("#sh-more-t").strip() == "更多设置",
          pg.inner_text("#sh-more-t"))
    more_rows = pg.evaluate("""() => ({
      total: document.querySelectorAll('#sheet-more .mrow').length,
      import: !!document.querySelector('#sheet-more .mrow#btn-import'),
      token: !!document.querySelector('#sheet-more .mrow[data-open=token] #more-tok'),
      theme: !!document.querySelector('#sheet-more .mrow#btn-theme #more-theme'),
      help: !!document.querySelector('#sheet-more .mrow[data-open=help]'),
    })""")
    check("更多设置 rows: 导入 .md / 令牌 / 外观 / 使用说明",
          more_rows == {"total": 4, "import": True, "token": True,
                        "theme": True, "help": True}, repr(more_rows))
    check("#more-tok shows the token status", pg.inner_text("#more-tok").strip() == "未设置",
          pg.inner_text("#more-tok"))
    check("#more-theme shows the light theme", pg.inner_text("#more-theme").strip() == "浅色",
          pg.inner_text("#more-theme"))
    order = pg.evaluate("""() => {
      const kids = Array.from(document.querySelector('#sheet-more .more-body').children);
      return {
        theme: kids.findIndex(function (e) { return e.id === 'btn-theme'; }),
        slot: kids.findIndex(function (e) { return e.id === 'draft-app-slot'; }),
        help: kids.findIndex(function (e) { return e.matches('[data-open=help]'); }),
      };
    }""")
    check("native #draft-app-slot sits between 外观 and 使用说明",
          0 <= order["theme"] < order["slot"] < order["help"], repr(order))
    pg.click("#more-theme")
    pg.wait_for_timeout(120)
    check("#btn-theme toggles the theme and updates #more-theme",
          pg.inner_text("#more-theme").strip() == "深色"
          and pg.evaluate("document.documentElement.dataset.theme") == "dark")
    pg.click("#more-theme")
    pg.wait_for_timeout(120)
    check("theme toggles back to 浅色", pg.inner_text("#more-theme").strip() == "浅色")
    pg.click("#sheet-more [data-open=help]")
    pg.wait_for_function("document.querySelector('#sheet-help').classList.contains('is-open')")
    check("使用说明 opens from 更多设置", pg.locator("#sheet-help.is-open").count() == 1)

    # #more-tok reflects the stored token status (presence only; the token and
    # publish flows are covered end-to-end by tests/test_write.py).
    pg.evaluate(
        "localStorage.setItem('pilog.write.ghToken', 'github_pat_FAKE0000TEST0000ONLY0000xyzw')")
    pg.reload(wait_until="domcontentloaded")
    pg.wait_for_function("!!window.__pilogWrite")
    open_drafts(pg)
    open_more(pg)
    check("#more-tok reflects a stored token", pg.inner_text("#more-tok").strip() == "已设置",
          pg.inner_text("#more-tok"))
    no_errors("dom", errs)
    ctx.close()


def gesture_checks(b):
    print("\n== swipe gestures ==")
    ctx, pg, cdp, errs = new_page(b)
    check_view(pg, "write", "initial view is 写作")
    swipe(pg, cdp, "#f-body", "left")
    check_view(pg, "preview", "left swipe on the editor (keyboard closed) → 预览")
    swipe(pg, cdp, "#pv-out", "right")
    check_view(pg, "write", "right swipe on 预览 → 写作")
    pg.click(".tab[data-view=meta]")
    check_view(pg, "meta", "tab click → 信息")
    swipe(pg, cdp, "#view-meta .zone", "left")
    check_view(pg, "write", "left swipe on 信息 → 写作")
    swipe(pg, cdp, "#f-body", "left")
    check_view(pg, "preview", "left swipe 写作 → 预览")
    swipe(pg, cdp, "#pv-out", "right")
    swipe(pg, cdp, "#f-body", "right")
    check_view(pg, "meta", "right swipe 写作 → 信息")
    swipe(pg, cdp, "#view-meta .form", "down")
    check_view(pg, "meta", "vertical drag does not switch views")
    swipe(pg, cdp, "#f-title-m", "left")
    check_view(pg, "meta", "swipe starting on an input is ignored")
    pg.click(".tab[data-view=write]")
    pg.wait_for_timeout(100)
    swipe(pg, cdp, "#f-body", "down")
    check_view(pg, "write", "vertical drag on the editor does not switch views")
    open_drafts(pg)
    swipe(pg, cdp, "#draft-list", "left")
    check_view(pg, "write", "swipe starting on an open sheet is ignored")
    swipe(pg, cdp, "#sheet-drafts .sheet-h", "down", dist=150)
    check("downward swipe on the sheet title bar closes the sheet",
          not pg.evaluate("document.querySelector('#sheet-drafts').classList.contains('is-open')"))
    no_errors("gestures", errs)
    ctx.close()


def pinyin_checks(b):
    print("\n== pinyin title sort ==")
    # Deliberately no polyphones: ICU reads 长 as zhǎng, so a title containing it
    # would test ICU's reading choice rather than the writer's collation hookup.
    titles = ["阿里", "波音", "程序", "数据", "张伟"]
    expected = ["阿里", "波音", "程序", "数据", "张伟"]  # a, bo, cheng, shu, zhang
    drafts = [
        draft(f"py{i}", t, updated=BASE_TS + (len(titles) - i) * 1000,
              created=BASE_TS + i * 1000, sortRank=i)
        for i, t in enumerate(titles)
    ]
    ctx, pg, _cdp, errs = new_page(b, drafts, {"sort": "updated", "filter": "all"})
    check("Intl pinyin collator is present in the page",
          pg.evaluate("new Intl.Collator('zh-Hans-CN-u-co-pinyin').compare('阿', '波') < 0"))
    collator_order = pg.evaluate(
        "t => t.slice().sort(function (a, b) {"
        " return new Intl.Collator('zh-Hans-CN-u-co-pinyin').compare(a, b); })", titles)
    codepoint = sorted(titles)
    check("page collator agrees with the expected pinyin order",
          collator_order == expected, f"{collator_order} vs {expected}")
    check("pinyin order differs from Unicode codepoint order",
          expected != codepoint, f"pinyin={expected} codepoint={codepoint}")

    open_drafts(pg)
    check("rows initially follow edited time (seed order)",
          row_titles(pg) == titles, repr(row_titles(pg)))
    pg.select_option("#d-sort", "title")
    pg.wait_for_timeout(140)
    order = row_titles(pg)
    check("名称拼音 sorts rows by pinyin collation, not codepoint",
          order == expected, f"got {order}, expected {expected}, codepoint {codepoint}")
    check("名称拼音 puts 阿 before 波 before 程", order[:3] == ["阿里", "波音", "程序"], repr(order))
    check("名称拼音 is not codepoint order", order != codepoint, repr(order))
    check("sort choice is persisted in pilog.write.prefs", prefs(pg).get("sort") == "title",
          repr(prefs(pg)))
    no_errors("pinyin", errs)
    ctx.close()


def updated_created_checks(b):
    print("\n== edited / created sort ==")
    drafts = [
        draft("u1", "甲", updated=BASE_TS + 3000, created=BASE_TS + 1000),
        draft("u2", "乙", updated=BASE_TS + 1000, created=BASE_TS + 3000),
        draft("u3", "丙", updated=BASE_TS + 2000, created=BASE_TS + 2000),
    ]
    ctx, pg, _cdp, errs = new_page(b, drafts, {"sort": "updated", "filter": "all"}, active="u1")
    open_drafts(pg)
    check("编辑时间 sorts newest first",
          row_titles(pg) == ["甲", "丙", "乙"], repr(row_titles(pg)))
    pg.select_option("#d-sort", "created")
    pg.wait_for_timeout(140)
    check("创建时间 sorts newest first",
          row_titles(pg) == ["乙", "丙", "甲"], repr(row_titles(pg)))
    pg.select_option("#d-sort", "updated")
    pg.wait_for_timeout(140)
    check("编辑时间 switch back restores edited order",
          row_titles(pg) == ["甲", "丙", "乙"], repr(row_titles(pg)))
    p = prefs(pg)
    check("sort choice is persisted", p.get("sort") == "updated", repr(p))
    check("prefs keeps only sort/filter (no grouping keys)",
          {"sort", "filter"} <= set(p) and "group" not in p and "collapsed" not in p, repr(p))
    no_errors("updated/created", errs)
    ctx.close()


def search_checks(b):
    print("\n== search: title default / 全文 toggle / snippets ==")
    drafts = [
        draft("s1", "排版笔记",
              body="正文讲 grid 布局 needle 的用法，后面的文字用来凑出一段可以被截断的长摘要。",
              tags=["CSS"], category="notes/tools", updated=BASE_TS + 6000),
        draft("s2", "Python 技巧", body="列表推导与生成器", tags=["代码"],
              category="notes/algo", updated=BASE_TS + 5000),
        draft("s3", "Alpha 杂谈", body="普通正文", tags=["misc"],
              category="reference", updated=BASE_TS + 4000),
        draft("s4", "归档旧稿", body="zebra 档案内容 needle", tags=["旧"],
              category="toy", archived=True, updated=BASE_TS + 3000),
        draft("s5", "", body="## 标题回退\n\n正文只有 xyz 这个词。",
              updated=BASE_TS + 2000),
    ]
    ctx, pg, _cdp, errs = new_page(b, drafts, {"sort": "updated", "filter": "all"},
                                   active="s1")
    open_drafts(pg)
    st = search_state(pg)
    check("search starts in TITLE mode with an empty query",
          st["value"] == "" and st["placeholder"] == "搜索标题"
          and st["mode"] == "false" and st["clearHidden"] is True
          and st["rows"] == ["s1", "s2", "s3", "s5"], repr(st))

    search(pg, "needle")
    st = search_state(pg)
    check("title mode ignores body-only matches",
          st["rows"] == [] and st["sub"] == "没有匹配"
          and st["note"] and "needle" in st["note"], repr(st))
    search(pg, "css")
    check("title mode ignores tag-only matches",
          search_state(pg)["rows"] == [], repr(search_state(pg)))
    search(pg, "notes/tools")
    check("title mode ignores category-only matches",
          search_state(pg)["rows"] == [], repr(search_state(pg)))
    search(pg, "alpha")
    check("title mode matches titles case-insensitively",
          search_state(pg)["rows"] == ["s3"], repr(search_state(pg)))
    search(pg, "标题回退")
    check("title mode falls back to the first body heading",
          search_state(pg)["rows"] == ["s5"], repr(search_state(pg)))
    search(pg, "python 技巧")
    check("title mode multi-term requires all terms in the title",
          search_state(pg)["rows"] == ["s2"], repr(search_state(pg)))
    search(pg, "python 列表")
    check("title mode multi-term rejects body-only terms",
          search_state(pg)["rows"] == [], repr(search_state(pg)))
    search(pg, "python")
    st = search_state(pg)
    check("title mode never renders snippets",
          st["rows"] == ["s2"] and st["snippets"] == [], repr(st))

    # 清除 only clears the query, keeping the current (title) mode
    search(pg, "needle")
    check("清除 appears while a query is present",
          search_state(pg)["clearHidden"] is False, repr(search_state(pg)))
    pg.click("#d-search-clear")
    pg.wait_for_timeout(200)
    st = search_state(pg)
    check("清除 restores the list without leaving title mode",
          st["value"] == "" and st["rows"] == ["s1", "s2", "s3", "s5"]
          and st["clearHidden"] is True and st["mode"] == "false"
          and st["placeholder"] == "搜索标题", repr(st))

    search(pg, "python")
    pg.press("#d-search", "Escape")
    pg.wait_for_timeout(200)
    st = search_state(pg)
    check("Esc clears the query and keeps the sheet + title mode",
          st["value"] == "" and st["rows"] == ["s1", "s2", "s3", "s5"]
          and st["clearHidden"] is True and st["sheetOpen"] is True
          and st["mode"] == "false" and st["placeholder"] == "搜索标题", repr(st))

    # 全文 toggle
    pg.click("#d-search-full")
    pg.wait_for_timeout(150)
    st = search_state(pg)
    check("全文 toggles aria-pressed and the placeholder",
          st["mode"] == "true" and st["placeholder"] == "搜索全文", repr(st))
    search(pg, "needle")
    st = search_state(pg)
    check("full mode finds body matches",
          st["rows"] == ["s1"] and st["sub"] == "1 个结果", repr(st))
    snip = st["snippets"][0] if st["snippets"] else {}
    check("body match renders a .drow-snip inside the row main button",
          len(st["snippets"]) == 1 and snip.get("id") == "s1"
          and snip.get("inMain") is True and "needle" in snip.get("text", ""),
          repr(st["snippets"]))
    check("snippet highlights the matched term with <mark>",
          snip.get("marks") == ["needle"], repr(snip))
    clamp = pg.evaluate("""() => {
      const s = document.querySelector('.drow-snip');
      if (!s) return null;
      const cs = getComputedStyle(s);
      return { clamp: cs.webkitLineClamp || cs.getPropertyValue('-webkit-line-clamp'),
               overflow: cs.overflow };
    }""")
    check("snippet is clamped to two lines",
          bool(clamp) and str(clamp["clamp"]) == "2"
          and clamp["overflow"] == "hidden", repr(clamp))
    search(pg, "grid needle")
    st = search_state(pg)
    check("multi-term full search highlights every matched term",
          st["rows"] == ["s1"]
          and (st["snippets"][0]["marks"] if st["snippets"] else []) == ["grid", "needle"],
          repr(st["snippets"]))
    search(pg, "python")
    st = search_state(pg)
    check("title-only match in full mode has no snippet",
          st["rows"] == ["s2"] and st["snippets"] == [], repr(st))
    search(pg, "css")
    st = search_state(pg)
    check("tag-only match in full mode has no snippet",
          st["rows"] == ["s1"] and st["snippets"] == [], repr(st))
    search(pg, "notes/tools")
    st = search_state(pg)
    check("category-only match in full mode has no snippet",
          st["rows"] == ["s1"] and st["snippets"] == [], repr(st))
    search(pg, "xyz")
    st = search_state(pg)
    check("body-only match in full mode has a snippet with <mark>",
          st["rows"] == ["s5"]
          and (st["snippets"][0]["marks"] if st["snippets"] else []) == ["xyz"],
          repr(st["snippets"]))
    search(pg, "needle 不存在")
    st = search_state(pg)
    check("full mode still requires every term to match",
          st["rows"] == [] and st["sub"] == "没有匹配", repr(st))

    # Esc and 清除 keep the 全文 mode
    search(pg, "needle")
    pg.press("#d-search", "Escape")
    pg.wait_for_timeout(200)
    st = search_state(pg)
    check("Esc keeps 全文 mode selected",
          st["value"] == "" and st["rows"] == ["s1", "s2", "s3", "s5"]
          and st["sheetOpen"] is True and st["mode"] == "true"
          and st["placeholder"] == "搜索全文", repr(st))
    search(pg, "needle")
    pg.click("#d-search-clear")
    pg.wait_for_timeout(200)
    st = search_state(pg)
    check("清除 keeps 全文 mode selected",
          st["value"] == "" and st["mode"] == "true"
          and st["placeholder"] == "搜索全文", repr(st))

    # reset on reopening the sheet
    search(pg, "needle")
    close_drafts(pg)
    open_drafts(pg)
    st = search_state(pg)
    check("reopening 稿件 resets query and mode",
          st["value"] == "" and st["mode"] == "false"
          and st["placeholder"] == "搜索标题"
          and st["rows"] == ["s1", "s2", "s3", "s5"], repr(st))

    # reset when switching normal/archive view
    pg.click("#d-search-full")
    pg.wait_for_timeout(120)
    search(pg, "needle")
    enter_archive(pg)
    st = search_state(pg)
    check("switching to the archive view resets query and mode",
          st["value"] == "" and st["mode"] == "false"
          and st["placeholder"] == "搜索标题" and st["rows"] == ["s4"], repr(st))
    pg.click("#d-search-full")
    pg.wait_for_timeout(120)
    search(pg, "needle")
    st = search_state(pg)
    check("archive full-text search renders snippets",
          st["rows"] == ["s4"]
          and (st["snippets"][0]["marks"] if st["snippets"] else []) == ["needle"],
          repr(st))
    search(pg, "python")
    check("archive search never returns normal drafts",
          search_state(pg)["rows"] == [], repr(search_state(pg)))
    leave_archive(pg)
    st = search_state(pg)
    check("← resets query and mode back to title",
          st["value"] == "" and st["mode"] == "false"
          and st["placeholder"] == "搜索标题"
          and st["rows"] == ["s1", "s2", "s3", "s5"], repr(st))
    no_errors("search", errs)
    ctx.close()


def narrow_checks(b):
    print("\n== 360px toolbar fits ==")
    drafts = [
        draft("n1", "排版笔记", body="grid needle", updated=BASE_TS + 2000),
        draft("n2", "Python 技巧", updated=BASE_TS + 1000),
    ]
    ctx, pg, _cdp, errs = new_page(b, drafts, {"sort": "updated", "filter": "all"},
                                   active="n1", width=360)
    open_drafts(pg)

    def geom():
        return pg.evaluate("""() => {
          const row = document.querySelector('#sheet-drafts .dtools-row');
          const wrap = document.querySelector('#sheet-drafts .dsearch');
          const inp = document.querySelector('#d-search');
          const full = document.querySelector('#d-search-full');
          const clear = document.querySelector('#d-search-clear');
          const rb = row.getBoundingClientRect(), wb = wrap.getBoundingClientRect();
          const ib = inp.getBoundingClientRect(), fb = full.getBoundingClientRect();
          const cb = clear.getBoundingClientRect();
          return {
            inner: window.innerWidth, rowRight: rb.right,
            rowScroll: row.scrollWidth, rowClient: row.clientWidth,
            searchRight: wb.right, inputWidth: ib.width,
            fullW: fb.width, fullRight: fb.right,
            clearHidden: clear.hidden, clearW: cb.width, clearRight: cb.right,
          };
        }""")

    g = geom()
    check("360px: toolbar fits with the 全文 button",
          g["rowScroll"] <= g["rowClient"] + 1
          and g["rowRight"] <= g["inner"] + 0.5
          and g["searchRight"] <= g["inner"] + 0.5
          and g["inputWidth"] > 20 and g["fullW"] > 0
          and g["fullRight"] <= g["searchRight"] + 0.5, repr(g))
    pg.fill("#d-search", "排")
    pg.wait_for_timeout(220)
    g = geom()
    check("360px: toolbar still fits with the clear button shown",
          g["clearHidden"] is False and g["clearW"] > 0
          and g["rowScroll"] <= g["rowClient"] + 1
          and g["rowRight"] <= g["inner"] + 0.5
          and g["searchRight"] <= g["inner"] + 0.5
          and max(g["fullRight"], g["clearRight"]) <= g["searchRight"] + 0.5,
          repr(g))
    no_errors("360px", errs)
    ctx.close()


def pin_archive_checks(b):
    print("\n== pin / archive view / restore / delete / counts ==")
    drafts = [
        draft("p1", "甲", updated=BASE_TS + 4000),
        draft("p2", "乙", updated=BASE_TS + 3000),
        draft("p3", "丙", updated=BASE_TS + 2000),
        draft("p4", "归档丁", updated=BASE_TS + 1000, archived=True),
    ]
    ctx, pg, _cdp, errs = new_page(b, drafts, {"sort": "updated", "filter": "all"}, active="p1")
    open_drafts(pg)
    check("normal view excludes archived drafts",
          row_ids(pg) == ["p1", "p2", "p3"], repr(row_ids(pg)))
    check("normal counts mention the archived draft",
          "3 篇" in sub_text(pg) and "归档 1" in sub_text(pg), sub_text(pg))
    check("sheet title is 稿件 and the menu offers 查看归档文章",
          pg.inner_text("#sh-drafts-t").strip() == "稿件"
          and "查看归档文章" in pg.inner_text("#d-archived"),
          f"{pg.inner_text('#sh-drafts-t')} / {pg.inner_text('#d-archived')}")

    pg.click("#sheet-drafts .drow[data-id='p3'] .drow-pin")
    pg.wait_for_timeout(160)
    rows = sheet_rows(pg)
    check("置顶 moves the row first and keeps the rest in sort order",
          row_ids(pg) == ["p3", "p1", "p2"], repr(row_ids(pg)))
    check("pinned row is marked and its button reads 取消置顶",
          rows[0]["pinned"] and row_actions(pg, "p3")[0]["text"] == "取消置顶", repr(rows[0]))
    check("pinned draft stored with pinned=true",
          (storage(pg)["drafts"]["p3"] or {}).get("pinned") is True)
    check("#drafts-sub counts the pinned draft", "置顶 1" in sub_text(pg), sub_text(pg))

    pg.click("#sheet-drafts .drow[data-id='p2'] .drow-arc")
    pg.wait_for_timeout(160)
    check("归档 removes the row from the normal list",
          row_ids(pg) == ["p3", "p1"], repr(row_ids(pg)))
    check("archived draft stored with archived=true",
          (storage(pg)["drafts"]["p2"] or {}).get("archived") is True)
    check("normal counts update after archiving",
          "2 篇" in sub_text(pg) and "归档 2" in sub_text(pg), sub_text(pg))

    enter_archive(pg)
    check("archive view title becomes 归档",
          pg.inner_text("#sh-drafts-t").strip() == "归档",
          pg.inner_text("#sh-drafts-t"))
    chrome = pg.evaluate("""() => ({
      menuHidden: document.querySelector('#d-menu').hidden,
      backHidden: document.querySelector('#d-back').hidden,
      backAria: document.querySelector('#d-back').getAttribute('aria-label'),
      popText: document.querySelector('#d-menu-pop').textContent,
    })""")
    check("archive view hides ⋯ and shows the ← back arrow",
          chrome["menuHidden"] is True and chrome["backHidden"] is False
          and chrome["backAria"] == "返回全部稿件", repr(chrome))
    check("archive view no longer carries a 返回全部稿件 menu item",
          "返回全部稿件" not in chrome["popText"], repr(chrome["popText"]))
    check("archive view lists archived drafts newest first",
          row_ids(pg) == ["p2", "p4"], repr(row_ids(pg)))
    acts = [(a["act"], a["text"]) for a in row_actions(pg, "p2")]
    check("archive row has exactly 恢复 + 删除 buttons",
          acts == [("restore", "恢复"), ("del", "删除")], repr(acts))
    check("archive row has no pin/archive buttons",
          not any(a["act"] in ("pin", "archive") for r in sheet_rows(pg) for a in r["actions"]))
    check("archive counts show the archived total", "2 篇" in sub_text(pg), sub_text(pg))

    pg.click("#sheet-drafts .drow[data-id='p2'] [data-act=restore]")
    pg.wait_for_timeout(160)
    check("恢复 removes the row from the archive view",
          row_ids(pg) == ["p4"], repr(row_ids(pg)))
    check("restored draft stored with archived=false",
          (storage(pg)["drafts"]["p2"] or {}).get("archived") is False)
    check("archive counts update after restoring", "1 篇" in sub_text(pg), sub_text(pg))

    pg.click("#sheet-drafts .drow[data-id='p4'] [data-act=del]")
    pg.wait_for_timeout(120)
    armed = pg.locator("#sheet-drafts .drow[data-id='p4'] [data-act=del]")
    check("first delete click arms 确认删除 without removing the row",
          armed.inner_text().strip() == "确认删除" and "p4" in row_ids(pg),
          armed.inner_text())
    armed.click()
    pg.wait_for_timeout(200)
    check("second delete click removes the archived draft",
          row_ids(pg) == []
          and "p4" not in (storage(pg)["index"] or {}).get("ids", [])
          and storage(pg)["drafts"].get("p4") is None, repr(row_ids(pg)))
    check("empty archive state shows a hint",
          pg.locator("#draft-list .note").count() == 1
          and "没有归档" in pg.inner_text("#drafts-sub"), sub_text(pg))

    leave_archive(pg)
    check("← returns to the normal view",
          pg.inner_text("#sh-drafts-t").strip() == "稿件"
          and row_ids(pg) == ["p3", "p1", "p2"], repr(row_ids(pg)))
    chrome = pg.evaluate("""() => ({
      menuHidden: document.querySelector('#d-menu').hidden,
      backHidden: document.querySelector('#d-back').hidden,
    })""")
    check("normal view shows ⋯ again and hides ←",
          chrome == {"menuHidden": False, "backHidden": True}, repr(chrome))
    check("normal menu entry is 查看归档文章 again",
          "查看归档文章" in pg.inner_text("#d-archived"), pg.inner_text("#d-archived"))
    check("normal counts include the restored draft",
          "3 篇" in sub_text(pg) and "置顶 1" in sub_text(pg), sub_text(pg))

    pg.click("#sheet-drafts .drow[data-id='p3'] .drow-pin")
    pg.wait_for_timeout(160)
    check("取消置顶 puts the row back in edited order",
          row_ids(pg) == ["p1", "p2", "p3"] and "置顶" not in sub_text(pg),
          f"{row_ids(pg)} / {sub_text(pg)}")
    check("normal rows never expose delete/restore actions",
          pg.locator("#sheet-drafts [data-act=del]").count() == 0
          and pg.locator("#sheet-drafts [data-act=restore]").count() == 0)
    no_errors("pin/archive", errs)
    ctx.close()


def manual_checks(b):
    print("\n== manual sort: long-press drag ==")
    drafts = [
        draft("m1", "甲", updated=BASE_TS + 5000, sortRank=0),
        draft("m2", "乙", updated=BASE_TS + 4000, sortRank=1),
        draft("m3", "丙", updated=BASE_TS + 3000, sortRank=2),
        draft("m4", "丁", updated=BASE_TS + 2000, sortRank=3),
        draft("a5", "归档戊", updated=BASE_TS + 1000, archived=True),
    ]
    ctx, pg, cdp, errs = new_page(b, drafts, {"sort": "updated", "filter": "all"}, active="m1")
    open_drafts(pg)
    check("edited order before switching to manual",
          row_ids(pg) == ["m1", "m2", "m3", "m4"], repr(row_ids(pg)))
    pg.select_option("#d-sort", "manual")
    pg.wait_for_timeout(220)
    check("手动排序 keeps the visible order when selected",
          row_ids(pg) == ["m1", "m2", "m3", "m4"], repr(row_ids(pg)))
    check("sort choice persisted as manual", prefs(pg).get("sort") == "manual", repr(prefs(pg)))
    check("no 上移/下移 buttons after selecting manual",
          pg.locator("#sheet-drafts [data-act=up], #sheet-drafts [data-act=down]").count() == 0
          and "上移" not in pg.inner_text("#sheet-drafts")
          and "下移" not in pg.inner_text("#sheet-drafts"))

    y = drag_target_y(pg, "m1", 1)
    long_press_drag(pg, cdp, "m1", y)
    check("long-press drag moves a row one position down",
          row_ids(pg) == ["m2", "m1", "m3", "m4"], repr(row_ids(pg)))
    ranks = {k: storage(pg)["drafts"][k]["sortRank"] for k in ("m1", "m2", "m3", "m4")}
    check("sortRank values persist as numbers",
          all(isinstance(v, (int, float)) for v in ranks.values()), repr(ranks))
    check("sortRank order matches the dragged order",
          sorted(ranks, key=ranks.get) == ["m2", "m1", "m3", "m4"], repr(ranks))

    pg.reload(wait_until="domcontentloaded")
    pg.wait_for_function("!!window.__pilogWrite")
    open_drafts(pg)
    check("manual order survives a reload", row_ids(pg) == ["m2", "m1", "m3", "m4"],
          repr(row_ids(pg)))
    check("sort choice survives a reload", prefs(pg).get("sort") == "manual", repr(prefs(pg)))
    ranks_after = {k: storage(pg)["drafts"][k]["sortRank"] for k in ("m1", "m2", "m3", "m4")}
    check("sortRank values survive a reload", ranks_after == ranks,
          f"{ranks} -> {ranks_after}")

    y = drag_target_y(pg, "m4", 0)
    long_press_drag(pg, cdp, "m4", y)
    check("long-press drag moves a row to the top",
          row_ids(pg) == ["m4", "m2", "m1", "m3"], repr(row_ids(pg)))
    ranks_top = {k: storage(pg)["drafts"][k]["sortRank"] for k in ("m1", "m2", "m3", "m4")}
    check("top drag reassigns sortRank in the new order",
          sorted(ranks_top, key=ranks_top.get) == ["m4", "m2", "m1", "m3"], repr(ranks_top))

    enter_archive(pg)
    check("archive view is active for the drag check",
          pg.inner_text("#sh-drafts-t").strip() == "归档" and row_ids(pg) == ["a5"],
          f"{pg.inner_text('#sh-drafts-t')} / {row_ids(pg)}")
    archived_rank = storage(pg)["drafts"]["a5"]["sortRank"]
    box = row_boxes(pg)[0]
    long_press_drag(pg, cdp, "a5", box["cy"] + 120)
    check("dragging is disabled in the archive view",
          row_ids(pg) == ["a5"]
          and storage(pg)["drafts"]["a5"]["sortRank"] == archived_rank,
          f"{row_ids(pg)} / {storage(pg)['drafts']['a5']['sortRank']} vs {archived_rank}")
    leave_archive(pg)
    check("manual order is intact after leaving the archive view",
          row_ids(pg) == ["m4", "m2", "m1", "m3"], repr(row_ids(pg)))
    no_errors("manual", errs)
    ctx.close()


def only_archived_checks(b):
    print("\n== only-archived / empty states ==")
    drafts = [
        draft("a1", "归档甲", updated=BASE_TS + 2000, archived=True),
        draft("a2", "归档乙", updated=BASE_TS + 1000, archived=True),
    ]
    ctx, pg, _cdp, errs = new_page(b, drafts, {"sort": "updated", "filter": "archived"},
                                   active="a1")
    open_drafts(pg)
    check("archive view lists the archived drafts with 恢复/删除",
          pg.inner_text("#sh-drafts-t").strip() == "归档"
          and row_ids(pg) == ["a1", "a2"]
          and all([(a["act"], a["text"]) for a in r["actions"]]
                  == [("restore", "恢复"), ("del", "删除")] for r in sheet_rows(pg)),
          repr(sheet_rows(pg)))
    leave_archive(pg)
    check("全部 hides archived drafts entirely", row_ids(pg) == [], repr(row_ids(pg)))
    check("empty 全部 state shows a hint",
          pg.locator("#draft-list .note").count() == 1
          and pg.inner_text("#draft-list .note").strip() != "")
    check("empty 全部 counts still mention archived drafts",
          "没有稿件" in sub_text(pg) and "归档 2" in sub_text(pg), sub_text(pg))
    enter_archive(pg)
    check("returning to the archive view shows both drafts again",
          pg.inner_text("#sh-drafts-t").strip() == "归档"
          and row_ids(pg) == ["a1", "a2"], repr(row_ids(pg)))
    no_errors("only-archived", errs)
    ctx.close()


def main() -> None:
    shutil.rmtree(TMP, ignore_errors=True)
    TMP.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(downloads_path=str(TMP))
        try:
            dom_contract_checks(b)
            gesture_checks(b)
            pinyin_checks(b)
            updated_created_checks(b)
            search_checks(b)
            narrow_checks(b)
            pin_archive_checks(b)
            manual_checks(b)
            only_archived_checks(b)
        finally:
            b.close()
    shutil.rmtree(TMP, ignore_errors=True)
    srv.shutdown()
    print("ALL PASS" if ok else "SOME FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
