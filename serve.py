#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pilog 本地开发服务器 + 图片工作台。

用法:
    python serve.py              # 打开 http://127.0.0.1:8000/
    python serve.py --watch      # 监视 blogs/，改动后自动重新构建
    python serve.py --port 9000

图片工作台: http://127.0.0.1:8000/manager
把图片拖进来即可加入 blogs/ 目录；支持缩放、裁剪、替换与删除。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PIL import Image

from build import build_site
from generator.config import Config


ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config.json"
MANAGER_HTML = ROOT / "tools" / "manager.html"

_dirty = False
_mutex = threading.Lock()


def log(msg: str) -> None:
    print(f"[pilog] {msg}", flush=True)


def rebuild(clean: bool = False) -> None:
    try:
        build_site(CONFIG, clean=clean)
    except Exception as exc:  # noqa: BLE001
        log(f"build failed: {exc}")


def fingerprint() -> str:
    cfg = Config.load(CONFIG)
    blog_root = cfg.blog_dir
    h = hashlib.sha1()

    def add(path: Path) -> None:
        if path.is_file():
            h.update(str(path).encode("utf-8"))
            h.update(str(path.stat().st_mtime_ns).encode("utf-8"))
            h.update(str(path.stat().st_size).encode("utf-8"))

    add(CONFIG)
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
        global _dirty
        try:
            changed = _dirty or fingerprint() != last
        except OSError:
            changed = False
        if changed:
            _dirty = False
            last = fingerprint()
            log("change detected, rebuilding…")
            rebuild()


class Handler(SimpleHTTPRequestHandler):
    server_version = "pilog-dev"

    def __init__(self, *args, **kwargs):
        cfg = Config.load(CONFIG)
        self.blog_root = cfg.blog_dir
        self.out_root = cfg.out_dir
        self.cache_dir = ROOT / ".cache" / "manager"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        super().__init__(*args, directory=str(self.out_root), **kwargs)

    # ---------- helpers ----------

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

    # ---------- routing ----------

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/manager" or path == "/manager/":
            self._serve_manager()
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
        if path.startswith("/api/"):
            self._send_json({"ok": False, "error": "not found"}, 404)
            return
        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/upload":
            self._api_upload()
            return
        self._send_json({"ok": False, "error": "not found"}, 404)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/file":
            qs = parse_qs(parsed.query)
            self._api_delete(qs.get("path", [""])[0])
            return
        self._send_json({"ok": False, "error": "not found"}, 404)

    # ---------- pages ----------

    def _serve_manager(self):
        global _mutex
        if not MANAGER_HTML.exists():
            self._send_json({"ok": False, "error": "manager.html missing"}, 404)
            return
        with _mutex:
            html = MANAGER_HTML.read_text(encoding="utf-8")
        html = html.replace("__BLOG_DIR__", str(self.blog_root))
        self._send_bytes(html.encode("utf-8"), "text/html; charset=utf-8")

    # ---------- api ----------

    def _api_tree(self):
        def walk(d: Path) -> list:
            out = []
            for sub in sorted(d.iterdir(), key=lambda p: p.name.lower()):
                if sub.is_dir() and not sub.name.startswith((".", "_")):
                    rel = sub.relative_to(self.blog_root).as_posix()
                    out.append(
                        {
                            "name": sub.name,
                            "path": rel,
                            "children": walk(sub),
                        }
                    )
            return out

        self._send_json({"ok": True, "root": str(self.blog_root), "dirs": walk(self.blog_root)})

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
            buf = io_bytes(out, "JPEG")
            self._send_bytes(buf, "image/jpeg")
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
        global _dirty
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
        target.write_bytes(body)
        _dirty = True
        rel = target.relative_to(self.blog_root).as_posix()
        self._send_json({"ok": True, "name": target.name, "path": rel, "replaced": replace})

    def _api_delete(self, path_rel: str):
        global _dirty
        p = self._safe_blog_path(path_rel)
        if p is None or not p.is_file():
            self._send_json({"ok": False, "error": "file not found"}, 404)
            return
        p.unlink()
        _dirty = True
        self._send_json({"ok": True, "deleted": path_rel})

    # silence default logging noise
    def log_message(self, fmt, *args):
        if self.path.startswith("/api/"):
            log(f"api {self.command} {self.path}")


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".avif", ".ico"}


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

    cfg = Config.load(CONFIG)
    if not cfg.out_dir.joinpath("index.html").exists():
        log("first build…")
        rebuild()

    if args.watch:
        threading.Thread(target=watch_loop, daemon=True).start()
        log("watching for changes (Ctrl+C to stop)")

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    log(f"serving {cfg.out_dir} at {url}")
    log(f"image manager: {url}manager")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log("bye")


if __name__ == "__main__":
    main()
