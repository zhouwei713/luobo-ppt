#!/usr/bin/env python3
"""Five-dimension design self-review: measure the evidence, leave the judgement to the reviewer.

Usage:
  python review.py WORK_DIR

Reads out/layout_dump.json, out/qa_report.json, deck.json and style.json, and writes
out/review.md: one evidence table per dimension (numbers a script can count), empty
score slots, and the rubric from references/critique.md in short form. Claude then
looks at out/sheet.png and the page PNGs, fills in the scores and the Keep / Fix /
Quick-win lists, fixes what is cheap, and reports the verdict when delivering.

Dimensions: 统一 (one direction throughout), 层级 (what to read first),
细节 (alignment, spacing, small defects), 传达 (does each page land its point),
节奏 (variety and pacing across the deck).
"""
import argparse
import statistics as st
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_json, load_style, clen, CANVAS_W  # noqa: E402

CONTENT_ROLES_SKIP = ("background", "decor", "chrome")
NEUTRALS = {"FFFFFF", "000000", "1A1A1A", "111111"}  # ink_on() picks these for text on fills


def content_texts(sd):
    return [e for e in sd["elements"] if e["t"] == "text" and e.get("role") not in CONTENT_ROLES_SKIP]


def near_misses(values, tol_lo=0.03, tol_hi=0.18):
    """Pairs of edges that almost line up: closer than tol_hi but not equal. Usually a slip."""
    vs = sorted(set(round(v, 2) for v in values))
    return [(a, b) for a, b in zip(vs, vs[1:]) if tol_lo < b - a < tol_hi]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    a = ap.parse_args()
    work = Path(a.work)
    out = work / "out"
    dump = load_json(out / "layout_dump.json")
    deck = load_json(work / "deck.json")
    style = load_style(work / "style.json")
    # a missing report, or one older than the layout dump, means QA did not check this build
    rp = out / "qa_report.json"
    qa_ran = rp.exists() and rp.stat().st_mtime >= (out / "layout_dump.json").stat().st_mtime
    qa = load_json(rp) if qa_ran else {"issues": [], "counts": {}}
    qa_errors = qa.get("counts", {}).get("ERROR", 0) if qa_ran else "QA 没跑完（报告缺失或过期），先重跑 qa_check.py"
    slides = dump["slides"]
    n = len(slides)

    # ---- 统一
    sizes = Counter()
    fonts = Counter()
    raw_colors = Counter()
    radii = Counter()
    for sd in slides:
        for e in sd["elements"]:
            if e.get("role") in CONTENT_ROLES_SKIP:
                continue
            if e["t"] == "text":
                sizes[e["size"]] += 1
                fonts[e.get("font", "body")] += 1
            for k in ("color", "fill"):
                v = str(e.get(k) or "")
                if (v and v.lstrip("#").isalnum() and len(v.lstrip("#")) == 6 and v.split("@")[0] not in style.palette
                        and v.lstrip("#").upper() not in NEUTRALS):
                    raw_colors[v] += 1
            # cards only: pills (radius = h/2), hairlines and tiny marks are not cards
            if (e["t"] == "rect" and e.get("radius") and e["w"] > 1.0 and e["h"] > 0.6
                    and e["radius"] < min(e["w"], e["h"]) / 2 - 0.01):
                radii[round(e["radius"], 2)] += 1
    unity = [
        ("全篇字号种数（不含页眉页脚）", len(sizes), "8 种以内好，超过 10 种就散"),
        ("用到的字体角色", ", ".join(f"{k}×{v}" for k, v in fonts.most_common()), "display 只该出现在封面、大数字、章节号"),
        ("色板之外的颜色", len(raw_colors), "应为 0"),
        ("卡片圆角种数", len(radii), "1 到 2 种"),
    ]

    # ---- 层级
    hier_rows, weak = [], []
    for sd in slides:
        ts = content_texts(sd)
        if not ts:
            continue
        big = max(t["size"] for t in ts)
        body = st.median([t["size"] for t in ts])
        per = len({t["size"] for t in ts})
        ratio = big / body if body else 0
        hier_rows.append((sd["n"], big, body, round(ratio, 2), per))
        if ratio < 1.5 or per > 5:
            weak.append(sd["n"])
    hierarchy = [
        ("最大字号与中位字号之比 < 1.5 或单页超过 5 种字号的页", weak or "无", "主角不突出，或者字号太碎"),
    ]

    # ---- 细节
    miss = []
    for sd in slides:
        ts = content_texts(sd)
        lefts = [t["x"] for t in ts if t.get("align", "l") == "l"]
        m = near_misses(lefts)
        if m:
            miss.append(f"{sd['n']}：{', '.join(f'{x:.2f}/{y:.2f}' for x, y in m[:3])}")
    warn_by = Counter(i["check"] for i in qa.get("issues", []) if i["level"] == "WARN")
    detail = [
        ("左边缘差一点没对齐（英寸）", "；".join(miss) if miss else "无", "0.03 到 0.18 英寸的错位多半是失误"),
        ("QA 警告分布", ", ".join(f"{k}×{v}" for k, v in warn_by.most_common()) or "无", "contrast、rail、accent 优先处理"),
        ("QA 错误", qa_errors, "必须为 0"),
    ]

    # ---- 传达
    dens, no_notes = [], []
    for s in deck["slides"]:
        from outline_check import screen_text
        c = sum(clen(t) for t in screen_text(s))
        dens.append((s["n"], c))
        if not s.get("notes") and s.get("type") not in ("cover", "section", "toc", "closing"):
            no_notes.append(s["n"])
    heavy = [f"{k}({c})" for k, c in dens if c > 160]
    convey = [
        ("屏幕字数超过 160 的页", ", ".join(heavy) or "无", "字多的页要么拆，要么换成更有结构的版式"),
        ("没有口播备注的内容页", no_notes or "无", "口播稿要求每页都有"),
        ("标题平均字数", round(st.mean(clen(s.get("title") or s.get("headline") or s.get("question") or s.get("quote") or "") for s in deck["slides"]), 1),
         "结论式标题通常 10 到 20 字"),
    ]

    # ---- 节奏
    layouts = [sd["layout"] for sd in slides]
    runs = [layouts[i] for i in range(2, n) if layouts[i] == layouts[i - 1] == layouts[i - 2]]
    counts = [c for _, c in dens]
    heroes = sum(1 for sd in slides for e in sd["elements"] if e["t"] == "image" and e.get("role") not in ("background", "decor"))
    rhythm = [
        ("用到的版式种数 / 页数", f"{len(set(layouts))} / {n}", "至少一半"),
        ("连续三页同版式", runs or "无", "应为无"),
        ("字数起伏（标准差 / 平均）", round(st.pstdev(counts) / max(1, st.mean(counts)), 2) if counts else 0,
         "0.3 到 0.7 有呼吸感；太低像流水账，太高忽密忽疏"),
        ("插画数量", heroes, "封面、章节、结论页有图就够，不必页页有"),
    ]

    def table(rows):
        lines = ["| 检查项 | 结果 | 参考 |", "|---|---|---|"]
        lines += [f"| {a} | {b} | {c} |" for a, b, c in rows]
        return "\n".join(lines)

    md = [f"# 设计自评：{deck.get('meta', {}).get('title', work.name)}", "",
          "先看 out/sheet.png 和逐页 PNG，再结合下面的数字打分。每项 0 到 10 分，"
          "0 到 4 不及格，5 到 6 能用，7 到 8 扎实，9 到 10 出彩。分数别平均掉，哪项差就直说哪项差。", "",
          "## 1 统一：整套是不是一个方向到底", "", table(unity), "", "分数：", "",
          "## 2 层级：陌生人能不能一眼看出先读什么", "", table(hierarchy), "",
          "| 页 | 最大字号 | 中位字号 | 比值 | 字号种数 |", "|---|---|---|---|---|",
          *[f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} |" for r in hier_rows], "", "分数：", "",
          "## 3 细节：对齐、间距、小瑕疵", "", table(detail), "", "分数：", "",
          "## 4 传达：每页的观点有没有落地", "", table(convey), "", "分数：", "",
          "## 5 节奏：翻页时有没有起伏", "", table(rhythm), "", "分数：", "",
          "## 结论", "", "一句话判断：", "",
          "保留（做对了、别动）：", "", "要修（影响观感的问题，交付前修掉）：", "",
          "顺手改（几分钟就能改好、效果明显）：", ""]
    (out / "review.md").write_text("\n".join(md), encoding="utf-8")
    print(f"wrote {out / 'review.md'}")
    print(f"  字号 {len(sizes)} 种，版式 {len(set(layouts))}/{n}，层级偏弱的页 {weak or '无'}，"
          f"对齐疑点 {len(miss)} 页，QA 错误 {qa_errors}")
    return 0 if qa_ran else 1


if __name__ == "__main__":
    sys.exit(main())
