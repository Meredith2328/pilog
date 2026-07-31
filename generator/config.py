from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


DEFAULTS: dict = {
    "site": {
        "title": "MEREDITH'S LOG",
        "subtitle": "pixel · minimal · notes",
        "author": "Meredith",
        "language": "zh-CN",
        "blog_dir": "blogs",
        "out_dir": "site",
        "base_path": "",
        "site_url": "",
        "use_google_fonts": True,
        "footer_text": "",
        "show_dino": True,
        "cards_per_page": 12,
        "collapse_threshold": 25,
    },
    "giscus": {
        "enabled": False,
        "repo": "",
        "repo_id": "",
        "category": "Announcements",
        "category_id": "",
        "mapping": "pathname",
        "strict": "0",
        "reactions": "1",
        "emit_metadata": "0",
        "input_position": "top",
        "lang": "zh-CN",
    },
    "socials": {},
}


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            out[key] = _merge(base[key], value)
        else:
            out[key] = value
    return out


@dataclass
class Config:
    raw: dict
    root: Path

    @property
    def site(self) -> dict:
        return self.raw["site"]

    @property
    def blog_dir(self) -> Path:
        return (self.root / self.site["blog_dir"]).resolve()

    @property
    def out_dir(self) -> Path:
        return (self.root / self.site["out_dir"]).resolve()

    @property
    def base_path(self) -> str:
        bp = self.site.get("base_path", "").strip()
        if bp and not bp.startswith("/"):
            bp = "/" + bp
        return bp.rstrip("/")

    @property
    def site_url(self) -> str:
        return self.site.get("site_url", "").rstrip("/")

    @property
    def giscus(self) -> dict:
        return self.raw.get("giscus", {})

    @property
    def socials(self) -> dict:
        return self.raw.get("socials", {})

    def show_dino(self) -> bool:
        return bool(self.site.get("show_dino", True))

    @classmethod
    def load(cls, path: Path) -> "Config":
        root = path.resolve().parent
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raw = {}
        merged = _merge(DEFAULTS, raw)
        return cls(raw=merged, root=root)
