#!/usr/bin/env python3
"""
render_gates.py — the render stage's honesty gates (RENDER_100 items 23-35 and 73-80, 94).

Principle: the render never shows a number the facts don't hold, never contradicts another slot on the same card, and
fails loudly instead of shipping a broken layout.  Everything here is deterministic (no model calls) and reads only
the doc ({"facts", "card", ...}); the DOM helpers need Playwright and are only used on a real render.

Public API
    evaluate(doc, inputs=None)      -> GateReport   static checks on facts + card text (no browser)
    decide(doc, report, inputs)     -> Decision     render | draft | refuse, with the overlay tags
    apply(doc, inputs=None)         -> Decision     evaluate + decide + doc["gate"] = overlay (what render_html reads)
    overlay_for(doc)                -> dict|None    the overlay render_html passes to the template
    post_render(html_path, doc, decision, out, stem) -> GateReport   DOM checks: number trace, layout 1080/390, badge
    refusal_html(doc) / write_notice(...)   the notice that replaces a retracted paper's card
    inputs_from_run(run_dir)        -> dict         audit/verify results from runs/<slug>/pipeline.report.json

Every finding says which slot, which element and which fix (item 94):  Finding.line().
Severity: "error" (the card is not final: DRAFT mark + gate failure), "warn" (review flag), "info" (note only).
"""
from __future__ import annotations

import html as _html
import json
import math
import pathlib
import re
from dataclasses import dataclass, field, asdict
from itertools import combinations
from typing import Any, Iterable, Optional

GATE_VERSION = "render-gates-1"
HERE = pathlib.Path(__file__).parent
BADGE_MAX = 24
OVERLAP_MAX = 0.60
EXIT_GATE = 5

# ====================================================================== findings
@dataclass
class Finding:
    id: str                 # stable rule id, e.g. "G24_ARMS"
    item: int               # RENDER_100 item number
    severity: str           # error | warn | info
    slot: str               # headline | dek | beats | data_block | source_strip | takeaway | foot | badge | ...
    element: str            # e.g. "data_block.items[1].label"
    message: str
    fix: str = ""
    path: str = ""          # facts path when the finding is about a number

    def line(self) -> str:
        s = f"[{self.id}] {self.slot} > {self.element}: {self.message}"
        return s + (f" | fix: {self.fix}" if self.fix else "")

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class GateReport:
    findings: list = field(default_factory=list)
    traced: dict = field(default_factory=dict)       # "slot|number" -> facts path
    gate_version: str = GATE_VERSION

    def add(self, *a, **k) -> None:
        self.findings.append(Finding(*a, **k))

    @property
    def errors(self) -> list: return [f for f in self.findings if f.severity == "error"]
    @property
    def warns(self) -> list: return [f for f in self.findings if f.severity == "warn"]
    def ids(self, severity: Optional[str] = None) -> list:
        return [f.id for f in self.findings if severity in (None, f.severity)]
    def lines(self, severity: Optional[str] = None) -> list:
        return [f.line() for f in self.findings if severity in (None, f.severity)]
    def as_dict(self) -> dict:
        return {"gate_version": self.gate_version, "errors": len(self.errors), "warnings": len(self.warns),
                "findings": [f.as_dict() for f in self.findings], "traced": self.traced}


# ====================================================================== text helpers
STOP = set("""a an the and or but of in on at to for from by with without as is are was were be been being it its this that these those
than then so such into over under about after before during across per vs versus not no did does do done has have had
will would can could may might should also only just more most less least very much many few some any all each both
their there they them he she his her we our you your i up out off""".split())
STOP_ARM = STOP | {"mean", "sd", "total", "n", "plus", "group", "arm", "average", "median", "change", "level", "score", "time"}
NEG_WORDS = {"not", "no", "never", "neither", "nor", "without"}

def stem(w: str) -> str:
    w = w.lower()
    return w[:5] if len(w) > 5 else w

def words(s: str) -> list:
    return re.findall(r"[a-zα-ωµ][a-zα-ωµ\-']*|\d+(?:\.\d+)?", (s or "").lower().replace("’", "'"))

def content_stems(s: str, stop=STOP) -> set:
    out = set()
    for w in words(s):
        for part in w.split("-"):
            if part and part not in stop and len(part) > 1 and not part.isdigit():
                out.add(stem(part))
    return out

NUM_RE = re.compile(r"(?<![\w.])([−+\-]?)(\d[\d,]*(?:\.\d+)?)(?![\w])")
NUM_RE_LOOSE = re.compile(r"(?<![\w.])([−+\-]?)(\d[\d,]*(?:\.\d+)?)")
NUMWORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
            "twelve": 12, "fifteen": 15, "twenty": 20}
UNITISH = r"(?:trials?|studies|nights?|weeks?|months?|years?|days?|hours?|participants|people|adults|groups|arms|periods|sites|sessions|doses|cohorts)"
NUMWORD_RE = re.compile(rf"\b({'|'.join(NUMWORDS)})\s+(?={UNITISH}\b)", re.I)

def dec_places(tok: str) -> int:
    tok = tok.replace(",", "")
    return len(tok.split(".")[1]) if "." in tok else 0

def to_float(sign: str, digits: str) -> float:
    v = float(digits.replace(",", ""))
    return -v if sign in ("-", "−") else v

def numbers_in(text: str) -> list:
    """[(float value, decimals, raw token, start)] for every digit number in text (units glued to letters excluded)."""
    out = []
    for m in NUM_RE.finditer(text or ""):
        out.append((to_float(m.group(1), m.group(2)), dec_places(m.group(2)), m.group(0), m.start()))
    for m in NUMWORD_RE.finditer(text or ""):
        out.append((float(NUMWORDS[m.group(1).lower()]), 0, m.group(1), m.start()))
    return out


# ====================================================================== slots: every string the card renders
def _item_texts(prefix: str, b: dict, slot="data_block") -> Iterable[tuple]:
    for k in ("title", "subtitle", "footnote", "not_measured", "delta_note", "x_label", "axis_label", "unit"):
        if isinstance(b.get(k), str): yield slot, f"{prefix}.{k}", b[k]
    for i, it in enumerate(b.get("items") or []):
        if not isinstance(it, dict): continue
        for k in ("label", "display", "sub"):
            if it.get(k) not in (None, ""): yield slot, f"{prefix}.items[{i}].{k}", str(it[k])
        if it.get("display") in (None, "") and isinstance(it.get("value"), (int, float)):
            yield slot, f"{prefix}.items[{i}].value", f"{it['value']:g}"
        if isinstance(it.get("ci"), (list, tuple)) and len(it["ci"]) == 2:
            yield slot, f"{prefix}.items[{i}].ci", f"{it['ci'][0]:g} to {it['ci'][1]:g}"
        if isinstance(it.get("n"), (int, float)) and not isinstance(it.get("n"), bool):
            yield slot, f"{prefix}.items[{i}].n", f"n = {it['n']:g}"
    for i, r in enumerate(b.get("rows") or []):
        if isinstance(r, dict) and r.get("label"): yield slot, f"{prefix}.rows[{i}].label", str(r["label"])
    if isinstance(b.get("n"), (int, float)) and not isinstance(b.get("n"), bool): yield slot, f"{prefix}.n", f"N = {b['n']:g}"

def slots(card: dict) -> list:
    """[(slot, element, text)] in reading order: what the template prints, as the card holds it."""
    c, out = card or {}, []
    def add(slot, el, t):
        if isinstance(t, str) and t.strip(): out.append((slot, el, t))
    add("top", "eyebrow", c.get("eyebrow")); add("top", "badge", c.get("badge")); add("top", "series", c.get("series"))
    h = c.get("headline"); add("headline", "headline.text", h.get("text") if isinstance(h, dict) else h)
    add("dek", "dek", c.get("dek"))
    for i, s in enumerate(c.get("stats_line") or []): add("stats", f"stats_line[{i}]", s)
    for i, b in enumerate(c.get("beats") or []):
        add("beats", f"beats[{i}].lead", b.get("lead")); add("beats", f"beats[{i}].detail", b.get("detail"))
    for key in ("data_block", "secondary_block"):
        if isinstance(c.get(key), dict): out.extend(_item_texts(key, c[key]))
    for i, t in enumerate(c.get("context_tiles") or []):
        add("ctx", f"context_tiles[{i}].lead", t.get("lead")); add("ctx", f"context_tiles[{i}].detail", t.get("detail"))
    for i, s in enumerate(c.get("source_strip") or []): add("source_strip", f"source_strip[{i}]", s)
    add("boundary", "evidence_boundary", c.get("evidence_boundary"))
    tk = c.get("takeaway") or {}; add("takeaway", "takeaway.text", tk.get("text") if isinstance(tk, dict) else tk)
    add("foot", "citation", c.get("citation")); add("foot", "citation_line2", c.get("citation_line2"))
    cert = c.get("certainty") or {}; add("top", "certainty.label", cert.get("label") if isinstance(cert, dict) else None)
    return out


# ====================================================================== facts index (item 23)
SKIP_KEYS = {"provenance", "location", "section", "score", "confidence", "source_index", "table_ref", "checked", "schema_version",
             "template_version", "prompt_version", "source_hash", "card_id", "model", "model_fast", "date", "precision", "passes"}

def _walk(o, path, out):
    if isinstance(o, bool) or o is None: return
    if isinstance(o, (int, float)):
        d = dec_places(repr(o)) if isinstance(o, float) else 0
        out.append((float(o), d, path)); return
    if isinstance(o, str):
        for v, d, _raw, _s in numbers_in(o): out.append((v, d, path))
        return
    if isinstance(o, dict):
        for k, v in o.items():
            if k in SKIP_KEYS: continue
            _walk(v, f"{path}.{k}" if path else str(k), out)
    elif isinstance(o, (list, tuple)):
        for i, v in enumerate(o): _walk(v, f"{path}[{i}]", out)

def facts_index(facts: dict) -> list:
    """[(value, decimals, facts path)] for every number the facts hold, plus the stated derivations (differences, widths, sums)."""
    out: list = []
    _walk(facts or {}, "", out)
    f = facts or {}
    for i, o in enumerate(f.get("outcomes") or []):
        gs = o.get("group_stats") or []
        vals = [(g.get("value"), g) for g in gs if isinstance(g.get("value"), (int, float))]
        for (a, _), (b, _) in combinations(vals, 2):
            d = max(dec_places(repr(float(a))), dec_places(repr(float(b))))
            out.append((abs(round(a - b, 6)), d, f"derived: outcomes[{i}].group_stats difference"))
            if b:
                out.append((abs(round((a - b) / b * 100, 3)), 1, f"derived: outcomes[{i}].group_stats percent difference"))
        ci = o.get("ci")
        if isinstance(ci, (list, tuple)) and len(ci) == 2 and all(isinstance(x, (int, float)) for x in ci):
            out.append((abs(ci[1] - ci[0]), 2, f"derived: outcomes[{i}].ci width"))
    gsum = [g.get("n") for g in f.get("groups") or [] if isinstance(g.get("n"), (int, float))]
    if len(gsum) > 1: out.append((float(sum(gsum)), 0, "derived: sum of groups[].n"))
    return out

def trace_value(val: float, dec: int, idx: list, pct: bool = False) -> Optional[str]:
    """Facts path holding `val` (to `dec` decimals, rounding allowed down to the paper's own precision), else None."""
    a = abs(val)
    for fv, fd, path in idx:
        for cand in ((fv, fv * 100) if pct else (fv,)):
            dd = min(dec, fd) if cand is fv or fd < dec else dec
            if round(abs(cand), dd) == round(a, dd) and (dd > 0 or abs(abs(cand) - a) < 0.5 or a == round(abs(cand))):
                if dd == 0 and abs(abs(cand) - a) >= 0.5: continue
                return path
    return None

FREE_NUMBERS = {  # numbers that are conventions, not findings
    "ci": {90.0, 95.0, 99.0}, "p": {0.05, 0.01, 0.001, 0.1, 0.0001}}
YEAR_SLOTS = {"source_strip", "foot"}

def _is_free(slot: str, text: str, start: int, val: float, raw: str) -> bool:
    before, after = text[max(0, start - 8):start].lower(), text[start + len(raw):start + len(raw) + 6].lower()
    if val in FREE_NUMBERS["ci"] and (after.lstrip().startswith(("%", "ci", "% ci")) or "ci" in after):
        return True
    if val in FREE_NUMBERS["p"] and re.search(r"\bp\s*[<>=≤≥]*\s*$", before): return True
    if slot in YEAR_SLOTS and 1900 <= val <= 2100 and float(val).is_integer(): return True
    if re.search(r"pmid\s*[:\s]*$", before): return True     # checked against coverage.ids by the citation check
    if re.search(r"[a-z]$", before) and re.match(r"^\s*(?:vs\.?|and|or)\b", after): return False
    return False


def trace_card_numbers(card: dict, facts: dict, rep: GateReport) -> None:
    """23. Every number on the card must be found in the facts; the error names the slot, the element and the number."""
    idx = facts_index(facts)
    ids = (((facts or {}).get("coverage") or {}).get("ids")) or {}
    pool_by_slot: dict = {}
    for slot, el, text in slots(card):
        for val, dec, raw, start in numbers_in(text):
            if _is_free(slot, text, start, val, raw): continue
            if re.search(r"pmid\s*[:\s]*$", text[max(0, start - 8):start].lower()):
                ok = str(int(val)) == str(ids.get("pmid") or "") or any(abs(v - val) < 1 for v, _d, p in idx if "pmid" in p.lower())
                if not ok and ids.get("pmid"):
                    rep.add("G23_NUMBER_UNTRACED", 23, "error", slot, el, f"PMID {raw} differs from the facts' PMID {ids.get('pmid')}", "use the PMID from facts.coverage.ids")
                continue
            tail = text[start + len(raw):start + len(raw) + 2]
            pct = tail.lstrip().startswith("%")
            path = trace_value(val, dec, idx, pct=pct)
            if path is None and not pct and re.match(r"\s*(?:pp|percentage point)", tail): path = trace_value(val, dec, idx, pct=True)
            if path is not None:
                rep.traced[f"{slot}|{el}|{raw}"] = path
                pool_by_slot.setdefault((slot, el), []).append((val, dec))
                continue
            # derived from two numbers in the same string (a gap, a percent change)
            pool = [(v, d) for v, d, _r, _s in numbers_in(text) if _s != start]
            hit = None
            for (a, da), (b, db) in combinations(pool, 2):
                for lab, cand in (("difference", abs(a - b)), ("sum", a + b)):
                    if round(cand, dec) == round(abs(val), dec): hit = f"derived: {lab} of {a:g} and {b:g}"
                if b and round(abs((a - b) / b * 100), dec) == round(abs(val), dec): hit = f"derived: percent change {a:g} vs {b:g}"
                if hit: break
            if hit:
                rep.traced[f"{slot}|{el}|{raw}"] = hit; continue
            rep.add("G23_NUMBER_UNTRACED", 23, "error", slot, el,
                    f"number {raw} is not in the facts (no facts path holds it, even rounded or as a stated difference)",
                    "use a number from the facts, or add the quote that supports it to the facts", path="")


# ====================================================================== 24 arms vs headline
ARM_BLOCKS = ("stat_tiles", "bar_h", "bar_v", "stat_row")

def check_arms(card: dict, facts: dict, rep: GateReport) -> None:
    b = card.get("data_block") or {}
    if b.get("type") not in ARM_BLOCKS: return
    items = [it for it in b.get("items") or [] if isinstance(it, dict) and it.get("label")]
    if len(items) < 2: return
    lab = [content_stems(it["label"], STOP_ARM) for it in items]
    common = set.intersection(*lab) if lab else set()
    arm = set().union(*[l - common for l in lab])
    arm_words = sorted({w for it in items for w in re.findall(r"[A-Za-z][\w\-]+", it["label"]) if stem(w.lower()) in arm})
    if not arm: return
    h = card.get("headline") or {}
    head = content_stems((h.get("text") if isinstance(h, dict) else str(h)) or "")
    if head & arm: return
    # a facts-level alias of an arm (group code or description) may be what the headline uses
    f = facts or {}
    aliases = []
    for g in f.get("groups") or []:
        txt = f"{g.get('name', '')} {g.get('description', '')}"
        if content_stems(txt) & arm: aliases.append(content_stems(txt))
    if any(a & head for a in aliases): return
    rep.add("G24_ARMS_VS_HEADLINE", 24, "error", "data_block", "data_block.items[].label",
            f"the arms drawn ({', '.join(arm_words)}) do not include the subject the headline talks about "
            f"('{(h.get('text') if isinstance(h, dict) else h)}')",
            "show the headline's arm (e.g. the milk-protein arms) beside the comparator, or rewrite the headline about the arms shown")


# ====================================================================== 25 counts, 26 N
OUTCOME_SYN = {
    "gait speed": ("gait", "walking speed", "walk"), "grip strength": ("grip", "handgrip"),
    "five-times sit-to-stand": ("sit-to-stand", "chair stand", "sit to stand", "sts"),
    "skeletal muscle mass index": ("muscle mass", "smi", "muscle index")}
COUNT_RE = re.compile(r"(?<![\w.])(\d[\d,]*)\s+(?:randomi[sz]ed\s+|controlled\s+|eligible\s+|included\s+)?(trials?|studies|rcts?|cohorts?)\b", re.I)

def _outcome_mentions(text: str, keys: Iterable[str]) -> list:
    t = (text or "").lower(); hit = []
    for k in keys:
        kl = k.lower()
        names = (kl,) + OUTCOME_SYN.get(kl, ()) + tuple(w for w in re.findall(r"[a-z]{4,}", kl) if w not in ("pooled", "index", "mass", "times"))
        if any(n in t for n in names): hit.append(k)
    return hit

def check_counts(card: dict, facts: dict, rep: GateReport) -> None:
    f = facts or {}
    dd = f.get("design_detail") or {}
    per = dd.get("outcome_studies") or {}
    total = dd.get("studies")
    sl = slots(card)
    block_title = " ".join(t for s, e, t in sl if s == "data_block" and e.endswith((".title", ".subtitle")))
    seen = []
    for slot, el, text in sl:
        for m in COUNT_RE.finditer(text):
            n = int(m.group(1).replace(",", ""))
            ctx = text + (" " + block_title if slot == "data_block" else "")
            seen.append((slot, el, n, text, ctx))
    if not seen: return
    for slot, el, n, text, ctx in seen:
        outs = _outcome_mentions(ctx, per.keys()) if per else []
        if slot == "headline" and per:
            outs = _outcome_mentions(text, per.keys())
        for o in outs:
            if per.get(o) is not None and per[o] != n:
                rep.add("G25_COUNT_MISMATCH", 25, "error", slot, el,
                        f"says {n} trials for {o}, but the paper pooled {per[o]} for {o}"
                        + (f" ({total} trials overall)" if total else ""),
                        f"write '{per[o]} trials' for {o} (or '{total} trials, {per[o]} measured {o}')")
    distinct = sorted({n for _s, _e, n, _t, _c in seen})
    if len(distinct) > 1 and not any(f.id == "G25_COUNT_MISMATCH" for f in rep.findings):
        rep.add("G25_COUNT_VARIES", 25, "warn", "card", "counts",
                f"trial counts differ across slots ({', '.join(map(str, distinct))}) and none is tied to an outcome",
                "say which outcome each count belongs to, or use one count")


N_EQ = re.compile(r"\bN\s*=\s*(\d[\d,]*)")
n_EQ = re.compile(r"\bn\s*=\s*(\d[\d,]*)")
VS_PEOPLE = re.compile(r"(\d[\d,]*)\s+(?:vs\.?|versus|and)\s+(\d[\d,]*)\s+(people|adults|participants|patients|men|women|athletes|children|persons)", re.I)

def facts_totals(facts: dict) -> dict:
    f, t = facts or {}, {}
    for k in ("n", "n_analyzed", "n_randomized", "n_enrolled"):
        if isinstance(f.get(k), (int, float)) and not isinstance(f.get(k), bool): t[k] = float(f[k])
    gs = [g.get("n") for g in f.get("groups") or [] if isinstance(g.get("n"), (int, float))]
    if gs: t["sum(groups.n)"] = float(sum(gs))
    dd = f.get("design_detail") or {}
    if isinstance(dd.get("participants"), (int, float)): t["design_detail.participants"] = float(dd["participants"])
    return t

def check_n(card: dict, facts: dict, rep: GateReport) -> None:
    totals = facts_totals(facts)
    known = set(totals.values())
    sl = slots(card)
    shown = []   # (slot, el, N, text, kind)
    for slot, el, text in sl:
        for m in N_EQ.finditer(text): shown.append((slot, el, float(m.group(1).replace(",", "")), text, "N"))
        for m in n_EQ.finditer(text):
            v = float(m.group(1).replace(",", ""))
            arms = {float(g["n"]) for g in (facts or {}).get("groups") or [] if isinstance(g.get("n"), (int, float))}
            if arms and v not in arms and v not in known:
                rep.add("G26_N_NOT_IN_FACTS", 26, "error", slot, el, f"n = {v:,.0f} is not an arm size in the facts ({', '.join(f'{x:,.0f}' for x in sorted(arms))})", "use the arm sizes from facts.groups")
        for m in VS_PEOPLE.finditer(text):
            a, b = float(m.group(1).replace(",", "")), float(m.group(2).replace(",", ""))
            shown.append((slot, el, a + b, text, "pair"))
    if not shown: return
    Ns = [s for s in shown if s[4] == "N"]
    if len({s[2] for s in Ns}) > 1:
        vals = sorted({s[2] for s in Ns})
        rep.add("G26_N_DIFFERS", 26, "error", Ns[0][0], Ns[0][1], "N differs between slots: " + ", ".join(f"{v:,.0f}" for v in vals),
                "one N on the card; label any subset with its outcome")
    for slot, el, tot, text, kind in shown:
        if kind == "N":
            if known and tot not in known:
                rep.add("G26_N_NOT_IN_FACTS", 26, "error", slot, el, f"N = {tot:,.0f} is not an N the facts hold ({', '.join(f'{k}={v:,.0f}' for k, v in totals.items())})",
                        "use facts.n / n_analyzed or the sum of the arm sizes")
            continue
        others = [s for s in Ns if s[2] != tot]
        if tot in known: continue
        if others:
            rep.add("G26_N_DIFFERS", 26, "error", slot, el,
                    f"'{text}' adds up to {tot:,.0f} people but {others[0][0]} ({others[0][1]}) says N = {others[0][2]:,.0f}",
                    "say which outcome the smaller group is for, or show the paper's N")
        elif known:
            rep.add("G26_N_NOT_IN_FACTS", 26, "warn", slot, el, f"'{text}' totals {tot:,.0f}, which no N in the facts equals", "check against the arm sizes")


# ====================================================================== 27 design label, 28 one certainty scale
RANDOMISED = {"rct", "crossover", "cluster_rct", "factorial_rct", "pilot_rct"}
CLASS_WORDS = [
    ("meta", r"meta-?analy|systematic review|pooled"), ("randomised", r"randomi[sz]ed|\brct\b|crossover|cross-over|\btrial\b"),
    ("observational", r"cohort|case-control|cross-sectional|observational|registry|records? review|association"),
    ("animal", r"\bmice\b|\bmouse\b|\brats?\b|animal|cell study|in vitro")]

def design_class(design: str) -> str:
    d = (design or "").lower()
    if d in RANDOMISED or "rct" in d or "crossover" in d: return "randomised"
    if "meta" in d: return "meta"
    if d in ("cohort", "case_control", "cross_sectional", "records_review", "mendelian_randomization"): return "observational"
    if d in ("animal", "mechanistic") or d.startswith("cell"): return "animal"
    return d or "unknown"

def label_classes(text: str) -> set:
    t = (text or "").lower(); out = set()
    for cls, rx in CLASS_WORDS:
        if re.search(rx, t): out.add(cls)
    if "meta" in out: out.discard("randomised"); out.discard("observational")      # "meta-analysis of RCTs" is a meta-analysis
    return out

def check_design_labels(card: dict, facts: dict, rep: GateReport) -> None:
    f = facts or {}; dcls = design_class(f.get("design"))
    labelled = []
    c = card
    for slot, el, text in slots(card):
        if el in ("badge", "eyebrow") or slot == "source_strip" or el == "citation_line2":
            if slot == "source_strip" and not re.search(r"randomi|rct|trial|cohort|case-control|cross-sectional|meta-?analy|crossover|observational|review|mice|mouse|rat", text, re.I): continue
            labelled.append((slot, el, text, label_classes(text)))
    for slot, el, text, cl in labelled:
        if cl and dcls in ("randomised", "meta", "observational", "animal") and dcls not in cl and not (dcls == "randomised" and cl == {"randomised"}):
            if dcls == "meta" and "randomised" in cl: continue
            if "observational" in cl and "randomised" in cl: continue
            rep.add("G27_DESIGN_LABEL", 27, "error", slot, el, f"'{text}' reads as {'/'.join(sorted(cl))}, the facts say design={f.get('design')} ({dcls})",
                    "use the design label the facts support")
    # the strength meter speaks observational language for a randomised design
    tk = c.get("takeaway") or {}; st = tk.get("strength")
    if st in ("observation", "association") and dcls == "randomised":
        why = ""
        try:
            from editorial.takeaway import strength_cap, RANK_NAME
            cap, w = strength_cap(f); why = f" (the cap is {RANK_NAME[cap]} by rule: {w})" if cap <= 1 else ""
        except Exception:
            pass
        rep.add("G27_STRENGTH_VS_DESIGN", 27, "warn", "foot", "takeaway.strength",
                f"the footer strength bar reads '{st.upper()}' but the design is {f.get('design')} (a randomised trial){why}: "
                f"'observation'/'association' are observational-study words",
                "rename the bar (e.g. 'claim: limited') or print the reason beside it; do not leave a trial labelled ASSOCIATION")
    if st in ("recommendation", "mechanism") and dcls == "observational":
        rep.add("G27_STRENGTH_VS_DESIGN", 27, "error", "foot", "takeaway.strength", f"strength '{st}' on an observational design", "cap at association")
    ey = (c.get("eyebrow") or "").lower()
    if dcls == "observational" and re.search(r"\btrial\b", ey):
        rep.add("G27_DESIGN_LABEL", 27, "error", "top", "eyebrow", f"eyebrow '{c.get('eyebrow')}' says trial for an observational design", "use the design label")

CERT_RANK = {"very_low": 0, "low": 1, "moderate": 2, "high": 3}
STRENGTH_RANK = {"observation": 0, "association": 1, "mechanism": 2, "recommendation": 3}

def check_scales(card: dict, facts: dict, rep: GateReport) -> None:
    cert = (card.get("certainty") or {}).get("level"); st = (card.get("takeaway") or {}).get("strength")
    if cert not in CERT_RANK or st not in STRENGTH_RANK: return
    c, s = CERT_RANK[cert], STRENGTH_RANK[st]
    msg = None
    if c <= 1 and s >= 3: msg = f"badge says {cert.replace('_', ' ')} certainty but the bar says {st}"
    elif c == 0 and s >= 2: msg = f"badge says very low certainty but the bar says {st}"
    elif c >= 3 and s == 0: msg = f"badge says high certainty but the bar says only {st}"
    if msg:
        rep.add("G28_TWO_SCALES", 28, "error", "foot", "certainty vs takeaway.strength", msg,
                "one certainty scale: make the bar follow the badge, or explain that the bar is about the claim, not the evidence")


# ====================================================================== 29 null card shows the gap, 30 SD
NULLISH = re.compile(r"\b(did not|didn't|no (?:clear )?(?:change|difference|effect)|not differ|no better|unchanged|was not|were not|neither)\b", re.I)
GAP_WORDS = re.compile(r"\b(gap|difference|differ(?:ed|ence)?|range|interval|CI)\b", re.I)
NO_RANGE = re.compile(r"(no (?:range|interval)|not (?:give|report|provide)\w*|gave no|did not (?:give|report)|no CI|without an interval)", re.I)

def check_null_card(card: dict, facts: dict, rep: GateReport) -> None:
    b = card.get("data_block") or {}
    h = (card.get("headline") or {}).get("text", "") if isinstance(card.get("headline"), dict) else str(card.get("headline") or "")
    if not NULLISH.search(h): return
    outs = (facts or {}).get("outcomes") or []
    texts = " ".join(t for _s, _e, t in slots(card))
    if b.get("type") == "stat_tiles" and len(b.get("items") or []) == 2:
        vals = []
        for it in b["items"]:
            v = it.get("value")
            if isinstance(v, (int, float)): vals.append(float(v))
        if len(vals) == 2:
            gap = abs(vals[0] - vals[1]); d = max(dec_places(repr(vals[0])), dec_places(repr(vals[1])))
            gap_s = f"{gap:.{d}f}"
            shown = gap_s in texts or f"{gap:g}" in texts
            ref = b["items"][0].get("ref")
            has_ci = isinstance(ref, int) and ref < len(outs) and bool(outs[ref].get("ci"))
            said_none = bool(NO_RANGE.search(texts))
            if not shown:
                rep.add("G29_NULL_NO_GAP", 29, "warn", "data_block", "stat_tiles",
                        f"the card says no difference but shows two means without the gap between them ({gap_s})",
                        f"add the gap ({gap_s}) as a computed difference and its interval, or say plainly that the paper gave none")
            if not has_ci and not said_none:
                rep.add("G29_NULL_NO_INTERVAL", 29, "warn", "dek", "dek", "no interval for the gap is shown and the card does not say the paper gave none",
                        "write 'the paper gave no range for the gap'")
            elif has_ci and not re.search(r"\(?\s*-?\d[\d.]*\s*(?:to|,|–|−|-)\s*-?\d", texts):
                rep.add("G29_NULL_NO_INTERVAL", 29, "error", "data_block", "stat_tiles", "the paper gives an interval for the difference and the card does not show it", "show the interval")

def check_spread(card: dict, facts: dict, rep: GateReport) -> None:
    b = card.get("data_block") or {}
    outs = (facts or {}).get("outcomes") or []
    for i, it in enumerate(b.get("items") or []):
        if not isinstance(it, dict): continue
        sub = str(it.get("sub") or "")
        if b.get("type") in ("stat_tiles", "stat_row") and re.search(r"\bSD\b|±|\bsd\b", sub) and not re.search(r"spread", sub, re.I):
            rep.add("G30_SD_NOT_LABELLED", 30, "warn", "data_block", f"data_block.items[{i}].sub",
                    f"'{sub}' shows an SD without saying it is spread", f"label it 'spread (SD)': {sub!r} is how much people vary, not how sure we are")
        ref = it.get("ref")
        if b.get("type") in ("forest", "bar_h", "bar_v") and it.get("ci") and isinstance(ref, int) and ref < len(outs):
            o = outs[ref]
            sd_only = not o.get("ci") and any(str(g.get("spread_type", "")).lower() in ("sd", "se", "sem") for g in o.get("group_stats") or [])
            if sd_only:
                rep.add("G30_SD_AS_INTERVAL", 30, "error", "data_block", f"data_block.items[{i}].ci",
                        "an error bar is drawn where the facts hold only a spread (SD): spread is not uncertainty about an effect",
                        "drop the whisker or use the paper's interval for the difference")


# ====================================================================== 31 precision, 32 signs
def _display_number(s: str) -> Optional[tuple]:
    m = NUM_RE_LOOSE.search((s or "").replace("–", "-"))
    return (to_float(m.group(1), m.group(2)), dec_places(m.group(2)), m.group(1) in ("-", "−")) if m else None

def _outcome_values(o: dict) -> list:
    vals = []
    if isinstance(o.get("value"), (int, float)): vals.append((float(o["value"]), dec_places(repr(o["value"])), "value"))
    if vals and str(o.get("unit") or "") == "%" and (str(o.get("kind") or "") == "hazard_or_odds" or str(o.get("measure") or "").upper() in ("RR", "HR", "OR")):
        vals.append((1 + float(o["value"]) / 100, 2, "value (as a ratio: 1 + value/100)"))
    for j, g in enumerate(o.get("group_stats") or []):
        if isinstance(g.get("value"), (int, float)): vals.append((float(g["value"]), dec_places(repr(g["value"])), f"group_stats[{j}].value"))
    for j, c in enumerate(o.get("ci") or []):
        if isinstance(c, (int, float)): vals.append((float(c), dec_places(repr(c)), f"ci[{j}]"))
    return vals

def check_precision(card: dict, facts: dict, rep: GateReport) -> None:
    outs = (facts or {}).get("outcomes") or []
    for key in ("data_block", "secondary_block"):
        b = card.get(key) or {}
        for i, it in enumerate(b.get("items") or []):
            if not isinstance(it, dict): continue
            ref = it.get("ref")
            if not (isinstance(ref, int) and ref < len(outs)): continue
            o = outs[ref]; vals = _outcome_values(o)
            if not vals: continue
            disp = _display_number(str(it.get("display", "")))
            el = f"{key}.items[{i}]"
            if disp:
                dv, dd, _neg = disp
                maxd = max(d for _v, d, _p in vals)
                best = None
                for fv, fd, p in vals:
                    dd2 = min(dd, fd)
                    if round(abs(fv), dd2) == round(abs(dv), dd2): best = (fv, fd, p); break
                if best is None:
                    rep.add("G31_PRECISION", 31, "error", "data_block", el + ".display",
                            f"'{it.get('display')}' is not the paper's value ({vals[0][0]:g}) at any rounding", "print the paper's number or its editorial rounding", path=f"outcomes[{ref}]")
                elif dd > max(maxd, int(o.get("precision") or 0)):
                    rep.add("G31_PRECISION", 31, "error", "data_block", el + ".display",
                            f"'{it.get('display')}' has {dd} decimals; the paper gives {max(maxd, int(o.get('precision') or 0))}",
                            "never print more precision than the paper", path=f"outcomes[{ref}].{best[2]}")
            if isinstance(it.get("ci"), (list, tuple)) and isinstance(o.get("ci"), (list, tuple)) and len(it["ci"]) == len(o["ci"]) == 2:
                for j in (0, 1):
                    d = dec_places(repr(o["ci"][j]))
                    if round(it["ci"][j], d) != round(o["ci"][j], d):
                        rep.add("G31_PRECISION", 31, "error", "data_block", f"{el}.ci[{j}]",
                                f"interval end {it['ci'][j]:g} differs from the paper's {o['ci'][j]:g}", "copy the paper's interval", path=f"outcomes[{ref}].ci[{j}]")

LOSS_WORDS = re.compile(r"\b(lost|loss|lose|decline[ds]?|decrease[ds]?|drop(?:ped)?|fall|fell|reduction|reduced|fewer)\b", re.I)
def check_signs(card: dict, facts: dict, rep: GateReport) -> None:
    """32. Detect only: a minus sign on a magnitude drawn on a 'lost' axis, or a label whose sign differs from the value."""
    outs = (facts or {}).get("outcomes") or []
    for key in ("data_block", "secondary_block"):
        b = card.get(key) or {}
        if b.get("type") not in ("bar_h", "bar_v", "forest", "stat_tiles", "stat_row", "line_area"): continue
        axis_text = " ".join(str(b.get(k) or "") for k in ("title", "subtitle", "axis_label", "x_label"))
        lossy = bool(LOSS_WORDS.search(axis_text)); bad = []
        for i, it in enumerate(b.get("items") or []):
            if not isinstance(it, dict): continue
            disp = _display_number(str(it.get("display", ""))); v = it.get("value")
            if not disp or not isinstance(v, (int, float)): continue
            neg_label = disp[2]; el = f"{key}.items[{i}]"
            if neg_label and v > 0:
                bad.append((i, it.get("display"), v))
            elif not neg_label and v < 0:
                rep.add("G32_SIGN", 32, "error", "data_block", el, f"the label reads {it.get('display')} but the value is {v:g}", "make the label carry the sign")
            elif neg_label and v < 0 and lossy and b.get("type") in ("bar_h", "bar_v"):
                rep.add("G32_SIGN", 32, "warn", "data_block", el, f"negative value on a loss axis ('{axis_text.strip()[:40]}'): a double negative", "plot magnitudes or relabel the axis")
            ref = it.get("ref")
            if isinstance(ref, int) and ref < len(outs) and isinstance(outs[ref].get("value"), (int, float)):
                fv = outs[ref]["value"]
                if fv != 0 and abs(abs(fv) - abs(v)) < 1e-9 and (fv < 0) != (v < 0) and b.get("type") != "bar_h":
                    rep.add("G32_SIGN", 32, "error", "data_block", el, f"the facts hold {fv:g}, the block plots {v:g}", "carry the sign from the facts")

        if bad:
            extra = " on a 'lost' axis" if lossy else ""
            plots_label = b.get("type") in ("bar_h", "bar_v")          # chartgeom._signed draws the sign of the label when |label| == |value| (r4 item 32)
            rep.add("G32_SIGN", 32, "warn" if plots_label else "error", "data_block", f"{key}.items[{','.join(str(i) for i, _d, _v in bad)}]",
                    "labels read " + ", ".join(str(d) for _i, d, _v in bad) + " but the stored values are the positive " + ", ".join(f"+{v:g}" for _i, _d, v in bad) + extra
                    + (": the renderer draws the labelled (negative) sign, so the picture agrees with the label; the stored value should carry the sign"
                       if plots_label else ": the minus sign and the bar disagree"),
                    "store the signed value (or plot magnitudes with 'lost' on the axis and drop the minus)")


# ====================================================================== 33 pp vs %, 35 timepoint, 34 subgroup rows
PP_UNITS = ("pp", "percentage points", "percentage point", "percent points")
def check_pp(card: dict, facts: dict, rep: GateReport) -> None:
    outs = (facts or {}).get("outcomes") or []
    b = card.get("data_block") or {}
    block_text = " ".join(t for s, e, t in slots(card) if s in ("data_block", "headline", "dek"))
    refs = {it.get("ref") for it in (b.get("items") or []) if isinstance(it, dict) and isinstance(it.get("ref"), int)}
    for ref in sorted(r for r in refs if r < len(outs)):
        o = outs[ref]; unit = str(o.get("unit") or "").lower(); kind = str(o.get("kind") or "").lower()
        rel = kind in ("ratio", "relative") or str(o.get("measure") or "").upper() in ("HR", "OR", "RR", "IRR")
        if unit in PP_UNITS or kind in ("absolute_risk_difference", "risk_difference"):
            if re.search(r"\d\s*%", block_text) and not re.search(r"percentage point|\bpp\b|points", block_text, re.I):
                rep.add("G33_PP_VS_PERCENT", 33, "error", "data_block", f"outcomes[{ref}]", "a difference in percentages is printed as '%'", "write 'percentage points' (pp) on the axis, tile and dek")
        if rel and re.search(r"percentage point|\bpp\b", block_text, re.I):
            rep.add("G33_PP_VS_PERCENT", 33, "error", "data_block", f"outcomes[{ref}]", "a relative measure is called percentage points", "use '%' for relative change")
    # a '%' tile with no unit word anywhere in the block title/subtitle/axis for percent outcomes
    for i, it in enumerate(b.get("items") or []):
        if isinstance(it, dict) and re.search(r"\d\s*%", str(it.get("display", ""))) and isinstance(it.get("ref"), int) and it["ref"] < len(outs):
            o = outs[it["ref"]]
            if str(o.get("unit") or "").lower() in PP_UNITS and not re.search(r"pp|point", str(it.get("display")), re.I) and not re.search(r"point|pp", str(b.get("title", "")) + str(b.get("subtitle", "")), re.I):
                rep.add("G33_PP_VS_PERCENT", 33, "error", "data_block", f"data_block.items[{i}].display", f"'{it.get('display')}' is a percentage-point difference printed as a percent", "add 'points'")

TIME_RE = re.compile(r"(\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|twelve)[\s\-]*(?:days?|nights?|weeks?|months?|years?|hours?|h|min|minutes?|wk|mo|yr)\b"
                     r"|\bbaseline\b|\bfollow-?up\b|\bpost-?(?:intervention|treatment|exercise)\b|\bend of\b|\bat \d+|\bover time\b|\bone year\b|\b\d+ ?(?:y|mo)\b)", re.I)
def _facts_timepoints(card: dict, facts: dict) -> list:
    outs = (facts or {}).get("outcomes") or []; b = card.get("data_block") or {}; out = []
    for it in b.get("items") or []:
        ref = it.get("ref") if isinstance(it, dict) else None
        if isinstance(ref, int) and ref < len(outs) and outs[ref].get("timepoint"): out.append(str(outs[ref]["timepoint"]))
    f = facts or {}
    for k in ("follow_up",):
        if f.get(k): out.append(str(f[k]))
    if not out and TIME_RE.search(str(f.get("exposure") or "")): out.append(str(f["exposure"]))
    return out

def check_timepoint(card: dict, facts: dict, rep: GateReport) -> None:
    b = card.get("data_block") or {}
    if not b or b.get("type") in ("none", None): return
    exp = _facts_timepoints(card, facts)
    if not exp: return
    txt = " ".join(str(b.get(k) or "") for k in ("title", "subtitle", "x_label"))
    if b.get("type") in ("stat_tiles", "stat_row"):
        txt += " " + " ".join(str(it.get("sub") or "") + " " + str(it.get("label") or "") for it in b.get("items") or [] if isinstance(it, dict))
    if not TIME_RE.search(txt):
        rep.add("G35_TIMEPOINT", 35, "warn", "data_block", "data_block.title/subtitle",
                f"the chart does not say when the outcome was measured (the facts say: '{exp[0][:60]}')",
                "put the timepoint in the chart title or subtitle, e.g. 'after one year'")

ALL_ROW = re.compile(r"^(all|overall|pooled|total)\b", re.I)
def forest_row_roles(card: dict) -> list:
    b = card.get("data_block") or {}
    if b.get("type") != "forest": return []
    return ["pooled" if ALL_ROW.match(str(it.get("label", ""))) or it.get("pooled") else "subgroup" for it in b.get("items") or []]

def check_subgroups(card: dict, facts: dict, rep: GateReport) -> None:
    roles = forest_row_roles(card)
    if "pooled" in roles and "subgroup" in roles:
        if roles.count("pooled") == 1 and roles.count("subgroup") >= 2: return      # chartgeom.mark_pooled draws it: diamond + indented lighter rows (r4 item 34)
        b = card["data_block"]
        if not any(isinstance(it, dict) and (it.get("role") or it.get("row_kind") or it.get("pooled")) for it in b["items"]):
            rep.add("G34_SUBGROUP_STYLE", 34, "warn", "data_block", "data_block.items[].role",
                    f"a pooled row and {roles.count('subgroup')} subgroup rows are drawn alike (nothing marks which is the pooled estimate)",
                    "mark rows with item.role = 'pooled' | 'subgroup' so the chart can draw a diamond and indented lighter rows (chart agent)")


# ====================================================================== 78-80 slot hygiene
PLACEHOLDER = re.compile(r"(?<![\w])(TBD|TODO|FIXME|XXX+|lorem ipsum|placeholder|undefined|null|none|nan|n/a|\?\?+)(?![\w])|&#x?[0-9a-f]+;|&(?:amp|lt|gt|quot|apos);|\{\{|\}\}|\{%|%\}|\[object|<[a-z/]+>", re.I)
REQUIRED = [("headline", "headline.text"), ("dek", "dek"), ("takeaway", "takeaway.text"), ("foot", "citation")]

def check_hygiene(card: dict, facts: dict, rep: GateReport) -> None:
    present = {el for _s, el, _t in slots(card)}
    for slot, el in REQUIRED:
        if el not in present:
            rep.add("G79_EMPTY_SLOT", 79, "error" if el != "dek" else "warn", slot, el, "slot is empty", "fill it or remove the block that needs it")
    for i, b in enumerate(card.get("beats") or []):
        for k in ("lead", "detail"):
            if not str(b.get(k) or "").strip():
                rep.add("G79_EMPTY_SLOT", 79, "error", "beats", f"beats[{i}].{k}", "beat text is empty", "write it or drop the beat")
    for slot, el, text in slots(card):
        for m in PLACEHOLDER.finditer(text):
            tok = m.group(0)
            if tok.lower() in ("none", "null", "nan", "n/a", "undefined") and not re.fullmatch(r"\s*" + re.escape(tok) + r"\s*", text, re.I) and len(text.split()) > 3 and tok.lower() == "none":
                continue          # the English word 'none' inside a sentence ("none of the trials") is not a placeholder
            rep.add("G79_PLACEHOLDER", 79, "error", slot, el, f"placeholder or leaked markup '{tok}' in '{text[:50]}'", "write the real text; entities must not be pre-escaped")
            break
    b = card.get("data_block") or {}
    for i, it in enumerate(b.get("items") or []):
        if isinstance(it, dict) and not str(it.get("label") or "").strip():
            rep.add("G79_EMPTY_SLOT", 79, "error", "data_block", f"data_block.items[{i}].label", "item has no label", "label every row")

def badge_text(card: dict, facts: dict) -> Optional[str]:
    if card.get("badge"): return card["badge"]
    return None

def check_badge(card: dict, facts: dict, rep: GateReport) -> None:
    for el, t in (("badge", card.get("badge")), ("certainty.label", (card.get("certainty") or {}).get("label")), ("series", card.get("series"))):
        if isinstance(t, str) and len(t) > BADGE_MAX:
            rep.add("G80_BADGE_LENGTH", 80, "error", "top", el, f"'{t}' is {len(t)} characters (max {BADGE_MAX}); it will wrap", f"shorten to {BADGE_MAX} characters or fewer")

def check_takeaway_overlap(card: dict, facts: dict, rep: GateReport) -> None:
    h = card.get("headline"); h = h.get("text") if isinstance(h, dict) else h
    tk = card.get("takeaway") or {}
    t, hl = tk.get("text") or "", tk.get("highlight") or ""
    if not h or not t: return
    main = t.replace(hl, " ") if hl and hl in t else t
    # the question is whether the takeaway's own claim is the headline again: its words, minus the new (highlighted) part
    H, T = content_stems(h), content_stems(main)
    if len(T) < 3: return
    ov = len(H & T) / len(T)
    both_neg = bool(NEG_WORDS & set(words(h)) and NEG_WORDS & set(words(main)))
    if ov > OVERLAP_MAX:
        rep.add("G78_TAKEAWAY_REPEATS_HEADLINE", 78, "error", "takeaway", "takeaway.text",
                f"{ov:.0%} of the takeaway's content words are the headline's ({', '.join(sorted(H & T))[:60]})",
                "say what the reader should do or doubt, not the result again")


# ====================================================================== 76 abstract-only, 75 retraction, 73/74 draft: the decision
@dataclass
class Decision:
    action: str = "render"                  # render | draft | refuse
    draft_reasons: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    refuse_reason: str = ""
    overlay: Optional[dict] = None

    @property
    def refuse(self) -> bool: return self.action == "refuse"
    @property
    def draft(self) -> bool: return self.action == "draft"
    def as_dict(self) -> dict:
        return {"action": self.action, "draft_reasons": self.draft_reasons, "tags": self.tags, "refuse_reason": self.refuse_reason}


def inputs_from_run(run_dir) -> dict:
    """audit / verify results of an existing run: {"audit_fatal": n, "verify_verdict": str}, from pipeline.report.json."""
    p = pathlib.Path(run_dir) / "pipeline.report.json"
    try: rep = json.loads(p.read_text())
    except Exception: return {}
    out: dict = {}
    why = " ; ".join(str(x) for x in rep.get("why") or [])
    note = ((rep.get("stages") or {}).get("audit") or {}).get("note") or ""
    m = re.search(r"fatal (\d+)", note)
    if m: out["audit_fatal"] = int(m.group(1))
    else:
        m = re.search(r"(\d+) editorial rule failures", why)
        if m: out["audit_fatal"] = int(m.group(1))
    m = re.search(r"verify verdict: (\w+)", why)
    if m: out["verify_verdict"] = m.group(1)
    if "BLOCK: retracted" in why: out["retracted"] = True
    return out

def _fatal_count(inputs: dict) -> int:
    v = (inputs or {}).get("audit_fatal")
    if isinstance(v, (list, tuple, set)): return len(v)
    try: return int(v or 0)
    except (TypeError, ValueError): return 0

def decide(doc: dict, report: Optional[GateReport], inputs: Optional[dict] = None) -> Decision:
    inputs = inputs or doc.get("gate_inputs") or {}
    f = doc.get("facts") or {}; d = Decision()
    st = f.get("status") or {}
    if st.get("retracted") or inputs.get("retracted"):
        d.action, d.refuse_reason = "refuse", "the paper has been retracted"
    elif st.get("expression_of_concern"):
        d.action, d.refuse_reason = "refuse", "the journal has published an expression of concern about the paper"
    if d.refuse:
        return d
    n = _fatal_count(inputs)
    if n: d.draft_reasons.append(f"{n} editorial rule failure{'s' if n != 1 else ''} (audit fatal)")
    if (inputs or {}).get("verify_verdict") == "needs_person": d.draft_reasons.append("verification verdict: needs a person")
    if (inputs or {}).get("verify_verdict") == "gate_bug": d.draft_reasons.append("a verification gate crashed")
    if report is not None and report.errors:
        d.draft_reasons.append(f"{len(report.errors)} render gate error{'s' if len(report.errors) != 1 else ''}")
    cov = f.get("coverage") or {}
    if cov.get("abstract_only") or cov.get("source") in ("abstract", "pubmed_abstract"):
        d.tags.append("FROM THE ABSTRACT ONLY")
    if d.draft_reasons: d.action = "draft"
    d.overlay = {"draft": d.draft, "tags": list(d.tags), "reasons": list(d.draft_reasons), "gate_version": GATE_VERSION} if (d.draft or d.tags) else None
    return d

def overlay_for(doc: dict) -> Optional[dict]:
    """What render_html hands the template: set by apply(); a doc that never went through apply() still gets the
    facts-only tags (abstract-only) and refusals never reach here."""
    g = doc.get("gate")
    if isinstance(g, dict): return g or None
    d = decide(doc, None, doc.get("gate_inputs"))
    return d.overlay

def evaluate(doc: dict, inputs: Optional[dict] = None) -> GateReport:
    card, facts = doc.get("card") or {}, doc.get("facts") or {}
    rep = GateReport()
    for fn in (trace_card_numbers, check_arms, check_counts, check_n, check_design_labels, check_scales, check_null_card, check_spread,
               check_precision, check_signs, check_pp, check_timepoint, check_subgroups, check_hygiene, check_badge, check_takeaway_overlap):
        try:
            fn(card, facts, rep)
        except Exception as e:            # a gate bug is a finding, never a crash of the render
            rep.add("G00_GATE_BUG", 0, "warn", "gates", fn.__name__, f"{type(e).__name__}: {e}", "fix the gate")
    return rep

def apply(doc: dict, inputs: Optional[dict] = None) -> Decision:
    """Evaluate, decide, and store the overlay on the doc so render_html draws it.  Returns the Decision (report on .report)."""
    inputs = inputs if inputs is not None else doc.get("gate_inputs") or {}
    rep = evaluate(doc, inputs); d = decide(doc, rep, inputs); d.report = rep           # type: ignore[attr-defined]
    doc["gate"] = d.overlay or {}
    doc["gate_decision"] = d.as_dict()
    return d


# ====================================================================== 75: the notice that replaces a retracted card
def refusal_html(doc: dict, reason: str = "") -> str:
    f = doc.get("facts") or {}; ids = (f.get("coverage") or {}).get("ids") or {}
    pmid = ids.get("pmid") or ""; st = f.get("status") or {}
    why = reason or ("the paper has been retracted" if st.get("retracted") else "the journal has published an expression of concern")
    e = _html.escape
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>No card: {e(why)}</title>
<style>body{{margin:0;background:#f8f6f1;font-family:Inter,system-ui,sans-serif;color:#1a1a1a}}
.card{{width:1080px;height:1350px;box-sizing:border-box;padding:96px 80px;display:flex;flex-direction:column;justify-content:center;gap:28px}}
.k{{font:700 22px/1 ui-monospace,monospace;letter-spacing:.16em;color:#c8102e;text-transform:uppercase}}
h1{{font-size:64px;line-height:1.05;margin:0}} p{{font-size:30px;line-height:1.4;color:#444;margin:0}}</style></head>
<body><div class="card" data-slot="notice"><div class="k">No card produced</div>
<h1>This paper is not summarised: {e(why)}.</h1>
<p>{('PMID ' + e(str(pmid)) + '. ') if pmid else ''}A card would present withdrawn or doubted results as evidence, so none was made. Checked {e(str(st.get('checked') or 'recently'))} against {e(str(st.get('source') or 'the publisher record'))}.</p></div></body></html>"""

def write_notice(doc: dict, out: pathlib.Path, stem: str, reason: str = "") -> pathlib.Path:
    out = pathlib.Path(out); out.mkdir(parents=True, exist_ok=True)
    p = out / f"{stem}.notice.html"; p.write_text(refusal_html(doc, reason))
    return p


# ====================================================================== DOM checks on the real render (browser)
DOM_JS = r"""
(() => {
  const card = document.querySelector('.card'); const cr = card.getBoundingClientRect();
  const TICK = '.axis span, .grid .gl span, text.tk, .tk, .pax span, .bax span, .pax, .bax';
  const slotOf = e => { const s = e.closest('[data-slot]'); return s ? s.dataset.slot : (e.closest('.foot') ? 'foot' : '?'); };
  const texts = [];
  const walker = document.createTreeWalker(card, NodeFilter.SHOW_TEXT);
  let n; while ((n = walker.nextNode())) {
    const t = n.textContent; if (!t.trim()) continue;
    const el = n.parentElement; if (!el) continue;
    if (el.closest('style,script,.sr-only')) continue;
    if (el.closest(TICK)) continue;                       // computed axis ticks are not claims
    if (el.closest('.gate-mark,.gate-tag')) continue;     // the DRAFT / abstract-only overlay carries no numbers
    texts.push({slot: slotOf(el), el: (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/)[0] : el.tagName.toLowerCase()), text: t.trim()});
  }
  // layout: text ranges outside the card or clipped by an overflow:hidden ancestor; overlaps between unrelated text boxes
  const problems = [];
  const boxes = [];
  const w2 = document.createTreeWalker(card, NodeFilter.SHOW_TEXT);
  while ((n = w2.nextNode())) {
    if (!n.textContent.trim()) continue; const el = n.parentElement; if (!el || el.closest('style,script,.gate-mark,.gate-tag,.sr-only,.ct')) continue;
    const r = document.createRange(); r.selectNodeContents(n); const rects = [...r.getClientRects()].filter(q => q.width > 1 && q.height > 1);
    if (!rects.length) continue;
    const b = rects.reduce((a, q) => ({l: Math.min(a.l, q.left), t: Math.min(a.t, q.top), r: Math.max(a.r, q.right), b: Math.max(a.b, q.bottom)}), {l: 1e9, t: 1e9, r: -1e9, b: -1e9});
    const desc = (slotOf(el) + ' ' + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/)[0] : el.tagName.toLowerCase())) + ' "' + n.textContent.trim().slice(0, 28) + '"';
    if (b.l < cr.left - 1 || b.r > cr.right + 1 || b.t < cr.top - 1 || b.b > cr.bottom + 1) problems.push({kind: 'outside', where: desc});
    for (let a = el; a && a !== card; a = a.parentElement) {
      const cs = getComputedStyle(a);
      if ((cs.overflow === 'hidden' || cs.overflowY === 'hidden') && a.clientHeight > 0 && (b.b > a.getBoundingClientRect().bottom + 2 || b.t < a.getBoundingClientRect().top - 2)) { problems.push({kind: 'clipped', where: desc}); break; }
      if ((cs.overflowX === 'hidden') && a.clientWidth > 0 && (b.r > a.getBoundingClientRect().right + 2)) { problems.push({kind: 'clipped', where: desc}); break; }
    }
    boxes.push({el, desc, rects: rects.map(q => { const lh = (parseFloat(getComputedStyle(el).lineHeight) * (parseFloat(document.body.style.zoom) || 1)) || q.height, pad = lh < q.height ? (q.height - lh) / 2 : 0;   // glyph boxes taller than the leading are not an overlap
      return {l: q.left, t: q.top + pad, r: q.right, b: q.bottom - pad}; }), ...b});
  }
  const inter = (p, q) => p.l < q.r - 2 && q.l < p.r - 2 && p.t < q.b - 2 && q.t < p.b - 2;
  for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
    const p = boxes[i], q = boxes[j];
    if (p.el.contains(q.el) || q.el.contains(p.el) || p.el === q.el) continue;
    if (p.el.closest('svg') && q.el.closest('svg')) continue;                 // chart labels are laid out by the chart
    if (p.rects.some(a => q.rects.some(c => inter(a, c)))) problems.push({kind: 'overlap', where: p.desc + '  x  ' + q.desc});
  }
  const bd = document.querySelector('.badge'); let badge = null;
  if (bd) { const lh = parseFloat(getComputedStyle(bd).lineHeight) || bd.getBoundingClientRect().height; badge = {text: bd.innerText, lines: Math.round(bd.getBoundingClientRect().height / (parseFloat(getComputedStyle(bd).fontSize) * 1.5)), h: bd.getBoundingClientRect().height, fs: parseFloat(getComputedStyle(bd).fontSize)}; }
  const cert = document.querySelector('.cert'); let certb = null;
  if (cert) certb = {text: cert.innerText, h: cert.getBoundingClientRect().height, fs: parseFloat(getComputedStyle(cert).fontSize)};
  const tk = document.querySelector('.takeaway'), tx = tk && tk.querySelector('.tx');
  if (tk && tx && tx.scrollHeight > tk.clientHeight + 6) problems.push({kind: 'clipped', where: 'takeaway .tx (text taller than its bar)'});
  const mark = document.querySelector('.gate-mark'); const tags = [...document.querySelectorAll('.gate-tag')].map(e => e.innerText);
  return {texts, problems, badge, cert: certb, mark: !!mark, tags, card: {w: cr.width, h: cr.height}};
})()
"""

def dom_inspect(html_path, width: int = 1080, height: int = 1350, pw=None, zoom: float = 1.0) -> dict:
    import render as _R                               # session-aware Playwright (inside render_session a second sync_playwright() fails)
    with _R._pw(pw) as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": int(width), "height": int(height)})
        pg.goto(pathlib.Path(html_path).resolve().as_uri()); pg.wait_for_load_state("networkidle")
        pg.evaluate("document.fonts.ready")
        if zoom != 1.0: pg.evaluate(f"document.body.style.zoom = {zoom}")
        r = pg.evaluate(DOM_JS); b.close()
    return r

def trace_dom(dom: dict, doc: dict, rep: GateReport) -> None:
    """23, hard gate on the rendered DOM: every number the reader sees, with the facts path or an error that names the slot."""
    idx = facts_index(doc.get("facts") or {})
    ids = (((doc.get("facts") or {}).get("coverage") or {}).get("ids")) or {}
    by_slot: dict = {}
    for t in dom["texts"]: by_slot.setdefault((t["slot"], t["el"]), []).append(t["text"])
    seen = set()
    for (slot, el), parts in by_slot.items():
        text = " ".join(parts)
        for val, dec, raw, start in numbers_in(text):
            if _is_free(SLOT_MAP.get(slot, slot), text, start, val, raw): continue
            if re.search(r"pmid\s*[:\s]*$", text[max(0, start - 8):start].lower()): continue
            tail = text[start + len(raw):start + len(raw) + 2]
            pct = tail.lstrip().startswith("%")
            path = trace_value(val, dec, idx, pct=pct)
            key = (slot, raw)
            if path is None:
                pool = [(v, d) for v, d, _r, s in numbers_in(text) if s != start]
                for (a, da), (b2, db) in combinations(pool, 2):
                    if round(abs(a - b2), dec) == round(abs(val), dec) or round(a + b2, dec) == round(abs(val), dec) or (b2 and round(abs((a - b2) / b2 * 100), dec) == round(abs(val), dec)):
                        path = f"derived from {a:g} and {b2:g}"; break
            if path is None and key not in seen:
                seen.add(key)
                rep.add("G23_NUMBER_UNTRACED", 23, "error", SLOT_MAP.get(slot, slot), f"rendered {el}", f"the rendered number {raw} is not in the facts", "remove it or add its source to the facts")
            elif path is not None:
                rep.traced.setdefault(f"dom|{slot}|{raw}", path)

SLOT_MAP = {"hd": "headline", "mid": "data_block", "boundary": "evidence_boundary", "stats": "stats", "top": "top", "foot": "foot", "takeaway": "takeaway", "dek": "dek", "beats": "beats", "ctx": "ctx"}

def post_render(html_path, doc: dict, decision: Optional[Decision], out=None, stem: Optional[str] = None, pw=None, width: int = 1080, height: int = 1350) -> GateReport:
    """DOM gates on the final HTML: number trace (23), layout at 1080 and at phone width 390 (77), badge wrap (80), overlay present (73-76)."""
    rep = GateReport()
    d1080 = dom_inspect(html_path, width, height, pw=pw)
    trace_dom(d1080, doc, rep)
    d390 = dom_inspect(html_path, 390, int(390 * height / width), pw=pw, zoom=390 / width)
    for tag, dom in (("1080", d1080), ("390", d390)):
        seen = set()
        for p in dom["problems"]:
            k = (p["kind"], p["where"])
            if k in seen: continue
            seen.add(k)
            slot = p["where"].split(" ")[0]
            rep.add("G77_LAYOUT", 77, "error", SLOT_MAP.get(slot, slot), f"{p['kind']} @ {tag}px", f"{p['kind']}: {p['where']}",
                    "shorten the copy in that slot or give the block more room")
    for nm, el in (("badge", d1080.get("badge")), ("certainty", d1080.get("cert"))):
        if el and el["h"] > el["fs"] * 2.4:
            rep.add("G80_BADGE_LENGTH", 80, "error", "top", nm, f"'{el['text']}' wraps onto {round(el['h'] / (el['fs'] * 1.5))} lines", f"shorten to {BADGE_MAX} characters or fewer")
    if decision is not None:
        if decision.draft and not d1080["mark"]:
            rep.add("G73_NO_DRAFT_MARK", 73, "error", "card", "gate-mark", "the card is a draft but the DRAFT watermark is not in the render", "render with the doc's gate overlay")
        for t in decision.tags:
            if t not in d1080["tags"]:
                rep.add("G76_NO_TAG", 76, "error", "card", "gate-tag", f"the tag '{t}' is not in the render", "render with the doc's gate overlay")
    if out is not None and stem:
        out = pathlib.Path(out); (out / f"{stem}.cardgates.post.json").write_text(json.dumps(rep.as_dict(), indent=1, ensure_ascii=False))
    return rep


def write_report(out, stem: str, pre: GateReport, post: Optional[GateReport], decision: Decision) -> pathlib.Path:
    out = pathlib.Path(out); p = out / f"{stem}.cardgates.json"
    data = {"gate_version": GATE_VERSION, "decision": decision.as_dict(), "pre": pre.as_dict(), "post": post.as_dict() if post else None}
    p.write_text(json.dumps(data, indent=1, ensure_ascii=False)); return p


# ====================================================================== CLI: python render_gates.py runs/<slug>/doc.json [--run-dir DIR]
def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Run the static render gates on a doc.json and print every finding.")
    ap.add_argument("doc"); ap.add_argument("--run-dir"); ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    p = pathlib.Path(a.doc); doc = json.loads(p.read_text())
    inputs = inputs_from_run(a.run_dir or p.parent)
    d = apply(doc, inputs); rep = d.report
    if a.json: print(json.dumps({"decision": d.as_dict(), **rep.as_dict()}, indent=1, ensure_ascii=False))
    else:
        print(f"{p.parent.name}: decision={d.action} reasons={d.draft_reasons} tags={d.tags}")
        for f in rep.findings: print(f"  {f.severity.upper():5} {f.line()}")
        print(f"  traced numbers: {len(rep.traced)}")
    return 1 if rep.errors else 0

if __name__ == "__main__":
    raise SystemExit(main())
