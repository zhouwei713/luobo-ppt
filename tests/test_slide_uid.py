"""A slide's uid is an id for outside tools, never text that should appear on the slide.

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

from outline_check import screen_text


def run_script(name, *args):
    return subprocess.run([sys.executable, str(SCRIPTS / name), *map(str, args)],
                          capture_output=True, text=True, encoding="utf-8",
                          env=dict(os.environ, PYTHONIOENCODING="utf-8"))


class SlideUidTests(unittest.TestCase):
    def test_uid_is_not_screen_text(self):
        self.assertEqual(screen_text({"n": 1, "uid": "s-7f3a", "title": "标题"}), ["标题"])

    def test_deck_with_uids_passes_qa(self):
        w = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, w, True)
        shutil.copy(ROOT / "references" / "styles" / "dark-tech.json", w / "style.json")
        deck = {"meta": {"title": "t"}, "slides": [
            {"n": 1, "uid": "s-cover01", "type": "cover", "title": "带稳定 id 的稿子"},
            {"n": 2, "uid": "s-point02", "type": "statement", "title": "一页主张", "headline": "一句话", "body": "补充。"}]}
        (w / "deck.json").write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")
        for step in (("plan_deck.py", w, "--level", "light"), ("make_assets.py", w), ("build_deck.py", w)):
            r = run_script(*step)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        run_script("qa_check.py", w)
        report = json.loads((w / "out" / "qa_report.json").read_text(encoding="utf-8"))
        self.assertFalse([i for i in report["issues"] if i["check"] == "fidelity"], report["issues"])

    def test_adding_uids_keeps_the_old_plan(self):
        w = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, w, True)
        shutil.copy(ROOT / "references" / "styles" / "dark-tech.json", w / "style.json")
        deck = {"meta": {"title": "t"}, "slides": [
            {"n": 1, "type": "statement", "title": "一页主张", "headline": "一句话", "body": "补充。"}]}
        (w / "deck.json").write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")
        run_script("plan_deck.py", w, "--level", "light")
        plan = json.loads((w / "plan.json").read_text(encoding="utf-8"))
        plan["slides"][0]["layout"] = "statement_number"  # a hand edit
        (w / "plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        deck["slides"][0]["uid"] = "s-later01"
        (w / "deck.json").write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")
        r = run_script("plan_deck.py", w, "--level", "light")
        self.assertIn("保留了 1 页", r.stdout)
        self.assertEqual(json.loads((w / "plan.json").read_text(encoding="utf-8"))["slides"][0]["layout"], "statement_number")


if __name__ == "__main__":
    unittest.main()
