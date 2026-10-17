"""Photos from stock libraries or the user's own files, for picture slots without an image model.

Network calls are replaced with canned responses shaped like each library's API.
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
from unittest.mock import patch
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from PIL import Image

import photo_assets as PA


def run_script(name, *args, env=None):
    return subprocess.run([sys.executable, str(SCRIPTS / name), *map(str, args)],
                          capture_output=True, text=True, encoding="utf-8",
                          env=dict(os.environ, PYTHONIOENCODING="utf-8", **(env or {})))


def make_work(tmp):
    work = Path(tmp) / "w"
    work.mkdir()
    shutil.copy(ROOT / "references" / "styles" / "business-blue.json", work / "style.json")
    deck = {"meta": {}, "slides": [{"n": 1, "type": "cover", "title": "cover"},
                                    {"n": 2, "type": "list", "title": "list", "items": [{"text": "a"}, {"text": "b"}]}]}
    (work / "deck.json").write_text(json.dumps(deck), encoding="utf-8")
    r = run_script("plan_deck.py", work, "--level", "full")
    assert r.returncode == 0, r.stdout + r.stderr
    photo = Path(tmp) / "photo.jpg"
    Image.new("RGB", (1200, 800), (180, 120, 60)).save(photo)
    return work, photo


def heroes(work):
    return [a for a in json.loads((work / "plan.json").read_text(encoding="utf-8"))["assets"] if a["kind"] == "hero"]


class FitTests(unittest.TestCase):
    def test_crop_to_slot_with_rounded_inset(self):
        out = PA.fit_photo(Image.new("RGB", (2000, 500), "red"), (1400, 830))
        self.assertEqual(out.size, (1400, 830))
        self.assertEqual(out.mode, "RGBA")
        self.assertEqual(out.getpixel((0, 0))[3], 0)           # corner outside the card
        self.assertEqual(out.getpixel((700, 415))[:3], (255, 0, 0))  # centre is the photo

    def test_tint_pulls_toward_colour(self):
        out = PA.fit_photo(Image.new("RGB", (800, 600), (255, 255, 255)), (800, 600), tint=0.2,
                           tint_color=(0, 0, 255))
        r, g, b, _ = out.getpixel((400, 300))
        self.assertLess(r, 255)
        self.assertEqual(b, 255)


class LicenceTests(unittest.TestCase):
    def test_wikimedia_licence_filter(self):
        m = lambda s: {"LicenseShortName": {"value": s}}
        self.assertEqual(PA._wm_license(m("CC0")), "cc0")
        self.assertEqual(PA._wm_license(m("Public domain")), "pdm")
        self.assertEqual(PA._wm_license(m("CC BY-SA 4.0")), "by-sa")
        self.assertEqual(PA._wm_license(m("CC BY 2.0")), "by")
        self.assertIsNone(PA._wm_license(m("CC BY-NC 2.0")))
        self.assertIsNone(PA._wm_license(m("CC BY-ND 3.0")))
        self.assertIsNone(PA._wm_license(m("Copyrighted")))

    def test_openverse_drops_non_commercial(self):
        resp = {"results": [
            {"id": "1", "title": "ok", "url": "u1", "thumbnail": "t1", "creator": "A", "license": "by"},
            {"id": "2", "title": "nc", "url": "u2", "thumbnail": "t2", "creator": "B", "license": "by-nc"},
            {"id": "3", "title": "zero", "url": "u3", "thumbnail": "t3", "creator": "C", "license": "cc0"}]}
        with patch.object(PA, "get_json", return_value=resp):
            got = PA.s_openverse("cat", 8, {})
        self.assertEqual([g["id"] for g in got], ["1", "3"])
        self.assertEqual(got[0]["preview"], "t1")

    def test_keyed_libraries_skip_without_key(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(PA.s_pexels("cat", 4, {}))
            self.assertEqual(PA.usable_sources({}), ["openverse", "wikimedia"])
        with patch.dict(os.environ, {"PEXELS_API_KEY": "k"}, clear=True):
            self.assertEqual(PA.usable_sources({})[0], "pexels")


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.work, self.photo = make_work(self.tmp)
        self.hid = heroes(self.work)[0]["id"]

    def manifest(self):
        return {m["id"]: m for m in json.loads((self.work / "assets" / "manifest.json").read_text(encoding="utf-8"))["assets"]}

    def test_local_photo_survives_force_and_drop_reverts(self):
        r = run_script("photo_assets.py", "local", self.work, self.hid, self.photo)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.manifest()[self.hid]["method"], "user")
        r = run_script("make_assets.py", self.work, "--force")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.manifest()[self.hid]["method"], "user")
        r = run_script("photo_assets.py", "drop", self.work, self.hid)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        run_script("make_assets.py", self.work)
        self.assertEqual(self.manifest()[self.hid]["method"], "procedural")

    def test_pick_records_credit(self):
        d = self.work / "photos" / self.hid
        d.mkdir(parents=True)
        shutil.copy(self.photo, d / "cand_01.jpg")
        cand = {"n": 1, "source": "openverse", "id": "x", "preview": self.photo.as_uri(), "full": self.photo.as_uri(),
                "author": "Jane", "page": "https://example.org/p", "license": "by", "license_url": "",
                "file": str(d / "cand_01.jpg")}
        (d / "candidates.json").write_text(json.dumps({"id": self.hid, "query": "q", "candidates": [cand]}),
                                           encoding="utf-8")
        r = run_script("photo_assets.py", "pick", self.work, self.hid, 1)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("CREDIT", r.stdout)
        m = self.manifest()[self.hid]
        self.assertEqual((m["method"], m["credit"]["author"]), ("photo:openverse", "Jane"))
        credits = (self.work / "out" / "image_credits.md").read_text(encoding="utf-8")
        self.assertIn("Jane", credits)
        self.assertIn("CC BY", credits)

    def test_search_offline_exits_2(self):
        with patch.object(PA, "fetch", side_effect=urllib.error.URLError("blocked")), \
                patch("sys.argv", ["photo_assets.py", "search", str(self.work), self.hid, "cat", "--sources", "openverse,wikimedia"]):
            self.assertEqual(PA.main(), 2)

    def test_search_makes_candidate_sheet(self):
        canned = [{"source": "openverse", "id": str(i), "title": "", "preview": "p", "full": "f", "author": "",
                   "author_url": "", "page": "", "license": "cc0", "license_url": ""} for i in range(3)]
        buf = Path(self.tmp) / "thumb.jpg"
        Image.new("RGB", (300, 200), "blue").save(buf)
        with patch.dict(PA.LIBRARIES, {"openverse": lambda q, n, c: canned}), \
                patch.object(PA, "fetch", return_value=buf.read_bytes()), \
                patch("sys.argv", ["photo_assets.py", "search", str(self.work), self.hid, "cat", "--sources", "openverse"]):
            self.assertEqual(PA.main(), 0)
        d = self.work / "photos" / self.hid
        self.assertTrue((d / "sheet.png").exists())
        self.assertEqual(len(json.loads((d / "candidates.json").read_text(encoding="utf-8"))["candidates"]), 3)

    def test_status_asks_when_no_model(self):
        r = run_script("make_assets.py", self.work, "--status", env={"LUOBO_PPT_CONFIG": str(Path(self.tmp) / "none.json")})
        self.assertIn("ASK", r.stdout)


if __name__ == "__main__":
    unittest.main()
