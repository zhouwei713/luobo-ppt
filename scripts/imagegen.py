"""Configurable AI image generation with graceful fallback.

Config lookup order (first found wins):
  1. --config PATH passed to make_assets.py
  2. env LUOBO_PPT_CONFIG
  3. ./luobo-ppt.config.json, then WORK_DIR/luobo-ppt.config.json
  4. ~/.config/luobo-ppt/config.json
  5. <skill>/config.json
Names from the skill's earlier releases (ppt-studio: PPT_STUDIO_*, ppt-studio.config.json,
~/.config/ppt-studio/; ppt-beautify: PPT_BEAUTIFY_* and the same patterns) are still honoured after the new ones.
If nothing is found but env LUOBO_PPT_PROVIDER is set, a config is built from env.
No config -> provider "none" -> callers use fallback_art (procedural).

Providers:
  openai             OpenAI Images API (gpt-image-1 / dall-e-3). Native transparent PNG with gpt-image-1.
  gemini             Google Gemini image models (generateContent, inline image data).
  ark                Volcengine Ark (Seedream / 即梦 models), OpenAI-style images endpoint.
  openai_compatible  Any service exposing POST {base_url}/images/generations.
  hiapi              HiAPI async task API (POST /v1/tasks, poll /v1/tasks/{id}); default gpt-image-2.5-flare.
  command            Run a local command template; it must write the PNG to {out}.
See config.example.json and references/imagegen_config.md.
"""
import base64
import io
import json
import os
import shlex
import subprocess
import time
from pathlib import Path

from common import SKILL_DIR

DEFAULTS = {
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-image-1", "api_key_env": "OPENAI_API_KEY"},
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta", "model": "gemini-2.5-flash-image",
               "api_key_env": "GEMINI_API_KEY"},
    "ark": {"base_url": "https://ark.cn-beijing.volces.com/api/v3", "model": "doubao-seedream-4-0-250828",
            "api_key_env": "ARK_API_KEY"},
    "openai_compatible": {"api_key_env": "IMAGE_API_KEY"},
    "hiapi": {"base_url": "https://api.hiapi.ai", "model": "gpt-image-2.5-flare/text-to-image",
              "api_key_env": "HIAPI_API_KEY"},
}


def find_config(explicit=None, work_dir=None):
    cands = []
    if explicit:
        cands.append(Path(explicit))
    for env in ("LUOBO_PPT_CONFIG", "PPT_STUDIO_CONFIG", "PPT_BEAUTIFY_CONFIG"):
        if os.environ.get(env):
            cands.append(Path(os.environ[env]))
    for name in ("luobo-ppt.config.json", "ppt-studio.config.json", "ppt-beautify.config.json"):
        cands.append(Path.cwd() / name)
        if work_dir:
            cands.append(Path(work_dir) / name)
    cands.append(Path.home() / ".config" / "luobo-ppt" / "config.json")
    cands.append(Path.home() / ".config" / "ppt-studio" / "config.json")
    cands.append(Path.home() / ".config" / "ppt-beautify" / "config.json")
    cands.append(SKILL_DIR / "config.json")
    for c in cands:
        if c.exists():
            with open(c, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            cfg["_path"] = str(c)
            return cfg
    prov = (os.environ.get("LUOBO_PPT_PROVIDER") or os.environ.get("PPT_STUDIO_PROVIDER")
            or os.environ.get("PPT_BEAUTIFY_PROVIDER"))
    if prov:
        g = lambda k: (os.environ.get(f"LUOBO_PPT_{k}") or os.environ.get(f"PPT_STUDIO_{k}")
                       or os.environ.get(f"PPT_BEAUTIFY_{k}"))
        return {"provider": prov, "model": g("MODEL"), "base_url": g("BASE_URL"), "_path": "env"}
    return {"provider": "none", "_path": None}


class ImageGen:
    def __init__(self, cfg):
        self.cfg = dict(cfg or {})
        self.provider = (self.cfg.get("provider") or "none").lower()
        d = DEFAULTS.get(self.provider, {})
        self.base_url = (self.cfg.get("base_url") or d.get("base_url") or "").rstrip("/")
        self.model = self.cfg.get("model") or d.get("model")
        key_env = self.cfg.get("api_key_env") or d.get("api_key_env")
        self.api_key = self.cfg.get("api_key") or (os.environ.get(key_env) if key_env else None)
        self.timeout = int(self.cfg.get("timeout", 180))
        self.extra = self.cfg.get("extra", {})
        self.retries = int(self.cfg.get("retries", 1))

    # ------------------------------------------------------------ status
    def available(self):
        if self.provider in ("none", "", None):
            return False, "no image provider configured"
        if self.provider == "command":
            return (bool(self.cfg.get("command")), "command template missing")
        if self.provider not in DEFAULTS:
            return False, f"unknown provider '{self.provider}'"
        if not self.api_key:
            return False, f"api key missing for {self.provider}"
        if not self.base_url:
            return False, "base_url missing"
        return True, f"{self.provider}:{self.model}"

    def use_for(self, kind):
        u = self.cfg.get("use_for", {"hero": True, "background": False})
        return bool(u.get(kind, kind == "hero"))

    # ------------------------------------------------------------ main
    def generate(self, prompt, w, h, transparent=False, out=None):
        """Returns (PIL.Image RGBA, native_transparent: bool)."""
        last = None
        for attempt in range(self.retries + 1):
            try:
                fn = getattr(self, "_gen_" + self.provider)
                return fn(prompt, w, h, transparent, out)
            except Exception as e:  # noqa: BLE001
                last = e
                time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"{self.provider} failed: {last}")

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _img(data_b64=None, url=None, raw=None):
        from PIL import Image
        if data_b64:
            raw = base64.b64decode(data_b64)
        elif url:
            import requests
            r = requests.get(url, timeout=120)
            r.raise_for_status()
            raw = r.content
        return Image.open(io.BytesIO(raw)).convert("RGBA")

    def _post(self, url, body, headers):
        import requests
        body = {**body, **self.extra}
        r = requests.post(url, json=body, headers=headers, timeout=self.timeout)
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:400]}")
        return r.json()

    @staticmethod
    def _aspect_size(w, h, options):
        ar = w / h
        return min(options, key=lambda s: abs((s[0] / s[1]) - ar))

    # ------------------------------------------------------------ providers
    def _gen_openai(self, prompt, w, h, transparent, out):
        m = (self.model or "").lower()
        if m.startswith("dall-e-3"):
            sw, sh = self._aspect_size(w, h, [(1024, 1024), (1792, 1024), (1024, 1792)])
        else:
            sw, sh = self._aspect_size(w, h, [(1024, 1024), (1536, 1024), (1024, 1536)])
        body = {"model": self.model, "prompt": prompt, "size": f"{sw}x{sh}", "n": 1}
        native = False
        if m.startswith("gpt-image"):
            body["quality"] = self.cfg.get("quality", "medium")
            if transparent:
                body["background"] = "transparent"
                body["output_format"] = "png"
                native = True
        else:
            body["response_format"] = "b64_json"
        js = self._post(f"{self.base_url}/images/generations", body,
                        {"Authorization": f"Bearer {self.api_key}"})
        d = js["data"][0]
        return self._img(d.get("b64_json"), d.get("url")), native

    def _gen_openai_compatible(self, prompt, w, h, transparent, out):
        size = self.cfg.get("size") or "{}x{}".format(*self._aspect_size(w, h, [(1024, 1024), (1536, 1024), (1024, 1536)]))
        body = {"model": self.model, "prompt": prompt, "size": size, "n": 1,
                "response_format": self.cfg.get("response_format", "b64_json")}
        js = self._post(f"{self.base_url}/images/generations", body,
                        {"Authorization": f"Bearer {self.api_key}"})
        d = js["data"][0]
        return self._img(d.get("b64_json"), d.get("url")), False

    def _gen_ark(self, prompt, w, h, transparent, out):
        # Seedream accepts WxH (roughly 1K..4K); keep aspect, long side 2048
        ar = w / h
        sw, sh = (2048, int(2048 / ar)) if ar >= 1 else (int(2048 * ar), 2048)
        sw, sh = max(1024, sw - sw % 8), max(1024, sh - sh % 8)
        body = {"model": self.model, "prompt": prompt, "size": self.cfg.get("size", f"{sw}x{sh}"),
                "response_format": "b64_json", "watermark": False}
        js = self._post(f"{self.base_url}/images/generations", body,
                        {"Authorization": f"Bearer {self.api_key}"})
        d = js["data"][0]
        return self._img(d.get("b64_json"), d.get("url")), False

    def _gen_gemini(self, prompt, w, h, transparent, out):
        ratios = {"1:1": 1, "4:3": 4 / 3, "3:4": 3 / 4, "16:9": 16 / 9, "9:16": 9 / 16, "3:2": 1.5, "2:3": 2 / 3}
        ar = min(ratios, key=lambda k: abs(ratios[k] - w / h))
        body = {"contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": ar}}}
        js = self._post(f"{self.base_url}/models/{self.model}:generateContent", body,
                        {"x-goog-api-key": self.api_key})
        for cand in js.get("candidates", []):
            for part in cand.get("content", {}).get("parts", []):
                data = part.get("inlineData") or part.get("inline_data")
                if data and data.get("data"):
                    return self._img(data["data"]), False
        raise RuntimeError("no image in Gemini response: " + json.dumps(js)[:300])

    def _gen_hiapi(self, prompt, w, h, transparent, out):
        """HiAPI task API: POST /v1/tasks, then poll GET /v1/tasks/{id} until success."""
        import requests
        ratios = {"1:1": 1, "3:2": 1.5, "2:3": 2 / 3, "4:3": 4 / 3, "3:4": 3 / 4, "16:9": 16 / 9, "9:16": 9 / 16,
                  "21:9": 21 / 9, "9:8": 9 / 8, "8:9": 8 / 9}
        ar = min(ratios, key=lambda k: abs(ratios[k] - w / h))
        res = self.cfg.get("resolution", "1K")
        inp = {"prompt": prompt, "aspect_ratio": ar, "resolution": res}
        native = bool(transparent and res == "1K")  # transparent output only exists at 1K
        if native:
            inp["background"] = "transparent"
        hdr = {"Authorization": f"Bearer {self.api_key}"}
        js = self._post(f"{self.base_url}/v1/tasks", {"model": self.model, "input": inp}, hdr)
        tid = (js.get("data") or {}).get("taskId")
        if not tid:
            raise RuntimeError("no taskId: " + json.dumps(js, ensure_ascii=False)[:300])
        deadline = time.time() + self.timeout
        wait = 3
        while time.time() < deadline:
            time.sleep(wait)
            wait = min(wait + 2, 10)
            r = requests.get(f"{self.base_url}/v1/tasks/{tid}", headers=hdr, timeout=60)
            if r.status_code >= 400:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
            d = r.json().get("data") or {}
            st = d.get("status")
            if st == "success":
                outs = d.get("output") or []
                if not outs or not outs[0].get("url"):
                    raise RuntimeError("success without output url")
                return self._img(url=outs[0]["url"]), native
            if st == "fail":
                raise RuntimeError("task failed: " + json.dumps(d.get("error"), ensure_ascii=False)[:300])
        raise RuntimeError(f"task {tid} not done after {self.timeout}s")

    def _gen_command(self, prompt, w, h, transparent, out):
        from PIL import Image
        out = Path(out or "gen.png")
        pf = out.with_suffix(".prompt.txt")
        pf.write_text(prompt, encoding="utf-8")
        cmd = self.cfg["command"].format(prompt_file=shlex.quote(str(pf)), out=shlex.quote(str(out)),
                                         w=w, h=h, prompt=shlex.quote(prompt))
        subprocess.run(cmd, shell=True, check=True, timeout=self.timeout)
        return Image.open(out).convert("RGBA"), bool(self.cfg.get("native_transparent", False))


# ---------------------------------------------------------------- background removal
def remove_background(img, tol=26, feather=1.2):
    """Make the flat background transparent.

    Uses rembg when installed; otherwise flood-fills from the borders on the
    border color (prompts ask for a plain white background, which this handles well).
    """
    try:
        from rembg import remove  # type: ignore
        return remove(img)
    except Exception:
        pass
    import numpy as np
    from PIL import Image, ImageFilter
    from scipy import ndimage
    a = np.asarray(img.convert("RGB")).astype(int)
    h, w, _ = a.shape
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    bgc = np.median(border, axis=0)
    dist = np.sqrt(((a - bgc) ** 2).sum(-1))
    cand = dist < tol
    lab, _n = ndimage.label(cand)
    edge_labels = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    bgmask = np.isin(lab, list(edge_labels))
    alpha = np.where(bgmask, 0, 255).astype("uint8")
    al = Image.fromarray(alpha).filter(ImageFilter.GaussianBlur(feather))
    out = img.convert("RGBA")
    out.putalpha(al)
    return out


def trim_transparent(img, pad=0.04):
    bbox = img.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
    if not bbox:
        return img
    x0, y0, x1, y1 = bbox
    p = int(max(img.size) * pad)
    return img.crop((max(0, x0 - p), max(0, y0 - p), min(img.width, x1 + p), min(img.height, y1 + p)))
