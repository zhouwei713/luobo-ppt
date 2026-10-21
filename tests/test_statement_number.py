"""A wide hero number must not push its lines off the slide.

Run with: python -m unittest discover -s tests -v
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from common import CANVAS_W, CANVAS_H
import qa_check as Q


def run_script(name, *args):
    return subprocess.run([sys.executable, str(SCRIPTS / name), *map(str, args)],
                          capture_output=True, text=True, encoding="utf-8",
                          env=dict(os.environ, PYTHONIOENCODING="utf-8"))


class StatementNumberTests(unittest.TestCase):
    def setUp(self):
        self.w = Path(tempfile.mkdtemp())
        shutil.copy(ROOT / "references" / "styles" / "dark-tech.json", self.w / "style.json")
        deck = {"meta": {"title": "t"}, "slides": [
            {"n": 1, "type": "big_number", "title": "成本也算一算", "number": "≤ 0.5 元 / 秒",
             "lines": ["4K MG 高清动效", "官方给出的每秒成本"], "body": "拿这个价格去对比外包报价。"},
            {"n": 2, "type": "big_number", "title": "海外先火了一把", "number": "No.1",
             "lines": ["8 月海外发布", "当日最佳产品"], "body": "国内版已上线。"}]}
        (self.w / "deck.json").write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.w, ignore_errors=True)

    def test_wide_number_keeps_every_text_on_the_slide(self):
        for step in (("plan_deck.py", self.w, "--level", "light"), ("make_assets.py", self.w), ("build_deck.py", self.w)):
            r = run_script(*step)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        dump = json.loads((self.w / "out" / "layout_dump.json").read_text(encoding="utf-8"))
        for sd in dump["slides"]:
            for e in sd["elements"]:
                if e["t"] != "text":
                    continue
                with self.subTest(slide=sd["n"], text=e["text"][:12]):
                    self.assertGreater(e["w"], 0)
                    self.assertGreaterEqual(e["x"], -0.01)
                    self.assertLessEqual(e["x"] + e["w"], CANVAS_W + 0.01)
                    self.assertLessEqual(e["y"] + e["h"], CANVAS_H + 0.01)
        texts = " ".join(e["text"] for sd in dump["slides"] for e in sd["elements"] if e["t"] == "text")
        self.assertIn("官方给出的每秒成本", texts)

    def test_sample_bg_survives_inverted_and_offslide_boxes(self):
        from PIL import Image
        bg = self.w / "bg.png"
        Image.new("RGB", (400, 225), (10, 20, 30)).save(bg)
        for box in [(13.35, 2.4, 7.3, 4.3), (20, 1, 25, 2), (-5, -5, -1, -1), (1, 1, 1, 1)]:
            with self.subTest(box=box):
                self.assertEqual(Q.sample_bg(str(bg), box), "0A141E")


if __name__ == "__main__":
    unittest.main()
