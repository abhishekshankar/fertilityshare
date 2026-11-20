#!/usr/bin/env python3
"""
render_gate.py — item 100: a card that fails any render gate goes to the review queue with the reason, never to out/ as final.

Flow (pipeline.s_render calls this; see backlog/RENDER_R5_WIRING.patch):
    staging = render_gate.staging_dir(run_dir)              # runs/<slug>/render_held/  (NOT out/)
    ... render.py writes <slug>.html/.png/.fit.json/.legibility.json into `staging` ...
    res = render_gate.finalize(slug, staging, out_dir, doc=doc)
        -> {"status": "final", "promoted": [...]}                       every gate passed: files copied to out/
        -> {"status": "held", "entry": review/queue/render/<slug>.json}  any gate failed: files stay in staging, queue entry written

Gates (each returns ok / detail / severity / slot):
    fit            fit.json warnings: 'trim copy', takeaway overflow, 'still overflowing', beat > 3 lines     (block)
    legibility     numbers OCR cannot read at 390px (legibility.json `missing`)                                (block)
    layout         layout_check problems: hero sliver, caption overlapping footer / data / takeaway             (block)
    numbers        every number on the rendered card is in the facts (render_numbers hook, if supplied)         (block)
    hero           the hero decision: a pinned hero rejected for not matching the outcome is a WARN, not a block (warn)
    lint           template.html literals above the brand-token baseline                                        (block)
    critic         visual critic verdict 'revise' (only when a critic record exists)                            (warn)
    primary        headline's primary outcome position-only / conflicting across independent documents          (hold)
Only `block` and `hold` failures hold a card (`hold` = queue for review, not a defect in the render); `warn` entries ride along on the final card's gates file and show in the review page.

Queue entry (review/queue/render/<slug>.json), schema render.queue/1:
  {version, slug, status: "held"|"released"|"overridden", created, template_sha, facts_sha,
   reasons: [{gate, severity, detail, slot}],       # why it is held, one line each, slot = card slot to trim when known
   gates: {gate: {ok, severity, detail}},            # all gates, pass or fail
   hero: {decision...}, hero_line: "one line for the reviewer",
   artifacts: {png, html, png_390, fit_json, legibility_json}   # absolute paths inside the staging dir
   actions: ["edit card copy and re-render", "override with a reason", "drop the hero", ...],
   review_seconds: int, resolution: null | {by, at, how, note}}
"""
from __future__ import annotations
import datetime, hashlib, json, pathlib, shutil

HERE = pathlib.Path(__file__).resolve().parent
QUEUE_DIR = HERE / "review" / "queue" / "render"
OUT = HERE / "out"
FINAL_SUFFIXES = (".png", ".html", ".pdf", ".fit.json", ".legibility.json", ".390.png", ".gates.json", ".render.json", ".cardgates.json", ".cardgates.post.json", ".alt.json")

def staging_dir(run_dir) -> pathlib.Path:
    d = pathlib.Path(run_dir) / "render_held"; d.mkdir(parents=True, exist_ok=True); return d

def template_sha() -> str:
    h = hashlib.sha1()
    for f in ("template.html", "render.py", "brand.json"):
        p = HERE / f
        if p.exists(): h.update(p.read_bytes())
    return h.hexdigest()[:12]

def _load(p):
    try: return json.loads(pathlib.Path(p).read_text())
    except (OSError, ValueError): return None

def _gate(ok, detail="", severity="block", slot=None):
    return {"ok": bool(ok), "severity": severity, "detail": detail, "slot": slot}

def evaluate(slug, staging, doc=None, layout=None, numbers=None, critic=None, lint=True, card_gates=None) -> dict:
    """All gates for a staged render. `layout`: list of problems (render.layout_check) or None; `numbers`: list of problems or None;
    `critic`: a visual-critic record or None."""
    staging = pathlib.Path(staging); g = {}
    fit = _load(staging / f"{slug}.fit.json"); lg = _load(staging / f"{slug}.legibility.json")
    if fit is None: g["fit"] = _gate(False, "no fit.json: the render did not complete")
    else:
        bad = [w for w in fit.get("warnings", []) if not w.startswith(("layout:", "legibility", "illegible", "gate:"))]
        slot = next((w.split("trim copy:")[1].split("(")[0].strip() for w in bad if "trim copy:" in w), None)
        g["fit"] = _gate(not bad, "; ".join(bad)[:400], slot=slot)
    if lg is None: g["legibility"] = _gate(False, "no legibility.json: the 390px read-back did not run")
    elif lg.get("ocr_error") and lg.get("missing") is None: g["legibility"] = _gate(True, f"gate open: {lg['ocr_error']}", "warn")
    else:
        miss = lg.get("missing") or []
        failing = lg.get("failing") or []                       # r2 (68): OCR misses + number font floor + headline/takeaway read-back
        ok = lg.get("pass", not miss) and not miss
        where = sorted({(v or {}).get("slot", "?") for v in (lg.get("where") or {}).values()})
        g["legibility"] = _gate(ok, ("unreadable at 390px: " + "; ".join(map(str, failing or miss)))[:400] if not ok else "", slot=",".join(where) or None)
    if layout is None and fit is not None:
        layout = [w[len("layout: "):] for w in fit.get("warnings", []) if w.startswith("layout:")]
    g["layout"] = _gate(not layout, "; ".join(layout or [])[:300])
    if numbers is not None: g["numbers"] = _gate(not numbers, "; ".join(map(str, numbers))[:400])
    if card_gates is not None:                       # render_gates.py (rr1): the DRAFT decision and every error-level finding (static + DOM)
        dec, errs = card_gates
        reasons = list(getattr(dec, "draft_reasons", None) or [])
        lines = [getattr(f, "line", lambda: str(f))() for f in (errs or [])]
        g["card_gates"] = _gate(not (reasons or lines), "; ".join(reasons + lines)[:500],
                                slot=next((getattr(f, "slot", None) for f in (errs or [])), None))
    tri = (((doc or {}).get("gate_inputs") or {}).get("triangulation")) if doc else None
    if tri:                                           # graph/triangulate.py: a card is publishable only when its headline claim is triangulated;
        ok = tri.get("combined", tri.get("status")) == "triangulated"        # a warning (REVIEW), never a block
        g["triangulation"] = _gate(ok, "" if ok else f"headline claim {tri.get('idx')}: {tri.get('status')} (primary-ness {tri.get('primary_status')}); not confirmed by independent routes", "warn")
        pc = tri.get("primary_confirm")                # graph/primary_routes.py: which outcome is primary, confirmed by >= 1 independent document
        if pc is not None:
            okp = pc not in ("position-only", "conflict")
            g["primary"] = _gate(okp, "" if okp else f"headline claim {tri.get('idx')}: primary outcome not confirmed by an independent source ({pc})", "hold")
    hero = ((doc or {}).get("card") or {}).get("hero", {}) if doc else {}
    dec = hero.get("decision")
    if dec:
        rej = dec.get("mode") == "pinned-rejected"
        g["hero"] = _gate(not rej, dec.get("reason", "") if rej else "", "warn")
    if lint:
        try:
            import render_lint as L
            c = L.counts(L.scan()); base = _load(L.BASELINE)
            over = base is not None and c["total"] > base["max_total"]
            g["lint"] = _gate(not over, f"{c['total']} literals > baseline {base['max_total']}" if over else "")
        except Exception as e:
            g["lint"] = _gate(True, f"lint unavailable: {e}", "warn")
    if critic is not None:
        rev = (critic.get("verdict") == "revise")
        g["critic"] = _gate(not rev, "; ".join((critic.get("layout_issues") or [])[:3]) if rev else "", "warn")
    return g

def blocking(gates) -> list:
    return [{"gate": k, "severity": v["severity"], "detail": v["detail"], "slot": v.get("slot")} for k, v in gates.items() if not v["ok"] and v["severity"] in ("block", "hold")]

def _actions(reasons, hero):
    a = []
    gs = {r["gate"] for r in reasons}
    if "fit" in gs or "legibility" in gs: a.append("shorten the named slot's copy (the renderer never shrinks type below the legibility floor) and re-render")
    if "layout" in gs: a.append("drop the hero (hero.placement 'none') or move the data block, then re-render")
    if "numbers" in gs: a.append("fix the card number or the facts path named in the detail, then re-render")
    if "card_gates" in gs: a.append("resolve the DRAFT reason / gate finding named in the detail (copy, facts or audit), then re-render; a DRAFT card is never final")
    if "primary" in gs: a.append("confirm which outcome is primary (registry / protocol / statement) and override with the source, or fix the headline")
    if "lint" in gs: a.append("move the new colour / font literal into brand.json tokens")
    a.append("override with a written reason (records who, why; promotes the staged files)")
    return a

def hold(slug, staging, gates, doc=None, facts_sha=None) -> dict:
    """Write the queue entry. Files stay in `staging`; nothing is written to out/."""
    staging = pathlib.Path(staging); reasons = blocking(gates)
    hero = (((doc or {}).get("card") or {}).get("hero") or {}).get("decision")
    try:
        import hero_match as HM; hero_line = HM.explain(hero) if hero else None
    except Exception: hero_line = None
    art = {}
    for k, suf in (("png", ".png"), ("html", ".html"), ("png_390", ".390.png"), ("fit_json", ".fit.json"), ("legibility_json", ".legibility.json")):
        p = staging / f"{slug}{suf}"
        if p.exists(): art[k] = str(p.resolve())
    entry = {"version": "render.queue/1", "slug": slug, "status": "held", "created": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
             "template_sha": template_sha(), "facts_sha": facts_sha, "reasons": reasons, "gates": gates, "hero": hero, "hero_line": hero_line,
             "artifacts": art, "actions": _actions(reasons, hero), "review_seconds": 30 + 20 * len(reasons), "resolution": None,
             "superseded_final": str(OUT / f"{slug}.png") if (OUT / f"{slug}.png").exists() else None}
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    (QUEUE_DIR / f"{slug}.json").write_text(json.dumps(entry, indent=1, ensure_ascii=False))
    return entry

def promote(slug, staging, out_dir=OUT, gates=None, override=None) -> list:
    """Copy the staged files to out/ (the only place a final render is created) with a .gates.json record."""
    staging, out_dir = pathlib.Path(staging), pathlib.Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True); done = []
    for p in sorted(staging.glob(f"{slug}.*")):
        if p.name.endswith(FINAL_SUFFIXES):
            shutil.copy2(p, out_dir / p.name); done.append(str(out_dir / p.name))
    rec = {"slug": slug, "template_sha": template_sha(), "gates": gates, "override": override,
           "at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    (out_dir / f"{slug}.gates.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False)); done.append(str(out_dir / f"{slug}.gates.json"))
    q = QUEUE_DIR / f"{slug}.json"
    if q.exists():                                      # a clean re-render clears an older held entry
        e = _load(q) or {}
        if e.get("status") == "held": e["status"] = "released" if not override else "overridden"; e["resolution"] = override or {"by": "gates", "how": "re-render passed"}; q.write_text(json.dumps(e, indent=1))
    return done

def finalize(slug, staging, out_dir=OUT, doc=None, layout=None, numbers=None, critic=None, facts_sha=None, card_gates=None) -> dict:
    gates = evaluate(slug, staging, doc, layout, numbers, critic, card_gates=card_gates)
    if blocking(gates):
        return {"status": "held", "entry": hold(slug, staging, gates, doc, facts_sha), "gates": gates}
    return {"status": "final", "promoted": promote(slug, staging, out_dir, gates), "gates": gates}

def override(slug, by, note, out_dir=OUT) -> dict:
    """Human release of a held card. The reason is mandatory and stored in the entry and in out/<slug>.gates.json."""
    if not (by and note and note.strip()): raise ValueError("an override needs who and why")
    q = QUEUE_DIR / f"{slug}.json"; e = _load(q)
    if not e: raise FileNotFoundError(q)
    staging = pathlib.Path(next(iter(e["artifacts"].values()))).parent
    res = {"by": by, "at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "how": "override", "note": note}
    promote(slug, staging, out_dir, e["gates"], override=res)
    e["status"], e["resolution"] = "overridden", res; q.write_text(json.dumps(e, indent=1)); return e

def pending() -> list:
    return sorted(p.stem for p in QUEUE_DIR.glob("*.json") if (_load(p) or {}).get("status") == "held") if QUEUE_DIR.exists() else []
