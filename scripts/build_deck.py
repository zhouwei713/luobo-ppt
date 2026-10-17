#!/usr/bin/env python3
"""Step 5: assemble the beautified deck.

Usage:
  python build_deck.py WORK_DIR [--out WORK_DIR/out/beautified.pptx] [--only 2,5]

Reads WORK_DIR/deck.json, style.json, plan.json, assets/manifest.json.
All text stays editable text boxes; cards, pills and dividers are native shapes;
only backgrounds, illustrations, icons and brush strokes are pictures.
Also writes out/layout_dump.json (every element) for qa_check.py.
"""
import argparse
import copy
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_json, save_json, load_style, CANVAS_W, CANVAS_H, text_width_pt, mix  # noqa: E402
import layouts as L  # noqa: E402
import animate as A  # noqa: E402
from chartcheck import spec_label_format  # noqa: E402

from pptx import Presentation  # noqa: E402
from pptx.util import Inches, Pt, Emu  # noqa: E402
from pptx.dml.color import RGBColor  # noqa: E402
from pptx.enum.shapes import MSO_SHAPE  # noqa: E402
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR, MSO_AUTO_SIZE  # noqa: E402
from pptx.oxml.ns import qn  # noqa: E402
from lxml import etree  # noqa: E402

ALIGN = {"l": PP_ALIGN.LEFT, "c": PP_ALIGN.CENTER, "r": PP_ALIGN.RIGHT}
VALIGN = {"t": MSO_ANCHOR.TOP, "m": MSO_ANCHOR.MIDDLE, "b": MSO_ANCHOR.BOTTOM}


class Builder:
    def __init__(self, work, style, meta, assets, slide_w_in, slide_h_in):
        self.work = Path(work)
        self.S = style
        self.meta = meta
        self.assets = assets
        self.k = slide_w_in / CANVAS_W
        self.icon_cache = self.work / "assets" / "_icons"
        self.icon_cache.mkdir(parents=True, exist_ok=True)
        self.warnings = []

    # ---------------------------------------------------------- units
    def E(self, v):
        return Emu(int(round(v * self.k * 914400)))

    def pt(self, v):
        return Pt(round(v * self.k * 2) / 2)

    # ---------------------------------------------------------- xml helpers
    @staticmethod
    def _strip_style(shape):
        st = shape._element.find(qn("p:style"))
        if st is not None:
            shape._element.remove(st)

    def _alpha(self, shape, alpha):
        if alpha is None or alpha >= 0.999:
            return
        sf = shape.fill._xPr.find(qn("a:solidFill"))
        if sf is not None and len(sf):
            clr = sf[0]
            a = etree.SubElement(clr, qn("a:alpha"))
            a.set("val", str(int(alpha * 100000)))

    def _shadow(self, shape, soft=False):
        spPr = shape._element.spPr
        eff = etree.SubElement(spPr, qn("a:effectLst"))
        sh = etree.SubElement(eff, qn("a:outerShdw"))
        sh.set("blurRad", str(int((304800 if soft else 152400) * self.k)))
        sh.set("dist", str(int((25400 if soft else 38100) * self.k)))
        sh.set("dir", "5400000")
        sh.set("algn", "t")
        sh.set("rotWithShape", "0")
        clr = etree.SubElement(sh, qn("a:srgbClr"))
        clr.set("val", self.S.c("primary_dark"))
        a = etree.SubElement(clr, qn("a:alpha"))
        a.set("val", "7000" if soft else "16000")

    def _font(self, run, role, size, bold, color, serif=False):
        f = run.font
        f.size = self.pt(size)
        f.bold = bool(bold)
        f.color.rgb = RGBColor.from_string(self.S.c(color))
        fonts = self.S.fonts
        latin = fonts.get(f"{role}_latin") or fonts["body_latin"]
        ea = fonts["heading_ea"] if role in ("heading", "display") else fonts["body_ea"]
        if serif:  # emphasis run switched to the serif family (decor.emphasis = "serif")
            ea = self.S.data.get("fonts", {}).get("serif_ea", "Source Han Serif SC")
            latin = self.S.data.get("fonts", {}).get("serif_latin", "Georgia")
        f.name = latin
        rPr = run._r.get_or_add_rPr()
        latin_el = rPr.find(qn("a:latin"))
        for tag, face in (("a:ea", ea), ("a:cs", latin)):
            el = rPr.find(qn(tag))
            if el is None:
                el = etree.Element(qn(tag))
                latin_el.addnext(el) if tag == "a:ea" else rPr.find(qn("a:ea")).addnext(el)
            el.set("typeface", face)

    # ---------------------------------------------------------- element renderers
    def text(self, slide, e):
        tb = slide.shapes.add_textbox(self.E(e["x"]), self.E(e["y"]), self.E(e["w"]), self.E(e["h"]))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.auto_size = MSO_AUTO_SIZE.NONE
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        tf.vertical_anchor = VALIGN.get(e.get("valign", "t"), MSO_ANCHOR.TOP)
        paras = str(e["text"]).split("\n")
        base_bold = e.get("bold", False)
        color = e.get("color", "text")
        on_dark = color in ("on_primary",) or str(color).startswith("primary@")
        emph_color = color if (on_dark or base_bold) else self.S.data.get("emphasis_color", "primary_dark")
        if base_bold and not on_dark and e.get("font") in ("heading", "display"):
            # a **word** inside a headline: the one coloured word of the title
            emph_color = self.S.data.get("title_emphasis_color", "highlight")
        for i, ptxt in enumerate(paras):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = ALIGN.get(e.get("align", "l"), PP_ALIGN.LEFT)
            p.line_spacing = e.get("ls", 1.2)
            segs = re.split(r"(\*\*.+?\*\*)", ptxt)
            for seg in segs:
                if not seg:
                    continue
                emph = seg.startswith("**") and seg.endswith("**") and len(seg) > 4
                for r in self._add_runs(p, seg[2:-2] if emph else seg):
                    self._font(r, e.get("font", "body"), e["size"], True if emph else base_bold,
                               emph_color if emph else color,
                               serif=emph and self.S.decor.get("emphasis") == "serif" and e.get("font") in ("heading", "display"))
                    if e.get("spc"):
                        r._r.get_or_add_rPr().set("spc", str(int(e["spc"] * 100)))
            self._sync_breaks(p)
        return tb

    def rect(self, slide, e, oval=False):
        shapes = {"diamond": MSO_SHAPE.DIAMOND, "hexagon": MSO_SHAPE.HEXAGON, "triangle": MSO_SHAPE.ISOSCELES_TRIANGLE,
                  "half_circle": MSO_SHAPE.CHORD, "parallelogram": MSO_SHAPE.PARALLELOGRAM}
        if oval:
            kind = MSO_SHAPE.OVAL
        elif e.get("shape") in shapes:
            kind = shapes[e["shape"]]
        else:
            kind = MSO_SHAPE.ROUNDED_RECTANGLE if e.get("radius") else MSO_SHAPE.RECTANGLE
        shp = slide.shapes.add_shape(kind, self.E(e["x"]), self.E(e["y"]), self.E(e["w"]), self.E(e["h"]))
        self._strip_style(shp)
        if e.get("rot"):
            shp.rotation = e["rot"]
        if not oval and e.get("radius") and not e.get("shape"):
            shp.adjustments[0] = max(0.0, min(0.5, e["radius"] / max(0.01, min(e["w"], e["h"]))))
        if e.get("fill"):
            shp.fill.solid()
            shp.fill.fore_color.rgb = RGBColor.from_string(self.S.c(e["fill"]))
            self._alpha(shp, e.get("alpha", 1.0))
        else:
            shp.fill.background()
        if e.get("line"):
            shp.line.color.rgb = RGBColor.from_string(self.S.c(e["line"]))
            shp.line.width = self.pt(e.get("line_w", 0.75))
        else:
            shp.line.fill.background()
        if e.get("shadow") and self.S.depth not in ("flat", "ring"):
            self._shadow(shp, soft=(e["shadow"] == "soft" or self.S.depth == "whisper"))
        return shp

    def image(self, slide, e):
        from PIL import Image
        path = e.get("path")
        if not path or not Path(path).exists():
            self.warnings.append(f"missing image {path}")
            return None
        x, y, w, h = e["x"], e["y"], e["w"], e["h"]
        if e.get("fit", "contain") == "contain":
            with Image.open(path) as im:
                iw, ih = im.size
            ar = iw / ih
            if w / h > ar:
                nw = h * ar
                x += (w - nw) / 2 if e.get("align", "center") == "center" else 0
                w = nw
            else:
                nh = w / ar
                y += (h - nh) / 2
                h = nh
            e.update(rx=x, ry=y, rw=w, rh=h)
        return slide.shapes.add_picture(str(path), self.E(x), self.E(y), self.E(w), self.E(h))

    def icon(self, slide, e):
        from fallback_art import tinted_icon
        name = e["name"]
        col = self.S.c(e.get("color", "primary"))
        cache = self.icon_cache / f"{name}_{col}.png"
        if not cache.exists():
            im = tinted_icon(name, col, 256)
            if im is None:
                self.warnings.append(f"unknown icon '{name}', used 'sparkles'")
                im = tinted_icon("sparkles", col, 256)
            im.save(cache)
        s = e["size"]
        if e.get("bg"):
            be = {"x": e["x"], "y": e["y"], "w": s, "h": s, "fill": e["bg"], "alpha": e.get("bg_alpha", 1.0),
                  "radius": None if e.get("circle", True) else s * 0.28}
            self.rect(slide, be, oval=e.get("circle", True))
            pad = s * e.get("pad", 0.24)
        else:
            pad = 0
        slide.shapes.add_picture(str(cache), self.E(e["x"] + pad), self.E(e["y"] + pad),
                                 self.E(s - 2 * pad), self.E(s - 2 * pad))

    def line(self, slide, e):
        from pptx.enum.shapes import MSO_CONNECTOR
        c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, self.E(e["x1"]), self.E(e["y1"]),
                                       self.E(e["x2"]), self.E(e["y2"]))
        self._strip_style(c)
        c.line.color.rgb = RGBColor.from_string(self.S.c(e.get("color", "line")))
        c.line.width = self.pt(e.get("lw", 1.5))
        if e.get("dash"):
            from pptx.enum.dml import MSO_LINE_DASH_STYLE
            c.line.dash_style = MSO_LINE_DASH_STYLE.DASH
        if e.get("arrow"):
            ln = c.line._get_or_add_ln()
            tail = etree.SubElement(ln, qn("a:tailEnd"))
            tail.set("type", "triangle")
            tail.set("w", "med")
            tail.set("len", "med")
        return c

    @staticmethod
    def _add_runs(p, text):
        """Add text to paragraph p as runs; each "\v" becomes a soft line break (<a:br>)."""
        runs = []
        for i, part in enumerate(text.split("\v")):
            if i:
                p.add_line_break()
            if part:
                r = p.add_run()
                r.text = part
                runs.append(r)
        return runs

    @staticmethod
    def _sync_breaks(p):
        """Give each <a:br> the run properties of the run before it, so the line keeps its height."""
        prev = None
        for child in p._p:
            if child.tag == qn("a:r"):
                prev = child.find(qn("a:rPr"))
            elif child.tag == qn("a:br") and prev is not None:
                for old in child.findall(qn("a:rPr")):
                    child.remove(old)
                child.insert(0, copy.deepcopy(prev))

    def _cell_text(self, cell, text, size, color, bold, align="l"):
        tf = cell.text_frame
        tf.word_wrap = True
        cell.margin_left = cell.margin_right = self.E(0.1)
        cell.margin_top = cell.margin_bottom = self.E(0.05)
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]
        p.alignment = ALIGN.get(align, PP_ALIGN.LEFT)
        for seg in re.split(r"(\*\*.+?\*\*)", str(text)):
            if not seg:
                continue
            emph = seg.startswith("**") and seg.endswith("**") and len(seg) > 4
            for r in self._add_runs(p, seg[2:-2] if emph else seg):
                self._font(r, "body", size, bold or emph, color)
        self._sync_breaks(p)

    def table(self, slide, e):
        rows, cols = len(e["rows"]) + 1, len(e["columns"])
        gf = slide.shapes.add_table(rows, cols, self.E(e["x"]), self.E(e["y"]), self.E(e["w"]), self.E(e["h"]))
        tbl = gf.table
        # drop the built-in table style so only our colours show
        tblPr = tbl._tbl.tblPr
        for attr in ("bandRow", "firstRow"):
            tblPr.set(attr, "0")
        sid = tblPr.find(qn("a:tableStyleId"))
        if sid is not None:
            sid.text = "{5940675A-B579-460E-94D1-54222C63F5DA}"  # "No Style, Table Grid"
        widths = e.get("col_widths") or [1] * cols
        tot = sum(widths)
        for i, wv in enumerate(widths):
            tbl.columns[i].width = self.E(e["w"] * wv / tot)
        rh = e["h"] / rows
        for r in range(rows):
            tbl.rows[r].height = self.E(rh)
        hl = e.get("highlight_col")
        for c, name in enumerate(e["columns"]):
            cell = tbl.cell(0, c)
            cell.fill.solid()
            cell.fill.fore_color.rgb = RGBColor.from_string(self.S.c("primary"))
            self._cell_text(cell, name, e["head_size"], "on_primary", True, "c" if c else "l")
        for r, row in enumerate(e["rows"], 1):
            for c in range(cols):
                cell = tbl.cell(r, c)
                cell.fill.solid()
                if hl is not None and c == hl:
                    fill = "tint"
                else:
                    fill = "surface" if r % 2 else "bg_bottom"
                cell.fill.fore_color.rgb = RGBColor.from_string(self.S.c(fill))
                val = row[c] if c < len(row) else ""
                self._cell_text(cell, val, e["size"], "strong" if c == 0 else "text", c == 0 or (hl == c),
                                "l" if c == 0 else "c")
        # thin borders in the line colour
        for r in range(rows):
            for c in range(cols):
                tcPr = tbl.cell(r, c)._tc.get_or_add_tcPr()
                for tag in ("a:lnL", "a:lnR", "a:lnT", "a:lnB"):
                    ln = etree.SubElement(tcPr, qn(tag))
                    ln.set("w", str(int(9525 * self.k)))
                    sf = etree.SubElement(ln, qn("a:solidFill"))
                    clr = etree.SubElement(sf, qn("a:srgbClr"))
                    clr.set("val", self.S.c("line"))
                # schema order: borders must come before the fill
                fill = tcPr.find(qn("a:solidFill"))
                if fill is not None:
                    tcPr.remove(fill)
                    tcPr.append(fill)
        return gf

    def chart(self, slide, e):
        from pptx.chart.data import CategoryChartData
        from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION, XL_LABEL_POSITION
        spec = e["chart"]
        kind = spec.get("type", "column")
        types = {"column": XL_CHART_TYPE.COLUMN_CLUSTERED, "bar": XL_CHART_TYPE.BAR_CLUSTERED,
                 "line": XL_CHART_TYPE.LINE_MARKERS, "pie": XL_CHART_TYPE.PIE,
                 "doughnut": XL_CHART_TYPE.DOUGHNUT, "stacked": XL_CHART_TYPE.COLUMN_STACKED}
        cd = CategoryChartData()
        cats = [str(c) for c in spec["categories"]]
        if kind == "bar":  # bar charts draw bottom-up; reverse so the first category is on top
            cats = cats[::-1]
        cd.categories = cats
        series = spec["series"]
        for sr in series:
            vals = list(sr["values"])
            cd.add_series(sr.get("name", ""), vals[::-1] if kind == "bar" else vals)
        gf = slide.shapes.add_chart(types.get(kind, XL_CHART_TYPE.COLUMN_CLUSTERED), self.E(e["x"]), self.E(e["y"]),
                                    self.E(e["w"]), self.E(e["h"]), cd)
        ch = gf.chart
        ch.font.size = self.pt(e.get("size", 12))
        ch.font.color.rgb = RGBColor.from_string(self.S.c("muted"))
        ch.font.name = self.S.fonts["body_latin"]
        ch.has_title = False
        P = self.S
        palette = [P.c("primary"), P.c("accent"), P.c("primary@0.45"), P.c("muted"), P.c("primary_dark"), P.c("accent@0.5")]
        hl = spec.get("highlight")
        plot = ch.plots[0]
        if kind in ("pie", "doughnut"):
            n = len(cats)
            shades = [P.c("primary")] + [mix(P.c("primary"), "FFFFFF", 0.2 + 0.6 * i / max(1, n - 1)) for i in range(1, n)]
            if hl is not None and 0 <= hl < n:
                shades[hl] = P.c("accent")
            for i, pt in enumerate(plot.series[0].points):
                pt.format.fill.solid()
                pt.format.fill.fore_color.rgb = RGBColor.from_string(shades[i % len(shades)])
                pt.format.line.color.rgb = RGBColor.from_string(P.c("surface"))
            plot.has_data_labels = True
            dl = plot.data_labels
            dl.number_format = spec_label_format(spec)
            dl.number_format_is_linked = False
            dl.font.size = self.pt(e.get("size", 12))
            dl.font.bold = True
            dl.font.color.rgb = RGBColor.from_string(self.S.c("text"))
            dl.show_value = True
            if kind == "doughnut":
                # labels sit on the slices: pick dark or light ink per slice
                from common import contrast
                for i, pt in enumerate(plot.series[0].points):
                    f = shades[i % len(shades)]
                    ink = max(("1A1A1A", "FFFFFF"), key=lambda c: contrast(c, f))
                    pl = pt.data_label
                    pl.font.size = self.pt(e.get("size", 12))
                    pl.font.bold = True
                    pl.font.color.rgb = RGBColor.from_string(ink)
                    # a point label does not inherit the series number format; copy it in
                    d = pl._dLbl
                    if d is not None and d.find(qn("c:numFmt")) is None:
                        from lxml import etree
                        nf = etree.Element(qn("c:numFmt"))
                        nf.set("formatCode", dl.number_format)
                        nf.set("sourceLinked", "0")
                        d.insert(1, nf)
            if kind == "pie":
                dl.position = XL_LABEL_POSITION.OUTSIDE_END  # doughnut labels take no position (PowerPoint rejects it)
            ch.has_legend = True
            ch.legend.position = XL_LEGEND_POSITION.RIGHT
            ch.legend.include_in_layout = False
            ch.legend.font.size = self.pt(e.get("size", 12))
            if kind == "doughnut":
                hole = ch._chartSpace.find(".//" + qn("c:holeSize"))
                if hole is not None:
                    hole.set("val", "58")
            return gf
        # category charts
        for i, sr in enumerate(plot.series):
            col = palette[i % len(palette)]
            if kind == "line":
                sr.format.line.color.rgb = RGBColor.from_string(col)
                sr.format.line.width = self.pt(2.5)
                sr.smooth = False
                sr.marker.format.fill.solid()
                sr.marker.format.fill.fore_color.rgb = RGBColor.from_string(col)
                sr.marker.format.line.color.rgb = RGBColor.from_string(P.c("surface"))
            else:
                sr.format.fill.solid()
                base = P.c("primary@0.45") if (hl is not None and len(series) == 1) else col
                sr.format.fill.fore_color.rgb = RGBColor.from_string(base)
                if hl is not None and len(series) == 1:
                    idx = (len(cats) - 1 - hl) if kind == "bar" else hl
                    pt = sr.points[idx]
                    pt.format.fill.solid()
                    pt.format.fill.fore_color.rgb = RGBColor.from_string(P.c("primary"))
        if kind != "line":
            plot.gap_width = 60
            if kind == "stacked":
                plot.overlap = 100
        plot.has_data_labels = True
        dl = plot.data_labels
        dl.font.size = self.pt(e.get("size", 12))
        dl.font.bold = True
        dl.font.color.rgb = RGBColor.from_string(P.c("text"))
        # the unit travels with the numbers: 35 with unit "%" reads 35%, not 35
        fmt = spec_label_format(spec)
        if fmt != "General":
            dl.number_format = fmt
            dl.number_format_is_linked = False
        if kind == "stacked":
            dl.position = XL_LABEL_POSITION.CENTER
        elif kind == "line":
            dl.position = XL_LABEL_POSITION.ABOVE
            if len(series) > 1:
                # several lines: numbers at every point collide, label only the last point
                from lxml import etree
                for si, sr in enumerate(plot.series):
                    lbls = sr._element.get_or_add_dLbls()
                    npts = len(sr.values)
                    for i in range(npts - 1):
                        d = etree.SubElement(lbls, qn("c:dLbl"))
                        etree.SubElement(d, qn("c:idx")).set("val", str(i))
                        etree.SubElement(d, qn("c:delete")).set("val", "1")
                        lbls.remove(d)
                        lbls.insert(i, d)
                    for tag, val in (("c:showLegendKey", "0"), ("c:showVal", "1"), ("c:showCatName", "0"),
                                     ("c:showSerName", "0"), ("c:showPercent", "0"), ("c:showBubbleSize", "0")):
                        el = lbls.find(qn(tag))
                        if el is not None:
                            el.set("val", val)
                    last = sr.points[npts - 1].data_label
                    last.position = XL_LABEL_POSITION.RIGHT
                    last.font.size = self.pt(e.get("size", 12))
                    last.font.bold = True
                    last.font.color.rgb = RGBColor.from_string(palette[si % len(palette)])
        else:
            dl.position = XL_LABEL_POSITION.OUTSIDE_END
        va, ca = ch.value_axis, ch.category_axis
        va.visible = False
        va.has_major_gridlines = kind == "line"
        if va.has_major_gridlines:
            va.major_gridlines.format.line.color.rgb = RGBColor.from_string(P.c("line"))
        ca.format.line.color.rgb = RGBColor.from_string(P.c("line"))
        ca.tick_labels.font.size = self.pt(e.get("size", 12))
        ca.tick_labels.font.color.rgb = RGBColor.from_string(P.c("text"))
        from pptx.enum.chart import XL_TICK_MARK
        ca.major_tick_mark = XL_TICK_MARK.NONE
        ch.has_legend = len(series) > 1
        if ch.has_legend:
            ch.legend.position = XL_LEGEND_POSITION.TOP
            ch.legend.include_in_layout = False
            ch.legend.font.size = self.pt(e.get("size", 12))
        return gf

    def render(self, slide, els):
        """Draw els in order. Returns [(element, [shape ids it produced])] for the animation pass."""
        out = []
        for e in els:
            before = len(slide.shapes)
            self._render_one(slide, e)
            out.append((e, [sh.shape_id for sh in list(slide.shapes)[before:]]))
        return out

    def _render_one(self, slide, e):
        t = e["t"]
        if t == "text":
            self.text(slide, e)
        elif t == "rect":
            self.rect(slide, e)
        elif t == "ellipse":
            self.rect(slide, e, oval=True)
        elif t == "image":
            self.image(slide, e)
        elif t == "icon":
            self.icon(slide, e)
        elif t == "line":
            self.line(slide, e)
        elif t == "table":
            self.table(slide, e)
        elif t == "chart":
            self.chart(slide, e)

    # ---------------------------------------------------------- master chrome
    def master(self, s, info, plan_slide):
        els = []
        m = info.get("master", "content")
        bg = self.assets.get(f"bg_{m}") or self.assets.get("bg_content")
        if bg:
            els.append({"t": "image", "x": 0, "y": 0, "w": CANVAS_W, "h": CANVAS_H, "path": bg, "fit": "stretch",
                        "role": "background"})
        else:
            els.append({"t": "rect", "x": 0, "y": 0, "w": CANVAS_W, "h": CANVAS_H,
                        "fill": "primary_dark" if m == "closing" else "bg_bottom", "role": "background"})
        return els

    def chrome(self, s, info, plan_slide):
        """Header + bottom pill/footer drawn above the layout."""
        els = []
        m = info.get("master", "content")
        series = self.meta.get("series")
        if self.S.decor.get("chrome") == "editorial":
            return self._chrome_editorial(s, info, plan_slide)
        if m == "content" and series and info.get("header", True) and self.S.decor.get("header", True):
            size = 14
            tw = text_width_pt(series, size, True) / 72 + len(series) * 0.035
            x = (CANVAS_W - tw) / 2
            els.append(L.T(series, x - 0.2, 0.28, tw + 0.4, 0.42, size, "highlight", True, align="c", valign="m", spc=3))
            lp = self.assets.get("decor_leaf_l")
            rp = self.assets.get("decor_leaf_r")
            if lp and self.S.decor.get("leaf", True):
                for e in (L.IMG(lp, x - 0.72, 0.2, 0.5, 0.5), L.IMG(rp, x + tw + 0.22, 0.2, 0.5, 0.5)):
                    e["role"] = "decor"
                    els.append(e)
        if m == "closing":
            return els
        page = s.get("page", "")
        if not page and self.meta.get("auto_page") and m == "content":
            page = f"{s['n']:02d} / {self.meta.get('total') or self.total:02d}"
        src = s.get("source") or s.get("footnote")
        if src:
            # "footnote" is printed as written; "source" gets a 来源 label unless it has one
            src_txt = src if (s.get("footnote") and not s.get("source")) or SOURCE_LABEL.match(src) else f"来源：{src}"
            # under the pill when there is one, otherwise on its own line above the footer row
            yb = 7.12 if (s.get("takeaway") and not info.get("uses_takeaway")) else 6.52
            els.append(L.T(src_txt, CANVAS_W / 2 - 3.2, yb, 6.4, 0.26, 10.5, "subtle", align="c", valign="m"))
        footer = self.meta.get("footer", "") if s.get("show_footer", m == "content") else ""
        meta_txt = "  ·  ".join([t for t in (footer, page) if t])
        tk = s.get("takeaway")
        if tk and not info.get("uses_takeaway"):
            x, y, w, h = L.MX, 6.33, L.CW, 0.74
            els.append(L.R(x, y, w, h, fill="surface", alpha=0.82, radius=h / 2,
                           line=None if self.S.depth in ("flat", "whisper") else "line", shadow=True))
            els.append(L.ICON(plan_slide.get("takeaway_icon", "globe"), x + 0.13, y + 0.12, h - 0.24,
                              color="on_primary", bg="primary"))
            mw = text_width_pt(meta_txt, 12) / 72 + 0.3 if meta_txt else 0
            tw = w - 0.95 - mw - 0.3
            from common import fit_size
            fs = fit_size(tk, tw, h - 0.14, 18, 11, bold=False, max_lines=2)
            els.append(L.T(tk, x + 0.9, y + 0.07, tw, h - 0.14, fs, "text", False, valign="m", spc=0.5))
            if meta_txt:
                els.append(L.T(meta_txt, x + w - mw - 0.3, y, mw, h, 12, "subtle", align="r", valign="m"))
        else:
            if footer:
                els.append(L.T(footer, L.MX, 6.85, 4, 0.3, 11, "subtle", valign="m"))
            if page:
                els.append(L.T(page, CANVAS_W - L.MX - 2, 6.85, 2, 0.3, 11, "subtle", align="r", valign="m"))
        return els

    def _chrome_editorial(self, s, info, plan_slide):
        """Magazine chrome: a metadata strip and hairline on top, footer and folio on a hairline at the
        bottom; the takeaway becomes a plain line with a short rule instead of a pill."""
        els = []
        m = info.get("master", "content")
        tk = s.get("takeaway")
        if m != "content":
            # no strip or folio on cover / section / closing, but a takeaway line must never be dropped
            if tk and not info.get("uses_takeaway") and m != "closing":
                from common import fit_size
                els.append(L.R(L.MX, 6.62, 0.36, 0.06, fill="primary"))
                fs = fit_size(tk, L.CW - 0.6, 0.42, 18, 12, max_lines=1)
                els.append(L.T(tk, L.MX + 0.55, 6.44, L.CW - 0.6, 0.42, fs, "text", False, valign="m"))
            return els
        top_l = self.meta.get("series") or self.meta.get("title", "")
        top_r = self.meta.get("issue") or self.meta.get("date") or ""
        if info.get("header", True) and top_l:
            els.append(L.T(top_l, L.MX, 0.3, 7, 0.3, 10.5, "subtle", True, valign="m", spc=2))
        if top_r:
            els.append(L.T(top_r, CANVAS_W - L.MX - 4, 0.3, 4, 0.3, 10.5, "subtle", True, align="r", valign="m", spc=2))
        els.append(L.LN(L.MX, 0.68, CANVAS_W - L.MX, 0.68, "line", 0.75))
        if tk and not info.get("uses_takeaway"):
            from common import fit_size
            els.append(L.R(L.MX, 6.44, 0.36, 0.06, fill="primary"))
            fs = fit_size(tk, L.CW - 0.6, 0.42, 18, 12, max_lines=1)
            els.append(L.T(tk, L.MX + 0.55, 6.26, L.CW - 0.6, 0.42, fs, "text", False, valign="m"))
        els.append(L.LN(L.MX, 6.8, CANVAS_W - L.MX, 6.8, "line", 0.75))
        footer = self.meta.get("footer", "")
        if footer:
            els.append(L.T(footer, L.MX, 6.88, 5, 0.3, 10.5, "subtle", valign="m"))
        folio = s.get("page") or f"{s['n']:02d} / {self.meta.get('total') or self.total:02d}"
        els.append(L.T(folio, CANVAS_W - L.MX - 2, 6.88, 2, 0.3, 10.5, "subtle", True, "display", align="r", valign="m"))
        src = s.get("source") or s.get("footnote")
        if src:
            # "footnote" is printed as written; "source" gets a 来源 label unless it has one
            src_txt = src if (s.get("footnote") and not s.get("source")) or SOURCE_LABEL.match(src) else f"来源：{src}"
            els.append(L.T(src_txt, CANVAS_W / 2 - 3.2, 6.88, 6.4, 0.3, 10.5, "subtle", align="c", valign="m"))
        return els


# a source line that already carries its own label ("数据来源：", "资料来源", "Source:") is not prefixed again
SOURCE_LABEL = re.compile(r"^\s*(数据|资料|图片|信息)?(来源|出处)|^\s*(source|data|via)\b", re.I)

# modular scale (~1.2 ratio) in pt; style.json "type_scale" overrides it, false turns snapping off
from common import TYPE_SCALE, LADDER, snap_size  # noqa: E402


def load_assets(work):
    man = Path(work) / "assets" / "manifest.json"
    out = {}
    if man.exists():
        for a in load_json(man).get("assets", []):
            if a.get("path") and Path(a["path"]).exists():
                out[a["id"]] = a["path"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("--out")
    a = ap.parse_args()
    work = Path(a.work)
    deck = load_json(work / "deck.json")
    plan = load_json(work / "plan.json")
    style = load_style(work / "style.json")
    assets = load_assets(work)
    import common as _c
    _c.PROJECTION["on"] = bool(deck.get("meta", {}).get("projection"))
    src = work / "source.pptx"
    if src.exists():
        sp = Presentation(str(src))
        sw, sh = sp.slide_width, sp.slide_height
    else:
        sw, sh = Inches(CANVAS_W), Inches(CANVAS_H)
    if abs(sw / sh - 16 / 9) > 0.02:
        print(f"NOTE source is {sw/914400:.2f}x{sh/914400:.2f} in (not 16:9); output uses 13.333x7.5 widescreen")
        sw, sh = Inches(CANVAS_W), Inches(CANVAS_H)
    prs = Presentation()
    prs.slide_width, prs.slide_height = sw, sh
    blank = prs.slide_layouts[6]
    b = Builder(work, style, deck.get("meta", {}), assets, sw / 914400, sh / 914400)
    b.total = len(deck["slides"])
    plan_by_n = {p["n"]: p for p in plan.get("slides", [])}
    dump = {"slide_w": sw / 914400, "slide_h": sh / 914400, "scale": b.k, "slides": []}
    ladder = style.data.get("type_scale", TYPE_SCALE) if style.data.get("type_scale", True) is not False else None
    if ladder is True:
        ladder = TYPE_SCALE
    LADDER["steps"] = sorted(ladder) if ladder else None
    # chapters: section slides get 01, 02 ... when unnumbered, and a toc slide without items lists them
    meta_ctx = dict(deck.get("meta", {}))
    meta_ctx["_work"] = str(work)
    secs, k = [], 0
    for s in deck["slides"]:
        if s.get("type") == "section" or plan_by_n.get(s["n"], {}).get("layout") == "section":
            k += 1
            if not s.get("number") and meta_ctx.get("auto_number", True):
                s["number"] = f"{k:02d}"
            secs.append({"number": s.get("number"), "title": s.get("title", ""), "text": s.get("subtitle", "")})
    meta_ctx["_sections"] = secs
    built = []
    for s in deck["slides"]:
        ps = plan_by_n.get(s["n"], {})
        lname = ps.get("layout") or s.get("layout") or L.TYPE_TO_LAYOUTS.get(s.get("type"), ["list_icons"])[0]
        fn = L.LAYOUTS.get(lname)
        if not fn:
            b.warnings.append(f"slide {s['n']}: unknown layout {lname}, used list_icons")
            fn, lname = L.list_icons, "list_icons"
        ctx = L.Ctx(style, meta_ctx, assets, ps)
        L.step_reset()
        els, info = fn(s, ctx)
        L.step_end()
        els = L.apply_markers(els, ctx, lname)
        # small pictures kept from the original at a fixed spot: logos, AI-generated labels
        for st in s.get("stamps", []):
            sp = L._img_file(ctx, st.get("image"))
            if sp:
                e = L.IMG(sp, st["x"], st["y"], st["w"], st["h"])
                e["role"] = "stamp"
                els.append(e)
        info.update(ps.get("info", {}))
        # sibling texts (same "grp") share one size: the smallest that fits all of them
        sizes = {}
        for e in els:
            if e.get("t") == "text" and e.get("grp"):
                sizes[e["grp"]] = min(sizes.get(e["grp"], 999), e["size"])
        for e in els:
            if e.get("t") == "text" and e.get("grp"):
                e["size"] = sizes[e["grp"]]
        # one deck-wide type ladder: every computed size snaps down to the nearest step,
        # so body text is 14 or 17pt everywhere instead of 15 here and 16 there
        if ladder:
            for e in els:
                if e.get("t") == "text" and e.get("role") != "decor":
                    e["size"] = snap_size(e["size"])
        built.append((s, ps, lname, info, els))

    # deck-wide groups ("dgrp", e.g. every slide title): the most common size wins, larger ones
    # shrink to it (shrinking always still fits), so titles do not change size from page to page
    groups = {}
    for _, _, _, _, els in built:
        for e in els:
            if e.get("t") == "text" and e.get("dgrp"):
                groups.setdefault(e["dgrp"], []).append(e)
    for g, es in groups.items():
        # the median size: half the titles already fit at it, larger ones come down to it
        sizes = sorted(e["size"] for e in es)
        target = sizes[len(sizes) // 2]
        for e in es:
            e["size"] = min(e["size"], target)

    for s, ps, lname, info, els in built:
        chrome = b.chrome(s, info, ps)
        for e in chrome:
            e.setdefault("role", "chrome")
        all_els = b.master(s, info, ps) + els + chrome
        pill = bool(s.get("takeaway") and not info.get("uses_takeaway"))
        # content must end above the takeaway pill, the source line or the footer row
        rail = 6.25 if pill else (6.45 if ((s.get("source") or s.get("footnote")) and style.decor.get("chrome") != "editorial") else 6.8)
        slide = prs.slides.add_slide(blank)
        rendered = b.render(slide, all_els)
        mode, effect = A.resolve(deck.get("meta", {}), s)
        builds = A.apply(slide, rendered, mode, effect)
        notes = s.get("notes")
        if notes:
            slide.notes_slide.notes_text_frame.text = notes
        dump["slides"].append({"n": s["n"], "layout": lname, "master": info.get("master", "content"),
                               "rail": rail, "animation": {"mode": mode, "builds": builds},
                               "elements": all_els})
    out = Path(a.out) if a.out else work / "out" / "beautified.pptx"
    out.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(out))
    save_json(dump, out.parent / "layout_dump.json")
    print(f"saved {out}")
    for w in b.warnings:
        print("WARN", w)
    for f in style.fixes:
        print("NOTE", f)


if __name__ == "__main__":
    main()
