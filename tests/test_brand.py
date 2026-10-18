"""Brand kit: a VI manual's colours, logo and signature elements kept on every page.

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
import zipfile
import re

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from PIL import Image, ImageDraw

from common import Style, snap_color

PALETTE = {"primary": "14306B", "secondary": "1FA3F5", "accent": "F97316", "background": "F4F6FA", "text": "1F2937"}


def run_script(name, *args):
    return subprocess.run([sys.executable, str(SCRIPTS / name), *map(str, args)],
                          capture_output=True, text=True, encoding="utf-8",
                          env=dict(os.environ, PYTHONIOENCODING="utf-8"))


def make_manual(path):
    """A manual exported as one long image: three white pages on a grey backdrop. Page 2 has the
    swatches, page 3 a logo (a navy disc with an orange dot) and a mascot."""
    W, P, gap = 900, 600, 60
    im = Image.new("RGB", (W + 400, 3 * P + 4 * gap), (232, 235, 240))
    d = ImageDraw.Draw(im)
    for k in range(3):
        y = gap + k * (P + gap)
        d.rectangle((200, y, 200 + W, y + P), fill="white")
    y = gap + P + gap
    for i, h in enumerate(PALETTE.values()):
        d.rectangle((240 + i * 160, y + 100, 380 + i * 160, y + 240), fill="#" + h)
    y = gap + 2 * (P + gap)
    d.ellipse((260, y + 100, 420, y + 260), fill="#14306B")
    d.ellipse((370, y + 110, 410, y + 150), fill="#F97316")
    d.rounded_rectangle((600, y + 100, 760, y + 300), radius=40, fill="#1FA3F5")
    im.save(path)


def brand_json(work):
    return {"name": "测试品牌",
            "colors": [{"name": k, "hex": v, "role": k} for k, v in PALETTE.items()],
            "allow": ["FFFFFF"],
            "fonts": {"heading_ea": "Microsoft YaHei", "body_ea": "Microsoft YaHei"},
            "logos": [{"file": "brand/logo.png", "kind": "horizontal", "on": "light"},
                      {"file": "brand/logo_plate.png", "kind": "horizontal", "on": "dark"}],
            "logo": {"clear_space": 0.25, "height": 0.6, "min_height": 0.3, "content": "top-right",
                     "cover": "horizontal", "closing": "horizontal"},
            "signature": {"title_bar": "accent"},
            "art": ["brand/mascot.png"],
            "forbid": {"gradients": True, "shadows": True}}


DECK = {"meta": {"title": "测试", "footer": "测试品牌"}, "slides": [
    {"n": 1, "type": "cover", "title": "品牌测试稿", "subtitle": "副标题"},
    {"n": 2, "type": "list", "title": "三件事", "items": [{"title": "一", "text": "第一件"},
                                                       {"title": "二", "text": "第二件"},
                                                       {"title": "三", "text": "第三件"}]},
    {"n": 3, "type": "chart", "title": "增长", "chart": {"type": "column", "categories": ["Q1", "Q2", "Q3"],
                                                        "series": [{"name": "A", "values": [1, 2, 3]},
                                                                   {"name": "B", "values": [2, 1, 2]}]},
     "source": "示例"},
    {"n": 4, "type": "closing", "headline": "谢谢", "body": "再见"}]}


def colors_used(pptx):
    out = set()
    with zipfile.ZipFile(pptx) as z:
        for n in z.namelist():
            if n.endswith(".xml") and (n.startswith("ppt/slides/slide") or n.startswith("ppt/charts/chart")):
                out |= {c.upper() for c in re.findall(r'srgbClr val="([0-9A-Fa-f]{6})"', z.read(n).decode("utf-8"))}
    return out


class SnapTests(unittest.TestCase):
    def test_snap_keeps_text_readable(self):
        allowed = ["14306B", "1FA3F5", "F97316", "F4F6FA", "1F2937", "FFFFFF"]
        self.assertIn(snap_color("5A6B80", allowed), ("1F2937", "14306B"))
        self.assertEqual(snap_color("FAFBFC", allowed), "FFFFFF")
        # a grey for small text: only colours readable on white are candidates
        self.assertIn(snap_color("9AA3AF", allowed, ("FFFFFF",), 4.5), ("1F2937", "14306B"))

    def test_style_palette_is_all_brand(self):
        st = {"palette": {"primary": "14306B", "accent": "F59E0B", "bg_top": "FFFFFF", "bg_bottom": "FFFFFF"},
              "brand": {"colors": [{"hex": h, "role": r} for r, h in PALETTE.items()], "allow": ["FFFFFF"]}}
        S = Style(st)
        allowed = set(PALETTE.values()) | {"FFFFFF"}
        self.assertTrue(set(S.palette.values()) <= allowed, S.palette)
        self.assertEqual(S.palette["accent"], "F97316")
        self.assertTrue(any("F59E0B" in f for f in S.fixes))
        self.assertIn(S.c("primary@0.45"), allowed - {"FFFFFF"})


class BrandKitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        make_manual(cls.tmp / "manual.png")
        cls.w = cls.tmp / "w"
        r = run_script("brand_kit.py", "pages", cls.tmp / "manual.png", cls.w)
        assert r.returncode == 0, r.stdout + r.stderr
        cls.pages = sorted((cls.w / "brand" / "pages").glob("p*.png"))
        p3 = cls.pages[2]
        for args in (("crop", cls.w, p3, 50, 90, 230, 270, "logo", "--clear"),
                     ("crop", cls.w, p3, 390, 90, 570, 310, "mascot", "--clear"),
                     ("plate", cls.w, "brand/logo.png", "logo_plate")):
            r = run_script("brand_kit.py", *args)
            assert r.returncode == 0, r.stdout + r.stderr
        (cls.w / "brand.json").write_text(json.dumps(brand_json(cls.w), ensure_ascii=False), encoding="utf-8")
        r = run_script("brand_kit.py", "apply", cls.w)
        assert r.returncode == 0, r.stdout + r.stderr
        (cls.w / "deck.json").write_text(json.dumps(DECK, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, True)

    def build(self, deck=None, style_edit=None):
        w = self.tmp / "b"
        shutil.rmtree(w, True)
        shutil.copytree(self.w, w)
        if deck:
            (w / "deck.json").write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")
        if style_edit:
            st = json.loads((w / "style.json").read_text(encoding="utf-8"))
            style_edit(st)
            (w / "style.json").write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
        for args in (("plan_deck.py", w, "--level", "full"), ("make_assets.py", w), ("build_deck.py", w)):
            r = run_script(*args)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = run_script("qa_check.py", w)
        rep = json.loads((w / "out" / "qa_report.json").read_text(encoding="utf-8"))
        dump = json.loads((w / "out" / "layout_dump.json").read_text(encoding="utf-8"))
        return w, [i for i in rep["issues"] if i["level"] == "ERROR"], dump

    def test_pages_split_at_the_gaps(self):
        self.assertEqual(len(self.pages), 3)
        self.assertLess(Image.open(self.pages[0]).width, 1000)  # grey sides dropped

    def test_check_finds_colours_in_the_manual(self):
        r = run_script("brand_kit.py", "check", self.w)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertNotIn("找不到", r.stdout)
        b = brand_json(self.w)
        b["colors"][2]["hex"] = "F97361"  # a misread digit
        w2 = self.tmp / "c"
        shutil.rmtree(w2, True)
        shutil.copytree(self.w, w2)
        (w2 / "brand.json").write_text(json.dumps(b), encoding="utf-8")
        self.assertIn("F97361 在手册页面上一个像素都找不到", run_script("brand_kit.py", "check", w2).stdout)

    def test_brand_deck_keeps_to_the_manual(self):
        w, errs, dump = self.build()
        self.assertEqual(errs, [])
        allowed = set(PALETTE.values()) | {"FFFFFF"}
        self.assertTrue(colors_used(w / "out" / "beautified.pptx") <= allowed)
        for sd in dump["slides"]:
            self.assertTrue(any(e.get("role") == "logo" and e["t"] == "image" for e in sd["elements"]), sd["n"])
        closing = dump["slides"][-1]["elements"]
        logo = next(e for e in closing if e.get("role") == "logo" and e["t"] == "image")
        self.assertIn("logo_plate", logo["path"])  # dark closing page: the white-plate logo
        bars = [e for e in dump["slides"][1]["elements"] if e.get("t") == "rect" and e.get("fill") == "accent"
                and e.get("w", 1) < 0.15]
        self.assertTrue(bars)  # the title bar
        man = json.loads((w / "assets" / "manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(any(m.get("method") == "brand" for m in man["assets"]))

    def test_logo_steps_around_a_sticker(self):
        deck = json.loads(json.dumps(DECK))
        deck["slides"][1]["stamps"] = [{"image": str(self.w / "brand" / "mascot.png"), "x": 11.6, "y": 0.4,
                                        "w": 0.9, "h": 0.9}]
        _, errs, dump = self.build(deck)
        self.assertEqual([e for e in errs if e["check"].startswith("brand")], [])
        logo = next(e for e in dump["slides"][1]["elements"] if e.get("role") == "logo" and e["t"] == "image")
        self.assertFalse(logo["x"] > 11 and logo["y"] < 1.5)  # moved off the sticker's corner

    def test_quiet_brand_breaks_are_errors(self):
        # stickers in every corner: nowhere is free, the logo lands in its corner and QA says so
        crowd = json.loads(json.dumps(DECK))
        crowd["slides"][1]["stamps"] = [{"image": str(self.w / "brand" / "mascot.png"), "x": x, "y": y,
                                         "w": 0.9, "h": 0.9}
                                        for x in (0.3, 6.2, 12.1) for y in (0.3, 6.3)]
        cases = {
            "clear space": (crowd, None),
            "tiny logo": (None, lambda st: st["brand"]["logo"].update(height=0.2)),
            "tints": (None, lambda st: st["brand"].update(tints=True)),
        }
        for name, (deck, edit) in cases.items():
            with self.subTest(case=name):
                _, errs, _ = self.build(deck, edit)
                self.assertTrue(any(e["check"].startswith("brand") for e in errs), (name, errs))


class HeaderAndArtTests(BrandKitTests):
    """A manual whose inner pages carry a text header, and a mascot used on purpose."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        b = brand_json(cls.w)
        b["logo"].update(content="header", header_text="测试品牌 TEST")
        b["art"] = [{"file": "brand/mascot.png", "mood": "wave"}, {"file": "brand/logo.png", "mood": "question"}]
        (cls.w / "brand.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
        r = run_script("brand_kit.py", "apply", cls.w)
        assert r.returncode == 0, r.stdout + r.stderr

    def test_brand_deck_keeps_to_the_manual(self):
        deck = json.loads(json.dumps(DECK))
        deck["slides"][1]["kicker"] = "01 · 三件事"
        deck["slides"].insert(2, {"n": 3, "type": "list", "title": "问题来了", "art": "question",
                                  "items": [{"title": "甲", "text": "第一问"}, {"title": "乙", "text": "第二问"}]})
        for i, sl in enumerate(deck["slides"]):
            sl["n"] = i + 1
        w, errs, dump = self.build(deck)
        self.assertEqual([e for e in errs if e["check"].startswith("brand")], [])
        s2 = dump["slides"][1]["elements"]
        self.assertTrue(any(e.get("brand_header") and e.get("text") == "测试品牌 TEST" for e in s2))
        self.assertTrue(any(e.get("brand_header") and e.get("text") == "01 · 三件事" for e in s2))
        self.assertFalse(any(e.get("grp") == "kicker" for e in s2))  # the kicker moved up
        self.assertFalse(any(e.get("role") == "logo" for e in s2))  # no logo picture inside
        plan = json.loads((w / "plan.json").read_text(encoding="utf-8"))
        heroes = {p["n"]: p.get("hero") for p in plan["slides"]}
        self.assertIsNone(heroes[2])  # a list page that did not ask: no mascot
        art = {a["slide"]: a.get("art") for a in plan["assets"] if a["kind"] == "hero"}
        self.assertTrue(art[1].endswith("mascot.png"))  # the cover gets the first one
        self.assertTrue(art[3].endswith("logo.png"))  # "question" picked by mood

    test_quiet_brand_breaks_are_errors = None
    test_logo_steps_around_a_sticker = None


if __name__ == "__main__":
    unittest.main()
