"""Brand kit: a company's VI manual turned into rules the deck follows.

A VI manual fixes exact colours, fonts, the logo and how it may be used, signature graphics and
the mascot or stickers. Taking colours off a reference image gets them wrong (the swatches are a
small part of a white page), so a brand deck starts from the manual instead:

  pages  MANUAL.pdf|IMG... WORK      manual pages as images in WORK/brand/pages (a single very long
                                     page is cut into screen-sized parts), the text layer in
                                     WORK/brand/manual.txt and every #RRGGBB / RGB(...) found in it,
                                     plus WORK/brand.draft.json to fill in
  crop   WORK PAGE.png X0 Y0 X1 Y1 NAME [--clear] [--trim-bottom F]
                                     cut a logo, mascot or sticker out of a page (pixels, or 0..1
                                     fractions) into WORK/brand/NAME.png; --clear turns the white
                                     around it transparent
  plate  WORK LOGO NAME              the logo on a white rounded plate (for dark backgrounds when the
                                     manual has no reversed logo)
  check  WORK                        brand.json: required fields, files, readable text colour, and
                                     each declared hex looked up in the manual pages (a misread
                                     F97316 / F97361 shows up here)
  apply  WORK [--base PRESET]        writes WORK/style.json from brand.json (palette from the brand
                                     colours only, fonts, signature elements, no gradients / blobs)
  card   WORK                        WORK/brand/brand_card.png for the user to confirm

brand.json (see references/brand.md for every field):
  {"name": "...", "colors": [{"name": "...", "hex": "14306B", "role": "primary"}, ...],
   "allow": ["FFFFFF"], "fonts": {...}, "logos": [{"file": "brand/logo_h.png", "kind": "horizontal",
   "on": "light"}], "logo": {"clear_space": 0.25, "content": "top-right", "height": 0.5},
   "signature": {"title_bar": "accent", "outline": false}, "art": ["brand/ip_1.png"],
   "forbid": {"gradients": true, "shadows": true}, "rules": ["..."]}
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (load_json, save_json, hex_clean, contrast, rel_lum, color_dist, brand_allowed,  # noqa: E402
                    get_font, SKILL_DIR, style_file)

ROLES = ("primary", "secondary", "accent", "extra", "text", "background", "neutral")
HEX_RE = re.compile(r"#\s*([0-9A-Fa-f]{6})\b")
RGB_RE = re.compile(r"RGB\D{0,4}(\d{1,3})\s*[,/ ]\s*(\d{1,3})\s*[,/ ]\s*(\d{1,3})", re.I)


# ------------------------------------------------------------------ pages
def cmd_pages(a):
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    work = Path(a.work)
    out = work / "brand" / "pages"
    out.mkdir(parents=True, exist_ok=True)
    text = []
    n = 0
    for src in a.src:
        src = Path(src)
        if src.suffix.lower() == ".pdf":
            tmp = work / "brand" / "_render"
            tmp.mkdir(exist_ok=True)
            subprocess.run(["pdftoppm", "-r", str(a.dpi), "-png", str(src), str(tmp / "p")], check=True)
            imgs = sorted(tmp.glob("p-*.png"))
            try:
                text.append(subprocess.run(["pdftotext", "-layout", str(src), "-"], capture_output=True,
                                           text=True).stdout)
            except FileNotFoundError:
                pass
        else:
            imgs = [src]
        for p in imgs:
            for part in split_pages(Image.open(p).convert("RGB")):
                n += 1
                part.save(out / f"p{n:03d}.png")
        if src.suffix.lower() == ".pdf":
            shutil.rmtree(work / "brand" / "_render", ignore_errors=True)
    txt = "\n".join(text)
    (work / "brand" / "manual.txt").write_text(txt, encoding="utf-8")
    found = list(dict.fromkeys(m.upper() for m in HEX_RE.findall(txt)))
    for r, g, b in RGB_RE.findall(txt):
        if max(int(r), int(g), int(b)) <= 255:
            found.append("%02X%02X%02X" % (int(r), int(g), int(b)))
    found = list(dict.fromkeys(found))
    draft = {"name": "", "source": [str(s) for s in a.src],
             "colors": [{"name": "", "hex": h, "role": ""} for h in found],
             "allow": ["FFFFFF"], "tints": False,
             "fonts": {"heading_ea": "", "body_ea": "", "heading_latin": "", "body_latin": ""},
             "logos": [], "logo": {"clear_space": 0.25, "height": 0.5, "content": "top-right",
                                   "cover": "auto", "closing": "auto"},
             "signature": {"title_bar": None, "outline": False, "radius": 0.12},
             "art": [], "forbid": {"gradients": True, "shadows": True}, "rules": []}
    dst = work / "brand.draft.json"
    save_json(draft, dst)
    print(f"pages: {n} -> {out}")
    print(f"text layer: {len(txt.strip())} characters" + ("" if txt.strip() else
          "（这份手册是整页图片，色值、字体要看图读出来）"))
    print("colours in the text: " + (", ".join("#" + h for h in found) if found else "none"))
    print(f"wrote {dst}")
    return 0


def split_pages(im):
    """A manual exported as one endless image: drop the grey backdrop at the sides and cut at the
    gaps between the pages; parts still very tall are cut about as tall as they are wide.
    The page boxes are found on a small copy (a 150 dpi manual is a hundred megapixels)."""
    import numpy as np
    from PIL import Image
    f = max(1, int(im.width / 800))
    sm = np.asarray(im.resize((im.width // f, im.height // f))).astype(np.int16)
    diff = np.abs(sm - sm[1, 1]).max(axis=2) > 10
    cols = np.where(diff.mean(axis=0) > 0.2)[0]  # page columns differ from the backdrop on most rows
    c0, c1 = 0, diff.shape[1] - 1
    if len(cols):
        # the widest run of such columns is the page (a stray edge column is not)
        runs, s0 = [], cols[0]
        for i in range(1, len(cols) + 1):
            if i == len(cols) or cols[i] != cols[i - 1] + 1:
                runs.append((s0, cols[i - 1]))
                if i < len(cols):
                    s0 = cols[i]
        c0, c1 = max(runs, key=lambda r: r[1] - r[0])
    filled = diff[:, c0:c1 + 1].mean(axis=1) > 0.003
    h = len(filled)
    segs, start = [], None
    for y in range(h):
        if filled[y] and start is None:
            start = y
        if not filled[y] and start is not None:
            if y - start > 5:
                segs.append((start, y))
            start = None
    if start is not None and h - start > 5:
        segs.append((start, h))
    if not segs:
        segs = [(0, h)]
    X0, X1 = max(0, (c0 - 1) * f), min(im.width, (c1 + 2) * f)
    W = X1 - X0
    out = []
    for y0, y1 in segs:
        Y0, Y1 = y0 * f, min(im.height, y1 * f)
        step = int(W * 0.9) if (Y1 - Y0) > W * 1.6 else (Y1 - Y0)
        for y in range(Y0, Y1, step):
            out.append(im.crop((X0, y, X1, min(Y1, y + step))))
    return out


# ------------------------------------------------------------------ crops
def clear_white(im, thr=235):
    """White (and near white) touching the border becomes transparent; inner whites stay."""
    im = im.convert("RGBA")
    w, h = im.size
    px = im.load()
    seen = bytearray(w * h)
    stack = [(x, 0) for x in range(w)] + [(x, h - 1) for x in range(w)] + \
            [(0, y) for y in range(h)] + [(w - 1, y) for y in range(h)]
    while stack:
        x, y = stack.pop()
        if not (0 <= x < w and 0 <= y < h) or seen[y * w + x]:
            continue
        seen[y * w + x] = 1
        r, g, b, al = px[x, y]
        if r > thr and g > thr and b > thr:
            px[x, y] = (r, g, b, 0)
            stack += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
    bb = im.getbbox()
    return im.crop(bb) if bb else im


def cmd_crop(a):
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    work = Path(a.work)
    im = Image.open(a.page)
    box = [float(v) for v in (a.x0, a.y0, a.x1, a.y1)]
    if all(v <= 1.0 for v in box):
        box = [box[0] * im.width, box[1] * im.height, box[2] * im.width, box[3] * im.height]
    im = im.crop(tuple(int(round(v)) for v in box))
    if a.trim_bottom:
        im = im.crop((0, 0, im.width, int(im.height * (1 - a.trim_bottom))))
    if a.clear:
        im = clear_white(im)
    out = work / "brand" / f"{a.name}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    print(f"{out}  {im.width}x{im.height}")
    if min(im.size) < 160:
        print("NOTE 截出来不到 160 像素，放大会糊；手册能导出更高清的图就换高清的，或者把 pages 的 --dpi 调高")
    return 0


def cmd_plate(a):
    from PIL import Image, ImageDraw
    work = Path(a.work)
    lg = Image.open(work / a.logo if not Path(a.logo).is_absolute() else a.logo).convert("RGBA")
    w, h = lg.size
    pad = int(max(w, h) * 0.16)
    W, H = w + 2 * pad, h + 2 * pad
    plate = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(plate).rounded_rectangle((0, 0, W - 1, H - 1), radius=int(min(W, H) * 0.08), fill=(255, 255, 255, 255))
    plate.paste(lg, (pad, pad), lg)
    out = work / "brand" / f"{a.name}.png"
    plate.save(out)
    print(out)
    return 0


# ------------------------------------------------------------------ check
def by_role(brand, role):
    return [hex_clean(c["hex"]) for c in brand.get("colors", []) if c.get("role") == role and c.get("hex")]


def find_in_pages(work, hexes):
    """Share of each colour among the pixels of the manual pages (0 = not printed anywhere)."""
    from PIL import Image
    pages = sorted((Path(work) / "brand" / "pages").glob("p*.png"))
    if not pages:
        return {}
    counts = {h: 0 for h in hexes}
    total = 0
    tgt = {h: tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) for h in hexes}
    for p in pages:
        im = Image.open(p).convert("RGB")
        im.thumbnail((500, 500))
        for cnt, col in im.getcolors(500 * 500):
            total += cnt
            for h, t in tgt.items():
                if max(abs(col[i] - t[i]) for i in range(3)) <= 6:
                    counts[h] += cnt
    return {h: counts[h] / max(1, total) for h in hexes}


def cmd_check(a):
    work = Path(a.work)
    path = work / "brand.json"
    if not path.exists():
        print(f"ERROR 没有 {path}，先把 brand.draft.json 填好另存为 brand.json")
        return 1
    b = load_json(path)
    errs, warns = [], []
    cols = b.get("colors", [])
    for c in cols:
        h = str(c.get("hex", ""))
        if not re.fullmatch(r"#?[0-9A-Fa-f]{6}", h):
            errs.append(f"色值格式不对：{c}")
        if c.get("role") not in ROLES:
            errs.append(f"{c.get('name') or h} 的 role 要从 {', '.join(ROLES)} 里选")
    if not by_role(b, "primary"):
        errs.append("没有 role 为 primary 的主色")
    allowed = brand_allowed(b) if not errs else []
    text = (by_role(b, "text") or [None])[0]
    page = (b.get("page") or ("FFFFFF" if "FFFFFF" in allowed else (by_role(b, "background") or ["FFFFFF"])[0]))
    if not errs:
        if not text:
            dark = [h for h in allowed if contrast(h, page) >= 7]
            if dark:
                warns.append(f"没写正文色（role: text），会用 #{min(dark, key=rel_lum)}")
            else:
                errs.append("品牌色里没有能当正文的深色（和页面底色对比度 7 以上），手册里通常有一个深灰或墨黑，补上")
        elif contrast(text, page) < 4.5:
            errs.append(f"正文色 #{text} 在页面底色 #{page} 上对比度只有 {contrast(text, page):.1f}，读不清")
    fonts = b.get("fonts", {})
    if not fonts.get("heading_ea") or not fonts.get("body_ea"):
        warns.append("fonts 里没写中文标题、正文字体，会用微软雅黑")
    for lg in b.get("logos", []):
        f = work / lg.get("file", "")
        if not f.exists():
            errs.append(f"logo 文件不存在：{lg.get('file')}")
        elif lg.get("on") not in ("light", "dark", "any"):
            errs.append(f"logo {lg.get('file')} 的 on 要写 light、dark 或 any（放在浅底还是深底上）")
    if not b.get("logos"):
        warns.append("没有 logo，成品不会放标志")
    for a in b.get("art", []):
        f = a.get("file", "") if isinstance(a, dict) else a
        if not (work / f).exists():
            errs.append(f"art 文件不存在：{f}")
    share = find_in_pages(work, [hex_clean(c["hex"]) for c in cols if c.get("hex")]) if not errs else {}
    for h, s in share.items():
        if s == 0:
            warns.append(f"#{h} 在手册页面上一个像素都找不到，核对一下是不是读错了（比如 F97316 读成 F97361）")
    for e in errs:
        print("ERROR", e)
    for w in warns:
        print("WARN", w)
    if share:
        print("手册页面上的占比：" + "，".join(f"#{h} {s * 100:.2f}%" for h, s in share.items()))
    print("OK" if not errs else f"{len(errs)} 个错误")
    return 1 if errs else 0


# ------------------------------------------------------------------ apply
def build_style(work, b, base=None):
    """style.json for a brand: the palette only uses brand colours."""
    work = Path(work)
    allowed = brand_allowed(b)
    primary = by_role(b, "primary")[0]
    secondary = (by_role(b, "secondary") or [None])[0]
    accent = (by_role(b, "accent") or [secondary or primary])[0]
    page = hex_clean(b.get("page") or ("FFFFFF" if "FFFFFF" in allowed else (by_role(b, "background") or ["FFFFFF"])[0]))
    text = (by_role(b, "text") or [None])[0] or min([h for h in allowed if contrast(h, page) >= 7] or ["111111"], key=rel_lum)
    lights = [h for h in by_role(b, "background") + by_role(b, "neutral") if rel_lum(h) > 0.7 and h != page]
    tint = lights[0] if lights else page
    if tint == page and rel_lum(accent) > 0.6:
        # no light grey in the manual but a light accent (a pop yellow): emphasis cards and
        # labels sit on the accent with dark text, the way such manuals do it
        tint = accent
    sig = b.get("signature", {})
    outline = bool(sig.get("outline"))
    forbid = b.get("forbid", {})
    on_primary = "FFFFFF" if ("FFFFFF" in allowed and contrast("FFFFFF", primary) >= 3) else text
    # cards: on a white page a flat white card disappears, so a light brand grey carries them
    # (most manuals lay their own pages out this way); outlined cards stay white
    surface = "FFFFFF" if "FFFFFF" in allowed else page
    if surface == page and tint != page and not outline:
        surface = tint
    # dark grounds (closing page, dark bands) need white to read; a light primary such as an
    # orange hands that job to the darkest brand colour
    dark = primary
    if not ("FFFFFF" in allowed and contrast("FFFFFF", primary) >= 4.5):
        darks = [h for h in allowed if "FFFFFF" in allowed and contrast("FFFFFF", h) >= 4.5 and h != text]
        dark = min(darks, key=rel_lum) if darks else primary
    pal = {"primary": primary, "primary_dark": dark, "accent": accent, "bg_top": page, "bg_bottom": page,
           "surface": surface, "tint": tint, "text": text, "muted": text,
           "on_primary": on_primary, "line": text if outline else tint,
           "on_dark": "FFFFFF" if ("FFFFFF" in allowed and contrast("FFFFFF", dark) >= 4.5) else text}
    style = load_json(style_file(base)) if base else {}
    fonts = {"heading_ea": "Microsoft YaHei", "body_ea": "Microsoft YaHei", "heading_latin": "Arial",
             "body_latin": "Arial", "display_latin": "Arial Black"}
    fonts.update({k: v for k, v in b.get("fonts", {}).items() if v and k in fonts})
    if "display_latin" not in b.get("fonts", {}):
        fonts["display_latin"] = fonts["heading_latin"]
    depth = "outline" if outline else ("flat" if forbid.get("shadows", True) else "whisper")
    style.update({
        "name": f"brand-{b.get('name', 'brand')}", "label": f"{b.get('name', '')} VI",
        "palette": pal, "fonts": fonts,
        "shape": {"radius": sig.get("radius", 0.12), "shadow": not forbid.get("shadows", True), "card_alpha": 1.0,
                  "depth": depth, "outline_w": sig.get("outline_w", 2.25), "hard_shadow": sig.get("hard_shadow", 0.07)},
        "decor": {"header": True, "leaf": False, "brush": False, "sparkles": False,
                  "title_mark": "bar" if sig.get("title_bar") else sig.get("title_mark", False),
                  "title_bar_color": sig.get("title_bar") or "accent",
                  "closing_dark": b.get("closing_dark", True), "bullet": sig.get("bullet", "number"),
                  "number_style": sig.get("number_style", "badge" if outline else "plain"),
                  "emphasis": "color", "chrome": "standard"},
        "background": {"decor": [], "cover_decor": [], "closing_decor": [], "flat": True},
        "illustration": {"style_prompt": b.get("imagery_prompt", ""), "negative": "text, letters, words, logo, watermark",
                         "fallback_look": "flat"},
        "emphasis_color": "accent" if contrast(accent, page) >= 3 else "primary",
        "rules": b.get("rules", []), "forbid": {},
    })
    # the brand travels inside style.json with absolute paths, so later steps need nothing else
    bb = json.loads(json.dumps(b))
    for lg in bb.get("logos", []):
        lg["file"] = str((work / lg["file"]).resolve())
    bb["art"] = [dict(a, file=str((work / a["file"]).resolve())) if isinstance(a, dict) else str((work / a).resolve())
                 for a in bb.get("art", [])]
    style["brand"] = bb
    return style


def cmd_apply(a):
    work = Path(a.work)
    b = load_json(work / "brand.json")
    if cmd_check(a):
        print("brand.json 还有错误，先改好再 apply")
        return 1
    st = build_style(work, b, a.base)
    save_json(st, work / "style.json")
    p = st["palette"]
    print(f"wrote {work / 'style.json'}  主色 #{p['primary']} 强调 #{p['accent']} 正文 #{p['text']} 底色 #{p['bg_top']}")
    return cmd_card(a)


# ------------------------------------------------------------------ card
def cmd_card(a):
    from PIL import Image, ImageDraw
    work = Path(a.work)
    b = load_json(work / "brand.json")
    W, H = 1600, 1000
    im = Image.new("RGB", (W, H), "#FFFFFF")
    d = ImageDraw.Draw(im)
    fb, f, fs = get_font(34, True), get_font(22), get_font(18)
    d.text((48, 36), f"{b.get('name', '')} 品牌规范确认", font=fb, fill="#111111")
    d.text((48, 86), "颜色、字体、logo 和规则都从手册来。不对的地方改 brand.json 再 apply", font=fs, fill="#555555")
    x, y = 48, 140
    for c in b.get("colors", []):
        h = hex_clean(c["hex"])
        d.rounded_rectangle((x, y, x + 160, y + 110), radius=12, fill="#" + h, outline="#DDDDDD")
        d.text((x, y + 118), c.get("name") or c.get("role", ""), font=f, fill="#222222")
        d.text((x, y + 146), f"#{h}  {c.get('role', '')}", font=fs, fill="#666666")
        x += 186
        if x > W - 200:
            x, y = 48, y + 200
    y += 210
    fo = b.get("fonts", {})
    d.text((48, y), "字体  标题 " + (fo.get("heading_ea") or "—") + " / " + (fo.get("heading_latin") or "—") +
           "   正文 " + (fo.get("body_ea") or "—") + " / " + (fo.get("body_latin") or "—"), font=f, fill="#222222")
    y += 50
    sig = b.get("signature", {})
    marks = []
    if sig.get("title_bar"):
        marks.append(f"标题竖条（{sig['title_bar']}）")
    if sig.get("outline"):
        marks.append("粗描边加硬投影")
    fb_ = b.get("forbid", {})
    if fb_.get("gradients", True):
        marks.append("不用渐变")
    if fb_.get("shadows", True) and not sig.get("outline"):
        marks.append("不用阴影")
    lg = b.get("logo", {})
    marks.append(f"logo 安全空间 {lg.get('clear_space', 0.25)} 倍高，内容页 {lg.get('content', 'top-right')}")
    d.text((48, y), "版式  " + "，".join(marks), font=f, fill="#222222")
    y += 60
    # logos on light and dark
    x = 48
    dark_bg = "#" + by_role(b, "primary")[0] if by_role(b, "primary") else "#111111"
    for bg in ("#FFFFFF", dark_bg):
        d.rounded_rectangle((x, y, x + 700, y + 220), radius=14, fill=bg, outline="#DDDDDD")
        xx = x + 24
        for l in b.get("logos", []):
            fpath = work / l["file"]
            if not fpath.exists():
                continue
            on_dark = bg != "#FFFFFF"
            if (l.get("on") == "dark") != on_dark and l.get("on") != "any":
                continue
            lo = Image.open(fpath).convert("RGBA")
            lo.thumbnail((300, 170))
            im.paste(lo, (xx, y + 25), lo)
            xx += lo.width + 30
        d.text((x + 16, y + 190), "浅底用" if bg == "#FFFFFF" else "深底用", font=fs, fill="#888888" if bg == "#FFFFFF" else "#DDDDDD")
        x += 740
    y += 250
    x = 48
    for a in b.get("art", [])[:10]:
        p = work / (a.get("file", "") if isinstance(a, dict) else a)
        if p.exists():
            lo = Image.open(p).convert("RGBA")
            lo.thumbnail((130, 130))
            im.paste(lo, (x, y), lo)
            x += 145
    out = work / "brand" / "brand_card.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    print(f"card: {out}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pages")
    p.add_argument("src", nargs="+")
    p.add_argument("work")
    p.add_argument("--dpi", type=int, default=110)
    p = sub.add_parser("crop")
    for k in ("work", "page", "x0", "y0", "x1", "y1", "name"):
        p.add_argument(k)
    p.add_argument("--clear", action="store_true")
    p.add_argument("--trim-bottom", type=float, default=0.0)
    p = sub.add_parser("plate")
    for k in ("work", "logo", "name"):
        p.add_argument(k)
    for name in ("check", "apply", "card"):
        p = sub.add_parser(name)
        p.add_argument("work")
        if name == "apply":
            p.add_argument("--base", help="a preset to start from (fonts and layout habits), brand values win")
    a = ap.parse_args()
    return {"pages": cmd_pages, "crop": cmd_crop, "plate": cmd_plate, "check": cmd_check,
            "apply": cmd_apply, "card": cmd_card}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
