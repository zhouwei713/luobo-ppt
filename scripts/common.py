"""Shared helpers for luobo-ppt scripts."""
import json
import os
import re
import glob
import zipfile
import shutil
import tempfile
from pathlib import Path

SKILL_VERSION = "2.8.0"
SKILL_DIR = Path(__file__).resolve().parent.parent
# bundled icons and gallery: <skill>/assets, or <skill>/scripts/assets in packages whose
# platform only allows SKILL.md + references/ + scripts/ + templates/ (WorkBuddy)
ASSET_DIR = next((d for d in (SKILL_DIR / "assets", Path(__file__).resolve().parent / "assets",
                               Path(__file__).resolve().parent)
                  if (d / "icons.json").exists()), SKILL_DIR / "assets")


def style_file(name):
    """Preset style json: references/styles/<name>.json, or references/style-<name>.json in
    flat packages (platforms that allow only one directory level, e.g. WorkBuddy)."""
    nested = SKILL_DIR / "references" / "styles" / f"{name}.json"
    return nested if nested.exists() else SKILL_DIR / "references" / f"style-{name}.json"
SETUP_CACHE = Path.home() / ".config" / "luobo-ppt" / "setup.json"

# Design canvas used by all layouts (16:9 widescreen, inches)
CANVAS_W = 13.333
CANVAS_H = 7.5


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(obj, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- colors
def hex_clean(h):
    h = str(h).strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return h.upper()[:6]


def hex_to_rgb(h):
    h = hex_clean(h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "".join(f"{max(0, min(255, int(round(c)))):02X}" for c in rgb[:3])


def mix(h1, h2, t):
    """Blend color h1 toward h2 by t (0..1)."""
    a, b = hex_to_rgb(h1), hex_to_rgb(h2)
    return rgb_to_hex([a[i] + (b[i] - a[i]) * t for i in range(3)])


def rel_lum(h):
    def ch(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = hex_to_rgb(h)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(h1, h2):
    l1, l2 = rel_lum(h1), rel_lum(h2)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


# minimum contrast on the page for colours used as text (big numbers and headlines are large text)
TEXT_ROLES = {"text": 4.5, "muted": 4.5, "subtle": 4.5, "secondary": 4.5, "label": 4.5, "strong": 3.0, "highlight": 3.0}


def brand_allowed(brand):
    """The colours a brand kit lets onto a page: its palette plus the extra neutrals it allows."""
    out = [hex_clean(c["hex"]) for c in brand.get("colors", []) if c.get("hex")]
    out += [hex_clean(c) for c in brand.get("allow", [])]
    return list(dict.fromkeys(out))


def color_dist(a, b):
    """Perceptual-ish distance ("redmean" weighted RGB)."""
    r1, g1, b1 = hex_to_rgb(a)
    r2, g2, b2 = hex_to_rgb(b)
    rm = (r1 + r2) / 2
    return (((512 + rm) * (r1 - r2) ** 2) / 256 + 4 * (g1 - g2) ** 2 + ((767 - rm) * (b1 - b2) ** 2) / 256) ** 0.5


def snap_color(c, allowed, page=None, need=0.0):
    """Nearest allowed colour; with `page` (background colours) only ones reading at `need`:1."""
    c = hex_clean(c)
    if not allowed:
        return c
    cands = [a for a in allowed if not page or min(contrast(a, p) for p in page) >= need] if need else list(allowed)
    if not cands:
        return None
    return min(cands, key=lambda a: color_dist(a, c))


class Style:
    """Wraps style.json; resolves color tokens like 'primary' or '#AABBCC'."""

    DEFAULT_PALETTE = {
        "primary": "17806D", "primary_dark": "115E52", "accent": "F4D35E",
        "bg_top": "CFF1E2", "bg_bottom": "F6FCF9", "surface": "FFFFFF",
        "tint": "DDF3EA", "text": "1F3A33", "muted": "5E7069", "on_primary": "FFFFFF",
        "line": "CFE6DC",
    }

    def __init__(self, data):
        self.data = data
        pal = dict(self.DEFAULT_PALETTE)
        pal.update({k: hex_clean(v) for k, v in data.get("palette", {}).items()})
        # derived roles
        self.dark = rel_lum(pal["bg_bottom"]) < 0.18
        if "strong" not in data.get("palette", {}):
            # headline color: deep primary on light backgrounds, light primary on dark ones
            pal["strong"] = mix(pal["primary"], "FFFFFF", 0.55) if self.dark else pal["primary_dark"]
        if "highlight" not in data.get("palette", {}):
            # colored text (numbers, side titles): primary on light, lifted primary on dark
            pal["highlight"] = mix(pal["primary"], "FFFFFF", 0.4) if self.dark else pal["primary"]
        # fourth text level: meta text (page numbers, sources, footers), lighter than muted
        # but still readable (>= 4.5:1 on the page background)
        if "subtle" not in data.get("palette", {}):
            bgc = pal["bg_bottom"]
            sub = pal["muted"]
            for k in ((0.3, 0.2, 0.1) if not self.dark else ()):  # dark pages: blobs brighten corners, keep muted
                cand = mix(pal["muted"], bgc, k)
                # backgrounds are gradients with soft blobs: stay readable on both ends
                if min(contrast(cand, pal["bg_bottom"]), contrast(cand, pal["bg_top"])) >= 5.2:
                    sub = cand
                    break
            pal["subtle"] = sub
        # second text level: between body text and muted, for card descriptions
        if "secondary" not in data.get("palette", {}):
            pal["secondary"] = mix(pal["text"], pal["muted"], 0.5)
        # small grey text must stay readable even when style.json sets it by eye:
        # pull muted / subtle toward the body text colour until 4.6:1 on both background ends
        self.fixes = []
        for key in ("muted", "subtle"):
            c0 = pal[key]
            c = c0
            for k in range(1, 11):
                if min(contrast(c, pal["bg_top"]), contrast(c, pal["bg_bottom"])) >= 4.6:
                    break
                c = mix(c0, pal["text"], k / 10)
            if c != c0:
                pal[key] = c
                self.fixes.append(f"{key} #{c0} 在背景上太浅，已加深到 #{c}")
        # "label": highlight pulled just far enough toward the text colour to read at 12pt
        # (kickers, small item numbers). highlight itself stays vivid for big numbers and marks.
        if "label" not in pal and "highlight" in pal:
            c0 = c = pal["highlight"]
            for k in range(1, 21):
                if min(contrast(c, pal["bg_top"]), contrast(c, pal["bg_bottom"])) >= 4.6:
                    break
                c = mix(c0, pal["text"], k / 20)
            pal["label"] = c
        self.brand = data.get("brand") or None
        if self.brand:
            # a brand kit: every colour on the page comes from the manual's palette. Derived roles
            # (muted grey, label blue, light tints) are snapped to the nearest brand colour, text
            # roles only to brand colours that stay readable on the page
            self.allowed = brand_allowed(self.brand)
            if not self.brand.get("tints", False):
                page = (pal["bg_top"], pal["bg_bottom"])
                given = {k: hex_clean(v) for k, v in data.get("palette", {}).items()}
                # text sits on the page and on the light cards: readable on both
                grounds = tuple(dict.fromkeys(page + (pal["surface"], pal["tint"])))
                order = {"primary": 0, "secondary": 1, "accent": 2, "extra": 3, "text": 4}
                by_role = [hex_clean(c["hex"]) for c in sorted(self.brand.get("colors", []),
                                                                key=lambda c: order.get(c.get("role"), 9))
                           if c.get("hex") and c.get("role") in order]
                for k, v in list(pal.items()):
                    need = TEXT_ROLES.get(k, 0)
                    snapped = snap_color(v, self.allowed, grounds if need else None, need)
                    if need and (snapped is None or snapped != snap_color(v, self.allowed)):
                        # the nearest colour does not read: go down the manual's own hierarchy
                        # (primary, secondary, accent...) instead of borrowing a look-alike hue
                        snapped = next((c for c in by_role if min(contrast(c, g) for g in grounds) >= need), None)
                    pal[k] = snapped or pal.get("text", v)
                    if k in given and pal[k] != given[k]:
                        self._snapped = getattr(self, "_snapped", []) + [f"{k} #{given[k]} 不在品牌色板里，按 #{pal[k]} 用"]
        self.palette = pal
        self.fixes += getattr(self, "_snapped", [])
        sh = data.get("shape", {})
        # depth: flat (no edge) | ring (1px line) | whisper (very soft halo) | shadow (classic drop)
        self.depth = sh.get("depth") or ("shadow" if sh.get("shadow", True) else "ring")
        f = data.get("fonts", {})
        self.fonts = {
            "heading_ea": f.get("heading_ea", "Microsoft YaHei"),
            "body_ea": f.get("body_ea", "Microsoft YaHei"),
            "heading_latin": f.get("heading_latin", "Arial"),
            "body_latin": f.get("body_latin", "Arial"),
            "display_latin": f.get("display_latin", f.get("heading_latin", "Arial")),
        }
        self.shape = {"radius": 0.16, "shadow": True, "card_alpha": 0.86}
        self.shape.update(data.get("shape", {}))
        self.decor = {"header": True, "leaf": True, "brush": True, "title_mark": True,
                      "sparkles": True, "closing_dark": True}
        self.decor.update(data.get("decor", {}))
        self.illustration = data.get("illustration", {})
        self.background = data.get("background", {})

    def c(self, token, default="text"):
        if token is None:
            token = default
        t = str(token)
        if t in self.palette:
            return self.palette[t]
        if re.fullmatch(r"#?[0-9A-Fa-f]{6}|#?[0-9A-Fa-f]{3}", t):
            return hex_clean(t)
        # token with modifier e.g. "primary@0.3" = 30% primary over the page tone
        # (white on light styles, the background colour on dark ones)
        m = re.fullmatch(r"(\w+)@([0-9.]+)", t)
        if m and m.group(1) in self.palette:
            base = self.palette["bg_bottom"] if getattr(self, "dark", False) else "FFFFFF"
            c = mix(base, self.palette[m.group(1)], float(m.group(2)))
            if self.brand and not self.brand.get("tints", False):
                # a light wash (under 0.3) stays a light brand colour; anything stronger is a
                # fill that has to show on the page, so the page colours are not candidates
                if float(m.group(2)) < 0.3:
                    c = snap_color(c, self.allowed)
                else:
                    page = {self.palette["bg_top"], self.palette["bg_bottom"], self.palette["surface"]}
                    c = snap_color(c, [a for a in self.allowed if a not in page] or self.allowed)
            return c
        return self.palette.get(default, "333333")

    def brand_series(self):
        """Chart series colours for a brand deck: the brand colours that read on the card,
        primary first, then the rest by contrast (a pale yellow line on white comes last)."""
        if not self.brand:
            return None
        surf = self.palette["surface"]
        order = {"primary": 0, "secondary": 1, "accent": 2, "extra": 3}
        cols = []
        for x in sorted(self.brand.get("colors", []), key=lambda x: order.get(x.get("role"), 9)):
            c = hex_clean(x["hex"])
            if x.get("role") in ("background", "neutral") or c in cols or c in (surf, self.palette["bg_top"]):
                continue
            cols.append(c)
        if not cols:
            return [self.palette["primary"]]
        # the manual's order (primary, secondary, accent, extra), with colours that barely show on
        # the card (a light yellow on white) moved to the end
        return [c for c in cols if contrast(c, surf) >= 1.6] + [c for c in cols if contrast(c, surf) < 1.6]


def load_style(path):
    return Style(load_json(path))


# ---------------------------------------------------------------- pptx normalize
def normalize_pptx(src, dst):
    """Rewrite a pptx so LibreOffice/python-pptx can read it.

    Some generators write zip entries with backslashes (ppt\\slides/) which make
    LibreOffice fail with 'source file could not be loaded'. We rebuild the zip
    skipping bogus directory entries and fixing separators.
    """
    src, dst = str(src), str(dst)
    with zipfile.ZipFile(src) as zin:
        names = zin.namelist()
        bad = any("\\" in n for n in names)
        if not bad:
            if os.path.abspath(src) != os.path.abspath(dst):
                shutil.copyfile(src, dst)
            return dst
        tmp = dst + ".tmp"
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
            seen = set()
            # [Content_Types].xml first
            order = sorted(names, key=lambda n: 0 if n == "[Content_Types].xml" else 1)
            for n in order:
                fixed = n.replace("\\", "/")
                if fixed.endswith("/") or fixed in seen:
                    continue
                seen.add(fixed)
                zout.writestr(fixed, zin.read(n))
    os.replace(tmp, dst)
    return dst


# ---------------------------------------------------------------- fonts for measuring
_FONT_CACHE = {}


CJK_FONT_CANDIDATES = {
    True: [  # bold
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Bold.ttc",
        "C:/Windows/Fonts/msyhbd.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
    ],
    False: [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ],
}


def _find_font_file(bold):
    for c in CJK_FONT_CANDIDATES[True] if bold else []:
        if os.path.exists(c):
            return c
    for c in CJK_FONT_CANDIDATES[False]:
        if os.path.exists(c):
            return c
    pats = ["/usr/share/fonts/**/*CJK*.tt*", "/usr/share/fonts/**/*[Hh]ei*.tt*",
            os.path.expanduser("~/.fonts/**/*CJK*.tt*"), os.path.expanduser("~/Library/Fonts/*CJK*.tt*")]
    for pat in pats:
        hits = glob.glob(pat, recursive=True)
        if hits:
            return hits[0]
    return None


def find_cjk_font():
    return _find_font_file(False)


def _cached_tool(key):
    try:
        with open(SETUP_CACHE, "r", encoding="utf-8") as f:
            p = json.load(f).get(key)
        return p if p and os.path.exists(p) else None
    except Exception:
        return None


def find_soffice():
    """LibreOffice executable: PATH, cached setup result, then common install locations."""
    for name in ("soffice", "libreoffice"):
        p = shutil.which(name)
        if p:
            return p
    p = _cached_tool("soffice")
    if p:
        return p
    cands = [
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        "/opt/libreoffice/program/soffice",
        "/usr/lib/libreoffice/program/soffice",
        "/snap/bin/libreoffice",
    ]
    cands += glob.glob("/opt/libreoffice*/program/soffice")
    for c in cands:
        if os.path.exists(c):
            return c
    return None


def find_pdftoppm():
    return shutil.which("pdftoppm") or _cached_tool("pdftoppm")


def get_font(size_px, bold=False):
    from PIL import ImageFont
    key = (int(size_px), bold)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    path = _find_font_file(bold)
    try:
        font = ImageFont.truetype(path, int(size_px)) if path else ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()
    _FONT_CACHE[key] = font
    return font


def strip_marks(s):
    return (s or "").replace("**", "")


def text_width_pt(text, size_pt, bold=False, latin_scale=1.0):
    """Approximate rendered width (pt) of a single line.

    latin_scale widens latin letters/digits for wide display faces (Arial Black ~1.25),
    since measuring uses a CJK sans whose latin glyphs are narrower.
    """
    scale = 4  # measure at 4x for precision
    f = get_font(size_pt * scale, bold)
    t = strip_marks(text)
    try:
        w = f.getlength(t)
        if latin_scale != 1.0:
            lat = "".join(ch for ch in t if ord(ch) < 0x2E80)
            if lat:
                w += (latin_scale - 1.0) * f.getlength(lat)
    except Exception:
        w = len(t) * size_pt * scale
    return w / scale


def wrap_lines(text, size_pt, box_w_pt, bold=False, latin_scale=1.0):
    """Greedy CJK-aware wrap. Returns list of lines."""
    lines = []
    for para in re.split(r"[\n\v]", strip_marks(text)):
        if not para:
            lines.append("")
            continue
        cur = ""
        tokens = re.findall(r"[A-Za-z0-9\.\-_/%]+|\s+|.", para)
        for tok in tokens:
            trial = cur + tok
            if text_width_pt(trial, size_pt, bold, latin_scale) <= box_w_pt or not cur:
                cur = trial
            else:
                lines.append(cur.rstrip())
                cur = tok.lstrip()
        lines.append(cur)
    return lines


# A PowerPoint line-spacing multiple of 1.0 is the font's own single spacing, not 1em:
# measured 1.2em for Noto Sans CJK in LibreOffice, about 1.32em for Microsoft YaHei.
# Every height estimate multiplies by this so fits and QA match what actually renders.
LINE_PITCH = 1.2


def text_height_pt(text, size_pt, box_w_pt, bold=False, line_spacing=1.2, latin_scale=1.0):
    n = len(wrap_lines(text, size_pt, box_w_pt, bold, latin_scale))
    return n * size_pt * line_spacing * LINE_PITCH


# renderers add CJK/latin auto-spacing and use slightly different fonts than the measuring font
WIDTH_SAFETY = 0.92


# projection mode: text is read from across a room, so nothing auto-sized goes below 14pt
# and body copy starts at 18pt (set by build_deck from deck.meta.projection)
PROJECTION = {"on": False}


# One deck-wide type ladder. fit_size only tries these steps, so the size it measures is the size
# that ships (build_deck used to snap the result down afterwards, which turned a measured 10pt
# into 9pt even when 10.5pt fit, and checked orphans at a size that was then changed).
# build_deck replaces "steps" from style.type_scale; None means plain 1pt steps.
TYPE_SCALE = [9, 10.5, 12, 14, 16, 18, 20, 24, 28, 32, 36, 44, 54, 66, 80, 96, 120, 150, 180, 240, 330]
LADDER = {"steps": TYPE_SCALE}


def snap_size(size):
    """Largest ladder step <= size (tolerant of float noise like 10.4999)."""
    steps = LADDER["steps"]
    if not steps:
        return size
    return max([v for v in steps if v <= size + 0.05] or [size])


def _candidates(max_pt, min_pt):
    steps = LADDER["steps"]
    if not steps:
        out, v = [], max_pt
        while v >= min_pt:
            out.append(v)
            v -= 1
        return out, min_pt
    floor = snap_size(min_pt)
    return sorted({v for v in steps if floor - 0.01 <= v <= max_pt + 0.05}, reverse=True) or [floor], floor


def fit_size(text, box_w_in, box_h_in, max_pt, min_pt=10, bold=False, line_spacing=1.2,
             max_lines=None, orphan=True, latin_scale=1.0):
    """Largest font size (pt) so text fits in box (inches).

    orphan=True also rejects sizes whose last line holds only 1-2 CJK characters
    (a dangling "任" looks careless); falls back to the plain fit if nothing avoids it.
    """
    if PROJECTION["on"]:
        min_pt = max(min_pt, 14)
        max_pt = max(max_pt, min_pt)
    w_pt, h_pt = box_w_in * 72 * WIDTH_SAFETY, box_h_in * 72
    first_fit = None
    cands, floor = _candidates(max_pt, min_pt)
    for size in cands:
        lines = wrap_lines(text, size, w_pt, bold, latin_scale)
        ok = len(lines) * size * line_spacing * LINE_PITCH <= h_pt and (max_lines is None or len(lines) <= max_lines)
        if ok:
            if first_fit is None:
                first_fit = size
            last = lines[-1].strip() if lines else ""
            dangling = len(lines) > 1 and len(re.sub(r"[，。、；：！？,.;:!?」』）)\s]", "", last)) <= 2
            if not orphan or not dangling:
                return size
            if first_fit - size >= 8:  # do not shrink too far just for the orphan
                return first_fit
    return first_fit or floor


def n_lines(text, size_pt, box_w_in, bold=False, latin_scale=1.0):
    return len(wrap_lines(text, size_pt, box_w_in * 72 * WIDTH_SAFETY, bold, latin_scale))


DISPLAY_LATIN = 1.4  # width factor for the display role (Arial Black and its substitutes are wide)


def clen(s):
    """Length in reading units: one CJK character or one latin word counts as one."""
    s = strip_marks(s or "")
    return len(re.findall(r"[\u4e00-\u9fff]", s)) + len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'\.\-%]*", s))


# Icons ship as one atlas (assets/icons.png, alpha masks) plus a coordinate index, so the skill
# stays a small number of files; single icons are cut out on first use into a local cache.
ICON_CACHE = Path.home() / ".cache" / "luobo-ppt" / "icons"
_ATLAS = {}


def _atlas():
    if not _ATLAS:
        idx = load_json(ASSET_DIR / "icons.json")
        _ATLAS["cell"], _ATLAS["pos"] = idx["cell"], idx["icons"]
    return _ATLAS


def find_icon(name):
    a = _atlas()
    if name not in a["pos"]:
        return None
    p = ICON_CACHE / f"{name}.png"
    if not p.exists():
        from PIL import Image
        if "img" not in a:
            a["img"] = Image.open(ASSET_DIR / "icons.png").convert("L")
        x, y = a["pos"][name]
        c = a["cell"]
        mask = a["img"].crop((x, y, x + c, y + c))
        icon = Image.new("RGBA", (c, c), (0, 0, 0, 0))
        icon.putalpha(mask)
        p.parent.mkdir(parents=True, exist_ok=True)
        icon.save(p)
    return p


def list_icons():
    return sorted(_atlas()["pos"])


def svg_to_png(svg_path, png_path, width_px=1600):
    """Rasterise an SVG picture (PowerPoint can hold SVG without a PNG fallback, and python-pptx
    cannot place SVG). Tries cairosvg, then a headless Chromium via Playwright. True on success."""
    svg_path, png_path = Path(svg_path), Path(png_path)
    try:
        import cairosvg  # noqa
        cairosvg.svg2png(url=str(svg_path), write_to=str(png_path), output_width=width_px)
        return png_path.exists()
    except Exception:
        pass
    try:
        from playwright.sync_api import sync_playwright
        svg = svg_path.read_text(encoding="utf-8", errors="ignore")
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(device_scale_factor=4)
            pg.set_content("<html><body style='margin:0;background:transparent'><div id='w' style='width:420px;"
                           "display:inline-block;font-family:\"Noto Sans CJK SC\",\"Microsoft YaHei\",sans-serif'>"
                           + svg + "</div></body></html>")
            el = pg.query_selector("#w svg")
            el.screenshot(path=str(png_path), omit_background=True)
            b.close()
        return png_path.exists()
    except Exception:
        return False
