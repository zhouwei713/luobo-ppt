#!/usr/bin/env python3
"""Show, don't ask: render three style options with the user's own content.

Usage:
  python style_previews.py WORK_DIR --auto                 pick 3 presets (safe / bold / wildcard)
  python style_previews.py WORK_DIR --presets mint-fresh,dark-tech,paper-notes
  python style_previews.py WORK_DIR --apply dark-tech      copy the chosen preset to WORK_DIR/style.json
  python style_previews.py --sample --all                  rebuild the skill's own preset gallery

Each option is a real cover + the first content slide of deck.json, built with the preset and
procedural pictures (fast, no model cost). Output: WORK_DIR/previews/sheet.png with rows
numbered 1-3. Slides carry only the user's content; preset names are listed in chat, never
drawn on the slides.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import load_json, save_json, SKILL_DIR, ASSET_DIR, get_font, style_file  # noqa: E402


SAMPLE = {"meta": {"title": "示例", "series": "三分钟看懂", "anchor": {"description": "a glossy app icon", "glyph": "AI"}},
          "slides": [{"n": 1, "type": "cover", "kicker": "三分钟看懂", "title": "一个能替你办事的 AI",
                      "subtitle": "不是聊天，是动手", "items": [{"text": "它是什么"}, {"text": "怎么上手"}, {"text": "有哪些坑"}]},
                     {"n": 2, "type": "stats", "title": "它火得数据很硬",
                      "items": [{"value": "73万", "label": "上线 5 天下载"}, {"value": "250万", "label": "13 天累计下载"},
                                {"value": "3倍", "label": "日活对比同期"}],
                      "takeaway": "真有人天天在用，不是一阵风", "page": "02 / 11"}]}


def run(args):
    # the child scripts print UTF-8; decode it as such, not with the console code page (GBK on Chinese Windows)
    return subprocess.run([sys.executable] + [str(a) for a in args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env={**os.environ, "PYTHONIOENCODING": "utf-8"})


def pick_auto(work):
    idx = load_json(style_file("index"))["styles"]
    text = ""
    for f in ("source.md", "deck.json"):
        if (work / f).exists():
            text += (work / f).read_text(encoding="utf-8", errors="ignore")
    scen = ""
    if (work / "analysis.json").exists():
        scen = load_json(work / "analysis.json").get("scenario", "")
    try:
        from imagegen import find_config
        has_ai = (find_config(work_dir=work).get("provider") or "none") != "none"
    except Exception:
        has_ai = False
    scored = []
    for st in idx:
        if st.get("imagery") == "photo" and not has_ai:
            continue  # photo-driven styles look empty without pictures
        sc = sum(len(k) for k in st.get("keywords", []) if k.lower() in text.lower())
        if st.get("imagery") == "illustration" and not has_ai:
            sc -= 1
        if scen in ("report",) and st["formality"] == "high":
            sc += 3
        if scen in ("oral", "talk") and st["formality"] != "high":
            sc += 1
        scored.append((sc, st))
    scored.sort(key=lambda x: -x[0])
    safe = scored[0][1]
    bold = next((st for _, st in scored[1:] if st["mood"] != safe["mood"] and st["scheme"] == safe["scheme"]), scored[1][1])
    wild = next((st for _, st in scored if st["id"] not in (safe["id"], bold["id"]) and
                 (st["scheme"] != safe["scheme"] or st["texture"] != safe["texture"])), scored[2][1])
    return [safe["id"], bold["id"], wild["id"]]


def mini_deck(deck):
    slides = deck["slides"]
    cover = next((s for s in slides if s.get("type") == "cover"), slides[0])
    content = next((s for s in slides if s.get("type") not in ("cover", "closing", "section")), None)
    out = [dict(cover, n=1)]
    if content:
        out.append(dict(content, n=2))
    meta = dict(deck.get("meta", {}))
    meta.setdefault("total", len(slides))
    return {"meta": meta, "slides": out}


LITE = []  # presets whose previews came from render_lite


def build_one(work, preset, deck):
    d = work / "previews" / preset
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    style = load_json(style_file(preset))
    save_json(style, d / "style.json")
    save_json(mini_deck(deck), d / "deck.json")
    for step in ([HERE / "plan_deck.py", d, "--level", "standard"],
                 [HERE / "make_assets.py", d, "--procedural"],
                 [HERE / "build_deck.py", d]):
        r = run(step)
        if r.returncode:
            raise SystemExit(f"{preset}: {Path(str(step[0])).name} failed\n{r.stdout[-400:]}{r.stderr[-400:]}")
    if run([HERE / "render.py", d / "out" / "beautified.pptx", d / "png", "--dpi", "60"]).returncode == 0:
        return sorted((d / "png").glob("slide-*.png"))
    # no LibreOffice: draw approximate previews from the layout data, as pipeline.py does
    r = run([HERE / "render_lite.py", d, "--dpi", "60"])
    if r.returncode:
        raise SystemExit(f"{preset}: render_lite.py failed\n{r.stdout[-400:]}{r.stderr[-400:]}")
    LITE.append(preset)
    return sorted((d / "out" / "png").glob("slide-*.png"))


def sheet(rows, out, labels):
    from PIL import Image, ImageDraw
    ims = [[Image.open(p).convert("RGB") for p in r] for r in rows]
    w, h = ims[0][0].size
    pad, lab = 16, 56
    W = lab + 2 * w + 3 * pad
    H = len(ims) * (h + pad) + pad
    sh = Image.new("RGB", (W, H), (236, 238, 237))
    d = ImageDraw.Draw(sh)
    f = get_font(30, True)
    for i, r in enumerate(ims):
        y = pad + i * (h + pad)
        d.text((16, y + h // 2 - 18), labels[i], fill=(40, 40, 40), font=f)
        for j, im in enumerate(r[:2]):
            sh.paste(im, (lab + pad + j * (w + pad), y))
    sh.save(out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work", nargs="?")
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--presets")
    ap.add_argument("--apply")
    ap.add_argument("--sample", action="store_true", help="use built-in sample content")
    ap.add_argument("--all", action="store_true", help="every preset (gallery)")
    a = ap.parse_args()
    idx = {s["id"]: s for s in load_json(style_file("index"))["styles"]}

    if a.apply:
        work = Path(a.work)
        if a.apply not in idx:
            raise SystemExit(f"unknown preset {a.apply}; choose from {', '.join(idx)}")
        shutil.copyfile(style_file(a.apply), work / "style.json")
        print(f"style.json <- {a.apply}（{idx[a.apply]['name']}）")
        return

    if a.sample:
        work = Path(a.work) if a.work else Path("/tmp/pb_gallery")
        work.mkdir(parents=True, exist_ok=True)
        deck = SAMPLE
    else:
        work = Path(a.work)
        deck = load_json(work / "deck.json")
    if a.all:
        presets = list(idx)
    elif a.presets:
        presets = [p.strip() for p in a.presets.split(",")]
    else:
        presets = pick_auto(work)
    rows, labels = [], []
    for i, p in enumerate(presets, 1):
        if p not in idx:
            raise SystemExit(f"unknown preset {p}")
        rows.append(build_one(work, p, deck))
        labels.append(str(i))
        print(f"{i}. {p}（{idx[p]['name']}）适合：{idx[p]['best_for']}")
    out = work / "previews" / "sheet.png"
    sheet(rows, out, labels)
    print(f"sheet: {out}")
    if LITE:
        print("NOTE 没找到 LibreOffice，样张是按排版数据直接画的近似图（render_lite），配色和版式照样能比，细节以成品为准")
    if a.sample and a.all:
        # one gallery image for the whole preset library (keeps the skill package small)
        from PIL import Image, ImageDraw
        w0, h0 = Image.open(rows[0][0]).size
        tw, th = 560, int(560 * h0 / w0)
        lab, pad = 150, 10
        G = Image.new("RGB", (lab + 2 * (tw + pad) + pad, len(rows) * (th + pad) + pad), (236, 238, 237))
        d = ImageDraw.Draw(G)
        f = get_font(24, True)
        fs = get_font(15)
        for i, (p, r) in enumerate(zip(presets, rows)):
            y = pad + i * (th + pad)
            d.text((14, y + th // 2 - 26), idx[p]["name"], fill=(30, 30, 30), font=f)
            d.text((14, y + th // 2 + 8), p, fill=(110, 110, 110), font=fs)
            for j, x in enumerate(r[:2]):
                G.paste(Image.open(x).convert("RGB").resize((tw, th), Image.LANCZOS), (lab + pad + j * (tw + pad), y))
        gal = ASSET_DIR / "style_gallery.jpg"
        G.save(gal, quality=86, optimize=True)
        print(f"gallery -> {gal}")


if __name__ == "__main__":
    main()
