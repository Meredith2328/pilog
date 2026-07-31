#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate fine-grained pixel-art SVG details (banner + side decorations).

All art uses the site palette and 3-4px cells, rendered as crisp rects —
the same fine-grained approach as the dino sprite itself.
"""

from __future__ import annotations

import math
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "generator" / "static" / "img"

P = "#f7f7f7"   # paper
L = "#e8eaed"   # light
H = "#dadce0"   # hairline
M = "#9aa0a6"   # mute
T = "#5f6368"   # text
K = "#3c4043"   # ink
Y = "#fbbc04"   # sun


def svg_open(width: int, height: int) -> list:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        'shape-rendering="crispEdges">'
    ]


def rects_from_map(rows: list, cell: int, ox: int, oy: int, color: str) -> list:
    out = []
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in (" ", "."):
                continue
            out.append(f'<rect x="{ox + x * cell}" y="{oy + y * cell}" '
                       f'width="{cell}" height="{cell}" fill="{color}"/>')
    return out


def ridge(cell: int, x0: int, x1: int, base: int, amp: int,
          freq: float, phase: float, color: str) -> list:
    """A stepped mountain ridge; heights quantized to 2-cell pixel steps."""
    out = []
    for cx in range(x0, x1):
        h = base - 2 * int((math.sin(cx * freq + phase) + 1) / 2 * amp / 2)
        h = max(0, h)
        out.append(f'<rect x="{cx * cell}" y="{h * cell}" width="{cell}" '
                   f'height="{(base - h) * cell}" fill="{color}"/>')
    return out


def bird(cell: int, x: int, y: int, color: str = M) -> list:
    return rects_from_map(["k...k", ".k.k.", "..k.."], cell, x, y, color)


DINO = [
    "....######....",
    "...########...",
    "...####.####..",
    "..####..####..",
    "..##########..",
    "..##......##..",
    "..##......##..",
    "..##......##..",
    ".###########..",
    "..####..####..",
]

CACTUS = [
    "...k...",
    "...k.k.",
    "...k.k.",
    "..kkkk.",
    "...k...",
    "...k...",
]


def banner() -> str:
    cell = 4
    W, H = 800, 120
    lines = svg_open(W, H)
    lines.append(f'<rect width="{W}" height="{H}" fill="{P}"/>')
    # three fine mountain layers (drawn first, sky elements above)
    # integer wave periods (2/3/4 across 200 cells) -> tiles seamlessly
    lines += ridge(cell, 0, 200, 30, 18, 2 * math.pi * 2 / 200, 0.0, L)
    lines += ridge(cell, 0, 200, 30, 12, 2 * math.pi * 3 / 200, 1.3, H)
    lines += ridge(cell, 0, 200, 30, 7, 2 * math.pi * 4 / 200, 2.6, L)
    # ground dashes
    for x in range(0, 800, 16):
        lines.append(f'<rect x="{x}" y="114" width="8" height="2" fill="{K}"/>')
    # sun with rays
    lines.append(f'<rect x="684" y="20" width="36" height="36" fill="{Y}"/>')
    lines += [
        f'<rect x="700" y="12" width="4" height="8" fill="{Y}"/>',
        f'<rect x="700" y="56" width="4" height="8" fill="{Y}"/>',
        f'<rect x="676" y="34" width="8" height="4" fill="{Y}"/>',
        f'<rect x="720" y="34" width="8" height="4" fill="{Y}"/>',
    ]
    # clouds (fine 4px puffs)
    clouds = [
        (90, 22, 16), (150, 34, 12), (430, 18, 14), (540, 40, 10),
    ]
    for x, y, w in clouds:
        lines.append(f'<rect x="{x}" y="{y + 8}" width="{w * 4}" height="8" fill="{L}"/>')
        lines.append(f'<rect x="{x + 8}" y="{y + 4}" width="{(w - 4) * 4}" height="4" fill="{L}"/>')
        lines.append(f'<rect x="{x + 16}" y="{y}" width="{(w - 8) * 4}" height="4" fill="{L}"/>')
    # cacti
    lines += rects_from_map(CACTUS, 3, 152, 96, T)
    lines += rects_from_map(CACTUS, 3, 596, 92, T)
    # the dino (fine-grained, standing on the ground)
    lines += rects_from_map(DINO, 3, 240, 84, K)
    # birds (in the sky, above mountains)
    lines += bird(3, 300, 44)
    lines += bird(3, 352, 34)
    lines += bird(3, 470, 54)
    lines.append("</svg>")
    return "\n".join(lines)


TREE = [
    "....kk....",
    "...kkkk...",
    "..kkkkkk..",
    ".kkkkkkkk.",
    "..kkkkkk..",
    "...kkkk...",
    "....kk....",
    "....kk....",
    "....kk....",
]


def deco_left() -> str:
    cell = 3
    W, H = 120, 260
    lines = svg_open(W, H)
    lines.append(f'<rect width="{W}" height="{H}" fill="{P}"/>')
    # star
    lines += rects_from_map(["..k..", ".kkk.", "k.k.k", ".kkk.", "..k.."], cell, 84, 14, M)
    # small cloud
    lines += rects_from_map(
        ["..lll..", ".lllll.", "lllllll"], cell, 18, 30, L
    )
    # tall cactus
    lines += rects_from_map(
        [
            "....t....",
            "....t....",
            "....t.t..",
            "....t.t..",
            "....ttt..",
            "..ttttt..",
            "....t....",
            "....t....",
            "....t....",
            "....t....",
            "....t....",
            "....t....",
            "....t....",
            "....t....",
            "...ttt...",
        ],
        cell, 30, 96, T,
    )
    # ground
    lines += rects_from_map(
        ["h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h"],
        cell, 0, 84, H,
    )
    lines.append("</svg>")
    return "\n".join(lines)


def deco_right() -> str:
    cell = 3
    W, H = 120, 260
    lines = svg_open(W, H)
    lines.append(f'<rect width="{W}" height="{H}" fill="{P}"/>')
    # moon (crescent in mute tones)
    lines += rects_from_map(
        [
            "...kkk...",
            "..k...k..",
            ".k.....k.",
            ".k...k.k.",
            "k.....k..",
            "k....k...",
            "k...k....",
            ".k..k....",
            ".k..k....",
            "..k......",
            "...k.....",
        ],
        cell, 84, 12, M,
    )
    # stars
    lines += rects_from_map(["..k..", "k.k.k", "..k.."], cell, 16, 20, L)
    lines += rects_from_map(["k.k", ".k.", "k.k"], cell, 60, 52, L)
    # pixel tree
    lines += rects_from_map(TREE, cell, 44, 96, T)
    # small bird
    lines += bird(cell, 76, 92, M)
    # ground
    lines += rects_from_map(
        ["h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h.h"],
        cell, 0, 84, H,
    )
    lines.append("</svg>")
    return "\n".join(lines)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in [
        ("banner-default.svg", banner),
        ("deco-left.svg", deco_left),
        ("deco-right.svg", deco_right),
    ]:
        (OUT / name).write_text(fn(), encoding="utf-8")
        print("wrote", OUT / name)


if __name__ == "__main__":
    main()
