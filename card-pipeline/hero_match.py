#!/usr/bin/env python3
"""
hero_match.py — items 53-58: the hero image must match what the card is ABOUT, and say why it was chosen.

The old chooser was a keyword macro (`category()` in template.html) and a substring match in hero.py. It produced a shoulder
muscle drawing for walking speed (sarcopenia) and a spine segment for hip bone density (vest). This module replaces it with a
TAGGED MATCH:

  1. The card's OUTCOME is read as body sites (hip, spine, walking/leg, brain, heart ...) with word-boundary patterns
     (`SITES`), from what the card says: headline + data-block title first, then the data-block row labels, then the facts'
     outcome names.  `rem` no longer matches "remission" or "tremor".
  2. Every library image carries tags in assets/library/manifest.json: `sites` (what it depicts exactly), `systems` (the
     body system it may stand for when the outcome names no finer site), `generic`, `implies` (an intervention the picture
     suggests: pills, nutrient particles ...), `depicts` (the intervention it shows: coffee, vest, stairs ...), `approved`.
  3. match levels:  3  an image whose `sites` contain a site the outcome names
                    2  an image that depicts the TESTED intervention (exposure text matches its `depicts` terms)
                    1  a `generic` image for the outcome's body system, only when the outcome names no specific site
     A specific site that no image covers (hip, walking) is NOT downgraded to a neighbouring organ: the card gets NO image,
     the reason and the library image it needs are recorded (`needs`).
  4. item 57: an image that implies an intervention (a pill, nutrient particles) is rejected unless the trial tested it.
  5. item 56: a hero is optional; when the data block needs the width (many rows, wide chart) the hero is dropped, reason recorded.
  6. item 55: every decision is returned as a dict (`decide`) and rendered one-line by `explain` for the review queue.
  7. item 58: images that were generated (never by this module) enter as `status: pending_approval` and are used only after
     `approve(tag, by)`; nothing in the render path generates.

No model calls. Deterministic.
"""
from __future__ import annotations
import json, pathlib, re

HERE = pathlib.Path(__file__).resolve().parent
LIB = HERE / "assets" / "library"
MANIFEST = LIB / "manifest.json"

ALLOW_INTERVENTION_HERO = True      # level 2: a picture of the tested intervention is a valid hero when no anatomy image fits

# ---------------------------------------------------------------- body-site ontology
# site id -> (system, specific?, pattern).  specific=False: a system-level concept with no finer anatomy (bone density in
# general, cognition, sleep) which a `generic` image of that system may stand for.
def _p(*words):
    return re.compile(r"(?<![A-Za-z])(?:" + "|".join(words) + r")", re.I)

SITES = {
    "hip":            ("skeletal",       True,  _p(r"hips?\b", r"femor\w*", r"femur\b", r"trochant\w*")),
    "spine":          ("skeletal",       True,  _p(r"spine\b", r"spinal\b", r"vertebr\w*", r"lumbar\b")),
    "bone":           ("skeletal",       False, _p(r"bones?\b", r"bmd\b", r"osteopor\w*", r"osteopen\w*", r"fractur\w*", r"trabecular\b", r"bone mineral")),
    "walking":        ("musculoskeletal", True, _p(r"gait\b", r"walking\b", r"walk speed", r"stride\b", r"locomot\w*", r"timed up and go", r"\btug\b",
                                                   r"sit-to-stand", r"chair stand", r"5sts\b", r"mobility\b", r"steps per day")),
    "stair_climbing": ("musculoskeletal", True, _p(r"stair\w*")),
    "shoulder_arm":   ("muscle",         True,  _p(r"shoulders?\b", r"deltoid\w*", r"biceps?\b", r"triceps?\b", r"upper[- ]arm", r"rotator")),
    "hand_grip":      ("muscle",         True,  _p(r"grip\b", r"handgrip", r"hand grip", r"forearm\b")),
    "skeletal_muscle": ("muscle",        False, _p(r"muscle\b", r"muscles\b", r"lean mass", r"fat-free mass", r"sarcopeni\w*", r"myofibr\w*", r"muscle fib\w*",
                                                   r"skeletal muscle", r"sprint\w*", r"anaerobic", r"muscle power", r"strength\b")),
    "brain":          ("brain",          False, _p(r"brain\b", r"cogniti\w*", r"memory\b", r"dementia\b", r"alzheimer\w*", r"executive function", r"attention\b",
                                                   r"neurodegenerat\w*", r"mci\b")),
    "sleep":          ("brain",          False, _p(r"sleep\w*", r"insomnia\b", r"nocturnal")),
    "mood":           ("brain",          False, _p(r"depress\w*", r"anxiety\b", r"mood\b")),
    "substantia_nigra": ("brain",        True,  _p(r"parkinson\w*", r"substantia nigra", r"dopamin\w*")),
    "myelin":         ("nerve",          True,  _p(r"myelin\w*", r"multiple sclerosis", r"neuropath\w*", r"demyelinat\w*")),
    "heart":          ("cardiovascular", False, _p(r"heart\b", r"cardiac\b", r"cardiovascular", r"ejection fraction", r"heart failure", r"cardiomyopath\w*")),
    "heart_rhythm":   ("cardiovascular", True,  _p(r"atrial fibrillation", r"arrhythm\w*", r"sinus node", r"afib\b")),
    "blood_pressure": ("cardiovascular", False, _p(r"blood pressure", r"systolic", r"diastolic", r"hypertens\w*", r"\bsbp\b", r"\bdbp\b")),
    "artery":         ("cardiovascular", True,  _p(r"coronary", r"atheroscler\w*", r"plaque\b", r"arter(?:y|ies|ial)\b", r"carotid", r"intima", r"stroke\b", r"myocardial infarction")),
    "liver":          ("liver",          True,  _p(r"liver\b", r"hepat\w*", r"\bmash\b", r"masld\b", r"nafld\b", r"steatotic", r"steatohepatitis", r"fatty liver")),
    "kidney":         ("kidney",         True,  _p(r"kidneys?\b", r"renal\b", r"egfr\b", r"\bckd\b", r"creatinine", r"albuminuria")),
    "gut":            ("gut",            False, _p(r"\bgut\b", r"bowel", r"colon\w*", r"intestin\w*", r"stool", r"\bibs\b", r"constipation", r"diarrh\w*")),
    "microbiome":     ("gut",            True,  _p(r"microbio\w*", r"microbes?\b", r"bifido\w*", r"lactobac\w*", r"alpha-diversity", r"urolithin\w*", r"probiotic\w*", r"synbiotic\w*")),
    "stomach":        ("gut",            True,  _p(r"stomach\b", r"gastric\b", r"reflux\b", r"gerd\b")),
    "lung":           ("lung",           False, _p(r"lungs?\b", r"copd\b", r"asthma\b", r"pulmonary", r"fev1\b", r"respirat\w*")),
    "eye":            ("eye",            False, _p(r"\beyes?\b", r"macular\w*", r"retina\w*", r"myopia\b", r"glaucoma\b", r"vision\b")),
    "ear":            ("ear",            False, _p(r"hearing\b", r"tinnitus\b", r"cochlea\w*", r"deaf\w*")),
    "skin":           ("skin",           False, _p(r"\bskin\b", r"melanoma\b", r"dermat\w*", r"wrinkl\w*", r"sunburn\w*")),
    "glucose":        ("endocrine",      False, _p(r"glucose", r"glycaemi\w*", r"glycemi\w*", r"hba1c", r"insulin\w*", r"diabet\w*")),
    "pancreas":       ("endocrine",      True,  _p(r"pancrea\w*", r"beta[- ]cell")),
    "blood_marker":   ("blood",          False, _p(r"cholesterol", r"\bldl\b", r"triglycerid\w*", r"serum\b", r"plasma\b", r"hemoglobin", r"ferritin", r"b12\b", r"vitamin d level", r"25\(oh\)")),
    "weight":         ("metabolic",      False, _p(r"body weight", r"weight loss", r"\bbmi\b", r"obes\w*", r"waist")),
}
# sites that have a pencil sketch in template.html `sketch()`: site -> sketch category (others -> generic)
SKETCH = {"brain": "brain", "sleep": "brain", "mood": "brain", "heart": "heart", "heart_rhythm": "heart", "artery": "heart", "blood_pressure": "heart",
          "gut": "gut", "microbiome": "gut", "stomach": "gut", "skeletal_muscle": "muscle", "shoulder_arm": "muscle", "lung": "lungs",
          "bone": "bone", "spine": "bone", "blood_marker": "blood"}
FOOD_RE = _p(r"berr\w*", r"coffee", r"rice\b", r"potato\w*", r"pasta\b", r"bowl\b", r"food\w*", r"fruit\w*", r"meal\w*", r"diet\w*", r"milk\b")
STAIRS_RE = _p(r"stair\w*")

def sites_in(text: str) -> list:
    """Site ids named in `text`, in ontology order, with the matched words: [(site, [words])]."""
    out = []
    for sid, (_sys, _spec, rx) in SITES.items():
        m = [x.group(0).strip().lower() for x in rx.finditer(text or "")]
        if m: out.append((sid, sorted(set(m))))
    return out

def category(subject: str) -> str:
    """Sketch category for the template's pencil placeholders (replaces the substring macro; word boundaries, ontology order)."""
    s = subject or ""
    if STAIRS_RE.search(s): return "stairs"
    for sid, _w in sites_in(s):
        if sid in SKETCH: return SKETCH[sid]
    if FOOD_RE.search(s): return "food"
    return "generic"

# ---------------------------------------------------------------- the card's outcome text, tiered
def _items(b):
    return [str(it.get("label") or "") for it in (b or {}).get("items") or [] if isinstance(it, dict)]

def outcome_tiers(card: dict, facts: dict | None) -> list:
    """[(tier name, text)]: what the card says first, then its rows, then the facts' outcome names. The first tier that names
    a body site decides the hero (the card's headline claim is what the picture has to agree with)."""
    c, f = card or {}, facts or {}
    hl = (c.get("headline") or {}); hl = hl.get("text") if isinstance(hl, dict) else str(hl or "")
    db, sb = c.get("data_block") or {}, c.get("secondary_block") or {}
    t1 = " . ".join(str(x) for x in (hl, db.get("title"), db.get("subtitle")) if x)
    t2 = " . ".join(_items(db) + [str(sb.get("title") or "")] + _items(sb))
    outs = f.get("outcomes") or []
    refs = [it.get("ref") for it in db.get("items") or [] if isinstance(it, dict) and isinstance(it.get("ref"), int)]
    t3 = " . ".join(str(outs[i].get("name") or "") for i in refs if i < len(outs)) or " . ".join(str(o.get("name") or "") for o in outs[:4])
    return [("headline+data title", t1), ("data rows", t2), ("facts outcomes", t3)]

def exposure_text(card: dict, facts: dict | None) -> str:
    f = facts or {}
    g = " ".join(str((x or {}).get("label") or (x or {}).get("name") or x) if not isinstance(x, str) else x for x in (f.get("groups") or []))
    return " . ".join(str(x) for x in (f.get("exposure"), f.get("exposure_detail"), g) if x)

# exposure classes: what a picture may suggest was tested
CLASS_RE = {
    "nutrient":  _p(r"supplement\w*", r"capsule\w*", r"tablet\w*", r"vitamin\w*", r"protein", r"amino", r"leucine", r"creatine", r"extract", r"powder",
                    r"milk", r"whey", r"nutrition\w*", r"diet\w*", r"food\w*", r"caffeine", r"coffee", r"probiotic\w*", r"synbiotic\w*", r"fiber", r"fibre",
                    r"mg\b", r"dose\b", r"carbohydrate\w*", r"drink\w*"),
    "drug":      _p(r"drug", r"tablet\w*", r"capsule\w*", r"pill\w*", r"semaglutide", r"statin", r"placebo", r"medication\w*", r"inhibitor", r"agonist", r"mg\b"),
    "exercise":  _p(r"exercis\w*", r"training", r"resistance", r"aerobic", r"walking", r"stair\w*", r"yoga", r"tai chi", r"physical activity"),
    "device":    _p(r"vest\b", r"device\w*", r"hearing aid\w*", r"wearable", r"cuff", r"monitor\w*"),
}

def exposure_classes(text: str) -> set:
    return {k for k, rx in CLASS_RE.items() if rx.search(text or "")}

# ---------------------------------------------------------------- manifest
def load_manifest() -> dict:
    try: return json.loads(MANIFEST.read_text())
    except (OSError, ValueError): return {}

def _entry(man, tag):
    e = man.get(tag)
    return e if isinstance(e, dict) else ({"file": e} if e else {})

def _file(ent, tag):
    f = ent.get("file")
    cands = [pathlib.Path(f) if f and pathlib.Path(f).is_absolute() else (HERE / f if f else None)]
    cands += [LIB / f"{tag}{x}" for x in (".png", ".jpg", ".jpeg", ".webp")]
    return next((c for c in cands if c and c.exists()), None)

def tagged_library() -> dict:
    """tag -> {entry..., 'path': Path|None, 'usable': bool, 'why_unusable': str|None}. usable = file present, approved, ready."""
    man, out = load_manifest(), {}
    for tag, ent in man.items():
        ent = dict(_entry(man, tag)); p = _file(ent, tag); ent["path"] = p
        why = None
        if p is None: why = "pending: no image file yet"
        elif ent.get("status") == "pending_approval" or ent.get("approved") is False: why = "generated image awaiting human approval"
        ent["usable"] = why is None; ent["why_unusable"] = why; out[tag] = ent
    return out

def tag_for_file(path, lib=None):
    """Manifest tag of an image file (by resolved path or name), or None when the file is not in the library."""
    if not path: return None
    name = pathlib.Path(str(path).replace("file://", "")).stem
    lib = lib if lib is not None else tagged_library()
    try: rp = pathlib.Path(str(path).replace("file://", "")); rp = (rp if rp.is_absolute() else HERE / rp).resolve()
    except OSError: rp = None
    for tag, ent in lib.items():
        if ent.get("path") and rp and pathlib.Path(ent["path"]).resolve() == rp: return tag
    return name if name in lib else None

def approve(tag: str, by: str, note: str = "") -> dict:
    """58. One-time human approval of a generated image: only approved images are ever used as heroes afterwards."""
    man = load_manifest(); ent = dict(_entry(man, tag))
    if not ent: raise KeyError(tag)
    ent.update(approved=True, approved_by=by, status="ready");
    if note: ent["approval_note"] = note
    man[tag] = ent; MANIFEST.write_text(json.dumps(man, indent=1)); return ent

def submit_generated(tag: str, file: str, prompt: str, sites: list, systems: list | None = None, by: str = "generator") -> dict:
    """58. A generated hero enters the library as pending_approval with its tags; it is invisible to `decide` until approved."""
    man = load_manifest()
    man[tag] = {"file": str(file), "prompt": prompt, "status": "pending_approval", "approved": False, "kind": "anatomy", "sites": sites,
                "systems": systems or [], "generic": False, "generated_by": by}
    MANIFEST.write_text(json.dumps(man, indent=1)); return man[tag]

# ---------------------------------------------------------------- width demand (item 56)
def width_demand(card: dict) -> str | None:
    """Reason the data block needs the hero's column, else None. Deterministic row/series counts; the render-time
    measured check (hero column collapsing to a sliver, layout_check) is the second line of defence."""
    b = (card or {}).get("data_block") or {}; t = b.get("type"); items = b.get("items") or []
    n = len(items)
    if b.get("wide") or b.get("needs_width"): return "data block marked wide"
    if t in ("forest", "bar_h") and n >= 8: return f"{t} with {n} rows needs the width"
    if t == "stat_row" and n >= 5: return f"stat_row with {n} items needs the width"
    if t == "line_area": return "line chart: its labels are drawn with the chart, a half-width column shrinks them below the legibility floor"
    if t in ("timeline", "state_table", "pathway") and n >= 6: return f"{t} with {n} entries needs the width"
    if t in ("stacked_100", "dotmatrix", "isotype") and n >= 7: return f"{t} with {n} rows needs the width"
    return None

# ---------------------------------------------------------------- the decision
def _terms_match(terms, text):
    return [t for t in terms or [] if re.search(r"(?<![A-Za-z])" + re.escape(t), text or "", re.I)]

def _score(tag, ent, S, spec_sites, exp_text, exp_cls):
    """(level, matched words, reject reason|None) for one image against the outcome sites S ({site: words})."""
    if ent.get("implies"):                                              # 57: no pills for an exercise trial
        need = set(ent["implies"])
        if not (need & exp_cls):
            return 0, [], f"implies {sorted(need)} but the trial tested {sorted(exp_cls) or 'no such intervention'}"
    sites = set(ent.get("sites") or [])
    hit = sorted(sites & set(S))
    if hit: return 3, [w for s in hit for w in S[s]], None
    if ALLOW_INTERVENTION_HERO and ent.get("depicts"):
        words = _terms_match(ent.get("depicts_terms") or [], exp_text)
        if words: return 2, words, None
    if not spec_sites and ent.get("generic") and set(ent.get("systems") or []) & {SITES[s][0] for s in S}:
        sysm = sorted(set(ent["systems"]) & {SITES[s][0] for s in S})
        return 1, [w for s in S if SITES[s][0] in sysm for w in S[s]], None
    return 0, [], None

def decide(card: dict, facts: dict | None = None) -> dict:
    """Pick (or refuse) the hero for a card. Returns
      {image, tag, level, matched, text_tier, outcome_sites, rejected:[{tag,why}], needs:[tags], reason, mode, dropped_for_width}
    `image` is a repo-relative path or None. A pinned card.hero.image is verified against the same rules (mode pinned-ok /
    pinned-rejected); an untagged pinned image is rejected unless card.hero.approved is true."""
    c = card or {}; h = c.get("hero") or {}
    lib = tagged_library()
    exp_text = exposure_text(c, facts); exp_cls = exposure_classes(exp_text)
    d = {"image": None, "tag": None, "level": 0, "matched": [], "text_tier": None, "outcome_sites": [], "rejected": [], "needs": [],
         "reason": "", "mode": "auto", "dropped_for_width": None, "exposure_classes": sorted(exp_cls)}
    tier, S = None, {}
    for name, text in outcome_tiers(c, facts):
        found = sites_in(text)
        if found: tier, S = name, {sid: words for sid, words in found}; break
    d["text_tier"], d["outcome_sites"] = tier, sorted(S)
    spec_sites = [s for s in S if SITES[s][1]]
    cands = []
    for tag, ent in lib.items():
        if not ent["usable"]:
            continue
        lv, words, bad = _score(tag, ent, S, spec_sites, exp_text, exp_cls)
        if bad: d["rejected"].append({"tag": tag, "why": bad})
        elif lv: cands.append((lv, len(words), -int(ent.get("preference", 50)), tag, words))
    cands.sort(reverse=True)
    pinned = h.get("image")
    if pinned and h.get("placement") != "none" and not h.get("approved"):
        ptag = tag_for_file(pinned, lib)
        if ptag is None:
            d.update(mode="pinned-rejected", reason=f"pinned image {pathlib.Path(str(pinned)).name} is not in the tagged library: cannot verify it matches the outcome")
            return _finish(d, c, lib)
        ok = next((x for x in cands if x[3] == ptag), None)
        d["mode"] = "pinned-ok" if ok else "pinned-rejected"
        if not ok:
            why = next((r["why"] for r in d["rejected"] if r["tag"] == ptag), None) or (lib[ptag].get("why_unusable")) or \
                  f"{ptag} depicts {sorted(lib[ptag].get('sites') or [])}, the outcome is {sorted(S) or 'unclassified'}"
            d["reason"] = f"pinned hero {ptag} dropped: {why}"
            d["rejected"].append({"tag": ptag, "why": why})
            if cands: d["mode"] = "pinned-replaced"; d["reason"] += " (replaced by the best tagged match)"      # recorded, never silent
        else:
            cands = [ok]
    if cands:
        lv, _nw, _pref, tag, words = cands[0]
        d.update(tag=tag, level=lv, matched=words, image=str(pathlib.Path(lib[tag]["path"]).relative_to(HERE)) if _inside(lib[tag]["path"]) else str(lib[tag]["path"]),
                 reason=(d["reason"] + "; " if d["reason"] else "") + f"{tag}: level {lv} ({ {3: 'outcome site', 2: 'tested intervention', 1: 'body system'}[lv] }) matched {words} in {tier or 'exposure'}")
    elif not d["reason"]:
        needs = [t for t, e in lib.items() if set(e.get("sites") or []) & set(S) and not e["usable"]]
        if not needs and spec_sites: needs = [f"<{'/'.join(spec_sites)}>"]
        d["needs"] = needs
        if not S: d["reason"] = "no body site recognised in the headline, data block or outcomes: no hero"
        elif needs: d["reason"] = f"outcome site {sorted(S)} has no usable library image (needs {needs}): no hero"
        else: d["reason"] = f"no library image depicts {sorted(S)}: no hero"
    return _finish(d, c, lib)

def _inside(p):
    try: pathlib.Path(p).resolve().relative_to(HERE); return True
    except ValueError: return False

def _finish(d, c, lib):
    why = width_demand(c)
    if d["image"] and why and (c.get("hero") or {}).get("placement") in (None, "left_column", "right_column", "beside", "pair"):
        d["dropped_for_width"] = why; d["reason"] += f"; hero dropped: {why}"; d["image"] = None
    return d

def explain(d: dict) -> str:
    """One line for the review queue / fit.json."""
    pick = d.get("tag") or "none"
    rej = "; rejected " + ", ".join(f"{r['tag']} ({r['why']})" for r in d.get("rejected") or [] if r.get("why")) if d.get("rejected") else ""
    return f"hero {pick} [{d.get('mode')}] outcome sites {d.get('outcome_sites')}: {d.get('reason')}{rej}"

def apply(card: dict, facts: dict | None = None) -> dict:
    """Mutate `card.hero` with the decision: image set or cleared, placement 'none' when no image, `decision` recorded."""
    h = card.setdefault("hero", {})
    if h.get("images") and not h.get("image"):                 # multi-image band: each cell is chosen by hand, not verified here
        h["decision"] = {"image": None, "mode": "band-unverified", "reason": "hero.images band is author-chosen; not verified by the matcher"}
        return card
    d = decide(card, facts)
    if h.get("approved") and h.get("image"):
        d.update(mode="approved-override", image=h["image"], reason="hero.approved: author-approved image kept")
    if d["image"]:
        h["image"] = d["image"]; h.pop("fallback", None)
    else:
        h.pop("image", None); h.pop("images", None)
        if h.get("placement", "left_column") != "none": h["requested_placement"] = h.get("placement", "left_column")
        h["placement"] = "none"; h["fallback"] = d["reason"]; card.pop("hero2", None) if not (card.get("hero2") or {}).get("image") else None
    h["decision"] = d
    return card
