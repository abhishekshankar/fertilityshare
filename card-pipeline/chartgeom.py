"""
chartgeom.py — chart preparation for render.py / template.html (render backlog items 32, 34-52).

Pure functions, no model calls. Every number a chart draws comes from the card block or from facts.outcomes
(by `ref`); geometry (axis ticks, positions) is derived from those numbers, never invented.

    prepare(b, facts)      mutate-in-place: pooled/subgroup marks (34), subtitle timepoint/measure/interval (35, 49),
                           bar geometry with sign handling (32, 41-43), favours labels (40), paired comparison (45),
                           slope groups (44), waffle arrays (47), <2 points -> tiles (51), planner note (50)
"""
from __future__ import annotations
import math, re

MINUS = "−"
ALL_ROW = re.compile(r"^\s*(all|overall|total|pooled|everyone|whole)\b", re.I)
RATIO_UNITS = ("ratio", "hr", "or", "rr")
_NUMW = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8",
         "nine": "9", "ten": "10", "eleven": "11", "twelve": "12"}
MEASURE_WORDS = {"MD": "mean difference", "RR": "risk ratio", "HR": "hazard ratio", "OR": "odds ratio",
                 "SMD": "standardised mean difference", "WMD": "weighted mean difference", "IRR": "rate ratio"}
MEASURE_PATTERN = {"MD": r"mean diff|\bMD\b", "RR": r"risk ratio|relative risk|\bRR\b", "HR": r"hazard|\bHR\b", "OR": r"odds|\bOR\b",
                   "SMD": r"standardi[sz]ed|\bSMD\b", "WMD": r"weighted mean|\bWMD\b", "IRR": r"rate ratio|\bIRR\b"}


# ---------------------------------------------------------------- small helpers
def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)

def parse_num(s):
    """'−2.52' / '-2.52' / '7.62 h' / '221 W' -> (float, rest) or None."""
    if _num(s): return float(s), ""
    if not isinstance(s, str): return None
    m = re.match(r"^\s*([−–\-+]?)\s*(\d[\d,]*(?:\.\d+)?)\s*(.*?)\s*$", s)
    if not m: return None
    v = float(m.group(2).replace(",", ""))
    return (-v if m.group(1) in ("-", MINUS, "–") else v), m.group(3)

def outcome_of(it, facts):
    outs = (facts or {}).get("outcomes") or []
    r = it.get("ref") if isinstance(it, dict) else None
    return outs[r] if isinstance(r, int) and 0 <= r < len(outs) else None

def _outcomes(b, facts):
    return [o for o in (outcome_of(it, facts) for it in (b.get("items") or [])) if o]

def _close(a, b, tol=0.006):
    return _num(a) and _num(b) and abs(a - b) <= tol * max(1.0, abs(a), abs(b))

def _absclose(a, b):
    return _num(a) and _num(b) and _close(abs(a), abs(b))

def _nice_ticks(lo, hi, n=4):
    import render as R
    return R.nice_ticks(lo, hi, n)


# ---------------------------------------------------------------- 35 / 49: timepoint, measure, interval type in the subtitle
def _norm_words(s):
    s = (s or "").lower()
    s = re.sub(r"\b(" + "|".join(_NUMW) + r")\b", lambda m: _NUMW[m.group(1)], s)
    s = s.replace("12 months", "1 year").replace("twelve months", "1 year")
    return s

def _tp_covered(text, tp):
    t, p = _norm_words(text), _norm_words(tp)
    nums = re.findall(r"\d+", p)
    words = [w for w in re.findall(r"[a-z]+", p) if w in ("day", "days", "week", "weeks", "month", "months", "year", "years", "hour", "hours", "min")]
    if not nums: return p.strip() in t
    stem = lambda w: w.rstrip("s")
    return all(re.search(rf"(?<!\d){n}(?!\d)", t) for n in nums) and all(stem(w) in t for w in words)

def _clean_timepoint(tp):
    tp = (tp or "").strip()
    if not tp or len(tp) > 34 or not re.search(r"\d", tp): return None
    if re.match(r"^(through|from|after start|since)\b", tp, re.I): return None
    if re.match(r"^(at|after|by|to)\b", tp, re.I): return tp
    if re.match(r"^(day|week|month|year)\s*\d", tp, re.I) or re.match(r"^\d+[\d.]*\s*(min|h|hour|day|week|month|year)", tp, re.I): return "at " + tp
    return tp

def enrich_subtitle(b, facts):
    """Append only what is missing and what the facts hold: the shared timepoint of the referenced outcomes (35),
    the effect measure (MD / RR / HR ...) and the interval type (49). Records what it added in b.geo.added."""
    outs = _outcomes(b, facts)
    if not outs: return
    text = f"{b.get('title') or ''} {b.get('subtitle') or ''}"
    add = []
    tps = {(o.get("timepoint") or "").strip() for o in outs if (o.get("timepoint") or "").strip()}
    if len(tps) == 1:
        tp = _clean_timepoint(next(iter(tps)))
        if tp and not _tp_covered(text, tp): add.append(tp)
    ms = {(o.get("measure") or "").upper() for o in outs}
    if len(ms) == 1 and all(o.get("comparator") for o in outs):      # a between-group measure only when the paper names a comparator
        m = next(iter(ms))
        if m in MEASURE_WORDS and not re.search(MEASURE_PATTERN[m], text, re.I) and b.get("type") == "forest":
            add.append(MEASURE_WORDS[m])
    if b.get("type") == "forest" and any(it.get("ci") for it in b.get("items") or []) and not re.search(r"\bCI\b|confidence|interval", text, re.I):
        lv = {o.get("ci_level") for o in outs if o.get("ci")}
        add.append(f"{int(next(iter(lv)))}% CI" if len(lv) == 1 and _num(next(iter(lv))) else "confidence interval")
    if add:
        sub = (b.get("subtitle") or "").strip()
        b["subtitle"] = (sub + (" · " if sub else "") + " · ".join(add)).strip()
        b.setdefault("geo", {})["added"] = add


# ---------------------------------------------------------------- 34: pooled vs subgroup
def mark_pooled(b, facts):
    items = b.get("items") or []
    for it in items:
        o = outcome_of(it, facts) or {}
        it["pooled"] = bool(ALL_ROW.match(str(it.get("label", "")))) or bool(re.search(r"\bpooled\b", o.get("name") or "", re.I))
    pooled = [it for it in items if it["pooled"]]
    rest = [it for it in items if not it["pooled"]]
    b.setdefault("geo", {})["subgroups"] = bool(pooled and len(rest) >= 2)
    # one pooled row means 'the whole'; several 'pooled' rows are separate outcomes, not subgroups
    if len(pooled) != 1 or not rest:
        for it in items: it["pooled"] = False
        b["geo"]["subgroups"] = False
    elif b["geo"]["subgroups"]:
        for it in rest: it["sub_row"] = True


# ---------------------------------------------------------------- 40: favours-left / favours-right
def _group_name(facts, role, limit=3):
    for g in (facts or {}).get("groups") or []:
        if isinstance(g, dict) and g.get("role") == role and g.get("name"):
            w = re.sub(r"\s+\d[\d.,]*\s*(mg|g|kg|ml|mcg|µg|iu)\b.*$", "", g["name"], flags=re.I).split()
            return " ".join(w[:limit])
    return None

def _outcome_sign(o):
    rs = o.get("raw_stat") or {}
    if o.get("kind") in ("hazard_or_odds", "relative_change") and _num(rs.get("value")) and str(rs.get("type", "")).upper() in ("HR", "OR", "RR", "IRR"):
        return (rs["value"] > 1) - (rs["value"] < 1)
    v = o.get("value")
    return (v > 0) - (v < 0) if _num(v) else 0

def favours(b, facts, nv):
    """(left_label, right_label) from good_direction, or None when unknown / rows disagree / the card's sign is not the paper's."""
    try:
        from editorial import direction as D
    except Exception:
        return None
    sides = set()
    for it in b.get("items") or []:
        o = outcome_of(it, facts)
        if not o or not _num(it.get("value")): return None
        s_item = (it["value"] > nv) - (it["value"] < nv)
        if s_item == 0: continue
        if _outcome_sign(o) not in (0, s_item): return None
        imp = D.improvement(o, facts)
        if imp["polarity"] not in ("better", "worse"): return None
        side_of_value = "right" if s_item > 0 else "left"
        fav = side_of_value if imp["polarity"] == "better" else ("left" if side_of_value == "right" else "right")
        sides.add(fav)
    if len(sides) != 1: return None
    who = _group_name(facts, "intervention") or "the intervention"
    other = _group_name(facts, "control") or "the comparison"
    fav = next(iter(sides))
    return (f"favours {who}", f"favours {other}") if fav == "left" else (f"favours {other}", f"favours {who}")


# ---------------------------------------------------------------- 32 / 41 / 42 / 43: bars with signs, zero baseline, n column, CIs
def _signed(it, facts):
    d = parse_num(it.get("display")) if it.get("display") is not None else None
    v = it.get("value")
    if d and _num(v) and _close(abs(d[0]), abs(v)) and d[0] != 0: return abs(v) if d[0] > 0 else -abs(v)
    if _num(v):
        o = outcome_of(it, facts)
        if o and _num(o.get("value")) and _close(abs(o["value"]), abs(v)) and v > 0 and o["value"] < 0 and not d: return -abs(v)
    return v

def bar_geom(b, facts):
    its = b.get("items") or []
    vs, cis, ci_src = [], [], []
    for it in its:
        v = _signed(it, facts); vs.append(v)
        ci = it.get("ci")
        if ci and len(ci) == 2 and all(_num(c) for c in ci):
            ci = [min(ci), max(ci)]
            if v < 0 and ci[0] >= 0: ci = [-ci[1], -ci[0]]
            cis.append(ci); ci_src.append("card"); continue
        o = outcome_of(it, facts)
        oc = (o or {}).get("ci")
        if o and oc and len(oc) == 2 and all(_num(c) for c in oc) and (_absclose(o.get("value"), v) or _absclose((o.get("raw_stat") or {}).get("value"), v)):
            cis.append([min(oc), max(oc)]); ci_src.append("facts")
        else:
            cis.append(None); ci_src.append(None)
    allv = [0] + [v for v in vs if _num(v)] + [c for ci in cis if ci for c in ci]
    lo, hi = min(allv), max(allv)
    if b.get("axis_max") is not None and lo >= 0: hi = max(hi, b["axis_max"])
    ticks = _nice_ticks(lo, hi, 4)
    lo, hi = min(lo, ticks[0]), max(hi, ticks[-1])
    P = lambda x: round((x - lo) / ((hi - lo) or 1) * 100, 2)
    rows = []
    for it, v, ci in zip(its, vs, cis):
        a, z = P(min(0, v)), P(max(0, v))
        rows.append({"left": a, "width": round(z - a, 2), "neg": v < 0, "ci": ({"left": P(ci[0]), "width": round(P(ci[1]) - P(ci[0]), 2), "lo": ci[0], "hi": ci[1]} if ci else None), "v": v})
    n_col = [str(it.get("sub")) if it.get("sub") and re.match(r"^\s*n\s*=", str(it.get("sub")), re.I) else None for it in its]
    lv = {(outcome_of(it, facts) or {}).get("ci_level") for it in its if ci_src[its.index(it)]}
    any_ci = any(cis)
    note = None
    if any_ci:
        note = ("Whiskers: " + (f"{int(next(iter(lv)))}% CI" if len(lv) == 1 and _num(next(iter(lv))) else "confidence interval")
                + ("" if all(cis) else "; none reported for the other bars"))
    elif its:
        note = "No interval reported"
    neg_only = all(v <= 0 for v in vs if _num(v)) and any(v < 0 for v in vs if _num(v))
    end = None
    if b.get("axis_label"):
        end = ("left" if neg_only else "right", b["axis_label"])
    return {"lo": lo, "hi": hi, "zero": P(0), "ticks": [{"x": P(t), "label": t} for t in ticks if lo <= t <= hi], "rows": rows, "n_col": n_col,
            "has_n": any(n_col), "note": note, "end": end, "signed": any(r["neg"] for r in rows)}


# ---------------------------------------------------------------- 45: comparison tiles -> paired dots on a shared axis
def paired_geom(b, facts):
    its = b.get("items") or []
    if len(its) != 2: return None
    nums = [parse_num(it.get("display") if it.get("display") is not None else it.get("value")) for it in its]
    if any(n is None for n in nums): return None
    units = {n[1].strip() for n in nums}
    if len(units) != 1: return None
    outs = [outcome_of(it, facts) for it in its]
    spread, spread_type = [None, None], None
    same_outcome = outs[0] is not None and outs[0] is outs[1]
    if same_outcome:
        gs = outs[0].get("group_stats") or []
        for i, (it, n) in enumerate(zip(its, nums)):
            g = next((g for g in gs if _close(g.get("value"), n[0], 0.002)), None)
            if g and g.get("spread_type") == "sd" and g.get("spread") and _num(g["spread"][0]):
                spread[i] = g["spread"][0]; spread_type = "SD"
        if spread_type and not all(_num(s) for s in spread): spread = [None, None]; spread_type = None
    else:
        stem = lambda s: set(re.findall(r"[a-z]{3,}", s.lower().split(",")[0]))
        if not (stem(its[0]["label"]) & stem(its[1]["label"])): return None
    pts = [n[0] for n in nums]
    lo_v = min(p - (s or 0) for p, s in zip(pts, spread)); hi_v = max(p + (s or 0) for p, s in zip(pts, spread))
    span = (hi_v - lo_v) or abs(hi_v) * 0.2 or 1
    ticks = _nice_ticks(lo_v - 0.06 * span, hi_v + 0.06 * span, 4)
    lo, hi = ticks[0], ticks[-1]
    P = lambda x: round((x - lo) / ((hi - lo) or 1) * 100, 2)
    rows = []
    for i, (it, n) in enumerate(zip(its, nums)):
        s = spread[i]
        rows.append({"x": P(n[0]), "band": ({"left": P(n[0] - s), "width": round(P(n[0] + s) - P(n[0] - s), 2)} if s else None),
                     "filled": i == 0})
    xs = [r["x"] for r in rows]
    return {"rows": rows, "ticks": [{"x": P(t), "label": t} for t in ticks], "spread_type": spread_type, "unit": next(iter(units)),
            "guide": [min(xs), max(xs)], "lo": lo, "hi": hi}


# ---------------------------------------------------------------- 44: slope chart for before/after
def slope_geom(b):
    rows = b.get("rows") or []
    parsed = []
    for r in rows:
        pb, pa = parse_num(r.get("before")), parse_num(r.get("after"))
        if not pb or not pa or pb[1].strip() != pa[1].strip(): return None
        parsed.append((r, pb[0], pa[0], pb[1].strip()))
    if not parsed: return None
    groups = {}
    for p in parsed: groups.setdefault(p[3], []).append(p)
    out = []
    for unit, ps in groups.items():
        vals = [v for p in ps for v in p[1:3]]
        lo = min(0, min(vals)); ticks = _nice_ticks(lo, max(vals), 3); lo, hi = ticks[0], ticks[-1]
        H, top, bot = 150, 20, 130
        Y = lambda v: round(bot - (v - lo) / ((hi - lo) or 1) * (bot - top), 1)
        def spread_labels(ys, gap=22):
            order = sorted(range(len(ys)), key=lambda i: ys[i]); out_ = list(ys)
            for a, c in zip(order, order[1:]):
                if out_[c] - out_[a] < gap: out_[c] = out_[a] + gap
            return out_
        yb = spread_labels([Y(p[1]) for p in ps]); ya = spread_labels([Y(p[2]) for p in ps])
        out.append({"unit": unit, "H": H, "base": bot, "zero": Y(0) if lo <= 0 <= hi else None, "top": Y(hi), "hi_label": hi, "lo_label": lo,
                    "rows": [{"item": p[0].get("item"), "before": p[0].get("before"), "after": p[0].get("after"), "delta": p[0].get("delta"),
                              "y0": Y(p[1]), "y1": Y(p[2]), "lb": yb[i], "la": ya[i], "up": p[2] >= p[1]} for i, p in enumerate(ps)]})
    return out


# ---------------------------------------------------------------- 47: icon arrays per 100
def waffle_arrays(b, facts):
    o = outcome_of(b, facts)
    ev = (o or {}).get("events")
    if isinstance(ev, dict) and all(isinstance(ev.get(k), (list, tuple)) and len(ev[k]) == 2 and ev[k][1] for k in ("intervention", "control")):
        arrs = []
        for k, role in (("intervention", "intervention"), ("control", "control")):
            e, n = ev[k]
            arrs.append({"name": _group_name(facts, role, 4) or ("Intervention" if k == "intervention" else "Control"),
                         "hit": int(round(e / n * 100)), "total": 100, "raw": f"{e} of {n}"})
        return arrs
    if _num(b.get("hit")) and _num(b.get("total")):
        return [{"name": None, "hit": int(b["hit"]), "total": int(b["total"]), "raw": None}]
    return None


# ---------------------------------------------------------------- 51: fewer than 2 data points -> tiles
def _ci_text(it):
    import render as R
    ci = it.get("ci")
    return f"({R.fmt(ci[0])} to {R.fmt(ci[1])})" if ci and len(ci) == 2 else None

def to_tiles(b, reason):
    items = []
    if b["type"] == "line_area":
        for s in b.get("series") or []:
            pts = s.get("points") or []
            if pts:
                import render as R
                items.append({"label": s.get("label"), "value": R.fmt(pts[-1][1]), "display": R.fmt(pts[-1][1]), "sub": f"at {R.fmt(pts[-1][0])}" + (f" {b.get('x_label')}" if b.get("x_label") and len(b['x_label']) < 12 else "")})
    else:
        for it in b.get("items") or []:
            t = {"label": it.get("label"), "value": it.get("value"), "display": it.get("display"), "semantic": "result"}
            sub = _ci_text(it) or it.get("sub")
            if sub: t["sub"] = sub
            items.append(t)
    nb = {"type": "stat_tiles", "items": items, "geo": {"tiles_from": b["type"], "reason": reason}}
    for k in ("title", "subtitle", "n"):
        if b.get(k) is not None: nb[k] = b[k]
    b.clear(); b.update(nb)
    return b

def point_count(b):
    t = b.get("type")
    if t in ("forest", "bar_h", "bar_v"): return len(b.get("items") or [])
    if t == "line_area": return max([len(s.get("points") or []) for s in b.get("series") or []] + [0])
    return None


# ---------------------------------------------------------------- 50: planner override record
def planner_note(b, facts):
    try:
        import plan
        return plan.override_note(facts, b.get("type"))
    except Exception:
        return None


# ---------------------------------------------------------------- entry point
def prepare(b, facts, primary=True):
    if not b: return b
    b.setdefault("geo", {})
    t = b.get("type")
    n = point_count(b)
    if n is not None and n < 2:
        return to_tiles(b, f"{n} data point(s): a chart needs at least 2")
    if primary:
        note = planner_note(b, facts)
        if note: b["geo"]["planner_note"] = note
    if t in ("forest", "bar_h", "bar_v", "line_area"): enrich_subtitle(b, facts)
    if t == "forest":
        mark_pooled(b, facts)
        import render as R
        lo, hi, sc = R.forest_axis(b)
        nv = b.get("null_value") if b.get("null_value") is not None else (1 if sc == "log" else 0)
        b["geo"]["favours"] = favours(b, facts, nv)
    elif t == "bar_h":
        b["geo"]["bars"] = bar_geom(b, facts)
    elif t == "stat_tiles":
        b["geo"]["paired"] = paired_geom(b, facts)
    elif t == "before_after":
        b["geo"]["slope"] = slope_geom(b)
    elif t == "waffle":
        b["geo"]["arrays"] = waffle_arrays(b, facts)
    return b
