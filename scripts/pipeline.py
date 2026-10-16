#!/usr/bin/env python3
"""Run steps 4-6 in one go once deck.json, style.json and plan.json are ready.

Usage:
  python pipeline.py WORK_DIR [--config cfg.json] [--procedural] [--force-assets] [--dpi 110] [--lite]

  --lite skips LibreOffice and draws approximate previews (render_lite.py); also used
  automatically when LibreOffice is missing.

  make_assets -> build_deck -> render -> qa_check -> compare_sheet -> review
Prints the QA summary; outputs land in WORK_DIR/out/.
"""
import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(args):
    print("$", " ".join(str(a) for a in args[1:]))
    return subprocess.run([sys.executable] + [str(a) for a in args]).returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("--config")
    ap.add_argument("--procedural", action="store_true")
    ap.add_argument("--force-assets", action="store_true")
    ap.add_argument("--dpi", type=int, default=110)
    ap.add_argument("--lite", action="store_true",
                    help="skip LibreOffice and draw approximate previews from the layout dump (faster)")
    a = ap.parse_args()
    w = Path(a.work)
    ma = [HERE / "make_assets.py", w]
    if a.config:
        ma += ["--config", a.config]
    if a.procedural:
        ma.append("--procedural")
    if a.force_assets:
        ma.append("--force")
    if run(ma):
        sys.exit("make_assets failed")
    if run([HERE / "build_deck.py", w]):
        sys.exit("build_deck failed")
    lite = False
    rendered = (not a.lite) and run([HERE / "render.py", w / "out" / "beautified.pptx", w / "out" / "png", "--dpi", a.dpi,
                                     "--sheet", w / "out" / "sheet.png"]) == 0
    if not rendered:
        # no LibreOffice (or it failed): draw approximate previews from the layout dump instead,
        # so the look-over and the five-dimension review still have pictures to work with
        lite = run([HERE / "render_lite.py", w, "--dpi", a.dpi]) == 0
    rc = run([HERE / "qa_check.py", w])
    if rendered and (w / "source_png").exists():
        run([HERE / "compare_sheet.py", w])
    elif (w / "source_text.json").exists():
        print("NOTE 原稿没有渲染图（解析原稿时缺 LibreOffice），前后对比图跳过；美化版的逐页预览不受影响")
    run([HERE / "review.py", w])
    if lite:
        print("NOTE " + ("按 --lite 跳过了 LibreOffice" if a.lite else "没找到 LibreOffice") +
              "，预览图是按排版数据直接画的近似图（render_lite），排版和溢出照样能看，"
              "图表是简化画法；要看 PowerPoint 级效果，装 LibreOffice 后重跑")
    elif not rendered:
        print("NOTE 没有生成预览图，视觉检查只能跳过，pptx 已正常生成")
    print("\nQA", "has ERRORS, fix before delivering" if rc else "passed (review WARN lines)")
    return rc


if __name__ == "__main__":
    sys.exit(main())
