#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the self-contained index.html by inlining sprite sheets and sounds."""

import base64
from pathlib import Path

ROOT = Path(__file__).resolve().parent

TEMPLATE = ROOT / "game.template.html"
OUTPUT = ROOT / "index.html"

ASSETS = {
    "__SPRITE_1X__": ROOT / "reference" / "sprite_1x.png",
    "__SPRITE_2X__": ROOT / "reference" / "sprite_2x.png",
    "__SND_PRESS__": ROOT / "reference" / "button-press.mp3",
    "__SND_HIT__": ROOT / "reference" / "hit.mp3",
    "__SND_SCORE__": ROOT / "reference" / "score-reached.mp3",
}


def main() -> None:
    html = TEMPLATE.read_text(encoding="utf-8")
    for placeholder, path in ASSETS.items():
        assert placeholder in html, f"missing placeholder {placeholder}"
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        html = html.replace(placeholder, data)
    OUTPUT.write_text(html, encoding="utf-8")
    print(f"built {OUTPUT} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
