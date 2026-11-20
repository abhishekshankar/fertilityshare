"""typeset.py -- how the card's text is SET (never what it says).

Every function here changes only spacing, breaking and glyph form; `plain()` of the output equals `plain()` of the
input except for the typographic substitutions listed in `SUBSTITUTIONS` (minus sign, en dash in ranges, superscripts),
which tests/test_render_typeset.py asserts.

    tie(s)                  no-break spaces: 40 g, PMID 40540267, N = 21, 95% CI, p > 0.05, 0.09 to 0.11, 'a weighted'
    supers(s)               mg/cm3 -> mg/cm³, m2 -> m², 10^-4 -> 10⁻⁴
    dashes(s)               5-10 -> 5–10 (digits both sides only; dates and ids untouched)
    typeset(s)              dashes + supers + tie
    set_html(esc)           on ESCAPED html: unbreakable hyphen compounds ('wearable-estimated'), loose tracking at hyphens
    unit_pair_issues(text)  '7.62 hours ... and 7.52' (unit on the first number only) -> list of findings (copy-stage)
    font_floor(html, ...)   DOM scan: every text node holding a number, its px size at 1080; pass/fail + exact offenders
    contrast_report(html)   text/background contrast and colour-blind separation of categorical fills
    legibility_gate(lg)     (ok, failing) from render.legibility()'s report
    readback_compare(...)   OCR text vs the card's headline/takeaway words
    ten_second(card)        headline + data block answer what / how much / compared with what
    alt_text(facts, card)   {"alt", "long"} generated from facts + card, numbers only from the card's own slots
    embed_alt(png, alt)     PNG 'Description' text chunk + <stem>.alt.json sidecar
    sr_data_tables(card)    <table> fallback for every chart (screen readers); sr_page_patch for publish/permalink
    subset_fonts_css(...)   embedded subset fonts (woff) so every render uses the same metrics
"""
from __future__ import annotations

import base64, difflib, html, io, json, math, pathlib, re

HERE = pathlib.Path(__file__).parent
NBSP = "\u00a0"
FLOOR_PX = 20.0            # item 66: a value number (tile figures and SDs, bar/forest values, big numbers) is never set below this on the 1080 canvas
FLOOR_LABEL_PX = 18.0      # annotation numbers inside the data block (axis, CI, n, N line, source strip): 18px (20px made 3-line forest rows overflow)
FLOOR_FINE_PX = 14.0       # footer / eyebrow / badges / ordinal dots: not data, keep their own lower floor
FLOOR_PROSE_PX = 14.4      # running prose that happens to hold a number (beats, dek, boundary, context tiles)
SUBSTITUTIONS = ("\u2212", "\u2013", "\u00b2", "\u00b3", "\u207b", "\u2074", "\u2075", "\u2076")

# ------------------------------------------------------------------ units
_UNITS = (r"%|percent|mmol/L|ng/mL|nmol/L|pmol/L|mg/dL|mg/cm3|mg/cm\u00b3|kg/m2|kg/m\u00b2|g/100 g|g/day|g/d|mg/d|\u00b5g|mcg|mg|kg|g|ml|mL|dL|L|"
          r"cm|mm|m/s|m|bpm|mmHg|kcal|kJ|IU|Hz|ms|h|hr|hrs|min|sec|s|hours?|minutes?|seconds?|days?|weeks?|months?|years?|nights?|"
          r"adults|people|participants|athletes|trials|tests|cups?|steps|points?|pp")
_NUM = r"[\u2212+\-]?\d[\d,]*(?:\.\d+)?"
_SHORT_WORDS = r"(?:a|an|in|of|to|by|at|is|on|or|as|no|vs)"


def tie(s: str) -> str:
    """No-break spaces where a break would split a reading unit."""
    if not isinstance(s, str):
        return s
    s = re.sub(rf"(?<![\w.])({_NUM})\s+(?=(?:{_UNITS})(?![\w]))", rf"\1{NBSP}", s)          # 40 g, 7.62 h, 5 mg/cm3
    s = re.sub(r"\b(PMID|PMCID|DOI|NCT)\s+(?=\w)", rf"\1{NBSP}", s)                           # PMID 40540267
    s = re.sub(r"\b(N|n)\s*=\s*(?=[\d\u2212-])", lambda m: f"{m.group(1)}{NBSP}={NBSP}", s)    # N = 21
    s = re.sub(rf"\b(p|P)\s*([<>=\u2264\u2265])\s*(?=[\d.])", lambda m: f"{m.group(1)}{NBSP}{m.group(2)}{NBSP}", s)  # p > 0.05
    s = re.sub(r"(\d%?)\s+(CI|IQR|SD|SE)\b", rf"\1{NBSP}\2", s)                                # 95% CI
    s = re.sub(rf"({_NUM}%?)\s+(to|and|vs\.?)\s+(?=[\u2212+\-]?\d)", lambda m: f"{m.group(1)}{NBSP}{m.group(2)}{NBSP}", s)  # 0.09 to 0.11
    return s


def tie_short(esc: str) -> str:
    """Headline / takeaway only: a one- or two-letter function word stays with the next word ('a weighted', 'in 21')."""
    return _outside_tags(esc, lambda t: re.sub(rf"(?<![\w]){_SHORT_WORDS}[ ](?=[^\s<])", lambda m: m.group(0).rstrip() + NBSP, t, flags=re.I))


_SUP = {"0": "\u2070", "1": "\u00b9", "2": "\u00b2", "3": "\u00b3", "4": "\u2074", "5": "\u2075", "6": "\u2076", "7": "\u2077",
        "8": "\u2078", "9": "\u2079", "-": "\u207b", "\u2212": "\u207b"}


def supers(s: str) -> str:
    """Units as the paper prints them: cm3 -> cm³, m2 -> m², 10^-4 -> 10⁻⁴."""
    if not isinstance(s, str):
        return s
    s = re.sub(r"\b(cm|mm|m|km)([23])\b(?!\.\d)", lambda m: m.group(1) + _SUP[m.group(2)], s)
    s = re.sub(r"\b(10)\^([\-\u2212]?\d+)", lambda m: m.group(1) + "".join(_SUP[ch] for ch in m.group(2)), s)
    return s


def dashes(s: str) -> str:
    """Ranges get an en dash: 5-10 -> 5–10. Dates (2025-10-25), ids and hyphen-chains are left alone."""
    if not isinstance(s, str):
        return s
    return re.sub(r"(?<![\w.\-])(\d{1,4}(?:\.\d+)?)-(\d{1,4}(?:\.\d+)?)(?![\w\-]|\.\d)", "\\1\u2013\\2", s)


def typeset(s: str) -> str:
    return tie(supers(dashes(s))) if isinstance(s, str) else s


def plain(s: str) -> str:
    """Text with the set-only characters folded back (for the 'only how it is set' test)."""
    if not isinstance(s, str):
        return s
    s = s.replace(NBSP, " ").replace("\u202f", " ").replace("\u2212", "-").replace("\u2013", "-").replace("\u2011", "-").replace("\u2010", "-")
    for k, v in _SUP.items():
        if v in s and k not in "-":
            s = s.replace(v, k)
    return s.replace("\u207b", "-")


# ------------------------------------------------------------------ html level (input is already escaped)
_COMPOUND = re.compile(r"(?<![\w&#;.-])((?:[A-Za-z\u00c0-\u024f]{1,12}|\d+(?:\.\d+)?)(?:-[A-Za-z\u00c0-\u024f]{1,12}){1,2})(?![\w-])")   # also '2.2-fold', '49-fold', '12-week' (number + word)


def _outside_tags(esc: str, fn):
    parts = re.split(r"(<[^>]+>)", esc)
    return "".join(p if p.startswith("<") else fn(p) for p in parts)


def set_html(esc: str) -> str:
    """Escaped headline/takeaway html -> compounds never split at their hyphen ('wearable-/estimated'), the hyphen glyph gets
    its own span so headline tracking can loosen there (item 17). Spans are inline; text content is unchanged."""
    def comp(m):
        w = m.group(1)
        if len(w) > 24:
            return w
        return '<span class="nb">' + w.replace("-", '<span class="hy">-</span>') + "</span>"
    return _outside_tags(esc, lambda t: _COMPOUND.sub(comp, t))


def widow_tie(esc: str, words: int = 3) -> str:
    """Escaped html: bind the last `words` words of the text with no-break spaces, so the last line never holds one or two
    words ('over / a year.' -> 'over a year.' together). Spaces inside tags are untouched."""
    parts = re.split(r"(<[^>]+>)", esc)
    idx = [i for i, p in enumerate(parts) if not p.startswith("<") and re.search(r"[ \u00a0]", p)]
    todo = words - 1
    for i in reversed(idx):
        if todo <= 0:
            break
        seg = parts[i]
        pos = [m.start() for m in re.finditer(r" ", seg)]
        while pos and todo > 0:
            k = pos.pop()
            if k == len(seg) - 1:             # trailing space before a tag: keep breakable
                continue
            seg = seg[:k] + NBSP + seg[k + 1:]
            todo -= 1
        parts[i] = seg
    return "".join(parts)


def unit_pair_issues(text: str) -> list[str]:
    """Item 16: '7.62 hours ... and 7.52' -- a unit on the first number of a pair and none on the second.
    Detection only (changing the words belongs to the copy stage)."""
    out = []
    for m in re.finditer(rf"({_NUM})\s*({_UNITS})\b[^.;]{{0,60}}?\b(?:and|vs\.?|versus|or|to)\s+({_NUM})(?!\s*(?:{_UNITS})\b)(?![\d.]*\s*%)", text or ""):
        u = m.group(2)
        if u in ("%",):
            continue
        out.append(f"unit '{u}' on {m.group(1)} but not on {m.group(3)}: '{m.group(0)[:70]}'")
    return out


# ------------------------------------------------------------------ DOM scans (Playwright; reuse a `pw` when inside fit())
FLOOR_JS = r"""
(args) => {
  const [floor, fine, prose, label] = args; const out = [];
  const card = document.querySelector('.card'); if (!card) return out;
  const w = document.createTreeWalker(card, NodeFilter.SHOW_TEXT); let n;
  const FINE = '.foot, .boundary .hd2, .hero .lbl, .eyebrow, .hdr, .beat .n';
  const VALUE = '.tile .s, .tile .v, .big, .val, .est, .v';
  const PROSE = '.beat .tx, .dek, .boundary p, .ctx, .takeaway, h1, .stats-line';
  while ((n = w.nextNode())) {
    const t = n.textContent; if (!/\d/.test(t) || !t.trim()) continue;
    const el = n.parentElement; const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none' || el.closest('svg')) continue;
    if (el.closest('.sr-only')) continue;
    const r = el.getBoundingClientRect(); if (r.width < 1) continue;
    const px = parseFloat(cs.fontSize);
    const slot = el.closest('[data-slot]'); const isFine = !!el.closest(FINE);
    const min = isFine ? fine : (el.closest(PROSE) ? prose : (el.closest(VALUE) ? floor : label));
    if (px + 0.05 < min) {
      const cls = []; for (let e = el; e && e !== slot && cls.length < 3; e = e.parentElement) if (e.className && typeof e.className === 'string') cls.unshift('.' + e.className.trim().split(/\s+/)[0]);
      out.push({slot: slot ? slot.dataset.slot : '?', el: cls.join(' '), text: t.trim().slice(0, 40), px: Math.round(px * 100) / 100, min});
    }
  }
  return out;
}
"""

CONTRAST_JS = r"""
() => {
  const parse = c => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(',').map(s => parseFloat(s)); return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1}; };
  const bgOf = el => { let e = el; let acc = null;
    while (e) { const c = parse(getComputedStyle(e).backgroundColor); if (c && c.a > 0.5) return c; e = e.parentElement; }
    return parse(getComputedStyle(document.body).backgroundColor) || {r: 255, g: 255, b: 255, a: 1}; };
  const text = []; const w = document.createTreeWalker(document.querySelector('.card'), NodeFilter.SHOW_TEXT); let n;
  while ((n = w.nextNode())) {
    if (!n.textContent.trim()) continue; const el = n.parentElement; const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || el.closest('.sr-only') || el.getBoundingClientRect().width < 1) continue;
    const fg = parse(cs.color); if (!fg) continue;
    const slot = el.closest('[data-slot]');
    text.push({fg: [fg.r, fg.g, fg.b], a: fg.a, bg: (b => [b.r, b.g, b.b])(bgOf(el)), px: parseFloat(cs.fontSize), bold: parseInt(cs.fontWeight) >= 700,
               text: n.textContent.trim().slice(0, 36), slot: slot ? slot.dataset.slot : '?', el: (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/)[0] : el.tagName.toLowerCase())});
  }
  const fills = []; const seen = new Set();
  for (const el of document.querySelectorAll('.card .bar, .card .pt, .card .pip.on, .card .beat .n, .card .tile, .card .seg, .card .b.cyl, .card .b.flat, .card .b.cube, .card .cert, .card .meter')) {
    const cs = getComputedStyle(el); let c = parse(cs.backgroundColor); if (!c || c.a < .5) c = parse(cs.borderTopColor);
    if (!c || c.a < .5) continue; const k = c.r + ',' + c.g + ',' + c.b;
    const slot = el.closest('[data-slot]');
    fills.push({rgb: [c.r, c.g, c.b], el: '.' + (el.className && typeof el.className === 'string' ? el.className.trim().split(/\s+/)[0] : el.tagName), slot: slot ? slot.dataset.slot : '?', k});
  }
  return {text, fills};
}
"""


def _page(pw, html_path, w=1080, h=1350):
    b = pw.chromium.launch()
    pg = b.new_page(viewport={"width": w, "height": h})
    pg.goto(pathlib.Path(html_path).resolve().as_uri())
    pg.wait_for_load_state("networkidle")
    pg.evaluate("document.fonts.ready")
    return b, pg


def _with_pw(pw, fn):
    if pw is not None:
        return fn(pw)
    try:                                   # merged render: inside render.render_session() reuse its Playwright (a nested sync_playwright fails)
        import render as _R
        if _R._SESSION["depth"] > 0: return fn(_R._SESSION["p"])
    except Exception: pass
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        return fn(p)


def font_floor(html_path, pw=None, floor=FLOOR_PX, fine=FLOOR_FINE_PX, prose=FLOOR_PROSE_PX, label=FLOOR_LABEL_PX) -> list[dict]:
    """Offenders: every number-bearing text node set below the floor on the 1080 canvas. [] = pass."""
    def run(p):
        b, pg = _page(p, html_path)
        r = pg.evaluate(FLOOR_JS, [floor, fine, prose, label])
        b.close()
        return r
    return _with_pw(pw, run)


# ---- colour maths
def _lin(c):
    c = c / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rgb):
    r, g, b = (_lin(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg, bg):
    a, b = luminance(fg), luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def _blend(fg, bg, a):
    return [fg[i] * a + bg[i] * (1 - a) for i in range(3)]


# Machado et al. 2009, severity 1.0, linear RGB
_CVD = {"deuteranopia": ((0.367322, 0.860646, -0.227968), (0.280085, 0.672501, 0.047413), (-0.011820, 0.042940, 0.968881)),
        "protanopia": ((0.152286, 1.052583, -0.204868), (0.114503, 0.786281, 0.099216), (-0.003882, -0.048116, 1.051998))}


def simulate(rgb, kind):
    m = _CVD[kind]
    lin = [_lin(x) for x in rgb]
    out = [sum(m[i][j] * lin[j] for j in range(3)) for i in range(3)]
    f = lambda v: 255 * (12.92 * v if v <= 0.0031308 else 1.055 * max(v, 0) ** (1 / 2.4) - 0.055)
    return [min(255, max(0, f(max(0, min(1, v))))) for v in out]


def _lab(rgb):
    r, g, b = (_lin(x) for x in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    f = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e(a, b):
    return math.dist(_lab(a), _lab(b))


def contrast_report(html_path, pw=None, min_normal=4.5, min_large=3.0, cvd_min=14.0, apart=28.0) -> dict:
    """Item 64: every text/background pair; item 63: categorical fills that are distinct to a normal eye must stay distinct
    under deuteranopia and protanopia (red/green is never the only difference). pass is False when anything fails."""
    def run(p):
        b, pg = _page(p, html_path)
        r = pg.evaluate(CONTRAST_JS)
        b.close()
        return r
    d = _with_pw(pw, run)
    low, seen = [], set()
    for t in d["text"]:
        fg = _blend(t["fg"], t["bg"], t["a"]) if t["a"] < 1 else t["fg"]
        cr = contrast_ratio(fg, t["bg"])
        large = t["px"] >= 24 or (t["px"] >= 18.66 and t["bold"])
        need = min_large if large else min_normal
        key = (t["slot"], t["el"], tuple(round(x) for x in fg), tuple(round(x) for x in t["bg"]))
        if cr + 1e-9 < need and key not in seen:
            seen.add(key)
            low.append({"slot": t["slot"], "el": t["el"], "text": t["text"], "ratio": round(cr, 2), "need": need, "px": round(t["px"], 1),
                        "fg": "#%02x%02x%02x" % tuple(round(x) for x in fg), "bg": "#%02x%02x%02x" % tuple(round(x) for x in t["bg"])})
    uniq = {}
    for f in d["fills"]:
        uniq.setdefault(f["k"], f)
    cols = list(uniq.values())
    cvd = []
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            a, b_ = cols[i]["rgb"], cols[j]["rgb"]
            if delta_e(a, b_) < apart:
                continue                                    # not meant to be told apart in the first place
            for kind in _CVD:
                de = delta_e(simulate(a, kind), simulate(b_, kind))
                if de < cvd_min:
                    cvd.append({"kind": kind, "a": cols[i]["el"] + "@" + cols[i]["slot"], "b": cols[j]["el"] + "@" + cols[j]["slot"],
                                "rgb_a": a, "rgb_b": b_, "delta_e": round(de, 1), "need": cvd_min})
    return {"pass": not low and not cvd, "contrast_failures": low, "colour_blind_failures": cvd, "texts": len(d["text"]), "fills": len(cols)}


# ------------------------------------------------------------------ gates
def legibility_gate(lg: dict, floor: list[dict] | None = None) -> tuple[bool, list[str]]:
    """Item 68: pass/fail with the exact failing numbers. `lg` is render.legibility()'s report (OCR misses), `floor` the
    font_floor() offenders (defaults to lg['floor'])."""
    floor = lg.get("floor") if floor is None else floor
    msgs = []
    for n in lg.get("missing") or []:
        loc = (lg.get("where") or {}).get(n) or {}
        msgs.append(f"OCR cannot read {n} at {lg.get('width', 390)}px" + (f" (slot {loc.get('slot')}, {loc.get('el')}, {loc.get('px')}px)" if loc else ""))
    for f in floor or []:
        msgs.append(f"{f['text']!r} set at {f['px']}px < {f['min']:g}px (slot {f['slot']}, {f['el']})")
    for r in lg.get("readback_failures") or []:
        msgs.append(f"read-back: {r}")
    return (not msgs), msgs


def _words(s):
    return re.findall(r"[a-z0-9\u00b5][a-z0-9.%\u00b5'\-]*", plain(html.unescape(s or "")).lower())


def readback_compare(ocr_text: str, expected: str, min_hit=0.88, cutoff=0.8) -> dict:
    """Item 69: how much of the card text OCR finds (fuzzy per word; OCR is a lower bound, so the threshold is below 1)."""
    ow = _words(ocr_text)
    ex = _words(expected)
    miss = []
    pool = set(ow)
    for w in ex:
        if w in pool:
            continue
        if len(w) > 3 and difflib.get_close_matches(w, ow, n=1, cutoff=cutoff):
            continue
        miss.append(w)
    hit = 1 - len(miss) / max(len(ex), 1)
    return {"pass": hit >= min_hit, "hit": round(hit, 3), "missing": miss, "words": len(ex)}


_COMPARATOR = re.compile(r"\b(vs\.?|versus|than|compared|placebo|control|alone|usual|baseline|before|after|without|against|did not (?:change|differ)|no (?:change|difference))\b", re.I)


def ten_second(card: dict) -> dict:
    """Item 70: headline + data block alone say what (an outcome/subject), how much (a number) and compared with what
    (a comparator word, or >= 2 labelled arms/values). Findings are review flags, not copy."""
    h = (card.get("headline") or {}).get("text", "")
    b = card.get("data_block") or {}
    items = b.get("items") or b.get("rows") or b.get("series") or []
    labels = " ".join(str(i.get("label", "")) for i in items if isinstance(i, dict))
    blob = " ".join([h, b.get("title", "") or "", b.get("subtitle", "") or "", labels])
    nums = bool(re.search(r"\d", h)) or any(isinstance(i, dict) and (i.get("value") is not None or i.get("display")) for i in items) or b.get("type") in ("line_area", "waffle", "dotmatrix")
    what = len(re.findall(r"[A-Za-z]{4,}", h)) >= 3
    cmp_ = bool(_COMPARATOR.search(blob)) or len([i for i in items if isinstance(i, dict)]) >= 2
    issues = []
    if not what: issues.append("what: headline names no outcome")
    if not nums: issues.append("how much: no number in headline or data block")
    if not cmp_: issues.append("compared with what: no comparator in headline/data block")
    return {"pass": not issues, "what": what, "how_much": nums, "compared_with": cmp_, "issues": issues}


# ------------------------------------------------------------------ alt text (71)
def _num_txt(v):
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return f"{v:g}" if isinstance(v, float) else str(v)


def alt_text(facts: dict, card: dict, site: str | None = None, max_alt=250) -> dict:
    """Alt text from the card's own slots, checked against facts: every number is printed by the card; the outcome, the
    comparator, N and the certainty come from facts/card. `alt` is the short image description (<= max_alt chars),
    `long` the full description (every value). Never introduces a number the card does not show."""
    f = facts or {}
    h = (card.get("headline") or {}).get("text", "").strip()
    b = card.get("data_block") or {}
    cert = (card.get("certainty") or {}).get("label")
    design = (f.get("design") or "").replace("_", " ")
    n = f.get("n")
    parts_vals = []
    for blk in (card.get("data_block"), card.get("secondary_block")):
        if not blk:
            continue
        t = (blk.get("title") or blk["type"].replace("_", " ")).rstrip(".")
        if blk.get("items"):
            vals = "; ".join(f"{it.get('label', '')} {it.get('display') or _num_txt(it.get('value'))}".strip() for it in blk["items"] if isinstance(it, dict))
            parts_vals.append(f"{t}: {vals}.")
        elif blk.get("rows"):
            parts_vals.append(f"{t}: " + "; ".join(f"{r.get('label', '')} " + ", ".join(_num_txt(v) for v in r.get("values", [])) for r in blk["rows"]) + ".")
        elif blk.get("series"):
            parts_vals.append(f"{t}: " + "; ".join(f"{s.get('label', '')} ends at {_num_txt(s['points'][-1][1])}" for s in blk["series"] if s.get("points")) + ".")
    hp = h if not h or h[-1] in ".!?" else h + "."
    comp = ""
    prim = next((o for o in (f.get("outcomes") or []) if o.get("comparator")), None)
    if prim:
        comp = f"Compared with {prim['comparator']}."
    ctx = ", ".join(x for x in [design.capitalize() if design else "", f"N = {n}" if n else "", f"{cert}" if cert else ""] if x)
    short = " ".join(x for x in [hp, ctx + "." if ctx else "", comp] if x)
    if len(short) > max_alt:
        short = " ".join(x for x in [hp, ctx + "." if ctx else ""] if x)
    if len(short) > max_alt:
        short = h[:max_alt - 1].rstrip() + "\u2026"
    long = " ".join(x for x in [hp, ctx + "." if ctx else "", comp, *parts_vals, (card.get("evidence_boundary") or "").strip(),
                                (card.get("takeaway") or {}).get("text", ""), f"From {site}." if site else ""] if x)
    return {"alt": short, "long": long}


def embed_alt(png, alt: dict) -> None:
    """Store the alt text with the PNG: a 'Description' iTXt chunk (short) + <stem>.alt.json (short and long).
    Written at byte level by render_meta.stamp_png (pixels, the other metadata chunks and a C2PA manifest are never rewritten);
    a signed PNG keeps its signature and carries the alt text in the sidecar only."""
    import render_meta
    png = pathlib.Path(png)
    render_meta.stamp_png(png, ctx={"Description": alt["alt"]})
    png.with_suffix(".alt.json").write_text(json.dumps(alt, indent=1, ensure_ascii=False))


# ------------------------------------------------------------------ screen readers (72)
def _table(caption, head, rows):
    e = html.escape
    return (f"<table><caption>{e(caption)}</caption><thead><tr>" + "".join(f"<th scope=col>{e(h)}</th>" for h in head) + "</tr></thead><tbody>"
            + "".join("<tr>" + "".join(f"<{'th scope=row' if i == 0 else 'td'}>{e(str(c))}</{'th' if i == 0 else 'td'}>" for i, c in enumerate(r)) + "</tr>" for r in rows)
            + "</tbody></table>")


def sr_data_tables(card: dict) -> str:
    """A <table> for every chart/data block on the card: label, value, interval, n. Plain text, no styling dependence."""
    out = []
    for key in ("data_block", "secondary_block"):
        b = card.get(key)
        if not b:
            continue
        cap = (b.get("title") or b.get("type", "data").replace("_", " ")) + (f" ({b['subtitle']})" if b.get("subtitle") else "")
        if b.get("items"):
            has_ci = any(isinstance(i, dict) and i.get("ci") for i in b["items"])
            has_sub = any(isinstance(i, dict) and (i.get("sub") or i.get("n")) for i in b["items"])
            head = ["Label", "Value"] + (["95% interval"] if has_ci else []) + (["Detail"] if has_sub else [])
            rows = []
            for i in b["items"]:
                if not isinstance(i, dict):
                    continue
                r = [i.get("label", ""), i.get("display") or _num_txt(i.get("value", ""))]
                if has_ci: r.append(f"{_num_txt(i['ci'][0])} to {_num_txt(i['ci'][1])}" if i.get("ci") else "not reported")
                if has_sub: r.append(i.get("sub") or (f"n = {i['n']}" if i.get("n") else ""))
                rows.append(r)
            out.append(_table(cap, head, rows))
        elif b.get("rows"):
            cats = b.get("categories") or []
            out.append(_table(cap, ["Row"] + [f"{c} (%)" for c in cats], [[r.get("label", "")] + [_num_txt(v) for v in r.get("values", [])] for r in b["rows"]]))
        elif b.get("series"):
            for s in b["series"]:
                out.append(_table(f"{cap}: {s.get('label', '')}", ["x", "y"], [[_num_txt(p[0]), _num_txt(p[1])] for p in s.get("points", [])]))
        elif b.get("steps"):
            out.append(_table(cap, ["Step", "Detail"], [[s.get("label", s.get("title", "")), s.get("text", s.get("sub", ""))] if isinstance(s, dict) else [s, ""] for s in b["steps"]]))
    return "\n".join(out)


SR_CSS = ".sr-only{position:absolute!important;width:1px;height:1px;margin:-1px;padding:0;overflow:hidden;clip:rect(0 0 0 0);clip-path:inset(50%);white-space:nowrap;border:0}"


def sr_only_html(card: dict) -> str:
    """Hidden block appended inside .card (template hunk): the data tables for assistive tech, invisible in the PNG."""
    t = sr_data_tables(card)
    return f'<div class="sr-only" role="region" aria-label="Data tables for this card">{t}</div>' if t else ""


# ------------------------------------------------------------------ embedded subset fonts (22)
_SUBSET_RANGES = ("U+0020-007E,U+00A0-00FF,U+0100-017F,U+2010-2027,U+202F,U+2030-203A,U+2070-209F,U+2190-21FF,U+2200-22FF,"
                  "U+25A0-25FF,U+03B1-03C9,U+0394,U+03A3,U+03BC,U+00B5,U+2212,U+2264,U+2265,U+00D7,U+25B6,U+25B2,U+25CB,U+2205")
_CACHE: dict = {}


def subset_fonts_css(font_files) -> str:
    """@font-face rules with the faces subset (fontTools, WOFF) to the glyphs a card can use, base64-inlined. Deterministic,
    cached per process. Fails loudly (FileNotFoundError) when a required face is missing, instead of silently falling back."""
    from fontTools import subset as ST
    from fontTools.ttLib import TTFont
    unicodes = ST.parse_unicodes(_SUBSET_RANGES)
    css = []
    for fam, w, p in font_files:
        q = pathlib.Path(p)
        if not q.exists():
            raise FileNotFoundError(f"font missing: {fam} {w} at {p}")
        key = (str(q), q.stat().st_mtime_ns)
        if key not in _CACHE:
            opts = ST.Options()
            opts.flavor = "woff"
            opts.layout_features = ["kern", "liga", "tnum", "lnum", "case", "ccmp", "locl", "mark", "mkmk", "sups", "frac"]
            opts.name_IDs = [1, 2]
            opts.notdef_outline = True
            opts.hinting = False
            font = TTFont(str(q))
            sub = ST.Subsetter(opts)
            sub.populate(unicodes=unicodes)
            sub.subset(font)
            buf = io.BytesIO()
            font.flavor = "woff"
            font.save(buf)
            _CACHE[key] = base64.b64encode(buf.getvalue()).decode()
        css.append(f'@font-face{{font-family:"{fam}";font-weight:{w};src:url(data:font/woff;base64,{_CACHE[key]}) format("woff");}}')
    return "\n".join(css)
