#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compose the sample pixel-art cover (dino scene) used by demo posts.

The dino sprite is cropped from Chromium's 100-offline-sprite-2x.png
(BSD-3-Clause, part of the bundled dino game assets).
"""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SPRITE = ROOT / "dino" / "reference" / "sprite_2x.png"
OUT = ROOT / "blogs" / "assets" / "cover-pixel.png"

BG = (247, 247, 247)
DARK = (60, 64, 67)
MID = (95, 99, 104)
LIGHT = (218, 220, 224)
ACCENT = (26, 115, 232)

TREX_BOX = (76, 4, 164, 100)  # cropped from the 2x sprite sheet


def cactus(x: int, y: int, draw: ImageDraw.ImageDraw) -> None:
    """A small pixel cactus, game-style."""
    body = [(x, y), (x + 4, y), (x + 4, y + 18), (x, y + 18)]
    draw.rectangle([x, y, x + 3, y + 17], fill=DARK)
    draw.rectangle([x + 4, y + 2, x + 9, y + 5], fill=DARK)
    draw.rectangle([x + 7, y + 5, x + 10, y + 14], fill=DARK)


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    W, H = 384, 256
    img = Image.new("RGBA", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # Pixel sun (top right)
    sun = (W - 76, 40)
    draw.rectangle([sun[0], sun[1], sun[0] + 23, sun[1] + 23], fill=ACCENT)

    # Cloud (light gray, game-style)
    draw.rectangle([150, 58, 214, 61], fill=MID)
    draw.rectangle([156, 50, 205, 57], fill=MID)

    # Ground: dashes like the game's ground line
    y_ground = 214
    x = 0
    while x < W:
        draw.rectangle([x, y_ground, x + 7, y_ground + 1], fill=DARK)
        x += 12

    # Cacti
    cactus(24, y_ground - 34, draw)
    cactus(W - 64, y_ground - 40, draw)

    # The dino itself
    trex = Image.open(SPRITE).convert("RGBA").crop(TREX_BOX)
    img.paste(trex, (118, y_ground - trex.height + 6), trex)

    img.convert("RGB").save(OUT, "PNG")
    print(f"wrote {OUT} ({img.size})")


if __name__ == "__main__":
    main()
