"""Charts and fine print: units, axis titles, series and footnote marks checked on their own.

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

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.util import Inches

import chartcheck as CC


def run_script(name, *args):
    return subprocess.run([sys.executable, str(SCRIPTS / name), *map(str, args)],
                          capture_output=True, text=True, encoding="utf-8",
                          env=dict(os.environ, PYTHONIOENCODING="utf-8"))


class RenderTests(unittest.TestCase):
    def test_formats_read_like_powerpoint(self):
        cases = [(0.35, "0%", "35%"), (35, '0"%"', "35%"), (35, "General", "35"), (1234.5, "#,##0", "1,235"),
                 (35, 'General"万"', "35万"), (0.1234, "0.0%", "12.3%"), (12.0, "0.##", "12"), (12.5, "0.##", "12.5"),
                 (1500, '#,##0" 元"', "1,500 元"), (2.25, "0.0", "2.3"), (-1.5, "0;(0)", "(2)")]
        for v, code, want in cases:
            with self.subTest(code=code, v=v):
                self.assertEqual(CC.render(v, code), want)

    def test_spec_unit_becomes_label_format(self):
        self.assertEqual(CC.spec_label_format({"unit": "%"}), 'General"%"')
        self.assertEqual(CC.spec_label_format({"unit": "%", "number_format": "0.0"}), "0.0")
        self.assertEqual(CC.spec_label_format({}), "General")

    def test_fine_print_units(self):
        units = [{"text": "* 数据截至 9 月"}, {"text": "来源：会员系统"}, {"text": "**重点**说明在这"},
                 {"text": "x³ − 3x 的极值"}, {"text": "复购率 25%※"}, {"text": "普通正文"}]
        got = [u["text"] for u in CC.fine_print_units(units)]
        self.assertEqual(got, ["* 数据截至 9 月", "来源：会员系统", "复购率 25%※"])


def make_source(path):
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    s = prs.slides.add_slide(prs.slide_layouts[6])
    s.shapes.add_textbox(Inches(0.8), Inches(0.5), Inches(10), Inches(0.8)).text_frame.text = "复购率三个月翻了一倍"
    cd = CategoryChartData()
    cd.categories = ["7月", "8月", "9月"]
    cd.add_series("复购率", (0.12, 0.18, 0.25))
    ch = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.8), Inches(1.5), Inches(8), Inches(4.5), cd).chart
    ch.has_title = True
    ch.chart_title.text_frame.text = "会员复购率"
    p = ch.plots[0]
    p.has_data_labels = True
    p.data_labels.number_format = "0%"
    p.data_labels.number_format_is_linked = False
    ch.value_axis.has_title = True
    ch.value_axis.axis_title.text_frame.text = "占当月下单会员比例"
    s.shapes.add_textbox(Inches(0.8), Inches(6.3), Inches(10), Inches(0.5)).text_frame.text = "* 数据截至 9 月 30 日"
    prs.save(str(path))


class BeautifyChartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        make_source(cls.tmp / "src.pptx")
        r = run_script("extract_deck.py", cls.tmp / "src.pptx", cls.tmp / "w", "--no-render")
        assert r.returncode == 0, r.stdout + r.stderr
        shutil.copy(ROOT / "references" / "styles" / "business-blue.json", cls.tmp / "w" / "style.json")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, True)

    def draft(self):
        return json.loads((self.tmp / "w" / "deck.draft.json").read_text(encoding="utf-8"))["slides"][0]

    def build(self, change=None):
        d = self.draft()
        slide = {"n": 1, "type": "chart", "title": d["units"][0]["text"], "chart": json.loads(json.dumps(d["charts"][0])),
                 "footnote": d["units"][1]["text"]}
        if change:
            change(slide)
        w = self.tmp / "w"
        (w / "deck.json").write_text(json.dumps({"meta": {}, "slides": [slide]}, ensure_ascii=False), encoding="utf-8")
        for args in (("plan_deck.py", w, "--level", "light"), ("build_deck.py", w)):
            r = run_script(*args)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = run_script("qa_check.py", w)
        report = json.loads((w / "out" / "qa_report.json").read_text(encoding="utf-8"))
        errs = [i for i in report["issues"] if i["level"] == "ERROR"]
        return r.returncode, errs

    def test_extract_reads_chart_with_format_and_titles(self):
        spec = self.draft()["charts"][0]
        self.assertEqual(spec["categories"], ["7月", "8月", "9月"])
        self.assertEqual(spec["number_format"], "0%")
        self.assertEqual((spec["title"], spec["y_title"]), ("会员复购率", "占当月下单会员比例"))

    def test_faithful_copy_passes(self):
        rc, errs = self.build()
        self.assertEqual((rc, errs), (0, []))
        fp = (self.tmp / "w" / "out" / "fine_print.md").read_text(encoding="utf-8")
        self.assertIn("7月 显示为 12%", fp)

    def test_each_quiet_change_is_an_error(self):
        changes = {
            "unit": lambda s: s["chart"].pop("number_format"),
            "axis": lambda s: s["chart"].pop("y_title"),
            "data": lambda s: s["chart"]["series"][0]["values"].__setitem__(2, 0.52),
            "star": lambda s: s.__setitem__("footnote", s["footnote"].lstrip("* ")),
            "gone": lambda s: (s.__setitem__("type", "list"), s.pop("chart"),
                               s.__setitem__("items", [{"text": "会员复购率"}, {"text": "占当月下单会员比例"}])),
        }
        for name, ch in changes.items():
            with self.subTest(change=name):
                rc, errs = self.build(ch)
                self.assertEqual(rc, 1)
                self.assertTrue(any(e["check"] in ("chart", "fine-print") for e in errs), errs)


class GenerateUnitTests(unittest.TestCase):
    def test_unit_reaches_column_labels(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        shutil.copy(ROOT / "references" / "styles" / "business-blue.json", tmp / "style.json")
        deck = {"meta": {}, "slides": [{"n": 1, "type": "chart", "title": "复购率翻倍",
                                        "chart": {"type": "column", "categories": ["7月", "8月"],
                                                  "series": [{"name": "复购率", "values": [12, 18]}],
                                                  "unit": "%", "y_title": "单位：%"}, "source": "会员系统"}]}
        (tmp / "deck.json").write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")
        for args in (("plan_deck.py", tmp, "--level", "light"), ("build_deck.py", tmp), ("qa_check.py", tmp)):
            r = run_script(*args)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        ch = CC.charts_on_slide(Presentation(str(tmp / "out" / "beautified.pptx")).slides[0])[0]
        self.assertEqual(CC.render(ch["series"][0]["values"][0], CC.shown_format(ch)), "12%")


if __name__ == "__main__":
    unittest.main()
