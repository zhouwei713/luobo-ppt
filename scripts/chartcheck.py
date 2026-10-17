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
              "BAR_STACKED": "stacked", "COLUMN_STACKED_100": "stacked"}


def _axis_title(axis):
    try:
        if axis.has_title and axis.axis_title.has_text_frame:
            return axis.axis_title.text_frame.text.strip()
    except Exception:  # noqa: BLE001
        pass
    return ""


def read_chart(chart):
    """A chart object -> {type, title, categories, series, label_format, axis_format, x_title, y_title}."""
    try:
        tname = str(chart.chart_type).split(".")[-1].split(" ")[0]
    except Exception:  # noqa: BLE001
        tname = ""
    title = ""
    try:
        if chart.has_title and chart.chart_title.has_text_frame:
            title = chart.chart_title.text_frame.text.strip()
    except Exception:  # noqa: BLE001
        pass
    plot = chart.plots[0]
    cats = [str(c) for c in plot.categories]
    series = [{"name": s.name or "", "values": [None if v is None else float(v) for v in s.values]}
              for p in chart.plots for s in p.series]
    label_fmt = None
    try:
        if plot.has_data_labels:
            dl = plot.data_labels
            label_fmt = dl.number_format if not dl.number_format_is_linked else None
    except Exception:  # noqa: BLE001
        pass
    axis_fmt, x_title, y_title = None, "", ""
    try:
        va = chart.value_axis
        axis_fmt = va.tick_labels.number_format if not va.tick_labels.number_format_is_linked else None
        y_title = _axis_title(va)
    except Exception:  # noqa: BLE001
        pass
    try:
        x_title = _axis_title(chart.category_axis)
    except Exception:  # noqa: BLE001
        pass
    # linked formats come from the embedded sheet; the series' own format code is the best guess
    if not label_fmt and not axis_fmt:
        try:
            nf = chart._chartSpace.find(".//{http://schemas.openxmlformats.org/drawingml/2006/chart}numCache/"
                                        "{http://schemas.openxmlformats.org/drawingml/2006/chart}formatCode")
            if nf is not None and nf.text:
                axis_fmt = nf.text
        except Exception:  # noqa: BLE001
            pass
    return {"type": TYPE_NAMES.get(tname, tname.lower()), "title": title, "categories": cats, "series": series,
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


def from_spec(spec):
    """deck.json chart spec -> the shape read_chart returns."""
    return {"type": spec.get("type", "column"), "title": spec.get("title", ""),
            "categories": [str(c) for c in spec.get("categories", [])],
            "series": [{"name": s.get("name", ""), "values": [None if v is None else float(v) for v in s.get("values", [])]}
                       for s in spec.get("series", [])],
            "label_format": spec_label_format(spec), "axis_format": None,
            "x_title": spec.get("x_title", ""), "y_title": spec.get("y_title", "")}


def draft_spec(ch):
    """A deck.json chart spec drafted from a chart read out of the original."""
    spec = {"type": ch["type"] if ch["type"] in ("column", "bar", "line", "pie", "doughnut", "stacked") else "column",
            "categories": ch["categories"], "series": ch["series"]}
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
        out[s["name"]] = {c: v for c, v in zip(ch["categories"], s["values"])}
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
    if sorted(ref["categories"]) != sorted(out["categories"]):
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
