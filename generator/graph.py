from __future__ import annotations

from .utils import natural_key


def build_graph(posts: list, site_title: str) -> dict:
    """Nodes for posts + folders, links for hierarchy and references."""
    posts = [p for p in posts if not p.draft]
    nodes: dict[str, dict] = {}
    links: list[dict] = []

    # root node
    nodes[""] = {
        "id": "",
        "type": "root",
        "label": site_title or "BLOG",
        "url": "index.html",
    }

    for post in posts:
        parts = post.rel.split("/") if post.rel else []
        for i in range(1, len(parts) + 1):
            folder = "/".join(parts[:i])
            if folder not in nodes:
                nodes[folder] = {
                    "id": folder,
                    "type": "dir" if i < len(parts) else "post",
                    "label": parts[i - 1] if i < len(parts) else post.title,
                    "url": None if i < len(parts) else post.url,
                    "post_url": post.url if i == len(parts) else None,
                    "tags": post.tags if i == len(parts) else [],
                    "folder": "/".join(parts[: i - 1]),
                }
        post_id = post.rel
        nodes[post_id]["label"] = post.title
        nodes[post_id]["url"] = post.url
        nodes[post_id]["tags"] = post.tags
        nodes[post_id]["highlight"] = post.highlight

    # hierarchy edges
    for nid, node in sorted(nodes.items(), key=lambda kv: natural_key(kv[0])):
        if nid == "":
            continue
        parent = node["folder"] if node.get("folder") is not None else ""
        if parent in nodes:
            links.append(
                {"source": parent, "target": nid, "kind": "hierarchy"}
            )

    # reference edges (dashed)
    seen = set()
    for post in posts:
        for target_rel in post.refs:
            if target_rel in nodes and target_rel != post.rel:
                key = (post.rel, target_rel)
                if key not in seen:
                    seen.add(key)
                    links.append(
                        {"source": post.rel, "target": target_rel, "kind": "ref"}
                    )

    dirs = sum(1 for n in nodes.values() if n["type"] == "dir")
    refs = sum(1 for l in links if l["kind"] == "ref")
    return {
        "nodes": sorted(nodes.values(), key=lambda n: n["id"]),
        "links": links,
        "stats": {
            "posts": len(posts),
            "dirs": dirs,
            "refs": refs,
        },
    }
