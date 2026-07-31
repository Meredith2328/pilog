#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pilog 本地开发服务器 + 图片工作台 + 所见即所得编辑器。

用法:
    python serve.py              # 打开 http://127.0.0.1:8000/
    python serve.py --watch      # 监视 blogs/，改动后自动重新构建
    python serve.py --port 9000

工作台(仅本机可访问): http://127.0.0.1:8000/manager
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import re
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import yaml
from PIL import Image

from build import build_site
from generator.assets import AssetMap
from generator.config import Config
from generator.content import scan_posts, sorted_for_cards, split_front_matter
from generator.markdownx import MarkdownContext, find_asset


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
MANAGER_HTML = ROOT / "tools" / "manager.html"

_dirty = False
_mutex = threading.Lock()

# undo / redo stacks: {"before": [(Path, bytes|None)...], "after": [...]}
_undo: list = []
_redo: list = []


def log(msg: str) -> None:
    print(f"[pilog] {msg}", flush=True)


def rebuild(clean: bool = False) -> float:
    t0 = time.perf_counter()
    build_site(CONFIG_PATH, clean=clean)
    return time.perf_counter() - t0


def fingerprint() -> str:
    cfg = Config.load(CONFIG_PATH)
    blog_root = cfg.blog_dir
    h = hashlib.sha1()

    def add(path: Path) -> None:
        if path.is_file():
            h.update(str(path).encode("utf-8"))
            h.update(str(path.stat().st_mtime_ns).encode("utf-8"))
            h.update(str(path.stat().st_size).encode("utf-8"))

    add(CONFIG_PATH)
    add(ROOT / "build.py")
    for py in (ROOT / "generator").rglob("*.py"):
        add(py)
    for tpl in (ROOT / "generator" / "templates").rglob("*"):
        add(tpl)
    for st in (ROOT / "generator" / "static").rglob("*"):
        add(st)
    if blog_root.is_dir():
        for f in blog_root.rglob("*"):
            if f.is_file() and ".git" not in f.parts:
                add(f)
    return h.hexdigest()


def watch_loop(interval: float = 1.5) -> None:
    global _dirty
    last = fingerprint()
    rebuild()
    while True:
        time.sleep(interval)
        try:
            changed = _dirty or fingerprint() != last
        except OSError:
            changed = False
        if changed:
            _dirty = False
            last = fingerprint()
            log("change detected, rebuilding…")
            rebuild()


# ---------------------------------------------------------------------------
# undo / redo helpers
# ---------------------------------------------------------------------------


def _read_bytes(p: Path):
    return p.read_bytes() if p.exists() else None


def _snap(*paths: Path) -> list:
    return [(p, _read_bytes(p)) for p in paths]


def _record_change(before: list, after: list, label: str = "") -> None:
    _undo.append({"label": label, "before": before, "after": after})
    del _redo[:]
    if len(_undo) > 100:
        _undo.pop(0)


def _apply_snapshot(snapshot: list) -> list:
    changed = []
    for p, data in snapshot:
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        if data is None:
            if p.exists():
                p.unlink()
            changed.append({"path": rel, "action": "deleted"})
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
            changed.append({"path": rel, "action": "restored"})
    return changed


def _files_list(snapshot: list) -> list:
    return [
        {"path": str(p.relative_to(ROOT)).replace("\\", "/"), "action": "modified"}
        for p, _ in snapshot
    ]


# ---------------------------------------------------------------------------
# content helpers
# ---------------------------------------------------------------------------


def _blog_ctx() -> MarkdownContext:
    cfg = Config.load(CONFIG_PATH)
    return MarkdownContext(
        blog_root=cfg.blog_dir,
        assets=AssetMap(blog_root=cfg.blog_dir, out_root=cfg.blog_dir),
        base_path=cfg.base_path,
    )


def _update_front_matter(path: Path, updates: dict) -> None:
    text = path.read_text(encoding="utf-8")
    fm, body = split_front_matter(text)
    for key, value in updates.items():
        if value is None:
            fm.pop(key, None)
        else:
            fm[key] = value
    head = (
        "---\n"
        + yaml.safe_dump(
            fm, allow_unicode=True, sort_keys=False, default_flow_style=False
        ).strip()
        + "\n---\n"
    )
    path.write_text(head + body, encoding="utf-8")


def _first_image(post) -> str | None:
    ctx = _blog_ctx()
    if post.preview_image:
        found = find_asset(post.preview_image, post.src, ctx)
        if found:
            return found.relative_to(ctx.blog_root).as_posix()
    text = post.src.read_text(encoding="utf-8", errors="replace")
    for m in re.finditer(r"!\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]", text):
        found = find_asset(m.group(1).strip(), post.src, ctx)
        if found:
            return found.relative_to(ctx.blog_root).as_posix()
    for m in re.finditer(r"!\[[^\]]*\]\(([^)]+)\)", text):
        cand = m.group(1).strip()
        if cand.startswith(("http", "data:")):
            continue
        p = (post.src.parent / cand).resolve()
        if p.is_file():
            return p.relative_to(ctx.blog_root).as_posix()
        p2 = (ctx.blog_root / cand).resolve()
        if p2.is_file():
            return p2.relative_to(ctx.blog_root).as_posix()
    return None


def _post_payload(post) -> dict:
    return {
        "rel": post.rel,
        "url": post.url,
        "title": post.title,
        "date": post.date_str,
        "tags": post.tags,
        "folder": post.folder,
        "pin": post.pin,
        "highlight": post.highlight,
        "order": post.order,
        "preview": post.preview_plain[:160],
        "image": _first_image(post),
        "file": post.rel + ".md",
    }


def _parse_nav(text: str) -> list:
    items: list = []
    stack: list = []
    for line in text.splitlines():
        m = re.match(r"^(\s*)- \[([^\]]+)\]\(([^)]+)\)\s*$", line)
        if not m:
            continue
        indent = len(m.group(1))
        item = {"label": m.group(2), "href": m.group(3), "children": []}
        while stack and stack[-1][0] >= indent:
            stack.pop()
        if stack:
            stack[-1][1]["children"].append(item)
        else:
            items.append(item)
        stack.append((indent, item))
    return items


def _serialize_nav(items: list, indent: int = 0) -> str:
    pad = "  " * indent
    lines = []
    for it in items:
        lines.append(f"{pad}- [{it['label']}]({it['href']})")
        lines.extend(_serialize_nav(it.get("children", []), indent + 1))
    return "\n".join(lines) + ("\n" if lines else "")


# ---------------------------------------------------------------------------
# handler
# ---------------------------------------------------------------------------


class Handler(SimpleHTTPRequestHandler):
    server_version = "pilog-dev"

    def __init__(self, *args, **kwargs):
        self.cfg = Config.load(CONFIG_PATH)
        self.blog_root = self.cfg.blog_dir
        self.out_root = self.cfg.out_dir
        self.cache_dir = ROOT / ".cache" / "manager"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        super().__init__(*args, directory=str(self.out_root), **kwargs)

    # ---------- helpers ----------

    def _is_local(self) -> bool:
        host = self.client_address[0] if self.client_address else ""
        return host in ("127.0.0.1", "::1", "localhost")

    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, data: bytes, ctype: str):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _safe_blog_path(self, rel: str) -> Path | None:
        p = (self.blog_root / rel).resolve()
        if p == self.blog_root or p.is_relative_to(self.blog_root.resolve()):
            return p
        return None

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return b""
        return self.rfile.read(length)

    def _read_json(self):
        raw = self._read_body()
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None

    def _mutating(self) -> bool:
        if not self._is_local():
            self._send_json(
                {"ok": False, "error": "仅本机可访问（local only）"}, 403
            )
            return False
        return True

    # ---------- routing ----------

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path in ("/manager", "/manager/"):
            if not self._mutating():
                return
            self._serve_manager()
            return
        if path.startswith("/api/"):
            if not self._mutating():
                return
            self._api_get(path, qs)
            return
        super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/"):
            if not self._mutating():
                return
            self._api_post(self.path)
            return
        self._send_json({"ok": False, "error": "not found"}, 404)

    def do_DELETE(self):
        if self.path.startswith("/api/"):
            if not self._mutating():
                return
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            self._api_delete(parsed.path, qs)
            return
        self._send_json({"ok": False, "error": "not found"}, 404)

    # ---------- GET api ----------

    def _api_get(self, path: str, qs: dict):
        if path == "/api/config":
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            self._send_json(
                {"ok": True, "config": cfg, "path": "config.json"}
            )
            return
        if path == "/api/nav":
            nav_file = self.blog_root / "nav.md"
            items = (
                _parse_nav(nav_file.read_text(encoding="utf-8"))
                if nav_file.exists()
                else []
            )
            self._send_json(
                {"ok": True, "items": items, "path": "blogs/nav.md"}
            )
            return
        if path == "/api/posts":
            ctx = _blog_ctx()
            posts = scan_posts(self.blog_root, ctx)
            payload = [
                _post_payload(p) for p in sorted_for_cards(posts)
            ]
            self._send_json({"ok": True, "posts": payload})
            return
        if path == "/api/post/source":
            rel = qs.get("rel", [""])[0]
            p = self._safe_blog_path(rel + ".md")
            if p is None or not p.is_file():
                self._send_json({"ok": False, "error": "post not found"}, 404)
                return
            self._send_json(
                {"ok": True, "source": p.read_text(encoding="utf-8"),
                 "path": "blogs/" + rel + ".md"}
            )
            return
        if path == "/api/brand":
            self._send_json(
                {
                    "ok": True,
                    "logo": (self.blog_root / "assets" / "logo.png").exists(),
                    "header": (self.blog_root / "assets" / "header.png").exists(),
                    "paths": {
                        "logo": "blogs/assets/logo.png",
                        "header": "blogs/assets/header.png",
                    },
                }
            )
            return
        if path == "/api/tree":
            self._api_tree()
            return
        if path == "/api/list":
            self._api_list(qs.get("dir", [""])[0])
            return
        if path == "/api/thumb":
            self._api_thumb(qs.get("path", [""])[0])
            return
        if path == "/api/file":
            self._api_file(qs.get("path", [""])[0])
            return
        self._send_json({"ok": False, "error": "not found"}, 404)

    # ---------- POST api ----------

    def _api_post(self, path: str):
        if path == "/api/undo":
            self._api_undo()
            return
        if path == "/api/redo":
            self._api_redo()
            return
        if path == "/api/config":
            self._api_config()
            return
        if path == "/api/nav":
            self._api_nav()
            return
        if path == "/api/post/meta":
            self._api_post_meta()
            return
        if path == "/api/post/source":
            self._api_post_source()
            return
        if path == "/api/posts/order":
            self._api_posts_order()
            return
        if path == "/api/brand":
            self._api_brand_upload()
            return
        if path == "/api/rebuild":
            duration = rebuild()
            self._send_json({"ok": True, "duration": round(duration, 2)})
            return
        if path == "/api/upload":
            self._api_upload()
            return
        self._send_json({"ok": False, "error": "not found"}, 404)

    def _api_delete(self, path: str, qs: dict):
        if path == "/api/file":
            self._api_delete_file(qs.get("path", [""])[0])
            return
        if path == "/api/brand":
            self._api_brand_delete(qs.get("kind", [""])[0])
            return
        self._send_json({"ok": False, "error": "not found"}, 404)

    # ---------- config / nav / posts ----------

    def _api_config(self):
        body = self._read_json()
        if not body or "updates" not in body:
            self._send_json({"ok": False, "error": "bad payload"}, 400)
            return
        target = CONFIG_PATH
        before = _snap(target)
        cfg = json.loads(target.read_text(encoding="utf-8"))

        def merge(base: dict, upd: dict):
            for k, v in upd.items():
                if isinstance(v, dict) and isinstance(base.get(k), dict):
                    merge(base[k], v)
                else:
                    base[k] = v

        merge(cfg, body["updates"])
        target.write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        after = _snap(target)
        _record_change(before, after, "config.json")
        _dirty = True
        self._send_json(
            {"ok": True, "files": _files_list(after), "config": cfg}
        )

    def _api_nav(self):
        body = self._read_json()
        if not body or "items" not in body:
            self._send_json({"ok": False, "error": "bad payload"}, 400)
            return
        target = self.blog_root / "nav.md"
        before = _snap(target)
        target.write_text(
            "# 导航\n\n" + _serialize_nav(body["items"]), encoding="utf-8"
        )
        after = _snap(target)
        _record_change(before, after, "blogs/nav.md")
        _dirty = True
        self._send_json(
            {"ok": True, "files": _files_list(after), "items": body["items"]}
        )

    def _api_post_meta(self):
        body = self._read_json()
        rel = (body or {}).get("rel", "")
        updates = (body or {}).get("updates", {})
        if not rel or not updates:
            self._send_json({"ok": False, "error": "bad payload"}, 400)
            return
        p = self._safe_blog_path(rel + ".md")
        if p is None or not p.is_file():
            self._send_json({"ok": False, "error": "post not found"}, 404)
            return
        before = _snap(p)
        _update_front_matter(p, updates)
        after = _snap(p)
        _record_change(before, after, "blogs/" + rel + ".md")
        _dirty = True
        self._send_json(
            {"ok": True, "files": _files_list(after)}
        )

    def _api_post_source(self):
        body = self._read_json()
        rel = (body or {}).get("rel", "")
        source = (body or {}).get("source", "")
        if not rel or not isinstance(source, str):
            self._send_json({"ok": False, "error": "bad payload"}, 400)
            return
        p = self._safe_blog_path(rel + ".md")
        if p is None or not p.is_file():
            self._send_json({"ok": False, "error": "post not found"}, 404)
            return
        before = _snap(p)
        p.write_text(source, encoding="utf-8")
        after = _snap(p)
        _record_change(before, after, "blogs/" + rel + ".md")
        _dirty = True
        self._send_json({"ok": True, "files": _files_list(after)})

    def _api_posts_order(self):
        """body: {"items": [{"rel": ..., "pin": bool}...]} — full desired order."""
        body = self._read_json()
        items = (body or {}).get("items")
        if not isinstance(items, list):
            self._send_json({"ok": False, "error": "bad payload"}, 400)
            return
        before: list = []
        after: list = []
        changed: list = []
        for index, item in enumerate(items):
            rel = str(item.get("rel", ""))
            pin = bool(item.get("pin", False))
            p = self._safe_blog_path(rel + ".md")
            if p is None or not p.is_file():
                continue
            fm, _ = split_front_matter(p.read_text(encoding="utf-8"))
            if fm.get("pin", False) == pin and fm.get("order") == index:
                continue
            before.append((p, _read_bytes(p)))
            _update_front_matter(p, {"pin": pin, "order": index})
            after.append((p, _read_bytes(p)))
            changed.append(
                {"path": "blogs/" + rel + ".md", "action": "modified"}
            )
        if before:
            _record_change(before, after, "post order")
            _dirty = True
        self._send_json({"ok": True, "files": changed})

    # ---------- brand / logo / header ----------

    def _api_brand_upload(self):
        kind = (self.headers.get("X-Kind") or "").strip().lower()
        if kind not in ("logo", "header"):
            self._send_json({"ok": False, "error": "kind must be logo|header"}, 400)
            return
        body = self._read_body()
        if not body:
            self._send_json({"ok": False, "error": "empty body"}, 400)
            return
        assets = self.blog_root / "assets"
        assets.mkdir(parents=True, exist_ok=True)
        target = assets / f"{kind}.png"
        before = _snap(target)
        target.write_bytes(body)
        after = _snap(target)
        _record_change(before, after, f"blogs/assets/{kind}.png")
        _dirty = True
        self._send_json(
            {
                "ok": True,
                "kind": kind,
                "files": _files_list(after),
                "path": f"blogs/assets/{kind}.png",
            }
        )

    def _api_brand_delete(self, kind: str):
        if kind not in ("logo", "header"):
            self._send_json({"ok": False, "error": "kind must be logo|header"}, 400)
            return
        target = self.blog_root / "assets" / f"{kind}.png"
        if not target.is_file():
            self._send_json({"ok": True, "files": []})
            return
        before = _snap(target)
        target.unlink()
        after = _snap(target)
        _record_change(before, after, f"blogs/assets/{kind}.png")
        _dirty = True
        self._send_json(
            {
                "ok": True,
                "kind": kind,
                "files": [
                    {"path": f"blogs/assets/{kind}.png", "action": "deleted"}
                ],
            }
        )

    # ---------- undo / redo ----------

    def _api_undo(self):
        if not _undo:
            self._send_json({"ok": True, "files": []})
            return
        entry = _undo.pop()
        changed = _apply_snapshot(entry["before"])
        _redo.append(entry)
        _dirty = True
        self._send_json({"ok": True, "files": changed, "label": entry.get("label", "")})

    def _api_redo(self):
        if not _redo:
            self._send_json({"ok": True, "files": []})
            return
        entry = _redo.pop()
        changed = _apply_snapshot(entry["after"])
        _undo.append(entry)
        _dirty = True
        self._send_json({"ok": True, "files": changed, "label": entry.get("label", "")})

    # ---------- pages / images ----------

    def _serve_manager(self):
        global _mutex
        if not MANAGER_HTML.exists():
            self._send_json({"ok": False, "error": "manager.html missing"}, 404)
            return
        with _mutex:
            html = MANAGER_HTML.read_text(encoding="utf-8")
        self._send_bytes(html.encode("utf-8"), "text/html; charset=utf-8")

    def _api_tree(self):
        def walk(d: Path) -> list:
            out = []
            for sub in sorted(d.iterdir(), key=lambda p: p.name.lower()):
                if sub.is_dir() and not sub.name.startswith((".", "_")):
                    rel = sub.relative_to(self.blog_root).as_posix()
                    out.append(
                        {"name": sub.name, "path": rel, "children": walk(sub)}
                    )
            return out

        self._send_json(
            {
                "ok": True,
                "root": str(self.blog_root),
                "dirs": walk(self.blog_root),
            }
        )

    def _api_list(self, dir_rel: str):
        d = self._safe_blog_path(dir_rel)
        if d is None or not d.is_dir():
            self._send_json({"ok": False, "error": "invalid dir"}, 400)
            return
        images, dirs = [], []
        for item in sorted(d.iterdir(), key=lambda p: p.name.lower()):
            if item.is_dir() and not item.name.startswith((".", "_")):
                dirs.append(item.name)
            elif item.is_file() and item.suffix.lower() in IMAGE_EXTS:
                rel = item.relative_to(self.blog_root).as_posix()
                images.append(
                    {
                        "name": item.name,
                        "path": rel,
                        "size": item.stat().st_size,
                        "mtime": int(item.stat().st_mtime),
                    }
                )
        self._send_json(
            {
                "ok": True,
                "dir": dir_rel,
                "dirs": dirs,
                "images": images,
                "root": str(self.blog_root),
            }
        )

    def _api_thumb(self, path_rel: str):
        p = self._safe_blog_path(path_rel)
        if p is None or not p.is_file():
            self._send_json({"ok": False, "error": "file not found"}, 404)
            return
        try:
            img = Image.open(p)
            img.thumbnail((180, 180))
            out = img.convert("RGB")
            self._send_bytes(io_bytes(out, "JPEG"), "image/jpeg")
        except OSError:
            self._send_json({"ok": False, "error": "not an image"}, 400)

    def _api_file(self, path_rel: str):
        p = self._safe_blog_path(path_rel)
        if p is None or not p.is_file():
            self._send_json({"ok": False, "error": "file not found"}, 404)
            return
        ctype, _ = mimetypes.guess_type(p.name)
        self._send_bytes(p.read_bytes(), ctype or "application/octet-stream")

    def _api_upload(self):
        folder = self.headers.get("X-Folder") or ""
        name = Path(self.headers.get("X-Filename") or "").name
        replace = (self.headers.get("X-Replace") or "0") == "1"
        if not name:
            self._send_json({"ok": False, "error": "missing filename"}, 400)
            return
        d = self._safe_blog_path(folder)
        if d is None or not d.is_dir():
            self._send_json({"ok": False, "error": "invalid folder"}, 400)
            return
        body = self._read_body()
        if not body:
            self._send_json({"ok": False, "error": "empty body"}, 400)
            return
        target = d / name
        if target.exists() and not replace:
            stem, suffix = target.stem, target.suffix
            i = 2
            while (d / f"{stem}-{i}{suffix}").exists():
                i += 1
            target = d / f"{stem}-{i}{suffix}"
        before = _snap(target)
        target.write_bytes(body)
        after = _snap(target)
        _record_change(before, after, "upload")
        _dirty = True
        rel = target.relative_to(self.blog_root).as_posix()
        self._send_json(
            {
                "ok": True,
                "name": target.name,
                "path": rel,
                "replaced": replace,
                "files": _files_list(after),
            }
        )

    def _api_delete_file(self, path_rel: str):
        p = self._safe_blog_path(path_rel)
        if p is None or not p.is_file():
            self._send_json({"ok": False, "error": "file not found"}, 404)
            return
        before = _snap(p)
        p.unlink()
        after = _snap(p)
        _record_change(before, after, "delete")
        _dirty = True
        self._send_json(
            {
                "ok": True,
                "deleted": path_rel,
                "files": [{"path": path_rel, "action": "deleted"}],
            }
        )

    def log_message(self, fmt, *args):
        if self.path.startswith("/api/"):
            log(f"api {self.command} {self.path}")


IMAGE_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".avif", ".ico"
}


def io_bytes(img: Image.Image, fmt: str) -> bytes:
    import io

    buf = io.BytesIO()
    if fmt.upper() == "JPEG":
        img.save(buf, fmt, quality=86)
    else:
        img.save(buf, fmt)
    return buf.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description="pilog dev server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--watch", action="store_true", help="auto rebuild on change")
    args = parser.parse_args()

    if args.host not in ("127.0.0.1", "::1", "localhost"):
        log("WARNING: 非回环地址启动，/manager 与 /api 仍将拒绝非本机访问")

    cfg = Config.load(CONFIG_PATH)
    if not cfg.out_dir.joinpath("index.html").exists():
        log("first build…")
        rebuild()

    if args.watch:
        threading.Thread(target=watch_loop, daemon=True).start()
        log("watching for changes (Ctrl+C to stop)")

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    log(f"serving {cfg.out_dir} at {url}")
    log(f"WYSIWYG manager (local only): {url}manager")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log("bye")


if __name__ == "__main__":
    main()
