from __future__ import annotations

import re
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, quote

import markdown as md_lib
from bs4 import BeautifulSoup

from .utils import rel_output


IMG_TOKEN = "__PILOG_IMG__:"
LINK_TOKEN = "__PILOG_LINK__:"

WIKI_IMAGE_RE = re.compile(r"!\[\[([^\]|]+?)(?:\|([^\]]*))?\]\]")
WIKI_LINK_RE = re.compile(r"\[\[([^\]|]+?)(?:\|([^\]]*))?\]\]")


@dataclass
class MarkdownContext:
    blog_root: Path
    assets: object  # AssetMap
    base_path: str = ""
    posts_by_rel: dict = field(default_factory=dict)  # rel -> Post
    warnings: list = field(default_factory=list)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


@dataclass
class Rendered:
    html: str
    refs: list  # post rel targets
    image_sources: list  # abs Path of images found in body


def _parse_wiki(text: str) -> str:
    """Convert Obsidian [[...]] / ![[...]] into standard markdown tokens."""

    def img(m: re.Match) -> str:
        name = m.group(1).strip()
        opts = (m.group(2) or "").strip()
        payload = quote(name)
        if opts:
            payload += "|" + quote(opts)
        return f"![{name}]({IMG_TOKEN}{payload})"

    def link(m: re.Match) -> str:
        target = m.group(1).strip()
        label = (m.group(2) or "").strip() or target.split("#")[0].split("/")[-1]
        payload = quote(target)
        return f"[{label}]({LINK_TOKEN}{payload})"

    text = WIKI_IMAGE_RE.sub(img, text)
    text = WIKI_LINK_RE.sub(link, text)
    return text


def _md_instance() -> md_lib.Markdown:
    return md_lib.Markdown(
        extensions=[
            "extra",
            "codehilite",
            "toc",
            "sane_lists",
            "attr_list",
            # ~~删除线~~ and $...$ / $$...$$ LaTeX (rendered client-side by KaTeX)
            "pymdownx.tilde",
            "pymdownx.arithmatex",
        ],
        extension_configs={
            "codehilite": {
                "guess_lang": False,
                "css_class": "highlight",
                "linenums": False,
            },
            "toc": {"permalink": False, "toc_depth": "1-6"},
            "pymdownx.tilde": {"subscript": False},
            "pymdownx.arithmatex": {"generic": True},
        },
    )


def find_asset(name: str, src_file: Path, ctx: MarkdownContext) -> Path | None:
    """Locate an asset file by wiki-style name (Obsidian vault semantics)."""
    name = name.replace("\\", "/")
    src_dir = src_file.parent.resolve()
    root = ctx.blog_root.resolve()
    candidates: list[Path] = []

    if "/" in name:
        # explicit relative path inside the vault
        candidates += [src_dir / name, root / name, (root / "assets") / name]
    else:
        candidates += [
            src_dir / name,          # same folder as the post
            root / name,             # vault root
            (root / "assets") / name,  # vault-wide assets folder
        ]
        # any folder literally named assets
        for assets_dir in root.rglob("assets"):
            if assets_dir.is_dir():
                candidates.append(assets_dir / name)

    for cand in candidates:
        if cand.is_file():
            return cand.resolve()
    return None


def resolve_asset_out(src: Path, ctx: MarkdownContext) -> str:
    """Register an asset and return its site-root-relative output path."""
    src = src.resolve()
    root = ctx.blog_root.resolve()
    try:
        rel = src.relative_to(root).as_posix()
    except ValueError:
        digest = hashlib.sha1(str(src).encode("utf-8")).hexdigest()[:10]
        rel = f"assets/external/{quote(src.stem, safe='')}-{digest}{src.suffix.lower()}"
    return ctx.assets.register(src, rel)


def _apply_image_opts(img, opts: str) -> None:
    opts = unquote(opts)
    if not opts:
        return
    dims = re.search(r"(\d+)(?:x(\d+))?", opts)
    if not dims:
        return
    w = dims.group(1)
    h = dims.group(2)
    if h:
        img["width"] = w
        img["height"] = h
        img["style"] = "width:{w}px;height:{h}px;object-fit:cover".format(
            w=w, h=h
        )
    else:
        img["style"] = "width:{w}px".format(w=w)


def _rewrite_href(href: str, src_file: Path, page_url: str,
                  ctx: MarkdownContext, refs: list) -> str:
    base = ctx.base_path

    if href.startswith("#") or href.startswith(("http://", "https://",
                                                "mailto:", "tel:", "data:",
                                                "blob:", "javascript:")):
        return href

    if href.startswith("/"):
        if href == "/":
            # site root in a nav item: resolve page-relative so it works
            # under any deployment path (e.g. /blogtest or repo root)
            return rel_output(page_url, "index.html")
        if base and not href.startswith(base + "/"):
            return base + href
        return href

    # Resolve against the source file, then map into the output tree.
    anchor = ""
    path_part = href
    if "#" in href:
        path_part, anchor = href.split("#", 1)
        anchor = "#" + anchor

    if path_part == "index.html":
        return rel_output(page_url, "index.html") + anchor

    src_dir = src_file.parent.resolve()
    root = ctx.blog_root.resolve()
    candidates = [src_dir / path_part, root / path_part]

    if path_part.endswith(".md"):
        for cand in candidates:
            if cand.is_file():
                rel = cand.resolve().relative_to(root).as_posix()
                post = ctx.posts_by_rel.get(rel[:-3])
                if post:
                    refs.append(post.rel)
                    return rel_output(page_url, post.url) + anchor
        ctx.warn(f"link target not found: {href!r} in {src_file}")
        return href

    # dino game special case
    cleaned = path_part.lstrip("./")
    if cleaned.startswith("dino/") or cleaned == "dino":
        if cleaned in ("dino", "dino/", "dino/index.html"):
            return rel_output(page_url, "dino/index.html") + anchor

    if path_part.endswith("/"):
        for cand in candidates:
            index_md = cand / "index.md"
            if index_md.is_file():
                rel = index_md.resolve().relative_to(root).as_posix()
                post = ctx.posts_by_rel.get(rel[:-3])
                if post:
                    refs.append(post.rel)
                    return rel_output(page_url, post.url) + anchor
        # folder without its own page -> folder-aware target (each view
        # interprets it: cards filter / tree locate / graph subtree highlight)
        for cand in candidates:
            if cand.is_dir():
                folder_rel = cand.resolve().relative_to(root).as_posix()
                return rel_output(page_url, "index.html") + "#folder=" + folder_rel
        return rel_output(page_url, "index.html") + "#folder=" + path_part.rstrip("/")

    for cand in candidates:
        if cand.is_file() and not cand.is_dir():
            out_rel = resolve_asset_out(cand.resolve(), ctx)
            return rel_output(page_url, out_rel) + anchor

    ctx.warn(f"link target not found: {href!r} in {src_file}")
    return href


def render_markdown(text: str, src_file: Path, page_url: str,
                    ctx: MarkdownContext) -> Rendered:
    """Full pipeline: wiki syntax -> markdown -> link/image rewriting."""
    refs: list = []
    image_sources: list = []
    text = _parse_wiki(text)

    body = _md_instance()
    html = body.reset().convert(text)
    soup = BeautifulSoup(html, "html.parser")

    # task lists: - [x] / - [ ] (python-markdown's extra does not handle them)
    for li in soup.find_all("li"):
        first = li.find(string=True)
        if first is None:
            continue
        m = re.match(r"^\[([ xX])\]\s+", first)
        if not m:
            continue
        checkbox = soup.new_tag(
            "input",
            type="checkbox",
            disabled="disabled",
        )
        if m.group(1).lower() == "x":
            checkbox["checked"] = "checked"
        first.replace_with(first[m.end():])
        li.insert(0, checkbox)
        li["class"] = li.get("class", []) + ["task-list-item"]

    for img in soup.find_all("img"):
        src = img.get("src", "")
        if src.startswith(IMG_TOKEN):
            payload = src[len(IMG_TOKEN):]
            encoded_name, _, encoded_opts = payload.partition("|")
            name = unquote(encoded_name)
            opts = unquote(encoded_opts) if encoded_opts else ""
            found = find_asset(name, src_file, ctx)
            if found is None:
                ctx.warn(f"image not found: ![[{name}]] in {src_file.name}")
                img.decompose()
                continue
            out_rel = resolve_asset_out(found, ctx)
            image_sources.append(found)
            img["src"] = rel_output(page_url, out_rel)
            _apply_image_opts(img, opts)
        elif src.startswith(("http://", "https://", "data:", "blob:")):
            continue
        elif src.startswith("/"):
            base = ctx.base_path
            if base and not src.startswith(base + "/"):
                img["src"] = base + src
        else:
            # relative markdown image path
            cands = [src_file.parent.resolve() / src, ctx.blog_root.resolve() / src]
            for cand in cands:
                if cand.is_file():
                    out_rel = resolve_asset_out(cand.resolve(), ctx)
                    image_sources.append(cand.resolve())
                    img["src"] = rel_output(page_url, out_rel)
                    break
            else:
                ctx.warn(f"image not found: {src!r} in {src_file.name}")

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith(LINK_TOKEN):
            target = unquote(href[len(LINK_TOKEN):])
            anchor = ""
            if "#" in target:
                target, anchor = target.split("#", 1)
                anchor = "#" + re.sub(r"\s+", "-", anchor.strip())
            post = resolve_wiki_post(target, src_file, ctx)
            if post is None:
                ctx.warn(f"wiki link not found: [[{target}]] in {src_file.name}")
                a.name = "span"
                continue
            refs.append(post.rel)
            a["href"] = rel_output(page_url, post.url) + anchor
        else:
            new_href = _rewrite_href(href, src_file, page_url, ctx, refs)
            a["href"] = new_href

    return Rendered(html=str(soup), refs=refs, image_sources=image_sources)


def resolve_wiki_post(target: str, src_file: Path,
                      ctx: MarkdownContext):
    """Resolve [[target]] to the matching Post (or None)."""
    target = target.strip().replace("\\", "/")
    root = ctx.blog_root.resolve()
    src_dir = src_file.parent.resolve()
    post = None
    if target.endswith(".md"):
        target = target[:-3]
    if "/" in target:
        post = ctx.posts_by_rel.get(target)
    if post is None:
        post = ctx.posts_by_rel.get(target)
    if post is None:
        # same-folder stem match first, then unique stem
        same_folder = [
            p for p in ctx.posts_by_rel.values()
            if p.rel.rsplit("/", 1)[-1] == target and p.rel_dir == src_dir.relative_to(root).as_posix()
        ]
        stem_matches = [
            p for p in ctx.posts_by_rel.values()
            if p.rel.rsplit("/", 1)[-1] == target
        ]
        if same_folder:
            post = same_folder[0]
        elif len(stem_matches) == 1:
            post = stem_matches[0]
    if post is None:
        return None
    return post
