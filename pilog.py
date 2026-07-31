#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pilog 命令行入口 —— 与可视化工作台共用同一套代码路径。

用法:
    python pilog.py build                 # 构建静态站点
    python pilog.py serve --watch         # 本地开发服务器
    python pilog.py list                  # 列出文章
    python pilog.py import 路径...        # 批量导入 Markdown/图片/目录（保留结构）
    python pilog.py delete <rel>          # 删除文章（构建后站点自动移除）
    python pilog.py publish -m "说明"     # 构建并推送到 GitHub
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def _config():
    from generator.config import Config

    return Config.load(ROOT / "config.json")


def _ctx(cfg):
    from generator.assets import AssetMap
    from generator.markdownx import MarkdownContext

    return MarkdownContext(
        blog_root=cfg.blog_dir,
        assets=AssetMap(blog_root=cfg.blog_dir, out_root=cfg.blog_dir),
        base_path=cfg.base_path,
    )


def cmd_build(args) -> None:
    from build import build_site

    build_site(ROOT / "config.json", clean=args.clean)


def cmd_serve(args) -> None:
    import serve

    serve.start_server(args.host, args.port, args.watch)


def cmd_list(args) -> None:
    from generator.content import scan_posts, sorted_for_cards

    cfg = _config()
    posts = sorted_for_cards(scan_posts(cfg.blog_dir, _ctx(cfg)))
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "rel": p.rel,
                        "title": p.title,
                        "date": p.date_str,
                        "tags": p.tags,
                        "pin": p.pin,
                        "highlight": p.highlight,
                        "hidden": p.hidden,
                    }
                    for p in posts
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    print("date         pin  hid  path")
    for p in posts:
        print(
            f"{p.date_str:<12} {'yes' if p.pin else '-':<4} "
            f"{'hid' if p.hidden else '-':<4} {p.rel}  {p.title}"
        )


def _collect_paths(paths: list[str]) -> tuple[list, list]:
    """Collect markdown files (text) and images (base64) preserving structure."""
    files: list = []
    images: list = []
    IMG_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".avif"}
    for raw in paths:
        p = Path(raw)
        if not p.exists():
            print(f"跳过不存在的路径: {raw}", file=sys.stderr)
            continue
        items = sorted(p.rglob("*")) if p.is_dir() else [p]
        base = p if p.is_dir() else p.parent
        for f in items:
            if not f.is_file():
                continue
            rel = f.relative_to(base).as_posix()
            if f.suffix.lower() == ".md":
                files.append({"rel": rel, "text": f.read_text(encoding="utf-8")})
            elif f.suffix.lower() in IMG_EXTS:
                data = base64.b64encode(f.read_bytes()).decode("ascii")
                images.append({"rel": rel, "dataBase64": f"data:image/png;base64,{data}"})
            else:
                print(f"跳过不支持的文件: {rel}")
    return files, images


def cmd_import(args) -> None:
    from generator.editor import analyze_markdown, import_markdown

    cfg = _config()
    files, images = _collect_paths(args.paths)
    if args.dir:
        files = [dict(f, rel=f"{args.dir}/{f['rel']}") for f in files]
        images = [dict(i, rel=f"{args.dir}/{i['rel']}") for i in images]
    if not files:
        print("没有找到可导入的 Markdown 文件", file=sys.stderr)
        sys.exit(1)

    report = analyze_markdown(
        cfg.blog_dir,
        files,
        imported_images=[i["rel"] for i in images],
    )
    strip_imgs: dict = {}
    strip_links: dict = {}
    missing_img = missing_link = 0
    for r in report:
        for im in r["images"]:
            if im["status"] == "missing":
                missing_img += 1
                if args.strip_missing_images:
                    strip_imgs.setdefault(r["rel"], []).append(im["i"])
        for lk in r["links"]:
            if lk["status"] == "missing":
                missing_link += 1
                if args.strip_missing_links:
                    strip_links.setdefault(r["rel"], []).append(lk["i"])

    for r in report:
        print(f"  {r['rel']}")
        for im in r["images"]:
            print(f"    image [{'ok' if im['status']=='found' else 'MISSING'}] {im['ref']}")
        for lk in r["links"]:
            print(f"    link  [{'ok' if lk['status']=='found' else 'MISSING'}] {lk['ref']}")
    if missing_img and not args.strip_missing_images:
        print(f"提示: {missing_img} 个图片引用缺失（加 --strip-missing-images 可移除）")
    if missing_link and not args.strip_missing_links:
        print(f"提示: {missing_link} 个文章引用缺失（加 --strip-missing-links 可移除）")

    changed = import_markdown(
        cfg.blog_dir,
        files,
        images,
        strip_image_refs=strip_imgs,
        strip_link_refs=strip_links,
    )
    print(f"已导入 {len(changed)} 个文件")
    for c in changed:
        print(f"  + {c['path']}")


def cmd_delete(args) -> None:
    from generator.editor import delete_post

    cfg = _config()
    if not args.yes:
        answer = input(f"确定删除 blogs/{args.rel}.md ？(y/N) ").strip().lower()
        if answer not in ("y", "yes"):
            print("已取消")
            return
    changed = delete_post(cfg.blog_dir, args.rel)
    print(f"已删除 {changed['path']}，运行 build/publish 生效")


def cmd_publish(args) -> None:
    from publish import run_publish

    result = run_publish(args.message, build=not args.skip_build)
    if result.get("output"):
        print(result["output"])
    if not result.get("ok"):
        print("发布失败:", result.get("error", ""), file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="pilog — 像素风博客框架")
    sub = parser.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build", help="构建静态站点")
    b.add_argument("--clean", action="store_true", help="先清空输出目录")
    b.set_defaults(func=cmd_build)

    s = sub.add_parser("serve", help="本地开发服务器")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--watch", action="store_true", help="自动重建")
    s.set_defaults(func=cmd_serve)

    l = sub.add_parser("list", help="列出文章")
    l.add_argument("--json", action="store_true", help="JSON 输出")
    l.set_defaults(func=cmd_list)

    i = sub.add_parser("import", help="批量导入 Markdown/图片/目录")
    i.add_argument("paths", nargs="+", help="文件或目录路径")
    i.add_argument("--dir", default="", help="导入到 blogs/ 下的子目录")
    i.add_argument("--strip-missing-images", action="store_true", help="移除缺失的图片引用")
    i.add_argument("--strip-missing-links", action="store_true", help="把缺失的文章引用转为纯文本")
    i.set_defaults(func=cmd_import)

    d = sub.add_parser("delete", help="删除文章")
    d.add_argument("rel", help="文章相对路径，如 posts/tech/hello")
    d.add_argument("--yes", action="store_true", help="跳过确认")
    d.set_defaults(func=cmd_delete)

    p = sub.add_parser("publish", help="构建并推送到 GitHub")
    p.add_argument("-m", "--message", default=None, help="提交信息")
    p.add_argument("--skip-build", action="store_true", help="跳过重新构建")
    p.set_defaults(func=cmd_publish)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
