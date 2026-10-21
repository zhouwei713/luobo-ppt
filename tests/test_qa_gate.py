"""The QA gate must be trustworthy: hand-written lines, crashes, missing reports, free pages.

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

FREE_ELEMENTS = [
    {"t": "text", "x": 0.8, "y": 1.0, "w": 8, "h": 0.8, "text": "手工摆放的一页", "size": 32, "color": "text",
     "bold": True, "font": "heading", "align": "l", "valign": "m", "ls": 1.2, "spc": 0},
    {"t": "line", "x1": 0.8, "y1": 2.2, "x2": 6.8, "y2": 2.2, "color": "line", "lw": 1.5, "dash": False, "arrow": False},
]


def run_script(name, *args):
    return subprocess.run([sys.executable, str(SCRIPTS / name), *map(str, args)],
                          capture_output=True, text=True, encoding="utf-8",
                          env=dict(os.environ, PYTHONIOENCODING="utf-8"))


class QaGateTests(unittest.TestCase):
    def setUp(self):
        self.w = Path(tempfile.mkdtemp())
        shutil.copy(ROOT / "references" / "styles" / "dark-tech.json", self.w / "style.json")

    def tearDown(self):
        shutil.rmtree(self.w, ignore_errors=True)

    def write_deck(self, free_slide):
        deck = {"meta": {"title": "t"}, "slides": [
            {"n": 1, "type": "statement", "title": "一页普通内容", "headline": "一句主张", "body": "补充说明。"},
            free_slide]}
        (self.w / "deck.json").write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")

    def build(self):
        for step in (("plan_deck.py", self.w, "--level", "light"), ("make_assets.py", self.w), ("build_deck.py", self.w)):
            r = run_script(*step)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def dump_texts(self, n):
        dump = json.loads((self.w / "out" / "layout_dump.json").read_text(encoding="utf-8"))
        sd = next(s for s in dump["slides"] if s["n"] == n)
        return [e["text"] for e in sd["elements"] if e["t"] == "text"]

    def test_free_elements_in_deck_reach_the_slide_and_lines_do_not_crash_qa(self):
        self.write_deck({"n": 2, "layout": "free", "elements": FREE_ELEMENTS})
        self.build()
        self.assertIn("手工摆放的一页", self.dump_texts(2))
        r = run_script("qa_check.py", self.w)
        self.assertIn(r.returncode, (0, 1), r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        report = json.loads((self.w / "out" / "qa_report.json").read_text(encoding="utf-8"))
        self.assertFalse([i for i in report["issues"] if i["check"] == "free"])

    def test_hand_written_line_in_plan_does_not_crash_qa(self):
        self.write_deck({"n": 2, "layout": "free"})
        run_script("plan_deck.py", self.w, "--level", "light")
        plan = json.loads((self.w / "plan.json").read_text(encoding="utf-8"))
        next(p for p in plan["slides"] if p["n"] == 2)["elements"] = FREE_ELEMENTS
        (self.w / "plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        for step in (("make_assets.py", self.w), ("build_deck.py", self.w)):
            r = run_script(*step)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = run_script("qa_check.py", self.w)
        self.assertIn(r.returncode, (0, 1), r.stdout + r.stderr)
        self.assertTrue((self.w / "out" / "qa_report.json").exists())

    def test_empty_free_page_is_an_error(self):
        self.write_deck({"n": 2, "layout": "free"})
        r = run_script("plan_deck.py", self.w, "--level", "light")
        self.assertIn("ERROR slide 2", r.stdout)
        self.build()
        run_script("qa_check.py", self.w)
        report = json.loads((self.w / "out" / "qa_report.json").read_text(encoding="utf-8"))
        self.assertTrue([i for i in report["issues"] if i["check"] == "free" and i["level"] == "ERROR"])

    def test_hand_placed_plan_elements_survive_a_content_change(self):
        self.write_deck({"n": 2, "layout": "free", "kicker": "旧"})
        run_script("plan_deck.py", self.w, "--level", "light")
        plan = json.loads((self.w / "plan.json").read_text(encoding="utf-8"))
        next(p for p in plan["slides"] if p["n"] == 2)["elements"] = FREE_ELEMENTS
        (self.w / "plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        self.write_deck({"n": 2, "layout": "free", "kicker": "新"})
        run_script("plan_deck.py", self.w, "--level", "light")
        plan = json.loads((self.w / "plan.json").read_text(encoding="utf-8"))
        self.assertEqual(next(p for p in plan["slides"] if p["n"] == 2).get("elements"), FREE_ELEMENTS)

    def test_a_crash_is_not_reported_as_clean(self):
        self.write_deck({"n": 2, "layout": "free", "elements": FREE_ELEMENTS})
        self.build()
        self.assertEqual(run_script("qa_check.py", self.w).returncode in (0, 1), True)
        # break the dump so qa_check crashes; the old report from the run above must not be trusted
        dump_path = self.w / "out" / "layout_dump.json"
        dump = json.loads(dump_path.read_text(encoding="utf-8"))
        del dump["slides"][0]["elements"]
        dump_path.write_text(json.dumps(dump, ensure_ascii=False), encoding="utf-8")
        r = run_script("qa_check.py", self.w)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("QA CRASHED", r.stdout)
        self.assertFalse((self.w / "out" / "qa_report.json").exists())
        dump["slides"][0]["elements"] = []
        dump_path.write_text(json.dumps(dump, ensure_ascii=False), encoding="utf-8")
        r = run_script("review.py", self.w)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("QA 没跑完", r.stdout)
        self.assertIn("QA 没跑完", (self.w / "out" / "review.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
