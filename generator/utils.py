from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path


_DATE_RE = re.compile(
    r"^(?P<y>\d{4})[-/.]?(?P<m>\d{1,2})[-/.]?(?P<d>\d{1,2})"
)


def to_posix(p: Path) -> str:
    return p.as_posix()


def rel_output(current_page: str, target_out: str) -> str:
    """Relative URL from the directory of `current_page` to `target_out`.

    Both are site-root-relative posix paths such as "posts/tech/hello.html".
    This is the mechanism that keeps the site working under any GitHub Pages
    base path (e.g. /blogtest): every link is computed relative to the page.
    """
    from os.path import relpath

    cur_dir = Path(current_page).parent.as_posix()
    if cur_dir == ".":
        cur_dir = ""
    target = target_out if target_out else "index.html"
    if cur_dir:
        rel = relpath(target, cur_dir)
    else:
        rel = target
    return Path(rel).as_posix()


def root_prefix(current_page: str) -> str:
    """Prefix pointing back to the site root from `current_page`."""
    from os.path import relpath

    cur_dir = Path(current_page).parent.as_posix()
    if cur_dir == "." or not cur_dir:
        return ""
    rel = relpath(".", cur_dir)
    if rel == ".":
        return ""
    return Path(rel).as_posix() + "/"


def parse_date(value: object, default: datetime) -> datetime:
    if value is None:
        return default
    text = str(value).strip()
    m = _DATE_RE.match(text)
    if m:
        try:
            return datetime(int(m["y"]), int(m["m"]), int(m["d"]))
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return default


def natural_key(text: str):
    return [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", text)
    ]


def slugify(text: str) -> str:
    text = re.sub(r"\s+", "-", text.strip().lower())
    return re.sub(r"[^\w\u4e00-\u9fff-]", "", text)
