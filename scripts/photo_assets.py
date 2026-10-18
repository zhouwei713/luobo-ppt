#!/usr/bin/env python3
"""Real photos for picture slots, when there is no image model: from free stock libraries
or from the user's own files.

Usage:
  python photo_assets.py search WORK hero_03 "coffee shop interior" [--n 8] [--sources openverse,wikimedia]
  python photo_assets.py search WORK --queries queries.json        # {"hero_01": "...", "hero_05": "..."}
  python photo_assets.py pick   WORK hero_03 2                     # number from the candidate sheet
  python photo_assets.py local  WORK hero_03 path/to/photo.jpg      # the user's own picture
  python photo_assets.py local  WORK hero_03 photo.jpg --credit meta.json   # a library picture fetched elsewhere
  python photo_assets.py drop   WORK hero_03                       # back to an illustration on the next make_assets
  python photo_assets.py credits WORK                              # rewrite out/image_credits.md
  python photo_assets.py sources                                   # which libraries are usable now

search downloads small previews to WORK/photos/<id>/ and draws a numbered sheet.png to look at.
pick / local fetch the full picture, crop it to the slot's shape (asset "size" in plan.json),
round the corners like the style's cards, optionally pull it toward the palette (--tint 0.12),
save it as assets/<id>.png and record it in assets/manifest.json with its source and licence.
make_assets.py leaves such pictures alone (even with --force) unless named in --only.

Libraries and licences. Only pictures that may be used in a commercial deck, edited or not:
  openverse   no key. CC0, public domain mark, CC BY, CC BY-SA (BY and BY-SA need a credit line)
  wikimedia   no key. Same licence filter, read from each file's metadata
  pexels      key in env PEXELS_API_KEY (or config "photo": {"pexels_key_env": ...}). Pexels licence
  unsplash    key in env UNSPLASH_ACCESS_KEY. Unsplash licence
  pixabay     key in env PIXABAY_API_KEY. Pixabay content licence
Queries go out in English: write them that way (concrete nouns work, abstract ideas do not).
Exit code 2 when no library could be reached (offline or blocked network): fall back to the
user's files or the procedural pictures, and say so.
"""
import argparse
import io
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_json, save_json, load_style  # noqa: E402

UA = "luobo-ppt/1.0 (https://github.com/zhouwei713/luobo-ppt)"
OK_CC = {"cc0", "pdm", "by", "by-sa"}
NEEDS_CREDIT = {"by", "by-sa"}
LICENSE_NAMES = {"cc0": "CC0", "pdm": "Public Domain", "by": "CC BY", "by-sa": "CC BY-SA",
                 "pexels": "Pexels License", "unsplash": "Unsplash License", "pixabay": "Pixabay Content License"}


# ------------------------------------------------------------------ network
def fetch(url, headers=None, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def get_json(url, headers=None):
    # Openverse serves its browsable HTML page unless JSON is asked for
    return json.loads(fetch(url, {"Accept": "application/json", **(headers or {})}).decode("utf-8"))


def _key(cfg, name, env):
    p = (cfg or {}).get("photo", {})
    return os.environ.get(p.get(f"{name}_key_env", env)) or p.get(f"{name}_key")


def _strip_html(s):
    return re.sub(r"<[^>]+>", "", s or "").strip()


# ------------------------------------------------------------------ libraries
# each returns a list of candidates:
# {source, id, title, preview, full, width, height, author, author_url, page, license, license_url}
def s_openverse(q, n, cfg):
    url = "https://api.openverse.org/v1/images/?" + urllib.parse.urlencode(
        {"q": q, "page_size": min(20, n * 2), "license_type": "commercial,modification", "mature": "false"})
    out = []
    for r in get_json(url).get("results", []):
        lic = (r.get("license") or "").lower()
        if lic not in OK_CC:
            continue
        out.append({"source": "openverse", "id": r.get("id"), "title": r.get("title") or "",
                    "preview": r.get("thumbnail") or r.get("url"), "full": r.get("url"),
                    "width": r.get("width"), "height": r.get("height"), "author": r.get("creator") or "",
                    "author_url": r.get("creator_url") or "", "page": r.get("foreign_landing_url") or "",
                    "license": lic, "license_url": r.get("license_url") or "",
                    "via": r.get("provider") or ""})
    return out[:n]


def _wm_license(meta):
    short = (meta.get("LicenseShortName", {}).get("value") or "").lower()
    if "cc0" in short:
        return "cc0"
    if "public domain" in short or short == "pd":
        return "pdm"
    tokens = set(re.split(r"[\s\-_/.]+", short))
    if tokens & {"nc", "nd", "noncommercial", "noderivs"} or "non-commercial" in short:
        return None
    if short.startswith("cc by-sa") or short.startswith("cc-by-sa"):
        return "by-sa"
    if short.startswith("cc by") or short.startswith("cc-by"):
        return "by"
    return None


def s_wikimedia(q, n, cfg):
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "query", "format": "json", "generator": "search", "gsrsearch": f"{q} filetype:bitmap",
         "gsrnamespace": 6, "gsrlimit": min(30, n * 3), "prop": "imageinfo",
         "iiprop": "url|size|extmetadata", "iiurlwidth": 1600})
    pages = get_json(url).get("query", {}).get("pages", {})
    out = []
    for p in sorted(pages.values(), key=lambda p: p.get("index", 0)):
        info = (p.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        lic = _wm_license(meta)
        if not lic or not info.get("thumburl"):
            continue
        out.append({"source": "wikimedia", "id": str(p.get("pageid")), "title": p.get("title", "").replace("File:", ""),
                    "preview": info.get("thumburl"), "full": info.get("thumburl"),
                    "width": info.get("thumbwidth"), "height": info.get("thumbheight"),
                    "author": _strip_html(meta.get("Artist", {}).get("value")), "author_url": "",
                    "page": info.get("descriptionurl", ""), "license": lic,
                    "license_url": meta.get("LicenseUrl", {}).get("value", "")})
    return out[:n]


def s_pexels(q, n, cfg):
    key = _key(cfg, "pexels", "PEXELS_API_KEY")
    if not key:
        return None
    url = "https://api.pexels.com/v1/search?" + urllib.parse.urlencode({"query": q, "per_page": n})
    out = []
    for r in get_json(url, {"Authorization": key}).get("photos", []):
        src = r.get("src", {})
        out.append({"source": "pexels", "id": str(r.get("id")), "title": r.get("alt") or "",
                    "preview": src.get("medium"), "full": src.get("large2x") or src.get("original"),
                    "width": r.get("width"), "height": r.get("height"), "author": r.get("photographer", ""),
                    "author_url": r.get("photographer_url", ""), "page": r.get("url", ""),
                    "license": "pexels", "license_url": "https://www.pexels.com/license/"})
    return out


def s_unsplash(q, n, cfg):
    key = _key(cfg, "unsplash", "UNSPLASH_ACCESS_KEY")
    if not key:
        return None
    url = "https://api.unsplash.com/search/photos?" + urllib.parse.urlencode({"query": q, "per_page": n})
    out = []
    for r in get_json(url, {"Authorization": f"Client-ID {key}"}).get("results", []):
        u = r.get("urls", {})
        user = r.get("user", {})
        out.append({"source": "unsplash", "id": r.get("id"), "title": r.get("alt_description") or "",
                    "preview": u.get("small"), "full": u.get("regular"),
                    "width": r.get("width"), "height": r.get("height"), "author": user.get("name", ""),
                    "author_url": user.get("links", {}).get("html", ""), "page": r.get("links", {}).get("html", ""),
                    "license": "unsplash", "license_url": "https://unsplash.com/license",
                    "track": r.get("links", {}).get("download_location")})
    return out


def s_pixabay(q, n, cfg):
    key = _key(cfg, "pixabay", "PIXABAY_API_KEY")
    if not key:
        return None
    url = "https://pixabay.com/api/?" + urllib.parse.urlencode(
        {"key": key, "q": q, "image_type": "photo", "per_page": max(3, n), "safesearch": "true"})
    out = []
    for r in get_json(url).get("hits", []):
        out.append({"source": "pixabay", "id": str(r.get("id")), "title": r.get("tags", ""),
                    "preview": r.get("webformatURL"), "full": r.get("largeImageURL"),
                    "width": r.get("imageWidth"), "height": r.get("imageHeight"), "author": r.get("user", ""),
                    "author_url": "", "page": r.get("pageURL", ""),
                    "license": "pixabay", "license_url": "https://pixabay.com/service/license-summary/"})
    return out[:n]


LIBRARIES = {"pexels": s_pexels, "unsplash": s_unsplash, "pixabay": s_pixabay,
             "openverse": s_openverse, "wikimedia": s_wikimedia}


def usable_sources(cfg):
    keyed = {"pexels": _key(cfg, "pexels", "PEXELS_API_KEY"), "unsplash": _key(cfg, "unsplash", "UNSPLASH_ACCESS_KEY"),
             "pixabay": _key(cfg, "pixabay", "PIXABAY_API_KEY")}
    return [s for s in LIBRARIES if keyed.get(s, True)]


# ------------------------------------------------------------------ pictures
def slot_of(work, aid):
    plan = load_json(Path(work) / "plan.json")
    for a in plan.get("assets", []):
        if a["id"] == aid:
            return a
        for it in a.get("items", []):
            if it["id"] == aid:
                return dict(it, kind="hero", size=it.get("size") or a.get("size"))
    raise SystemExit(f"{aid} is not a picture slot in plan.json (see its assets list)")


def small_slot(work, aid):
    """True when the picture lands in a content page's top-right corner slot (layouts that call
    corner_hero): it is sized for a small transparent illustration, so a photo there looks cramped."""
    import inspect
    import layouts as L
    plan = load_json(Path(work) / "plan.json")
    slide = next((a.get("slide") for a in plan.get("assets", []) if a["id"] == aid), None)
    lay = next((s.get("layout") for s in plan.get("slides", []) if s.get("n") == slide), None)
    fn = L.LAYOUTS.get(lay)
    return bool(fn) and "corner_hero(ctx" in inspect.getsource(fn)


def fit_art(im, size, margin=0.04):
    """Brand artwork (a mascot, a sticker, a cut-out logo): the whole picture, never cropped,
    centred in the slot on a transparent canvas. No rounding, no shadow, no tint: a brand manual
    forbids changing its characters."""
    from PIL import Image
    im = im.convert("RGBA")
    bb = im.getbbox()
    if bb:
        im = im.crop(bb)
    W, H = int(size[0]), int(size[1])
    m = round(min(W, H) * margin)
    k = min((W - 2 * m) / im.width, (H - 2 * m) / im.height)
    im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    out.paste(im, ((W - im.width) // 2, (H - im.height) // 2), im)
    return out


def fit_photo(im, size, radius_frac=0.06, tint=0.0, tint_color=None, focus=(0.5, 0.42), margin=0.06, shadow=True):
    """Crop to the slot's aspect around `focus` (fractions; a little above centre suits most
    photos), scale to the slot, round the corners, optionally wash toward a palette colour."""
    from PIL import Image, ImageDraw
    im = im.convert("RGB")
    W, H = int(size[0]), int(size[1])
    ar, iar = W / H, im.width / im.height
    if iar > ar:
        cw, ch = round(im.height * ar), im.height
    else:
        cw, ch = im.width, round(im.width / ar)
    fx, fy = focus
    x0 = min(max(0, round(im.width * fx - cw / 2)), im.width - cw)
    y0 = min(max(0, round(im.height * fy - ch / 2)), im.height - ch)
    im = im.crop((x0, y0, x0 + cw, y0 + ch)).resize((W, H), Image.LANCZOS)
    if tint and tint_color:
        im = Image.blend(im, Image.new("RGB", im.size, tint_color), tint)
    # the photo sits inset in its slot on a soft shadow, so it reads as a placed card and keeps
    # clear of headers and edges the way the transparent illustrations do
    from PIL import ImageFilter
    m = round(min(W, H) * margin)
    pw, ph = W - 2 * m, H - 2 * m
    photo = im.resize((pw, ph), Image.LANCZOS)
    r = round(min(pw, ph) * radius_frac)
    mask = Image.new("L", (pw, ph), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, pw - 1, ph - 1), radius=r, fill=255)
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if shadow and m:
        sh = Image.new("L", (W, H), 0)
        dy = round(m * 0.35)
        ImageDraw.Draw(sh).rounded_rectangle((m, m + dy, m + pw - 1, m + ph - 1 + dy), radius=r, fill=70)
        sh = sh.filter(ImageFilter.GaussianBlur(m * 0.45))
        out.putalpha(sh)
        out = Image.composite(Image.new("RGBA", (W, H), (20, 30, 50, 255)), out, sh)
    photo = photo.convert("RGBA")
    photo.putalpha(mask)
    out.alpha_composite(photo, (m, m))
    return out


def _hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def place(work, aid, im, record, tint=0.0, focus=(0.5, 0.42)):
    work = Path(work)
    slot = slot_of(work, aid)
    size = slot.get("size") or [1400, 900]
    radius = 0.06
    tint_color = None
    if (work / "style.json").exists():
        st = load_style(work / "style.json")
        r_in = st.shape.get("radius", 0.16) or 0
        radius = 0.0 if r_in == 0 else 0.06
        tint_color = _hex_rgb(st.palette["primary"])
    src_w, src_h = record.pop("_src_size", None) or im.size
    out = fit_art(im, size) if record.get("method") == "brand" else fit_photo(im, size, radius, tint, tint_color, focus)
    adir = work / "assets"
    adir.mkdir(parents=True, exist_ok=True)
    path = adir / f"{aid}.png"
    out.save(path)
    man_path = adir / "manifest.json"
    man = load_json(man_path) if man_path.exists() else {"assets": []}
    man["assets"] = [m for m in man.get("assets", []) if m["id"] != aid]
    rec = {"id": aid, "kind": slot.get("kind", "hero"), "path": str(path), **record}
    man["assets"].append(rec)
    save_json(man, man_path)
    write_credits(work)
    # the slot is drawn at about half its pixel size on a 1080p screen; below that the photo looks soft
    ar = size[0] / size[1]
    crop_w = min(src_w, src_h * ar)
    if crop_w < size[0] * 0.5:
        print(f"NOTE {aid} 的原图只有 {src_w}x{src_h}，裁到图位后约 {int(crop_w)} 像素宽，放大后会发虚。"
              f"换一张至少 {int(size[0] * 0.5)} 像素宽的图")
    if small_slot(work, aid):
        print(f"NOTE {aid} 是内容页右上角的小装饰位，照片放这里偏挤。照片优先放封面、章节页、结尾页和图文页，"
              "这一页可以继续用插画，或在 plan.json 里把版式换成 media_text 这类大图版式")
    return path


def write_credits(work):
    work = Path(work)
    man_path = work / "assets" / "manifest.json"
    if not man_path.exists():
        return None
    rows = [m for m in load_json(man_path).get("assets", []) if m.get("method", "").startswith("photo:")]
    plan = load_json(work / "plan.json") if (work / "plan.json").exists() else {"assets": []}
    slide_of = {a["id"]: a.get("slide") for a in plan.get("assets", [])}
    out = work / "out" / "image_credits.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# 图片来源", "", "| 页 | 图片 | 作者 | 来源 | 协议 | 需要署名 |", "|---|---|---|---|---|---|"]
    for m in sorted(rows, key=lambda m: (slide_of.get(m["id"]) or 0, m["id"])):
        c = m.get("credit", {})
        lines.append(f"| {slide_of.get(m['id']) or ''} | {m['id']} | {c.get('author') or '未署名'} | "
                     f"[{where(c)}]({c.get('page')}) | {LICENSE_NAMES.get(c.get('license'), c.get('license'))} | "
                     f"{'是' if c.get('license') in NEEDS_CREDIT else '否'} |")
    lines += ["", "CC BY 和 CC BY-SA 的图要在页面或备注里写一行署名，格式如：图片：作者 / 来源 / 协议。"]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def where(c):
    """Where the picture lives: the original platform, and the search that found it."""
    via = (c.get("via") or "").strip()
    src = c.get("source") or ""
    return f"{via.capitalize()}（经 {src.capitalize()}）" if via and via.lower() != src.lower() else src.capitalize()


def credit_line(c):
    return f"图片：{c.get('author') or '佚名'} / {where(c)} / {LICENSE_NAMES.get(c.get('license'), c.get('license'))}"


# ------------------------------------------------------------------ commands
def cmd_search(a, cfg):
    work = Path(a.work)
    jobs = json.loads(Path(a.queries).read_text(encoding="utf-8")) if a.queries else {a.id: a.query}
    srcs = [s.strip() for s in (a.sources or ",".join(usable_sources(cfg))).split(",") if s.strip()]
    reached = False
    for aid, q in jobs.items():
        slot_of(work, aid)
        d = work / "photos" / aid
        d.mkdir(parents=True, exist_ok=True)
        cands, errors = [], []
        for s in srcs:
            if len(cands) >= a.n:
                break
            try:
                got = LIBRARIES[s](q, a.n - len(cands), cfg)
            except (urllib.error.URLError, OSError, ValueError) as e:
                errors.append(f"{s}: {getattr(e, 'reason', e)}")
                continue
            reached = True
            if got is None:
                continue
            cands += got
        kept = []
        for c in cands:
            try:
                raw = fetch(c["preview"])
                k = len(kept) + 1
                p = d / f"cand_{k:02d}.jpg"
                from PIL import Image
                Image.open(io.BytesIO(raw)).convert("RGB").save(p, quality=88)
                kept.append(dict(c, n=k, file=str(p)))
            except Exception as e:  # noqa: BLE001
                errors.append(f"preview {c.get('source')}:{c.get('id')}: {e}")
        save_json({"id": aid, "query": q, "candidates": kept}, d / "candidates.json")
        if kept:
            sheet(kept, d / "sheet.png")
            print(f"{aid}: {len(kept)} candidates for {q!r} -> {d / 'sheet.png'}")
        else:
            print(f"{aid}: nothing usable for {q!r}" + (f"  ({'; '.join(errors[:3])})" if errors else ""))
    if not reached:
        print("NO_NETWORK 图库都连不上（可能是网络受限）。改用用户自己的素材（local）或程序化插画，并告诉用户。")
        return 2
    return 0


def sheet(cands, out, tw=320):
    from PIL import Image, ImageDraw
    th = round(tw * 0.62)
    cols = min(4, len(cands))
    rows = (len(cands) + cols - 1) // cols
    sh = Image.new("RGB", (cols * (tw + 10) + 10, rows * (th + 34) + 10), (236, 238, 240))
    d = ImageDraw.Draw(sh)
    for i, c in enumerate(cands):
        x, y = 10 + (i % cols) * (tw + 10), 10 + (i // cols) * (th + 34)
        im = Image.open(c["file"]).convert("RGB")
        im.thumbnail((tw, th))
        sh.paste(im, (x + (tw - im.width) // 2, y + 24 + (th - im.height) // 2))
        d.text((x, y + 4), f"{c['n']}  {c['source']}  {LICENSE_NAMES.get(c['license'], c['license'])}", fill=(40, 40, 40))
    sh.save(out)


def cmd_pick(a, cfg):
    from PIL import Image
    work = Path(a.work)
    data = load_json(work / "photos" / a.id / "candidates.json")
    c = next((c for c in data["candidates"] if c["n"] == a.n), None)
    if not c:
        raise SystemExit(f"no candidate {a.n} for {a.id}")
    try:
        raw = fetch(c["full"], timeout=60)
        im = Image.open(io.BytesIO(raw))
    except Exception as e:  # noqa: BLE001
        print(f"full size failed ({e}); using the preview")
        im = Image.open(c["file"])
    if c.get("track"):  # Unsplash asks to count a download when a photo is used
        try:
            fetch(c["track"], {"Authorization": f"Client-ID {_key(cfg, 'unsplash', 'UNSPLASH_ACCESS_KEY')}"})
        except Exception:  # noqa: BLE001
            pass
    credit = {k: c.get(k) for k in ("source", "author", "author_url", "page", "license", "license_url", "title", "via")}
    rec = {"method": f"photo:{c['source']}", "credit": credit, "query": data.get("query")}
    if c.get("width") and c.get("height"):
        rec["_src_size"] = (int(c["width"]), int(c["height"]))
    path = place(work, a.id, im, rec, a.tint, tuple(a.focus))
    print(f"{a.id} <- {c['source']} #{a.n} ({LICENSE_NAMES.get(c['license'])}) -> {path}")
    if c["license"] in NEEDS_CREDIT:
        print(f"CREDIT 需要署名：{credit_line(credit)}")
    return 0


def cmd_local(a, cfg):
    """The user's own picture, or a library picture fetched some other way (a browser, say),
    with its source and licence in --credit meta.json."""
    from PIL import Image
    src = Path(a.file).expanduser()
    if not src.exists():
        raise SystemExit(f"no such file {src}")
    rec = {"method": "brand" if a.art else "user", "source_file": str(src)}
    if a.credit:
        c = json.loads(Path(a.credit).read_text(encoding="utf-8"))
        lic = (c.get("license") or "").lower()
        if lic not in OK_CC and lic not in ("pexels", "unsplash", "pixabay"):
            raise SystemExit(f"licence {lic!r} is not one that allows commercial use and changes; pick another picture")
        credit = {k: c.get(k) for k in ("source", "author", "author_url", "page", "license", "license_url", "title", "via")}
        rec = {"method": f"photo:{c.get('source') or 'web'}", "credit": credit, "source_file": str(src)}
        if c.get("width") and c.get("height"):
            rec["_src_size"] = (int(c["width"]), int(c["height"]))
    path = place(a.work, a.id, Image.open(src), rec, a.tint, tuple(a.focus))
    print(f"{a.id} <- {src.name} -> {path}")
    if rec.get("credit", {}).get("license") in NEEDS_CREDIT:
        print(f"CREDIT 需要署名：{credit_line(rec['credit'])}")
    return 0


def cmd_drop(a, cfg):
    work = Path(a.work)
    man_path = work / "assets" / "manifest.json"
    man = load_json(man_path) if man_path.exists() else {"assets": []}
    before = len(man.get("assets", []))
    man["assets"] = [m for m in man.get("assets", []) if m["id"] != a.id]
    save_json(man, man_path)
    for ext in (".png", ".jpg"):
        f = work / "assets" / f"{a.id}{ext}"
        if f.exists():
            f.unlink()
    write_credits(work)
    print(f"{a.id} cleared" if len(man["assets"]) < before else f"{a.id} was not placed")
    return 0


def main():
    from imagegen import find_config
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search")
    s.add_argument("work")
    s.add_argument("id", nargs="?")
    s.add_argument("query", nargs="?")
    s.add_argument("--queries")
    s.add_argument("--n", type=int, default=8)
    s.add_argument("--sources")
    for name in ("pick", "local"):
        p = sub.add_parser(name)
        p.add_argument("work")
        p.add_argument("id")
        p.add_argument("n" if name == "pick" else "file", type=int if name == "pick" else str)
        if name == "local":
            p.add_argument("--credit", help="json with source, author, page, license (and width, height of the original)")
            p.add_argument("--art", action="store_true",
                           help="brand artwork (mascot, sticker): placed whole, never cropped, no frame or shadow")
        p.add_argument("--tint", type=float, default=0.0, help="0..0.3, wash toward the primary colour")
        p.add_argument("--focus", type=float, nargs=2, default=[0.5, 0.42], metavar=("X", "Y"),
                       help="where to keep when cropping, as fractions of width and height")
    d = sub.add_parser("drop")
    d.add_argument("work")
    d.add_argument("id")
    c = sub.add_parser("credits")
    c.add_argument("work")
    sub.add_parser("sources")
    a = ap.parse_args()
    cfg = find_config(None, getattr(a, "work", None))
    if a.cmd == "sources":
        print("usable now:", ", ".join(usable_sources(cfg)), "(keyless ones still need network access)")
        return 0
    if a.cmd == "search":
        if not a.queries and not (a.id and a.query):
            ap.error("search needs ID QUERY or --queries file.json")
        return cmd_search(a, cfg)
    if a.cmd == "pick":
        return cmd_pick(a, cfg)
    if a.cmd == "local":
        return cmd_local(a, cfg)
    if a.cmd == "drop":
        return cmd_drop(a, cfg)
    out = write_credits(a.work)
    print(out or "no photos recorded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
