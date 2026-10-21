#!/usr/bin/env python3
"""Approximate slide previews drawn straight from out/layout_dump.json, no LibreOffice needed.

Usage:
  python render_lite.py WORK_DIR [--dpi 80] [--cols 3]

Writes out/png/slide-NN.png and out/sheet.png, the same files render.py makes, so the rest of
the pipeline (QA look-over, review, five-dimension self-check) works on machines without
LibreOffice. pipeline.py calls it automatically when render.py fails.

What it draws: backgrounds, cards, shapes, lines and arrows, icons, pictures, text with the
same wrapping the layouts measured with (so an overflow shows up here too), tables, and a
simplified version of each native chart. What it skips: rotation, gradients inside
PowerPoint itself, chart axes and fine typography. Treat it as a layout check, not as the
final look; the .pptx is unchanged.
"""
import argparse
import math
import os
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (load_json, load_style, wrap_lines, get_font, hex_to_rgb, mix, CANVAS_W, CANVAS_H,  # noqa: E402
                    LINE_PITCH)

SS = 2  # supersampling: draw at 2x, shrink at the end for smooth edges

SERIF_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/google-noto-cjk/NotoSerifCJK-Regular.ttc",
    "C:/Windows/Fonts/simsun.ttc",
    "C:/Windows/Fonts/STZHONGS.TTF",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/Library/Fonts/Songti.ttc",
]
SERIF_BOLD_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
    "/usr/share/fonts/noto-cjk/NotoSerifCJK-Bold.ttc",
    "/usr/share/fonts/google-noto-cjk/NotoSerifCJK-Bold.ttc",
]
_serif_cache = {}


def serif_font(px, bold):
    key = (int(px), bold)
    if key in _serif_cache:
        return _serif_cache[key]
    f = None
    for c in (SERIF_BOLD_CANDIDATES if bold else []) + SERIF_CANDIDATES:
        if os.path.exists(c):
            try:
                f = ImageFont.truetype(c, int(px))
                break
            except Exception:
                pass
    _serif_cache[key] = f or get_font(px, bold)
    return _serif_cache[key]


def is_serif(name):
    return bool(name) and bool(re.search(r"Serif|宋|Song|Georgia|Times|明朝|Mincho", str(name), re.I))


class Painter:
    def __init__(self, style, work, dpi):
        self.S = style
        self.work = Path(work)
        self.px = dpi * SS  # pixels per inch on the working canvas
        self.W, self.H = round(CANVAS_W * self.px), round(CANVAS_H * self.px)

    # ---------------------------------------------------------- helpers
    def P(self, v):
        return v * self.px

    def rgba(self, token, alpha=1.0):
        r, g, b = hex_to_rgb(self.S.c(token))
        return (r, g, b, int(255 * max(0.0, min(1.0, alpha if alpha is not None else 1.0))))

    def path(self, p):
        if not p:
            return None
        q = Path(p)
        if q.exists():
            return q
        if (self.work / p).exists():
            return self.work / p
        return None

    def layer(self):
        return Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))

    def over(self, im, lay):
        im.alpha_composite(lay)

    # ---------------------------------------------------------- shapes
    def _shape(self, d, e, box, fill, line, lw, oval=False):
        x0, y0, x1, y1 = box
        kind = e.get("shape")
        if oval:
            d.ellipse(box, fill=fill, outline=line, width=lw)
        elif kind == "diamond":
            pts = [((x0 + x1) / 2, y0), (x1, (y0 + y1) / 2), ((x0 + x1) / 2, y1), (x0, (y0 + y1) / 2)]
            d.polygon(pts, fill=fill, outline=line, width=lw)
        elif kind == "hexagon":
            q = (x1 - x0) * 0.25
            pts = [(x0 + q, y0), (x1 - q, y0), (x1, (y0 + y1) / 2), (x1 - q, y1), (x0 + q, y1), (x0, (y0 + y1) / 2)]
            d.polygon(pts, fill=fill, outline=line, width=lw)
        elif kind == "triangle":
            d.polygon([((x0 + x1) / 2, y0), (x1, y1), (x0, y1)], fill=fill, outline=line, width=lw)
        elif kind == "parallelogram":
            q = (x1 - x0) * 0.2
            d.polygon([(x0 + q, y0), (x1, y0), (x1 - q, y1), (x0, y1)], fill=fill, outline=line, width=lw)
        elif kind == "half_circle":
            d.chord([x0, y0, x1, y1 + (y1 - y0)], 180, 360, fill=fill, outline=line, width=lw)
        elif e.get("radius"):
            r = min(self.P(e["radius"]), (x1 - x0) / 2, (y1 - y0) / 2)
            d.rounded_rectangle(box, r, fill=fill, outline=line, width=lw)
        else:
            d.rectangle(box, fill=fill, outline=line, width=lw)

    def rect(self, im, e, oval=False):
        box = [self.P(e["x"]), self.P(e["y"]), self.P(e["x"] + e["w"]), self.P(e["y"] + e["h"])]
        if box[2] - box[0] < 1 or box[3] - box[1] < 1:
            return
        fill = self.rgba(e["fill"], e.get("alpha", 1.0)) if e.get("fill") else None
        line = self.rgba(e["line"]) if e.get("line") else None
        lw = max(1, round(self.P(e.get("line_w", 0.75) / 72))) if line else 0
        if e.get("shadow") and self.S.depth not in ("flat", "ring") and fill:
            soft = e["shadow"] == "soft" or self.S.depth == "whisper"
            sh = self.layer()
            sd = ImageDraw.Draw(sh)
            off = self.P(0.028 if soft else 0.042)
            sbox = [box[0], box[1] + off, box[2], box[3] + off]
            self._shape(sd, e, sbox, self.rgba("primary_dark", 0.10 if soft else 0.22), None, 0, oval)
            sh = sh.filter(ImageFilter.GaussianBlur(self.P(0.12 if soft else 0.06)))
            self.over(im, sh)
        lay = self.layer()
        self._shape(ImageDraw.Draw(lay), e, box, fill, line, lw, oval)
        self.over(im, lay)

    def line(self, im, e):
        lay = self.layer()
        d = ImageDraw.Draw(lay)
        col = self.rgba(e.get("color", "line"))
        w = max(1, round(self.P(e.get("lw", 1.5) / 72)))
        x1, y1, x2, y2 = (self.P(e[k]) for k in ("x1", "y1", "x2", "y2"))
        if e.get("dash"):
            L = math.hypot(x2 - x1, y2 - y1) or 1
            step, on = w * 6, w * 3.5
            t = 0
            while t < L:
                a, b = t / L, min(L, t + on) / L
                d.line([(x1 + (x2 - x1) * a, y1 + (y2 - y1) * a), (x1 + (x2 - x1) * b, y1 + (y2 - y1) * b)], fill=col, width=w)
                t += step
        else:
            d.line([(x1, y1), (x2, y2)], fill=col, width=w)
        if e.get("arrow"):
            ang = math.atan2(y2 - y1, x2 - x1)
            s = w * 4
            pts = [(x2, y2), (x2 - s * math.cos(ang - 0.45), y2 - s * math.sin(ang - 0.45)),
                   (x2 - s * math.cos(ang + 0.45), y2 - s * math.sin(ang + 0.45))]
            d.polygon(pts, fill=col)
        self.over(im, lay)

    def picture(self, im, e):
        p = self.path(e.get("path"))
        if not p:
            return
        try:
            src = Image.open(p).convert("RGBA")
        except Exception:
            return
        x, y, w, h = e["x"], e["y"], e["w"], e["h"]
        if e.get("fit", "contain") == "contain":
            ar = src.width / max(1, src.height)
            if w / h > ar:
                nw = h * ar
                x += (w - nw) / 2 if e.get("align", "center") == "center" else 0
                w = nw
            else:
                nh = w / ar
                y += (h - nh) / 2
                h = nh
        size = (max(1, round(self.P(w))), max(1, round(self.P(h))))
        pic = src.resize(size, Image.LANCZOS)
        lay = self.layer()
        lay.paste(pic, (round(self.P(x)), round(self.P(y))))
        self.over(im, lay)

    def icon(self, im, e):
        from fallback_art import tinted_icon
        s = e["size"]
        pad = 0
        if e.get("bg"):
            self.rect(im, {"x": e["x"], "y": e["y"], "w": s, "h": s, "fill": e["bg"], "alpha": e.get("bg_alpha", 1.0),
                           "radius": None if e.get("circle", True) else s * 0.28}, oval=e.get("circle", True))
            pad = s * e.get("pad", 0.24)
        ic = tinted_icon(e["name"], self.S.c(e.get("color", "primary")), 256) or tinted_icon("sparkles", self.S.c("primary"), 256)
        if ic is None:
            return
        px = max(1, round(self.P(s - 2 * pad)))
        ic = ic.resize((px, px), Image.LANCZOS)
        lay = self.layer()
        lay.paste(ic, (round(self.P(e["x"] + pad)), round(self.P(e["y"] + pad))))
        self.over(im, lay)

    # ---------------------------------------------------------- text
    def _font(self, e, size_pt, bold):
        role = e.get("font", "body")
        fonts = self.S.fonts
        face = fonts["heading_ea"] if role in ("heading", "display") else fonts["body_ea"]
        px = size_pt / 72 * self.px
        if is_serif(face):
            return serif_font(px, bold)
        return get_font(px, bold)

    def _emph_mask(self, text):
        """Stripped text plus a per-character flag for **emphasis** spans."""
        out, flags = [], []
        for seg in re.split(r"(\*\*.+?\*\*)", text):
            if not seg:
                continue
            emph = seg.startswith("**") and seg.endswith("**") and len(seg) > 4
            body = seg[2:-2] if emph else seg
            out.append(body)
            flags += [emph] * len(body)
        return "".join(out), flags

    def text(self, im, e, draw):
        size = e["size"]
        bold = e.get("bold", False)
        color = e.get("color", "text")
        on_dark = color in ("on_primary",) or str(color).startswith("primary@")
        emph_color = color if (on_dark or bold) else self.S.data.get("emphasis_color", "primary_dark")
        if bold and not on_dark and e.get("font") in ("heading", "display"):
            emph_color = self.S.data.get("title_emphasis_color", "highlight")
        base_rgba, emph_rgba = self.rgba(color), self.rgba(emph_color)
        plain, flags = self._emph_mask(str(e["text"]))
        lines = wrap_lines(str(e["text"]), size, e["w"] * 72 * 0.98, bold)
        step = size * e.get("ls", 1.2) * LINE_PITCH / 72 * self.px
        total = step * len(lines)
        box_h = self.P(e["h"])
        va = e.get("valign", "t")
        y = self.P(e["y"]) + (0 if va == "t" else (box_h - total) / 2 if va == "m" else box_h - total)
        spc = (e.get("spc") or 0) / 72 * self.px
        f_reg = self._font(e, size, bold)
        f_emp = self._font(e, size, True)
        cur = 0
        for ln in lines:
            # find this line in the stripped text so emphasis flags line up
            k = plain.find(ln, cur) if ln else cur
            k = cur if k < 0 else k
            fl = flags[k:k + len(ln)] if flags else [False] * len(ln)
            cur = k + len(ln)
            runs, buf, bf = [], "", None
            for ch, f_ in zip(ln, fl + [False] * (len(ln) - len(fl))):
                if bf is None or f_ == bf:
                    buf += ch
                    bf = f_ if bf is None else bf
                else:
                    runs.append((buf, bf))
                    buf, bf = ch, f_
            if buf:
                runs.append((buf, bf))
            width = sum(self._run_w(r, f_emp if em else f_reg, spc) for r, em in runs)
            x0 = self.P(e["x"])
            al = e.get("align", "l")
            if al == "c":
                x0 += (self.P(e["w"]) - width) / 2
            elif al == "r":
                x0 += self.P(e["w"]) - width
            # glyphs sit a little below the top of their line box
            yy = y + (step - size / 72 * self.px) / 2
            for r, em in runs:
                f = f_emp if em else f_reg
                col = emph_rgba if em else base_rgba
                if spc:
                    for ch in r:
                        draw.text((x0, yy), ch, font=f, fill=col)
                        x0 += f.getlength(ch) + spc
                else:
                    draw.text((x0, yy), r, font=f, fill=col)
                    x0 += f.getlength(r)
            y += step

    @staticmethod
    def _run_w(r, f, spc):
        return f.getlength(r) + spc * len(r)

    def text_el(self, im, e):
        lay = self.layer()
        self.text(lay, e, ImageDraw.Draw(lay))
        self.over(im, lay)

    # ---------------------------------------------------------- table and chart
    def table(self, im, e):
        cols = len(e["columns"])
        rows = [e["columns"]] + e["rows"]
        widths = e.get("col_widths") or [1] * cols
        tot = sum(widths)
        rh = e["h"] / len(rows)
        hl = e.get("highlight_col")
        y = e["y"]
        for r, row in enumerate(rows):
            x = e["x"]
            for c in range(cols):
                cw = e["w"] * widths[c] / tot
                fill = "primary" if r == 0 else ("tint" if hl == c else ("surface" if r % 2 else "bg_bottom"))
                self.rect(im, {"x": x, "y": y, "w": cw, "h": rh, "fill": fill, "line": "line", "line_w": 0.75})
                val = row[c] if c < len(row) else ""
                te = {"x": x + 0.1, "y": y, "w": cw - 0.2, "h": rh, "text": str(val),
                      "size": e["head_size"] if r == 0 else e["size"],
                      "color": "on_primary" if r == 0 else ("strong" if c == 0 else "text"),
                      "bold": r == 0 or c == 0 or hl == c, "align": "l" if c == 0 else "c", "valign": "m"}
                self.text_el(im, te)
                x += cw
            y += rh

    def chart(self, im, e):
        spec = e["chart"]
        kind = spec.get("type", "column")
        cats = [str(c) for c in spec.get("categories", [])]
        series = spec.get("series", [])
        hl = spec.get("highlight")
        size = e.get("size", 12)
        x, y, w, h = e["x"], e["y"], e["w"], e["h"]
        cols = ["primary", "accent", "primary@0.45", "muted", "primary_dark", "accent@0.5"]
        if not cats or not series:
            return
        if kind in ("pie", "doughnut"):
            vals = [max(0, float(v)) for v in series[0]["values"]]
            tot = sum(vals) or 1
            d = min(w * 0.55, h - 0.2)
            cx, cy = x + d / 2 + 0.2, y + h / 2
            lay = self.layer()
            dr = ImageDraw.Draw(lay)
            a = -90
            n = len(vals)
            labels = []
            for i, v in enumerate(vals):
                sweep = 360 * v / tot
                mid = math.radians(a + sweep / 2)
                rr = d * (0.39 if kind == "doughnut" else 0.3)
                labels.append((cx + rr * math.cos(mid), cy + rr * math.sin(mid), f"{round(100 * v / tot)}%"))
                col = self.rgba("accent") if hl == i else self.rgba(cols[0]) if i == 0 else \
                    tuple(list(hex_to_rgb(mix(self.S.c("primary"), "FFFFFF", 0.2 + 0.6 * i / max(1, n - 1)))) + [255])
                dr.pieslice([self.P(cx - d / 2), self.P(cy - d / 2), self.P(cx + d / 2), self.P(cy + d / 2)], a, a + sweep,
                            fill=col, outline=self.rgba("surface"), width=max(1, round(self.P(0.02))))
                a += sweep
            if kind == "doughnut":
                r2 = d * 0.28
                dr.ellipse([self.P(cx - r2), self.P(cy - r2), self.P(cx + r2), self.P(cy + r2)], fill=self.rgba("surface"))
            self.over(im, lay)
            for i, (tx_, ty_, txt) in enumerate(labels):
                if vals[i] / tot >= 0.05:
                    self.text_el(im, {"x": tx_ - 0.4, "y": ty_ - 0.15, "w": 0.8, "h": 0.3, "text": txt, "size": size,
                                      "color": "text", "bold": True, "align": "c", "valign": "m"})
            lx = cx + d / 2 + 0.3
            for i, c in enumerate(cats):
                ly = y + 0.2 + i * 0.36
                sw_ = "accent" if hl == i else ("primary" if i == 0 else
                                                  mix(self.S.c("primary"), "FFFFFF", 0.2 + 0.6 * i / max(1, n - 1)))
                self.rect(im, {"x": lx, "y": ly + 0.08, "w": 0.18, "h": 0.18, "fill": sw_})
                self.text_el(im, {"x": lx + 0.28, "y": ly, "w": x + w - lx - 0.3, "h": 0.34,
                                  "text": f"{c}  {series[0]['values'][i]}", "size": size, "color": "muted", "valign": "m"})
            return
        allv = [float(v) for s in series for v in s["values"]]
        stacked = kind == "stacked"
        vmax = max([sum(float(s["values"][i]) for s in series) for i in range(len(cats))] if stacked else allv + [0]) or 1
        lab_h = 0.4
        top = y + (0.35 if len(series) > 1 else 0.1)
        base = y + h - lab_h
        ph = base - top
        n = len(cats)
        slot = w / n
        if kind == "bar":
            slot_h = ph / n
            for i, c in enumerate(cats):
                v = float(series[0]["values"][i])
                bw = (w - 1.6) * v / vmax
                yy = top + i * slot_h + slot_h * 0.2
                self.text_el(im, {"x": x, "y": yy, "w": 1.4, "h": slot_h * 0.6, "text": c, "size": size,
                                  "color": "muted", "align": "r", "valign": "m"})
                self.rect(im, {"x": x + 1.5, "y": yy, "w": max(0.02, bw), "h": slot_h * 0.6,
                               "fill": ("primary" if hl == i else "primary@0.45") if hl is not None else "primary"})
                self.text_el(im, {"x": x + 1.55 + bw, "y": yy, "w": 1.0, "h": slot_h * 0.6, "text": str(series[0]["values"][i]),
                                  "size": size, "color": "text", "valign": "m"})
            return
        if kind == "line":
            for si, s in enumerate(series):
                pts = [(x + slot * (i + 0.5), base - ph * float(v) / vmax) for i, v in enumerate(s["values"])]
                for a_, b_ in zip(pts, pts[1:]):
                    self.line(im, {"x1": a_[0], "y1": a_[1], "x2": b_[0], "y2": b_[1], "color": cols[si % len(cols)], "lw": 2.5})
                for px_, py_ in pts:
                    self.rect(im, {"x": px_ - 0.06, "y": py_ - 0.06, "w": 0.12, "h": 0.12, "fill": cols[si % len(cols)]}, oval=True)
                if pts:
                    lx_, ly_ = pts[-1]
                    self.text_el(im, {"x": lx_ + 0.1, "y": ly_ - 0.16, "w": 0.9, "h": 0.32, "text": str(s["values"][-1]),
                                      "size": size, "color": cols[si % len(cols)], "bold": True, "valign": "m"})
        else:
            ns = 1 if stacked else len(series)
            bw = slot * 0.6 / ns
            for i in range(n):
                acc = 0.0
                for si, s in enumerate(series):
                    v = float(s["values"][i])
                    bh = ph * v / vmax
                    bx = x + slot * i + slot * 0.2 + (0 if stacked else si * bw)
                    by = base - bh - (acc if stacked else 0)
                    if hl is not None and len(series) == 1:
                        fill = "primary" if hl == i else "primary@0.45"
                    else:
                        fill = cols[si % len(cols)]
                    self.rect(im, {"x": bx, "y": by, "w": bw, "h": max(0.01, bh), "fill": fill})
                    if not stacked:
                        self.text_el(im, {"x": bx - 0.2, "y": by - 0.3, "w": bw + 0.4, "h": 0.28, "text": str(s["values"][i]),
                                          "size": size, "color": "text", "align": "c", "valign": "b"})
                    acc += bh if stacked else 0
        self.line(im, {"x1": x, "y1": base, "x2": x + w, "y2": base, "color": "line", "lw": 1})
        for i, c in enumerate(cats):
            self.text_el(im, {"x": x + slot * i, "y": base + 0.05, "w": slot, "h": lab_h - 0.05, "text": c, "size": size,
                              "color": "muted", "align": "c", "valign": "t"})
        if len(series) > 1:
            lx = x
            for si, s in enumerate(series):
                self.rect(im, {"x": lx, "y": y + 0.08, "w": 0.18, "h": 0.18, "fill": cols[si % len(cols)]})
                self.text_el(im, {"x": lx + 0.25, "y": y, "w": 2.0, "h": 0.34, "text": s.get("name", ""), "size": size,
                                  "color": "muted", "valign": "m"})
                lx += 2.3

    # ---------------------------------------------------------- slide
    def slide(self, sd):
        im = Image.new("RGBA", (self.W, self.H), self.rgba("bg_bottom"))
        for e in sd["elements"]:
            t = e["t"]
            try:
                if t == "image":
                    self.picture(im, e)
                elif t == "rect":
                    self.rect(im, e)
                elif t == "ellipse":
                    self.rect(im, e, oval=True)
                elif t == "line":
                    self.line(im, e)
                elif t == "icon":
                    self.icon(im, e)
                elif t == "text":
                    self.text_el(im, e)
                elif t == "table":
                    self.table(im, e)
                elif t == "chart":
                    self.chart(im, e)
            except Exception as ex:  # one odd element should not cost the whole preview
                print(f"  slide {sd['n']}: skipped {t} ({ex})")
        return im.convert("RGB").resize((self.W // SS, self.H // SS), Image.LANCZOS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("--dpi", type=int, default=80)
    ap.add_argument("--cols", type=int, default=3)
    ap.add_argument("--pages", help="draw only these pages (e.g. 3,7) and keep the other previews; no contact sheet")
    a = ap.parse_args()
    work = Path(a.work).resolve()
    dump = load_json(work / "out" / "layout_dump.json")
    style = load_style(work / "style.json")
    out = work / "out" / "png"
    out.mkdir(parents=True, exist_ok=True)
    total = len(dump["slides"])
    only = {int(x) for x in a.pages.split(",") if x.strip()} if a.pages else None
    for f in out.glob("slide-*.png"):
        n = int(f.stem.split("-")[1]) if f.stem.split("-")[1].isdigit() else 0
        if only is None or n in only or n > total:  # pages past the end belong to a longer old deck
            f.unlink()
    # pictures in the dump are relative to the work dir
    cwd = os.getcwd()
    os.chdir(work)
    try:
        p = Painter(style, work, a.dpi)
        files = []
        for i, sd in enumerate(dump["slides"], 1):
            if only is not None and i not in only:
                continue
            f = out / f"slide-{i:02d}.png"
            p.slide(sd).save(f)
            files.append(f)
            print(f)
    finally:
        os.chdir(cwd)
    if only is not None:
        print("NOTE 只画了指定的页，其余页的预览图保留原样，没有拼总览图")
        return
    from render import contact_sheet
    contact_sheet(files, work / "out" / "sheet.png", a.cols)
    print("sheet:", work / "out" / "sheet.png")
    print("NOTE 这是不经过 LibreOffice 的近似预览：排版、颜色、溢出都看得出来，图表是简化画法，字体细节以 PowerPoint 为准")


if __name__ == "__main__":
    main()
