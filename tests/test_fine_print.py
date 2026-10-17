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
from pptx.chart.data import CategoryChartData, XyChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.util import Inches, Pt

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


def make_tricky_source(path):
    """Things real decks do: a format only in the sheet, two charts on a page, a scatter chart
    inside a group, a table with units, a starred note and a source line at the bottom."""
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)

    def page(title):
        s = prs.slides.add_slide(prs.slide_layouts[6])
        s.shapes.add_textbox(Inches(0.8), Inches(0.4), Inches(11), Inches(0.8)).text_frame.text = title
        return s
    s = page("老客复购率稳住了")
    cd = CategoryChartData(number_format="0.0%")
    cd.categories = ["7月", "8月", "9月"]
    cd.add_series("老客", (0.312, 0.318, 0.321))
    cd.add_series("新客", (0.084, 0.097, 0.113))
    s.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS, Inches(0.8), Inches(1.5), Inches(11), Inches(4.8), cd)
    s = page("华东最大，会员过半")
    cd = CategoryChartData()
    cd.categories = ["华东", "华南", "华北"]
    cd.add_series("订单量", (5230, 3180, 2410))
    p_ = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(0.5), Inches(1.4), Inches(6), Inches(5), cd).chart.plots[0]
    p_.has_data_labels = True
    p_.data_labels.number_format = '#,##0" 单"'
    p_.data_labels.number_format_is_linked = False
    cd = CategoryChartData()
    cd.categories = ["会员", "非会员"]
    cd.add_series("构成", (56, 44))
    p_ = s.shapes.add_chart(XL_CHART_TYPE.DOUGHNUT, Inches(7), Inches(1.4), Inches(5.5), Inches(5), cd).chart.plots[0]
    p_.has_data_labels = True
    p_.data_labels.number_format = '0"%"'
    p_.data_labels.number_format_is_linked = False
    p_.data_labels.show_value = True
    s = page("客单价越高，转化率越低")
    xy = XyChartData()
    sr = xy.add_series("单品")
    for x, y in [(39, 0.062), (59, 0.051), (89, 0.038), (129, 0.027)]:
        sr.add_data_point(x, y)
    ch = s.shapes.add_group_shape().shapes.add_chart(XL_CHART_TYPE.XY_SCATTER, Inches(0.8), Inches(1.5), Inches(8),
                                                     Inches(4.8), xy).chart
    ch.value_axis.has_title = True
    ch.value_axis.axis_title.text_frame.text = "转化率"
    s = page("费用率压到 18.5%")
    t = s.shapes.add_table(3, 2, Inches(0.8), Inches(1.5), Inches(8), Inches(2)).table
    for i, row in enumerate([["项目", "金额（万元）"], ["营销", "1,120"], ["合计", "2,035"]]):
        for j, v in enumerate(row):
            t.cell(i, j).text = v
    for k, txt in enumerate(["※ 数据未经审计", "来源：财务部 9 月报表"]):
        tf = s.shapes.add_textbox(Inches(0.8), Inches(6.3 + k * 0.4), Inches(9), Inches(0.4)).text_frame
        tf.text = txt
        tf.paragraphs[0].runs[0].font.size = Pt(11)
    prs.save(str(path))


class TrickyDeckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        make_tricky_source(cls.tmp / "src.pptx")
        r = run_script("extract_deck.py", cls.tmp / "src.pptx", cls.tmp / "w", "--no-render")
        assert r.returncode == 0, r.stdout + r.stderr
        shutil.copy(ROOT / "references" / "styles" / "business-blue.json", cls.tmp / "w" / "style.json")
        cls.draft = json.loads((cls.tmp / "w" / "deck.draft.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, True)

    def faithful(self):
        draft = json.loads(json.dumps(self.draft))  # each build gets its own copy to change
        S = {s["n"]: dict(s, title=s["units"][0]["text"]) for s in draft["slides"]}
        t = S[4]["tables"][0]
        return {"meta": {}, "slides": [
            {"n": 1, "type": "chart", "title": S[1]["title"], "chart": S[1]["charts"][0]},
            {"n": 2, "type": "chart", "title": S[2]["title"], "charts": S[2]["charts"]},
            {"n": 3, "type": "chart", "title": S[3]["title"], "chart": S[3]["charts"][0]},
            {"n": 4, "type": "table", "title": S[4]["title"], "columns": t["columns"], "rows": t["rows"],
             "footnote": "※ 数据未经审计", "source": "来源：财务部 9 月报表"}]}

    def build(self, deck):
        w = self.tmp / "w"
        (w / "deck.json").write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")
        for args in (("plan_deck.py", w, "--level", "light"), ("build_deck.py", w)):
            r = run_script(*args)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = run_script("qa_check.py", w)
        report = json.loads((w / "out" / "qa_report.json").read_text(encoding="utf-8"))
        return r.returncode, [i for i in report["issues"] if i["level"] == "ERROR"]

    def test_draft_reads_what_the_reader_sees(self):
        S = {s["n"]: s for s in self.draft["slides"]}
        self.assertEqual(S[1]["charts"][0]["number_format"], "0.0%")  # only in the sheet, no labels
        self.assertEqual([c["number_format"] for c in S[2]["charts"]], ['#,##0" 单"', '0"%"'])
        self.assertEqual(S[2]["type"], "chart")
        sc = S[3]["charts"][0]
        self.assertEqual((sc["type"], sc["series"][0]["x"], sc.get("y_title")), ("scatter", [39, 59, 89, 129], "转化率"))
        self.assertEqual(S[4]["type"], "table")
        self.assertEqual(S[4]["tables"][0]["columns"], ["项目", "金额（万元）"])
        roles = {u["text"]: u["role"] for u in S[4]["units"]}
        self.assertEqual(roles["※ 数据未经审计"], "footnote")
        self.assertEqual(self.draft["meta"]["footer"], "")  # a page note is not the deck footer

    def test_faithful_copy_passes_and_labels_keep_format(self):
        rc, errs = self.build(self.faithful())
        self.assertEqual((rc, errs), (0, []))
        prs = Presentation(str(self.tmp / "w" / "out" / "beautified.pptx"))
        line = CC.charts_on_slide(prs.slides[0])[0]
        self.assertEqual(CC.render(line["series"][0]["values"][2], CC.shown_format(line)), "32.1%")
        self.assertEqual(len(CC.charts_on_slide(prs.slides[1])), 2)
        self.assertEqual(CC.charts_on_slide(prs.slides[2])[0]["type"], "scatter")

    def test_each_quiet_change_is_an_error(self):
        changes = {
            "sheet format": lambda d: d["slides"][0]["chart"].pop("number_format"),
            "one chart left": lambda d: d["slides"][1].__setitem__("charts", d["slides"][1]["charts"][:1]),
            "percent sign": lambda d: d["slides"][1]["charts"][1].__setitem__("number_format", "0%"),
            "scatter x": lambda d: d["slides"][2]["chart"]["series"][0]["x"].__setitem__(1, 60),
            "scatter as columns": lambda d: d["slides"][2].__setitem__("chart", {
                "type": "column", "categories": ["39", "59", "89", "129"], "y_title": "转化率",
                "series": [{"name": "单品", "values": [0.062, 0.051, 0.038, 0.027]}]}),
            "note mark": lambda d: d["slides"][3].__setitem__("footnote", "数据未经审计"),
        }
        for name, ch in changes.items():
            with self.subTest(change=name):
                d = self.faithful()
                ch(d)
                rc, errs = self.build(d)
                self.assertEqual(rc, 1, name)
                self.assertTrue(errs, name)

    def test_footnote_and_source_both_printed(self):
        sys.path.insert(0, str(SCRIPTS))
        import build_deck as B
        self.assertEqual(B.fine_line({"footnote": "※ 未经审计", "source": "财务部"}), "※ 未经审计    来源：财务部")
        self.assertEqual(B.fine_line({"source": "来源：财务部"}), "来源：财务部")


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

    def test_two_charts_and_scatter_from_deck_json(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        shutil.copy(ROOT / "references" / "styles" / "business-blue.json", tmp / "style.json")
        months = ["4月", "5月", "6月"]
        deck = {"meta": {}, "slides": [
            {"n": 1, "type": "chart", "title": "一起涨", "insights": ["入会率翻倍", "复购率高了"],
             "charts": [{"type": "line", "title": "入会率", "categories": months,
                         "series": [{"name": "入会率", "values": [12, 17, 26]}], "unit": "%"},
                        {"type": "line", "title": "复购率", "categories": months,
                         "series": [{"name": "复购率", "values": [0.31, 0.36, 0.41]}], "number_format": "0%"}],
             "footnote": "※ 复购率按满 90 天计算"},
            {"n": 2, "type": "chart", "title": "兑换越多流失越少", "source": "会员系统",
             "chart": {"type": "scatter", "number_format": "0%", "x_title": "兑换次数", "y_title": "流失率",
                       "series": [{"name": "门店", "x": [2, 8, 15], "values": [0.21, 0.14, 0.09]}]}}]}
        (tmp / "deck.json").write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")
        for args in (("plan_deck.py", tmp, "--level", "light"), ("build_deck.py", tmp), ("qa_check.py", tmp)):
            r = run_script(*args)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        prs = Presentation(str(tmp / "out" / "beautified.pptx"))
        a, b = CC.charts_on_slide(prs.slides[0])
        self.assertEqual((CC.render(26, CC.shown_format(a)), CC.render(0.41, CC.shown_format(b))), ("26%", "41%"))
        sc = CC.charts_on_slide(prs.slides[1])[0]
        self.assertEqual((sc["type"], sc["series"][0]["x"]), ("scatter", [2, 8, 15]))


if __name__ == "__main__":
    unittest.main()
