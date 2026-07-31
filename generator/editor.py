from __future__ import annotations

import base64
import re
from pathlib import Path

import yaml

from .content import split_front_matter


def safe_path(root: Path, rel: str) -> Path | None:
    """Resolve `rel` inside `root`; returns None for traversal escapes."""
    p = (root / rel).resolve()
    if p == root or p.is_relative_to(root.resolve()):
        return p
    return None


def update_front_matter(path: Path, updates: dict) -> None:
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


def _changed(rel: str, action: str = "modified") -> dict:
    return {"path": "blogs/" + rel, "action": action}


def update_post_meta(blog_root: Path, rel: str, updates: dict) -> dict:
    p = safe_path(blog_root, rel + ".md")
    if p is None or not p.is_file():
        raise FileNotFoundError(f"post not found: {rel}.md")
    update_front_matter(p, updates)
    return _changed(rel + ".md")


def update_post_source(blog_root: Path, rel: str, source: str) -> dict:
    p = safe_path(blog_root, rel + ".md")
    if p is None or not p.is_file():
        raise FileNotFoundError(f"post not found: {rel}.md")
    p.write_text(source, encoding="utf-8")
    return _changed(rel + ".md")


def delete_post(blog_root: Path, rel: str) -> dict:
    p = safe_path(blog_root, rel + ".md")
    if p is None or not p.is_file():
        raise FileNotFoundError(f"post not found: {rel}.md")
    p.unlink()
    return _changed(rel + ".md", action="deleted")


def md_refs(text: str):
    images = []
    for m in re.finditer(r"!\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]", text):
        images.append({"ref": m.group(0), "target": m.group(1).strip()})
    for m in re.finditer(r"!\[([^\]]*)\]\(([^)]+)\)", text):
        if m.group(2).startswith(("http://", "https://", "data:")):
            continue
        images.append({"ref": m.group(0), "target": m.group(2).strip()})
    links = []
    for m in re.finditer(r"(?<!!)\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]", text):
        links.append({"ref": m.group(0), "target": m.group(1).strip()})
    for m in re.finditer(r"\[([^\]]+)\]\(([^)]+\.md)(#[^)]*)?\)", text):
        links.append({"ref": m.group(0), "target": m.group(2).strip()})
    return images, links


def img_exists(blog_root: Path, target: str, md_dir: str, imported_images: list) -> bool:
    t = target.replace("\\", "/")
    candidates = [
        blog_root / md_dir / t,
        blog_root / t,
        blog_root / "assets" / t,
    ]
    if any(c.is_file() for c in candidates):
        return True
    base = t.split("/")[-1]
    return any((ir or "").split("/")[-1] == base for ir in imported_images)


def md_exists(blog_root: Path, target: str, md_dir: str, imported_mds: list) -> bool:
    t = target.replace("\\", "/")
    if t.endswith(".md"):
        t = t[:-3]
    t = t.split("#")[0]
    if "/" in t:
        if (blog_root / (t + ".md")).is_file():
            return True
    else:
        if (blog_root / md_dir / (t + ".md")).is_file():
            return True
        if list(blog_root.rglob(t + ".md")):
            return True
    return t in imported_mds


def analyze_markdown(
    blog_root: Path, files: list, imported_images: list | None = None
) -> list:
    """Report image/link references per markdown file (status found|missing)."""
    imported_mds = [f.get("rel", "")[:-3] for f in files]
    imported_images = imported_images or []
    report = []
    for f in files:
        rel = str(f.get("rel", ""))
        text = str(f.get("text", ""))
        md_dir = rel.rsplit("/", 1)[0] if "/" in rel else ""
        images, links = md_refs(text)
        report.append(
            {
                "rel": rel,
                "images": [
                    {
                        "i": i,
                        "ref": im["ref"],
                        "target": im["target"],
                        "status": (
                            "found"
                            if img_exists(blog_root, im["target"], md_dir, imported_images)
                            else "missing"
                        ),
                    }
                    for i, im in enumerate(images)
                ],
                "links": [
                    {
                        "i": i,
                        "ref": lk["ref"],
                        "target": lk["target"],
                        "status": (
                            "found"
                            if md_exists(blog_root, lk["target"], md_dir, imported_mds)
                            else "missing"
                        ),
                    }
                    for i, lk in enumerate(links)
                ],
            }
        )
    return report


def import_markdown(
    blog_root: Path,
    files: list,
    images: list,
    strip_image_refs: dict | None = None,
    strip_link_refs: dict | None = None,
) -> list:
    """Write imported markdown/images into blogs/, rewriting stripped refs."""
    strip_image_refs = strip_image_refs or {}
    strip_link_refs = strip_link_refs or {}
    changed: list = []

    for img in images:
        rel = str(img.get("rel", ""))
        data = str(img.get("dataBase64", ""))
        p = safe_path(blog_root, rel)
        if p is None or len(data) > 12_000_000:
            continue
        try:
            raw = base64.b64decode(data.split(",", 1)[-1])
        except Exception:
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(raw)
        changed.append(_changed(rel, action="imported"))

    for f in files:
        rel = str(f.get("rel", ""))
        text = str(f.get("text", ""))
        p = safe_path(blog_root, rel)
        if p is None:
            continue
        _, _ = md_refs(text)  # keep ordering consistent with analyze
        positions_img = []
        for m in re.finditer(r"!\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]", text):
            positions_img.append((m.start(), m.end(), ""))
        for m in re.finditer(r"!\[([^\]]*)\]\(([^)]+)\)", text):
            if m.group(2).startswith(("http://", "https://", "data:")):
                continue
            positions_img.append((m.start(), m.end(), ""))
        positions_link = []
        for m in re.finditer(r"(?<!!)\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]", text):
            raw = m.group(1)
            label = raw.split("|")[0].split("#")[0].split("/")[-1]
            if "|" in raw:
                label = raw.split("|")[1]
            positions_link.append((m.start(), m.end(), label))
        for m in re.finditer(r"\[([^\]]+)\]\(([^)]+\.md)(#[^)]*)?\)", text):
            positions_link.append((m.start(), m.end(), m.group(1)))

        strips = []
        for idx in strip_image_refs.get(rel, []) or []:
            if 0 <= idx < len(positions_img):
                strips.append(positions_img[idx])
        for idx in strip_link_refs.get(rel, []) or []:
            if 0 <= idx < len(positions_link):
                strips.append(positions_link[idx])
        if strips:
            strips.sort(key=lambda s: s[0], reverse=True)
            for start, end, repl in strips:
                text = text[:start] + repl + text[end:]

        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        changed.append(_changed(rel, action="imported"))

    return changed
