"""How much each layout can hold, so overflow is caught while writing the outline.

Units are reading units: one CJK character or one latin word = 1 (see common.clen).
Each entry:
  items      (min, max) number of entries in slide["items"]
  item       per-item field -> max units
  fields     top-level (or dotted, e.g. "side.title") field -> max units
  lists      field -> (min, max, max units per entry) for plain string lists
Used by outline_check.py (warnings), plan_deck.py (pick a layout that fits) and layout_info.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import clen  # noqa: E402

T = {"title": 22}
CAPACITY = {
    "cover_hero": {"fields": {"title": 16, "subtitle": 18, "body": 30, "kicker": 14}, "items": (0, 4), "item": {"text": 12}},
    "statement_number": {"fields": {**T, "number": 4, "body": 44}, "lists": {"lines": (1, 3, 12)}},
    "rows_side": {"fields": {**T, "side.title": 12, "side.body": 40}, "items": (2, 4), "item": {"title": 8, "text": 26}},
    "stats_row": {"fields": {**T, "takeaway": 36}, "items": (2, 4), "item": {"value": 6, "label": 12}},
    "media_text": {"fields": {**T, "point": 22, "body": 44, "callout": 50, "diagram.title": 14}},
    "side_cards": {"fields": {**T, "side.title": 12, "side.body": 40}, "items": (1, 3), "item": {"title": 18, "text": 44}},
    "quote_cards": {"fields": {**T, "lead": 30}, "items": (1, 4), "item": {"text": 50}},
    "statement_hero": {"fields": {**T, "headline": 16, "body": 44, "pill": 22}},
    "cards_quote": {"fields": T, "items": (1, 3), "item": {"title": 14, "text": 32}, "lists": {"quote_lines": (1, 3, 12)}},
    "list_icons": {"fields": T, "items": (1, 6), "item": {"title": 12, "text": 60}},
    "grid_cards": {"fields": T, "items": (2, 6), "item": {"title": 10, "text": 28}},
    "steps_flow": {"fields": {**T, "takeaway": 36}, "items": (2, 5), "item": {"title": 8, "text": 30}},
    "compare_split": {"fields": {**T, "left.title": 10, "right.title": 10},
                      "lists": {"left.items": (1, 5, 20), "right.items": (1, 5, 20)}},
    "cycle": {"fields": {**T, "center": 6}, "items": (3, 6), "item": {"title": 8, "text": 20}},
    "pyramid": {"fields": T, "items": (2, 5), "item": {"title": 8, "text": 26}},
    "section": {"fields": {"title": 16, "subtitle": 30, "number": 3}},
    "cover_type": {"fields": {"title": 24, "subtitle": 26, "body": 30, "kicker": 16}, "items": (0, 4), "item": {"text": 8}},
    "cover_center": {"fields": {"title": 16, "subtitle": 16, "body": 34, "kicker": 30, "takeaway": 34}},
    "rank_grid": {"fields": T, "items": (3, 10), "item": {"title": 8, "text": 10}, "lists": {"findings.items": (0, 4, 26)}},
    "question": {"fields": {"question": 30, "kicker": 12, "body": 40}},
    "shot_notes": {"fields": {**T, "caption": 30}, "items": (0, 5), "item": {"title": 10, "text": 30}},
    "shot_stack": {"fields": T, "items": (1, 4), "item": {"title": 10, "text": 20}},
    "explain": {"fields": {**T, "takeaway": 40}},
    "big_quote": {"fields": {"quote": 70, "by": 20, "note": 30}},
    "toc": {"fields": {"title": 6, "kicker": 3}, "items": (0, 6), "item": {"title": 14, "text": 22}},
    "toc_row": {"fields": {"title": 10, "kicker": 3}, "items": (0, 5), "item": {"title": 8, "text": 16}},
    "closing": {"fields": {"headline": 18, "body": 30, "cta": 12}},
    "timeline": {"fields": T, "items": (3, 6), "item": {"date": 8, "title": 8, "text": 20}},
    "funnel": {"fields": T, "items": (3, 5), "item": {"label": 8, "value": 8, "text": 26}},
    "hub": {"fields": {**T, "center.title": 8}, "items": (3, 6), "item": {"title": 8, "text": 18}},
    "matrix": {"fields": {**T, "x_axis.label": 8, "y_axis.label": 6}, "quadrants": (4, 4, 8, 3, 14)},
    "table": {"fields": {**T, "note": 40}, "table": {"columns": (2, 6), "rows": (1, 8), "cell": 16}},
    "chart": {"fields": T, "chart": {"categories": (2, 8), "series": (1, 3)}, "lists": {"insights": (0, 3, 32)}},
    "framework": {"fields": T, "framework": {"swot": (1, 4, 16), "pest": (1, 4, 14), "five_forces": (1, 3, 14),
                                             "canvas": (1, 3, 14)}},
}


def _get(d, dotted):
    for k in dotted.split("."):
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def _txt(x):
    return x if isinstance(x, str) else (x.get("text", "") if isinstance(x, dict) else str(x))


# projection mode (deck.meta.projection) raises the font floor, so every text limit shrinks
SCALE = {"v": 1.0}


def set_projection(on):
    SCALE["v"] = 0.65 if on else 1.0


def _m(mx):
    return max(2, int(mx * SCALE["v"]))


def check(slide, layout):
    """Return a list of human-readable problems ("" when it fits)."""
    cap = CAPACITY.get(layout)
    if not cap:
        return []
    out = []
    for f, mx in cap.get("fields", {}).items():
        v = _get(slide, f)
        if isinstance(v, str) and clen(v) > _m(mx):
            out.append(f"{f} 约 {clen(v)} 字，{layout} 最多 {_m(mx)}")
    if "items" in cap:
        lo, hi = cap["items"]
        items = slide.get("items", [])
        if not (lo <= len(items) <= hi):
            out.append(f"{len(items)} 条 items，{layout} 需要 {lo} 到 {hi} 条")
        for i, it in enumerate(items, 1):
            if not isinstance(it, dict):
                continue
            for f, mx in cap.get("item", {}).items():
                v = it.get(f)
                if v is not None and clen(str(v)) > _m(mx):
                    out.append(f"第 {i} 条的 {f} 约 {clen(str(v))} 字，最多 {_m(mx)}")
    for f, (lo, hi, mx) in cap.get("lists", {}).items():
        v = _get(slide, f)
        if v is None:
            continue
        v = v if isinstance(v, list) else [v]
        if not (lo <= len(v) <= hi):
            out.append(f"{f} 有 {len(v)} 条，需要 {lo} 到 {hi} 条")
        for i, x in enumerate(v, 1):
            if clen(_txt(x)) > _m(mx):
                out.append(f"{f} 第 {i} 条约 {clen(_txt(x))} 字，最多 {_m(mx)}")
    if "quadrants" in cap:
        lo, hi, tmx, imax, iw = cap["quadrants"]
        q = slide.get("quadrants", [])
        if len(q) != 4:
            out.append(f"quadrants 需要正好 4 个，现在 {len(q)} 个")
        for i, qq in enumerate(q, 1):
            if clen(qq.get("title", "")) > _m(tmx):
                out.append(f"第 {i} 象限标题最多 {_m(tmx)} 字")
            its = qq.get("items", [])
            if len(its) > imax:
                out.append(f"第 {i} 象限 {len(its)} 条，最多 {imax} 条")
            for x in its:
                if clen(_txt(x)) > _m(iw):
                    out.append(f"第 {i} 象限有一条约 {clen(_txt(x))} 字，最多 {_m(iw)}")
    if "table" in cap:
        t = cap["table"]
        cols, rows = slide.get("columns", []), slide.get("rows", [])
        if not (t["columns"][0] <= len(cols) <= t["columns"][1]):
            out.append(f"表格 {len(cols)} 列，需要 {t['columns'][0]} 到 {t['columns'][1]} 列")
        if not (t["rows"][0] <= len(rows) <= t["rows"][1]):
            out.append(f"表格 {len(rows)} 行，需要 {t['rows'][0]} 到 {t['rows'][1]} 行，多了就拆页")
        long_cells = [c for r in rows for c in r if clen(str(c)) > _m(t["cell"])]
        if long_cells:
            out.append(f"{len(long_cells)} 个单元格超过 {_m(t['cell'])} 字")
    if "chart" in cap:
        c = cap["chart"]
        specs = slide.get("charts") or [slide.get("chart") or {}]
        if len(specs) > 3:
            out.append(f"一页 {len(specs)} 个图表，最多 3 个，多了就拆页")
        for k, spec in enumerate(specs):
            tag = f"第 {k + 1} 个图表" if len(specs) > 1 else "图表"
            spec = spec or {}
            cats, ser = spec.get("categories", []), spec.get("series", [])
            if not (c["series"][0] <= len(ser) <= c["series"][1]):
                out.append(f"{tag} {len(ser)} 组数据，需要 {c['series'][0]} 到 {c['series'][1]} 组")
            if spec.get("type") == "scatter":
                # a scatter chart has no categories: each series carries its own x values
                for sr in ser:
                    xs, ys = sr.get("x", []), sr.get("values", [])
                    if len(xs) != len(ys):
                        out.append(f"{tag}的数据组 {sr.get('name', '')} x 和 values 个数不一致")
                    if not (2 <= len(ys) <= 60):
                        out.append(f"{tag}的数据组 {sr.get('name', '')} 有 {len(ys)} 个点，需要 2 到 60 个")
                continue
            if not (c["categories"][0] <= len(cats) <= c["categories"][1]):
                out.append(f"{tag} {len(cats)} 个分类，需要 {c['categories'][0]} 到 {c['categories'][1]} 个")
            for sr in ser:
                if len(sr.get("values", [])) != len(cats):
                    out.append(f"{tag}的数据组 {sr.get('name', '')} 的数值个数和分类个数不一致")
            if spec.get("type") in ("pie", "doughnut") and len(ser) > 1:
                out.append("饼图和环形图只能有一组数据")
    if "framework" in cap:
        fw = slide.get("framework") or {}
        kind = fw.get("kind")
        lim = cap["framework"].get(kind)
        if not lim:
            out.append(f"framework.kind 只能是 {', '.join(cap['framework'])}")
        else:
            lo, hi, mx = lim
            for k, v in (fw.get("blocks") or {}).items():
                v = v if isinstance(v, list) else [v]
                if len(v) > hi:
                    out.append(f"{kind} 的 {k} 有 {len(v)} 条，最多 {hi} 条")
                for x in v:
                    if clen(_txt(x)) > _m(mx):
                        out.append(f"{kind} 的 {k} 有一条约 {clen(_txt(x))} 字，最多 {_m(mx)}")
    return out


def summary(layout):
    cap = CAPACITY.get(layout, {})
    parts = []
    if "items" in cap:
        lo, hi = cap["items"]
        its = "，".join(f"{k}≤{v}" for k, v in cap.get("item", {}).items())
        parts.append(f"items {lo}-{hi} 条（{its}）")
    for f, (lo, hi, mx) in cap.get("lists", {}).items():
        parts.append(f"{f} {lo}-{hi} 条（每条≤{mx}）")
    if "quadrants" in cap:
        parts.append("4 个象限（标题≤8，每格≤3 条、每条≤14）")
    if "table" in cap:
        t = cap["table"]
        parts.append(f"{t['columns'][0]}-{t['columns'][1]} 列，{t['rows'][0]}-{t['rows'][1]} 行，单元格≤{t['cell']}")
    if "chart" in cap:
        parts.append("分类 2-8 个（散点图不限分类），数据 1-3 组，一页最多 3 个图表，结论≤3 条")
    if "framework" in cap:
        parts.append("每格≤4 条、每条≤16 字（画布每格≤3 条、每条≤14 字）")
    fl = "，".join(f"{k}≤{v}" for k, v in cap.get("fields", {}).items())
    if fl:
        parts.append(fl)
    return "；".join(parts)
