"""What a person changed on a page's plan stays put when plan_deck runs again.

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
STEPS = {"n": 1, "type": "process", "title": "四步走完",
         "items": [{"title": f"第{i}步", "text": f"做第{i}件事"} for i in range(1, 5)]}


def run_script(name, *args):
    return subprocess.run([sys.executable, str(SCRIPTS / name), *map(str, args)],
                          capture_output=True, text=True, encoding="utf-8",
                          env=dict(os.environ, PYTHONIOENCODING="utf-8"))


class PlanLockTests(unittest.TestCase):
    def setUp(self):
        self.w = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.w, True)
        shutil.copy(ROOT / "references" / "styles" / "dark-tech.json", self.w / "style.json")

    def deck(self, *slides):
        (self.w / "deck.json").write_text(json.dumps({"meta": {"title": "t"}, "slides": list(slides)},
                                                     ensure_ascii=False), encoding="utf-8")

    def plan(self, *args):
        r = run_script("plan_deck.py", self.w, "--level", "full", *args)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout, json.loads((self.w / "plan.json").read_text(encoding="utf-8"))

    def edit_plan(self, change):
        plan = json.loads((self.w / "plan.json").read_text(encoding="utf-8"))
        change(plan)
        (self.w / "plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")

    def hero(self, plan, n):
        hid = plan["slides"][n - 1].get("hero")
        return next((a for a in plan["assets"] if a.get("id") == hid), None)

    def test_locked_layout_icons_and_prompt_survive_a_content_change_and_reset(self):
        self.deck(STEPS)
        _, plan = self.plan()
        self.assertTrue(self.hero(plan, 1), "the steps page should get an illustration at level full")

        def lock(p):
            p["slides"][0].update(layout="list_icons", icons=["star", "star", "star", "star"],
                                  locked=["layout", "icons", "prompt"])
            p["slides"][0]["hero"] = p["slides"][0].get("hero")
            self.hero(p, 1)["prompt"] = "a hand-written prompt"
        self.edit_plan(lock)
        self.deck(dict(STEPS, title="改过的标题"))
        for args in ((), ("--reset",)):
            with self.subTest(args=args):
                _, plan = self.plan(*args)
                page = plan["slides"][0]
                self.assertEqual(page["layout"], "list_icons")
                self.assertEqual(page["icons"], ["star"] * 4)
                self.assertEqual(page["locked"], ["icons", "layout", "prompt"])
                if self.hero(plan, 1):
                    self.assertEqual(self.hero(plan, 1)["prompt"], "a hand-written prompt")

    def test_a_locked_layout_is_kept_even_when_the_content_overflows_it(self):
        self.deck(STEPS)
        self.plan()
        self.edit_plan(lambda p: p["slides"][0].update(layout="steps_flow", locked=["layout"]))
        self.deck(dict(STEPS, items=STEPS["items"] * 2))  # eight steps, more than steps_flow holds
        _, plan = self.plan()
        self.assertEqual(plan["slides"][0]["layout"], "steps_flow")
        self.assertTrue(plan["slides"][0]["capacity_warnings"])
        self.assertNotIn("layout_auto", plan["slides"][0])

    def test_replan_redoes_a_page_whose_content_did_not_change(self):
        self.deck(STEPS)
        self.plan()
        self.edit_plan(lambda p: p["slides"][0].update(layout="list_icons", icons=["zzz"], locked=["layout"]))
        out, plan = self.plan()
        self.assertEqual(plan["slides"][0]["icons"], ["zzz"], "unchanged content keeps the old plan as it is")
        out, plan = self.plan("--replan", "1")
        self.assertNotIn("保留了", out)
        self.assertEqual(plan["slides"][0]["layout"], "list_icons")
        self.assertNotIn("zzz", plan["slides"][0]["icons"], "icons follow the new layout")

    def test_an_automatic_layout_switch_says_why(self):
        six = [{"title": f"第{i}步", "text": f"做第{i}件事"} for i in range(1, 7)]  # steps_flow holds 5, list_icons 6
        self.deck(dict(STEPS, items=six))
        _, plan = self.plan()
        page = plan["slides"][0]
        self.assertNotEqual(page["layout"], "steps_flow")
        self.assertEqual(page["layout_auto"]["wanted"], "steps_flow")
        self.assertTrue(page["layout_auto"]["reason"])

    def test_a_page_animation_does_not_re_plan_it(self):
        self.deck(STEPS)
        self.plan()
        self.edit_plan(lambda p: p["slides"][0].update(icons=["star"] * 4))
        self.deck(dict(STEPS, animation="click"))
        out, plan = self.plan()
        self.assertIn("保留了 1 页", out)
        self.assertEqual(plan["slides"][0]["icons"], ["star"] * 4)


if __name__ == "__main__":
    unittest.main()
