#!/usr/bin/env python3
"""Step 3: draft plan.json (layout per slide, icons, asset list with prompts).

Usage:
  python plan_deck.py WORK_DIR [--level light|standard|full]

Reads deck.json + style.json. Claude reviews the result and edits hero prompts,
icons and layouts before running make_assets.py.

Levels
  light     palette + master + layouts + icons, no illustrations
  standard  + illustrations on cover, closing and slides with a large hero slot
  full      + an illustration on every slide that has a slot (the look of the sample)
"""
import argparse
import sys
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_json, save_json, SKILL_DIR, ASSET_DIR, list_icons  # noqa: E402
import layouts as L  # noqa: E402

KW = load_json(ASSET_DIR / "icon_keywords.json")
ICONS = set(list_icons())

DEFAULT_ICONS = {
    "cover_hero": ["flame", "rocket", "alert-triangle", "lightbulb"],
    "rows_side": ["smartphone", "cpu", "message-circle", "tag"],
    "stats_row": ["download", "trending-up", "users", "bar-chart"],
    "side_cards": ["sliders", "link", "check-circle", "arrow-right"],
    "cards_quote": ["ban", "badge-alert", "alert-triangle"],
    "list_icons": ["check-circle", "lightbulb", "star", "target", "flag"],
    "grid_cards": ["check-circle", "lightbulb", "star", "target", "flag", "sparkles"],
    "steps_flow": ["pen", "wand", "send", "check-circle", "flag"],
    "compare_split": ["check-circle"],
    "cycle": ["refresh"],
    "pyramid": ["layers"],
    "section": ["flag"],
    "toc": ["list"],
    "toc_row": ["list"],
    "hub": ["sparkles", "star", "target", "flag", "lightbulb", "check-circle"],
    "quote_cards": ["message-circle"],
    "media_text": ["lightbulb"],
    "statement_hero": ["check-circle"],
    "closing": ["arrow-right"],
}

# hero idea + fallback scene per layout
HERO_IDEAS = {
    "cover_hero": ("hero shot of {anchor}, floating above a soft round pedestal, a few small floating badges around it", "tile"),
    "statement_number": ("{anchor}, shown as the single friendly hero of the scene, simple and iconic", "tile"),
    "rows_side": ("three neat stacked cards with small symbols, next to a small {anchor}", "cards"),
    "stats_row": ("{anchor} next to a rising bar chart with an upward arrow", "chart"),
    "media_text": ("a secure glowing cloud computer with a shield, related to {topic}", "badge"),
    "side_cards": ("a checklist card with a big check mark, related to {topic}", "cards"),
    "quote_cards": ("a friendly chat bubble with quote marks, related to {topic}", "badge"),
    "statement_hero": ("{anchor} doing a small safe task, like reading a document, calm mood", "cards"),
    "cards_quote": ("a caution sign with {anchor} nearby, gentle not scary", "badge"),
    "list_icons": ("a small iconic object representing {topic}", "badge"),
    "grid_cards": ("a small iconic object representing {topic}", "badge"),
    "steps_flow": ("a small path of stepping stones leading to a flag, related to {topic}", "cards"),
    "section": ("{anchor}, calm and iconic, introducing a new chapter", "tile"),
    "closing": ("{anchor} waving hello, optimistic and inviting", "tile"),
}

FOCUS = {
    "cover_hero": "大标题和主视觉", "statement_number": "大数字", "rows_side": "对照卡片", "stats_row": "数字",
    "media_text": "左侧示意图", "side_cards": "主色重点卡片", "quote_cards": "例句卡片", "statement_hero": "一句主张",
    "cards_quote": "右侧金句", "list_icons": "要点列表", "grid_cards": "要点卡片", "steps_flow": "步骤编号和连线",
    "compare_split": "左右对比", "cycle": "循环圆环", "pyramid": "层级", "section": "章节编号", "closing": "行动号召按钮",
    "toc": "章节编号和标题", "toc_row": "章节编号和标题",
    "cover_type": "超大标题和强调词", "question": "一句大问句", "big_quote": "引文本身",
    "timeline": "时间轴和当前节点", "funnel": "逐层收窄的漏斗", "hub": "中心圆和连线", "matrix": "高亮象限",
    "table": "高亮列", "chart": "图表里的高亮数据", "framework": "框架全貌",
    "free": "自定",
}

SIZES = {"large": (1400, 1300), "side": (1400, 900), "corner": (1400, 830), "top": (1400, 1050)}


def pick_icon(text, used, default, strong=""):
    """Keyword match; words found in `strong` (e.g. an item title) count double."""
    best, score = None, 0
    for name, words in KW.items():
        if name not in ICONS or name in used:
            continue
        sc = sum(len(w) * (2 if strong and w.lower() in strong.lower() else 1)
                 for w in words if w and w.lower() in (strong + text).lower())
        if sc > score:
            best, score = name, sc
    return best or default


def write_spec(work, deck, plan):
    """design_spec.md: the one page the user confirms before pictures are made."""
    meta = deck.get("meta", {})
    try:
        from common import load_style
        st = load_style(work / "style.json")
        P, F = st.palette, st.fonts
        style_line = (f"{st.data.get('name', '')} · 主色 #{P['primary']} · 强调 #{P['accent']} · 背景 #{P['bg_top']}→#{P['bg_bottom']}"
                      f" · 字体 {F['heading_ea']} / {F['heading_latin']}")
        rules = st.data.get("rules", [])
    except Exception:
        style_line, rules = "（style.json 未就绪）", []
    heroes = {x["id"]: x for x in plan["assets"] if x["kind"] == "hero"}
    for x in plan["assets"]:
        for it in x.get("items", []):
            heroes[it["id"]] = it
    by_n = {s["n"]: s for s in deck["slides"]}
    lines = [f"# 设计规格 · {meta.get('title', '')}", "",
             f"- 风格：{style_line}",
             f"- 美化力度：{plan['level']}，共 {len(plan['slides'])} 页，插画 {len(heroes)} 张",
             f"- 视觉锚点：{(meta.get('anchor') or {}).get('description', '（未设置）')}"]
    if rules:
        lines += ["- 风格硬规则：" + "；".join(rules)]
    lines += ["", "| 页 | 标题 | 版式 | 视觉焦点 | 插画 |", "| --- | --- | --- | --- | --- |"]
    for p in plan["slides"]:
        s = by_n.get(p["n"], {})
        title = (s.get("title") or s.get("headline") or s.get("question") or s.get("quote") or "").replace("**", "").replace("|", "/")
        h = heroes.get(p.get("hero", ""), {})
        lines.append(f"| {p['n']} | {title} | {p['layout']} | {p.get('focus', '')} | {h.get('prompt', '-')[:60]} |")
    warn = [(p["n"], w) for p in plan["slides"] for w in p.get("capacity_warnings", [])]
    if warn:
        lines += ["", "容量提醒（出图前先处理）："] + [f"- 第 {n} 页：{w}" for n, w in warn]
    lines += ["", "确认后再出图；要调整就改 plan.json 里对应页的 layout、icons 或插画 prompt。"]
    (work / "design_spec.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("--level", default="full", choices=["light", "standard", "full"])
    ap.add_argument("--sheets", action="store_true",
                    help="group small corner/side illustrations into shared sheets (one AI call per 3-4 pictures)")
    ap.add_argument("--reset", action="store_true",
                    help="re-plan every slide; by default slides whose deck.json content did not change keep their "
                         "existing plan (layout, icons, hand-edited hero prompts)")
    a = ap.parse_args()
    work = Path(a.work)
    deck = load_json(work / "deck.json")
    meta = deck.get("meta", {})
    anchor = (meta.get("anchor") or {}).get("description") or f"a glossy rounded app icon for {meta.get('title', 'the topic')}"
    # the tile carries the title's first character when it is a letter; "2026 年…" would put a
    # lone "2" (or a stray "年") on the cover, so then the first latin letter, else an icon
    tt = (meta.get("title", "") or "").strip()
    first = tt[:1] if re.match(r"[A-Za-z\u4e00-\u9fff]", tt) else (re.search(r"[A-Za-z]", tt) or [None])[0]
    glyph = (meta.get("anchor") or {}).get("glyph") or (first.upper() if first else None)
    topic = meta.get("topic") or meta.get("title", "")
    slides, assets = [], []
    try:
        _st = load_json(work / "style.json")
        style_prefs = _st.get("prefer_layouts", {})
        style_skip = set((_st.get("illustration") or {}).get("skip_layouts", []))
    except Exception:
        _st, style_prefs, style_skip = {}, {}, set()
    # a brand's mascot is not wallpaper: it shows on the cover, section and closing pages and
    # on pages that ask for it ("art": true or a mood such as "question"), large, a few times
    brand = _st.get("brand") or {}
    arts = [a if isinstance(a, dict) else {"file": a} for a in brand.get("art", [])]
    art_max = brand.get("art_max", 4)
    BIG = ("cover_hero", "cover_center", "cover_type", "section", "closing")
    art_used = []

    def pick_art(asked):
        if isinstance(asked, str):
            for a in arts:
                if asked in (a.get("mood"), Path(a["file"]).stem, a["file"]) or asked in (a.get("moods") or []):
                    return a["file"]
        fresh = [a["file"] for a in arts if a["file"] not in art_used]
        return (fresh or [a["file"] for a in arts])[0]
    assets += [{"id": "bg_content", "kind": "background", "variant": "content"},
               {"id": "bg_cover", "kind": "background", "variant": "cover"},
               {"id": "bg_closing", "kind": "background", "variant": "closing"},
               {"id": "decor_leaf_l", "kind": "decor", "shape": "leaf"},
               {"id": "decor_leaf_r", "kind": "decor", "shape": "leaf", "flip": True},
               {"id": "decor_brush", "kind": "decor", "shape": "brush"}]
    prev = None
    for s in deck["slides"]:
        cands = list(L.TYPE_TO_LAYOUTS.get(s.get("type"), ["list_icons"]))
        items_ = s.get("items", [])
        short = items_ and 2 <= len(items_) <= 6 and all(len((it.get("text") or "") + (it.get("title") or "")) <= 22 for it in items_)
        if s.get("type") == "list" and short:
            cands = ["grid_cards", "list_icons"]  # few short points read better as big cards
        import capacity
        capacity.set_projection(meta.get("projection"))
        fits = [c for c in cands if not capacity.check(s, c)]
        if not s.get("layout") and fits and fits[0] != cands[0]:
            cands = fits + [c for c in cands if c not in fits]
        pref = (style_prefs.get(s.get("type")) if style_prefs else None)
        if pref in cands and not capacity.check(s, pref):
            cands = [pref] + [c for c in cands if c != pref]
        layout = s.get("layout") or cands[0]
        if layout == prev and len(cands) > 1 and not s.get("layout"):
            layout = cands[1] if not capacity.check(s, cands[1]) else layout
        prev = layout
        cap_probs = capacity.check(s, layout)
        items = s.get("items", [])
        used, icons = set(), []
        defaults = DEFAULT_ICONS.get(layout, ["check-circle"])
        if items:
            for i, it in enumerate(items):
                ic = pick_icon(it.get("text", "") + it.get("label", ""), used,
                               defaults[i % len(defaults)], strong=it.get("title", ""))
                used.add(ic)
                icons.append(ic)
        else:
            src = s.get("callout") or s.get("lead") or s.get("pill") or s.get("cta") or ""
            icons.append(pick_icon(src, used, defaults[0]))
        ps = {"n": s["n"], "layout": layout, "icons": icons,
              "purpose": s.get("purpose", ""), "focus": FOCUS.get(layout, ""), "relation": ""}
        if cap_probs:
            ps["capacity_warnings"] = cap_probs
        if s.get("lead"):
            ps["lead_icon"] = pick_icon(s["lead"], set(), "message-circle")
        if s.get("takeaway"):
            ps["takeaway_icon"] = pick_icon(s["takeaway"], set(), "info")
        slot = L.HERO_SLOT.get(layout)
        want = slot and (a.level == "full" or (a.level == "standard" and (slot in ("large", "top") or layout == "cover_hero")))
        if layout in style_skip:
            want = False  # the style lets typography carry these pages
        asked = s.get("art")
        if arts:
            if asked is False:
                want = False
            elif asked:
                want = bool(slot)
            else:
                want = bool(slot) and layout in BIG
            if want and layout not in BIG and len(art_used) >= art_max:
                want = False
        if want:
            hid = f"hero_{s['n']:02d}"
            idea, scene = HERO_IDEAS.get(layout, HERO_IDEAS["list_icons"])
            w, h = SIZES.get(slot, (1400, 1200))
            assets.append({"id": hid, "kind": "hero", "slide": s["n"], "size": [w, h], "transparent": True,
                           "prompt": idea.format(anchor=anchor, topic=topic),
                           "fallback": {"scene": scene, "glyph": glyph if scene == "tile" else None}})
            ps["hero"] = hid
            if arts:
                assets[-1]["art"] = pick_art(asked)
                art_used.append(assets[-1]["art"])
        slides.append(ps)
    if a.sheets:
        small = [x for x in assets if x["kind"] == "hero" and x["size"][1] <= 900]
        rest = [x for x in assets if x not in small]
        for k in range(0, len(small), 4):
            grp = small[k:k + 4]
            if len(grp) == 1:
                rest.append(grp[0])
                continue
            rest.append({"id": f"sheet_{k // 4 + 1:02d}", "kind": "sheet", "items": grp})
        assets = rest
    # keep hand edits: a slide whose content is unchanged since the last plan keeps its old plan entry
    # (notes and the uid are not content: adding a uid to an old deck must not re-plan every page)
    import hashlib
    import json as _json
    def h(sl):
        return hashlib.sha1(_json.dumps({k: v for k, v in sl.items() if k not in ("notes", "uid")}, ensure_ascii=False,
                                        sort_keys=True).encode("utf-8")).hexdigest()[:12]
    deck_by_n = {sl["n"]: sl for sl in deck["slides"]}
    for ps in slides:
        ps["src_hash"] = h(deck_by_n[ps["n"]])
    old_path = work / "plan.json"
    kept = []
    if old_path.exists() and not a.reset:
        old = load_json(old_path)
        old_slides = {p["n"]: p for p in old.get("slides", [])}
        old_assets = {x["id"]: x for x in old.get("assets", [])}
        for x in old.get("assets", []):  # heroes that live inside an old sheet
            for it in x.get("items", []):
                old_assets[it["id"]] = it
        for k, ps in enumerate(slides):
            op = old_slides.get(ps["n"])
            if op and op.get("src_hash") == ps["src_hash"]:
                slides[k] = op
                kept.append(ps["n"])
                hid = op.get("hero")
                if hid and hid in old_assets:
                    # put the old (possibly hand-edited) hero back in place of the new one
                    def swap(lst):
                        for j, x in enumerate(lst):
                            if x.get("id") == hid:
                                lst[j] = old_assets[hid]
                                return True
                            if x.get("kind") == "sheet" and swap(x.get("items", [])):
                                return True
                        return False
                    if not swap(assets):
                        assets.append(old_assets[hid])
            elif op and ps["layout"] == "free" and op.get("elements") and not deck_by_n[ps["n"]].get("elements"):
                # content changed, but hand-placed elements only exist in the old plan
                ps["elements"] = op["elements"]
                if op.get("master"):
                    ps["master"] = op["master"]
    for ps in slides:
        if ps["layout"] == "free" and not ps.get("elements") and not deck_by_n[ps["n"]].get("elements"):
            print(f"ERROR slide {ps['n']}: free 版式没有 elements，页面会是空的；写进 deck.json 或 plan.json 这一页")
    plan = {"level": a.level, "confirmed": False, "slides": slides, "assets": assets}
    save_json(plan, work / "plan.json")
    if kept:
        print(f"保留了 {len(kept)} 页原有规划（内容没变）：{kept}；要全部重排加 --reset")
    write_spec(work, deck, plan)
    for p in slides:
        print(f"  {p['n']:>2}  {p['layout']:<17} hero={p.get('hero') or '-':<8} icons={p['icons']}")
        for w in p.get("capacity_warnings", []):
            print(f"      ! 超出容量：{w}")
    n_pics = sum(len(x.get("items", [])) if x["kind"] == "sheet" else 1 for x in assets if x["kind"] in ("hero", "sheet"))
    print(f"wrote {work/'plan.json'} and design_spec.md ({n_pics} illustrations)")


if __name__ == "__main__":
    main()
