#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke-test the hiDPI path + audio decoding, and save preview screenshots."""

import io
import time
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "preview"


def main():
    OUT.mkdir(exist_ok=True)
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        # ---- hiDPI (deviceScaleFactor=2) smoke test ----
        page = browser.new_page(viewport={"width": 1000, "height": 800},
                                device_scale_factor=2)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text)
                if m.type == "error" else None)
        page.goto((ROOT / "index.html").as_uri())
        page.wait_for_function("window.Runner && Runner.instance_ && Runner.instance_.tRex")
        info = page.evaluate("""() => {
          const c = document.getElementById('runner-canvas');
          return {width: c.width, height: c.height,
                  cssWidth: getComputedStyle(c).width};
        }""")
        assert info["width"] == 1200 and info["height"] == 300, info
        print("hiDPI ok:", info)
        page.screenshot(path=str(OUT / "start_hidpi.png"))

        # 开始游戏，验证音频解码 + 跑动画面
        page.keyboard.press("Space")
        time.sleep(2.2)
        audio = page.evaluate("() => window.__getAudioState()")
        assert audio["ctx"] and audio["loaded"] == 3, audio
        print("audio decoded ok:", audio)
        page.screenshot(path=str(OUT / "running_hidpi.png"))

        # 夜晚模式截图
        page.evaluate("() => { Runner.instance_.distanceRan = 28000; }")
        time.sleep(1.2)
        page.screenshot(path=str(OUT / "night_hidpi.png"))
        browser.close()

        # ---- 1x 预览图（供 README / 展示）----
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1000, "height": 800})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto((ROOT / "index.html").as_uri())
        page.wait_for_function("window.Runner && Runner.instance_ && Runner.instance_.tRex")
        # 开场画面（保留 44px 窄条，与真实游戏一致）
        page.screenshot(path=str(OUT / "start.png"))
        # 展开画面：强制容器宽度并冻结
        page.evaluate("""() => {
          const r = Runner.instance_;
          cancelAnimationFrame(r.raqId);
          r.raqId = 0;
          document.getElementById('runner-container').style.width = '600px';
        }""")
        page.locator("#runner-canvas").screenshot(
            path=str(OUT / "start_full.png"))
        # 游戏中
        page.keyboard.press("Space")
        time.sleep(1.4)
        page.locator("#runner-canvas").screenshot(
            path=str(OUT / "running.png"))
        # 游戏结束
        page.evaluate("""() => {
          const r = Runner.instance_;
          r.horizon.obstacles = [];
          r.horizon.addNewObstacle(r.currentSpeed);
          const o = r.horizon.obstacles[0];
          o.xPos = 60;
          r.runningTime = 5000;
        }""")
        time.sleep(1.5)
        page.locator("#runner-canvas").screenshot(
            path=str(OUT / "gameover.png"))
        browser.close()

    print("errors:", errors)
    assert not errors, errors
    for f in sorted(OUT.glob("*.png")):
        im = Image.open(f)
        print(f.name, im.size)


if __name__ == "__main__":
    main()
