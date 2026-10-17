"""Slide transitions and item builds, written straight into the slide XML.

python-pptx has no animation API, so this module writes the <p:transition> and <p:timing>
parts PowerPoint itself writes for "Fade" transitions and "Fade" / "Float In" / "Wipe"
entrance effects. Kept to a few calm effects on purpose.

Modes (deck meta "animation", or per slide "animation"):
  none        nothing moves
  transition  only a soft fade between slides (the default, and for report / reading decks)
  auto        fade between slides, and the items of a page come in one after another by
              themselves when the page opens (about a third of a second apart)
  click       fade between slides, and each item comes in on its own click: for talks,
              lessons and voice-over recordings where the speaker paces the page (the
              default for meta.scenario oral and talk)

What moves is decided by the layout: elements tagged with "step" (cards, rows, steps, stats...)
build in step order; titles, backgrounds, footers and pictures without a step are there from
the start. A page with fewer than two steps only gets the transition.
"""
from lxml import etree
from pptx.oxml.ns import qn

MODES = ("none", "transition", "auto", "click")
# when the deck does not say, the scenario decides: someone talking over the slides paces
# them by click; a report or a deck read on screen just turns pages
BY_SCENARIO = {"oral": "click", "talk": "click", "report": "transition", "reading": "transition"}
EFFECTS = ("rise", "fade", "wipe")
DUR = 500        # ms per effect
STAGGER = 320    # ms between items in auto mode
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"


def resolve(meta, slide):
    """(mode, effect) for one slide: the slide's own setting wins over the deck's."""
    def norm(v):
        if isinstance(v, dict):
            return v.get("mode"), v.get("effect")
        return v, None
    dm, de = norm(meta.get("animation"))
    sm, se = norm(slide.get("animation"))
    mode = sm or dm or BY_SCENARIO.get(meta.get("scenario"), "transition")
    if mode is True:
        mode = "auto"
    if mode is False:
        mode = "none"
    mode = mode if mode in MODES else "transition"
    effect = se or de or meta.get("animation_effect") or "rise"
    return mode, (effect if effect in EFFECTS else "rise")


def _el(tag, parent=None, **attrs):
    e = etree.SubElement(parent, qn(tag)) if parent is not None else etree.Element(qn(tag))
    for k, v in attrs.items():
        e.set(k, str(v))
    return e


class _Ids:
    def __init__(self):
        self.n = 0

    def __call__(self):
        self.n += 1
        return self.n


def _behaviour(parent, ids, spid, dur, attr=None, fill=None):
    cbhvr = _el("p:cBhvr", parent)
    ctn = _el("p:cTn", cbhvr, id=ids(), dur=dur)
    if fill:
        ctn.set("fill", fill)
    tgt = _el("p:tgtEl", cbhvr)
    _el("p:spTgt", tgt, spid=spid)
    if attr:
        names = _el("p:attrNameLst", cbhvr)
        _el("p:attrName", names).text = attr
    return cbhvr


def _effect(ids, spid, effect, node_type, delay=0):
    """One entrance effect on one shape, as PowerPoint writes it."""
    preset = {"fade": ("10", "0"), "rise": ("42", "0"), "wipe": ("22", "8")}[effect]
    par = _el("p:par")
    ctn = _el("p:cTn", par, id=ids(), presetID=preset[0], presetClass="entr", presetSubtype=preset[1],
              fill="hold", grpId="0", nodeType=node_type)
    st = _el("p:stCondLst", ctn)
    _el("p:cond", st, delay=delay)
    kids = _el("p:childTnLst", ctn)
    # become visible at the start of the effect
    s = _el("p:set", kids)
    cb = _behaviour(s, ids, spid, 1, "style.visibility", fill="hold")
    cb.find(qn("p:cTn")).append(_cond_list(0))
    to = _el("p:to", s)
    _el("p:strVal", to, val="visible")
    filt = {"fade": "fade", "rise": "fade", "wipe": "wipe(left)"}[effect]
    ae = _el("p:animEffect", kids, transition="in", filter=filt)
    _behaviour(ae, ids, spid, DUR)
    if effect == "rise":
        for attr, frm in (("ppt_x", "#ppt_x"), ("ppt_y", "#ppt_y+0.06")):
            an = _el("p:anim", kids, calcmode="lin", valueType="num")
            _behaviour(an, ids, spid, DUR, attr, fill="hold")
            tav = _el("p:tavLst", an)
            for tm, val in (("0", frm), ("100000", f"#{attr}")):
                t = _el("p:tav", tav, tm=tm)
                v = _el("p:val", t)
                _el("p:strVal", v, val=val)
    return par


def _cond_list(delay):
    st = etree.Element(qn("p:stCondLst"))
    _el("p:cond", st, delay=delay)
    return st


def _group_par(ids, delay_cond, effects):
    """<p:par> holding one inner <p:par> of simultaneous effects."""
    outer = _el("p:par")
    octn = _el("p:cTn", outer, id=ids(), fill="hold")
    ost = _el("p:stCondLst", octn)
    for c in delay_cond:
        ost.append(c)
    okids = _el("p:childTnLst", octn)
    inner = _el("p:par", okids)
    ictn = _el("p:cTn", inner, id=ids(), fill="hold")
    ictn.append(_cond_list(0))
    ikids = _el("p:childTnLst", ictn)
    for e in effects:
        ikids.append(e)
    return outer


def _anchor(sld):
    # lxml elements without children are falsy, so test for None explicitly
    for tag in ("p:clrMapOvr", "p:cSld"):
        e = sld.find(qn(tag))
        if e is not None:
            return e
    raise ValueError("slide has no cSld")


def set_transition(slide, on=True):
    sld = slide._element
    for old in sld.findall(qn("p:transition")):
        sld.remove(old)
    if not on:
        return
    tr = etree.Element(qn("p:transition"))
    tr.set("spd", "med")
    _el("p:fade", tr)
    # schema order: cSld, clrMapOvr, transition, timing, extLst
    _anchor(sld).addnext(tr)


def set_builds(slide, groups, mode, effect="rise"):
    """groups: list (in build order) of lists of shape ids that come in together.
    Returns the number of builds written (0 when the page stays still)."""
    sld = slide._element
    for old in sld.findall(qn("p:timing")):
        sld.remove(old)
    groups = [g for g in groups if g]
    if mode not in ("auto", "click") or len(groups) < 2:
        return 0
    ids = _Ids()
    timing = etree.Element(qn("p:timing"))
    tnlst = _el("p:tnLst", timing)
    root = _el("p:par", tnlst)
    rctn = _el("p:cTn", root, id=ids(), dur="indefinite", restart="never", nodeType="tmRoot")
    rkids = _el("p:childTnLst", rctn)
    seq = _el("p:seq", rkids, concurrent="1", nextAc="seek")
    sctn = _el("p:cTn", seq, id=ids(), dur="indefinite", nodeType="mainSeq")
    skids = _el("p:childTnLst", sctn)
    if mode == "click":
        for g in groups:
            effs = [_effect(ids, spid, effect, "clickEffect" if k == 0 else "withEffect")
                    for k, spid in enumerate(g)]
            c = etree.Element(qn("p:cond"))
            c.set("delay", "indefinite")
            skids.append(_group_par(ids, [c], effs))
    else:
        effs = []
        for gi, g in enumerate(groups):
            for k, spid in enumerate(g):
                first = gi == 0 and k == 0
                effs.append(_effect(ids, spid, effect, "afterEffect" if first else "withEffect",
                                    delay=gi * STAGGER))
        c1 = etree.Element(qn("p:cond"))
        c1.set("delay", "indefinite")
        c2 = etree.Element(qn("p:cond"))
        c2.set("evt", "onBegin")
        c2.set("delay", "0")
        _el("p:tn", c2, val="2")
        skids.append(_group_par(ids, [c1, c2], effs))
    prev = _el("p:prevCondLst", seq)
    pc = _el("p:cond", prev, evt="onPrev", delay="0")
    _el("p:sldTgt", _el("p:tgtEl", pc))
    nxt = _el("p:nextCondLst", seq)
    nc = _el("p:cond", nxt, evt="onNext", delay="0")
    _el("p:sldTgt", _el("p:tgtEl", nc))
    # build list: every animated autoshape with a text body
    shapes = {sh.shape_id: sh for sh in slide.shapes}
    bld = _el("p:bldLst", timing)
    seen = set()
    for g in groups:
        for spid in g:
            sh = shapes.get(spid)
            if spid in seen or sh is None or sh._element.tag != qn("p:sp"):
                continue
            seen.add(spid)
            b = _el("p:bldP", bld, spid=spid, grpId="0")
            if sh._element.find(qn("p:txBody")) is not None:
                b.set("animBg", "1")
    if not len(bld):
        timing.remove(bld)
    tr = sld.find(qn("p:transition"))
    (tr if tr is not None else _anchor(sld)).addnext(timing)
    return len(groups)


def animated_ids(slide):
    """Shape ids a slide's timing refers to (for checks)."""
    t = slide._element.find(qn("p:timing"))
    if t is None:
        return set()
    return {int(e.get("spid")) for e in t.iter(qn("p:spTgt"))}


def apply(slide, rendered, mode, effect="rise"):
    """rendered: [(element, [shape ids])] in drawing order. Writes transition and builds."""
    set_transition(slide, mode != "none")
    steps = {}
    for e, spids in rendered:
        st = e.get("step")
        if st is None or e.get("role") in ("background", "chrome", "decor"):
            continue
        steps.setdefault(st, []).extend(spids)
    groups = [steps[k] for k in sorted(steps)]
    return set_builds(slide, groups, mode, effect)
