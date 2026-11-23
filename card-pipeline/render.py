#!/usr/bin/env python3
"""
render.py — card.json -> HTML -> PNG (+PDF), with the FIT LOOP. Deterministic: no model calls.

Loop L2: render in "measure" mode (auto height), compare content height to the canvas, then
  1. let the hero column absorb slack (grow) before touching type,
  2. scale the global font between a floor (0.9) and a ceiling (1.1) — everything is em-based,
  3. below the floor, report which block to trim instead of shrinking further,
  3b. LEGIBILITY GATE (blocking): type never shrinks below fs 1.0 unless the 390px phone render still OCRs every
      number; if it does not, the loop stops and reports the slot to trim. main() re-checks the final render and
      exits 3 when any number is unreadable at 390px (unless --allow-illegible).
  4. reflow headline / dek / takeaway so no line ends in a single word and the red payoff starts a line.

Usage:
  python render.py cards/x.json [-o out] [--scale 2] [--target print|social] [--pdf] [--theme dark]
                   [--inline-fonts] [--carousel] [--variants] [--fs 1.0] [--brand brand.json]
"""
import argparse, base64, copy, datetime, hashlib, html, json, math, pathlib, re, shutil, subprocess
from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup
import typeset

HERE = pathlib.Path(__file__).parent
CANVAS = {"4:5": (1080, 1350), "1:1": (1080, 1080), "9:16": (1080, 1920)}
TARGETS = {"print": {"scale": 3, "pdf": True}, "social": {"scale": 2, "pdf": False}}
FS_FLOOR, FS_CEIL = 0.9, 1.1
FS_LEGIBLE = 1.0                          # the CSS type floor (0.95em for any number) is calibrated at fs 1.0
EXIT_ILLEGIBLE = 3
EXIT_GATE = 5
HERO_MIN, HERO_MAX = 18.0, 30.0           # em, column heroes
BAND_MIN, BAND_MAX = 10.0, 16.0           # em, band heroes

# ---------------------------------------------------------------- honesty tables (mirror audit.py)
OBSERVATIONAL = {"cohort", "case_control", "cross_sectional", "records_review"}
DESIGN_LABEL = {"cohort": "Observational cohort", "case_control": "Case-control", "cross_sectional": "Cross-sectional",
                "records_review": "Records review", "animal": "Animal study", "mechanistic": "Mechanism",
                "pilot": "Pilot study", "review": "Review", "meta_analysis": "Meta-analysis"}
SPECIES_LABEL = {"mouse": "Mouse study", "rat": "Rat study", "cell": "Cell study", "mixed": "Mixed species"}
STRENGTH_RANK = {"observation": 1, "association": 2, "mechanism": 3, "recommendation": 4}
TONE_FOR_STRENGTH = {"observation": {"caveat", "caution"}, "association": {"caveat", "caution"},
                     "mechanism": {"caveat", "caution", "action"}, "recommendation": {"action", "caution", "caveat"}}
PROXY_WORDS = ("estimated", "self-reported", "self-report", "wrist", "wrist-estimated", "questionnaire", "device-estimated", "inferred")

# ---------------------------------------------------------------- typography filters
_UNIT = r"(?:%|percent|mmol/L|ng/mL|nmol/L|mg/dL|g/100 g|adults|people|trials|tests|hours|minutes|seconds|years|months|weeks|days|mg|g|kg|ml|m/s|cups?)"

def typo(s):
    """True minus before numbers, × for multiplication, no space before %, thin space before compound units."""
    if not isinstance(s, str): return s
    s = re.sub(r"(?<![\w.])-(?=\d)", "−", s)               # -46 -> −46  (not in 'et-al' or 'a-b')
    s = re.sub(r"(?<=\d)\s*[x×]\s*(?=\d)", "×", s)         # 2 x 3 -> 2×3
    s = re.sub(r"(?<=\d)\s*x\b", "×", s)                   # 2x -> 2×
    s = re.sub(r"(?<=\d)\s+%", "%", s)                          # 42 % -> 42%
    s = re.sub(r"(?<=\d)\s+(?=[A-Za-zµ]+/[0-9A-Za-z]+)", " ", s)  # 5 g/100 g -> 5 g/100 g (thin space)
    return typeset.typeset(s)                                  # r2: no-break ties, superscript units, en-dash ranges (typeset.py)

def mark(text, sub, cls, proxy=False):
    """Wrap `sub` (payoff / highlight) in a span; optionally dotted-underline proxy-measure words."""
    text, sub = typo(text), typo(sub)
    esc = html.escape(text)
    if sub and html.escape(sub) in esc:
        esc = esc.replace(html.escape(sub), f'<span class="{cls}">{html.escape(sub)}</span>', 1)
    if proxy:
        for w in sorted(PROXY_WORDS, key=len, reverse=True):
            esc = re.sub(rf"(?<![\w-])({re.escape(w)})(?![\w-])", r'<span class="proxy">\1</span>', esc, flags=re.I)
    return Markup(typeset.widow_tie(typeset.tie_short(typeset.set_html(esc))))

def boldnums(text):
    esc = html.escape(typo(text))
    return Markup(typeset.set_html(re.sub(rf"(?<!&#x)(?<!&#)(\d[\d,.]*\s?{_UNIT}?)", r"<b>\1</b>", esc)))

def bignum(s):
    """−46% -> −46<small>%</small>; 1.9 / 10 -> 1.9<small> / 10</small>."""
    s = html.escape(typo(str(s)))
    m = re.match(r"^([−+\-]?[\d,.]+)(.*)$", s)
    if m and m.group(2).strip():
        return Markup(f"{m.group(1)}<small>{m.group(2)}</small>")
    return Markup(s)

NAMED = {"red", "amber", "green", "blue", "purple", "grey-bar", "ochre1", "ochre2", "ink", "ink3"}
def col(name):
    """Palette names -> CSS vars so cards say 'purple', not a hex."""
    if not name: return name
    n = str(name).lower().replace("gray", "grey")
    if n == "grey": n = "grey-bar"
    return f"var(--{n})" if n in NAMED else name

def nice_step(vmax, target=4):
    raw = vmax / target
    if raw <= 0: return 1
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag: return m * mag
    return 10 * mag

def nice_ticks(vmin, vmax, target=4):
    """Nice tick values covering [vmin, vmax]."""
    if vmax <= vmin: return [vmin, vmax]
    step = nice_step(vmax - vmin, target)
    if (vmax - vmin) <= 3.0 and step > 0.5 and step < 1.5: step = 0.5     # 71: small ranges (0 to 3) tick every 0.5
    lo = math.floor(vmin / step) * step
    hi = math.ceil(vmax / step) * step
    n = int(round((hi - lo) / step))
    ticks = [lo + i * step for i in range(n + 1)]
    return [round(t, 6) for t in ticks]

def fmt(v):
    if isinstance(v, float) and v.is_integer(): v = int(v)
    if isinstance(v, float): return typo(f"{v:g}")
    return typo(str(v))

# ---------------------------------------------------------------- line chart geometry (python, deterministic)
def catmull_rom(pts, tension=0.5):
    """Centripetal-ish Catmull-Rom through pts -> SVG path with cubic beziers."""
    if len(pts) < 3: return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    d = [f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"]
    for i in range(len(pts) - 1):
        p0 = pts[i - 1] if i > 0 else pts[i]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[i + 2] if i + 2 < len(pts) else p2
        c1 = (p1[0] + (p2[0] - p0[0]) * tension / 3, p1[1] + (p2[1] - p0[1]) * tension / 3)
        c2 = (p2[0] - (p3[0] - p1[0]) * tension / 3, p2[1] - (p3[1] - p1[1]) * tension / 3)
        d.append(f"C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}")
    return " ".join(d)

def line_geom(b, colors):
    W, H, pl, pr, pt, pb = 560, 240, 46, 170, 26, 36
    series = b["series"]
    allp = [p for s in series for p in s["points"]]
    xs, ys = [p[0] for p in allp], [p[1] for p in allp]
    ys += [v for s in series for c in (s.get("ci") or []) for v in (c or []) if isinstance(v, (int, float))]
    x0, x1 = min(xs), max(xs)
    y0 = min(0, min(ys))
    ticks = nice_ticks(y0, max(ys) * 1.08, 4)
    y1 = ticks[-1]
    X = lambda v: pl + (v - x0) / ((x1 - x0) or 1) * (W - pl - pr)
    Y = lambda v: pt + (1 - (v - y0) / ((y1 - y0) or 1)) * (H - pt - pb)
    smooth = bool(b.get("illustrative"))
    out = {"W": W, "H": H, "pl": pl, "pr": pr, "pt": pt, "pb": pb, "x0": fmt(x0), "x1": fmt(x1),
           "grid": [{"y": round(Y(t), 1), "label": fmt(t)} for t in ticks], "series": [], "fill": None, "peak": None,
           "xticks": []}
    scaled = []
    for i, s in enumerate(series):
        pts = [(round(X(p[0]), 1), round(Y(p[1]), 1)) for p in s["points"]]
        scaled.append(pts)
        col = s.get("color") or colors[i % len(colors)]
        band = None
        cis = s.get("ci") or []
        if cis and len(cis) == len(s["points"]) and all(c and len(c) == 2 for c in cis):
            up = [(round(X(p[0]), 1), round(Y(c[1]), 1)) for p, c in zip(s["points"], cis)]
            dn = [(round(X(p[0]), 1), round(Y(c[0]), 1)) for p, c in zip(s["points"], cis)]
            band = "M" + " L".join(f"{x},{y}" for x, y in up) + " L" + " L".join(f"{x},{y}" for x, y in reversed(dn)) + " Z"
        out["series"].append({"band": band, "label": s["label"], "color": col, "path": catmull_rom(pts) if smooth else "M" + " L".join(f"{x},{y}" for x, y in pts),
                              "pts": pts, "end": {"x": pts[-1][0], "y": pts[-1][1], "v": fmt(s["points"][-1][1])},
                              "measured": [j for j, p in enumerate(s["points"]) if (not smooth) or j == 0 or j == len(s["points"]) - 1 or (p[0] in (b.get("measured_x") or []))]})
    if b.get("fill_between") and len(series) == 2:
        a, c = scaled[0], scaled[1]
        if smooth:
            d1 = catmull_rom(a); d2 = catmull_rom(list(reversed(c)))
            out["fill"] = d1 + " L" + d2[1:] + " Z"
        else:
            out["fill"] = "M" + " L".join(f"{x},{y}" for x, y in a) + " L" + " L".join(f"{x},{y}" for x, y in reversed(c)) + " Z"
    if b.get("annotate_peak") and len(series) >= 2:
        s0 = series[0]["points"]; j = max(range(len(s0)), key=lambda k: s0[k][1]); px, pv = s0[j]
        s1 = series[1]["points"]; v1 = next((p[1] for p in s1 if p[0] == px), None)
        if v1 is None:
            v1 = min(s1, key=lambda p: abs(p[0] - px))[1]
        pct = (1 - v1 / pv) * 100 if pv else 0
        out["peak"] = {"x": round(X(px), 1), "y_top": round(Y(pv), 1), "y_bot": round(Y(v1), 1), "y_axis": round(H - pb, 1), "label": typo(f"−{pct:.0f}% below peak")}
    # 46: x ticks at the real timepoints (distinct x values), in the block's own units; never evenly spaced labels
    dx = sorted({p[0] for p in allp})
    if len(dx) <= 6: tx = dx
    else: tx = [t for t in nice_ticks(x0, x1, 5) if x0 <= t <= x1]
    labels = b.get("x_ticks") if b.get("x_ticks") and len(b["x_ticks"]) == len(tx) else None
    out["xticks"] = [{"x": round(X(v), 1), "label": (labels[k] if labels else fmt(v))} for k, v in enumerate(tx)]
    keep = []                                            # 46: drop ticks that would touch (0 and 2 on a 52-week axis); first and last win
    for k, tk in enumerate(out["xticks"]):
        if k == len(out["xticks"]) - 1:
            while keep and tk["x"] - keep[-1]["x"] < 44 and len(keep) > 1: keep.pop()
            if keep and tk["x"] - keep[-1]["x"] < 44: keep.pop()
            keep.append(tk)
        elif not keep or tk["x"] - keep[-1]["x"] >= 44: keep.append(tk)
    out["xticks"] = keep
    ends = sorted(range(len(out["series"])), key=lambda i: out["series"][i]["end"]["y"])      # end labels: no two closer than 22 units
    prev = None
    for i in ends:
        e = out["series"][i]["end"]; e["ly"] = e["y"] if prev is None or e["y"] - prev >= 22 else prev + 22; prev = e["ly"]
    return out

# ---------------------------------------------------------------- derived context (honesty + tone)
# ---------------------------------------------------------------- block preparation (items 73, 76, 78)
ALL_ROW = re.compile(r"^\s*(all|overall|total|pooled|everyone|whole)\b", re.I)
COLUMN_PLACEMENTS = ("left_column", "right_column", "beside", "pair")

def hero_fallback(c, facts=None):
    """73. A column hero with no image (and no images / zoom image) never renders: it collapsed to a sliver and its
    caption ran into the footer. Fall back to the full-width layout (placement 'none') and record why."""
    h = c.setdefault("hero", {})
    import hero_match as _hm; _hm.apply(c, facts)          # 53-58: tagged match on the outcome's body site; no image + recorded reason
    pl = h.get("placement", "left_column")
    has_img = bool(h.get("image") or h.get("images"))
    if pl in COLUMN_PLACEMENTS and not has_img:
        h["requested_placement"] = pl; h["placement"] = "none"; h["fallback"] = "no hero image: full-width layout"
        c.pop("hero2", None) if not (c.get("hero2") or {}).get("image") else None
    return c

def order_forest(b):
    """76. Subgroup forest: the 'all' row first, the rest sorted by magnitude (largest effect first). Forests with no
    all-row keep the author's order (primary / secondary outcomes are ordered by importance, not size)."""
    items = b.get("items") or []
    allrows = [it for it in items if ALL_ROW.match(str(it.get("label", "")))]
    if not allrows or len(items) < 3: return b
    rest = sorted((it for it in items if it not in allrows), key=lambda it: -abs(it.get("value") or 0))
    b["items"] = allrows[:1] + rest + allrows[1:]
    return b

def _outcome_null(o):
    if o is None: return None
    if o.get("significant") is False or o.get("headline_eligible") is False or o.get("null_result"): return True
    ci = o.get("ci"); nv = 1 if (o.get("unit") or "").lower() in ("ratio", "hr", "or", "rr") or o.get("kind") == "ratio" else 0
    if ci and len(ci) == 2: return ci[0] <= nv <= ci[1]
    return None if o.get("significant") is None else not o["significant"]

def sig_only_colour(b, facts, threshold=0.5):
    """78. On null-heavy cards (at least half the referenced outcomes are non-significant) colour encodes significance
    only: significant -> red, not significant -> grey, whatever the direction. Sets item.color and block.sig_only."""
    outs = (facts or {}).get("outcomes") or []
    items = b.get("items") or []
    nulls = [_outcome_null(outs[it["ref"]]) if isinstance(it.get("ref"), int) and it["ref"] < len(outs) else None for it in items]
    known = [n for n in nulls if n is not None]
    if not known or sum(known) / len(known) < threshold: return b
    b["sig_only"] = True
    for it, n in zip(items, nulls):
        it["color"] = "grey" if n else "red"
    return b

def prepare_blocks(c, facts):
    for key in ("data_block", "secondary_block"):
        b = c.get(key)
        if not b: continue
        if b.get("type") == "forest": order_forest(b)
        if b.get("type") in ("forest", "bar_h", "bar_v", "stat_row"): sig_only_colour(b, facts)
        import chartgeom; chartgeom.prepare(b, facts, primary=(key == "data_block"))      # r4: items 32-52
    return c

def derive(doc, brand, theme="light"):
    c = copy.deepcopy(doc["card"]); f = doc.get("facts") or {}
    prepare_blocks(c, f)
    design, species = f.get("design"), f.get("species", "human")
    ctx = {"facts": f, "design": design, "species": species}
    ctx["observational"] = design in OBSERVATIONAL
    ctx["animal"] = species in ("mouse", "rat", "cell") or design == "animal"
    tone = c.get("tone")
    if not tone:
        tone = "trial" if design in ("rct", "crossover") else "observational" if design in OBSERVATIONAL else "mechanism" if design in ("mechanistic", "animal") else "neutral"
    ctx["tone"] = tone
    # design badge (79): explicit card.badge wins; else derive for observational / animal / cell
    badge = c.get("badge"); badge_cls = ""
    if not badge:
        if ctx["animal"]: badge, badge_cls = SPECIES_LABEL.get(species, "Animal study"), "animal"
        elif ctx["observational"]: badge = DESIGN_LABEL.get(design, "Observational")
    elif ctx["animal"]: badge_cls = "animal"
    ctx["badge"], ctx["badge_cls"] = badge, badge_cls
    expo = (f.get("exposure") or "").lower()
    ctx["proxy"] = any(w in expo for w in ("estimat", "self-report", "wrist", "actigraph", "questionnaire", "inferred", "device"))
    ctx["n"] = f.get("n")
    ctx["strength_idx"] = STRENGTH_RANK.get((c.get("takeaway") or {}).get("strength"), 0)
    tk = c.get("takeaway") or {}
    ctx["tone_warning"] = None
    if tk.get("strength") and tk.get("tone") not in TONE_FOR_STRENGTH.get(tk["strength"], set()):
        ctx["tone_warning"] = f"takeaway.tone={tk.get('tone')} is unusual for strength={tk['strength']} (association/observation should read as caveat or caution)"
    ctx["theme"] = theme
    import brand_tokens as _bt; ctx["tokens_css"] = _bt.root_css(brand)
    ctx["aspect"] = c.get("aspect", "4:5")
    ctx["monogram"] = _abs(brand.get("monogram")) if brand.get("monogram") else None
    src = json.dumps(f, sort_keys=True, ensure_ascii=False).encode()
    ctx["provenance"] = {"facts_sha1": hashlib.sha1(src).hexdigest()[:16], "model": doc.get("model") or brand.get("model") or "n/a",
                         "date": datetime.date.today().isoformat(), "renderer": "render.py v2"}
    return c, ctx

# ---------------------------------------------------------------- browser session / timing / preflight (items 89, 90, 92, 96)
import contextlib, os, time, atexit
CHROMIUM_ARGS = ["--font-render-hinting=none", "--disable-lcd-text", "--force-color-profile=srgb", "--disable-gpu",
                 "--hide-scrollbars", "--disable-background-timer-throttling", "--disable-dev-shm-usage"]   # 96: same pixels every run
RENDER_VERSION = "render.py v3-layout"
RENDER_BUDGET_S = float(os.environ.get("RENDER_BUDGET_S", "90"))   # 89: per-card wall-clock budget (fit + png + gates)
class RenderError(RuntimeError):
    """A render precondition failed (missing font / asset): fail fast with a message that names the file."""

_SESSION = {"p": None, "b": None, "depth": 0, "launches": 0}

@contextlib.contextmanager
def render_session():
    """90. One Chromium for a whole batch: every fit()/to_png()/legibility()/layout_check() inside the `with` reuses it
    (nestable). Outside a session each call launches (and closes) its own browser exactly as before."""
    from playwright.sync_api import sync_playwright
    if _SESSION["depth"] == 0:
        _SESSION["p"] = sync_playwright().start()
        _SESSION["b"] = _SESSION["p"].chromium.launch(args=CHROMIUM_ARGS); _SESSION["launches"] += 1
    _SESSION["depth"] += 1
    try: yield _SESSION["b"]
    finally:
        _SESSION["depth"] -= 1
        if _SESSION["depth"] == 0:
            try: _SESSION["b"].close(); _SESSION["p"].stop()
            finally: _SESSION["p"] = _SESSION["b"] = None

@contextlib.contextmanager
def _pw(pw=None):
    """Playwright handle: the session's, the caller's, or a fresh one."""
    from playwright.sync_api import sync_playwright
    if _SESSION["depth"] > 0: yield _SESSION["p"]
    elif pw is not None: yield pw
    else:
        with sync_playwright() as p: yield p

def _launch(p):
    if _SESSION["depth"] > 0: return _SESSION["b"]
    _SESSION["launches"] += 1
    return p.chromium.launch(args=CHROMIUM_ARGS)

def _release(b, pg=None):
    """Close the page; close the browser only when it is not the shared one."""
    if pg is not None:
        try: pg.close()
        except Exception: pass
    if _SESSION["depth"] == 0 or b is not _SESSION["b"]: b.close()

class Timer:
    """89. Per-step wall-clock timing for the render report."""
    def __init__(self): self.t0 = time.perf_counter(); self.steps = {}
    @contextlib.contextmanager
    def step(self, name):
        t = time.perf_counter()
        try: yield
        finally: self.steps[name] = round(self.steps.get(name, 0) + time.perf_counter() - t, 3)
    def total(self): return round(time.perf_counter() - self.t0, 3)

REQUIRED_FAMILIES = ("Inter", "TeX Gyre Heros Cn", "DejaVu Sans Mono")

def preflight(doc, brand=None):
    """92. Fail fast, with a message that names the file, when a font or an image the card needs is missing, instead of
    shipping a card typeset in a fallback face or with a hole where the art should be."""
    missing = [f"font file missing: {p} ({fam} {w})" for fam, w, p in FONT_FILES if fam in REQUIRED_FAMILIES and not pathlib.Path(p).exists()]
    c = doc.get("card") or {}
    def chk(path_s, where):
        if not path_s or re.match(r"^(https?:|data:)", str(path_s)): return
        q = pathlib.Path(str(path_s)[7:] if str(path_s).startswith("file://") else str(path_s))
        if not q.is_absolute(): q = HERE / q
        if not q.exists(): missing.append(f"asset missing: {where} -> {q}")
    h = c.get("hero") or {}
    chk(h.get("image"), "card.hero.image")
    for i, im in enumerate(h.get("images") or []): chk(im, f"card.hero.images[{i}]")
    chk((h.get("zoom") or {}).get("image"), "card.hero.zoom.image")
    chk((c.get("hero2") or {}).get("image"), "card.hero2.image")
    for nm in ("data_block", "secondary_block"):
        for i, ic in enumerate((c.get(nm) or {}).get("icons") or []): chk(ic, f"card.{nm}.icons[{i}]")
    for i, t in enumerate(c.get("context_tiles") or []): chk(t.get("icon"), f"card.context_tiles[{i}].icon")
    if brand and brand.get("monogram"): chk(brand["monogram"], "brand.monogram")
    if missing: raise RenderError("render preflight failed:\n  " + "\n  ".join(missing))

def split_citation(cit):
    """10. 'Title. Authors et al., Journal 2025 · PMID n' -> (title, rest). No title -> (None, cit)."""
    cit = (cit or "").strip()
    i = cit.find(" et al")
    pre = cit[:i] if i > 0 else cit
    k = pre.rfind(". ")
    if k > 0 and i > 0: return cit[:k + 1], cit[k + 2:]
    if i < 0:
        m = re.match(r"^(.+?\.)\s+(\S.*\d{4}.*)$", cit)
        if m and len(m.group(1)) > 12: return m.group(1), m.group(2)
    return None, cit

# ---------------------------------------------------------------- env
def _abs(p):
    if not p or re.match(r"^(https?:|data:|file:)", str(p)): return p
    q = pathlib.Path(p)
    return (q if q.is_absolute() else (HERE / q)).resolve().as_uri()

def forest_axis(b):
    """(lo, hi, scale) for a forest block. Ratio estimates use a log axis (scale 'log'), so 0.04 and 3.6 are both readable."""
    scale = b.get("scale") or "linear"
    vals = [it["value"] for it in b["items"]] + [v for it in b["items"] for v in (it.get("ci") or [])] + [b.get("null_value") or (1 if scale == "log" else 0)]
    lo, hi = b.get("axis_min"), b.get("axis_max")
    # 70: an explicit axis may widen the data range but never clip a CI: extend to cover every plotted value
    if lo is not None or hi is not None:
        dv = [v for v in vals if isinstance(v, (int, float)) and (scale != "log" or v > 0)]
        if dv:
            if lo is not None: lo = min(lo, min(dv) / (1.25 if scale == "log" else 1))
            if hi is not None: hi = max(hi, max(dv) * (1.25 if scale == "log" else 1))
    pos = [v for v in vals if isinstance(v, (int, float)) and v > 0]
    if scale == "linear" and b.get("null_value") == 1 and len(pos) == len([v for v in vals if isinstance(v, (int, float))]):
        scale = "log"                                   # 39: ratios (null at 1, all positive) always get the log axis
    if scale == "log":
        lo = lo if (lo and lo > 0) else min(pos) / 1.25
        hi = hi if (hi and hi > lo) else max(pos) * 1.25
    else:
        dv = [v for v in vals if isinstance(v, (int, float))]
        span = (max(dv) - min(dv)) or 1
        auto = lo is None and hi is None
        lo = min(dv) - 0.06 * span if lo is None else lo
        hi = max(dv) + 0.06 * span if hi is None else hi
        if auto:                                        # 38: pad, then snap the frame to nice tick values
            tk = nice_ticks(lo, hi, 5); lo, hi = tk[0], tk[-1]
        else:                                           # 38: an explicit axis never lets a whisker touch the frame
            pad = 0.03 * (hi - lo)
            if min(dv) < lo + pad: lo = min(dv) - pad
            if max(dv) > hi - pad: hi = max(dv) + pad
    return lo, hi, scale

RATIO_TICKS = (0.1, 0.2, 0.25, 0.33, 0.5, 0.67, 0.75, 1, 1.5, 2, 3, 4, 5, 8, 10, 20, 50, 100)

def log_ticks(lo, hi):
    """39: readable ticks for a ratio axis (0.5 / 1 / 2 ...), always including the null at 1 when it is in range."""
    out = [t for t in RATIO_TICKS if lo <= t <= hi]
    if len(out) > 6:
        keep = [t for t in out if t in (0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100)]
        out = keep if len(keep) >= 3 else out[::2]
    if len(out) < 3:                          # narrow range (0.67 to 1.12): linear-nice ticks, placed on the log axis
        out = [round(t, 6) for t in nice_ticks(lo, hi, 5) if lo <= t <= hi and t > 0]
    return out

def ax(x, lo, hi, scale="linear"):
    """position of x on the axis, 0-100 (%)."""
    import math
    if scale == "log":
        x = max(x, 1e-12)
        return round((math.log(x) - math.log(lo)) / ((math.log(hi) - math.log(lo)) or 1) * 100, 1)
    return round((x - lo) / ((hi - lo) or 1) * 100, 1)

def env():
    e = Environment(loader=FileSystemLoader(str(HERE)), autoescape=True)
    import hero_match as _hm; e.globals["hero_category"] = _hm.category
    e.globals.update(nice_step=nice_step, nice_ticks=nice_ticks, line_geom=line_geom, fmt=fmt, forest_axis=forest_axis, log_ticks=log_ticks)
    e.globals["sr_only_html"] = lambda card: Markup(typeset.sr_only_html(card))   # r2 (72)
    e.filters.update(mark=mark, boldnums=boldnums, bignum=bignum, typo=typo, fmt=fmt, col=col, ax=ax)
    return e

FONT_FILES = [
    ("Inter", 400, "/usr/share/fonts/opentype/inter/Inter-Regular.otf"), ("Inter", 600, "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf"),
    ("Inter", 700, "/usr/share/fonts/opentype/inter/Inter-Bold.otf"), ("Inter", 800, "/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf"),
    ("Inter Display", 800, "/usr/share/fonts/opentype/inter/InterDisplay-ExtraBold.otf"), ("Inter Display", 900, "/usr/share/fonts/opentype/inter/InterDisplay-Black.otf"),
    ("TeX Gyre Heros Cn", 700, "/usr/share/texmf/fonts/opentype/public/tex-gyre/texgyreheroscn-bold.otf"),
    ("DejaVu Sans Mono", 400, "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"), ("DejaVu Sans Mono", 700, "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"),
]

import brand_tokens as _bt
FONT_FILES = _bt.font_files(HERE / "brand.json") or FONT_FILES        # 99: font files listed in brand.json

def inline_fonts_css():
    # r2 (22): always embedded, subset (typeset.subset_fonts_css); a missing required face fails loudly
    return typeset.subset_fonts_css([f for f in FONT_FILES if pathlib.Path(f[2]).exists() or f[0] != "Inter Display"])

def _inline_fonts_css_full():
    css = []
    for fam, w, p in FONT_FILES:
        q = pathlib.Path(p)
        if not q.exists(): continue
        mime = "font/otf" if q.suffix == ".otf" else "font/ttf"
        b64 = base64.b64encode(q.read_bytes()).decode()
        css.append(f'@font-face{{font-family:"{fam}";font-weight:{w};src:url(data:{mime};base64,{b64}) format("{"opentype" if q.suffix == ".otf" else "truetype"}");}}')
    return "\n".join(css)

def trimmed(p, tol=18, pad=0.04):
    """Organ/food art for stat_row & band: crop to the subject and turn the paper background transparent, so the
    illustration sits directly on the card cream and fills its column (cached under assets/.trim/, deterministic)."""
    if not p or re.match(r"^(https?:|data:)", str(p)): return p
    src = pathlib.Path(str(p).replace("file://", "")) if str(p).startswith("file://") else pathlib.Path(p)
    if not src.is_absolute(): src = HERE / src
    if not src.exists(): return _abs(str(p))
    cache = HERE / "assets" / ".trim"; cache.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f"{src.resolve()}:{src.stat().st_mtime_ns}:{tol}".encode()).hexdigest()[:12]
    out = cache / f"{src.stem}.{key}.png"
    if not out.exists():
        from PIL import Image, ImageChops, ImageFilter
        im = Image.open(src).convert("RGB"); w, h = im.size
        corners = [im.getpixel(xy) for xy in ((2, 2), (w - 3, 2), (2, h - 3), (w - 3, h - 3))]
        bg = tuple(sorted(c[i] for c in corners)[2] for i in range(3))
        diff = ImageChops.difference(im, Image.new("RGB", im.size, bg)).convert("L")
        alpha = diff.point(lambda v: 0 if v < tol * 0.5 else 255 if v > tol * 2 else int((v - tol * 0.5) / (tol * 1.5) * 255))
        alpha = alpha.filter(ImageFilter.GaussianBlur(1.2))
        box = diff.point(lambda v: 255 if v > tol else 0).getbbox() or (0, 0, w, h)
        px, py = int((box[2] - box[0]) * pad), int((box[3] - box[1]) * pad)
        box = (max(0, box[0] - px), max(0, box[1] - py), min(w, box[2] + px), min(h, box[3] + py))
        rgba = im.copy(); rgba.putalpha(alpha); rgba.crop(box).save(out)
    return out.resolve().as_uri()

def _hero_img(p):
    """59: column heroes are cropped with a uniform margin and the paper tint made transparent (no visible box edge)."""
    import hero as _h
    return _h.hero_image(p) or _abs(p)

def render_html(doc, brand, fs=1.0, measure=False, hero_h=None, tweaks=None, theme="light", inline_fonts=False, variant_headline=None):
    c, ctx = derive(doc, brand, theme)
    if variant_headline: c["headline"] = variant_headline
    hero_fallback(c, doc.get("facts"))
    hero = c["hero"]
    if hero.get("image"): hero["image"] = _hero_img(hero["image"])
    if hero.get("images"): hero["images"] = [trimmed(i) for i in hero["images"]]
    if hero.get("zoom", {}).get("image"): hero["zoom"]["image"] = _abs(hero["zoom"]["image"])
    if c.get("hero2", {}).get("image"): c["hero2"]["image"] = _abs(c["hero2"]["image"])
    for b in (c.get("data_block"), c.get("secondary_block")):
        if b and b.get("icons"): b["icons"] = [trimmed(i) if b.get("type") == "stat_row" and i else _abs(i) for i in b["icons"]]
        if b and b.get("steps"):
            for st in b["steps"]:
                if isinstance(st, dict) and st.get("icon"): st["icon"] = _abs(st["icon"])
    for t in c.get("context_tiles") or []:
        if t.get("icon"): t["icon"] = _abs(t["icon"])
    ctx["overlay"] = __import__("render_gates").overlay_for(doc)        # gates: DRAFT mark / abstract-only tag
    placement = hero.get("placement", "left_column")
    ctx["wide_data"] = placement in ("none", "band", "shelf")            # the data block has the full card width (slope chart needs it)
    if hero_h is None: hero_h = BAND_MIN if placement in ("band", "shelf") else HERO_MIN
    if c.get("aspect") == "9:16": fs_base = 1.18
    else: fs_base = 1.0
    ctx["cit_title"], ctx["cit_rest"] = split_citation(c.get("citation"))
    lay = dict(DEFAULT_LAYOUT, **((tweaks or {}).get("layout") or {}))
    return env().get_template("template.html").render(c=c, x=ctx, brand=brand, fs=fs * fs_base, measure=measure, hero_h=hero_h, lay=lay,
                                                      tw=tweaks or {}, font_css=inline_fonts_css())

# ---------------------------------------------------------------- layout knobs (items 1-4, 6, 9)
# One dict travels in tweaks["layout"] (so fit()'s 4-tuple return and every caller stay unchanged):
#   variant  sparse | normal | dense   chosen from a first measurement BEFORE the fit loop
#   sp       spacing multiplier on the 8-px scale (0.75 dense ... 2.0 sparse)
#   dz       data-block zoom (charts, tables)     tg  tile growth (stat_tiles type + padding)
#   beats    cols | rows (one beat per row when 3 columns would run a beat past 3 lines)
DEFAULT_LAYOUT = {"variant": "normal", "sp": 1.0, "dz": 1.0, "tg": 0.0, "beats": "cols"}
SP_MIN, SP_MAX, DZ_MAX, TG_MAX = 0.75, 2.0, 1.22, 1.8
BAND_FREE = 48            # px of empty band above the takeaway that counts as healthy breathing room (item 8: max gap)
BEAT_LINE_PENALTY = 40    # px-equivalent cost per beat line beyond 3
VARIANT_SPARSE, VARIANT_DENSE = 0.80, 1.0     # first-measure content_h / canvas_h thresholds

def fit_score(m, h):
    """2. Fit score = overflow + empty-band penalty (+ long-beat and clipped-takeaway penalties). Lower is better; 0 = fills the
    frame, nothing overflows, no beat over 3 lines. The fit loop keeps the best-scoring state it has seen."""
    over = max(0, m["content_h"] - h)
    band = max(0, h - m["content_h"] - BAND_FREE)
    beat = sum(max(0, n - 3) for n in m["beat_lines"]) * BEAT_LINE_PENALTY
    take = max(0, m.get("take_over", 0) - 6) * 4
    clip = m.get("clip_px", 0) * 2
    return round(over * 10 + band + beat + take + clip, 1)

# ---------------------------------------------------------------- the fit loop
REFLOW_JS = r"""
(() => {
  // words -> client rects -> lines; returns {lines, lastWords, payoffAtLineStart}
  function lineInfo(el, payoffSel) {
    const words = []; const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    let node; while ((node = walker.nextNode())) {
      const t = node.textContent; const re = /\S+/g; let m;
      while ((m = re.exec(t))) { const r = document.createRange(); r.setStart(node, m.index); r.setEnd(node, m.index + m[0].length);
        const rc = r.getBoundingClientRect(); if (rc.width) words.push({top: Math.round(rc.top), left: rc.left, node}); }
    }
    const lines = []; for (const w of words) { const L = lines.find(l => Math.abs(l.top - w.top) < 4); if (L) { L.words.push(w); } else lines.push({top: w.top, words: [w]}); }
    lines.sort((a, b) => a.top - b.top);
    let payoffOK = true;   // the red payoff phrase begins at the start of a line (never splits mid-line into the next)
    if (payoffSel) { const p = el.querySelector(payoffSel); if (p) { const first = words.find(w => p.contains(w.node)); const L = first && lines.find(l => Math.abs(l.top - first.top) < 4);
      if (L) { const lineFirst = L.words.reduce((a, b) => a.left < b.left ? a : b); const inLine = L.words.filter(w => p.contains(w.node)).length; payoffOK = (lineFirst === first) || inLine === words.filter(w => p.contains(w.node)).length; } } }
    return {lines: lines.length, lastWords: lines.length ? lines[lines.length - 1].words.length : 0, payoffOK};
  }
  const out = {};
  for (const [key, sel, payoff] of [["h1", "h1", ".payoff"], ["dek", ".dek", null], ["take", ".takeaway .tx", null]]) {
    const el = document.querySelector(sel); if (!el) continue;
    el.style.maxWidth = ""; const base = lineInfo(el, payoff);
    let best = 100, bestInfo = base;
    const ok = i => i.lastWords !== 1 && i.lines <= base.lines;
    // pass 1: orphan-free at the same line count AND (h1) payoff starting a line; pass 2: orphan-free only
    let found = null;
    for (let w = 100; w >= 78 && !found; w -= 2) { el.style.maxWidth = w + "%"; const i = lineInfo(el, payoff); if (ok(i) && (!payoff || i.payoffOK)) found = [w, i]; }
    for (let w = 100; w >= 78 && !found; w -= 2) { el.style.maxWidth = w + "%"; const i = lineInfo(el, payoff); if (ok(i)) found = [w, i]; }
    if (found) { best = found[0]; bestInfo = found[1]; }
    el.style.maxWidth = best + "%"; out[key] = {w: best, lines: bestInfo.lines, orphan: bestInfo.lastWords === 1, payoffAtLineStart: bestInfo.payoffOK};
  }
  return out;
})()
"""
MEASURE_JS = r"""
(() => {
  const card = document.querySelector('.card');
  const h = r => Math.round(r.getBoundingClientRect().height);
  const blocks = [...card.children].map(e => [e.dataset.slot || e.className || e.tagName, h(e)]);
  const hero = document.querySelector('.herocol'); const data = document.querySelector('.datacol');
  const beats = [...document.querySelectorAll('.beat')].map(b => { const t = b.querySelector('.tx'); const lh = parseFloat(getComputedStyle(t).lineHeight); return Math.round(t.getBoundingClientRect().height / lh); });
  const tk = document.querySelector('.takeaway'), tx = tk && tk.querySelector('.tx');
  const take_over = tk && tx ? Math.max(0, Math.round(tx.scrollHeight - (tk.clientHeight - 50))) : 0;
  // px that block text / chart labels run past their block or the card (growth must never make this worse)
  const cr = card.getBoundingClientRect(); let clip_px = 0;
  for (const t of card.querySelectorAll('.block text, .block .delta, .block .cue, .block .v, .block .lbl')) {
    const r = t.getBoundingClientRect(); if (!r.width) continue; const bl = t.closest('.block'); const br = bl.getBoundingClientRect();
    clip_px += Math.max(0, r.right - Math.min(br.right, cr.right) - 1); }
  return {content_h: h(card), blocks, hero_h: hero ? h(hero) : 0, data_h: data ? h(data) : 0, beat_lines: beats, take_over, clip_px: Math.round(clip_px)};
})()
"""

def fit(doc, brand, html_path, log, theme="light", inline_fonts=False, gate=None):
    """Loop L2. Returns (fs, hero_h, tweaks, warnings). gate: (out, stem) enables the blocking 390px legibility check
    before any shrink below FS_LEGIBLE. tweaks carries the reflow widths plus tweaks["layout"] (variant, spacing, data-block
    growth, beats mode) and tweaks["_fit"] (score, band, ...) so the 4-tuple contract is unchanged.
    Order: (0) measure once and pick the variant sparse / normal / dense, (1) the original fit (hero column, font scale,
    dense tightening before any shrink), (2) FILL: spend the remaining empty band on a bigger data block, spacing and
    one-beat-per-row, keeping whichever state has the lowest fit_score (overflow + empty band + long beats)."""
    c = doc["card"]; w, h = CANVAS[c.get("aspect", "4:5")]
    placement = hero_fallback(copy.deepcopy(c), doc.get("facts"))["hero"].get("placement", "left_column")     # 73: no image -> 'none'
    if c.get("aspect") == "9:16" and placement != "none": placement = "band"
    has_hero = placement not in ("none",)
    hmin, hmax = (BAND_MIN, BAND_MAX) if placement in ("band", "shelf") else (HERO_MIN, HERO_MAX)
    if c.get("aspect") == "9:16": hmax = 26.0
    if c.get("aspect") == "1:1": hmax = min(hmax, 22.0)
    tiles = (c.get("data_block") or {}).get("type") == "stat_tiles"
    fs, hero_h, tweaks, warnings = 1.0, hmin, {}, []
    lay = dict(DEFAULT_LAYOUT)
    lo_target, hi_target = 0.93 * h, 0.995 * h
    def secant(target, ch, prev):
        """Next font scale: secant step from the last (fs, content_h) pair, else a proportional guess."""
        if prev and abs(ch - prev[1]) > 2 and abs(fs - prev[0]) > 1e-4:
            return fs + (target - ch) * (fs - prev[0]) / (ch - prev[1])
        return fs * (target / ch) ** 1.4
    with _pw() as p:
        b = _launch(p); pg = b.new_page(viewport={"width": w, "height": h})
        def probe(fs_, hh_, lay_, tag=""):
            html_path.write_text(render_html(doc, brand, fs_, measure=True, hero_h=hh_, theme=theme, inline_fonts=inline_fonts, tweaks={"layout": lay_}))
            pg.goto(html_path.resolve().as_uri()); pg.wait_for_load_state("networkidle")
            pg.evaluate("document.fonts.ready")
            rf = pg.evaluate(REFLOW_JS); m = pg.evaluate(MEASURE_JS)
            log.append({"iter": len(log), "fs": round(fs_, 3), "hero_h_em": round(hh_, 2), "content_h": m["content_h"], "canvas_h": h, "blocks": m["blocks"],
                        "reflow": rf, "layout": dict(lay_), "score": fit_score(m, h), "phase": tag})
            return m, rf
        last = None; prev = None; rf = {}; ok_fs = None
        # (0) variant from a first measurement, before any fitting decision
        m0, _ = probe(fs, hero_h, lay, "variant")
        r0 = m0["content_h"] / h
        lay["variant"] = "sparse" if r0 < VARIANT_SPARSE else "dense" if r0 > VARIANT_DENSE else "normal"
        lay["sp"] = {"sparse": 1.25, "normal": 1.0, "dense": 0.85}[lay["variant"]]
        for i in range(12):
            m, rf = probe(fs, hero_h, lay, "fit"); last = m; tweaks = rf
            ch = m["content_h"]
            # growing the type must not push a beat past 3 lines (the render gate holds such a card): fall back to the last scale that did not
            if any(n > 3 for n in m["beat_lines"]):
                if ok_fs is not None and fs > ok_fs + 1e-6:
                    fs = ok_fs; m, rf = probe(fs, hero_h, lay, "fit:beats"); last = m; tweaks = rf; break
            else: ok_fs = fs
            if placement in ("left_column", "right_column") and has_hero and m["hero_h"] < m["data_h"] - 4 and hero_h < hmax and ch <= hi_target:
                hero_h = min(hmax, m["data_h"] / (16 * fs)); continue   # free: fill the column beside the data block
            if lo_target <= ch <= hi_target: break
            if ch > hi_target:                                      # overflow
                over = ch - hi_target
                if lay["beats"] == "rows": lay["beats"] = "cols"; continue          # tighten before shrinking anything
                if fs > FS_LEGIBLE + 1e-6: pass          # type above the legible scale is the cheapest thing to give back
                elif lay["sp"] > SP_MIN + 1e-6: lay["sp"] = max(SP_MIN, lay["sp"] - max(0.25, over / 140)); continue
                elif lay["dz"] > 1 or lay["tg"] > 0: lay["dz"], lay["tg"] = 1.0, 0.0; continue
                if has_hero and hero_h > hmin and m["hero_h"] >= m["data_h"]:   # hero taller than data: shrink hero first
                    hero_h = max(hmin, hero_h - over / (16 * fs)); continue
                want = secant(0.99 * h, ch, prev); prev = (fs, ch)
                if gate and want < FS_LEGIBLE:
                    cand = max(want, FS_FLOOR)
                    html_path.write_text(render_html(doc, brand, cand, hero_h=hero_h, theme=theme, inline_fonts=inline_fonts, tweaks={"layout": lay}))
                    lg = legibility(html_path, gate[0], gate[1], w, h, pw=p)
                    if lg.get("missing"):                           # shrinking would cost legibility: do not shrink
                        fs = max(fs, FS_LEGIBLE) if fs >= FS_LEGIBLE else fs
                        warnings.append("trim copy: " + trim_suggestion(m) + f" (shrinking to fs {cand:.2f} makes {lg['missing']} unreadable at 390px)")
                        break
                if want < FS_FLOOR:
                    if fs > FS_FLOOR: fs = FS_FLOOR; continue
                    warnings.append("trim copy: " + trim_suggestion(m)); break
                fs = min(want, fs)
            else:                                                   # slack
                slack = lo_target - ch
                if has_hero and hero_h < hmax:
                    # a column hero shorter than the data column grows for free up to it; beyond that, it absorbs the slack
                    base_px = max(m["hero_h"], m["data_h"]) if placement in ("left_column", "right_column") else m["hero_h"]
                    hero_h = min(hmax, (base_px + slack) / (16 * fs)); continue
                if fs < FS_CEIL:
                    want = secant(0.965 * h, ch, prev); prev = (fs, ch)
                    fs = min(FS_CEIL, max(want, fs)); continue
                break                                               # leave whitespace (the spacer absorbs it)
        # (2) FILL: items 1-4, 6. Spend the empty band above the takeaway on the data block, spacing and beat layout.
        score = fit_score(last, h)
        best = {"score": score, "lay": dict(lay), "hero_h": hero_h, "rf": rf, "m": last}
        stuck = set()
        for _ in range(12):
            band = h - best["m"]["content_h"]
            mb = best["m"]
            wants_rows = best["lay"]["beats"] == "cols" and any(n > 3 for n in mb["beat_lines"]) and "rows" not in stuck
            if band <= BAND_FREE and not wants_rows: break
            order = (["rows"] if wants_rows and band > 60 else []) + [k for k in ("grow", "sp") if k not in stuck]
            if not order: break
            kind = order[0]; improved = False
            for fac in (1.0, 0.5, 0.25):
                cand = dict(best["lay"])
                if kind == "rows": cand["beats"] = "rows"
                elif kind == "grow":
                    if tiles:
                        if cand["tg"] >= TG_MAX - 1e-6: break
                        cand["tg"] = round(min(TG_MAX, cand["tg"] + max(0.15, fac * 0.7 * band / 110)), 3)
                    else:
                        if cand["dz"] >= DZ_MAX - 1e-6: break
                        cand["dz"] = round(min(DZ_MAX, cand["dz"] * (1 + fac * 0.7 * band / max(mb["data_h"], 200))), 3)
                else:
                    if cand["sp"] >= SP_MAX - 1e-6: break
                    cand["sp"] = round(min(SP_MAX, cand["sp"] + max(0.1, fac * 0.5 * band / 110)), 3)
                hh2 = best["hero_h"]
                m2, rf2 = probe(fs, hh2, cand, "fill:" + kind)
                if has_hero and placement in ("left_column", "right_column") and m2["hero_h"] < m2["data_h"] - 4 and hh2 < hmax:
                    hh2 = min(hmax, m2["data_h"] / (16 * fs)); m2, rf2 = probe(fs, hh2, cand, "fill:" + kind + "+hero")
                sc2 = fit_score(m2, h)
                if sc2 < best["score"] - 0.5 and m2["content_h"] <= h:
                    best = {"score": sc2, "lay": cand, "hero_h": hh2, "rf": rf2, "m": m2}; improved = True; break
            if not improved: stuck.add(kind)
        lay, hero_h, tweaks, last = best["lay"], best["hero_h"], best["rf"], best["m"]
        tweaks = dict(tweaks); tweaks["layout"] = lay
        tweaks["_fit"] = {"score": best["score"], "band_px": max(0, h - last["content_h"]), "content_h": last["content_h"], "canvas_h": h,
                          "variant": lay["variant"], "beat_lines": last["beat_lines"], "take_over": last.get("take_over", 0)}
        if last and last.get("take_over", 0) > 6:
            warnings.append(f"takeaway overflows its fixed two-line bar by {last['take_over']}px: the copy is wrong (shorten it); not shrunk")
        if last and any(n > 3 for n in last["beat_lines"]):
            warnings.append(f"beat detail runs long: lines per beat = {last['beat_lines']} (max 3 wanted); shorten the beat copy")
        if h - last["content_h"] > 140:
            warnings.append(f"empty band of {h - last['content_h']}px above the takeaway: content-limited (data block, spacing and type are at their caps)")
        _release(b, pg)
    return fs, hero_h, tweaks, warnings

def trim_suggestion(m):
    """Which block to trim when the font floor is hit: the tallest text slot."""
    textish = {"h1": "headline", "dek": "dek", "beats": "beats", "boundary": "evidence_boundary", "ctx": "context_tiles", "takeaway": "takeaway", "mid": "data block / hero"}
    cands = [(hh, textish.get(n.split()[0], n)) for n, hh in m["blocks"] if n.split()[0] in textish]
    if not cands: return "copy"
    return max(cands)[1] + " (tallest text slot)"

# ---------------------------------------------------------------- outputs
LAYOUT_JS = r"""
(() => {
  const r = e => e && e.getBoundingClientRect();
  const inter = (a, b) => a && b && a.width > 0 && a.height > 0 && b.width > 0 && b.height > 0 &&
      a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1;
  const foot = r(document.querySelector('.foot')), card = r(document.querySelector('.card'));
  const out = {hero_sliver: false, overlaps: []};
  const hc = document.querySelector('.herocol');
  if (hc && card) { const hr = r(hc); if (hr.width < 0.2 * card.width) out.hero_sliver = Math.round(hr.width); }
  for (const sel of ['.hero .cap', '.hero img', '.hero svg.ph', '.herocol']) for (const el of document.querySelectorAll(sel)) {
    if (inter(r(el), foot)) out.overlaps.push(sel + ' overlaps .foot');
    const d = document.querySelector('.datacol'); if (sel === '.hero .cap' && d && inter(r(el), r(d))) out.overlaps.push('.hero .cap overlaps .datacol');
  }
  const tk = r(document.querySelector('.takeaway'));
  for (const el of document.querySelectorAll('.hero .cap')) if (inter(r(el), tk)) out.overlaps.push('.hero .cap overlaps .takeaway');
  return out;
})()
"""

QUALITY_JS = r"""
(() => {
  const card = document.querySelector('.card'); const cr = card.getBoundingClientRect();
  const R = e => e.getBoundingClientRect();
  const out = {clipped: [], outside: [], overlaps: [], min_font_px: null, min_font_text: null, text_nodes: 0, band_px: null, content_bottom: null};
  const label = e => { const s = e.closest('[data-slot]'); const cls = (typeof e.className === 'string' && e.className.trim()) ? '.' + e.className.trim().split(/\s+/)[0] : e.tagName.toLowerCase();
    return (s ? s.dataset.slot : '?') + ' ' + cls; };
  // text node boxes
  const tw = document.createTreeWalker(card, NodeFilter.SHOW_TEXT); const items = []; let n;
  while ((n = tw.nextNode())) {
    const t = n.textContent.trim(); if (!t) continue; const el = n.parentElement;
    if (el.closest('script,style,defs,clipPath,.sr-only,.gate-mark,.gate-tag')) continue;
    const cs = getComputedStyle(el); if (cs.visibility === 'hidden' || cs.display === 'none' || parseFloat(cs.opacity) === 0) continue;
    const rg = document.createRange(); rg.selectNodeContents(n); const rects = [...rg.getClientRects()].filter(q => q.width >= 1 && q.height >= 1); if (!rects.length) continue;
    if (el.closest('.ct')) continue;     // ellipsis-truncated citation title: its glyph box is allowed to exceed the clip
    const px = parseFloat(cs.fontSize) * (el.closest('svg') ? (R(el.closest('svg')).width / (el.closest('svg').viewBox.baseVal.width || R(el.closest('svg')).width)) : 1);
    const lhp = parseFloat(cs.lineHeight);       // glyph boxes taller than the leading are not an overlap: trim each rect to the line box
    const adj = r => { const pad = lhp && lhp < r.height ? (r.height - lhp) / 2 : 0; return {left: r.left, right: r.right, width: r.width, top: r.top + pad, bottom: r.bottom - pad, height: r.height - 2 * pad}; };
    for (const r of rects) items.push({el, r: adj(r), t, px}); out.text_nodes++;
    if (!out.min_font_px || px < out.min_font_px) { out.min_font_px = +px.toFixed(2); out.min_font_text = t.slice(0, 40) + ' [' + label(el) + ']'; }
    for (const r of rects) if (r.right > cr.right + 1 || r.left < cr.left - 1 || r.bottom > cr.bottom + 1) { out.outside.push(label(el) + ': "' + t.slice(0, 30) + '" leaves the card'); break; }
  }
  // clipped text: an element that scrolls past its own box and hides the rest
  for (const el of card.querySelectorAll('*')) {
    if (el.closest('svg') || el.closest('.sr-only') || !el.childNodes.length) continue;
    const cs = getComputedStyle(el); const clips = ['hidden', 'clip'].includes(cs.overflowX) || ['hidden', 'clip'].includes(cs.overflowY);
    if (!clips || el === card) continue;
    if (el.scrollWidth > el.clientWidth + 2 && cs.textOverflow !== 'ellipsis') out.clipped.push(label(el) + ': content is ' + (el.scrollWidth - el.clientWidth) + 'px wider than its box');
    if (el.scrollHeight > el.clientHeight + 3 && !el.matches('.card')) out.clipped.push(label(el) + ': content is ' + (el.scrollHeight - el.clientHeight) + 'px taller than its box');
  }
  // text that overflows the block / column that should contain it (e.g. a chart note running out of its tile)
  for (const it of items) {
    const box = it.el.closest('.block, .tile, .tile2, .beat, .takeaway, .foot .cit'); if (!box) continue;
    const br = R(box); if (it.r.right > br.right + 2 && !it.el.closest('svg')) out.outside.push(label(it.el) + ': "' + it.t.slice(0, 30) + '" runs ' + Math.round(it.r.right - br.right) + 'px past its box');
  }
  for (const svg of card.querySelectorAll('.block svg')) { const sr = R(svg); const blk = svg.closest('.block'); const br = R(blk);
    for (const tx of svg.querySelectorAll('text')) { const r = R(tx); if (r.width && r.right > br.right + 2) out.outside.push(label(tx) + ': chart label "' + tx.textContent.slice(0, 24) + '" runs ' + Math.round(r.right - br.right) + 'px past the block'); } }
  // overlapping text (different elements whose glyph boxes cross)
  const inter = (a, b) => { const w = Math.min(a.right, b.right) - Math.max(a.left, b.left), h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
    return w > 1 && h > 1 ? w * h : 0; };
  for (let i = 0; i < items.length; i++) for (let j = i + 1; j < items.length; j++) {
    const A = items[i], B = items[j]; if (A.el === B.el || A.el.contains(B.el) || B.el.contains(A.el)) continue;
    const ov = inter(A.r, B.r); if (!ov) continue;
    const small = Math.min(A.r.width * A.r.height, B.r.width * B.r.height);
    if (ov / small > 0.25) out.overlaps.push('text overlap: "' + A.t.slice(0, 20) + '" [' + label(A.el) + '] x "' + B.t.slice(0, 20) + '" [' + label(B.el) + ']');
  }
  const tk = document.querySelector('.takeaway'), sp = document.querySelector('.spacer');
  if (sp) out.band_px = Math.round(R(sp).height); out.card_h = Math.round(cr.height);
  const last = [...card.children].filter(e => !e.matches('.spacer, .takeaway, .foot, .sr-only, .gate-mark, .gate-tag')).pop(); if (last) out.content_bottom = Math.round(R(last).bottom - cr.top);
  const tx = tk && tk.querySelector('.tx'); if (tk && tx) out.take_over = Math.max(0, Math.round(tx.scrollHeight - tk.clientHeight));
  const ft = document.querySelector('.foot'); if (ft) { const f = R(ft); out.foot_bottom_gap = Math.round(cr.bottom - f.bottom); }
  const ct = document.querySelector('.foot .cit'); if (ct) { out.cit_h = Math.round(R(ct).height); out.foot_lines = Math.round(R(ct).height / parseFloat(getComputedStyle(ct).lineHeight)); }
  return out;
})()
"""
PHONE_MIN_PX = 4.0          # fail below this effective px on a 390 px phone render (1080 -> 390 = x0.361); the lower type floor is r2's (typography)

def layout_report(html_path, w=1080, h=1350, widths=(1080, 390), pw=None):
    """77. Layout metrics + problems at every width. The card is laid out once at its canvas width; the 390 pass checks what a
    phone shows: the same boxes scaled by 390/1080, so text must still be >= PHONE_MIN_PX there and nothing may be clipped.
    Returns {"problems": [...], "metrics": {...}, "per_width": {...}}; problems empty = clean."""
    probs, per = [], {}
    with _pw(pw) as p:
        b, pg = _page(p, w, h, 1)
        pg.goto(pathlib.Path(html_path).resolve().as_uri()); pg.wait_for_load_state("networkidle"); pg.evaluate("document.fonts.ready")
        r = pg.evaluate(LAYOUT_JS); q = pg.evaluate(QUALITY_JS); _release(b, pg)
    base = list(dict.fromkeys(r["overlaps"]))
    if r["hero_sliver"] is not False: base.append(f"hero column collapsed to a {r['hero_sliver']}px sliver")
    for wd in widths:
        k = wd / w; pr = [] if wd != w else list(base)
        pr += [f"[{wd}px] clipped: {m}" for m in q["clipped"]]
        pr += [f"[{wd}px] outside: {m}" for m in q["outside"]]
        pr += [f"[{wd}px] {m}" for m in q["overlaps"]]
        if (q.get("take_over") or 0) > 6: pr.append(f"[{wd}px] takeaway text overflows its bar by {q['take_over']}px")
        if q.get("card_h") and q.get("content_bottom") and q["content_bottom"] > q["card_h"] - 4: pr.append(f"[{wd}px] content runs to the card bottom")
        eff = (q["min_font_px"] or 99) * k
        if wd != w and eff < PHONE_MIN_PX: pr.append(f"[{wd}px] smallest text {q['min_font_px']}px renders at {eff:.1f}px (< {PHONE_MIN_PX}px): {q['min_font_text']}")
        if wd == w and (q.get("foot_lines") or 0) > 4: pr.append(f"[{wd}px] footer wraps to {q['foot_lines']} lines")
        per[wd] = {"problems": pr, "min_font_effective_px": round(eff, 2)}
        probs += pr
    return {"problems": list(dict.fromkeys(probs)), "metrics": q, "per_width": per}

def layout_check(html_path, w=1080, h=1350, widths=(1080, 390)):
    """74 + 77. Layout check on a rendered card at 1080 and 390: the hero column must not collapse to a sliver, nothing may
    overlap (hero caption vs footer / data / takeaway, text vs text), nothing may be clipped or run outside its block or the
    card, and the smallest text must stay legible on a phone. Returns a list of problem strings (empty = clean)."""
    return layout_report(html_path, w, h, widths)["problems"]

def _page(p, w, h, scale):
    b = _launch(p); pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=scale); return b, pg

def to_png(html_path, png_path, w, h, scale, pdf_path=None, carousel_dir=None):
    with _pw() as p:
        b, pg = _page(p, w, h, scale)
        pg.goto(html_path.resolve().as_uri()); pg.wait_for_load_state("networkidle"); pg.evaluate("document.fonts.ready")
        pg.locator(".card").screenshot(path=str(png_path), animations="disabled")
        if pdf_path:
            pg.pdf(path=str(pdf_path), width=f"{w}px", height=f"{h}px", print_background=True, page_ranges="1")
        if carousel_dir:
            carousel_dir.mkdir(parents=True, exist_ok=True)
            for i, slot in enumerate(["hd", "dek", "beats", "mid", "ctx", "boundary", "takeaway"]):
                loc = pg.locator(f'[data-slot="{slot}"]')
                if loc.count():
                    sp = carousel_dir / f"{i:02d}_{slot}.png"; loc.first.screenshot(path=str(sp)); _stamp(sp, scale)
        _release(b, pg)
    _png_meta(png_path)

SITE = None
def _site():
    global SITE
    if SITE is None:
        try: SITE = json.loads((HERE / "brand.json").read_text()).get("site") or ""
        except Exception: SITE = ""
    return SITE

def _stamp(path, scale=2):
    """Every carousel slide carries the site mark bottom-right (slides are crops without the footer)."""
    site = _site()
    if not site: return
    from PIL import Image, ImageDraw, ImageFont
    im = Image.open(path).convert("RGB"); pad = int(14 * scale)
    band = Image.new("RGB", (im.width, im.height + pad * 3), "#f8f6f1"); band.paste(im, (0, 0))
    d = ImageDraw.Draw(band)
    try: f = ImageFont.truetype("DejaVuSansMono-Bold.ttf", int(11 * scale))
    except Exception: f = ImageFont.load_default()
    w = d.textlength(site, font=f)
    d.text((band.width - w - pad, im.height + pad), site, fill="#c8102e", font=f)
    band.save(path); _png_meta(path)

META_CTX = {}          # set by main() / the pipeline: facts hash, card hash, gate and render version, PMID (render_meta.context_for)

def _png_meta(path):
    """Embed the site + byline + facts/card hash, gate and render version, PMID in PNG text chunks (byte level: pixels and a
    C2PA manifest are never touched), so reposts stay attributable and traceable."""
    import render_meta
    if str(path).endswith(".png"): render_meta.stamp_png(path, site=_site() or None, ctx=META_CTX)

# ---------------------------------------------------------------- legibility gate (phone width) + read-back hook
NUM_RE = re.compile(r"[\u2212+\-]?\d[\d,]*(?:\.\d+)?")

def expected_numbers(html_path, pw=None):
    """Every number the reader must be able to read: the DOM text of the rendered card (deterministic)."""
    with _pw(pw) as p:
        b = _launch(p); pg = b.new_page(viewport={"width": 1080, "height": 1350})
        pg.goto(html_path.resolve().as_uri()); pg.wait_for_load_state("networkidle")
        txt = pg.evaluate("""[...document.querySelectorAll('h1,.dek,.stats-line,.beat .tx,.block .big,.block .v,.block .val,.block .est,.block .t,.block .vt,.pdp .s,.funnel .lvl,.leg,.tile,.takeaway')].map(e=>e.innerText).join('\\n')""")
        _release(b, pg)
    return sorted({n.replace("\u2212", "-").replace(",", "") for n in NUM_RE.findall(txt)}, key=lambda v: (len(v), v))

SLOT_JS = r"""
(nums) => {
  const norm = t => t.replace(/[\u2212\u2012\u2013]/g, '-').replace(/,/g, '');
  const out = {};
  const walker = document.createTreeWalker(document.querySelector('.card'), NodeFilter.SHOW_TEXT);
  const nodes = []; let n; while ((n = walker.nextNode())) nodes.push(n);
  for (const num of nums) {
    const bare = num.replace(/^[+-]/, '');
    const re = new RegExp('(^|[^\\d.])[+-]?' + bare.replace(/\./g, '\\.') + '(?![\\d]|\\.\\d)');
    const hit = nodes.find(t => re.test(norm(t.textContent)));
    if (!hit) { out[num] = null; continue; }
    const el = hit.parentElement; const slot = el.closest('[data-slot]');
    const cls = []; for (let e = el; e && e !== slot && cls.length < 3; e = e.parentElement) if (e.className && typeof e.className === 'string') cls.unshift('.' + e.className.trim().split(/\s+/)[0]);
    const cr = document.querySelector('.card').getBoundingClientRect(), rr = el.getBoundingClientRect();
    out[num] = {slot: slot ? slot.dataset.slot : '?', el: cls.join(' '), px: parseFloat(getComputedStyle(el).fontSize), box: [rr.left - cr.left, rr.top - cr.top, rr.right - cr.left, rr.bottom - cr.top]};
  }
  return out;
}
"""
SLOT_NAMES = {"hd": "headline", "dek": "dek", "stats": "stats_line", "beats": "beats", "mid": "data_block", "ctx": "context_tiles",
              "boundary": "evidence_boundary", "takeaway": "takeaway", "foot": "citation", "top": "eyebrow", "data": "data_block"}

def locate_numbers(html_path, nums, pw=None):
    """Missing number -> {slot, el, px}: which card slot carries it (for the 'trim copy' report)."""
    if not nums: return {}
    with _pw(pw) as p:
        b = _launch(p); pg = b.new_page(viewport={"width": 1080, "height": 1350})
        pg.goto(html_path.resolve().as_uri()); pg.wait_for_load_state("networkidle")
        r = pg.evaluate(SLOT_JS, nums); _release(b, pg)
    return r

def illegible_report(lg):
    """One 'trim copy'-style line per slot: which numbers OCR missed at 390px and where they live."""
    by = {}
    for num, loc in (lg.get("where") or {}).items():
        key = SLOT_NAMES.get((loc or {}).get("slot"), (loc or {}).get("slot") or "?")
        by.setdefault(key, []).append(f"{num}" + (f" in {loc['el']} @{loc['px']:.0f}px" if loc else ""))
    return [f"illegible @390px — trim copy: {slot} (give its numbers room; type is not shrunk): " + "; ".join(v) for slot, v in by.items()]

def legibility(html_path, out, stem, w, h, width=390, pw=None):
    """Item 16: render the card as a phone shows it (390 px wide), OCR it, check every number survives.
    The OCR read-back is deterministic (tesseract). A VLM read-back is a hook: set READBACK_CMD to a command that
    takes the PNG path and the JSON manifest path and exits non-zero on failure (critique.py can play that role)."""
    png = out / f"{stem}.{width}.png"

    def _shoot(p):
        b, pg = _page(p, w, h, width / w)
        pg.goto(html_path.resolve().as_uri()); pg.wait_for_load_state("networkidle"); pg.evaluate("document.fonts.ready")
        pg.locator(".card").screenshot(path=str(png))
        bx = pg.evaluate("""(() => { const c = document.querySelector('.card').getBoundingClientRect();
          return [...document.querySelectorAll('.card [data-slot], .card .block, .card .beat')].map(e => { const r = e.getBoundingClientRect();
            return [r.left - c.left, r.top - c.top, r.right - c.left, r.bottom - c.top]; }).filter(r => r[2] - r[0] > 4 && r[3] - r[1] > 4); })()""")
        slotbox.update(pg.evaluate("""(() => { const c = document.querySelector('.card').getBoundingClientRect(); const o = {};   // r2 (69): headline / takeaway read-back
          for (const [k, sel] of [['headline', 'h1'], ['takeaway', '.takeaway .tx']]) { const e = document.querySelector(sel); if (!e) continue; const r = e.getBoundingClientRect();
            o[k] = {box: [r.left - c.left, r.top - c.top, r.right - c.left, r.bottom - c.top], text: e.innerText}; } return o; })()"""))
        _release(b, pg)
        return bx
    slotbox = {}
    with _pw(pw) as p:                       # session / fit()'s Playwright / a fresh one (a nested sync_playwright fails)
        boxes = _shoot(p)
    want = expected_numbers(html_path, pw=pw)
    rep_ = {"png": str(png), "width": width, "expected": want, "ocr": None, "missing": None, "readback_cmd": None}
    try:
        import pytesseract
        from PIL import Image
        im = Image.open(png).convert("L")
        im = im.resize((im.width * 3, im.height * 3), Image.LANCZOS)   # OCR at 3x; the eye at 1x is the target, OCR is a lower bound
        raw = pytesseract.image_to_string(im, config="--psm 3") + "\n" + pytesseract.image_to_string(im, config="--psm 11")
        # per-region pass: same 390px pixels, cropped to each slot / block / beat, so whole-page layout analysis
        # (which trips on charts beside text) is not mistaken for illegible type
        k = width / w * 3
        for x0, y0, x1, y1 in boxes:
            crop = im.crop((max(0, int(x0 * k) - 6), max(0, int(y0 * k) - 6), min(im.width, int(x1 * k) + 6), min(im.height, int(y1 * k) + 6)))
            raw += "\n" + pytesseract.image_to_string(crop, config="--psm 6") + "\n" + pytesseract.image_to_string(crop, config="--psm 11")
        raw = re.sub("[\u2012\u2013\u2014\u2015\u2212]", "-", raw)
        got = {n.replace(",", "") for n in NUM_RE.findall(raw)}
        got |= {g.lstrip("+-") for g in got}
        rep_["ocr"] = sorted(got)
        rep_["missing"] = [n for n in want if n not in got and n.lstrip("+-") not in got]
        if rep_["missing"]: rep_["where"] = locate_numbers(html_path, rep_["missing"], pw=pw)
        if rep_["missing"]:                                  # r2: second chance, per number: OCR the element's own crop (single line, 4x, sharpened)
            from PIL import ImageFilter, ImageOps
            base = Image.open(png).convert("L"); still = []; dot_tol = []
            for n in rep_["missing"]:
                bx = ((rep_.get("where") or {}).get(n) or {}).get("box"); ok = False
                if bx:
                    kk = width / w
                    cr_ = base.crop((max(0, int(bx[0] * kk) - 4), max(0, int(bx[1] * kk) - 4), min(base.width, int(bx[2] * kk) + 4), min(base.height, int(bx[3] * kk) + 4)))
                    cr_ = ImageOps.autocontrast(cr_.resize((cr_.width * 5, cr_.height * 5), Image.LANCZOS)).filter(ImageFilter.SHARPEN)
                    for psm in (7, 6, 13):
                        t = re.sub("[\u2012\u2013\u2014\u2015\u2212]", "-", pytesseract.image_to_string(cr_, config=f"--psm {psm}"))
                        toks = {g.replace(",", "").lstrip("+-") for g in NUM_RE.findall(t)}
                        if n.lstrip("+-") in toks: ok = True; break
                        # tesseract drops the decimal point of a small leading-zero number ('0.049' read as '0049'): the digits are all there
                        nb = n.lstrip("+-")
                        if nb.startswith("0.") and nb.replace(".", "") in toks: ok = True; dot_tol.append(n); break
                if not ok: still.append(n)
            rep_["recovered_by_crop"] = [n for n in rep_["missing"] if n not in still]; rep_["missing"] = still
            if dot_tol: rep_["recovered_dot_tolerance"] = dot_tol
        rep_["readback"], rep_["readback_failures"] = {}, []
        for key, v in slotbox.items():                       # r2 (69): OCR the headline and takeaway crops, compare to the card text
            x0, y0, x1, y1 = v["box"]
            crop = im.crop((max(0, int(x0 * k) - 6), max(0, int(y0 * k) - 6), min(im.width, int(x1 * k) + 6), min(im.height, int(y1 * k) + 6)))
            txt = pytesseract.image_to_string(crop, config="--psm 6") + "\n" + pytesseract.image_to_string(crop, config="--psm 4")
            rc = typeset.readback_compare(txt, v["text"])
            rep_["readback"][key] = rc
            if not rc["pass"]: rep_["readback_failures"].append(f"{key}: OCR found {rc['hit']:.0%} of the words; missing {rc['missing'][:8]}")
    except Exception as e:                                          # no tesseract: leave the gate open, say so
        rep_["ocr_error"] = str(e)
    rep_["floor"] = typeset.font_floor(html_path, pw=pw)       # r2 (66-68): number-bearing text below the px floor
    rep_["pass"], rep_["failing"] = typeset.legibility_gate(rep_)
    cmd = os.environ.get("READBACK_CMD")
    man = out / f"{stem}.legibility.json"; man.write_text(json.dumps(rep_, indent=1))
    if cmd:
        r = subprocess.run(cmd.split() + [str(png), str(man)], capture_output=True, text=True)
        rep_["readback_cmd"] = {"cmd": cmd, "rc": r.returncode, "out": r.stdout[-2000:]}
        man.write_text(json.dumps(rep_, indent=1))
    return rep_

def variants_png(doc, brand, out, stem, w, h, scale, theme, inline_fonts):
    """--variants: 3 headline candidates side by side (card.headline_candidates, else the headline alone)."""
    cands = doc["card"].get("headline_candidates") or [doc["card"]["headline"]]
    paths = []
    with _pw() as p:
        b, pg = _page(p, w, h, 1)
        for i, hc in enumerate(cands[:3]):
            hp = out / f"{stem}.variant{i}.html"
            hp.write_text(render_html(doc, brand, 1.0, hero_h=None, theme=theme, inline_fonts=inline_fonts, variant_headline=hc))
            pg.goto(hp.resolve().as_uri()); pg.wait_for_load_state("networkidle"); pg.evaluate("document.fonts.ready")
            pp = out / f"{stem}.variant{i}.png"; pg.locator(".card").screenshot(path=str(pp)); paths.append(pp)
        _release(b, pg)
    from PIL import Image
    ims = [Image.open(q) for q in paths]; gap = 24
    sheet = Image.new("RGB", (sum(i.width for i in ims) + gap * (len(ims) + 1), ims[0].height + 2 * gap), "#2a2a2a")
    x = gap
    for im in ims: sheet.paste(im, (x, gap)); x += im.width + gap
    sp = out / f"{stem}.variants.png"; sheet.save(sp); return sp

EXIT_LAYOUT, EXIT_ASSET = 4, 5

EXIT_HELD = 6

def default_args(**kw):
    """The CLI defaults as a namespace, for callers (pipeline.s_render, tests) that render without argparse."""
    d = dict(brand=str(HERE / "brand.json"), scale=None, target=None, pdf=False, theme="light", inline_fonts=False, carousel=False,
             variants=False, fs=None, allow_illegible=False, strict_layout=False, gate_inputs=None, allow_gate_errors=False, finalize=False)
    d.update(kw); return argparse.Namespace(**d)

def _opt(a, name, default=None):
    return getattr(a, name, default)

def _gate_inputs(doc, a, run_dir=None):
    """Audit fatal / verify verdict / retracted for the DRAFT and refuse decision: --gate-inputs (json file or a run dir), else
    doc['gate_inputs'] (pipeline), else the pipeline.report.json next to the card."""
    import render_gates as RG
    gi = _opt(a, "gate_inputs")
    if gi:
        return RG.inputs_from_run(gi) if pathlib.Path(gi).is_dir() else json.loads(pathlib.Path(gi).read_text())
    if doc.get("gate_inputs"): return doc["gate_inputs"]
    return RG.inputs_from_run(run_dir) if run_dir else {}

def render_doc(doc, stem, a, out, tm=None, brand=None, run_dir=None):
    """One doc -> html, png(s), fit.json, gates report and ONE render report (<stem>.render.json: timings, fit score, empty band,
    layout problems at 1080 and 390, min font, OCR misses, fonts, png sha256).  Order: preflight, gate decision (DRAFT / refuse) BEFORE
    anything is drawn, fit, png, alt text + metadata, layout report, post-render DOM gates, legibility gate, report.
    Returns (exit_code, info); info carries the pieces the pipeline and render_gate.finalize need."""
    import render_gates as RG, render_meta as RM, typeset
    tm = tm or Timer(); out = pathlib.Path(out); out.mkdir(parents=True, exist_ok=True)
    brand = brand or json.loads(pathlib.Path(a.brand).read_text())
    preset = TARGETS.get(a.target, {}); scale = a.scale or preset.get("scale", 2); want_pdf = a.pdf or preset.get("pdf", False)
    hp = out / f"{stem}.html"; pp = out / f"{stem}.png"
    log, warnings, tweaks, hero_h = [], [], {}, None
    info = {"stem": stem, "html": hp, "png": pp}
    with tm.step("preflight"): preflight(doc, brand)                  # 92: missing font / asset -> RenderError before any work
    dec = RG.apply(doc, _gate_inputs(doc, a, run_dir))                 # 73-76: DRAFT watermark / abstract-only tag / refusal, before drawing
    info["decision"] = dec
    if dec.refuse:                                                     # 75: a retracted paper gets a notice, never a card
        np_ = RG.write_notice(doc, out, stem, dec.refuse_reason)
        print("REFUSED:", dec.refuse_reason, "->", np_); info["notice"] = np_
        return EXIT_GATE, info
    META_CTX.clear(); META_CTX.update(RM.context_for(doc, dec.report, dec))
    if a.fs: fs = a.fs
    else:
        with tm.step("fit"): fs, hero_h, tweaks, warnings = fit(doc, brand, hp, log, a.theme, a.inline_fonts, gate=(out, stem))
    _c, ctx = derive(doc, brand)
    planner_override = ((_c.get("data_block") or {}).get("geo") or {}).get("planner_note")      # r4 item 50
    if ctx["tone_warning"]: warnings.append(ctx["tone_warning"])
    hp.write_text(render_html(doc, brand, fs, hero_h=hero_h, tweaks=tweaks, theme=a.theme, inline_fonts=a.inline_fonts))
    w, h = CANVAS[doc["card"].get("aspect", "4:5")]
    with tm.step("png"):
        to_png(hp, pp, w, h, scale, pdf_path=(out / f"{stem}.pdf") if want_pdf else None, carousel_dir=(out / f"{stem}.carousel") if a.carousel else None)
    with tm.step("meta"):
        alt = typeset.alt_text(doc.get("facts"), doc["card"], site=brand.get("site")); typeset.embed_alt(pp, alt)      # 71 (+ 84 stamped in to_png)
        info["alt"] = alt
    with tm.step("layout"): lr = layout_report(hp, w, h)               # 77: 1080 and 390, blocking
    warnings.extend("layout: " + m for m in lr["problems"])
    with tm.step("gates"):
        post = RG.post_render(hp, doc, dec, out, stem, width=w, height=h)   # 23 number trace, 77 layout @1080/390, 80 badge, 73-76 overlay
        RG.write_report(out, stem, dec.report, post, dec)
    warnings.extend("gate: " + f.line() for f in dec.report.findings + post.findings if f.severity != "info")
    gate_errors = dec.report.errors + post.errors
    info.update(post=post, gate_errors=gate_errors, number_errors=[f.line() for f in gate_errors if str(getattr(f, "id", "")).startswith("G23")])
    with tm.step("legibility"): lg = legibility(hp, out, stem, w, h)   # blocking gate on the final render
    illegible = not lg.get("pass", not lg.get("missing"))          # r2 (68): OCR misses, number font floor and headline/takeaway read-back all gate
    if illegible:
        if lg.get("missing"): warnings.append(f"legibility @390px: OCR could not read {lg['missing']} (see {stem}.legibility.json)")
        warnings.extend(illegible_report(lg))
        warnings.extend(f"legibility: {m}" for m in lg.get("failing", []) if not m.startswith("OCR cannot read"))
    elif lg.get("ocr") is not None: print(f"legibility @390px: all {len(lg['expected'])} numbers read back")
    else: warnings.append(f"legibility gate open: OCR unavailable ({lg.get('ocr_error')})")
    if a.variants:
        with tm.step("variants"): print("variants:", variants_png(doc, brand, out, stem, w, h, scale, a.theme, a.inline_fonts))
    ft = (tweaks or {}).get("_fit") or {}
    over_budget = tm.total() > RENDER_BUDGET_S
    if over_budget: warnings.append(f"render time {tm.total():.1f}s exceeds the {RENDER_BUDGET_S:.0f}s budget (steps: {tm.steps})")
    fit_json = {"fs": fs, "hero_h_em": hero_h, "reflow": {k: v for k, v in (tweaks or {}).items() if k not in ("layout", "_fit")},
                "layout": (tweaks or {}).get("layout"), "warnings": warnings, "planner_override": planner_override, "iterations": log}
    (out / f"{stem}.fit.json").write_text(json.dumps(fit_json, indent=1))
    report = {"card": stem, "renderer": RENDER_VERSION, "canvas": [w, h], "fs": round(fs, 4), "hero_h_em": hero_h and round(hero_h, 3),
              "layout": (tweaks or {}).get("layout"), "fit": ft, "fit_iterations": len(log),
              "empty_band_px": ft.get("band_px"), "overflow_px": max(0, (ft.get("content_h") or 0) - h) if ft else None,
              "beat_lines": ft.get("beat_lines"), "layout_problems": {str(k): v["problems"] for k, v in lr["per_width"].items()},
              "min_font_px_1080": lr["metrics"].get("min_font_px"), "min_font_px_390": lr["per_width"].get(390, {}).get("min_font_effective_px"),
              "ocr_expected": len(lg.get("expected") or []), "ocr_missing": lg.get("missing"), "ocr_available": lg.get("ocr") is not None,
              "legibility_pass": not illegible, "legibility_failing": lg.get("failing"),
              "gate_decision": dec.as_dict(), "gate_errors": [f.line() for f in gate_errors],
              "fonts_ok": True, "timing_s": dict(tm.steps, total=tm.total()), "budget_s": RENDER_BUDGET_S, "over_budget": over_budget,
              "png_sha256": hashlib.sha256(pp.read_bytes()).hexdigest(), "warnings": warnings}
    (out / f"{stem}.render.json").write_text(json.dumps(report, indent=1, sort_keys=True))
    info.update(fs=fs, hero_h=hero_h, lg=lg, lr=lr, warnings=warnings, report=report, w=w, h=h, illegible=illegible)
    print(f"wrote {pp}  (font scale {fs:.3f}, hero {hero_h and round(hero_h, 1)}em, {len(log)} fit iterations, "
          f"band {report['empty_band_px']}px, score {ft.get('score')}, {tm.total():.1f}s)")
    for wmsg in warnings: print("WARNING:", wmsg)
    if log and log[-1]["content_h"] > h: print("WARNING: still overflowing after fit loop; shorten copy")
    rc = 0
    if gate_errors:
        print(f"GATE: {len(gate_errors)} render gate error(s); the card is marked {dec.action.upper()} and is not final (see {stem}.cardgates.json)")
        for f in gate_errors[:8]: print("  GATE:", f.line())
        if not _opt(a, 'allow_gate_errors', False) and dec.action != "draft": rc = EXIT_GATE
    if illegible and not _opt(a, 'allow_illegible', False):
        print(f"FAIL: legibility gate: {len(lg.get('failing') or lg.get('missing') or [])} failure(s) ({'; '.join(map(str, (lg.get('failing') or lg.get('missing') or [])[:3]))}); trim the named slot(s) or pass --allow-illegible")
        rc = rc or EXIT_ILLEGIBLE
    if lr["problems"] and _opt(a, 'strict_layout', False):
        print(f"FAIL: {len(lr['problems'])} layout problem(s) (see {stem}.render.json)")
        rc = rc or EXIT_LAYOUT
    return rc, info

def render_card(card_path, a, out, tm=None):
    """One card file -> render_doc.  Returns the exit code.  With a.finalize the render is staged under <run dir>/render_held/ and
    promoted to `out` only when render_gate.finalize passes every gate (otherwise it is held and queued; exit 6)."""
    card_path = pathlib.Path(card_path)
    doc = json.loads(card_path.read_text())
    stem = card_path.parent.name if card_path.name == "doc.json" else card_path.stem        # runs/<slug>/doc.json -> <slug>.*
    if not _opt(a, "finalize", False):
        return render_doc(doc, stem, a, out, tm, run_dir=card_path.parent)[0]
    import render_gate as RGt
    stage = RGt.staging_dir(card_path.parent)
    rc, info = render_doc(doc, stem, a, stage, tm, run_dir=card_path.parent)
    if info.get("notice"):
        shutil.copy2(info["notice"], pathlib.Path(out) / info["notice"].name); return rc
    res = finalize_render(stem, stage, out, doc, info)
    print(f"render gate: {res['status']}" + ("" if res["status"] == "final" else "  held: " + "; ".join(f"{x['gate']}: {x['detail'][:90]}" for x in res["entry"]["reasons"])))
    return rc if res["status"] == "final" or rc else EXIT_HELD

def finalize_render(stem, stage, out, doc, info):
    """Item 100: promote the staged render to `out` only if render_gate passes it (draft decision, number trace, DOM gates, fit,
    legibility, layout, lint); otherwise hold it in `stage` and queue it for review."""
    import render_gate as RGt
    return RGt.finalize(stem, stage, out, doc=doc, numbers=info.get("number_errors") or None,
                        card_gates=(info.get("decision"), info.get("gate_errors") or []))

def render_batch(card_paths, a, out):
    """90. All cards through one Chromium. Returns the worst exit code; a RenderError on one card is reported and the batch goes on."""
    rc = 0
    with render_session():
        for cp in card_paths:
            try: rc = max(rc, render_card(cp, a, out))
            except RenderError as e:
                print(f"FAIL {cp}: {e}"); rc = max(rc, EXIT_ASSET)
    return rc

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("card", nargs="+", help="one or more card.json / doc.json files (several = one browser for the whole batch)"); ap.add_argument("-o", "--outdir", default="out")
    ap.add_argument("--brand", default=str(HERE / "brand.json")); ap.add_argument("--scale", type=int)
    ap.add_argument("--target", choices=list(TARGETS)); ap.add_argument("--pdf", action="store_true")
    ap.add_argument("--theme", choices=["light", "dark"], default="light"); ap.add_argument("--inline-fonts", action="store_true")
    ap.add_argument("--carousel", action="store_true"); ap.add_argument("--variants", action="store_true")
    ap.add_argument("--fs", type=float, help="skip the fit loop and use this font scale")
    ap.add_argument("--legibility", action="store_true", help="(default, kept for compatibility) 390px phone render + OCR read-back of every number")
    ap.add_argument("--allow-illegible", action="store_true", help="report numbers OCR cannot read at 390px but exit 0")
    ap.add_argument("--strict-layout", action="store_true", help="exit 4 when the 1080/390 layout check finds overflow, overlap or clipped text")
    ap.add_argument("--gate-inputs", help="JSON {audit_fatal, verify_verdict, retracted} (or a runs/<slug> dir) for the DRAFT / refuse decision; default: pipeline.report.json next to the card")
    ap.add_argument("--allow-gate-errors", action="store_true", help="report render-gate errors but exit 0 (the card is still marked DRAFT)")
    ap.add_argument("--finalize", action="store_true", help="stage under <run dir>/render_held/ and publish to --outdir only if render_gate passes it; otherwise hold + queue (exit 6)")
    a = ap.parse_args()
    out = pathlib.Path(a.outdir); out.mkdir(parents=True, exist_ok=True)
    rc = render_batch(a.card, a, out)
    if rc: raise SystemExit(rc)

if __name__ == "__main__":
    import sys; sys.modules.setdefault("render", sys.modules["__main__"])     # `import render` inside helpers must see THIS module (one render_session)
    main()
