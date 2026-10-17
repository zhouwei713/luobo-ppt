#!/usr/bin/env python3
"""Step 4: produce every picture listed in plan.json.

Usage:
  python make_assets.py WORK_DIR [--config cfg.json] [--only hero_02,bg_content] [--force]
                                 [--procedural] [--dry-run] [--status] [--rewrite-prompts]

Heroes use the configured image model when one is available, else (or on failure) the
procedural generator. Backgrounds and decor are procedural unless config
"use_for": {"background": true}.

Prompt files: before any model call, the full final prompt of each AI picture is written to
WORK_DIR/prompts/<id>.md. If that file already exists it is used as-is, so to change a
picture edit its prompt file and rerun with --only <id> --force. --rewrite-prompts rebuilds
the files from plan.json.

Sheets: an asset of kind "sheet" lists several small illustrations ("items"). With a model
they are drawn together in one image (same style, one call) and sliced apart; without a model
each item is drawn procedurally. Each item is saved under its own id.

Results go to WORK_DIR/assets/ and WORK_DIR/assets/manifest.json records how each was made.
Pictures placed by photo_assets.py (stock photos, the user's own files) are kept, even with
--force, unless named in --only.
"""
import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_json, save_json, load_style  # noqa: E402
import fallback_art as FA  # noqa: E402
from imagegen import find_config, ImageGen, remove_background, trim_transparent  # noqa: E402


def _style_lines(style):
    P = style.palette
    ill = style.illustration or {}
    out = []
    if ill.get("style_prompt"):
        out.append("Visual style: " + ill["style_prompt"].strip().rstrip(".") + ".")
    out.append(f"Color palette: main #{P['primary']}, deep #{P['primary_dark']}, accent #{P['accent']}, "
               f"soft tints of #{P['tint']} and white.")
    return out, ill.get("negative", "text, letters, words, watermark, logo")


def compose_prompt(asset, style, kind):
    lines, neg = _style_lines(style)
    if kind == "sheet":
        items = asset.get("items", [])
        cols, rows = sheet_grid(len(items))
        parts = [f"A set of {len(items)} separate small illustrations drawn in one image, laid out as a grid of "
                 f"{cols} columns and {rows} rows of equal cells, each cell holding exactly one standalone subject "
                 f"centred in its cell, with wide plain white gaps between cells and nothing crossing cell borders."]
        for i, it in enumerate(items, 1):
            parts.append(f"Cell {i}: {it.get('prompt', '').strip().rstrip('.')}.")
        parts.append("All cells share one consistent visual style.")
        parts += lines
        parts.append("Plain pure white background everywhere, no frames, no numbers, no labels.")
        parts.append("Do not include: " + neg + ".")
        return " ".join(parts)
    parts = [asset.get("prompt", "").strip().rstrip(".") + "."] + lines
    if kind == "hero":
        parts.append("Composition: one clear subject group in the center, fully visible, generous empty margin on all sides.")
        if asset.get("transparent", True):
            parts.append("Isolated on a plain pure white background, no scenery, no floor, no cast shadow beyond the subject.")
    else:
        parts.append("Soft abstract presentation background, very low detail in the center so text stays readable, "
                     "decoration only near the edges, 16:9.")
    parts.append("Do not include: " + neg + ".")
    return " ".join(parts)


def sheet_grid(n):
    if n <= 2:
        return max(1, n), 1
    if n <= 4:
        return 2, 2
    return 3, (n + 2) // 3


def prompt_file(work, asset, style, kind, rewrite=False):
    """The prompt file is the source of truth once written."""
    pdir = Path(work) / "prompts"
    pdir.mkdir(exist_ok=True)
    path = pdir / f"{asset['id']}.md"
    if path.exists() and not rewrite:
        return path.read_text(encoding="utf-8").strip(), path
    text = compose_prompt(asset, style, kind)
    path.write_text(text + "\n", encoding="utf-8")
    return text, path


def procedural(asset, style, out, plan=None):
    k = asset["kind"]
    if k == "background":
        FA.background(style, 1920, 1080, asset.get("variant", "content"), seed=asset.get("seed", 7)).save(out, quality=92)
    elif k == "decor":
        shp = asset.get("shape")
        if shp == "leaf":
            FA.leaf(style.c(asset.get("color", "primary")), 200, flip=asset.get("flip", False)).save(out)
        elif shp == "brush":
            col = style.c(asset.get("color") or style.decor.get("brush_color", "accent"))
            FA.brush(col, 900, 260, seed=asset.get("seed", 3)).save(out)
        elif shp == "sparkle":
            FA.sparkle(style.c(asset.get("color", "accent")), 120).save(out)
    elif k == "hero":
        fb = dict(asset.get("fallback", {}))
        if not fb.get("icons") and plan:
            ps = next((p for p in plan.get("slides", []) if p.get("n") == asset.get("slide")), {})
            fb["icons"] = [i for i in ps.get("icons", []) if i][:3]
        w, h = asset.get("size", [1400, 1200])
        seed = asset.get("seed", asset.get("slide", 1) * 7 + 3)
        FA.hero(style, w, h, fb.get("scene", "tile"), fb.get("glyph"), fb.get("icons", []), seed=seed).save(out)


def finish_hero(img, native, transparent, w, h, out):
    if transparent and not native:
        img = remove_background(img)
    img = trim_transparent(img)
    img.thumbnail((w, h))
    img.save(out)


def ai_make(gen, asset, style, out, prompt):
    kind = asset["kind"]
    w, h = asset.get("size", [1920, 1080] if kind == "background" else [1400, 1200])
    transparent = kind == "hero" and asset.get("transparent", True)
    img, native = gen.generate(prompt, w, h, transparent=transparent, out=str(out))
    if kind == "hero":
        finish_hero(img, native, transparent, w, h, out)
    else:
        from PIL import ImageOps
        img = ImageOps.fit(img.convert("RGB"), (1920, 1080))
        img.save(out, quality=92)


def ai_sheet(gen, asset, adir, prompt):
    items = asset.get("items", [])
    cols, rows = sheet_grid(len(items))
    img, native = gen.generate(prompt, 1024 * cols, 1024 * rows, transparent=True,
                               out=str(adir / f"{asset['id']}.png"))
    img.save(adir / f"{asset['id']}.png")
    W, H = img.size
    cw, ch = W / cols, H / rows
    paths = {}
    for i, it in enumerate(items):
        c, r = i % cols, i // cols
        cell = img.crop((int(c * cw), int(r * ch), int((c + 1) * cw), int((r + 1) * ch)))
        w, h = it.get("size", [1400, 1200])
        out = adir / f"{it['id']}.png"
        finish_hero(cell, native, True, w, h, out)
        paths[it["id"]] = out
    return paths


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("--config")
    ap.add_argument("--only")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--procedural", action="store_true", help="ignore any configured model")
    ap.add_argument("--dry-run", action="store_true", help="write and print prompt files, generate nothing")
    ap.add_argument("--status", action="store_true", help="only report which image provider would be used")
    ap.add_argument("--rewrite-prompts", action="store_true", help="rebuild prompt files from plan.json")
    a = ap.parse_args()
    work = Path(a.work)
    cfg = find_config(a.config, work)
    gen = ImageGen(cfg)
    ok, why = gen.available()
    if a.procedural:
        ok, why = False, "procedural forced by --procedural"
    print(f"image provider: {'AI ' + why if ok else 'procedural fallback (' + why + ')'}   config: {cfg.get('_path')}")
    if a.status:
        plan_path = work / "plan.json"
        if plan_path.exists():
            slots = [x for x in load_json(plan_path).get("assets", []) if x["kind"] in ("hero", "sheet")]
            n = sum(len(x.get("items", [])) or 1 for x in slots)
            man_path = work / "assets" / "manifest.json"
            placed = [m for m in (load_json(man_path).get("assets", []) if man_path.exists() else [])
                      if m.get("method", "").startswith("photo:") or m.get("method") == "user"]
            print(f"picture slots: {n}, filled with photos or the user's pictures: {len(placed)}")
            if n and not ok and not placed:
                print("ASK 需要配图但没有生图模型：先问用户选哪种，接入生图模型、搜公开图库、用自己的素材，"
                      "还是用程序化插画（见 SKILL.md「配图来源」）")
        return
    style = load_style(work / "style.json")
    plan = load_json(work / "plan.json")
    adir = work / "assets"
    adir.mkdir(parents=True, exist_ok=True)
    man_path = adir / "manifest.json"
    manifest = load_json(man_path) if man_path.exists() else {"assets": []}
    done = {m["id"]: m for m in manifest.get("assets", [])}
    only = set(a.only.split(",")) if a.only else None

    def wanted(asset):
        ids = {asset["id"]} | {it["id"] for it in asset.get("items", [])}
        return not only or bool(ids & only)

    todo = []
    for asset in plan.get("assets", []):
        if not wanted(asset):
            continue
        ext = ".jpg" if asset["kind"] == "background" else ".png"
        out = adir / f"{asset['id']}{ext}"
        if asset["kind"] == "sheet":
            fresh = all((adir / f"{it['id']}.png").exists() and it["id"] in done for it in asset.get("items", []))
        else:
            fresh = out.exists() and asset["id"] in done
        if fresh and not a.force:
            continue
        # a photo or the user's own picture placed by photo_assets.py stays unless asked for by name
        kept = done.get(asset["id"], {}).get("method", "")
        if (kept.startswith("photo:") or kept == "user") and out.exists() and not (only and asset["id"] in only):
            continue
        todo.append((asset, out))

    def ai_bound(asset):
        k = asset["kind"]
        return ok and asset.get("method", "auto") != "procedural" and (
            (k in ("hero", "sheet") and gen.use_for("hero")) or
            (k == "background" and (gen.use_for("background") or asset.get("method") == "ai")))

    if a.dry_run:
        for asset, out in todo:
            if asset["kind"] in ("hero", "sheet") or (asset["kind"] == "background" and gen.use_for("background")):
                text, path = prompt_file(work, asset, style, asset["kind"], a.rewrite_prompts)
                print(f"--- {asset['id']}  ({path})\n{text}\n")
        return

    placed = {i for i, m in done.items() if m.get("method", "").startswith("photo:") or m.get("method") == "user"}
    placed -= only or set()

    def work_one(item):
        asset, out = item
        recs = []
        if asset["kind"] == "sheet" and placed & {it["id"] for it in asset.get("items", [])}:
            # some pictures of this sheet are photos: draw only the others, one by one
            asset = dict(asset, items=[it for it in asset["items"] if it["id"] not in placed])
            if not asset["items"]:
                return []
            asset["method"] = "procedural" if not ai_bound(asset) else asset.get("method", "auto")
        if asset["kind"] == "sheet":
            base = {"sheet": asset["id"], "kind": "hero"}
            if ai_bound(asset):
                try:
                    prompt, pth = prompt_file(work, asset, style, "sheet", a.rewrite_prompts)
                    paths = ai_sheet(gen, asset, adir, prompt)
                    return [dict(base, id=i, path=str(p), method=f"ai-sheet:{gen.provider}:{gen.model}",
                                 prompt_file=str(pth)) for i, p in paths.items()]
                except Exception as e:  # noqa: BLE001
                    err = str(e)[:300]
            else:
                err = None
            for it in asset.get("items", []):
                o = adir / f"{it['id']}.png"
                procedural(dict(it, kind="hero"), style, o, plan)
                r = dict(base, id=it["id"], path=str(o), method="procedural" + (" (after AI error)" if err else ""))
                if err:
                    r["error"] = err
                recs.append(r)
            return recs
        rec = {"id": asset["id"], "kind": asset["kind"], "path": str(out)}
        if ai_bound(asset):
            try:
                prompt, pth = prompt_file(work, asset, style, asset["kind"], a.rewrite_prompts)
                ai_make(gen, asset, style, out, prompt)
                rec.update(method=f"ai:{gen.provider}:{gen.model}", prompt_file=str(pth))
                return [rec]
            except Exception as e:  # noqa: BLE001
                rec["error"] = str(e)[:300]
        procedural(asset, style, out, plan)
        rec["method"] = "procedural" + (" (after AI error)" if rec.get("error") else "")
        return [rec]

    par = int(cfg.get("max_parallel", 3)) if ok else 1
    with ThreadPoolExecutor(max_workers=max(1, par)) as ex:
        results = [r for rs in ex.map(work_one, todo) for r in rs]
    for r in results:
        done[r["id"]] = r
        flag = f"  !! {r['error']}" if r.get("error") else ""
        print(f"  {r['id']:<14} {r['method']}{flag}")
    manifest = {"provider": why if ok else "procedural", "assets": list(done.values())}
    save_json(manifest, man_path)
    print(f"wrote {man_path}")


if __name__ == "__main__":
    main()
