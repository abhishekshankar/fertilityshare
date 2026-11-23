#!/usr/bin/env python3
"""
plan.py — deterministic block planner for FertilityShare card pipeline.

Three layers:
  1. DECISION_TABLE / decide(facts)   deterministic: evidence shape → ranked candidate blocks
  2. retrieve(facts, block, k)        reference-driven: score past cards in cards/
  3. plan_prompt(facts)               FILL_SYSTEM + facts + planner decision + exemplars

Adapted from evidencebased card-pipeline plan.py; same block library, fertility-specific
domain hints and eyebrow rules.
"""
from __future__ import annotations
import json, pathlib, collections, re

HERE = pathlib.Path(__file__).parent

SMALL_RR = 0.25
SMALL_ARD_PER_100 = 5.0

# ---------------------------------------------------------------- block decision table

def _ctx(facts: dict) -> dict:
    outs = [o for o in facts.get("outcomes") or []
            if o.get("value") is not None or o["kind"] in ("qualitative", "series", "distribution")]
    c = {"outs": outs, "kinds": collections.Counter(o["kind"] for o in outs), "n": len(outs)}
    c["has_ci"] = [o for o in outs if o.get("ci")]
    c["counts"] = [o for o in outs if o["kind"] == "count"]
    c["hz"] = [o for o in outs if o["kind"] in ("hazard_or_odds", "relative_change")]
    c["lv"] = [o for o in outs if o["kind"] == "level" and o.get("group")]
    c["rat"] = [o for o in outs if o["kind"] == "ratio"]
    c["coef"] = [o for o in outs if o["kind"] == "coefficient"]
    c["series"] = [o for o in outs if o["kind"] == "series"]
    c["of_total"] = [o for o in outs if o["kind"] == "of_total"]
    c["dist"] = [o for o in outs if o["kind"] == "distribution"]
    c["qual"] = [o for o in outs if o["kind"] == "qualitative"]
    c["numeric"] = [o for o in outs if o["kind"] not in ("qualitative",)]
    return c

def _events_outcomes(facts: dict):
    for o in facts.get("outcomes") or []:
        ev = o.get("events")
        if isinstance(ev, dict) and all(
            isinstance(ev.get(k), (list, tuple)) and len(ev[k]) == 2 and ev[k][1]
            for k in ("intervention", "control")
        ):
            yield o, ev

def abs_risk_array(facts: dict, reason_only: bool = False):
    for o, ev in _events_outcomes(facts):
        (ei, ni), (ec, nc) = ev["intervention"], ev["control"]
        ri, rc = ei / ni * 100, ec / nc * 100
        rr = (ei / ni) / (ec / nc) if ec else None
        small = abs(ri - rc) < SMALL_ARD_PER_100 or (rr is not None and abs(rr - 1) < SMALL_RR)
        if not small:
            continue
        if reason_only:
            return f"events and N present, small effect ({ri:.1f} vs {rc:.1f} per 100): 100-person icon array"
        hit = round(ri)
        return {
            "type": "waffle", "title": f"Per 100 people: {o['name']}"[:40].rstrip(),
            "total": 100, "hit": hit,
            "hit_label": f"had it on treatment ({round(rc)} on control)"[:44],
            "miss_label": "did not", "ref": facts["outcomes"].index(o),
        }
    return None

# predicates — return reason string or None
def _two_est(f, c):
    if len(c["has_ci"]) == 2:
        return "two effect estimates with CIs: stat tiles carrying the CI"
def _forest(f, c):
    if c["has_ci"] and 3 <= len(c["has_ci"]) <= 6:
        return f"{len(c['has_ci'])} effect estimates with confidence intervals"
def _bar_h_ci(f, c):
    if c["has_ci"] and 6 < len(c["has_ci"]) <= 8:
        return f"{len(c['has_ci'])} estimates with CIs (>6): horizontal bars"
def _line(f, c):
    if c["series"]:
        pts = max(len(o.get("series") or []) for o in c["series"])
        return "time/age series" if pts >= 3 else "2-point series: stat pair + illustrative sparkline"
def _pathway(f, c):
    steps = f.get("mechanism_steps") or []
    if len(steps) >= 3 and f["design"] in ("mechanistic", "animal", "review") and not c["hz"] and not c["lv"]:
        return "mechanism given as steps, no effect sizes"
def _state(f, c):
    if c["qual"] and 2 <= len(c["qual"]) <= 4 and not c["numeric"]:
        return "combinatorial states, no numbers"
def _stacked(f, c):
    if c["dist"]:
        return "category distributions per group"
def _diverging(f, c):
    if c["coef"] and any(o["value"] < 0 for o in c["coef"]) and any(o["value"] > 0 for o in c["coef"]):
        return "signed coefficients: diverging bars"
def _stat_row(f, c):
    dirs = {o.get("direction") for o in c["hz"]}
    same = 2 <= len(c["hz"]) <= 5 and len(dirs) == 1 and None not in dirs and "none" not in dirs
    if same and (all(o["kind"] == "hazard_or_odds" for o in c["hz"]) or len(c["hz"]) == 2):
        return f"{len(c['hz'])} outcomes, same direction"
def _bar_v(f, c):
    if 3 <= len(c["lv"]) <= 5:
        return f"{len(c['lv'])} groups with one level each"
def _bar_h(f, c):
    if 2 <= len(c["hz"]) <= 8:
        return "ranked effects"
def _isotype(f, c):
    if 2 <= len(c["rat"]) <= 4 and all(o["value"] <= 30 for o in c["rat"]):
        return "small integer ratios between conditions"
def _range(f, c):
    if c["kinds"]["threshold"]:
        return "a threshold on a continuous scale"
def _before_after(f, c):
    ab = [o for o in c["outs"] if o["kind"] == "absolute_change" and o.get("baseline") is not None]
    if 2 <= len(ab) <= 4 and not c["hz"]:
        return "one transformation, before and after values"
def _funnel(f, c):
    k = c["counts"]
    if len(k) >= 3 and all(k[i]["value"] >= k[i + 1]["value"] for i in range(len(k) - 1)):
        return "monotone decreasing counts (attrition / funnel)"
def _dotmatrix(f, c):
    k = c["counts"]
    if len(k) == 2 and max(x["value"] for x in k) / max(1, min(x["value"] for x in k)) >= 20:
        return "two counts differing by ≥20×"
    ot = c["of_total"]
    if ot and ot[0].get("total") and ot[0]["value"] > 0 and (ot[0]["total"] - ot[0]["value"]) / max(1, ot[0]["value"]) >= 20:
        return "k of N with ≥20× contrast"
def _waffle(f, c):
    ot = c["of_total"]
    if ot:
        o = ot[0]
        return f"{o['value']} of {o['total']}"
def _tiles(f, c):
    if f.get("exposure") and any(
        o["kind"] == "level" and (o.get("unit") or "") in ("s", "min", "/10", "mg", "g", "cups", "steps", "IU", "ng/mL")
        for o in c["outs"]
    ):
        return "intervention parameters (dose, duration, effort)"
    if f["design"] in ("rct", "crossover", "pilot") and not c["lv"] and not c["series"]:
        return "trial parameters as tiles"
def _abs_risk(f, c):
    return abs_risk_array(f, reason_only=True)

PAIRINGS = {
    "stat_row":    ["stat_tiles", "funnel"],
    "line_area":   ["stat_tiles", "waffle"],
    "forest":      ["stat_tiles"],
    "bar_h":       ["stat_tiles", "funnel"],
    "bar_v":       ["stat_tiles"],
    "pathway":     ["state_table", "stat_tiles"],
    "stacked_100": ["stat_tiles"],
    "before_after":["stat_tiles"],
    "waffle":      ["stat_tiles"],
    "isotype":     ["stat_tiles"],
    "range_bar":   ["stat_tiles"],
    "dotmatrix":   ["stat_tiles"],
    "funnel":      ["stat_tiles"],
    "state_table": [],
    "stat_tiles":  [],
}
CHART_BLOCKS = {"line_area", "bar_h", "bar_v", "forest", "stacked_100", "pathway", "waffle", "isotype", "range_bar", "dotmatrix", "before_after", "stat_row"}

DECISION_TABLE = [
    ("two_est",     _two_est,     "stat_tiles",  "effect"),
    ("ci_forest",   _forest,      "forest",       "effect"),
    ("ci_bars",     _bar_h_ci,    "bar_h",        "effect"),
    ("series",      _line,        "line_area",    "effect"),
    ("mechanism",   _pathway,     "pathway",      "effect"),
    ("states",      _state,       "state_table",  "effect"),
    ("distribution",_stacked,     "stacked_100",  "effect"),
    ("signed",      _diverging,   "bar_h",        "effect"),
    ("same_dir",    _stat_row,    "stat_row",     "effect"),
    ("groups",      _bar_v,       "bar_v",        "effect"),
    ("ranked",      _bar_h,       "bar_h",        "effect"),
    ("ratios",      _isotype,     "isotype",      "effect"),
    ("threshold",   _range,       "range_bar",    "effect"),
    ("before_after",_before_after,"before_after", "effect"),
    ("attrition",   _funnel,      "funnel",       "count"),
    ("far_apart",   _dotmatrix,   "dotmatrix",    "count"),
    ("k_of_n",      _waffle,      "waffle",       "count"),
    ("abs_risk",    _abs_risk,    "waffle",       "count"),
    ("parameters",  _tiles,       "stat_tiles",   "tiles"),
]

def decide(facts: dict) -> dict:
    c = _ctx(facts)
    fired = []
    for name, pred, block, kind in DECISION_TABLE:
        why = pred(facts, c)
        if why:
            fired.append({"rule": name, "block": block, "kind": kind, "reason": why})
    effects = [r for r in fired if r["kind"] == "effect"]
    counts  = [r for r in fired if r["kind"] == "count"]
    tiles   = [r for r in fired if r["kind"] == "tiles"]
    if effects:
        primary = effects[0]
        allowed = PAIRINGS.get(primary["block"], [])
        pool = [r for r in counts + tiles if r["block"] in allowed and r["block"] not in CHART_BLOCKS]
        pool.sort(key=lambda r: allowed.index(r["block"]))
        secondary = pool[0] if pool else None
        ranked = effects + counts + tiles
    elif counts:
        primary = counts[0]
        pool = [r for r in counts[1:] + tiles if r["block"] in PAIRINGS.get(primary["block"], [])]
        secondary = pool[0] if pool else None
        ranked = counts + tiles
    else:
        primary = {"rule": "fallback", "block": "stat_tiles", "kind": "tiles", "reason": "fallback: headline parameters as tiles"}
        secondary = None
        ranked = [primary]
    flags = {}
    if primary["block"] == "line_area" and "2-point" in primary.get("reason", ""):
        flags["illustrative"] = True; flags["sparkline"] = True; flags["stat_pair"] = True
    if primary["block"] == "bar_h" and primary["rule"] == "signed":
        flags["diverging"] = True; flags["sort"] = "magnitude"; flags["negatives"] = "grey"
    if primary["block"] == "waffle" and c["of_total"] and c["of_total"][0].get("total", 0) > 120:
        flags["per_100"] = True
    if primary["block"] == "stacked_100":
        flags["max_categories"] = 4
    return {
        "primary": primary,
        "secondary": secondary,
        "alternatives": [r for r in ranked if r is not primary and r is not secondary],
        "flags": flags,
        "fired": [r["rule"] for r in fired],
    }

# ---------------------------------------------------------------- retrieval
def retrieve(facts: dict, block: str, k: int = 2, corpus_dir: pathlib.Path = HERE / "cards") -> list[dict]:
    scored = []
    for p in corpus_dir.glob("*.json"):
        try:
            c = json.loads(p.read_text())
        except (ValueError, OSError):
            continue
        if "card" not in c or "facts" not in c:
            continue
        s = 0
        s += 3 if (c["card"].get("data_block") or {}).get("type") == block else 0
        s += 2 if c["facts"].get("design") == facts.get("design") else 0
        s += 1 if c["facts"].get("species", "human") == facts.get("species", "human") else 0
        if facts.get("domain") and c["facts"].get("domain") == facts.get("domain"):
            s += 2
        scored.append((s, p.name, c))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [{"name": n, "card": c["card"]} for s, n, c in scored[:k] if s > 0]

# ---------------------------------------------------------------- planner prompt
PLANNER_SYSTEM = """You write one evidence card from a typed `facts` record. You fill ONLY the `card` object.

Frame (Wallace-style science cards):
- eyebrow: genre label in caps (TRIAL RESULT / COHORT FINDING / META-ANALYSIS / MECHANISM / CASE SERIES / PILOT).
- headline: [population or intervention] [past-tense verb] [outcome by number], two lines;
  `payoff` is the red phrase (the number and direction). Or a contrast pair.
- dek: 2–3 sentences, plain English. Numbers auto-bolded. Mention cycle count or cohort size when informative.
- data_block: use the planner's chosen block; explain override in planner_note.
  Every number carries `ref` = index into facts.outcomes.
- source_strip: journal+year | design | N or N cycles, mono caps.
- evidence_boundary: 1–2 sentences the reader needs before generalising (population, protocol, what was not measured).
- takeaway: one or two sentences; `highlight` = exact substring; tone: action/caution/caveat.
  `strength` ≤ design cap (rct/crossover N≥30 → recommendation; cohort/case_control → association;
  mechanistic/animal → mechanism; pilot/case_series → observation).
- hero.prompt: physical description only, watercolor anatomy, off-white background, "no text, no labels".
  Fertility subjects: ovaries, follicles, embryo, sperm, uterus, placenta — anatomically precise.
- Respect every maxLength. Plain words. No overclaiming.
"""

def plan_prompt(facts: dict) -> dict:
    d = decide(facts)
    block = d["primary"]["block"]
    exemplars = retrieve(facts, block)
    user = {
        "facts": facts,
        "planner": {
            "chosen_block": block,
            "reason": d["primary"]["reason"],
            "secondary": d["secondary"],
            "alternatives": d["alternatives"],
            "flags": d["flags"],
        },
        "exemplars": exemplars,
        "instruction": (
            "Fill `card` following the house grammar. "
            "Use `exemplars` for tone and structure, never for numbers. "
            "Never repeat what made a past card weak."
        ),
    }
    return {"system": PLANNER_SYSTEM, "user": json.dumps(user, ensure_ascii=False, indent=1), "block": block, "decision": d}


if __name__ == "__main__":
    import sys
    facts = json.loads(pathlib.Path(sys.argv[1]).read_text())["facts"]
    d = decide(facts)
    print(json.dumps(d, indent=1, ensure_ascii=False))
    print("exemplars:", [e["name"] for e in retrieve(facts, d["primary"]["block"])])
