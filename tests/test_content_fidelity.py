"""Regression checks for extraction, fidelity normalization and pipeline status.

Run with: python -m unittest discover -s tests -v
"""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from pptx import Presentation
from pptx.util import Inches

from extract_deck import para_text_marked
import pipeline
from qa_check import norm


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def run_script(name, *args):
    return subprocess.run([sys.executable, str(SCRIPTS / name), *map(str, args)],
                          capture_output=True, text=True, encoding="utf-8",
                          env=dict(os.environ, PYTHONIOENCODING="utf-8"))


class FidelityTests(unittest.TestCase):
    def test_preserves_numeric_signs(self):
        for text in ("-5°C", "-12.5%", "–5°C", "−5°C"):
            with self.subTest(text=text):
                self.assertEqual(norm(text), text)
        self.assertEqual(norm("first\n-5°C"), "first-5°C")
        self.assertEqual(norm("-\n5°C"), "-5°C")

    def test_still_ignores_list_markers_and_bold(self):
        for marker in ("·", "•", "●", "▪", "◦", "*", "-", "–"):
            with self.subTest(marker=marker):
                self.assertEqual(norm(f"{marker} **annual report**"), "annualreport")
        self.assertEqual(norm("- first\n- second"), "firstsecond")
        self.assertEqual(norm("•-5°C"), "-5°C")

    def test_reports_negative_value_changed_to_positive(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            out = work / "out"
            out.mkdir()
            prs = Presentation()
            slide = prs.slides.add_slide(prs.slide_layouts[6])
            box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(1))
            write_json(work / "style.json", {"name": "test"})
            write_json(work / "deck.json", {"meta": {}, "slides": [{"n": 1, "type": "content"}]})
            write_json(work / "source_text.json", {"slides": [
                {"n": 1, "units": [{"id": "s1_1_p0", "text": "-5°C"}]}]})
            write_json(out / "layout_dump.json", {"slides": [{"n": 1, "elements": []}]})
            for actual, expected_code in (("5°C", 1), ("-5°C", 0)):
                with self.subTest(actual=actual):
                    box.text = actual
                    prs.save(str(out / "beautified.pptx"))
                    result = run_script("qa_check.py", work)
                    self.assertEqual(result.returncode, expected_code, result.stdout + result.stderr)
                    report = json.loads((out / "qa_report.json").read_text(encoding="utf-8"))
                    errors = [i for i in report["issues"] if i["level"] == "ERROR"]
                    self.assertEqual(len(errors), expected_code)
                    if errors:
                        self.assertEqual(errors[0]["check"], "fidelity")


class ExtractionTests(unittest.TestCase):
    def test_soft_breaks_preserve_partial_and_full_bold(self):
        for left_bold, right_bold, expected in (
                (False, False, "annual\nreport"),
                (True, True, "annual\nreport"),
                (True, False, "**annual**\nreport"),
                (False, True, "annual\n**report**")):
            with self.subTest(left_bold=left_bold, right_bold=right_bold):
                prs = Presentation()
                slide = prs.slides.add_slide(prs.slide_layouts[6])
                para = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(2)).text_frame.paragraphs[0]
                left = para.add_run()
                left.text, left.font.bold = "annual", left_bold
                para.add_line_break()
                para.add_run()  # an empty run must not shift the text/bold mapping
                right = para.add_run()
                right.text, right.font.bold = "report", right_bold
                self.assertEqual(para_text_marked(para), expected)

    def test_plain_paragraph_and_break_only(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        para = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(2)).text_frame.paragraphs[0]
        para.text = "annual report"
        self.assertEqual(para_text_marked(para), "annual report")
        para.clear()
        para.add_line_break()
        self.assertEqual(para_text_marked(para), "\n")

    def test_extracts_soft_break_to_source_and_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            prs = Presentation()
            slide = prs.slides.add_slide(prs.slide_layouts[6])
            para = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(2)).text_frame.paragraphs[0]
            para.add_run().text = "annual"
            para.add_line_break()
            para.add_run().text = "report"
            src = work / "input.pptx"
            prs.save(str(src))
            result = run_script("extract_deck.py", src, work / "extracted", "--no-render")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for filename, key in (("source_text.json", "units"), ("deck.draft.json", "units"), ("raw.json", "shapes")):
                with self.subTest(filename=filename):
                    data = json.loads((work / "extracted" / filename).read_text(encoding="utf-8"))
                    self.assertEqual(data["slides"][0][key][0]["text"], "annual\nreport")


class PipelineTests(unittest.TestCase):
    def test_keeps_review_and_returns_qa_status(self):
        for qa_status in (0, 1, 2):
            with self.subTest(qa_status=qa_status), tempfile.TemporaryDirectory() as tmp:
                called = []

                def run_stage(args):
                    called.append(Path(args[0]).name)
                    return qa_status if called[-1] == "qa_check.py" else 0

                with patch.object(sys, "argv", ["pipeline.py", tmp, "--lite"]), \
                        patch.object(pipeline, "run", side_effect=run_stage), \
                        contextlib.redirect_stdout(io.StringIO()):
                    status = pipeline.main()
                self.assertEqual(status, qa_status)
                self.assertEqual(called[-1], "review.py")


if __name__ == "__main__":
    unittest.main()
