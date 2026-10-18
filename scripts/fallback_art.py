"""Procedural artwork used when no image model is configured (or for decor).

Everything is drawn with Pillow at 2x and downsampled, colored from style.json,
so it stays consistent with the palette. Nothing here contains text except the
optional hero glyph (usually one letter from the product name).
"""
import math
import random

from PIL import Image, ImageDraw, ImageFilter, ImageChops

from common import hex_to_rgb, mix, get_font, find_icon

SS = 2  # supersampling


def _rgba(h, a=255):
    r, g, b = hex_to_rgb(h)
    return (r, g, b, int(a))


def vgradient(w, h, top, bottom):
    t, b = hex_to_rgb(top), hex_to_rgb(bottom)
    col = Image.new("RGB", (1, h))
    for y in range(h):
        k = y / max(1, h - 1)
        col.putpixel((0, y), tuple(int(t[i] + (b[i] - t[i]) * k) for i in range(3)))
    return col.resize((w, h))


def _layer(size, color=None):
    """Transparent layer. Pass the dominant color so blurring does not pull in black."""
    if color is None:
        return Image.new("RGBA", size, (0, 0, 0, 0))
    r, g, b = hex_to_rgb(color)
    return Image.new("RGBA", size, (r, g, b, 0))


def _blur(im, r):
    return im.filter(ImageFilter.GaussianBlur(r)) if r > 0 else im


def _paste(base, layer):
    base.alpha_composite(layer)
    return base


# ------------------------------------------------------------------ backgrounds
def background(style, w=1920, h=1080, variant="content", seed=7):
    """variant: content | cover | closing. Returns RGB image."""
    rnd = random.Random(seed)
    P = style.palette
    bgcfg = style.background or {}
    closing_dark = variant == "closing" and style.decor.get("closing_dark", True)
    dark = closing_dark or getattr(style, "dark", False)
    if closing_dark:
        top, bottom = P["primary_dark"], P["primary"]
    else:
        top, bottom = P["bg_top"], P["bg_bottom"]
    if bgcfg.get("flat"):
        # brand manuals that forbid gradients: one flat colour
        top = bottom = P["primary_dark"] if closing_dark else P["bg_top"]
    base = vgradient(w, h, top, bottom).convert("RGBA")
    if variant == "cover":
        decor = bgcfg.get("cover_decor", ["blobs", "clouds", "hills"])
    elif variant == "closing":
        decor = bgcfg.get("closing_decor", ["blobs", "bokeh", "arcs"])
    else:
        decor = bgcfg.get("decor", ["blobs", "bokeh", "arcs"])

    if "blobs" in decor:
        spots = [(0.05, 0.1), (0.95, 0.15), (0.9, 0.9), (0.1, 0.85), (0.55, 0.05)]
        tint = mix(P["primary"], "FFFFFF", 0.55) if not dark else mix(P["primary"], "FFFFFF", 0.25)
        for col, idxs, a in (("FFFFFF", (0, 2, 4), 120 if not dark else 18), (tint, (1, 3), 70 if not dark else 55)):
            lay = _layer((w, h), col)
            d = ImageDraw.Draw(lay)
            for i in idxs:
                fx, fy = spots[i]
                r = h * rnd.uniform(0.22, 0.38)
                cx, cy = fx * w, fy * h
                d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=_rgba(col, a))
            _paste(base, _blur(lay, h * 0.12))

    if "clouds" in decor:
        mask = Image.new("L", (w, h), 0)
        md = ImageDraw.Draw(mask)
        for _ in range(4):
            cx, cy = rnd.uniform(0.08, 0.92) * w, rnd.uniform(0.2, 0.5) * h
            s_ = rnd.uniform(0.04, 0.075) * w
            one = Image.new("L", (w, h), 0)
            od = ImageDraw.Draw(one)
            for dx, dy, rr in [(-1.1, 0.15, 0.5), (-0.4, -0.25, 0.78), (0.45, -0.1, 0.62), (1.1, 0.15, 0.48)]:
                od.ellipse([cx + dx * s_ - rr * s_, cy + dy * s_ - rr * s_, cx + dx * s_ + rr * s_, cy + dy * s_ + rr * s_], fill=255)
            od.rectangle([0, cy + 0.35 * s_, w, h], fill=0)  # flat cloud bottom
            mask = ImageChops.lighter(mask, one)
        lay = Image.new("RGBA", (w, h), (255, 255, 255, 0))
        lay.putalpha(mask.point(lambda v: v * 0.5))
        _paste(base, _blur(lay, 2))

    if "hills" in decor:
        lay = _layer((w, h))
        d = ImageDraw.Draw(lay)
        for i, k in enumerate([0.12, 0.2, 0.3]):
            col = mix(P["bg_bottom"], P["primary"], k)
            yb = h * (0.80 + i * 0.06)
            amp = h * (0.05 - i * 0.01)
            ph = rnd.uniform(0, 6.28)
            pts = [(0, h)]
            for x in range(0, w + 20, 20):
                y = yb - amp * math.sin(x / w * math.pi * (1.4 + i * 0.5) + ph) - amp * 0.4 * math.sin(x / w * 7 + ph)
                pts.append((x, y))
            pts.append((w, h))
            d.polygon(pts, fill=_rgba(col, 120 + i * 30))
        _paste(base, _blur(lay, 2))

    if "arcs" in decor:
        lay = _layer((w * SS, h * SS))
        d = ImageDraw.Draw(lay)
        col = _rgba("FFFFFF", 150 if not dark else 45)
        for i in range(3):
            rx = w * SS * rnd.uniform(0.7, 1.1)
            cy = h * SS * rnd.uniform(1.15, 1.45)
            cx = w * SS * rnd.uniform(0.3, 0.7)
            d.ellipse([cx - rx, cy - rx * 0.62, cx + rx, cy + rx * 0.62], outline=col, width=3 * SS)
        lay = lay.resize((w, h), Image.LANCZOS)
        _paste(base, lay)

    if "grid" in decor:
        lay = _layer((w, h), "FFFFFF")
        d = ImageDraw.Draw(lay)
        col = _rgba(mix(P["primary"], "FFFFFF", 0.35) if not dark else mix(P["primary"], "FFFFFF", 0.3), 70 if not dark else 55)
        step = 48
        for gx in range(step // 2, w, step):
            for gy in range(step // 2, h, step):
                d.ellipse([gx - 1.6, gy - 1.6, gx + 1.6, gy + 1.6], fill=col)
        # fade the grid towards the centre so it never fights with text
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).ellipse([-w * 0.25, -h * 0.35, w * 1.25, h * 1.35], fill=255)
        mask = _blur(mask, h * 0.2).point(lambda v: 255 - int(v * 0.85))
        lay.putalpha(ImageChops.multiply(lay.getchannel("A"), mask))
        _paste(base, lay)

    if "grain" in decor:
        import numpy as np
        rng = np.random.default_rng(seed)
        noise = rng.normal(0, 1, (h // 2, w // 2))
        g = Image.fromarray(np.clip(128 + noise * 40, 0, 255).astype("uint8")).resize((w, h))
        tone = Image.new("RGBA", (w, h), _rgba(mix(P["bg_bottom"], "000000", 0.35), 0))
        tone.putalpha(g.point(lambda v: int(abs(v - 128) * 0.22)))
        _paste(base, tone)

    if "mist" in decor:
        _mist(base, style, w, h, variant, rnd, dark)
    if "rings" in decor:
        _rings(base, style, w, h, variant, dark)
    if "silk" in decor:
        _silk(base, style, w, h, variant, rnd)
    if "torn" in decor:
        _torn(base, style, w, h, variant, rnd)
    if "geo" in decor:
        _geo(base, style, w, h, variant)
    if "scene" in decor:
        _scene(base, style, w, h, variant)
    if "band" in decor:
        # a solid block of colour: along the bottom of the cover, down the left edge elsewhere
        col = _tok(style, bgcfg.get("band_color"), "primary")
        lay = _layer((w, h))
        d = ImageDraw.Draw(lay)
        if variant == "cover":
            d.rectangle([0, h * 0.8, w, h], fill=_rgba(col))
        else:
            d.rectangle([0, 0, w * 0.012, h], fill=_rgba(col))
        _paste(base, lay)

    if "bokeh" in decor:
        lay = _layer((w, h), "FFFFFF")
        d = ImageDraw.Draw(lay)
        for _ in range(18):
            r = rnd.uniform(4, 26)
            x, y = rnd.uniform(0, w), rnd.uniform(0, h)
            d.ellipse([x - r, y - r, x + r, y + r], fill=_rgba("FFFFFF", rnd.randint(60, 150) if not dark else rnd.randint(20, 60)))
        _paste(base, _blur(lay, 1.5))
    return base.convert("RGB")


# ------------------------------------------------------------------ motif backgrounds
def _tok(style, v, default):
    """A colour from background config: palette token or hex."""
    v = v or default
    return style.palette.get(v, v).lstrip("#")


def _mist(base, style, w, h, variant, rnd, dark):
    """Large saturated soft clouds in two colours (primary + accent), pastel gradient look."""
    P = style.palette
    cols = [mix("FFFFFF", P["primary"], 0.55), mix("FFFFFF", P["accent"], 0.55)]
    if variant == "cover":
        spots = [(0.12, 0.2, 0.42, 0), (0.85, 0.75, 0.48, 1), (0.6, 0.05, 0.25, 0)]
    else:
        spots = [(0.95, 0.1, 0.3, 0), (0.05, 0.95, 0.32, 1)]
    for fx, fy, fr, ci in spots:
        lay = _layer((w, h), cols[ci])
        r = h * fr
        cx, cy = fx * w, fy * h
        ImageDraw.Draw(lay).ellipse([cx - r * 1.25, cy - r, cx + r * 1.25, cy + r], fill=_rgba(cols[ci], 150 if not dark else 70))
        _paste(base, _blur(lay, h * 0.16))


def _rings(base, style, w, h, variant, dark):
    """Concentric thin ellipses sweeping off the canvas, like ripples of light."""
    cfg = style.background or {}
    col = _tok(style, cfg.get("line_color"), "accent")
    W, H = w * SS, h * SS
    lay = _layer((W, H), col)
    d = ImageDraw.Draw(lay)
    if variant == "cover":
        cx, cy, n, r0, step, amax = W * 0.62, H * 0.48, 26, W * 0.06, W * 0.022, 235
    elif variant == "closing":
        cx, cy, n, r0, step, amax = W * 0.8, H * 0.55, 22, W * 0.05, W * 0.02, 190
    else:
        cx, cy, n, r0, step, amax = W * 1.02, H * 0.2, 18, W * 0.05, W * 0.022, 120
    for i in range(n):
        rx = r0 + i * step
        ry = rx * 0.42
        a = amax * (0.35 + 0.65 * math.sin(math.pi * (i + 1) / (n + 1)))
        d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], outline=_rgba(col, a), width=max(2, int(1.7 * SS)))
    lay = lay.rotate(-14, resample=Image.BICUBIC, center=(cx, cy)).resize((w, h), Image.LANCZOS)
    glow = _blur(lay, 6)
    _paste(base, glow)
    _paste(base, lay)


def _silk(base, style, w, h, variant, rnd):
    """Bundles of fine flowing lines, like light on silk (gold on dark styles)."""
    cfg = style.background or {}
    col = _tok(style, cfg.get("line_color"), "accent")
    W, H = w * SS, h * SS
    lay = _layer((W, H), col)
    d = ImageDraw.Draw(lay)
    bands = [(0.12, 1.0), (0.9, 0.9)] if variant != "content" else [(0.95, 0.55)]
    if variant == "closing":
        bands = [(0.2, 0.8), (0.88, 1.0)]
    for yb, strength in bands:
        ph = rnd.uniform(0, 6.28)
        for i in range(34):
            k = i / 33
            amp = H * (0.05 + 0.05 * k)
            off = (k - 0.5) * H * 0.09
            pts = []
            for x in range(-40, W + 60, 24):
                t = x / W
                y = yb * H + off + amp * math.sin(t * math.pi * 1.6 + ph + k * 0.9) + H * 0.02 * math.sin(t * 9 + ph)
                pts.append((x, y))
            a = int(strength * (25 + 110 * math.sin(math.pi * k) ** 2))
            d.line(pts, fill=_rgba(col, a), width=max(1, int(0.8 * SS)))
    lay = lay.resize((w, h), Image.LANCZOS)
    _paste(base, _blur(lay, 3))
    _paste(base, lay)


def _torn_edge(W, y0, rnd, rough):
    """Y positions of a torn-paper edge: slow waves, fine fibre jitter and a few small notches."""
    ph = [rnd.uniform(0, 6.28) for _ in range(3)]
    pts = []
    for x in range(0, W + 6, 6):
        t = x / W
        y = y0 + rough * (0.55 * math.sin(t * 5.1 + ph[0]) + 0.3 * math.sin(t * 13.7 + ph[1]) + 0.15 * math.sin(t * 31 + ph[2]))
        pts.append([x, y])
    # a few wide shallow bites, then fine fibre jitter
    for _ in range(max(2, W // 400)):
        c, wd, dp = rnd.uniform(0, W), rnd.uniform(40, 120), rnd.uniform(0.25, 0.5) * rough
        for p in pts:
            k = abs(p[0] - c) / wd
            if k < 1:
                p[1] += dp * (1 - k * k)
    return [(x, y + rnd.uniform(-1, 1) * 1.2) for x, y in pts]


def _torn(base, style, w, h, variant, rnd):
    """A dark band with a torn-paper edge plus a few splatter dots in the accent colour."""
    cfg = style.background or {}
    col = _tok(style, cfg.get("band_color"), "primary_dark")
    acc = style.palette["accent"]
    lay = _layer((w, h), col)
    d = ImageDraw.Draw(lay)
    if variant == "cover":
        edge = _torn_edge(w, h * 0.8, rnd, h * 0.03)
        d.polygon([(0, h)] + edge + [(w, h)], fill=_rgba(col, 255))
    elif variant == "closing":
        edge = _torn_edge(w, h * 0.2, rnd, h * 0.03)
        d.polygon([(0, 0)] + edge + [(w, 0)], fill=_rgba(col, 255))
    else:
        edge = _torn_edge(w, h * 0.972, rnd, h * 0.01)
        d.polygon([(0, h)] + edge + [(w, h)], fill=_rgba(col, 255))
    # a lighter paper fibre line just outside the tear
    fib = [(x, y + (-3 if variant == "closing" else 3)) for x, y in edge]
    d.line(fib, fill=_rgba(col, 60), width=3)
    _paste(base, lay)
    spl = _layer((w, h), acc)
    sd = ImageDraw.Draw(spl)
    cx, cy = (w * 0.9, h * 0.74) if variant == "cover" else ((w * 0.93, h * 0.26) if variant == "closing" else (w * 0.93, h * 0.12))
    for _ in range(12 if variant != "content" else 6):
        r = rnd.uniform(3, 14)
        x, y = cx + rnd.gauss(0, w * 0.03), cy + rnd.gauss(0, h * 0.035)
        sd.ellipse([x - r, y - r, x + r, y + r], fill=_rgba(acc, 220))
    _paste(base, spl)


def _geo(base, style, w, h, variant):
    """Bold primitive shapes (circle, half circle, triangle, quarter disc, square) in flat colours."""
    cfg = style.background or {}
    P = style.palette
    cols = [c.lstrip("#") for c in cfg.get("geo_colors", [])] or [P["primary"], P["accent"], P["primary_dark"]]
    W, H = w * SS, h * SS
    lay = _layer((W, H))
    d = ImageDraw.Draw(lay)
    u = H * (0.2 if variant == "cover" else 0.1)

    def shape(kind, x, y, s, c):
        c = _rgba(cols[c % len(cols)])
        if kind == "circle":
            d.ellipse([x, y, x + s, y + s], fill=c)
        elif kind == "half":
            d.pieslice([x, y, x + s, y + s], 180, 360, fill=c)
        elif kind == "half_r":
            d.pieslice([x - s / 2, y, x + s / 2, y + s], 270, 450, fill=c)
        elif kind == "tri":
            d.polygon([(x + s / 2, y), (x + s, y + s), (x, y + s)], fill=c)
        elif kind == "quarter":
            d.pieslice([x - s, y - s, x + s, y + s], 0, 90, fill=c)
        elif kind == "square":
            d.rectangle([x, y, x + s, y + s], fill=c)
        elif kind == "ring":
            d.ellipse([x, y, x + s, y + s], outline=c, width=int(s * 0.16))

    if variant == "cover":
        plan = [("quarter", 0, 0, u * 1.2, 0), ("half", W - u * 2.1, -u * 0.5, u * 1.0, 1), ("ring", W - u * 1.1, u * 0.1, u * 0.9, 2),
                ("tri", W - u * 1.6, H - u * 1.1, u * 0.9, 3), ("circle", -u * 0.45, H - u * 1.0, u * 1.1, 1)]
    elif variant == "closing":
        plan = [("circle", -u * 0.8, -u * 0.8, u * 2.2, 1), ("tri", W - u * 2.4, H - u * 1.9, u * 1.7, 0),
                ("square", W - u * 0.9, H * 0.35, u * 0.6, 3)]
    else:
        plan = [("quarter", W, 0, u * 0.0, 0), ("half", W - u * 2.5, -u * 0.5, u * 1.0, 0), ("ring", W - u * 1.25, u * 0.15, u * 0.85, 1),
                ("tri", W - u * 1.1, H - u * 0.95, u * 0.7, 2)]
    for kind, x, y, s_, c in plan:
        if s_ > 0:
            shape(kind, x, y, s_, c)
    _paste(base, lay.resize((w, h), Image.LANCZOS))


def _scene(base, style, w, h, variant):
    """Flat landscape along the bottom: layered hills, a soft dome, houses, wind turbines,
    round trees and solar panels. Coloured from the palette; cover and closing only."""
    if variant == "content":
        return
    P = style.palette
    cfg = style.background or {}
    rnd = random.Random(23)
    W, H = w * SS, h * SS
    k = W / 1920.0
    lay = _layer((W, H))
    d = ImageDraw.Draw(lay)
    green = P["primary"]
    teal = cfg.get("scene_teal", mix(green, "6FC7B4", 0.6)).lstrip("#")
    dark = cfg.get("scene_dark", "4C5270").lstrip("#")
    sky = cfg.get("scene_sky", "8FCFD8").lstrip("#")
    leaf = mix(teal, "FFFFFF", 0.15)
    top = H * (0.56 if variant == "cover" else 0.6)
    ground = H * 0.955

    def C(hexv, a=255):
        return _rgba(hexv, a)

    # soft dome behind everything
    r = 380 * k
    cx = W * 0.5
    d.ellipse([cx - r, ground - r * 1.02, cx + r, ground + r * 0.98], fill=C(mix("FFFFFF", sky, 0.75), 200))
    for _ in range(9):
        bx, by = cx + rnd.uniform(-0.6, 0.6) * r, ground - rnd.uniform(0.45, 0.95) * r
        br = rnd.uniform(6, 26) * k
        d.ellipse([bx - br, by - br, bx + br, by + br], fill=C("FFFFFF", 150))
    # hills, back to front
    for i, (amp, base_y, col, ph) in enumerate([(150, 0.80, mix(teal, "FFFFFF", 0.35), 0.3),
                                                 (120, 0.86, mix(teal, green, 0.25), 1.7),
                                                 (90, 0.91, mix(teal, "FFFFFF", 0.1), 3.1)]):
        pts = [(0, H)]
        for x in range(0, W + 30, 30):
            t = x / W
            y = H * base_y - amp * k * (0.6 * math.sin(t * math.pi * 2.2 + ph) + 0.4 * math.sin(t * 7 + ph)) ** 2
            pts.append((x, max(top, y)))
        pts.append((W, H))
        d.polygon(pts, fill=C(col, 235))

    def tree(x, s, col):
        d.line([(x, ground), (x, ground - 70 * s)], fill=C(dark, 230), width=max(2, int(5 * s)))
        d.ellipse([x - 42 * s, ground - 150 * s, x + 42 * s, ground - 62 * s], fill=C(col))

    def house(x, s, wall="F3F7F4"):
        bw, bh = 170 * s, 110 * s
        d.rectangle([x, ground - bh, x + bw, ground], fill=C(wall))
        d.polygon([(x - 18 * s, ground - bh), (x + bw / 2, ground - bh - 75 * s), (x + bw + 18 * s, ground - bh)],
                  fill=C(dark))
        for wx in (x + 22 * s, x + bw - 58 * s):
            d.rectangle([wx, ground - bh + 30 * s, wx + 36 * s, ground - bh + 66 * s], fill=C(mix(sky, "FFFFFF", 0.3)))
        d.rectangle([x + bw / 2 - 16 * s, ground - 58 * s, x + bw / 2 + 16 * s, ground], fill=C(mix(teal, dark, 0.3)))

    def turbine(x, s, ang):
        hy = ground - 420 * s
        d.polygon([(x - 5 * s, ground), (x + 5 * s, ground), (x + 2.5 * s, hy), (x - 2.5 * s, hy)], fill=C(dark, 235))
        for a in (ang, ang + 120, ang + 240):
            rad = math.radians(a)
            ex, ey = x + math.cos(rad) * 150 * s, hy + math.sin(rad) * 150 * s
            px, py = -math.sin(rad) * 11 * s, math.cos(rad) * 11 * s
            d.polygon([(x, hy), (x + (ex - x) * 0.25 + px, hy + (ey - hy) * 0.25 + py), (ex, ey)],
                      fill=C(mix(teal, "FFFFFF", 0.25)))
        d.ellipse([x - 12 * s, hy - 12 * s, x + 12 * s, hy + 12 * s], fill=C(mix(teal, "FFFFFF", 0.4)))

    def solar(x, s):
        pw, ph = 170 * s, 95 * s
        quad = [(x, ground), (x + pw, ground), (x + pw - 25 * s, ground - ph), (x - 25 * s, ground - ph)]
        d.polygon(quad, fill=C(dark))
        for j in range(1, 5):
            t = j / 5
            d.line([(x + pw * t, ground - 4 * s), (x + pw * t - 25 * s, ground - ph + 4 * s)],
                   fill=C(mix(dark, sky, 0.45)), width=max(1, int(2 * s)))
        for j in range(1, 3):
            t = j / 3
            d.line([(x - 25 * s * t, ground - ph * t), (x + pw - 25 * s * t, ground - ph * t)],
                   fill=C(mix(dark, sky, 0.45)), width=max(1, int(2 * s)))

    s1 = k * (1.0 if variant == "cover" else 0.85)
    turbine(W * 0.19, s1, 15)
    turbine(W * 0.29, s1 * 0.8, 40)
    turbine(W * 0.86, s1 * 1.05, 70)
    for x, sc, col in ((0.06, 0.9, leaf), (0.24, 1.1, teal), (0.38, 1.25, leaf), (0.66, 1.2, teal),
                       (0.77, 0.95, leaf), (0.95, 1.0, teal)):
        tree(W * x, sc * s1, col)
    house(W * 0.42, s1 * 1.15)
    house(W * 0.54, s1 * 0.9, wall=mix("F3F7F4", teal, 0.15))
    house(W * 0.80, s1 * 0.75)
    solar(W * 0.11, s1)
    solar(W * 0.66, s1 * 1.05)
    # fence
    for j in range(16):
        fx = W * 0.47 + j * 14 * s1
        d.rectangle([fx, ground - 40 * s1, fx + 6 * s1, ground], fill=C("FFFFFF", 235))
    d.rectangle([W * 0.47, ground - 30 * s1, W * 0.47 + 16 * 14 * s1, ground - 25 * s1], fill=C("FFFFFF", 235))
    # ground strip
    d.rectangle([0, ground, W, H], fill=C(mix(teal, "FFFFFF", 0.55)))
    _paste(base, lay.resize((w, h), Image.LANCZOS))


# ------------------------------------------------------------------ small decor
def leaf(color, size=160, flip=False):
    W = size * SS
    lay = _layer((W, W))
    d = ImageDraw.Draw(lay)
    pts = []
    for t in range(0, 101):
        a = t / 100 * math.pi
        x = W * 0.1 + (W * 0.8) * t / 100
        y = W * 0.5 - math.sin(a) * W * 0.28
        pts.append((x, y))
    for t in range(100, -1, -1):
        a = t / 100 * math.pi
        x = W * 0.1 + (W * 0.8) * t / 100
        y = W * 0.5 + math.sin(a) * W * 0.12
        pts.append((x, y))
    d.polygon(pts, fill=_rgba(color))
    d.line([(W * 0.12, W * 0.5), (W * 0.86, W * 0.47)], fill=_rgba(mix(color, "FFFFFF", 0.45)), width=max(2, W // 60))
    lay = lay.rotate(28, resample=Image.BICUBIC)
    if flip:
        lay = lay.transpose(Image.FLIP_LEFT_RIGHT)
    return lay.resize((size, size), Image.LANCZOS)


def brush(color, w=900, h=260, seed=3, alpha=235):
    """Rough dry-brush stroke (highlighter behind a word or number)."""
    rnd = random.Random(seed)
    W, H = w * SS, h * SS
    lay = _layer((W, H), color)
    d = ImageDraw.Draw(lay)
    for i in range(90):
        band = rnd.uniform(0.22, 0.78)
        y = H * band
        edge = abs(band - 0.5) * 2  # strokes near the band edge are shorter -> ragged ends
        x0 = W * rnd.uniform(0.0, 0.06 + 0.12 * edge)
        x1 = W * rnd.uniform(0.9 - 0.14 * edge, 1.0)
        th = H * rnd.uniform(0.035, 0.08)
        pts = [(x0 + (x1 - x0) * t / 12, y + H * 0.025 * math.sin(t * 0.9 + i)) for t in range(13)]
        d.line(pts, fill=_rgba(color, rnd.randint(int(alpha * 0.35), int(alpha * 0.7))), width=int(th))
    # a few dry gaps
    for _ in range(14):
        y = H * rnd.uniform(0.25, 0.75)
        x0 = W * rnd.uniform(0.05, 0.7)
        d.line([(x0, y), (x0 + W * rnd.uniform(0.05, 0.25), y)], fill=_rgba(color, 0), width=int(H * 0.012))
    return lay.resize((w, h), Image.LANCZOS)


def sparkle(color, size=80):
    W = size * SS
    lay = _layer((W, W))
    d = ImageDraw.Draw(lay)
    c = W / 2
    r1, r2 = W * 0.48, W * 0.1
    pts = []
    for i in range(8):
        a = i * math.pi / 4 - math.pi / 2
        r = r1 if i % 2 == 0 else r2
        pts.append((c + r * math.cos(a), c + r * math.sin(a)))
    d.polygon(pts, fill=_rgba(color))
    return lay.resize((size, size), Image.LANCZOS)


def tinted_icon(name, color, size=256):
    p = find_icon(name)
    if not p:
        return None
    im = Image.open(p).convert("RGBA").resize((size, size), Image.LANCZOS)
    col = Image.new("RGBA", im.size, _rgba(color))
    col.putalpha(im.getchannel("A"))
    return col


# ------------------------------------------------------------------ hero illustrations
def _shadow(size, box, radius, color, alpha, blur, offset):
    lay = _layer(size, color)
    d = ImageDraw.Draw(lay)
    x0, y0, x1, y1 = box
    d.rounded_rectangle([x0, y0 + offset, x1, y1 + offset], radius=radius, fill=_rgba(color, alpha))
    return _blur(lay, blur)


def _grad_rounded(size_box, radius, top, bottom):
    w, h = size_box
    g = vgradient(w, h, top, bottom).convert("RGBA")
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    g.putalpha(m)
    return g


FLAT = {"on": False}


def _tile(canvas, cx, cy, s, P, content=None, glyph=None, circle=False, icon_color=None):
    """Glossy tile with drop shadow (or a flat sticker in flat look); content = icon name or glyph letter."""
    W, H = canvas.size
    r = s * (0.5 if circle else 0.24)
    box = [cx - s / 2, cy - s / 2, cx + s / 2, cy + s / 2]
    if FLAT["on"]:
        tile = _layer((int(s), int(s)))
        d = ImageDraw.Draw(tile)
        lw = max(3, int(s * 0.035))
        d.rounded_rectangle([lw, lw, s - lw - 1, s - lw - 1], radius=int(r), fill=_rgba(P.get("surface", "FFFFFF")),
                            outline=_rgba(P["primary_dark"]), width=lw)
        canvas.alpha_composite(tile, (int(box[0]), int(box[1])))
    else:
        canvas.alpha_composite(_shadow((W, H), box, r, P["primary_dark"], 70, s * 0.09, s * 0.07))
        tile = _grad_rounded((int(s), int(s)), int(r), "FFFFFF", mix("FFFFFF", P["primary"], 0.16))
        d = ImageDraw.Draw(tile)
        d.rounded_rectangle([2, 2, s - 3, s - 3], radius=int(r), outline=_rgba("FFFFFF", 230), width=max(2, int(s * 0.02)))
    if not FLAT["on"]:
        canvas.alpha_composite(tile, (int(box[0]), int(box[1])))
    ic = icon_color or P["primary"]
    if glyph:
        fs = int(s * 0.62)
        f = get_font(fs, bold=True)
        m = Image.new("L", (int(s), int(s)), 0)
        md = ImageDraw.Draw(m)
        bb = md.textbbox((0, 0), glyph, font=f)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        md.text(((s - tw) / 2 - bb[0], (s - th) / 2 - bb[1]), glyph, font=f, fill=255)
        g = vgradient(int(s), int(s), mix(P["primary"], "FFFFFF", 0.15), P["primary_dark"]).convert("RGBA")
        g.putalpha(m)
        canvas.alpha_composite(g, (int(box[0]), int(box[1])))
    elif content:
        ico = tinted_icon(content, ic, int(s * 0.5))
        if ico:
            canvas.alpha_composite(ico, (int(cx - s * 0.25), int(cy - s * 0.25)))


def hero(style, w=1400, h=1200, scene="tile", glyph=None, icons=None, seed=11):
    """Transparent PNG illustration built from palette + icons.

    scene: tile   big glossy app tile (glyph or icon) with orbit and satellites
           badge  big round badge with one icon
           cards  stacked cards (documents / lists / steps)
           chart  card with rising bars (data / growth)
    """
    rnd = random.Random(seed)
    P = style.palette
    FLAT["on"] = (style.illustration or {}).get("fallback_look") == "flat"
    icons = list(icons or [])
    W, H = w * SS, h * SS
    cv = _layer((W, H))
    d = ImageDraw.Draw(cv)
    m = min(W, H)
    cx, cy = W / 2, H * 0.48

    # glow
    flat = (style.illustration or {}).get("fallback_look") == "flat"
    dark = getattr(style, "dark", False)
    gcol = P["primary"] if dark else mix("FFFFFF", P["primary"], 0.28)
    if not flat:
        glow = _layer((W, H), gcol)
        gd = ImageDraw.Draw(glow)
        gd.ellipse([cx - m * 0.42, cy - m * 0.42, cx + m * 0.42, cy + m * 0.42], fill=_rgba(gcol, 120 if dark else 170))
        cv.alpha_composite(_blur(glow, m * 0.07))

    # pedestal
    py = H * 0.84
    ped = _layer((W, H), "FFFFFF")
    pd = ImageDraw.Draw(ped)
    pd.ellipse([cx - m * 0.33, py - m * 0.06, cx + m * 0.33, py + m * 0.06], fill=_rgba(mix("FFFFFF", P["primary"], 0.22), 200))
    pd.ellipse([cx - m * 0.27, py - m * 0.045, cx + m * 0.27, py + m * 0.035], fill=_rgba("FFFFFF", 230))
    cv.alpha_composite(_blur(ped, 2))

    # orbit
    orb = _layer((W, H))
    od = ImageDraw.Draw(orb)
    rx, ry = m * 0.46, m * 0.17
    od.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], outline=_rgba(P["primary"], 90), width=max(3, int(m * 0.004)))
    for k in range(5):
        a = rnd.uniform(0, 6.28)
        x, y = cx + rx * math.cos(a), cy + ry * math.sin(a)
        rr = m * rnd.uniform(0.008, 0.016)
        od.ellipse([x - rr, y - rr, x + rr, y + rr], fill=_rgba(P["primary"], 200))
    orb = orb.rotate(-12, center=(cx, cy), resample=Image.BICUBIC)
    cv.alpha_composite(orb)

    s = m * 0.40
    if scene == "cards":
        for i, (ang, off) in enumerate([(-10, -0.06), (6, 0.04), (0, 0)]):
            cw, ch = m * 0.46, m * 0.56
            card = _layer((int(cw * 1.5), int(ch * 1.5)))
            ox, oy = (card.size[0] - cw) / 2, (card.size[1] - ch) / 2
            cd = ImageDraw.Draw(card)
            fill = "FFFFFF" if i == 2 else mix("FFFFFF", P["primary"], 0.12 + 0.08 * i)
            cd.rounded_rectangle([ox, oy, ox + cw, oy + ch], radius=int(m * 0.04), fill=_rgba(fill))
            if i == 2:
                for j in range(4):
                    yy = oy + ch * (0.22 + j * 0.17)
                    cd.ellipse([ox + cw * 0.1, yy - m * 0.018, ox + cw * 0.1 + m * 0.036, yy + m * 0.018], fill=_rgba(P["primary"]))
                    cd.rounded_rectangle([ox + cw * 0.26, yy - m * 0.012, ox + cw * (0.85 - 0.12 * (j % 2)), yy + m * 0.012],
                                         radius=int(m * 0.012), fill=_rgba(mix("FFFFFF", P["primary"], 0.35)))
            card = card.rotate(ang, resample=Image.BICUBIC)
            px, py2 = int(cx - card.size[0] / 2 + off * m), int(cy - card.size[1] / 2)
            shadow = _layer((W, H), P["primary_dark"])
            ImageDraw.Draw(shadow).rounded_rectangle([px + ox, py2 + oy + m * 0.03, px + ox + cw, py2 + oy + ch + m * 0.03],
                                                     radius=int(m * 0.04), fill=_rgba(P["primary_dark"], 45))
            cv.alpha_composite(_blur(shadow, m * 0.03))
            cv.alpha_composite(card, (px, py2))
        if icons:
            _tile(cv, cx + m * 0.22, cy - m * 0.24, m * 0.17, P, content=icons.pop(0), circle=True)
    elif scene == "chart":
        cw, ch = m * 0.62, m * 0.46
        box = [cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2]
        cv.alpha_composite(_shadow((W, H), box, m * 0.04, P["primary_dark"], 60, m * 0.03, m * 0.03))
        card = _grad_rounded((int(cw), int(ch)), int(m * 0.04), "FFFFFF", mix("FFFFFF", P["primary"], 0.1))
        cd = ImageDraw.Draw(card)
        n = 5
        for i in range(n):
            bh = ch * (0.18 + 0.13 * i)
            bx = cw * (0.12 + i * 0.16)
            col = P["primary"] if i == n - 1 else mix("FFFFFF", P["primary"], 0.35 + 0.1 * i)
            cd.rounded_rectangle([bx, ch * 0.88 - bh, bx + cw * 0.1, ch * 0.88], radius=int(cw * 0.02), fill=_rgba(col))
        cd.line([(cw * 0.12, ch * 0.62), (cw * 0.4, ch * 0.5), (cw * 0.6, ch * 0.4), (cw * 0.86, ch * 0.16)],
                fill=_rgba(P["accent"]), width=int(m * 0.012), joint="curve")
        cv.alpha_composite(card, (int(box[0]), int(box[1])))
        if icons:
            _tile(cv, box[2] - m * 0.02, box[1] + m * 0.02, m * 0.16, P, content=icons.pop(0), circle=True)
    elif scene == "badge":
        _tile(cv, cx, cy, s * 1.05, P, content=icons.pop(0) if icons else "sparkles", circle=True)
    else:  # tile
        _tile(cv, cx, cy, s, P, glyph=glyph if glyph else None, content=None if glyph else (icons.pop(0) if icons else "sparkles"))

    # satellites
    spots = [(0.17, 0.28), (0.85, 0.24), (0.88, 0.66), (0.13, 0.66)]
    rnd.shuffle(spots)
    for (fx, fy), ic in zip(spots, icons[:3]):
        _tile(cv, W * fx, H * fy, m * 0.13, P, content=ic, circle=rnd.random() < 0.5)

    # sparkles
    if style.decor.get("sparkles", True):
        for i in range(4):
            sz = int(m * rnd.uniform(0.03, 0.055))
            sp = sparkle(P["accent"] if i % 2 else P["primary"], sz)
            x, y = rnd.uniform(0.08, 0.92) * W, rnd.uniform(0.08, 0.6) * H
            cv.alpha_composite(sp, (int(x), int(y)))
    return cv.resize((w, h), Image.LANCZOS)
