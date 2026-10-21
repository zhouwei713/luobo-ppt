"""Layout library. Each layout turns one semantic slide (deck.json) into
positioned elements on a 13.333 x 7.5 inch canvas.

Element types consumed by build_deck.py:
  {"t":"text", x,y,w,h, text, size, color, bold, font, align, valign, ls, spc}
  {"t":"rect", x,y,w,h, fill, alpha, radius, line, line_w, shadow}
  {"t":"ellipse", x,y,w,h, fill, alpha, line}
  {"t":"image", x,y,w,h, path, fit}
  {"t":"icon", x,y,size, name, color, bg, bg_alpha, circle}

Every layout returns (elements, info) where info may contain:
  master: "content" | "cover" | "closing"   which background + chrome to use
  uses_takeaway: True when the layout placed slide["takeaway"] itself
  header: False to suppress the series header
"""
from common import fit_size, n_lines, text_width_pt, CANVAS_W, CANVAS_H, DISPLAY_LATIN, LINE_PITCH

# content frame
MX = 0.8                      # side margin
CW = CANVAS_W - 2 * MX        # content width
TITLE_Y = 0.95
CONTENT_Y = 2.15
CONTENT_B = 6.05              # content bottom (pill starts at 6.3)


class Ctx:
    def __init__(self, style, meta, assets, plan_slide):
        self.S = style
        self.meta = meta
        self.assets = assets          # id -> path
        self.p = plan_slide or {}
        self.icons = list(self.p.get("icons", []))

    def asset(self, key):
        aid = self.p.get(key)
        return self.assets.get(aid) if aid else None

    def icon(self, i, default):
        return self.icons[i] if i < len(self.icons) and self.icons[i] else default


# ------------------------------------------------------------------ primitives
def T(text, x, y, w, h, size, color="text", bold=False, font="body", align="l", valign="t",
      ls=1.2, spc=0):
    return {"t": "text", "x": x, "y": y, "w": w, "h": h, "text": text, "size": size, "color": color,
            "bold": bold, "font": font, "align": align, "valign": valign, "ls": ls, "spc": spc}


def R(x, y, w, h, fill="surface", alpha=1.0, radius=None, line=None, line_w=0.75, shadow=False):
    return {"t": "rect", "x": x, "y": y, "w": w, "h": h, "fill": fill, "alpha": alpha,
            "radius": radius, "line": line, "line_w": line_w, "shadow": shadow}


def E(x, y, w, h, fill, alpha=1.0, line=None, line_w=1.5):
    return {"t": "ellipse", "x": x, "y": y, "w": w, "h": h, "fill": fill, "alpha": alpha, "line": line, "line_w": line_w}


def LN(x1, y1, x2, y2, color="line", w=1.5, dash=False, arrow=False):
    return {"t": "line", "x1": x1, "y1": y1, "x2": x2, "y2": y2, "color": color, "lw": w, "dash": dash,
            "arrow": arrow, "x": min(x1, x2), "y": min(y1, y2), "w": abs(x2 - x1), "h": abs(y2 - y1)}


def IMG(path, x, y, w, h, fit="contain", align="center"):
    return {"t": "image", "x": x, "y": y, "w": w, "h": h, "path": path, "fit": fit, "align": align}


def ICON(name, x, y, size, color="primary", bg="tint", bg_alpha=1.0, circle=True, pad=0.24):
    return {"t": "icon", "x": x, "y": y, "size": size, "name": name, "color": color, "bg": bg,
            "bg_alpha": bg_alpha, "circle": circle, "pad": pad}


# ------------------------------------------------------------------ build steps (animation)
# Elements made inside an item loop carry "step": i, so the builder can bring each item in on
# its own (one click, or one beat of the automatic build). Layouts call step(i) at the top of
# the loop body and step_end() after the loop; untagged elements (title, background, chrome)
# are on the slide from the start.
_STEP = {"cur": None, "n": -1}


def step(i=None):
    if i is None:
        i = _STEP["n"] + 1
    _STEP["cur"] = i
    _STEP["n"] = max(_STEP["n"], i)


def step_end():
    _STEP["cur"] = None


def step_reset():
    _STEP.update(cur=None, n=-1)


def _stepped(fn):
    def make(*a, **k):
        d = fn(*a, **k)
        if _STEP["cur"] is not None:
            d["step"] = _STEP["cur"]
        return d
    make.__name__, make.__doc__ = fn.__name__, fn.__doc__
    return make


T, R, E, LN, IMG, ICON = (_stepped(f) for f in (T, R, E, LN, IMG, ICON))



def item_mark(ctx, items, i, default, x, y, size, **kw):
    """Icon in front of an item, or the item's own number when the source deck numbered it
    (item field "num", e.g. "01"): numbered originals keep their numbers in every style."""
    it = items[i] if i < len(items) and isinstance(items[i], dict) else {}
    if it.get("num"):
        num = str(it["num"])
        fs = max(11, min(28, round(size * 72 * 0.55)))
        w = max(size, text_width_pt(num, fs, True, DISPLAY_LATIN) / 72 + 0.08)
        h = max(size, fs * 1.3 / 72)
        e = T(num, x, y + (size - h) / 2, w, h, fs, "on_primary" if kw.get("bg") == "surface" else ("highlight" if fs >= 14 else "label"),
              True, "display", valign="m", ls=1.0)
        e["role"] = "marker"
        return e
    return ICON(ctx.icon(i, default), x, y, size, **kw)

def card(ctx, x, y, w, h, kind="glass"):
    """Card in the style's depth: flat (fill only), ring (1px edge), whisper (soft halo), shadow."""
    S = ctx.S
    r = S.shape.get("radius", 0.16)
    d = getattr(S, "depth", "shadow")
    if d == "outline":
        # sticker look (thick ink edge + hard offset shadow), as in pop / comic brand manuals
        lw = S.shape.get("outline_w", 2.25)
        if kind == "primary":
            return R(x, y, w, h, fill="primary", radius=r, line="line", line_w=lw, shadow="hard")
        if kind == "tint":
            return R(x, y, w, h, fill="tint", radius=r, line="line", line_w=lw, shadow="hard")
        return R(x, y, w, h, fill="surface", radius=r, line="line", line_w=lw, shadow="hard")
    sh = {"shadow": True, "whisper": "soft"}.get(d, False)
    line = None if d in ("flat", "whisper") else "line"
    if kind == "primary":
        return R(x, y, w, h, fill="primary", radius=r, shadow=sh)
    if kind == "tint":
        return R(x, y, w, h, fill="tint", alpha=0.95, radius=r, line=line)
    return R(x, y, w, h, fill="surface", alpha=S.shape.get("card_alpha", 0.86), radius=r, line=line, shadow=sh)


def title_block(ctx, s, w=CW, x=MX, y=TITLE_Y):
    """Slide title + optional short mark. Returns (elements, bottom_y)."""
    els = []
    title = s.get("title", "")
    if s.get("kicker"):
        # small chapter tag above the title, e.g. "01 · 概览" (keep the source deck's little labels here)
        kw = min(w, text_width_pt(s["kicker"], 12, True) / 72 + len(s["kicker"]) * 0.03 + 0.2)
        k = T(s["kicker"], x, y - 0.3, kw, 0.28, 12, "label", True, "body", valign="m", spc=1.5)
        k["grp"] = "kicker"
        els.append(k)
    if not title:
        return els, y
    bar = ctx.S.decor.get("title_mark") == "bar"
    if bar:
        # a brand's title bar: a short vertical stripe in the accent colour left of the title
        els.append(R(x, y + 0.14, 0.09, 0.52, fill=ctx.S.decor.get("title_bar_color", "accent"), radius=0.03))
        x, w = x + 0.27, w - 0.27
    size = fit_size(title, w, 0.8, 36, 24, bold=True, max_lines=1)
    t = T(title, x, y, w, 0.8, size, "text", True, "heading", valign="m")
    t["dgrp"] = "title"  # unified across the deck in build_deck
    els.append(t)
    bottom = y + 0.8
    if ctx.S.decor.get("title_mark", True) and not bar:
        els.append(R(x, bottom + 0.06, 0.62, 0.08, fill="primary", radius=0.04))
        els.append(R(x + 0.7, bottom + 0.06, 0.14, 0.08, fill="primary@0.4", radius=0.04))
        bottom += 0.14
    return els, bottom


def hero_or_none(ctx, x, y, w, h, key="hero"):
    p = ctx.asset(key)
    return [IMG(p, x, y, w, h)] if p else []


def corner_hero(ctx, w=3.2, h=1.9):
    """Small illustration in the top-right corner, next to the title. A brand's mascot is a
    full figure, not a cut-off decoration: it stays above the content (no feet on the cards)."""
    y = 0.55
    b = getattr(ctx.S, "brand", None)
    if b:
        if (b.get("logo") or {}).get("content") == "header":
            y = 0.75  # below the running header's hairline
        h = min(h, CONTENT_Y - y - 0.12)
    return hero_or_none(ctx, CANVAS_W - MX - w + 0.2, y, w, h)


def brush_behind(ctx, x, y, w, h):
    p = ctx.assets.get("decor_brush")
    if p and ctx.S.decor.get("brush", True):
        e = IMG(p, x, y, w, h, fit="stretch")
        e["role"] = "decor"
        return [e]
    return []


def balanced_break(text, size, bold=True, latin_scale=1.0):
    """Split a title into two lines of similar width, never inside a latin word;
    a break right after punctuation or a space is preferred."""
    import re as _re
    if "\n" in text:
        return text
    best, best_score = None, None
    # never break inside a **marked** span: the marks must stay on one line to pair up
    locked = set()
    for mm in _re.finditer(r"\*\*.+?\*\*", text):
        locked.update(range(mm.start() + 1, mm.end()))
    for i in range(2, len(text) - 1):
        if i in locked:
            continue
        a, b = text[:i], text[i:]
        if b.lstrip("*")[:1] in "，。、；：！？）」』,.;:!?)":
            continue  # a line never starts with closing punctuation
        if _re.match(r"[A-Za-z0-9]", a[-1]) and _re.match(r"[A-Za-z0-9]", b[0]):
            continue
        wa = text_width_pt(a.rstrip(), size, bold, latin_scale)
        wb = text_width_pt(b.lstrip(), size, bold, latin_scale)
        bonus = 0
        if a[-1] in "，,、：:；; " or b[0] == " ":
            bonus = size * 3.0          # punctuation or a space: the natural place
        elif a[-1] in "的了和与及或是在把被让给":
            bonus = size * 1.2          # after a particle
        elif a[-1] in "个条种步招天年次位款件":
            bonus = size * 0.9          # after a measure word
        score = abs(wa - wb) - bonus
        if best_score is None or score < best_score:
            best, best_score = i, score
    return text if best is None else text[:best].rstrip() + "\n" + text[best:].lstrip()


def ink_on(ctx, fill):
    """Most readable text colour on a given fill: dark ink or white."""
    from common import contrast
    bg = ctx.S.c(fill)
    return max(("1A1A1A", "FFFFFF", ctx.S.c("text")), key=lambda c: contrast(c, bg))


def body_size(text, w, h, mx=18, mn=12, bold=False):
    from common import PROJECTION
    if PROJECTION["on"]:
        mn, mx = max(mn, 18), max(mx, 22)
    return fit_size(text, w, h, mx, mn, bold=bold)


# ------------------------------------------------------------------ layouts
def cover_hero(s, ctx):
    els = []
    hero = ctx.asset("hero")
    left_w = 6.1 if hero else CW
    x = MX + 0.1
    items_ = s.get("items", [])
    block = (0.7 if s.get("kicker") else 0) + 1.55 + (0.9 if s.get("subtitle") else 0) + (0.7 if s.get("body") else 0)
    bottom_lim = (5.1 if items_ else (6.1 if s.get("takeaway") else 6.6))
    y = max(1.1, 0.9 + (bottom_lim - 0.9 - block) / 2) if not items_ else 1.1
    if s.get("kicker"):
        k = s["kicker"]
        kw = min(left_w, 0.6 + len(k) * 0.2)
        els.append(R(x, y, kw, 0.46, fill="tint", alpha=0.9, radius=0.23))
        els.append(T(k, x, y, kw, 0.46, 14, "strong" if ctx.S.dark else "highlight", True, "body", align="c", valign="m", spc=2))
        y += 0.7
    t = s.get("title", "")
    if hero and len(t) > 8:
        left_w = 6.7  # long title: give it room, the illustration shrinks a little
    tsize = fit_size(t, left_w, 1.45, 88, 42, bold=True, max_lines=1, latin_scale=DISPLAY_LATIN)
    if n_lines(t, tsize, left_w, True, DISPLAY_LATIN) > 1:
        # long title: two lines, smaller
        tb2 = balanced_break(t, 60, True, DISPLAY_LATIN)
        tsize = fit_size(tb2, left_w, 2.3, 60, 30, bold=True, max_lines=2, line_spacing=1.1, latin_scale=DISPLAY_LATIN)
        els.append(T(tb2, x, y, left_w, 2.3, tsize, "strong", True, "display", valign="m", ls=1.1))
        y += 2.4
    else:
        els.append(T(t, x, y, left_w, 1.45, tsize, "strong", True, "display", valign="m"))
        y += 1.55
    if s.get("subtitle"):
        st = s["subtitle"]
        ssize = fit_size(st, left_w - 0.3, 0.7, 30, 18, bold=True, max_lines=1)
        from common import text_width_pt
        sw = min(left_w, text_width_pt(st, ssize, True) / 72 + 0.5)
        els += brush_behind(ctx, x - 0.12, y + 0.02, sw + 0.1, 0.72)
        els.append(T(st, x + 0.12, y, sw, 0.72, ssize, "text", True, "heading", valign="m"))
        y += 0.9
    if s.get("body"):
        bsize = body_size(s["body"], left_w, 0.5, 17, 12)
        els.append(T(s["body"], x, y, left_w, 0.5, bsize, "muted", False, "body", valign="m"))
        y += 0.7
    items = s.get("items", [])
    hero_h = 5.4
    if items:
        # agenda chips run across the full width above the takeaway pill
        n = len(items)
        gap = 0.25
        ch = 0.82
        iy = 5.28 if s.get("takeaway") else 5.6
        hero_h = iy - 0.95
        if n <= 4:
            cw = (CW - gap * (n - 1)) / n
            for i, it in enumerate(items):
                cx = MX + i * (cw + gap)
                els.append(card(ctx, cx, iy, cw, ch))
                els.append(item_mark(ctx, s.get("items", []), i, "sparkles", cx + 0.16, iy + (ch - 0.5) / 2, 0.5))
                txt = it.get("text") or it.get("title", "")
                fs = fit_size(txt, cw - 0.95, ch - 0.12, 18, 11, bold=True)
                els.append(T(txt, cx + 0.8, iy + 0.06, cw - 0.95, ch - 0.12, fs, "text", True, valign="m"))
        else:
            cols = 2
            cw = (CW - gap) / cols
            for i, it in enumerate(items):
                cx = MX + (i % cols) * (cw + gap)
                cy = iy - 0.5 * ((n - 1) // cols) + 0.5 * (i // cols)
                txt = it.get("text") or it.get("title", "")
                els.append(item_mark(ctx, s.get("items", []), i, "check", cx, cy, 0.36))
                els.append(T(txt, cx + 0.5, cy, cw - 0.5, 0.36, 15, "text", True, valign="m"))
    if hero:
        els.append(IMG(hero, MX + left_w + 0.1, 0.6, CANVAS_W - MX - left_w - 0.5, hero_h))
    return els, {"master": "cover", "header": False}


def statement_number(s, ctx):
    els, tb = title_block(ctx, s)
    hero = ctx.asset("hero")
    right = 7.3 if hero else CANVAS_W - MX
    num = str(s.get("number", ""))
    x = MX + 0.1
    top = CONTENT_Y + 0.2
    lines = s.get("lines", [])
    full_w = right - x
    stacked = False
    if num:
        ns = min(160, int(150 / max(1, len(num) ** 0.5)))
        nw = max(1.6, text_width_pt(num, ns, True, DISPLAY_LATIN) / 72 + 0.3)
        # a wide number ("≤ 0.5 元 / 秒") leaves no room beside it: lines go underneath
        stacked = bool(lines) and full_w - nw - 0.35 < 2.6
        if nw > full_w or stacked:
            ns = fit_size(num, full_w - 0.3, 1.4, ns, 40, bold=True, max_lines=1, latin_scale=DISPLAY_LATIN)
            nw = min(full_w, text_width_pt(num, ns, True, DISPLAY_LATIN) / 72 + 0.3)
        nh = 1.6 if stacked else 2.5
        ny = top - 0.25
        els += brush_behind(ctx, x - 0.2, ny + nh * 0.52, nw + 0.5, nh * 0.46)
        els.append(T(num, x, ny, nw, nh, ns, "highlight", True, "display", align="l" if stacked else "c", valign="m", ls=1.0))
        lx = x if stacked else x + nw + 0.35
    else:
        lx = x
    lw = right - lx
    if lines:
        joined = "\n".join(lines)
        ly, lh = (top + 1.45, 1.2) if stacked else (top + 0.05, 1.9)
        ls_ = fit_size(joined, lw, lh, 42, 18 if stacked else 22, bold=True)
        els.append(T(joined, lx, ly, lw, lh, ls_, "text", True, "heading", valign="m", ls=1.3))
    if s.get("body"):
        by = top + (2.8 if stacked else 2.35)
        bw = right - x
        els.append(T(s["body"], x, by, bw, 0.9, body_size(s["body"], bw, 0.9, 20, 13), "muted", False, valign="t", ls=1.4))
    if hero:
        els.append(IMG(hero, 7.3, 1.0, 5.4, 5.1))
    return els, {"master": "content"}


def rows_side(s, ctx):
    els, tb = title_block(ctx, s)
    side = s.get("side") or {}
    hero = ctx.asset("hero")
    sx, sw = MX, 3.45
    rx = MX + sw + 0.45 if (side or hero) else MX
    rw = CANVAS_W - MX - rx
    sy = CONTENT_Y + 0.05
    if side and side.get("number"):
        # a key figure in the side panel: label, the number on a brush highlight, a caption
        ph = CONTENT_B - sy
        els.append(card(ctx, sx, sy, sw, ph, "tint"))
        cy = sy + 0.35
        if side.get("title"):
            els.append(T(side["title"], sx + 0.25, cy, sw - 0.5, 0.6, body_size(side["title"], sw - 0.5, 0.6, 15, 11),
                         "secondary", align="c", valign="m"))
        num = str(side["number"])
        ns = fit_size(num, sw - 0.8, 1.1, 60, 30, bold=True, max_lines=1, latin_scale=DISPLAY_LATIN)
        ny = sy + ph / 2 - 0.6
        els += brush_behind(ctx, sx + 0.3, ny + 0.05, sw - 0.6, 1.05)
        els.append(T(num, sx + 0.2, ny, sw - 0.4, 1.15, ns, "strong", True, "display", align="c", valign="m"))
        if side.get("body"):
            els.append(T(side["body"], sx + 0.15, sy + ph - 1.0, sw - 0.3, 0.7, body_size(side["body"], sw - 0.3, 0.7, 14, 10),
                         "muted", align="c", valign="m"))
    elif side:
        if side.get("title"):
            fs = fit_size(side["title"], sw, 0.9, 24, 16, bold=True)
            els.append(T(side["title"], sx, sy, sw, 0.9, fs, "highlight", True, "heading", valign="b"))
        if side.get("body"):
            els.append(T(side["body"], sx, sy + 1.0, sw, 1.0, body_size(side["body"], sw, 1.0, 16, 12), "muted", ls=1.45))
    if hero:
        els.append(IMG(hero, sx - 0.15, 4.05 if side else CONTENT_Y, sw + 0.3, 2.05 if side else 3.9))
    items = s.get("items", [])
    n = max(1, len(items))
    gap = 0.2
    ly = CONTENT_Y
    if s.get("list_title"):
        els.append(T(s["list_title"], rx, CONTENT_Y - 0.05, rw, 0.42, 17, "strong", True, "heading", valign="m"))
        ly = CONTENT_Y + 0.5
    rh = min(1.2, (CONTENT_B - ly - gap * (n - 1)) / n)
    total = n * rh + (n - 1) * gap
    y = ly + (CONTENT_B - ly - total) / 2
    for i, it in enumerate(items):
        step(i)
        kind = "tint" if it.get("emphasis") in ("primary", "soft") or (i == 0 and s.get("first_emphasis", True)) else "glass"
        els.append(card(ctx, rx, y, rw, rh, kind))
        els.append(item_mark(ctx, s.get("items", []), i, "sparkles", rx + 0.22, y + (rh - 0.56) / 2, 0.56,
                        bg="surface" if kind == "tint" else "tint"))
        nx = rx + 1.0
        if it.get("title"):
            nw = 2.1
            fs = fit_size(it["title"], nw, rh - 0.2, 22, 13, bold=True)
            els.append(T(it["title"], nx, y + 0.1, nw, rh - 0.2, fs, "strong", True, "heading", valign="m"))
            tx, tw = nx + nw + 0.2, rw - (nx - rx) - nw - 0.4
        else:
            tx, tw = nx, rw - (nx - rx) - 0.3
        if it.get("text"):
            els.append(T(it["text"], tx, y + 0.1, tw, rh - 0.2,
                         body_size(it["text"], tw, rh - 0.2, 17 if it.get("title") else 20, 11), "text", valign="m"))
        y += rh + gap
    step_end()
    return els, {"master": "content"}


def stats_row(s, ctx):
    """Two to four big numbers. Optional per item "note" (a small line under the label), a page
    "body" paragraph under the cards, or a "detail" {title, body} block for a longer explanation."""
    els, tb = title_block(ctx, s, w=CW - (3.3 if ctx.asset("hero") else 0))
    els += corner_hero(ctx)
    items = s.get("items", [])
    n = max(1, len(items))
    gap = 0.35
    below = s.get("body") or s.get("detail")
    has_note = any(isinstance(it, dict) and it.get("note") for it in items)
    y = CONTENT_Y + (0.1 if below else 0.35)
    h = (2.2 if has_note else 2.0) if below else 2.75
    cw = (CW - gap * (n - 1)) / n
    for i, it in enumerate(items):
        step(i)
        x = MX + i * (cw + gap)
        els.append(card(ctx, x, y, cw, h))
        isz = 0.5 if below else 0.62
        els.append(item_mark(ctx, s.get("items", []), i, "bar-chart", x + (cw - isz) / 2, y + 0.2, isz))
        v = str(it.get("value", ""))
        vy = y + isz + 0.3
        vs = fit_size(v, cw - 0.5, 0.85, 52, 24, bold=True, max_lines=1, latin_scale=DISPLAY_LATIN)
        e = T(v, x + 0.15, vy, cw - 0.3, 0.85, vs, "highlight", True, "display", align="c", valign="m")
        e["grp"] = "stat_value"
        els.append(e)
        lab = it.get("label", "")
        e = T(lab, x + 0.15, vy + 0.88, cw - 0.3, 0.38, fit_size(lab, cw - 0.3, 0.38, 16, 11, bold=True, max_lines=1),
              "text" if has_note else "muted", has_note, align="c", valign="t")
        e["grp"] = "stat_label"
        els.append(e)
        if it.get("note"):
            e = T(it["note"], x + 0.15, vy + 1.26, cw - 0.3, 0.3, fit_size(it["note"], cw - 0.3, 0.3, 12, 9, max_lines=1),
                  "muted", align="c", valign="t")
            e["grp"] = "stat_note"
            els.append(e)
    step_end()
    by = y + h + 0.3
    if s.get("body"):
        bh = CONTENT_B - by
        els.append(T(s["body"], MX, by, CW, bh, body_size(s["body"], CW, min(bh, 1.0), 17, 12), "secondary", ls=1.5))
    elif s.get("detail"):
        dt = s["detail"]
        if dt.get("title"):
            els.append(T(dt["title"], MX, by, CW, 0.42, 18, "strong", True, "heading", valign="m"))
            by += 0.5
        bh = CONTENT_B - by
        els.append(card(ctx, MX, by, CW, bh, "tint"))
        els.append(T(dt.get("body", ""), MX + 0.3, by + 0.12, CW - 0.6, bh - 0.24,
                     body_size(dt.get("body", ""), CW - 0.6, bh - 0.24, 17, 11), "text", valign="m", ls=1.45))
    return els, {"master": "content"}


def _diagram(ctx, d, x, y, w, h):
    els = [card(ctx, x, y, w, h)]
    pad = 0.28
    iy = y + pad
    if d.get("title"):
        els.append(ICON(d.get("icon", "cloud"), x + pad, iy, 0.46))
        els.append(T(d["title"], x + pad + 0.58, iy, w - 2 * pad - 0.58, 0.46,
                     fit_size(d["title"], w - 2 * pad - 0.6, 0.46, 18, 11, bold=True, max_lines=1),
                     "highlight", True, "heading", valign="m"))
        iy += 0.7
    boxes = d.get("boxes", [])
    cap_h = 0.4 if d.get("caption") else 0
    n = max(1, len(boxes))
    gap = 0.22
    bh = min(0.95, (y + h - pad - cap_h - iy - gap * (n - 1)) / n)
    for b in boxes:
        prim = b.get("emphasis") == "primary"
        els.append(R(x + pad, iy, w - 2 * pad, bh, fill="primary" if prim else "surface",
                     radius=0.12, line=None if prim else "line", shadow=prim))
        tcol = "on_primary" if prim else "text"
        els.append(T(b["text"], x + pad + 0.22, iy, w - 2 * pad - 0.44, bh,
                     fit_size(b["text"], w - 2 * pad - 0.44, bh - 0.1, 17, 10, bold=prim), tcol, prim, valign="m"))
        iy += bh + gap
    if d.get("caption"):
        els.append(T(d["caption"], x + pad, y + h - pad - cap_h + 0.05, w - 2 * pad, cap_h,
                     fit_size(d["caption"], w - 2 * pad, cap_h, 13, 9), "muted", align="r", valign="m"))
    return els


def media_text(s, ctx):
    els, tb = title_block(ctx, s, w=CW - (3.3 if ctx.asset("hero") else 0))
    els += corner_hero(ctx)
    lx, lw = MX, 4.9
    y, h = CONTENT_Y, CONTENT_B - CONTENT_Y
    if s.get("diagram"):
        els += _diagram(ctx, s["diagram"], lx, y + 0.1, lw, h - 0.2)
    elif s.get("image"):
        els.append(IMG(s["image"], lx, y, lw, h))
    rx = lx + lw + 0.5
    rw = CANVAS_W - MX - rx
    ry = y + 0.25
    if s.get("point"):
        fs = fit_size(s["point"], rw, 0.9, 26, 16, bold=True)
        els.append(T(s["point"], rx, ry, rw, 0.9, fs, "text", True, "heading", valign="m"))
        ry += 1.0
    if s.get("body"):
        els.append(T(s["body"], rx, ry, rw, 0.8, body_size(s["body"], rw, 0.8, 17, 12), "muted", ls=1.45))
        ry += 1.0
    if s.get("callout"):
        ch = 1.3
        els.append(card(ctx, rx, ry, rw, ch, "tint"))
        els.append(ICON(ctx.icon(0, "lightbulb"), rx + 0.25, ry + (ch - 0.52) / 2, 0.52, bg="surface"))
        els.append(T(s["callout"], rx + 0.95, ry + 0.12, rw - 1.2, ch - 0.24,
                     body_size(s["callout"], rw - 1.2, ch - 0.24, 17, 11), "text", valign="m", ls=1.4))
    return els, {"master": "content"}


def side_cards(s, ctx):
    els, tb = title_block(ctx, s)
    side = s.get("side") or {}
    hero = ctx.asset("hero")
    sx, sw = MX, 3.45
    rx = MX + sw + 0.45
    rw = CANVAS_W - MX - rx
    if side:
        if side.get("title"):
            els.append(T(side["title"], sx, CONTENT_Y + 0.05, sw, 0.8,
                         fit_size(side["title"], sw, 0.8, 26, 16, bold=True), "highlight", True, "heading", valign="b"))
        if side.get("body"):
            els.append(T(side["body"], sx, CONTENT_Y + 0.95, sw, 0.9, body_size(side["body"], sw, 0.9, 16, 12), "muted", ls=1.45))
    if hero:
        els.append(IMG(hero, sx - 0.15, 4.0, sw + 0.3, 2.1))
    items = s.get("items", [])
    heights = [1.55 if it.get("emphasis") == "primary" else 1.1 for it in items]
    gap = 0.25
    total = sum(heights) + gap * (len(items) - 1)
    y = CONTENT_Y + max(0, (CONTENT_B - CONTENT_Y - total) / 2)
    for i, (it, hh) in enumerate(zip(items, heights)):
        step(i)
        prim = it.get("emphasis") == "primary"
        els.append(card(ctx, rx, y, rw, hh, "primary" if prim else "glass"))
        els.append(item_mark(ctx, s.get("items", []), i, "check-circle", rx + 0.25, y + (hh - 0.56) / 2, 0.56,
                        color="primary", bg="surface" if prim else "tint"))
        tx, tw = rx + 1.05, rw - 1.3
        tcol = "on_primary" if prim else "text"
        if it.get("title") and it.get("text"):
            els.append(T(it["title"], tx, y + 0.18, tw, 0.55, fit_size(it["title"], tw, 0.55, 22, 14, bold=True, max_lines=1),
                         tcol, True, "heading", valign="m"))
            els.append(T(it["text"], tx, y + 0.75, tw, hh - 0.9, body_size(it["text"], tw, hh - 0.9, 16, 11),
                         "on_primary" if prim else "muted", valign="t"))
        else:
            txt = it.get("text") or it.get("title", "")
            els.append(T(txt, tx, y + 0.12, tw, hh - 0.24, body_size(txt, tw, hh - 0.24, 18, 11, bold=prim), tcol, prim, valign="m"))
        y += hh + gap
    step_end()
    return els, {"master": "content"}


def quote_cards(s, ctx):
    els, tb = title_block(ctx, s, w=CW - (3.3 if ctx.asset("hero") else 0))
    els += corner_hero(ctx)
    y = CONTENT_Y
    if s.get("lead"):
        els.append(ICON(ctx.p.get("lead_icon", "message-circle"), MX, y, 0.42))
        els.append(T(s["lead"], MX + 0.55, y, CW - 3.6, 0.42, body_size(s["lead"], CW - 3.6, 0.42, 18, 12), "text", True, valign="m"))
        y += 0.65
    items = s.get("items", [])
    n = max(1, len(items))
    gap = 0.2
    ch = min(1.0, (CONTENT_B - y - gap * (n - 1)) / n)
    for i, it in enumerate(items):
        step(i)
        txt = it.get("text", "")
        els.append(card(ctx, MX, y, CW, ch))
        els.append(ICON("quote", MX + 0.22, y + (ch - 0.5) / 2, 0.5, bg="tint"))
        els.append(T(txt, MX + 0.95, y + 0.08, CW - 1.2, ch - 0.16, body_size(txt, CW - 1.2, ch - 0.16, 18, 11), "text", valign="m"))
        y += ch + gap
    step_end()
    return els, {"master": "content"}


def statement_hero(s, ctx):
    els, tb = title_block(ctx, s)
    hero = ctx.asset("hero")
    tw = 6.6 if hero else CW
    x = MX + 0.1
    head = s.get("headline", "")
    body = s.get("body", "")
    pill = s.get("pill", "")
    hs = fit_size(head, tw, 0.95, 40, 22, bold=True)
    block_h = 0.95 + (0.25 + 0.9 if body else 0) + (0.3 + 0.6 if pill else 0)
    y = CONTENT_Y + (CONTENT_B - CONTENT_Y - block_h) / 2
    if head:
        from common import text_width_pt
        hw = min(tw, text_width_pt(head, hs, True) / 72 + 0.3)
        els += brush_behind(ctx, x - 0.1, y + 0.42, hw + 0.2, 0.55)
        els.append(T(head, x, y, tw, 0.95, hs, "strong", True, "heading", valign="m"))
        y += 1.2
    if body:
        els.append(T(body, x, y, tw, 0.9, body_size(body, tw, 0.9, 20, 12), "muted", ls=1.45))
        y += 1.2
    if pill:
        from common import text_width_pt
        ps = 16
        pw = min(tw, text_width_pt(pill, ps, True) / 72 + 1.0)
        els.append(R(x, y, pw, 0.6, fill="tint", alpha=0.95, radius=0.3, line="line"))
        els.append(ICON(ctx.icon(0, "check-circle"), x + 0.1, y + 0.1, 0.4, bg="surface"))
        els.append(T(pill, x + 0.58, y, pw - 0.68, 0.6, ps, "strong" if ctx.S.dark else "highlight", True, valign="m"))
    if hero:
        els.append(IMG(hero, 7.6, 1.0, 5.1, 5.1))
    return els, {"master": "content"}


def cards_quote(s, ctx):
    els, tb = title_block(ctx, s)
    hero = ctx.asset("hero")
    items = s.get("items", [])
    lw = 7.0
    n = max(1, len(items))
    gap = 0.3
    ch = min(1.45, (CONTENT_B - CONTENT_Y - gap * (n - 1)) / n)
    total = n * ch + (n - 1) * gap
    y = CONTENT_Y + (CONTENT_B - CONTENT_Y - total) / 2
    for i, it in enumerate(items):
        step(i)
        els.append(card(ctx, MX, y, lw, ch))
        els.append(item_mark(ctx, s.get("items", []), i, "alert-triangle", MX + 0.25, y + (ch - 0.6) / 2, 0.6,
                        color="text" if ctx.S.dark else "primary_dark", bg="accent" if ctx.S.dark else "accent@0.45"))
        tx, tw = MX + 1.1, lw - 1.35
        th = min(0.5, ch * 0.38) if it.get("title") else 0
        bh_ = ch - 0.18 - th
        bs_ = body_size(it["text"], tw, bh_, 15, 11) if it.get("text") else 0
        used = n_lines(it["text"], bs_, tw) * bs_ * 1.2 * LINE_PITCH / 72 + 0.04 if it.get("text") else 0
        top = y + max(0.09, (ch - th - used) / 2)  # title and text sit as one block in the middle of the card
        if it.get("title"):
            els.append(T(it["title"], tx, top, tw, th, fit_size(it["title"], tw, th, 19, 13, bold=True, max_lines=1),
                         "text", True, "heading", valign="m"))
        if it.get("text"):
            ty_ = top + th
            els.append(T(it["text"], tx, ty_, tw, y + ch - 0.08 - ty_, bs_, "muted"))
        y += ch + gap
    step_end()
    qx = MX + lw + 0.5
    qw = CANVAS_W - MX - qx
    ql = s.get("quote_lines", [])
    qy = 3.9 if hero else CONTENT_Y + 1.0
    if hero:
        els.append(IMG(hero, qx, 1.75, qw, 2.1))
    for i, line in enumerate(ql):
        fs = fit_size(line, qw, 0.6, 26, 16, bold=True, max_lines=1)
        els.append(T(line, qx, qy + i * 0.7, qw, 0.6, fs, "highlight" if i == 0 else "text", True, "heading", valign="m"))
    return els, {"master": "content"}


def list_icons(s, ctx):
    """Generic fallback: title + icon rows (bullets, short points)."""
    corner = ctx.asset("hero")
    els, tb = title_block(ctx, s, w=CW - (3.3 if corner else 0))
    els += corner_hero(ctx)
    items = s.get("items", [])
    n = max(1, len(items))
    gap = 0.2
    top = CONTENT_Y + (0.1 if corner else 0)
    rh = min(1.05, (CONTENT_B - top - gap * (n - 1)) / n)
    total = n * rh + (n - 1) * gap
    y = top + max(0, (CONTENT_B - top - total) / 2) * 0.6  # sit a little above centre
    for i, it in enumerate(items):
        step(i)
        txt = it.get("text") or it.get("title", "")
        if it.get("title") and it.get("text"):
            txt = f"**{it['title']}**  {it['text']}"
        els.append(card(ctx, MX, y, CW, rh))
        isz = min(0.56, rh - 0.3)
        els.append(item_mark(ctx, s.get("items", []), i, "check-circle", MX + 0.22, y + (rh - isz) / 2, isz))
        tx = MX + 0.22 + isz + 0.3
        els.append(T(txt, tx, y + 0.06, CANVAS_W - MX - tx - 0.25, rh - 0.12,
                     body_size(txt, CANVAS_W - MX - tx - 0.25, rh - 0.12, 20, 11), "text", valign="m"))
        y += rh + gap
    step_end()
    return els, {"master": "content"}


def grid_cards(s, ctx):
    """2-3 column cards with a big icon; best for 3-6 short points."""
    corner = ctx.asset("hero")
    els, tb = title_block(ctx, s, w=CW - (3.3 if corner else 0))
    els += corner_hero(ctx)
    items = s.get("items", [])
    n = max(1, len(items))
    cols = 2 if n in (2, 4) else 3
    rows = (n + cols - 1) // cols
    gap = 0.3
    cw = (CW - gap * (cols - 1)) / cols
    top = CONTENT_Y + 0.1
    ch = min(1.9, (CONTENT_B - top - gap * (rows - 1)) / rows)
    for i, it in enumerate(items):
        step(i)
        x = MX + (i % cols) * (cw + gap)
        y = top + (i // cols) * (ch + gap)
        prim = it.get("emphasis") == "primary"
        els.append(card(ctx, x, y, cw, ch, "primary" if prim else "glass"))
        isz = min(0.8, ch * 0.45)
        els.append(item_mark(ctx, s.get("items", []), i, "check-circle", x + 0.3, y + (ch - isz) / 2, isz, bg="surface" if prim else "tint"))
        tx, tw = x + 0.3 + isz + 0.3, cw - isz - 0.9
        tcol = "on_primary" if prim else "text"
        if it.get("title") and it.get("text"):
            els.append(T(it["title"], tx, y + 0.2, tw, 0.55, fit_size(it["title"], tw, 0.55, 22, 13, bold=True, max_lines=1),
                         tcol, True, "heading", valign="m"))
            els.append(T(it["text"], tx, y + 0.8, tw, ch - 1.0, body_size(it["text"], tw, ch - 1.0, 17, 11),
                         tcol if prim else "muted"))
        else:
            txt = it.get("text") or it.get("title", "")
            els.append(T(txt, tx, y + 0.15, tw, ch - 0.3, body_size(txt, tw, ch - 0.3, 24, 12, bold=True), tcol, True,
                         "heading", valign="m"))
    step_end()
    return els, {"master": "content"}


def steps_flow(s, ctx):
    """2-5 steps left to right: numbered badges on a line, a card under each."""
    items = s.get("items", [])
    if len(items) > 5:
        return list_icons(s, ctx)
    corner = ctx.asset("hero")
    els, tb = title_block(ctx, s, w=CW - (3.3 if corner else 0))
    els += corner_hero(ctx)
    n = max(1, len(items))
    gap = 0.35
    cw = (CW - gap * (n - 1)) / n
    by = CONTENT_Y + 0.25 if not corner else CONTENT_Y + 0.35
    bs = 0.72
    # the line behind the badges
    if n > 1:
        x0 = MX + cw / 2
        x1 = MX + (n - 1) * (cw + gap) + cw / 2
        els.append(R(x0, by + bs / 2 - 0.025, x1 - x0, 0.05, fill="primary@0.35"))
    cy = by + bs + 0.3
    ch = CONTENT_B - cy
    # the badge above already numbers each step; when any card needs the room of its small
    # icon (projection sizes, long steps) the icons go from every card, so the row stays even
    tw0 = cw - 0.5
    def _need(it):
        nd = 0.5 if it.get("title") else 0
        if it.get("text"):
            b_ = body_size(it["text"], tw0, 2.0, 18, 11)
            nd += n_lines(it["text"], b_, tw0) * b_ * 1.35 * 1.2 / 72 + 0.3
        return nd
    no_icons = any(_need(it) > ch - 0.9 for it in items)
    for i, it in enumerate(items):
        step(i)
        x = MX + i * (cw + gap)
        els.append(E(x + cw / 2 - bs / 2, by, bs, bs, "primary"))
        els.append(T(f"{i + 1:02d}", x + cw / 2 - bs / 2, by, bs, bs, 20, "on_primary", True, "display",
                     align="c", valign="m"))
        els.append(card(ctx, x, cy, cw, ch))
        tx, tw = x + 0.25, cw - 0.5
        title = it.get("title") or ""
        text = it.get("text") or ""
        # the badge above already numbers the step; the small icon in the card is the first
        # thing to go when the words need its room (projection sizes, long steps)
        ty = cy + 0.9
        if no_icons:
            ty = cy + 0.25
        else:
            els.append(item_mark(ctx, s.get("items", []), i, "check-circle", x + 0.25, cy + 0.25, 0.5))
        if title:
            ts = fit_size(title, tw, 0.8, 21, 13, bold=True)
            th = min(0.8, n_lines(title, ts, tw, True) * ts * 1.2 * 1.2 / 72 + 0.04)
            els.append(T(title, tx, ty, tw, th, ts, "strong", True, "heading", valign="t"))
            els[-1]["grp"] = "steps_title"
            ty += th + 0.1
        if text:
            els.append(T(text, tx, ty, tw, cy + ch - ty - 0.2, body_size(text, tw, cy + ch - ty - 0.2, 18, 11),
                         "muted", ls=1.35))
            els[-1]["grp"] = "steps_text"
    step_end()
    return els, {"master": "content"}


def compare_split(s, ctx):
    """Two columns side by side (before/after, A vs B). The right side is the recommended one."""
    els, tb = title_block(ctx, s)
    left, right = s.get("left") or {}, s.get("right") or {}
    gap = 0.9
    cw = (CW - gap) / 2
    y, h = CONTENT_Y + 0.05, CONTENT_B - CONTENT_Y - 0.05
    m_max = max(len(left.get("items", [])), len(right.get("items", [])), 1)
    need = 1.0 + m_max * 0.8 + 0.35
    if need < h:  # few items: shorter cards, centred
        y, h = y + (h - need) / 2, need
    for side, x, prim in ((left, MX, False), (right, MX + cw + gap, True)):
        step()
        els.append(card(ctx, x, y, cw, h))
        els.append(R(x, y, cw, 0.8, fill="primary" if prim else "tint", radius=ctx.S.shape.get("radius", 0.16)))
        if side.get("title"):
            els.append(T(side["title"], x + 0.3, y, cw - 0.6, 0.8,
                         fit_size(side["title"], cw - 0.6, 0.7, 22, 13, bold=True, max_lines=1),
                         "on_primary" if prim else "strong", True, "heading", valign="m"))
        raw = side.get("items", [])
        its = [i if isinstance(i, str) else (i.get("text") or i.get("title", "")) for i in raw]
        m = max(1, len(its))
        rh = min(0.8 if not any(isinstance(i, dict) and i.get("num") for i in raw) else 1.0, (h - 1.1) / m)
        iy = y + 1.0
        icon = side.get("icon") or ("check-circle" if prim else "x-circle")
        for j, t in enumerate(its):
            it = raw[j] if isinstance(raw[j], dict) else {}
            if it.get("num"):
                els.append(T(str(it["num"]), x + 0.25, iy, 0.6, rh, 20, "highlight", True, "display", valign="m", ls=1.0))
            elif side.get("bullet") == "dash":
                els.append(R(x + 0.35, iy + rh / 2 - 0.03, 0.26, 0.06, fill="primary", radius=0.03))
            else:
                els.append(ICON(icon, x + 0.3, iy + (rh - 0.42) / 2, 0.42,
                                color="primary" if prim else "muted", bg="tint" if prim else "surface"))
            e = T(t, x + 0.9, iy, cw - 1.2, rh, body_size(t, cw - 1.2, rh - 0.05, 18, 11), "text", valign="m")
            e["grp"] = "cmp_text"
            els.append(e)
            iy += rh
    step_end()
    if s.get("vs_label", "VS"):  # "" = two parallel columns, no versus badge
        vs = 0.72
        els.append(E(MX + cw + gap / 2 - vs / 2, y + h / 2 - vs / 2, vs, vs, "accent"))
        els.append(T(s.get("vs_label", "VS"), MX + cw + gap / 2 - vs / 2, y + h / 2 - vs / 2, vs, vs, 16,
                     ink_on(ctx, "accent"), True, "display", align="c", valign="m"))
    return els, {"master": "content"}


def cycle(s, ctx):
    """3-6 stages that loop: numbered nodes on a ring, explanations listed on the right."""
    els, tb = title_block(ctx, s)
    items = s.get("items", [])
    n = max(3, len(items))
    import math
    cx, cy, r = MX + 2.55, (CONTENT_Y + CONTENT_B) / 2 + 0.05, 1.5
    els.append(E(cx - r, cy - r, 2 * r, 2 * r, None, line="primary@0.45"))
    cr = 0.95
    els.append(E(cx - cr, cy - cr, 2 * cr, 2 * cr, "tint"))
    if s.get("center"):
        els.append(T(s["center"], cx - cr + 0.12, cy - cr + 0.12, 2 * cr - 0.24, 2 * cr - 0.24,
                     fit_size(s["center"], 2 * cr - 0.3, 2 * cr - 0.4, 22, 11, bold=True), "strong", True,
                     "heading", align="c", valign="m"))
    ns = 0.7
    for i in range(len(items)):
        step(i)
        a = -math.pi / 2 + 2 * math.pi * i / n
        nx, ny = cx + r * math.cos(a), cy + r * math.sin(a)
        els.append(E(nx - ns / 2, ny - ns / 2, ns, ns, "primary"))
        els.append(T(f"{i + 1:02d}", nx - ns / 2, ny - ns / 2, ns, ns, 17, "on_primary", True, "display",
                     align="c", valign="m"))
    step_end()
    lx = cx + r + 0.9
    lw = CANVAS_W - MX - lx
    gap = 0.16
    rh = min(1.0, (CONTENT_B - CONTENT_Y - gap * (len(items) - 1)) / max(1, len(items)))
    total = len(items) * rh + (len(items) - 1) * gap
    y = CONTENT_Y + (CONTENT_B - CONTENT_Y - total) / 2
    for i, it in enumerate(items):
        step(i)
        els.append(card(ctx, lx, y, lw, rh))
        els.append(T(f"{i + 1:02d}", lx + 0.2, y, 0.6, rh, 18, "highlight", True, "display", valign="m"))
        tx, tw = lx + 0.85, lw - 1.05
        txt = f"**{it['title']}**  {it.get('text', '')}" if it.get("title") else it.get("text", "")
        els.append(T(txt.strip(), tx, y + 0.05, tw, rh - 0.1, body_size(txt, tw, rh - 0.1, 17, 11), "text", valign="m"))
        els[-1]["grp"] = "cycle_text"
        y += rh + gap
    step_end()
    return els, {"master": "content"}


def pyramid(s, ctx):
    """3-5 layers, top = narrowest; each layer's explanation on the right."""
    els, tb = title_block(ctx, s)
    items = s.get("items", [])
    n = max(1, len(items))
    gap = 0.12
    rh = min(0.9, (CONTENT_B - CONTENT_Y - gap * (n - 1)) / n)
    total = n * rh + (n - 1) * gap
    y = CONTENT_Y + (CONTENT_B - CONTENT_Y - total) / 2
    axis = MX + 2.7
    wmin, wmax = 2.0, 5.3
    for i, it in enumerate(items):
        step(i)
        w = wmin + (wmax - wmin) * (i / max(1, n - 1))
        # top layer solid, the rest light tints (mid-tones fail contrast with both white and dark text)
        strength = 1.0 if i == 0 else max(0.18, 0.5 - 0.32 * (i - 1) / max(1, n - 2))
        fill = "primary" if i == 0 else f"primary@{strength:.2f}"
        from common import contrast
        dark_fill = contrast(ctx.S.c("on_primary"), ctx.S.c(fill)) >= 3.2
        els.append(R(axis - w / 2, y, w, rh, fill=fill, radius=0.1))
        title = it.get("title") or it.get("text", "")
        els.append(T(title, axis - w / 2 + 0.15, y, w - 0.3, rh, fit_size(title, w - 0.3, rh - 0.1, 20, 11, bold=True, max_lines=1),
                     "on_primary" if dark_fill else "strong", True, "heading", align="c", valign="m"))
        if it.get("title") and it.get("text"):
            tx = axis + wmax / 2 + 0.45
            els.append(R(axis + w / 2 + 0.08, y + rh / 2 - 0.015, tx - (axis + w / 2) - 0.16, 0.03, fill="line"))
            els.append(T(it["text"], tx, y, CANVAS_W - MX - tx, rh,
                         body_size(it["text"], CANVAS_W - MX - tx, rh - 0.05, 17, 11), "text", valign="m"))
        y += rh + gap
    step_end()
    return els, {"master": "content"}


def _meta_strip(ctx, left, right="", y=0.42):
    """Magazine-style metadata strip: small tracked label left, date/issue right, hairline below."""
    els = []
    if left:
        els.append(T(left, MX, y, 7.5, 0.3, 12, "label", True, "body", valign="m", spc=2))
    if right:
        els.append(T(right, CANVAS_W - MX - 4.5, y, 4.5, 0.3, 12, "subtle", True, "body", align="r", valign="m", spc=1))
    els.append(LN(MX, y + 0.42, CANVAS_W - MX, y + 0.42, "line", 0.75))
    return els


def cover_type(s, ctx):
    """Typography cover: the title is the picture. Metadata strip on top, a huge title
    (one to three lines, a **word** in the highlight colour), subtitle, and a footer row."""
    els = _meta_strip(ctx, s.get("kicker") or ctx.meta.get("series", ""), ctx.meta.get("date") or ctx.meta.get("issue", ""))
    t = s.get("title", "")
    w = CW * 0.9
    size = fit_size(t, w, 1.7, 120, 60, bold=True, max_lines=1, latin_scale=DISPLAY_LATIN)
    if n_lines(t, size, w, True, DISPLAY_LATIN) > 1:
        t = balanced_break(t, 96, True, DISPLAY_LATIN)
        size = fit_size(t, w, 3.3, 104, 48, bold=True, max_lines=2, line_spacing=1.1, latin_scale=DISPLAY_LATIN)
    lines = n_lines(t, size, w, True, DISPLAY_LATIN)
    th = lines * size * 1.1 * 1.2 / 72 + 0.1
    bottom = 4.75
    els.append(T(t, MX, bottom - th, w, th, size, "strong", True, "display", valign="b", ls=1.1))
    y = bottom + 0.2
    if s.get("subtitle"):
        st_ = s["subtitle"]
        els.append(T(st_, MX, y, w, 0.6, fit_size(st_, w, 0.6, 28, 18, max_lines=1), "secondary", False, "heading", valign="t"))
        y += 0.75
    # the footer row may sit on a solid colour band (background decor "band")
    on_band = "band" in (ctx.S.background or {}).get("cover_decor", [])
    band_tok = (ctx.S.background or {}).get("band_color", "primary")
    if on_band:
        from common import contrast
        bc = ctx.S.c(band_tok)
        ink = max(("on_primary", "text", "bg_top"), key=lambda k: contrast(ctx.S.c(k), bc))
    else:
        ink = "muted"
    if not on_band:
        els.append(LN(MX, 6.2, CANVAS_W - MX, 6.2, "line", 0.75))
    if s.get("body"):
        els.append(T(s["body"], MX, 6.3, CW * 0.55, 0.4, body_size(s["body"], CW * 0.55, 0.4, 15, 11), ink, valign="m"))
    items = s.get("items", [])
    if items:
        n = len(items)
        iw = min(2.6, CW * 0.45 / n)
        for i, it in enumerate(items):
            x = CANVAS_W - MX - (n - i) * iw
            txt = f"{i + 1:02d}  " + (it.get("text") or it.get("title", ""))
            els.append(T(txt, x, 6.3, iw - 0.1, 0.4, fit_size(txt, iw - 0.1, 0.4, 13, 10, max_lines=1), ink, True, valign="m"))
    return els, {"master": "cover", "header": False}


def question(s, ctx):
    """One big question on an otherwise quiet page; an optional hint underneath."""
    els = []
    q = s.get("question") or s.get("title", "")
    k = s.get("kicker")
    w = CW * 0.82
    # headings may use a serif latin face (Georgia) that runs wider than the measuring font
    ls_ = 1.25 if "georgia" in ctx.S.fonts.get("heading_latin", "").lower() else 1.05
    size = fit_size(q, w, 3.0, 80, 36, bold=True, max_lines=3, line_spacing=1.15, latin_scale=ls_)
    if n_lines(q, size, w, True, ls_) == 2:
        q = balanced_break(q, size, True, ls_)
        size = fit_size(q, w, 3.0, size, 36, bold=True, max_lines=2, line_spacing=1.15, latin_scale=ls_)
    lines = n_lines(q, size, w, True, ls_)
    th = lines * size * 1.15 * 1.2 / 72 + 0.1
    top = 3.6 - th / 2 - (0.3 if s.get("body") else 0)
    if k:
        els.append(R(MX, top - 0.52, 0.36, 0.06, fill="primary"))
        els.append(T(k, MX + 0.5, top - 0.68, 6, 0.38, 14, "highlight", True, valign="m", spc=2))
    els.append(T(q, MX, top, w, th, size, "strong", True, "heading", valign="t", ls=1.15))
    if s.get("body"):
        els.append(T(s["body"], MX, top + th + 0.3, w * 0.8, 0.8, body_size(s["body"], w * 0.8, 0.8, 20, 14), "muted", ls=1.35))
    return els, {"master": "content", "header": False}


def big_quote(s, ctx):
    """A pull quote as the whole page: huge quote mark, the quote, who said it."""
    els = []
    qt = s.get("quote", "")
    x = MX + 0.9
    w = CW - 1.8
    size = fit_size(qt, w, 2.8, 44, 24, bold=False, max_lines=4, line_spacing=1.3)
    lines = n_lines(qt, size, w)
    th = lines * size * 1.3 * 1.2 / 72 + 0.1
    top = 3.55 - th / 2
    m = T("\u201c", MX - 0.05, top - 1.05, 1.6, 1.6, 150, ctx.S.decor.get("quote_mark_color", "primary@0.35"),
          True, "display", valign="t", ls=1.0)
    m["role"] = "decor"
    els.append(m)
    els.append(T(qt, x, top, w, th, size, "strong", False, "heading", valign="t", ls=1.3))
    y = top + th + 0.35
    if s.get("by"):
        els.append(R(x, y + 0.17, 0.36, 0.05, fill="primary"))
        els.append(T(s["by"], x + 0.5, y, w - 0.5, 0.4, 16, "muted", True, valign="m"))
        y += 0.5
    if s.get("note"):
        els.append(T(s["note"], x + 0.5, y, w - 0.5, 0.5, body_size(s["note"], w - 0.5, 0.5, 14, 11), "subtle"))
    return els, {"master": "content", "header": False}


def cover_center(s, ctx):
    """Centred cover for styles with a landscape along the bottom (background decor "scene"):
    small kicker, big title, subtitle on a brush highlight, one line of body, the takeaway line."""
    els = []
    w = CW * 0.9
    x = (CANVAS_W - w) / 2
    y = 0.75
    if s.get("kicker"):
        els.append(T(s["kicker"], x, y, w, 0.4, 14, "strong", True, "body", align="c", valign="m", spc=3))
        y += 0.55
    t = s.get("title", "")
    ts = fit_size(t, w, 1.2, 66, 36, bold=True, max_lines=1, latin_scale=DISPLAY_LATIN)
    els.append(T(t, x, y, w, 1.2, ts, "strong", True, "display", align="c", valign="m"))
    y += 1.3
    if s.get("subtitle"):
        st_ = s["subtitle"]
        ss = fit_size(st_, w * 0.6, 0.62, 30, 18, bold=True, max_lines=1)
        sw_ = min(w, text_width_pt(st_, ss, True) / 72 + 1.2)
        sx = (CANVAS_W - sw_) / 2
        els += brush_behind(ctx, sx, y, sw_, 0.72)
        els.append(T(st_, sx, y, sw_, 0.72, ss, "strong", True, "heading", align="c", valign="m"))
        y += 0.9
    if s.get("body"):
        els.append(T(s["body"], x, y, w, 0.4, body_size(s["body"], w, 0.4, 16, 11), "secondary", align="c", valign="m"))
        y += 0.5
    if s.get("takeaway"):
        els.append(T(s["takeaway"], x, y, w, 0.4, body_size(s["takeaway"], w, 0.4, 16, 11), "muted", True, align="c",
                     valign="m", spc=1))
    return els, {"master": "cover", "header": False, "uses_takeaway": True}


def rank_grid(s, ctx):
    """A ranked list of up to 10 short entries (num, title, text) in two rows, with an optional
    "findings" box {title, items:[...]} underneath. Good for TOP-N lists."""
    els, tb = title_block(ctx, s)
    items = s.get("items", [])
    n = max(1, len(items))
    cols = 5 if n > 6 else max(1, min(n, 3))
    rows = (n + cols - 1) // cols
    gap = 0.18
    cw = (CW - gap * (cols - 1)) / cols
    fd = s.get("findings")
    fh_box = 1.25 if fd else 0
    area_b = CONTENT_B - (fh_box + 0.2 if fd else 0)
    chh = min(1.35, (area_b - CONTENT_Y - gap * (rows - 1)) / rows)
    k = chh / 1.13  # inner offsets scale with the card height
    for i, it in enumerate(items):
        step(i)
        x = MX + (i % cols) * (cw + gap)
        y = CONTENT_Y + (i // cols) * (chh + gap)
        prim = i < 3 and s.get("top3", False)
        els.append(card(ctx, x, y, cw, chh, "tint" if prim else "glass"))
        num = str(it.get("num") or f"{i + 1:02d}")
        els.append(R(x + 0.18, y + 0.12 * k, 0.5, 0.28, fill="tint" if not prim else "surface", radius=0.14))
        e = T(num, x + 0.18, y + 0.12 * k, 0.5, 0.28, 12, "highlight", True, "display", align="c", valign="m", ls=1.0)
        e["grp"] = "rank_num"
        els.append(e)
        ti = it.get("title", "")
        e = T(ti, x + 0.18, y + 0.40 * k, cw - 0.3, 0.38, fit_size(ti, cw - 0.3, 0.38, 18, 12, bold=True, max_lines=1),
              "strong", True, "heading", valign="m")
        e["grp"] = "rank_title"
        els.append(e)
        if it.get("text"):
            e = T(it["text"], x + 0.18, y + 0.40 * k + 0.37, cw - 0.3, 0.26,
                  fit_size(it["text"], cw - 0.3, 0.26, 12, 9, max_lines=1), "muted", valign="t")
            e["grp"] = "rank_text"
            els.append(e)
    step_end()
    if fd:
        fy = CONTENT_Y + rows * chh + (rows - 1) * gap + 0.25
        fbh = min(fh_box, CONTENT_B - fy)
        els.append(card(ctx, MX, fy, CW, fbh, "tint"))
        lx = MX + 0.35
        if fd.get("title"):
            els.append(T(fd["title"], lx, fy, 1.7, fbh, 20, "strong", True, "heading", valign="m"))
            lx += 1.9
        fi = fd.get("items", [])
        fcols = 2 if len(fi) > 2 else 1
        frows = (len(fi) + fcols - 1) // fcols
        fw = (MX + CW - 0.3 - lx) / fcols
        fh = (fbh - 0.3) / max(1, frows)
        for j, t in enumerate(fi):
            fx = lx + (j % fcols) * fw
            fy2 = fy + 0.15 + (j // fcols) * fh
            els.append(R(fx, fy2 + fh / 2 - 0.03, 0.18, 0.06, fill="primary", radius=0.03))
            e = T(t, fx + 0.3, fy2, fw - 0.4, fh, fit_size(t, fw - 0.4, fh, 16, 11, max_lines=1), "text", valign="m")
            e["grp"] = "rank_find"
            els.append(e)
    return els, {"master": "content"}


def num_mark(ctx, num, x, y, s, big=False):
    """Chapter number drawn in the style's number_style, shared by toc and section pages
    so the two always match. s = box height in inches. Returns (elements, width)."""
    st = ctx.S.decor.get("number_style", "plain")
    num = str(num)
    if st == "plain":
        return num_mark_plain(ctx, num, x, y, s)
    size = round(s * 72 * (0.36 if len(num) > 1 else 0.44))
    if st in ("badge", "ring", "block", "diamond"):
        if st == "badge":
            shape = E(x, y, s, s, "primary")
        elif st == "ring":
            shape = E(x, y, s, s, None, line="highlight", line_w=2.0 if big else 1.25)
        elif st == "block":
            shape = R(x, y, s, s, fill="primary", radius=min(s * 0.18, ctx.S.shape.get("radius", 0.16)) or None)
        else:
            shape = R(x, y, s, s, fill=None, line="highlight", line_w=2.0 if big else 1.25)
            shape["shape"] = "diamond"
        ink = _ink(ctx, "primary") if st in ("badge", "block") else "highlight"
        return [shape, T(num, x, y, s, s, size, ink, True, "display", align="c", valign="m", ls=1.0)], s
    return num_mark_plain(ctx, num, x, y, s)


def num_mark_plain(ctx, num, x, y, s):
    size = round(s * 72 * 0.82)
    w = text_width_pt(num, size, True, DISPLAY_LATIN) / 72 + 0.1
    return [T(num, x, y, w, s, size, "highlight", True, "display", valign="m", ls=1.0)], w


def _toc_items(s, ctx):
    items = s.get("items") or ctx.meta.get("_sections") or []
    out = []
    for i, it in enumerate(items):
        if isinstance(it, str):
            it = {"title": it}
        out.append({"num": it.get("number") or f"{i + 1:02d}", "title": it.get("title", ""), "text": it.get("text", "")})
    return out


def toc(s, ctx):
    """Contents page: big label on the left, numbered chapters stacked on the right.
    With no items it lists the deck's section slides."""
    items = _toc_items(s, ctx)
    n = max(1, len(items))
    els = []
    head = s.get("title") or "目录"
    kick = s.get("kicker") or "CONTENTS"
    lw = 4.1
    hs = fit_size(head, lw, 1.2, 60, 36, bold=True, max_lines=1)
    els.append(T(head, MX, 2.55, lw, 1.2, hs, "strong", True, "heading", valign="b", ls=1.0))
    els.append(T(kick, MX, 3.8, lw, 0.45, 16, "highlight", True, "display", valign="t", spc=4))
    els.append(R(MX, 4.4, 0.62, 0.08, fill="primary", radius=0.04))
    x0 = MX + 4.9
    w0 = CANVAS_W - MX - x0
    row = min(1.2, 5.2 / n)
    top = 3.85 - row * n / 2
    ms = min(0.76, row * 0.66)
    has_text = any(it["text"] for it in items)
    for i, it in enumerate(items):
        step(i)
        y = top + i * row
        mk, mw = num_mark(ctx, it["num"], x0, y + (row - ms) / 2, ms)
        els += mk
        tx = x0 + max(mw, ms) + 0.32
        tw = CANVAS_W - MX - tx
        if has_text and it["text"]:
            th = row * 0.5
            e = T(it["title"], tx, y + row * 0.5 - th, tw, th, fit_size(it["title"], tw, th, 28, 16, bold=True, max_lines=1),
                  "text", True, "heading", valign="b")
            e["grp"] = "toc_title"
            els.append(e)
            e = T(it["text"], tx, y + row * 0.52, tw, row * 0.4, body_size(it["text"], tw, row * 0.4, 16, 11), "muted", valign="t")
            e["grp"] = "toc_text"
            els.append(e)
        else:
            e = T(it["title"], tx, y, tw, row, fit_size(it["title"], tw, row * 0.8, 30, 16, bold=True, max_lines=1),
                  "text", True, "heading", valign="m")
            e["grp"] = "toc_title"
            els.append(e)
        if i < n - 1:
            els.append(LN(x0, y + row, x0 + w0, y + row, "line", 0.75))
    step_end()
    return els, {"master": "content", "header": False}


def toc_row(s, ctx):
    """Contents page as one row of columns (3 to 5 chapters): number, title, short line."""
    items = _toc_items(s, ctx)
    n = max(1, len(items))
    els = []
    head = s.get("title") or "目录"
    kick = s.get("kicker") or "CONTENTS"
    hs = fit_size(head, CW * 0.6, 0.9, 44, 30, bold=True, max_lines=1)
    els.append(T(head, MX, 1.05, CW * 0.6, 0.9, hs, "strong", True, "heading", valign="b", ls=1.0))
    els.append(T(kick, MX, 1.98, CW * 0.6, 0.4, 14, "highlight", True, "display", spc=4))
    gap = 0.35
    cw = (CW - gap * (n - 1)) / n
    y = 3.05
    ms = 0.9
    for i, it in enumerate(items):
        step(i)
        x = MX + i * (cw + gap)
        mk, mw = num_mark(ctx, it["num"], x, y, ms)
        els += mk
        e = T(it["title"], x, y + ms + 0.25, cw, 0.6, fit_size(it["title"], cw, 0.6, 24, 15, bold=True, max_lines=1),
              "text", True, "heading", valign="t")
        e["grp"] = "toc_title"
        els.append(e)
        els.append(R(x, y + ms + 0.95, min(cw * 0.5, 1.4), 0.06, fill="primary@0.6", radius=0.03))
        if it["text"]:
            e = T(it["text"], x, y + ms + 1.15, cw, 0.9, body_size(it["text"], cw, 0.9, 15, 11), "muted", valign="t")
            e["grp"] = "toc_text"
            els.append(e)
    step_end()
    return els, {"master": "content", "header": False}


def section(s, ctx):
    """Chapter divider: number in the shared number style, title, one line."""
    els = []
    hero = ctx.asset("hero")
    num = str(s.get("number", ""))
    wm = num and not hero and ctx.S.decor.get("number_watermark", True)
    tw = 6.8 if (hero or wm) else CW
    x = MX + 0.1
    if wm:
        # giant faded chapter number filling the empty right half
        size = 330 if len(num) <= 2 else 240
        e = T(num, 6.4, 0.9, CANVAS_W - 6.4 - 0.3, 5.8, size, ctx.S.decor.get("watermark_color", "primary@0.10"),
              True, "display", align="r", valign="m", ls=0.9)
        e["role"] = "decor"
        els.append(e)
    y = 1.9
    if num:
        st = ctx.S.decor.get("number_style", "plain")
        mk, _ = num_mark(ctx, num, x, y + (0 if st == "plain" else 0.25), 1.5 if st == "plain" else 1.1, big=True)
        els += mk
        y += 1.6
    if s.get("kicker"):
        k = T(s["kicker"], x, y - 0.05, tw, 0.4, 14, "highlight", True, "body", valign="m", spc=2)
        k["grp"] = "kicker"
        els.append(k)
        y += 0.45
    t = s.get("title", "")
    els.append(T(t, x, y, tw, 1.0, fit_size(t, tw, 1.0, 44, 26, bold=True, max_lines=1), "strong", True, "heading", valign="m"))
    y += 1.1
    if s.get("subtitle"):
        els.append(T(s["subtitle"], x, y, tw, 0.6, body_size(s["subtitle"], tw, 0.6, 20, 13), "muted", valign="t"))
    if hero:
        els.append(IMG(hero, 7.7, 1.1, 5.0, 5.0))
    return els, {"master": "cover", "header": False}


# ------------------------------------------------------------------ relationship & data layouts
def _tints(ctx, n):
    """Fill tokens for n stacked bands: solid first, then light tints (mid-tones fail text contrast)."""
    out = []
    for i in range(n):
        lo = 0.34 if ctx.S.dark else 0.16  # on dark pages faint tints vanish into the background
        st = 1.0 if i == 0 else max(lo, 0.55 - (0.55 - lo) * (i - 1) / max(1, n - 2))
        out.append("primary" if i == 0 else f"primary@{st:.2f}")
    return out


def _ink(ctx, fill):
    """Text token for a tinted fill: on_primary when it reads, else the best of the page tones."""
    from common import contrast
    bg = ctx.S.c(fill)
    if contrast(ctx.S.c("on_primary"), bg) >= 3.2:
        return "on_primary"
    return max(("strong", "text", "bg_top"), key=lambda k: contrast(ctx.S.c(k), bg))


def timeline_layout(s, ctx):
    """3-6 dated milestones on one axis; a card under each."""
    els, tb = title_block(ctx, s)
    items = s.get("items", [])
    n = max(1, len(items))
    cw = CW / n
    longest = max(len(str(x.get("text", ""))) for x in items) if items else 0
    ch_est = min(CONTENT_B - CONTENT_Y - 1.45, 1.25 + 0.5 * (longest * 16 / 72 / max(0.5, cw - 0.44)))
    ay = CONTENT_Y + 1.05 + max(0, (CONTENT_B - CONTENT_Y - 1.45 - ch_est) / 2)
    els.append(LN(MX, ay, CANVAS_W - MX, ay, "primary@0.45", 2.5, arrow=True))
    for i, it in enumerate(items):
        step(i)
        cx = MX + cw * (i + 0.5)
        emph = it.get("emphasis") == "primary"
        d = 0.42 if emph else 0.28
        els.append(E(cx - d / 2, ay - d / 2, d, d, "accent" if emph else "primary"))
        date = str(it.get("date", ""))
        if date:
            els.append(T(date, cx - cw / 2 + 0.05, ay - 0.95, cw - 0.1, 0.62,
                         fit_size(date, cw - 0.1, 0.6, 22, 12, bold=True, max_lines=1, latin_scale=DISPLAY_LATIN),
                         "highlight", True, "display", align="c", valign="b"))
        cy = ay + 0.4
        ch = min(CONTENT_B - cy, ch_est)
        els.append(LN(cx, ay + d / 2, cx, cy, "primary@0.45", 1.25))
        els.append(card(ctx, cx - cw / 2 + 0.07, cy, cw - 0.14, ch, "tint" if emph else "glass"))
        tx, tw = cx - cw / 2 + 0.22, cw - 0.44
        ty = cy + 0.2
        if it.get("title"):
            ts = fit_size(it["title"], tw, 0.7, 19, 12, bold=True)
            th = min(0.7, n_lines(it["title"], ts, tw, True) * ts * 1.2 * 1.2 / 72 + 0.04)
            els.append(T(it["title"], tx, ty, tw, th, ts, "strong", True, "heading", align="c"))
            els[-1]["grp"] = "tl_title"
            ty += th + 0.1
        if it.get("text"):
            els.append(T(it["text"], tx, ty, tw, cy + ch - ty - 0.15, body_size(it["text"], tw, cy + ch - ty - 0.15, 17, 10),
                         "muted", align="c", ls=1.3))
            els[-1]["grp"] = "tl_text"
    step_end()
    return els, {"master": "content"}


def funnel_layout(s, ctx):
    """3-5 narrowing stages, value inside each band, explanation on the right."""
    els, tb = title_block(ctx, s)
    items = s.get("items", [])
    n = max(1, len(items))
    gap = 0.1
    rh = min(0.85, (CONTENT_B - CONTENT_Y - gap * (n - 1)) / n)
    total = n * rh + (n - 1) * gap
    y = CONTENT_Y + (CONTENT_B - CONTENT_Y - total) / 2
    axis = MX + 3.1
    wmax, wmin = 6.0, 2.4
    fills = _tints(ctx, n)
    import re as _re
    nums = []
    for it in items:
        m = _re.search(r"[\d.]+", str(it.get("value", "")).replace(",", ""))
        nums.append(float(m.group()) if m else None)
    prop = all(v is not None and v > 0 for v in nums) and len(nums) > 1
    for i, it in enumerate(items):
        step(i)
        if prop:
            w = max(wmin, wmax * nums[i] / max(nums))
        else:
            w = wmax - (wmax - wmin) * (i / max(1, n - 1))
        els.append(R(axis - w / 2, y, w, rh, fill=fills[i], radius=0.1))
        lab = " ".join(t for t in (str(it.get("label", "")), str(it.get("value", ""))) if t)
        els.append(T(lab, axis - w / 2 + 0.1, y, w - 0.2, rh,
                     fit_size(lab, w - 0.2, rh - 0.1, 20, 11, bold=True, max_lines=1),
                     _ink(ctx, fills[i]), True, "heading", align="c", valign="m"))
        if it.get("text"):
            tx = axis + wmax / 2 + 0.45
            els.append(LN(axis + w / 2 + 0.08, y + rh / 2, tx - 0.12, y + rh / 2, "line", 1.0))
            els.append(T(it["text"], tx, y, CANVAS_W - MX - tx, rh,
                         body_size(it["text"], CANVAS_W - MX - tx, rh - 0.05, 17, 11), "text", valign="m"))
        y += rh + gap
    step_end()
    return els, {"master": "content"}


def hub_layout(s, ctx):
    """One centre, 3-6 related parts around it (left and right columns, lines to the centre)."""
    import math
    els, tb = title_block(ctx, s)
    center = s.get("center") or {}
    items = s.get("items", [])
    n = len(items)
    cx, cy, r = CANVAS_W / 2, (CONTENT_Y + CONTENT_B) / 2 + 0.05, 1.05
    colw = 4.2
    left = items[: (n + 1) // 2]
    right = items[(n + 1) // 2:]
    lines, cards = [], []
    for side, col in ((left, "l"), (right, "r")):
        k = max(1, len(side))
        gap = 0.22
        rh = min(1.15, (CONTENT_B - CONTENT_Y - gap * (k - 1)) / k)
        total = k * rh + (k - 1) * gap
        y = CONTENT_Y + (CONTENT_B - CONTENT_Y - total) / 2
        x = MX if col == "l" else CANVAS_W - MX - colw
        for it in side:
            ex = x + colw if col == "l" else x
            ey = y + rh / 2
            ang = math.atan2(ey - cy, ex - cx)
            lines.append(LN(cx + r * math.cos(ang), cy + r * math.sin(ang), ex, ey, "primary@0.5", 1.5))
            cards.append((it, x, y, rh))
            y += rh + gap
    els += lines
    els.append(E(cx - r - 0.12, cy - r - 0.12, 2 * r + 0.24, 2 * r + 0.24, "primary@0.18"))
    els.append(E(cx - r, cy - r, 2 * r, 2 * r, "primary"))
    ct = center.get("title") or s.get("center_title", "")
    if ct:
        els.append(T(ct, cx - r + 0.12, cy - r + 0.15, 2 * r - 0.24, 2 * r - 0.3,
                     fit_size(ct, 2 * r - 0.3, 2 * r - 0.5, 24, 12, bold=True), "on_primary", True, "heading",
                     align="c", valign="m"))
    for i, (it, x, y, rh) in enumerate(cards):
        step(i)
        els.append(card(ctx, x, y, colw, rh))
        isz = min(0.5, rh - 0.3)
        els.append(item_mark(ctx, s.get("items", []), i, "sparkles", x + 0.2, y + (rh - isz) / 2, isz))
        tx, tw = x + 0.35 + isz, colw - isz - 0.55
        txt = f"**{it['title']}**  {it.get('text', '')}" if it.get("title") else it.get("text", "")
        els.append(T(txt.strip(), tx, y + 0.06, tw, rh - 0.12, body_size(txt, tw, rh - 0.12, 17, 10), "text", valign="m"))
        els[-1]["grp"] = "hub_text"
    step_end()
    return els, {"master": "content"}


def matrix_layout(s, ctx):
    """2x2 positioning matrix: two named axes, four quadrants (TL, TR, BL, BR)."""
    els, tb = title_block(ctx, s)
    xa, ya = s.get("x_axis") or {}, s.get("y_axis") or {}
    quads = (s.get("quadrants") or [])[:4]
    gut = 1.0
    ax0, ax1 = MX + gut, CANVAS_W - MX
    ay0, ay1 = CONTENT_Y + 0.05, CONTENT_B - 0.35
    gap = 0.12
    qw, qh = (ax1 - ax0 - gap) / 2, (ay1 - ay0 - gap) / 2
    pos = [(ax0, ay0), (ax0 + qw + gap, ay0), (ax0, ay0 + qh + gap), (ax0 + qw + gap, ay0 + qh + gap)]
    for q, (x, y) in zip(quads, pos):
        step()
        emph = q.get("emphasis") == "primary"
        els.append(R(x, y, qw, qh, fill="primary" if emph else "surface", alpha=1.0 if emph else ctx.S.shape.get("card_alpha", 0.86),
                     radius=ctx.S.shape.get("radius", 0.16), line=None if emph else "line", shadow=emph))
        tc = "on_primary" if emph else "strong"
        if q.get("title"):
            els.append(T(q["title"], x + 0.25, y + 0.15, qw - 0.5, 0.5,
                         fit_size(q["title"], qw - 0.5, 0.5, 20, 12, bold=True, max_lines=1), tc, True, "heading", valign="m"))
        its = [i if isinstance(i, str) else i.get("text", "") for i in q.get("items", [])]
        if its:
            body = "\n".join(f"· {t}" for t in its)
            els.append(T(body, x + 0.25, y + 0.72, qw - 0.5, qh - 0.85, body_size(body, qw - 0.5, qh - 0.85, 16, 10),
                         "on_primary" if emph else "text", ls=1.35))
    step_end()
    # axes
    els.append(LN(ax0 - 0.12, ay1 + 0.12, ax0 - 0.12, ay0 - 0.05, "muted", 1.5, arrow=True))
    els.append(LN(ax0 - 0.12, ay1 + 0.12, ax1 + 0.05, ay1 + 0.12, "muted", 1.5, arrow=True))
    if ya.get("high"):
        els.append(T(ya["high"], MX - 0.05, ay0, gut - 0.25, 0.4, 12, "muted", align="r", valign="t"))
    if ya.get("label"):
        els.append(T(ya["label"], MX - 0.05, ay0 + qh - 0.2, gut - 0.25, 1.0,
                     fit_size(ya["label"], gut - 0.25, 1.0, 14, 10, bold=True), "strong", True, align="r", valign="m"))
    if ya.get("low"):
        els.append(T(ya["low"], MX - 0.05, ay1 - 0.4, gut - 0.25, 0.4, 12, "muted", align="r", valign="b"))
    if xa.get("low"):
        els.append(T(xa["low"], ax0, ay1 + 0.18, 2.5, 0.32, 12, "muted", valign="t"))
    if xa.get("label"):
        els.append(T(xa["label"], (ax0 + ax1) / 2 - 2.5, ay1 + 0.18, 5.0, 0.32, 14, "strong", True, align="c", valign="t"))
    if xa.get("high"):
        els.append(T(xa["high"], ax1 - 2.5, ay1 + 0.18, 2.5, 0.32, 12, "muted", align="r", valign="t"))
    return els, {"master": "content"}


def table_layout(s, ctx):
    """Native, editable table. First column = row names; optional highlighted column."""
    els, tb = title_block(ctx, s)
    cols = s.get("columns", [])
    rows = s.get("rows", [])
    if not cols:
        return list_icons(s, ctx)
    y0 = CONTENT_Y
    avail = CONTENT_B - y0 - (0.45 if s.get("note") else 0)
    nr = len(rows) + 1
    rh = min(0.62, avail / nr)
    h = rh * nr
    lens = []
    for c in range(len(cols)):
        cells = [str(cols[c])] + [str(r[c]) if c < len(r) else "" for r in rows]
        lens.append(max(4, max(len(x.replace("**", "")) for x in cells)))
    tot = sum(lens)
    size = 16
    for c, L_ in enumerate(lens):
        cwid = CW * L_ / tot
        longest = max([str(cols[c])] + [str(r[c]) if c < len(r) else "" for r in rows], key=len)
        size = min(size, fit_size(longest, cwid - 0.25, rh - 0.1, 16, 10, max_lines=2))
    els.append({"t": "table", "x": MX, "y": y0, "w": CW, "h": h, "columns": cols, "rows": rows,
                "col_widths": lens, "size": size, "head_size": min(size + 1, 17),
                "highlight_col": s.get("highlight_col")})
    if s.get("note"):
        els.append(T(s["note"], MX, y0 + h + 0.1, CW, 0.35, 12, "muted", valign="t"))
    return els, {"master": "content"}


def _chart_panel(ctx, spec, x, y0, cw, h):
    """One chart in a card: its own title, unit line above, category-axis line below."""
    els = [card(ctx, x, y0, cw, h)]
    if spec.get("title"):
        els.append(T(spec["title"], x + 0.3, y0 + 0.15, cw - 0.6, 0.4, 14, "muted", True, valign="m"))
    top = y0 + (0.55 if spec.get("title") else 0.2)
    bottom = y0 + h - 0.15
    # axis titles carry the unit or the meaning of the scale ("单位：万元"); the value axis is
    # hidden, so they sit as small text above and below the plot instead of on the axes
    if spec.get("y_title"):
        els.append(T(spec["y_title"], x + 0.3, top, cw - 0.6, 0.32, 12, "muted", valign="m"))
        top += 0.36
    if spec.get("x_title"):
        bottom -= 0.36
        els.append(T(spec["x_title"], x + 0.3, bottom + 0.04, cw - 0.6, 0.32, 12, "muted", align="c", valign="m"))
    els.append({"t": "chart", "x": x + 0.2, "y": top, "w": cw - 0.4, "h": bottom - top, "chart": spec, "size": 14})
    return els


def chart_layout(s, ctx):
    """Native chart on the left, 1-3 insight cards on the right. With "charts" (two or three
    charts on one page, as in many originals) the charts sit side by side, one card each, and
    the insights run as a row of short cards underneath."""
    els, tb = title_block(ctx, s)
    specs = [c for c in (s.get("charts") or [s.get("chart") or {}]) if c is not None]
    ins = s.get("insights", [])
    y0, h = CONTENT_Y, CONTENT_B - CONTENT_Y
    if len(specs) > 1:
        rh = 0.95 if ins else 0
        ch_h = h - (rh + 0.2 if ins else 0)
        gap = 0.3
        n = len(specs)
        cw = (CW - gap * (n - 1)) / n
        for i, spec in enumerate(specs):
            els += _chart_panel(ctx, spec, MX + i * (cw + gap), y0, cw, ch_h)
        if ins:
            iy = y0 + ch_h + 0.2
            m = len(ins)
            iw = (CW - gap * (m - 1)) / m
            for i, t in enumerate(ins):
                x = MX + i * (iw + gap)
                step(i)
                els.append(card(ctx, x, iy, iw, rh, "tint" if i == 0 else "glass"))
                els.append(T(t, x + 0.25, iy + 0.08, iw - 0.5, rh - 0.16, body_size(t, iw - 0.5, rh - 0.16, 17, 11),
                             "text", i == 0, valign="m"))
            step_end()
        return els, {"master": "content"}
    spec = specs[0] if specs else {}
    cw = 7.5 if ins else CW
    els += _chart_panel(ctx, spec, MX, y0, cw, h)
    if ins:
        x = MX + cw + 0.4
        w = CANVAS_W - MX - x
        n = len(ins)
        gap = 0.2
        rh = min(1.3, (h - gap * (n - 1)) / n)
        total = n * rh + (n - 1) * gap
        y = y0 + (h - total) / 2
        for i, t in enumerate(ins):
            prim = i == 0
            els.append(card(ctx, x, y, w, rh, "tint" if prim else "glass"))
            els.append(T(f"{i + 1:02d}", x + 0.2, y, 0.6, rh, 20, "highlight", True, "display", valign="m"))
            els.append(T(t, x + 0.85, y + 0.08, w - 1.05, rh - 0.16, body_size(t, w - 1.05, rh - 0.16, 17, 11),
                         "text", prim, valign="m"))
            y += rh + gap
    return els, {"master": "content"}


FRAME_LABELS = {
    "swot": {"s": "优势", "w": "劣势", "o": "机会", "t": "威胁"},
    "pest": {"p": "政治", "e": "经济", "s": "社会", "t": "技术"},
    "five_forces": {"center": "行业内竞争", "entrant": "新进入者威胁", "substitute": "替代品威胁",
                    "supplier": "供应商议价能力", "buyer": "购买者议价能力"},
    "canvas": {"kp": "重要伙伴", "ka": "关键业务", "kr": "核心资源", "vp": "价值主张", "cr": "客户关系",
               "ch": "渠道通路", "cs": "客户细分", "cost": "成本结构", "revenue": "收入来源"},
}


def _block(ctx, x, y, w, h, label, items, badge=None, badge_fill="primary", emph=False, size_max=15, inline=False):
    els = [card(ctx, x, y, w, h, "tint" if emph else "glass")]
    tx = x + 0.2
    if badge:
        bs = 0.56
        els.append(E(x + 0.2, y + 0.18, bs, bs, badge_fill))
        els.append(T(badge, x + 0.2, y + 0.18, bs, bs, 18, _ink(ctx, badge_fill), True, "display", align="c", valign="m"))
        tx = x + 0.2 + bs + 0.15
    lw_ = 1.5 if inline else x + w - tx - 0.15
    els.append(T(label, tx, y + (0.12 if inline else 0.18), lw_, (h - 0.24) if inline else (0.56 if badge else 0.4),
                 fit_size(label, lw_, 0.5, 18 if badge else 15, 10, bold=True, max_lines=1),
                 "strong", True, "heading", valign="m"))
    els[-1]["grp"] = "fw_label"
    top = y + (0.9 if badge else 0.62)
    its = [i if isinstance(i, str) else i.get("text", "") for i in (items or [])]
    if isinstance(items, str):
        its = [items]
    if its and inline:
        body = "、".join(its)
        lw = x + w - tx - 0.15 - 1.6
        els.append(T(body, x + 1.8, y + 0.12, w - 2.0, h - 0.24, body_size(body, w - 2.0, h - 0.24, size_max, 10),
                     "text", valign="m"))
    elif its:
        body = "\n".join(f"· {t}" for t in its)
        els.append(T(body, x + 0.2, top, w - 0.4, y + h - top - 0.12,
                     body_size(body, w - 0.4, y + h - top - 0.12, size_max, 10), "text", ls=1.3))
        els[-1]["grp"] = "fw_body"
    return els


def framework_layout(s, ctx):
    """Analysis frameworks: swot, pest, five_forces, canvas."""
    els, tb = title_block(ctx, s)
    fw = s.get("framework") or {}
    kind = fw.get("kind", "swot")
    B = fw.get("blocks", {})
    lab = dict(FRAME_LABELS.get(kind, {}))
    lab.update(fw.get("labels", {}))
    y0, y1 = CONTENT_Y, CONTENT_B
    if kind == "swot":
        gap = 0.25
        w, h = (CW - gap) / 2, (y1 - y0 - gap) / 2
        spec = [("s", "S", "primary"), ("w", "W", "accent"), ("o", "O", "primary"), ("t", "T", "accent")]
        for i, (k, letter, fill) in enumerate(spec):
            step(i)
            x = MX + (i % 2) * (w + gap)
            y = y0 + (i // 2) * (h + gap)
            els += _block(ctx, x, y, w, h, lab[k], B.get(k), letter, fill, size_max=18)
        step_end()
    elif kind == "pest":
        gap = 0.25
        w = (CW - 3 * gap) / 4
        most = max((len(B.get(k) or []) if isinstance(B.get(k), list) else 1) for k in "pest")
        h = min(y1 - y0, 1.2 + 0.62 * most + 0.3)
        yy = y0 + (y1 - y0 - h) / 2
        for i, k in enumerate(["p", "e", "s", "t"]):
            step(i)
            x = MX + i * (w + gap)
            els += _block(ctx, x, yy, w, h, lab[k], B.get(k), k.upper(), "primary" if i % 2 == 0 else "accent",
                          size_max=18)
        step_end()
    elif kind == "five_forces":
        cx, cy = CANVAS_W / 2, (y0 + y1) / 2
        cw_, ch_ = 3.8, 1.4
        sw, sh = 3.4, 1.55
        tw, th = 5.8, 1.05
        boxes = {"center": (cx - cw_ / 2, cy - ch_ / 2, cw_, ch_),
                 "entrant": (cx - tw / 2, y0, tw, th), "substitute": (cx - tw / 2, y1 - th, tw, th),
                 "supplier": (MX, cy - sh / 2, sw, sh), "buyer": (CANVAS_W - MX - sw, cy - sh / 2, sw, sh)}
        arrows = [(cx, y0 + th, cx, cy - ch_ / 2), (cx, y1 - th, cx, cy + ch_ / 2),
                  (MX + sw, cy, cx - cw_ / 2, cy), (CANVAS_W - MX - sw, cy, cx + cw_ / 2, cy)]
        for a in arrows:
            els.append(LN(*a, color="primary@0.5", w=1.75, arrow=True))
        for k, (x, y, w, h) in boxes.items():
            step()
            els += _block(ctx, x, y, w, h, lab[k], B.get(k), None, emph=(k == "center"), size_max=14)
        step_end()
    elif kind == "canvas":
        gap = 0.1
        bh = 0.72
        topH = (y1 - y0) - bh - gap
        w = (CW - 4 * gap) / 5
        xs = [MX + i * (w + gap) for i in range(5)]
        half = (topH - gap) / 2
        cells = [("kp", xs[0], y0, w, topH), ("ka", xs[1], y0, w, half), ("kr", xs[1], y0 + half + gap, w, half),
                 ("vp", xs[2], y0, w, topH), ("cr", xs[3], y0, w, half), ("ch", xs[3], y0 + half + gap, w, half),
                 ("cs", xs[4], y0, w, topH)]
        for k, x, y, ww, hh in cells:
            els += _block(ctx, x, y, ww, hh, lab[k], B.get(k), None, emph=(k == "vp"), size_max=14)
        by = y0 + topH + gap
        bw = (CW - gap) / 2
        for k, x in (("cost", MX), ("revenue", MX + bw + gap)):
            els += _block(ctx, x, by, bw, bh, lab[k], B.get(k), None, size_max=15, inline=True)
    return els, {"master": "content"}


def closing(s, ctx):
    dark = ctx.S.decor.get("closing_dark", True)
    # text on the dark closing ground (a brand with a light primary closes on its darkest colour)
    on = ("on_dark" if "on_dark" in ctx.S.palette else "on_primary") if dark else "strong"
    soft = ("on_dark" if "on_dark" in ctx.S.palette else "primary@0.18") if dark else None
    els = []
    hero = ctx.asset("hero")
    y = 0.7
    if hero:
        els.append(IMG(hero, (CANVAS_W - 3.6) / 2, 0.5, 3.6, 2.7))
        y = 3.25
    else:
        y = 2.2
    head = s.get("headline") or s.get("title", "")
    if s.get("kicker"):
        els.append(T(s["kicker"], MX, y, CW, 0.4, 14, soft if dark else "highlight", True, "body",
                     align="c", valign="m", spc=2))
        y += 0.5
    els.append(T(head, MX, y, CW, 0.95, fit_size(head, CW, 0.95, 46, 26, bold=True, max_lines=1), on, True, "heading",
                 align="c", valign="m"))
    y += 1.05
    if s.get("body"):
        els.append(T(s["body"], MX + 1, y, CW - 2, 0.6, body_size(s["body"], CW - 2, 0.6, 19, 12),
                     soft if dark else "muted", align="c", valign="m"))
        y += 0.95
    if s.get("cta"):
        from common import text_width_pt
        cs = 17
        cw = text_width_pt(s["cta"], cs, True) / 72 + 1.3
        cx = (CANVAS_W - cw) / 2
        els.append(R(cx, y, cw, 0.7, fill="surface" if dark else "primary", radius=0.35 if ctx.S.shape.get("radius", 0.16) >= 0.1 else (ctx.S.shape.get("radius") or None), shadow=True))
        els.append(T(s["cta"], cx + 0.35, y, cw - 1.0, 0.7, cs, "primary" if dark else "on_primary", True, align="c", valign="m"))
        els.append(ICON(ctx.icon(0, "arrow-right"), cx + cw - 0.62, y + 0.14, 0.42,
                        color="on_primary" if dark else "primary", bg="primary" if dark else "surface"))
    return els, {"master": "closing", "header": False}


# ------------------------------------------------------------------ screenshots
def _img_file(ctx, path):
    """Image path as written in deck.json: absolute, relative to the cwd, or to the work dir."""
    from pathlib import Path as _P
    if not path:
        return None
    p = _P(path)
    if p.exists():
        return str(p)
    w = ctx.meta.get("_work")
    if w and (_P(w) / path).exists():
        return str(_P(w) / path)
    return None


def _img_ratio(path):
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.size[0] / max(1, im.size[1])
    except Exception:
        return 16 / 10


def shot_frame(ctx, path, x, y, w, h, frame=None, align="l"):
    """A screenshot fitted into the box (x, y, w, h), inside a frame that hugs the picture.
    frame: "window" (card with a slim title bar and three dots), "card" (card only) or "none".
    Returns (elements, (ix, iy, iw, ih)) where the second part is where the picture landed."""
    frame = frame or ctx.S.decor.get("shot_frame", "window")
    bar = 0.26 if frame == "window" else 0
    pad = 0.07 if frame != "none" else 0
    ar = _img_ratio(path) if path else 16 / 10
    aw, ah = w - 2 * pad, h - 2 * pad - bar
    iw, ih = (aw, aw / ar) if aw / ah < ar else (ah * ar, ah)
    fw, fh = iw + 2 * pad, ih + 2 * pad + bar
    fx = x if align == "l" else (x + (w - fw) / 2 if align == "c" else x + w - fw)
    fy = y + (h - fh) / 2
    els = []
    if frame != "none":
        r = min(0.14, ctx.S.shape.get("radius", 0.16) or 0.0) or None
        d = getattr(ctx.S, "depth", "shadow")
        els.append(R(fx, fy, fw, fh, fill="surface", radius=r, line="line" if d != "shadow" else None,
                     shadow={"shadow": True, "whisper": "soft"}.get(d, False)))
        if bar:
            for k in range(3):
                els.append(E(fx + 0.14 + k * 0.17, fy + 0.085, 0.1, 0.1, "primary@0.35"))
    ix, iy = fx + pad, fy + pad + bar
    if path:
        im = IMG(path, ix, iy, iw, ih, fit="stretch")
        im["role"] = "shot"
        els.append(im)
    else:
        els.append(R(ix, iy, iw, ih, fill="tint"))
        els.append(T("截图", ix, iy, iw, ih, 16, "muted", align="c", valign="m"))
    return els, (ix, iy, iw, ih)


def _pin(ctx, num, cx, cy, d=0.36):
    """Numbered pin placed on a screenshot."""
    ring = E(cx - d / 2 - 0.03, cy - d / 2 - 0.03, d + 0.06, d + 0.06, "surface")
    dot = E(cx - d / 2, cy - d / 2, d, d, "primary")
    t = T(str(num), cx - d / 2, cy - d / 2, d, d, 12, _ink(ctx, "primary"), True, "display", align="c", valign="m", ls=1.0)
    t["role"] = "marker"
    for e in (ring, dot):
        e["role"] = "marker"
    return [ring, dot, t]


def shot_notes(s, ctx):
    """One big screenshot with numbered notes beside it. items[].at = [x, y] (0..1 of the picture)
    drops a numbered pin on the screenshot that matches the note."""
    els, tb = title_block(ctx, s)
    items = [it if isinstance(it, dict) else {"text": it} for it in (s.get("items") or [])][:5]
    path = _img_file(ctx, s.get("image"))
    ar = _img_ratio(path) if path else 16 / 10
    y0, y1 = max(CONTENT_Y, tb + 0.3), CONTENT_B
    cap = s.get("caption")
    if cap:
        y1 -= 0.4
    if not items:
        fr, box = shot_frame(ctx, path, MX, y0, CW, y1 - y0, s.get("frame"), align="c")
        els += fr
    else:
        # wide shots get about 62% of the width, tall phone shots only what their height allows
        sw = min(CW * 0.62, (y1 - y0) * ar + 0.2) if ar >= 1 else min(CW * 0.45, (y1 - y0 - 0.33) * ar + 0.14)
        sw = max(sw, 2.4)
        fr, box = shot_frame(ctx, path, MX, y0, sw, y1 - y0, s.get("frame"))
        els += fr
        fx_right = max(e["x"] + e["w"] for e in fr if e["t"] in ("rect", "image"))
        nx = fx_right + 0.5
        nw = CANVAS_W - MX - nx
        n = len(items)
        gap = 0.18
        rh = min(1.35, (y1 - y0 - gap * (n - 1)) / n)
        top = y0 + (y1 - y0 - (rh * n + gap * (n - 1))) / 2
        d = 0.42
        for i, it in enumerate(items):
            step(i)
            num = it.get("num") or str(i + 1)
            yy = top + i * (rh + gap)
            els += _pin(ctx, num, nx + d / 2, yy + d / 2 + 0.02, d)
            tx, tw = nx + d + 0.2, nw - d - 0.2
            ty = yy
            if it.get("title"):
                ts = fit_size(it["title"], tw, 0.4, 18, 14, bold=True, max_lines=1)
                t = T(it["title"], tx, ty, tw, 0.42, ts, "strong", True, valign="m")
                t["grp"] = "shot_t"
                els.append(t)
                ty += 0.44
            if it.get("text"):
                bh = max(0.3, yy + rh - ty)
                t = T(it["text"], tx, ty, tw, bh, body_size(it["text"], tw, bh, 16, 11), "text", valign="t")
                if not it.get("title"):
                    # first line sits level with the pin
                    lh = t["size"] * 1.2 * 1.2 / 72
                    t["y"], t["h"] = yy + 0.02 + max(0, (d - lh) / 2), max(0.3, rh - 0.02 - max(0, (d - lh) / 2))
                t["grp"] = "shot_b"
                els.append(t)
            if it.get("at") and path:
                ax, ay = it["at"]
                ix, iy, iw, ih = box
                els += _pin(ctx, num, ix + iw * float(ax), iy + ih * float(ay), 0.36)
        step_end()
    if cap:
        ix, iy, iw, ih = box
        bottom = max(e["y"] + e["h"] for e in els if e["t"] in ("rect", "image") and e.get("role") != "marker")
        els.append(T(cap, MX, bottom + 0.08, CW, 0.32, 12, "muted", align="l", valign="t"))
    return els, {}


def shot_stack(s, ctx):
    """Two to four screenshots in a row, each with a number, a short title and one line.
    Arrows between them when the items are steps (flow, default true)."""
    els, tb = title_block(ctx, s)
    head = list(els)
    items = [it if isinstance(it, dict) else {"image": it} for it in (s.get("items") or [])][:4]
    n = max(1, len(items))
    y0, y1 = max(CONTENT_Y, tb + 0.3), CONTENT_B
    has_cap = any(it.get("title") or it.get("text") for it in items)
    cap_h = 0.0
    if has_cap:
        cap_h = (0.42 if any(it.get("title") for it in items) else 0) + (0.62 if any(it.get("text") for it in items) else 0) + 0.12
    flow = s.get("flow", True) and n > 1
    gap = 0.55 if flow else 0.5
    ih = y1 - y0 - cap_h
    paths = [_img_file(ctx, it.get("image")) for it in items]
    # each column as wide as its picture wants at full height (a phone shot is narrow, a desktop
    # shot wide); squeeze them all by one factor when the row is too long, then centre the row
    frame = s.get("frame") or ctx.S.decor.get("shot_frame", "window")
    extra_h = (0.26 if frame == "window" else 0) + (0.14 if frame != "none" else 0)
    want = [max(1.6, (ih - extra_h) * (_img_ratio(p) if p else 1.6) + 0.14) for p in paths]
    k = min(1.0, (CW - gap * (n - 1)) / sum(want))
    widths = [w_ * k for w_ in want]
    if n > 1 and k == 1.0:
        gap = min(1.2, (CW - sum(widths)) / (n - 1) * 0.5 + gap * 0.5) if sum(widths) + gap * (n - 1) < CW else gap
    x = MX + (CW - sum(widths) - gap * (n - 1)) / 2
    frames = []
    for i, it in enumerate(items):
        fr, box = shot_frame(ctx, paths[i], x, y0, widths[i], ih, s.get("frame"), align="c")
        frames.append((fr, box, x))
        x += widths[i] + gap
    # line the frames up on one bottom edge so captions start at the same height
    def _bottom(fr):
        return max(e["y"] + e["h"] for e in fr if e["t"] in ("rect", "image"))
    fb = max(_bottom(fr) for fr, _, _ in frames)
    mids = []
    for fr, box, x in frames:
        dy = fb - _bottom(fr)
        for e in fr:
            e["y"] += dy
        mids.append(box[1] + dy + box[3] / 2)
        els += fr
    for i, ((fr, box, x), it) in enumerate(zip(frames, items)):
        cy = fb + 0.14
        num = it.get("num") or (f"{i + 1:02d}" if flow else None)
        # captions start at the frame's left edge; narrow frames borrow width from the gap
        fx0 = min(e["x"] for e in fr if e["t"] in ("rect", "image"))
        cw = max(widths[i], 2.2) if n * 2.2 + gap * (n - 1) <= CW else widths[i]
        x = fx0
        tx, tw = x, cw
        if it.get("title"):
            if num:
                nm = T(num, x, cy, 0.62, 0.4, 20, "highlight", True, "display", valign="m", ls=1.0)
                nm["role"] = "marker"
                els.append(nm)
                tx, tw = x + 0.62, cw - 0.62
            t = T(it["title"], tx, cy, tw, 0.4, fit_size(it["title"], tw, 0.4, 18, 13, bold=True, max_lines=1),
                  "strong", True, valign="m")
            t["grp"] = "stack_t"
            els.append(t)
            cy += 0.42
        if it.get("text"):
            t = T(it["text"], x, cy, cw, 0.6, body_size(it["text"], cw, 0.6, 15, 11), "text")
            t["grp"] = "stack_b"
            els.append(t)
    if flow:
        for i in range(n - 1):
            r_ = max(e["x"] + e["w"] for e in frames[i][0] if e["t"] in ("rect", "image"))
            l_ = min(e["x"] for e in frames[i + 1][0] if e["t"] in ("rect", "image"))
            my = (mids[i] + mids[i + 1]) / 2
            span = min(0.45, (l_ - r_) * 0.6)
            ax = (r_ + l_ - span) / 2
            els.append(LN(ax, my, ax + span, my, color="primary", w=2.0, arrow=True))
    # the row is width-bound when the shots are wide: centre it in the free height
    mine = els[len(head):]
    if mine:
        top = min(e["y"] for e in mine)
        bot = max(e["y"] + e["h"] for e in mine)
        dy = max(0.0, (y1 - bot) - (top - y0)) / 2
        if dy > 0.05:
            for e in mine:
                e["y"] += dy
                if e["t"] == "line":
                    e["y1"] += dy
                    e["y2"] += dy
    return els, {}


# ------------------------------------------------------------------ explanation with formulas
TONES = {"up": "2E7D32", "down": "C62828", "good": "2E7D32", "bad": "C62828"}


def _formula_size(f, fs, w):
    """A display formula reads best on one line: start a step above the body size and come
    down (not below the body size minus one step) until it fits."""
    from common import LADDER
    floor_ = fs if w >= 3.0 else max(12, fs * 0.7)  # narrow columns may shrink further to stay on one line
    steps = [v for v in (LADDER["steps"] or range(8, 100)) if floor_ - 0.01 <= v <= fs * 1.2 + 0.01]
    steps = sorted(steps, reverse=True) or [fs]
    for v in steps:
        if n_lines(f, v, w - 0.4, "**" in f) <= 1:
            return v
    return steps[-1]  # still too long: wrap at body size rather than shrink it unreadable


def _block_h(b, fs, w, fsize=None):
    """Height (in) of one explain block at base size fs (fsize: formula size, if fixed)."""
    pitch = 1.2 * LINE_PITCH / 72
    if "label" in b:
        return fs * pitch + 0.04
    if "formula" in b:
        f2 = fsize or _formula_size(b["formula"], fs, w)
        return n_lines(b["formula"], f2, w - 0.4, False) * f2 * 1.15 * pitch + 0.24
    if "rule" in b:
        return n_lines(b["rule"], fs, w - 0.42, True) * fs * 1.25 * pitch + 0.04
    if "note" in b:
        f2 = max(11, fs * 0.85)
        return n_lines(b["note"], f2, w, False) * f2 * 1.3 * pitch + 0.04
    t = b.get("text", "")
    return n_lines(t, fs, w, False) * fs * 1.35 * pitch + 0.06


def explain(s, ctx):
    """Teaching page: labels, sentences and display formulas, in one to four columns,
    optionally next to a diagram. Blocks: {label}, {text}, {formula}, {rule, tone}, {note}.
    Formulas sit centred in a tinted strip; rules get a coloured dot (tone up/down keeps
    the green/red a maths deck uses for increasing/decreasing)."""
    els, tb = title_block(ctx, s)
    head = len(els)
    cols = s.get("columns") or [{"blocks": s.get("blocks", [])}]
    cols = [c if isinstance(c, dict) else {"blocks": c} for c in cols][:4]
    # without a takeaway pill or source line the page has room down to the footer row
    y1 = CONTENT_B if (s.get("takeaway") or s.get("source") or s.get("footnote")) else 6.5
    y0 = max(CONTENT_Y, tb + 0.3)
    x0, w_all = MX, CW
    img = _img_file(ctx, s.get("image"))
    if img:
        ar = _img_ratio(img)
        ih = y1 - y0 - 0.4
        iw = min(CW * 0.40, ih * ar)
        ih = min(ih, iw / ar)
        cw_ = iw + 0.4
        els.append(card(ctx, MX, y0, cw_, ih + 0.4))
        im = IMG(img, MX + 0.2, y0 + 0.2, iw, ih)
        im["role"] = "diagram"
        els.append(im)
        x0 = MX + cw_ + 0.45
        w_all = CANVAS_W - MX - x0
    n = len(cols)
    boxed = s.get("boxed", n > 1)
    gap = 0.35
    colw = (w_all - gap * (n - 1)) / n
    pad = 0.3 if boxed else 0.0
    inner_w, inner_h = colw - 2 * pad, (y1 - y0) - 2 * pad
    gaps = 0.1
    def fit(c):
        for cand in (20, 18, 16, 14, 12):
            if sum(_block_h(b, cand, inner_w) + gaps for b in c.get("blocks", [])) <= inner_h + gaps:
                return cand
        return 12
    sizes = [fit(c) for c in cols]
    # columns may differ by one step at most, so neighbours still look like one page
    floor_ = min(sizes)
    sizes = [min(z, {12: 14, 14: 16, 16: 18, 18: 20, 20: 20}[floor_]) for z in sizes]
    # every formula on the page at one size, the smallest any of them needs
    fsizes = [_formula_size(b["formula"], sizes[i], inner_w) for i, c in enumerate(cols)
              for b in c.get("blocks", []) if "formula" in b]
    fsz = min(fsizes) if fsizes else None
    # builds: several columns come in one column at a time; a single column comes in by its
    # groups: a new group at each label or rule, and at text that follows a formula (the next
    # step of a derivation); formulas and notes ride along with the group before them
    k = -1
    prev = None
    for i, c in enumerate(cols):
        fs = sizes[i]
        cx = x0 + i * (colw + gap)
        blocks = c.get("blocks", [])
        if n > 1:
            step(i)
        if boxed:
            els.append(card(ctx, cx, y0, colw, y1 - y0))
        bx, by, bw = cx + pad, y0 + pad, inner_w
        for b in blocks:
            if n == 1 and (k < 0 or "label" in b or "rule" in b or ("text" in b and prev == "formula")):
                k += 1
                step(k)
            prev = next((t for t in ("label", "formula", "rule", "note") if t in b), "text")
            h = _block_h(b, fs, bw, fsz)
            if "label" in b:
                t = T(b["label"], bx, by, bw, h, fs, "label", True, valign="t")
                t["grp"] = f"ex_label{i}"
            elif "formula" in b:
                els.append(R(bx, by, bw, h, fill="tint", radius=min(0.12, ctx.S.shape.get("radius", 0.16) or 0.0) or None))
                t = T(b["formula"], bx + 0.2, by + 0.07, bw - 0.4, h - 0.14, fsz, "strong", False,
                      align="c", valign="m", ls=1.15)
            elif "rule" in b:
                col = TONES.get(b.get("tone"), b.get("tone") or "primary")
                dot = 0.16
                els.append(E(bx, by + (fs * 1.2 * LINE_PITCH / 72 - dot) / 2 + 0.02, dot, dot, col))
                t = T(b["rule"], bx + 0.32, by, bw - 0.32, h, fs, col if b.get("tone") else "text", True, ls=1.25)
                t["grp"] = f"ex_rule{i}"
            elif "note" in b:
                t = T(b["note"], bx, by, bw, h, max(11, fs * 0.85), "muted", ls=1.3)
                t["grp"] = f"ex_note{i}"
            else:
                t = T(b.get("text", ""), bx, by, bw, h, fs, "text", ls=1.35)
                t["grp"] = f"ex_text{i}"
            els.append(t)
            by += h + gaps
    step_end()
    if not boxed:
        # a short diagram-and-notes page sits in the middle of the free height, not at its top
        body = els[head:]
        bot = max(e["y"] + e["h"] for e in body)
        dy = (y1 - bot) / 2
        if dy > 0.3:
            for e in body:
                e["y"] += dy
    return els, {"master": "content"}


def free(s, ctx):
    """Claude supplies ready elements in the plan or deck slide 'elements' (13.333x7.5 canvas)."""
    els = ctx.p.get("elements") or s.get("elements") or []
    master = ctx.p.get("master") or s.get("master") or "content"
    return list(els), {"master": master, "empty": not els}


LAYOUTS = {
    "cover_hero": cover_hero,
    "statement_number": statement_number,
    "rows_side": rows_side,
    "stats_row": stats_row,
    "media_text": media_text,
    "side_cards": side_cards,
    "quote_cards": quote_cards,
    "statement_hero": statement_hero,
    "cards_quote": cards_quote,
    "list_icons": list_icons,
    "grid_cards": grid_cards,
    "steps_flow": steps_flow,
    "compare_split": compare_split,
    "cycle": cycle,
    "pyramid": pyramid,
    "section": section,
    "cover_type": cover_type,
    "cover_center": cover_center,
    "rank_grid": rank_grid,
    "question": question,
    "big_quote": big_quote,
    "toc": toc,
    "toc_row": toc_row,
    "timeline": timeline_layout,
    "funnel": funnel_layout,
    "hub": hub_layout,
    "matrix": matrix_layout,
    "table": table_layout,
    "chart": chart_layout,
    "framework": framework_layout,
    "closing": closing,
    "shot_notes": shot_notes,
    "shot_stack": shot_stack,
    "explain": explain,
    "free": free,
}

# page type -> preferred layouts (first = default)
TYPE_TO_LAYOUTS = {
    "cover": ["cover_hero", "cover_type", "cover_center"],
    "ranking": ["rank_grid"],
    "big_number": ["statement_number"],
    "definitions": ["rows_side", "list_icons"],
    "stats": ["stats_row"],
    "diagram_text": ["media_text"],
    "steps": ["side_cards", "list_icons"],
    "quotes": ["quote_cards", "list_icons"],
    "statement": ["statement_hero"],
    "warnings": ["cards_quote", "side_cards"],
    "side_cards": ["side_cards"],
    "list": ["list_icons", "grid_cards"],
    "grid": ["grid_cards", "list_icons"],
    "process": ["steps_flow", "list_icons"],
    "compare": ["compare_split"],
    "cycle": ["cycle"],
    "layers": ["pyramid"],
    "section": ["section"],
    "toc": ["toc", "toc_row"],
    "question": ["question"],
    "big_quote": ["big_quote"],
    "timeline": ["timeline"],
    "funnel": ["funnel"],
    "hub": ["hub"],
    "matrix": ["matrix"],
    "table": ["table"],
    "chart": ["chart"],
    "framework": ["framework"],
    "screenshot": ["shot_notes"],
    "screenshots": ["shot_stack"],
    "explain": ["explain"],
    "closing": ["closing"],
}

# which layouts have a big hero slot vs a small corner slot
HERO_SLOT = {
    "cover_hero": "large", "statement_number": "large", "statement_hero": "large",
    "rows_side": "side", "side_cards": "side", "cards_quote": "side", "closing": "top",
    "stats_row": "corner", "media_text": "corner", "quote_cards": "corner", "list_icons": "corner",
    "grid_cards": "corner", "steps_flow": "corner", "section": "large",
}


# ------------------------------------------------------------------ list markers
# layouts whose icons decorate a single number, callout or button rather than mark list items
MARKER_OFF = {"stats_row", "media_text", "quote_cards", "statement_hero", "statement_number", "closing",
              "cover_hero", "compare_split", "cards_quote", "shot_notes", "shot_stack", "explain"}


def apply_markers(els, ctx, layout=""):
    """Swap item icons for the style's list marker: dash (short accent bar), number (01, 02...)
    or none. Icons stay when decor.bullet is "icon" (the default). In MARKER_OFF layouts the
    icons are simply dropped, since a number next to a statistic reads as a ranking."""
    mode = ctx.S.decor.get("bullet", "icon")
    if mode == "icon":
        return els
    if layout in MARKER_OFF:
        mode = "none"
    icons = [e for e in els if e.get("t") == "icon" and e.get("role") not in ("chrome", "decor")]
    order = {id(e): k for k, e in enumerate(sorted(icons, key=lambda e: (round(e["y"], 1), e["x"])))}
    out = []
    for e in els:
        if id(e) not in order:
            out.append(e)
            continue
        s_ = e["size"]
        n0 = len(out)
        on_fill = e.get("bg") == "surface"  # icons sitting on a primary card use a surface disc
        if mode == "number":
            # the box grows to fit the digits (small icons used to squeeze 12pt numbers into 0.17in)
            num = f"{order[id(e)] + 1:02d}"
            fs = max(11, min(28, round(s_ * 72 * 0.55)))
            w = max(s_ * 1.2, text_width_pt(num, fs, True, DISPLAY_LATIN) / 72 + 0.08)
            h = max(s_, fs * 1.3 / 72)
            t = T(num, e["x"], e["y"] + (s_ - h) / 2, w, h, fs,
                  "on_primary" if on_fill else ("highlight" if fs >= 14 else "label"), True, "display", valign="m", ls=1.0)
            t["role"] = "marker"
            out.append(t)
        elif mode == "dash":
            out.append(R(e["x"], e["y"] + s_ / 2 - 0.035, min(0.34, s_ * 0.7), 0.07,
                         fill="on_primary" if on_fill else "primary", radius=0.035))
        # the marker comes in with the item it stands for
        for m in out[n0:]:
            if e.get("step") is not None:
                m["step"] = e["step"]
            else:
                m.pop("step", None)
    return out
