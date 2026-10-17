"""Charts and fine print: the places where the body text is right but the meaning moved.

A chart can keep every word around it and still change what it says: a unit dropped from
the labels (35% shown as 35), a value axis title lost, a series renamed, a footnote's
asterisk gone. This module reads charts out of a .pptx, turns a deck.json chart spec into
the same shape, renders values the way PowerPoint shows them, and compares the two.

Used by extract_deck.py (charts in the original), build_deck.py (label format of a spec)
and qa_check.py (the chart and fine-print checks, out/fine_print.md).
"""
import math
import re

# a line that is fine print: notes, sources, units, footnote marks
FINE_PRINT = re.compile(r"^\s*(\*|※|†|‡|注|备注|说明|来源|数据来源|资料来源|单位|口径|source|note|unit)", re.I)
# a footnote mark glued to a number or word: 35%*, 营收※ (superscript digits are left out:
# in a maths deck x³ is far more common than a numbered footnote)
FOOT_MARK = re.compile(r"[\*※†‡]")


# ------------------------------------------------------------------ number formats
def _split_sections(code):
    out, cur, q = [], "", False
    for ch in code:
        if ch == '"':
            q = not q
        if ch == ";" and not q:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return out


def render(value, code="General"):
    """The text PowerPoint shows for `value` under number format `code` (the common cases:
    General, 0, 0.0, #,##0, percents, quoted or escaped literal text)."""
    if value is None:
        return ""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    code = (code or "General").strip() or "General"
    secs = _split_sections(code)
    sec = secs[1] if v < 0 and len(secs) > 1 else secs[0]
    neg = v < 0 and len(secs) == 1
    v = abs(v) if (v < 0) else v
    # pull literal text out: "..." and \x
    lits = []

    def keep(m):
        lits.append(m.group(1) if m.group(1) is not None else m.group(2))
        return chr(0xE000 + len(lits) - 1)  # a private-use char: no digit for the number pattern to eat
    body = re.sub(r'"([^"]*)"|\\(.)', keep, sec)
    body = re.sub(r"\[[^\]]*\]", "", body)          # colours, conditions
    body = body.replace("_)", "").replace("*", "")
    if "general" in body.lower():
        num = f"{v:.10g}"
        txt = re.sub("(?i)general", num, body, count=1)
    else:
        pct = body.count("%")
        if pct:
            v = v * (100 ** pct)
        m = re.search(r"[#0,.]+", body)
        if not m:
            txt = body
        else:
            pat = m.group(0)
            dec = len(pat.split(".")[1]) if "." in pat else 0
            dec_digits = re.sub(r"[^0#]", "", pat.split(".")[1]) if "." in pat else ""
            req = dec_digits.count("0")
            # Excel rounds halves away from zero (Python's format rounds them to even)
            from decimal import Decimal, ROUND_HALF_UP
            q = Decimal(repr(v)).quantize(Decimal(1).scaleb(-dec), rounding=ROUND_HALF_UP)
            s = f"{q:,.{dec}f}" if "," in pat.split(".")[0] else f"{q:.{dec}f}"
            if dec and req < dec:  # optional '#' decimals drop trailing zeros
                intp, frac = s.split(".")
                frac = frac.rstrip("0")
                frac = frac + "0" * max(0, req - len(frac))
                s = intp + ("." + frac if frac else "")
            txt = body[:m.start()] + s + body[m.end():]
    txt = re.sub("[\ue000-\ue0ff]", lambda m: lits[ord(m.group(0)) - 0xE000], txt)
    return ("-" if neg else "") + txt.strip()


def spec_label_format(spec):
    """Data label format the builder uses for a deck.json chart spec."""
    if spec.get("number_format"):
        return spec["number_format"]
    unit = spec.get("unit")
    if unit:
        return f'General"{unit}"'
    return "General"


# ------------------------------------------------------------------ reading charts
TYPE_NAMES = {"COLUMN_CLUSTERED": "column", "COLUMN_STACKED": "stacked", "BAR_CLUSTERED": "bar",
              "LINE": "line", "LINE_MARKERS": "line", "PIE": "pie", "DOUGHNUT": "doughnut",
              "BAR_STACKED": "stacked", "COLUMN_STACKED_100": "stacked",
              "XY_SCATTER": "scatter", "XY_SCATTER_LINES": "scatter", "XY_SCATTER_LINES_NO_MARKERS": "scatter",
              "XY_SCATTER_SMOOTH": "scatter", "XY_SCATTER_SMOOTH_NO_MARKERS": "scatter"}
SPEC_TYPES = ("column", "bar", "line", "pie", "doughnut", "stacked", "scatter")
C_NS = "{http://schemas.openxmlformats.org/drawingml/2006/chart}"


def _axis_title(axis):
    try:
        if axis.has_title and axis.axis_title.has_text_frame:
            return axis.axis_title.text_frame.text.strip()
    except Exception:  # noqa: BLE001
        pass
    return ""


def _own_format(el):
    """The format code an element sets itself; None when it has none or follows the sheet
    (sourceLinked="1": PowerPoint then shows the numbers in the embedded sheet's format)."""
    nf = el.find(C_NS + "numFmt") if el is not None else None
    if nf is None or nf.get("sourceLinked") == "1":
        return None
    return nf.get("formatCode")


def _sheet_format(ser, tag="val"):
    """The embedded sheet's format of a series' numbers (what linked labels and axes show)."""
    if ser is None:
        return None
    for t in (tag, "yVal") if tag == "val" else (tag,):
        nf = ser.find(f"{C_NS}{t}//{C_NS}numCache/{C_NS}formatCode")
        if nf is not None and (nf.text or "").strip():
            return nf.text.strip()
    return None


def _cache_numbers(ser, tag):
    out = []
    el = ser.find(C_NS + tag) if ser is not None else None
    if el is None:
        return out
    pts = {}
    for pt in el.iter(C_NS + "pt"):
        v = pt.find(C_NS + "v")
        try:
            pts[int(pt.get("idx", len(pts)))] = float(v.text)
        except (TypeError, ValueError, AttributeError):
            pass
    n = max(pts) + 1 if pts else 0
    return [pts.get(i) for i in range(n)]


def _labels_shown(dl):
    if dl is None:
        return False
    d = dl.find(C_NS + "delete")
    if d is not None and d.get("val") in ("1", "true"):
        return False
    sv = dl.find(C_NS + "showVal")
    sp = dl.find(C_NS + "showPercent")
    return any(e is not None and e.get("val") in ("1", "true") for e in (sv, sp))


def read_chart(chart):
    """A chart object -> {type, title, categories, series, label_format, axis_format, x_title, y_title}.

    Formats come from the XML, not python-pptx's accessors: an axis or label without its own
    numFmt, or with sourceLinked="1", shows the embedded sheet's format (0.312 under "0.0%"
    reads 31.2%), and python-pptx reports that case as "General"."""
    try:
        tname = str(chart.chart_type).split(".")[-1].split(" ")[0]
    except Exception:  # noqa: BLE001
        tname = ""
    kind = TYPE_NAMES.get(tname, tname.lower())
    title = ""
    try:
        if chart.has_title and chart.chart_title.has_text_frame:
            title = chart.chart_title.text_frame.text.strip()
    except Exception:  # noqa: BLE001
        pass
    cs = chart._chartSpace
    plot_el = cs.find(f".//{C_NS}plotArea")
    sers = list(plot_el.iter(C_NS + "ser")) if plot_el is not None else []
    first = sers[0] if sers else None
    sheet_fmt = _sheet_format(first)
    series = []
    if kind == "scatter":
        for ser in sers:
            tx = ser.find(f"{C_NS}tx//{C_NS}v")
            series.append({"name": (tx.text if tx is not None else "") or "",
                           "x": _cache_numbers(ser, "xVal"), "values": _cache_numbers(ser, "yVal")})
        xs = series[0]["x"] if series else []
        cats = [render(x, _sheet_format(first, "xVal") or "General") for x in xs]
    else:
        plot = chart.plots[0]
        try:
            cats = [str(c) for c in plot.categories]
        except Exception:  # noqa: BLE001
            cats = []
        series = [{"name": s.name or "", "values": [None if v is None else float(v) for v in s.values]}
                  for p in chart.plots for s in p.series]
    # data labels, most specific first: a point's own label, the series' labels, the chart
    # group's labels. A series dLbls replaces the group's entirely, numFmt included, so a
    # format set on the group does not reach labels the series defines itself.
    label_fmt = None
    groups = [g for g in (plot_el if plot_el is not None else []) if g.tag.endswith("Chart")]
    sdl = first.find(C_NS + "dLbls") if first is not None else None
    if sdl is not None:
        pts = [d for d in sdl.findall(C_NS + "dLbl") if _labels_shown(d)]
        if pts:
            label_fmt = _own_format(pts[0]) or _own_format(sdl) or sheet_fmt or "General"
        elif _labels_shown(sdl):
            label_fmt = _own_format(sdl) or sheet_fmt or "General"
    else:
        for dl in [g.find(C_NS + "dLbls") for g in groups]:
            if _labels_shown(dl):
                label_fmt = _own_format(dl) or sheet_fmt or "General"
                break
    # value axis: for a scatter chart the vertical one
    axis_fmt = None
    vals = plot_el.findall(C_NS + "valAx") if plot_el is not None else []
    va = next((a for a in vals if (a.find(C_NS + "axPos") is not None
                                   and a.find(C_NS + "axPos").get("val") in ("l", "r"))), vals[0] if vals else None)
    if kind not in ("pie", "doughnut") and va is not None:
        axis_fmt = _own_format(va) or sheet_fmt or "General"
    x_title, y_title = "", ""
    try:
        y_title = _axis_title(chart.value_axis)
        x_title = _axis_title(chart.category_axis)
    except Exception:  # noqa: BLE001
        pass
    if kind == "scatter" and len(vals) >= 2:
        # python-pptx gives the first valAx for both; read the titles straight from each axis
        def _t(ax):
            t = ax.find(f"{C_NS}title")
            return "".join(x.text or "" for x in t.iter("{http://schemas.openxmlformats.org/drawingml/2006/main}t")).strip() if t is not None else ""
        hx = next((a for a in vals if a is not va), None)
        y_title, x_title = _t(va), _t(hx) if hx is not None else ""
    return {"type": kind, "title": title, "categories": cats, "series": series,
            "label_format": label_fmt, "axis_format": axis_fmt, "x_title": x_title, "y_title": y_title}


def charts_on_slide(slide):
    out = []

    def walk(shapes):
        for sh in shapes:
            if getattr(sh, "shapes", None) is not None and sh.shape_type == 6:  # group
                walk(sh.shapes)
            elif getattr(sh, "has_chart", False) and sh.has_chart:
                out.append(read_chart(sh.chart))
    walk(slide.shapes)
    return out


def spec_charts(slide):
    """The chart specs of a deck.json slide: "chart" (one) or "charts" (two or three side by side)."""
    if slide.get("charts"):
        return [c for c in slide["charts"] if c]
    return [slide["chart"]] if slide.get("chart") else []


def _xcats(xs):
    return [render(x, "General") for x in xs]


def from_spec(spec):
    """deck.json chart spec -> the shape read_chart returns."""
    kind = spec.get("type", "column")
    series = []
    for s in spec.get("series", []):
        d = {"name": s.get("name", ""), "values": [None if v is None else float(v) for v in s.get("values", [])]}
        if kind == "scatter":
            d["x"] = [float(v) for v in s.get("x", [])]
        series.append(d)
    cats = _xcats(series[0]["x"]) if kind == "scatter" and series else [str(c) for c in spec.get("categories", [])]
    return {"type": kind, "title": spec.get("title", ""), "categories": cats, "series": series,
            "label_format": spec_label_format(spec), "axis_format": None,
            "x_title": spec.get("x_title", ""), "y_title": spec.get("y_title", "")}


def draft_spec(ch):
    """A deck.json chart spec drafted from a chart read out of the original."""
    kind = ch["type"] if ch["type"] in SPEC_TYPES else "column"
    spec = {"type": kind}
    if kind != "scatter":
        spec["categories"] = ch["categories"]
    spec["series"] = ch["series"]
    fmt = shown_format(ch)
    if fmt and fmt.lower() != "general":
        spec["number_format"] = fmt
    for k in ("title", "x_title", "y_title"):
        if ch.get(k):
            spec[k] = ch[k]
    return spec


def shown_format(ch):
    """The format the reader sees numbers in: data labels first, else the value axis."""
    return ch.get("label_format") or ch.get("axis_format") or "General"


# ------------------------------------------------------------------ comparing
def _norm(s):
    return re.sub(r"\s+", "", (s or "").replace("**", ""))


def _values_by_cat(ch):
    out = {}
    for s in ch["series"]:
        cats = _xcats(s["x"]) if s.get("x") else ch["categories"]  # scatter: each series has its own x
        out[s["name"]] = {c: v for c, v in zip(cats, s["values"])}
    return out


def _close(a, b):
    if a is None or b is None:
        return a is None and b is None
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)


def compare(ref, out, slide_text=""):
    """Problems as (level, message), plus rows for the side-by-side list."""
    probs, rows = [], []
    blob = _norm(slide_text)
    # categories (order may legitimately flip for bar charts)
    if ref.get("type") == "scatter" or out.get("type") == "scatter":
        if ref.get("type") != out.get("type"):
            probs.append(("ERROR", f"图表类型变了，原来是 {ref.get('type')}，现在是 {out.get('type')}（散点图的横轴是数值）"))
        rx = sorted(c for s in ref["series"] for c in _xcats(s.get("x", [])))
        ox = sorted(c for s in out["series"] for c in _xcats(s.get("x", [])))
        if rx != ox:
            probs.append(("ERROR", f"散点图的横轴数值对不上，原来 {rx[:6]}，现在 {ox[:6]}"))
    elif sorted(ref["categories"]) != sorted(out["categories"]):
        miss = [c for c in ref["categories"] if c not in out["categories"]]
        extra = [c for c in out["categories"] if c not in ref["categories"]]
        probs.append(("ERROR", f"图表类别对不上，缺少 {miss}，多出 {extra}"))
    rows.append(("类别", " / ".join(ref["categories"]), " / ".join(out["categories"])))
    rv, ov = _values_by_cat(ref), _values_by_cat(out)
    ref_names = [s["name"] for s in ref["series"]]
    out_names = [s["name"] for s in out["series"]]
    if len(ref_names) == 1 and len(out_names) == 1 and ref_names[0] != out_names[0] and not ref_names[0]:
        out_names = ref_names  # an unnamed single series may come back as "Series 1"
        ov = {ref_names[0]: list(ov.values())[0]}
    if sorted(ref_names) != sorted(out_names):
        probs.append(("ERROR", f"图表系列名变了，原来 {ref_names}，现在 {out_names}"))
    rows.append(("系列", " / ".join(ref_names), " / ".join(out_names)))
    rfmt, ofmt = shown_format(ref), shown_format(out)
    bad_vals, bad_shown = [], []
    for name, cv in rv.items():
        oc = ov.get(name, {})
        for c, v in cv.items():
            if c not in oc:
                continue
            if not _close(v, oc[c]):
                bad_vals.append(f"{name or '数值'}·{c} {v} → {oc[c]}")
            elif render(v, rfmt) != render(oc[c], ofmt):
                bad_shown.append(f"{c} {render(v, rfmt)} → {render(oc[c], ofmt)}")
    if bad_vals:
        probs.append(("ERROR", "图表数据变了：" + "；".join(bad_vals[:4])))
    if bad_shown:
        probs.append(("ERROR", "图上显示的数字变了（单位或格式没带过来）：" + "；".join(bad_shown[:4])))
    sample = next(((c, v) for cv in rv.values() for c, v in cv.items() if v is not None), None)
    if sample:
        c, v = sample
        o = ov.get(next(iter(ov), None), {}).get(c) if ov else None
        rows.append(("数字显示", f"{c} 显示为 {render(v, rfmt)}",
                     f"{c} 显示为 {render(o, ofmt)}" if o is not None else "（没找到）"))
    for key, label in (("title", "图表标题"), ("y_title", "数值轴标题"), ("x_title", "类别轴标题")):
        want = ref.get(key) or ""
        got = out.get(key) or ""
        if want:
            ok = _norm(want) in (_norm(got) + blob)
            if not ok:
                probs.append(("ERROR", f"{label}「{want}」不见了，图上和页面上都没有"))
            rows.append((label, want, got or ("页面文字里有" if ok else "（缺）")))
    return probs, rows


def fine_print_units(units):
    """Source text units that are fine print: notes, sources, units, footnote marks."""
    out = []
    for u in units:
        t = (u.get("text") or "").replace("**", "")  # bold marks are not footnote marks
        if t.strip() and (FINE_PRINT.match(t) or FOOT_MARK.search(t)):
            out.append(u)
    return out


def strict(s):
    """Fine print is compared without dropping list markers or footnote marks."""
    return re.sub(r"\s+", "", (s or "").replace("**", "")).replace("“", "\"").replace("”", "\"")
