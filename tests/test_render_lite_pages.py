"""render_lite.py --pages redraws only the pages asked for.

Run with: python -m unittest discover -s tests -v
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def run_script(name, *args):
    return subprocess.run([sys.executable, str(SCRIPTS / name), *map(str, args)],
                          capture_output=True, text=True, encoding="utf-8",
                          env=dict(os.environ, PYTHONIOENCODING="utf-8"))


class RenderLitePagesTests(unittest.TestCase):
    def test_only_the_named_pages_are_redrawn(self):
        w = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, w, True)
        shutil.copy(ROOT / "references" / "styles" / "dark-tech.json", w / "style.json")
        deck = {"meta": {"title": "t"}, "slides": [
            {"n": 1, "type": "cover", "title": "第一页"},
            {"n": 2, "type": "statement", "title": "第二页", "headline": "一句话", "body": "补充。"},
            {"n": 3, "type": "closing", "title": "第三页", "headline": "谢谢"}]}
        (w / "deck.json").write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")
        for step in (("plan_deck.py", w, "--level", "light"), ("build_deck.py", w), ("render_lite.py", w, "--dpi", "40")):
            r = run_script(*step)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        png = w / "out" / "png"
        sheet = w / "out" / "sheet.png"
        self.assertEqual(sorted(p.name for p in png.glob("*.png")), ["slide-01.png", "slide-02.png", "slide-03.png"])
        before = {p.name: p.stat().st_mtime_ns for p in png.glob("*.png")}
        sheet_before = sheet.stat().st_mtime_ns
        (png / "slide-09.png").write_bytes((png / "slide-01.png").read_bytes())  # left over from a longer deck
        time.sleep(0.05)

        r = run_script("render_lite.py", w, "--dpi", "40", "--pages", "2")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        after = {p.name: p.stat().st_mtime_ns for p in png.glob("*.png")}
        self.assertEqual(sorted(after), ["slide-01.png", "slide-02.png", "slide-03.png"])
        self.assertEqual(after["slide-01.png"], before["slide-01.png"])
        self.assertEqual(after["slide-03.png"], before["slide-03.png"])
        self.assertNotEqual(after["slide-02.png"], before["slide-02.png"])
        self.assertEqual(sheet.stat().st_mtime_ns, sheet_before)


if __name__ == "__main__":
    unittest.main()
