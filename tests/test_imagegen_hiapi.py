"""HiAPI provider: submit a task, poll until success, read the picture from the output url."""
from pathlib import Path
import io
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from PIL import Image

import imagegen as IG


def resp(js=None, status=200, content=b""):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = js
    r.text = str(js)
    r.content = content
    r.raise_for_status = lambda: None
    return r


class HiapiTests(unittest.TestCase):
    def setUp(self):
        buf = io.BytesIO()
        Image.new("RGBA", (64, 48), (255, 0, 0, 255)).save(buf, "PNG")
        self.png = buf.getvalue()
        self.gen = IG.ImageGen({"provider": "hiapi", "api_key": "k", "timeout": 30, "retries": 0})

    def test_defaults(self):
        self.assertEqual(self.gen.base_url, "https://api.hiapi.ai")
        self.assertEqual(self.gen.available()[0], True)

    def test_submit_poll_download(self):
        posts = []

        def post(url, json=None, headers=None, timeout=None):
            posts.append((url, json))
            return resp({"code": 200, "data": {"taskId": "tk-1"}})
        polls = iter([resp({"data": {"status": "handling"}}),
                      resp({"data": {"status": "success", "output": [{"url": "https://x/img.png"}]}})])

        def get(url, headers=None, timeout=None):
            return next(polls) if "/v1/tasks/" in url else resp(content=self.png)
        with patch("requests.post", post), patch("requests.get", get), patch("time.sleep"):
            img, native = self.gen.generate("a cup", 1400, 830, transparent=True)
        url, body = posts[0]
        self.assertTrue(url.endswith("/v1/tasks"))
        self.assertEqual(body["model"], "gpt-image-2.5-flare/text-to-image")
        self.assertEqual(body["input"]["aspect_ratio"], "16:9")
        self.assertEqual(body["input"]["background"], "transparent")
        self.assertTrue(native)
        self.assertEqual(img.size, (64, 48))

    def test_failed_task_raises(self):
        with patch("requests.post", lambda *a, **k: resp({"data": {"taskId": "tk-2"}})), \
                patch("requests.get", lambda *a, **k: resp({"data": {"status": "fail", "error": {"msg": "bad"}}})), \
                patch("time.sleep"):
            with self.assertRaises(RuntimeError):
                self.gen.generate("a cup", 1000, 1000)

    def test_no_transparency_above_1k(self):
        g = IG.ImageGen({"provider": "hiapi", "api_key": "k", "resolution": "2K", "retries": 0})
        seen = {}

        def post(url, json=None, headers=None, timeout=None):
            seen.update(json["input"])
            return resp({"data": {"taskId": "t"}})
        with patch("requests.post", post), \
                patch("requests.get", lambda u, **k: resp({"data": {"status": "success", "output": [{"url": "u"}]}}) if "/v1/tasks/" in u else resp(content=self.png)), \
                patch("time.sleep"):
            _, native = g.generate("a cup", 1000, 1000, transparent=True)
        self.assertNotIn("background", seen)
        self.assertFalse(native)


if __name__ == "__main__":
    unittest.main()
