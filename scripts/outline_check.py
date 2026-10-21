#!/usr/bin/env python3
"""Generation step 2: check a drafted deck.json before any design work, and render it
as outline.md for the user to confirm.

Usage:
  python outline_check.py WORK_DIR            check + write WORK_DIR/outline.md
  python outline_check.py WORK_DIR --strict   exit 1 on WARN as well as ERROR

Checks (rules are explained in references/generate.md)
  titles     every content slide has a title that states a point; bare topic labels such as
             "背景介绍" "注意事项" "总结" are flagged; length 4-22 characters
  ghost      prints all titles in order: read them alone, they should tell the story
  density    on-screen text per slide against meta.density (low: 口播/演讲, high: 阅读/汇报)
  items      list length against the density limit, split the slide if exceeded
  notes      speaker notes present and roughly 40-260 characters when meta.notes is on
  pages      page count against analysis.json
  flow       the same slide type three times in a row; long decks without section slides;
             a closing slide that only says thanks
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_json, strip_marks  # noqa: E402
import capacity  # noqa: E402
import layouts as LY  # noqa: E402

LIMITS = {  # on-screen characters (notes excluded) and list length per slide
    "low": {"chars": 100, "items": 4},
    "high": {"chars": 200, "items": 6},
}
TOPIC_WORDS = ["介绍", "概述", "简介", "总结", "背景", "目录", "注意事项", "优势", "方法", "原理", "概况",
               "现状", "分析", "说明", "要点", "内容", "问题", "结论", "谢谢", "感谢", "Q&A", "结束"]
NON_SCREEN = {"n", "uid", "type", "layout", "notes", "page", "emphasis", "icon", "purpose", "show_footer", "source",
              "chart", "charts", "art", "logo", "section", "kind", "highlight_col", "image", "at", "frame", "flow", "tone", "boxed", "stamps"}
NO_TITLE_TYPES = {"cover", "closing", "section", "toc", "question", "big_quote"}


def screen_text(obj, key=None):
    """All on-screen strings of a slide (notes and metadata excluded)."""
    if key in NON_SCREEN:
        return []
    if isinstance(obj, str):
        return [strip_marks(obj)]
    if isinstance(obj, list):
        return [t for x in obj for t in screen_text(x)]
    if isinstance(obj, dict):
        return [t for k, v in obj.items() for t in screen_text(v, k)]
    return []


def clen(s):
    """Length in reading units: a CJK character or a latin word counts as one."""
    return len(re.findall(r"[一-鿿]", s)) + len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'\.\-]*", s))


def looks_like_topic(title):
    t = strip_marks(title).strip()
    if not t:
        return False
    for w in TOPIC_WORDS:
        # "X介绍" / "注意事项" / "总结" alone = a label; allow them inside a longer claim
        if t.endswith(w) and clen(t) <= len(w) + 6:
            return True
    return t.startswith(("什么是", "如何", "怎么")) and clen(t) <= 8 and not re.search(r"[，,：:]", t)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()
    work = Path(a.work)
    deck = load_json(work / "deck.json")
    meta = deck.get("meta", {})
    capacity.set_projection(meta.get("projection"))
    slides = deck.get("slides", [])
    density = meta.get("density", "low")
    lim = LIMITS.get(density, LIMITS["low"])
    notes_on = meta.get("notes", True)
    issues = []

    def add(level, n, msg):
        issues.append((level, n, msg))

    # titles + ghost deck
    ghost = []
    for s in slides:
        n, typ = s.get("n"), s.get("type", "")
        title = s.get("title") or s.get("headline") or s.get("question") or s.get("quote") or ""
        ghost.append((n, typ, strip_marks(title)))
        if typ in NO_TITLE_TYPES:
            continue
        if not title:
            add("ERROR", n, "缺少标题")
            continue
        L = clen(strip_marks(title))
        if looks_like_topic(title):
            add("WARN", n, f"标题像话题标签，改成一句结论：{title}")
        if L < 4 or L > 22:
            add("WARN", n, f"标题长度 {L}，建议 4 到 22：{title}")
    # density + items + notes
    for s in slides:
        n, typ = s.get("n"), s.get("type", "")
        txt = screen_text(s)
        total = sum(clen(t) for t in txt)
        cap = lim["chars"] * (1.4 if typ in ("cover", "closing") else 1)
        if total > cap:
            add("WARN", n, f"屏幕文字约 {total} 字，超过 {density} 密度上限 {int(cap)}，考虑拆页或把展开内容挪进备注")
        items = s.get("items", [])
        if len(items) > lim["items"]:
            add("WARN", n, f"{len(items)} 条要点，超过 {density} 密度上限 {lim['items']} 条，建议拆成两页")
        if notes_on and typ not in ("section", "toc"):
            nt = strip_marks(s.get("notes", ""))
            if not nt:
                add("WARN", n, "没有口播备注")
            elif clen(nt) < 40 or clen(nt) > 260:
                add("WARN", n, f"备注约 {clen(nt)} 字，口播一页建议 40 到 260 字")
    # layout capacity: does the content fit the layout it will get?
    for s in slides:
        lay = s.get("layout") or LY.TYPE_TO_LAYOUTS.get(s.get("type"), ["list_icons"])[0]
        probs = capacity.check(s, lay)
        if probs:
            alts = [a for a in LY.TYPE_TO_LAYOUTS.get(s.get("type"), [])[1:] + ["list_icons", "grid_cards"]
                    if a != lay and not capacity.check(s, a)]
            hint = f"；可改用 {alts[0]}" if alts and not s.get("layout") else "；精简文字或拆页"
            add("WARN", s.get("n"), f"{lay} 装不下：" + "；".join(probs[:3]) + hint)
    # pages
    an = work / "analysis.json"
    if an.exists():
        p = load_json(an).get("pages", {})
        if p and not (p.get("min", 0) <= len(slides) <= p.get("max", 999)):
            add("WARN", 0, f"共 {len(slides)} 页，素材分析建议 {p.get('min')} 到 {p.get('max')} 页")
    # flow
    for i in range(2, len(slides)):
        t = [slides[j].get("type") for j in (i - 2, i - 1, i)]
        if t[0] == t[1] == t[2] and t[0] not in ("section",):
            add("WARN", slides[i].get("n"), f"连续三页都是 {t[0]}，换一种页型或版式")
    if len(slides) > 15 and not any(s.get("type") == "section" for s in slides):
        add("WARN", 0, "超过 15 页，建议加章节分隔页（type: section）")
    if slides and slides[-1].get("type") == "closing":
        h = strip_marks(slides[-1].get("headline") or slides[-1].get("title") or "")
        if re.fullmatch(r"(谢谢|感谢)(观看|收听|聆听|大家)?[！!。]?|Thanks?.*|Q&A", h.strip()):
            add("WARN", slides[-1].get("n"), "结尾页只有致谢，换成一句结论或行动号召")
    if slides and slides[0].get("type") != "cover":
        add("WARN", slides[0].get("n"), "第一页不是封面")

    # outline.md for the user
    out = [f"# {meta.get('title', '')} 大纲", ""]
    out.append(f"场景 {meta.get('scenario', '')} · 受众 {meta.get('audience', '')} · 密度 {density} · 共 {len(slides)} 页")
    if meta.get("storyline"):
        out += ["", f"故事线：{meta['storyline']}"]
    out += ["", "## 只读标题（幽灵稿）", ""] + [f"{n}. {t}" for n, _, t in ghost]
    out += ["", "## 逐页", ""]
    for s in slides:
        title = s.get("title") or s.get("headline") or s.get("question") or s.get("quote") or ""
        out.append(f"### {s.get('n')} · {s.get('type', '')} · {strip_marks(title)}")
        if s.get("purpose"):
            out.append(f"- 作用：{s['purpose']}")
        body = [t for t in screen_text(s) if t != strip_marks(title)]
        if body:
            out.append("- 屏幕：" + " / ".join(body))
        if s.get("notes"):
            out.append("- 口播：" + strip_marks(s["notes"]))
        out.append("")
    (work / "outline.md").write_text("\n".join(out), encoding="utf-8")

    print("幽灵稿（只读标题）")
    for n, typ, t in ghost:
        print(f"  {n:>2}. [{typ}] {t}")
    print()
    order = {"ERROR": 0, "WARN": 1}
    for level, n, msg in sorted(issues, key=lambda x: (order[x[0]], x[1] or 0)):
        where = f"第 {n} 页" if n else "整体"
        print(f"[{level}] {where}：{msg}")
    errs = sum(1 for i in issues if i[0] == "ERROR")
    warns = len(issues) - errs
    print(f"\nERROR {errs}  WARN {warns}   已写出 {work/'outline.md'}")
    sys.exit(1 if errs or (a.strict and warns) else 0)


if __name__ == "__main__":
    main()
