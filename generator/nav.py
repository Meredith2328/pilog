from __future__ import annotations

import re


def parse_nav(text: str) -> list:
    """Parse nav.md's top-level/nested link list into item dicts."""
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


def serialize_nav(items: list, indent: int = 0) -> str:
    """Serialize nav items back into a markdown list."""
    pad = "  " * indent
    lines = []
    for it in items:
        lines.append(f"{pad}- [{it['label']}]({it['href']})")
        child = serialize_nav(it.get("children", []), indent + 1).rstrip("\n")
        if child:
            lines.append(child)
    return "\n".join(lines) + ("\n" if lines else "")
