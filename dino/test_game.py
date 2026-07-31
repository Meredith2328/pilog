#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Headless verification of the T-Rex Runner clone.

Checks:
  1. Page loads without console errors and game state initializes.
  2. Start screen is pixel-identical to a PIL reference render.
  3. Jump physics, intro animation, running frames, score, ducking.
  4. Mid-air speed drop.
  5. Collision -> game over panel + high score persistence.
  6. Restart via Enter.
  7. Night mode (inverted background + moon/stars).
  8. Pterodactyl spawns and animates at high speed.
  9. Blur pauses / focus resumes.
"""

import sys
import time
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "index.html"
REF = ROOT / "reference"


def render_start_screen_reference(trex_frame_offset):
    """Render the deterministic start screen with PIL from the 1x sheet."""
    sheet = Image.open(REF / "sprite_1x.png").convert("RGBA")
    bg = Image.new("RGBA", (600, 150), (0xF7, 0xF7, 0xF7, 255))
    # Horizon line (two 600px strips at y=127)
    ground = sheet.crop((2, 52, 602, 64))
    bg.paste(ground, (0, 127), ground)
    bg.paste(ground, (600, 127), ground)
    # Score digits "00000" at top right
    digit = sheet.crop((655, 2, 665, 15))
    for i in range(5):
        bg.paste(digit, (534 + i * 11, 5), digit)
    # Trex standing frame at (0, 93)
    tx = 848 + trex_frame_offset
    trex = sheet.crop((tx, 2, tx + 44, 49))
    bg.paste(trex, (0, 93), trex)
    return bg.convert("RGB")


def diff_report(a, b, label):
    pa = a.load()
    pb = b.load()
    w, h = a.size
    diff = 0
    for y in range(h):
        for x in range(w):
            ca = pa[x, y]
            cb = pb[x, y]
            if abs(ca[0] - cb[0]) > 12 or abs(ca[1] - cb[1]) > 12 or \
                    abs(ca[2] - cb[2]) > 12:
                diff += 1
    pct = diff * 100.0 / (w * h)
    status = "OK" if pct < 0.05 else "FAIL"
    print(f"[{status}] {label}: {diff} px differ ({pct:.4f}%)")
    return status == "OK"


def wait_for(predicate, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def main():
    results = []
    console_errors = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1000, "height": 800})
        page.on("console", lambda msg: console_errors.append(msg.text)
                if msg.type == "error" else None)
        page.on("pageerror", lambda exc: console_errors.append(str(exc)))
        page.goto(INDEX.as_uri())
        page.wait_for_function("window.Runner && Runner.instance_ && Runner.instance_.tRex")

        # ---- 1. state initialization ----
        state = page.evaluate("""() => {
          const r = Runner.instance_;
          return {
            playing: r.playing,
            crashed: r.crashed,
            activated: r.activated,
            speed: r.currentSpeed,
            tRexY: r.tRex.yPos,
            tRexStatus: r.tRex.status,
            containerWidth: getComputedStyle(document.getElementById('runner-container')).width,
            hiDpi: window.devicePixelRatio > 1,
          };
        }""")
        ok = (state["playing"] is False and state["crashed"] is False and
              state["tRexStatus"] == "WAITING" and
              state["containerWidth"] == "44px" and state["tRexY"] == 93)
        results.append(("start screen state (44px strip, waiting trex)", ok))
        print("state:", state)

        # ---- 2. pixel-perfect start screen ----
        page.evaluate("""() => {
          const r = Runner.instance_;
          cancelAnimationFrame(r.raqId);
          r.raqId = 0;
          document.getElementById('runner-container').style.width = '600px';
          r.tRex.currentFrame = 0;
          r.tRex.draw(r.tRex.currentAnimFrames[0], 0);
        }""")
        shot = page.locator("#runner-canvas").screenshot()
        shot_img = Image.open(__import__("io").BytesIO(shot)).convert("RGB")
        ref_img = render_start_screen_reference(44)
        results.append(("start screen pixels == PIL reference",
                        diff_report(ref_img, shot_img, "start screen")))

        # ---- 3. jump + intro + running + score ----
        page.keyboard.press("Space")
        time.sleep(0.1)
        j1 = page.evaluate("() => Runner.instance_.tRex.jumping")
        results.append(("space starts jump", j1 is True))

        # wait for landing (intro should trigger after first jump)
        wait_for(lambda: page.evaluate(
            "() => Runner.instance_.tRex.jumpCount >= 1"), 5)
        intro = page.evaluate("""() => {
          const r = Runner.instance_;
          return {
            playingIntro: r.playingIntro,
            introClass: document.getElementById('runner-container')
              .classList.contains('intro'),
            activated: r.activated,
            xPos: r.tRex.xPos,
          };
        }""")
        results.append(("intro triggered after first jump", intro["playingIntro"]))
        results.append(("trex slides toward x=50 during intro", intro["xPos"] > 0))

        # wait for intro to finish and the game to be running
        wait_for(lambda: page.evaluate(
            "() => !Runner.instance_.playingIntro"), 3)
        time.sleep(0.4)
        run = page.evaluate("""() => {
          const r = Runner.instance_;
          return {playing: r.playing, speed: r.currentSpeed,
                  distance: r.distanceRan, status: r.tRex.status,
                  containerWidth: getComputedStyle(
                    document.getElementById('runner-container')).width};
        }""")
        results.append(("game running after intro", run["playing"] and
                        run["status"] == "RUNNING"))
        results.append(("container expanded to 600px",
                        run["containerWidth"] == "600px"))
        d1 = run["distance"]
        time.sleep(0.6)
        d2 = page.evaluate("() => Runner.instance_.distanceRan")
        results.append(("distance increases", d2 > d1))

        # running animation alternates frames
        frames = set()
        for _ in range(5):
            frames.add(page.evaluate(
                "() => Runner.instance_.tRex.currentFrame"))
            time.sleep(0.12)
        results.append(("run animation frames alternate",
                        len(frames) >= 2))

        # ---- 4. ducking ----
        page.keyboard.down("ArrowDown")
        time.sleep(0.2)
        duck = page.evaluate("""() => {
          const t = Runner.instance_.tRex;
          return {ducking: t.ducking, status: t.status,
                  boxes: t.getCollisionBoxes().length};
        }""")
        results.append(("down key ducks (hitbox switches)", duck["ducking"] and
                        duck["status"] == "DUCKING" and duck["boxes"] == 1))
        page.keyboard.up("ArrowDown")
        time.sleep(0.15)
        standing = page.evaluate("() => !Runner.instance_.tRex.ducking")
        results.append(("release down -> stand up", standing))

        # ---- 5. mid-air speed drop ----
        page.keyboard.press("Space")
        # 升空早期（明显高于地面）即按下方向键
        page.wait_for_function("() => Runner.instance_.tRex.yPos < 80",
                               timeout=2000)
        air_y = page.evaluate("() => Runner.instance_.tRex.yPos")
        page.keyboard.down("ArrowDown")
        time.sleep(0.08)
        drop = page.evaluate("""() => {
          const t = Runner.instance_.tRex;
          return {speedDrop: t.speedDrop, y: t.yPos, ducking: t.ducking};
        }""")
        print(f"speed-drop debug: air_y={air_y} drop={drop}")
        results.append(("mid-air down triggers speed drop",
                        drop["y"] > air_y and
                        (drop["speedDrop"] or drop["ducking"])))
        page.keyboard.up("ArrowDown")
        time.sleep(0.5)

        # ---- 6. obstacles spawn ----
        ok = wait_for(lambda: page.evaluate(
            "() => Runner.instance_.horizon.obstacles.length > 0"), 6)
        results.append(("obstacles spawn after clear time", ok))
        obs = page.evaluate("""() => {
          const o = Runner.instance_.horizon.obstacles[0];
          return o ? {type: o.typeConfig.type, x: o.xPos,
                      visible: o.xPos + o.width > 0} : null;
        }""")
        print("first obstacle:", obs)

        # ---- 7. night mode ----
        # 清空障碍物，避免测试期间被撞导致状态混乱
        page.evaluate("() => { Runner.instance_.horizon.obstacles = []; }")
        page.evaluate("() => { Runner.instance_.distanceRan = 28000; }")
        ok = wait_for(lambda: page.evaluate(
            "() => Runner.instance_.inverted"), 3)
        results.append(("night mode activates at 700 score", ok))
        time.sleep(0.6)
        # 固定月亮相位/位置和星星位置，确定性验证夜晚渲染
        page.evaluate("""() => {
          const nm = Runner.instance_.horizon.nightMode;
          nm.currentPhase = 3;      // 满月（40px 宽）
          nm.xPos = 40;
          nm.opacity = 1;
          nm.stars[0] = {x: 90, y: 40, sourceY: nm.stars[0].sourceY};
          nm.stars[1] = {x: 130, y: 55, sourceY: nm.stars[1].sourceY};
          nm.draw();
        }""")
        time.sleep(0.1)
        night = page.evaluate("""() => {
          const r = Runner.instance_;
          const c = r.canvas.getContext('2d').getImageData(5, 100, 1, 1).data;
          return {pixel: Array.from(c), inverted: r.inverted,
                  playing: r.playing, crashed: r.crashed};
        }""")
        print("night sample:", night)
        results.append(("night background inverted (#080808)",
                        night["pixel"][0] < 40 and night["pixel"][1] < 40 and
                        night["pixel"][2] < 40))
        night_shot = page.locator("#runner-canvas").screenshot()
        night_img = Image.open(__import__("io").BytesIO(night_shot)).convert("RGB")
        # 夜晚整页反色：月亮/星星精灵（浅灰）反色后为深灰，背景为近黑
        region = night_img.crop((40, 25, 175, 70))
        visible = sum(
            1 for px in region.getdata()
            if abs(px[0] - 8) > 20 or abs(px[1] - 8) > 20 or abs(px[2] - 8) > 20)
        # 背景应该仍然是深色
        bg_px = night_img.getpixel((5, 100))
        results.append(("moon/stars visible in night mode",
                        visible > 100 and bg_px[0] < 40))

        # ---- 8. pterodactyl spawn + animation ----
        ptero = page.evaluate("""() => {
          const r = Runner.instance_;
          for (let i = 0; i < 100; i++) {
            r.horizon.obstacles = [];
            r.horizon.addNewObstacle(9);
            const o = r.horizon.obstacles[0];
            if (o && o.typeConfig.type === 'pterodactyl') {
              o.xPos = 300;
              return {found: true, yPos: o.yPos, frame: o.currentFrame};
            }
          }
          return {found: false};
        }""")
        results.append(("pterodactyl spawns at speed >= 8.5", ptero["found"]))
        if ptero["found"]:
            time.sleep(0.2)
            ptero2 = page.evaluate("() => Runner.instance_.horizon.obstacles[0].currentFrame")
            results.append(("pterodactyl wings animate", ptero["frame"] != ptero2))

        # ---- 9. crash -> game over panel ----
        # 强制白天模式，保证面板以正常颜色渲染（可确定性检测）
        page.evaluate("""() => {
          const r = Runner.instance_;
          r.invert(true);
          r.invertTimer = 0;
          r.invertTrigger = false;
          r.distanceRan = 1000;
        }""")
        page.evaluate("""() => {
          const r = Runner.instance_;
          r.horizon.obstacles = [];
          r.horizon.addNewObstacle(r.currentSpeed);
          const o = r.horizon.obstacles[0];
          if (o) { o.xPos = 60; }
          r.runningTime = 5000;
        }""")
        ok = wait_for(lambda: page.evaluate(
            "() => Runner.instance_.crashed"), 3)
        results.append(("collision triggers game over", ok))
        time.sleep(1.2)  # let restart button animate
        go = page.evaluate("""() => {
          const r = Runner.instance_;
          return {panel: !!r.gameOverPanel,
                  crashed: r.crashed,
                  highScore: localStorage.getItem('tRexRunnerHighScore'),
                  inverted: r.inverted};
        }""")
        print("game over state:", go)
        results.append(("game over panel created", go["panel"] and go["crashed"]))
        go_shot = page.locator("#runner-canvas").screenshot()
        go_img = Image.open(__import__("io").BytesIO(go_shot)).convert("RGB")
        # GAME OVER text region (centered ~ y=42..53)
        text_region = go_img.crop((205, 42, 396, 53))
        dark = sum(1 for px in text_region.getdata() if px[0] < 120)
        print(f"game-over text dark px: {dark}")
        results.append(("GAME OVER text rendered", dark > 100))
        # restart button region (centered x=284..320, y=75..107)
        btn_region = go_img.crop((284, 75, 320, 107))
        dark_btn = sum(1 for px in btn_region.getdata() if px[0] < 120)
        light_btn = sum(1 for px in btn_region.getdata() if px[0] > 180)
        print(f"restart button dark px: {dark_btn}, light px: {light_btn}")
        # the complete button is a dark rounded rect with a light arrow;
        # a tiny arc (stuck animation frame) or a solid block would fail this
        results.append(("restart button shows complete icon",
                        700 < dark_btn < 1150 and light_btn > 100))
        results.append(("high score saved", go["highScore"] is not None))

        # ---- 10. restart via Enter ----
        page.keyboard.press("Enter")
        time.sleep(0.3)
        rst = page.evaluate("""() => {
          const r = Runner.instance_;
          return {crashed: r.crashed, playing: r.playing,
                  distance: r.distanceRan, speed: r.currentSpeed};
        }""")
        results.append(("Enter restarts the game", not rst["crashed"] and
                        rst["playing"] and rst["distance"] < 400))

        # ---- 11. blur pauses / focus resumes ----
        page.evaluate("() => window.dispatchEvent(new Event('blur'))")
        time.sleep(0.2)
        paused = page.evaluate("() => Runner.instance_.paused")
        results.append(("blur pauses game", paused))
        page.evaluate("() => window.dispatchEvent(new Event('focus'))")
        time.sleep(0.3)
        resumed = page.evaluate("() => Runner.instance_.playing")
        results.append(("focus resumes game", resumed))

        browser.close()

    print("\n=== console errors ===")
    for err in console_errors:
        print("ERR:", err)
    print(f"({len(console_errors)} errors)")

    print("\n=== results ===")
    failed = 0
    for name, ok in results:
        print(("PASS" if ok else "FAIL"), "-", name)
        if not ok:
            failed += 1
    print(f"\n{len(results) - failed}/{len(results)} passed")
    sys.exit(1 if failed or console_errors else 0)


if __name__ == "__main__":
    main()
