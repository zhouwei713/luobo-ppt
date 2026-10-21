"""Style previews work with or without LibreOffice.

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


class StylePreviewTests(unittest.TestCase):
    def test_previews_and_sheet_are_drawn(self):
        w = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, w, True)
        deck = {"meta": {"title": "风格样张测试"}, "slides": [
            {"n": 1, "type": "cover", "title": "风格样张测试", "subtitle": "两页就够"},
            {"n": 2, "type": "grid", "title": "三张卡片", "items": [{"title": f"第{i}点", "text": "说明文字"} for i in range(1, 4)]}]}
        (w / "deck.json").write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")
        # no PYTHONIOENCODING here on purpose: the script must read its children's output on any console
        env = {k: v for k, v in os.environ.items() if k != "PYTHONIOENCODING"}
        r = subprocess.run([sys.executable, str(SCRIPTS / "style_previews.py"), str(w), "--presets", "dark-tech,mint-fresh"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("UnicodeDecodeError", r.stdout + r.stderr)
        self.assertTrue((w / "previews" / "sheet.png").exists())
        for preset in ("dark-tech", "mint-fresh"):
            pngs = list((w / "previews" / preset).rglob("slide-*.png"))
            self.assertEqual(len(pngs), 2, preset)


if __name__ == "__main__":
    unittest.main()
