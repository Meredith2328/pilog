from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


@dataclass
class AssetMap:
    blog_root: Path
    out_root: Path

    def __post_init__(self) -> None:
        self._map: dict[Path, str] = {}  # source abs path -> out rel posix

    def register(self, src: Path, out_rel: str) -> str:
        src = src.resolve()
        key = str(src).lower()
        for existing, rel in self._map.items():
            if str(existing).lower() == key:
                return rel
        self._map[src] = out_rel
        return out_rel

    def resolve_in_blog(self, rel: str) -> Path:
        return (self.blog_root / rel).resolve()

    def out_of(self, src: Path) -> Path:
        rel = self._map.get(src.resolve())
        if rel is None:
            raise KeyError(src)
        return self.out_root / rel

    def copy_all(self, logger) -> None:
        for src, rel in self._map.items():
            dst = self.out_root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        logger(f"copied {len(self._map)} assets")


def copy_tree(src: Path, dst: Path, logger=None) -> int:
    """Copy a directory wholesale; returns number of files copied."""
    count = 0
    if not src.exists():
        return 0
    for item in src.rglob("*"):
        if item.is_file():
            target = dst / item.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
            count += 1
    if logger:
        logger(f"copied {count} files from {src.name}/")
    return count


def sync_tree(src: Path, dst: Path, logger=None) -> int:
    """Copy `src` into `dst` and prune files no longer present in `src`."""
    count = copy_tree(src, dst, logger=logger)
    if not dst.exists():
        return count
    src_files = {
        p.relative_to(src).as_posix()
        for p in src.rglob("*")
        if p.is_file()
    } if src.exists() else set()
    pruned = 0
    for p in dst.rglob("*"):
        if p.is_file() and ".thumbs" not in p.parts:
            rel = p.relative_to(dst).as_posix()
            if rel not in src_files:
                p.unlink()
                pruned += 1
    if pruned and logger:
        logger(f"pruned {pruned} stale asset files")
    return count


def _is_pixel_art(img: Image.Image) -> bool:
    if img.width <= 128 and img.height <= 128:
        colors = len(img.getcolors(maxcolors=4096) or [])
        return colors <= 64
    return False


def make_thumbnail(src: Path, dst_dir: Path, width: int = 400) -> Path | None:
    """Generate a fixed-width thumbnail (nearest-neighbor for pixel art).

    Animated GIF covers keep their animation (each frame resized); everything
    else is saved as a JPEG thumbnail.
    """
    try:
        img = Image.open(src)
        if img.width <= width:
            return None  # original is small enough
        ratio = width / img.width
        new_size = (width, max(1, round(img.height * ratio)))

        n_frames = getattr(img, "n_frames", 1)
        if src.suffix.lower() == ".gif" and n_frames > 120:
            # huge animated GIFs (e.g. notegotya's 746-frame cover): keep the
            # original file so the animation stays intact in cards
            return None
        if src.suffix.lower() == ".gif" and 1 < n_frames <= 120:
            frames = _resize_gif_frames(img, new_size)
            if frames:
                dst = dst_dir / f"{hashlib.sha1(src.read_bytes()).hexdigest()[:12]}.gif"
                dst.parent.mkdir(parents=True, exist_ok=True)
                durations = [
                    frame.info.get("duration", 80) or 80 for frame in frames
                ]
                frames[0].save(
                    dst,
                    "GIF",
                    save_all=True,
                    append_images=frames[1:],
                    duration=durations,
                    loop=0,
                    disposal=2,
                )
                return dst

        img = img.convert("RGB")
        resample = Image.NEAREST if _is_pixel_art(img) else Image.LANCZOS
        img = img.resize(new_size, resample)
        dst = dst_dir / f"{hashlib.sha1(src.read_bytes()).hexdigest()[:12]}.jpg"
        dst.parent.mkdir(parents=True, exist_ok=True)
        img.save(dst, "JPEG", quality=84, optimize=True)
        return dst
    except OSError:
        return None


def _resize_gif_frames(img, new_size: tuple) -> list | None:
    """Resize every frame of an animated GIF, preserving per-frame palettes."""
    frames: list = []
    try:
        for i in range(img.n_frames):
            img.seek(i)
            frame = img.copy()
            if frame.mode not in ("P", "L", "RGB", "RGBA"):
                frame = frame.convert("RGBA")
            frames.append(frame.resize(new_size, Image.NEAREST))
        if len(frames) < 2 or img.n_frames > 120:
            return None
    except Exception:
        return None
    return frames


def make_pixel_placeholder(dst_dir: Path, seed: str, size: int = 8) -> Path:
    """Deterministic pixel-art placeholder PNG for posts without images."""
    palette = [
        (247, 247, 247),
        (232, 234, 237),
        (218, 220, 224),
        (154, 160, 166),
        (95, 99, 104),
        (60, 64, 67),
        (26, 115, 232),
    ]
    digest = hashlib.sha1(seed.encode("utf-8")).digest()
    scale = 8
    img = Image.new("RGB", (size * scale, size * scale))
    px = img.load()
    for y in range(size):
        for x in range(size):
            color = palette[digest[(x * 2 + y * 3) % len(digest)] % len(palette)]
            for dy in range(scale):
                for dx in range(scale):
                    px[x * scale + dx, y * scale + dy] = color
    dst = dst_dir / f"placeholder_{digest.hex()[:10]}.png"
    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(dst, "PNG")
    return dst
