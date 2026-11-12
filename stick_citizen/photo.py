"""Turn a product-style stick photo into a cut-out on a transparent background."""
from __future__ import annotations

from pathlib import Path


def cutout(src, dst, max_side: int = 1100, white: int = 232):
    """Remove a plain light background (flood-filled from the edges) and crop to the stick."""
    from PIL import Image, ImageDraw, ImageFilter

    im = Image.open(src)
    im.load()
    if im.mode in ("RGBA", "LA") and im.getextrema()[-1][0] < 250:
        out = im.convert("RGBA")                       # already has transparency: keep it
    else:
        rgb = im.convert("RGB")
        # light = 255 where every channel is near-white
        r, g, b = rgb.split()
        light = Image.eval(r, lambda v: 255 if v > white else 0)
        for ch in (g, b):
            light = Image.composite(light, Image.new("L", rgb.size, 0), Image.eval(ch, lambda v: 255 if v > white else 0))
        mask = light.copy()
        w, h = mask.size
        step = max(1, min(w, h) // 60)
        seeds = [(x, y) for x in range(0, w, step) for y in (0, h - 1)] + [(x, y) for y in range(0, h, step) for x in (0, w - 1)]
        for xy in seeds:
            if mask.getpixel(xy) == 255:
                ImageDraw.floodfill(mask, xy, 128)
        alpha = Image.eval(mask, lambda v: 0 if v == 128 else 255).filter(ImageFilter.GaussianBlur(1.1))
        out = rgb.convert("RGBA")
        out.putalpha(alpha)
    out.putalpha(_largest_blob(out.getchannel("A")))
    box = out.getchannel("A").point(lambda v: 255 if v > 24 else 0).getbbox()
    if box:
        out = out.crop(box)
    out.thumbnail((max_side, max_side))
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    out.save(dst)
    return Path(dst)


def _largest_blob(alpha):
    """Keep only the biggest solid shape (drops logos and specks left on the background)."""
    from collections import deque

    from PIL import Image, ImageChops
    w, h = alpha.size
    scale = 200 / max(w, h)
    sw, sh = max(1, int(w * scale)), max(1, int(h * scale))
    small = alpha.resize((sw, sh)).point(lambda v: 1 if v > 40 else 0)
    px = small.load()
    label = [[0] * sw for _ in range(sh)]
    best, best_n, n = 0, 0, 0
    for y in range(sh):
        for x in range(sw):
            if px[x, y] and not label[y][x]:
                n += 1
                size, q = 0, deque([(x, y)])
                label[y][x] = n
                while q:
                    cx, cy = q.popleft()
                    size += 1
                    for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                        if 0 <= nx < sw and 0 <= ny < sh and px[nx, ny] and not label[ny][nx]:
                            label[ny][nx] = n
                            q.append((nx, ny))
                if size > best_n:
                    best, best_n = n, size
    if n <= 1:
        return alpha
    keep = Image.new("L", (sw, sh), 0)
    kp = keep.load()
    for y in range(sh):
        for x in range(sw):
            if label[y][x] == best:
                kp[x, y] = 255
    keep = keep.resize((w, h)).point(lambda v: 255 if v > 0 else 0)
    keep = keep.filter(__import__("PIL.ImageFilter", fromlist=["MaxFilter"]).MaxFilter(9))
    return ImageChops.multiply(alpha, keep)


def needs_cutout(path) -> bool:
    """True for a photo that still has its solid background (no transparent pixels)."""
    from PIL import Image
    try:
        with Image.open(path) as im:
            if im.mode not in ("RGBA", "LA", "P"):
                return True
            return im.convert("RGBA").getchannel("A").getextrema()[0] > 200
    except OSError:
        return False
