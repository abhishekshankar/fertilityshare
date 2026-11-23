#!/usr/bin/env python3
"""
run.py — FertilityShare evidence-card pipeline.

   PDF ─► [extract]  facts.json          (LLM, forced schema; quotes required)
            │  L0: quotes ⊂ source ──┐ repair ×1
            ▼                        │
          [plan]   block choice + exemplars
            │
            ▼
          [fill]   card.json              (LLM, forced schema, exemplars as few-shot)
            │  L1: numbers ⊂ facts ──┐ repair ×2
            │  L3: claim strength ≤ design
            ▼
          [render] fit loop L2 → PNG
            │
            ▼
          [critique] L4 vision QA → patches → re-render
            │
            ▼
          out/<slug>.png + out/<slug>.report.json

Usage:
  export ANTHROPIC_API_KEY=...
  python run.py paper.pdf --slug ivf2024 --brief "patients; live birth rate is the hook"
  python run.py paper.pdf --slug ivf2024 --no-critique   # skip L4
  python run.py paper.pdf --slug ivf2024 --n 3           # best-of-3
"""
import argparse, json, os, pathlib, sys, re

HERE = pathlib.Path(__file__).parent
MODEL = os.environ.get("FS_MODEL", "claude-sonnet-5-20251101")

# ---------------------------------------------------------------- schemas
_sf = json.loads((HERE / "schema_facts.json").read_text())
_sc = json.loads((HERE / "schema_card.json").read_text())

EXTRACT_SYSTEM = """Extract a typed `facts` record from the fertility / reproductive medicine paper.
Rules:
- Every outcome carries a verbatim quote (≤30 words) from the source that contains its number.
- `kind` must describe what the number IS (a hazard ratio converted to % change is hazard_or_odds;
  a count is count; k of N is of_total; a live-birth rate is hazard_or_odds or of_total).
- Record `measured_not_measured`: the thing a lay reader would assume was measured but wasn't
  (e.g. "live birth rate measured; singleton vs twin rate not measured").
- `design` and `n` from the methods. `limits` from the authors' own limitations paragraph.
- Do not editorialize. No headline, no advice.
- For fertility papers use domain "fertility". Species is almost always "human".
- Common outcome kinds in this domain: live_birth_rate (of_total), clinical_pregnancy_rate (of_total),
  miscarriage_rate (of_total), implantation_rate (of_total), sperm_motility (level), AMH (level),
  ovarian_reserve (level), time_to_pregnancy (level), cumulative_live_birth (of_total).
"""

FILL_SYSTEM = """You write one evidence card from a typed `facts` record. You fill ONLY the `card` object.

Frame (Wallace-style science cards, adapted for fertility medicine):
- eyebrow: genre label in caps (TRIAL RESULT / COHORT FINDING / META-ANALYSIS / MECHANISM / CASE SERIES).
  For fertility: include scale hint when relevant (e.g. "RCT · 312 CYCLES").
- headline: [population or intervention] [past-tense verb] [outcome by number], two lines;
  `payoff` is the red phrase (the number and its direction). Or a contrast pair.
- dek OR stats_line, not both. Numbers in the dek are auto-bolded.
  For fertility: mention cycle count or cohort size in the dek when it matters.
- data_block: use the block the planner chose; say why in planner_note if you override.
  Every number in the block carries `ref` = index into facts.outcomes.
- source_strip: journal+year | design | N/population, mono caps.
- evidence_boundary: 1–2 sentences the reader needs to know before generalising
  (population, protocol, what was not measured). Be honest about what this study cannot say.
- takeaway: one or two sentences; `highlight` is the exact substring;
  tone: action=green (RCT evidence) / caution=red (contradicts common belief) / caveat=amber (observational).
  `strength` must not exceed what the design supports:
    rct/crossover with N≥30 → recommendation
    cohort/case_control/cross_sectional/records_review → association
    mechanistic/animal/cell → mechanism
    pilot (N<30) or case_series → observation
- hero.prompt: physical description only, watercolor textbook anatomy/illustration, off-white background,
  "no text, no labels". The renderer draws labels in HTML over the image.
  For fertility: ovaries, follicles, embryos, sperm, uterus — anatomically precise, not decorative.
- Respect every maxLength. Plain words. Plain numbers. Never overpromise.
"""


def read_source(p: str) -> tuple[str, str]:
    p = pathlib.Path(p)
    if p.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        return p.name, "\n".join((pg.extract_text() or "") for pg in PdfReader(str(p)).pages)
    return p.name, p.read_text(errors="ignore")


def llm_tool(system: str, user: str, name: str, schema: dict, max_tokens: int = 5000) -> dict:
    import anthropic
    c = anthropic.Anthropic()
    r = c.messages.create(
        model=MODEL, max_tokens=max_tokens, system=system,
        tools=[{"name": name, "description": name, "input_schema": schema}],
        tool_choice={"type": "tool", "name": name},
        messages=[{"role": "user", "content": user}],
    )
    for b in r.content:
        if b.type == "tool_use":
            return b.input
    raise RuntimeError("no tool_use block in response")


# ---------------------------------------------------------------- L0: quote check
def _ngrams(text: str, n: int) -> set:
    words = re.findall(r"\w+", text.lower())
    return {" ".join(words[i:i+n]) for i in range(len(words) - n + 1)}

def l0_check(facts: dict, src_text: str) -> list[str]:
    ng = _ngrams(src_text, 6)
    fails = []
    for i, o in enumerate(facts.get("outcomes") or []):
        q = (o.get("evidence") or {}).get("quote", "")
        if q and "TRANSCRIBED" not in q:
            qng = _ngrams(q, 6)
            if qng and not (qng & ng):
                fails.append(f"outcome[{i}] quote not found in source: {q[:60]!r}")
    return fails


# ---------------------------------------------------------------- L1: number check
def l1_check(doc: dict) -> list[str]:
    facts, card = doc["facts"], doc["card"]
    outs = facts.get("outcomes") or []
    fails = []
    # every ref in data_block must resolve
    def check_block(b, label):
        if not isinstance(b, dict): return
        for it in b.get("items") or []:
            ref = it.get("ref")
            if ref is not None and not (0 <= ref < len(outs)):
                fails.append(f"{label} item {it.get('label')!r} ref={ref} out of range (facts has {len(outs)} outcomes)")
        for s in b.get("series") or []:
            ref = s.get("ref")
            if ref is not None and not (0 <= ref < len(outs)):
                fails.append(f"{label} series {s.get('label')!r} ref={ref} out of range")
    check_block(card.get("data_block"), "data_block")
    check_block(card.get("secondary_block"), "secondary_block")
    # payoff must be substring of headline
    hl = card.get("headline") or {}
    payoff = hl.get("payoff", "")
    if payoff and payoff not in hl.get("text", ""):
        fails.append(f"headline.payoff {payoff!r} is not a substring of headline.text")
    # highlight must be substring of takeaway
    tw = card.get("takeaway") or {}
    hl2 = tw.get("highlight", "")
    if hl2 and hl2 not in tw.get("text", ""):
        fails.append(f"takeaway.highlight {hl2!r} is not a substring of takeaway.text")
    return fails


# ---------------------------------------------------------------- L3: strength check
STRENGTH_RANK = {"observation": 1, "association": 2, "mechanism": 3, "recommendation": 4}
DESIGN_CAP = {
    "rct": "recommendation", "crossover": "recommendation",
    "cohort": "association", "case_control": "association",
    "cross_sectional": "association", "records_review": "association",
    "mechanistic": "mechanism", "animal": "mechanism", "cell": "mechanism",
    "pilot": "observation", "case_series": "observation",
    "review": "association", "meta_analysis": "recommendation",
}

def l3_check(doc: dict) -> list[str]:
    facts, card = doc["facts"], doc["card"]
    design = facts.get("design", "")
    n = facts.get("n") or 0
    if design == "rct" and isinstance(n, int) and n < 30:
        design = "pilot"  # downgrade small trials
    cap = DESIGN_CAP.get(design, "association")
    tw = card.get("takeaway") or {}
    strength = tw.get("strength", "")
    if STRENGTH_RANK.get(strength, 0) > STRENGTH_RANK.get(cap, 2):
        return [f"takeaway.strength={strength!r} exceeds design cap {cap!r} for design={design!r}"]
    # causal verbs in observational headline
    if design in ("cohort", "case_control", "cross_sectional", "records_review"):
        hl = (card.get("headline") or {}).get("text", "").lower()
        causal = ["caused", "causes", "prevented", "prevents", "reduced", "reduces", "cured", "cures"]
        for v in causal:
            if re.search(rf"\b{v}\b", hl):
                return [f"headline contains causal verb {v!r} in observational study"]
    return []


# ---------------------------------------------------------------- plan (deterministic block choice)
import plan as PL


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="FertilityShare card pipeline")
    ap.add_argument("sources", nargs="+")
    ap.add_argument("--slug", required=True)
    ap.add_argument("--brief", default="")
    ap.add_argument("--no-critique", action="store_true")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--n", type=int, default=1, help="best-of-N candidates")
    a = ap.parse_args()

    srcs = [read_source(s) for s in a.sources]
    src_text = "\n\n".join(t for _, t in srcs)
    src_blob = "\n\n".join(
        f'<source index="{i}" label="{l}">\n{t[:60000]}\n</source>'
        for i, (l, t) in enumerate(srcs)
    )
    report = {"slug": a.slug, "loops": {}}

    # ---- extract
    print(f"[extract] {a.slug}…")
    facts = llm_tool(
        EXTRACT_SYSTEM,
        f"Extract facts from this paper.\n\n{src_blob}",
        "facts", _sf, max_tokens=4000,
    )
    # ensure domain
    facts.setdefault("domain", "fertility")

    l0 = l0_check(facts, src_text)
    report["loops"]["L0"] = l0
    if l0:
        print(f"  L0 fails: {l0}")
        facts = llm_tool(
            EXTRACT_SYSTEM,
            f"Re-extract. These quotes were not found verbatim in the source — fix only them:\n"
            + "\n".join(f"- {f}" for f in l0)
            + f"\n\nSource:\n{src_blob}",
            "facts", _sf, max_tokens=4000,
        )
        report["loops"]["L0_repair"] = l0_check(facts, src_text)

    # ---- plan
    pp = PL.plan_prompt(facts)
    report["plan"] = pp["decision"]
    user_fill = pp["user"]
    if a.brief:
        user_fill += f"\n\n<editorial_brief>{a.brief}</editorial_brief>"

    # ---- fill (best-of-N, L1+L3 loops)
    print(f"[fill] candidates={a.n}…")
    cands = []
    for k in range(max(1, a.n)):
        card = llm_tool(FILL_SYSTEM, user_fill, "card", _sc, max_tokens=5000)
        doc = {"facts": facts, "card": card}
        for rnd in range(3):
            probs = l1_check(doc) + l3_check(doc)
            report["loops"][f"L1L3_round{rnd}" + (f"_cand{k}" if a.n > 1 else "")] = probs
            if not probs:
                break
            print(f"  L1/L3 round {rnd}: {probs}")
            card = llm_tool(
                FILL_SYSTEM,
                user_fill + "\n\nFix ONLY these failures, keep everything else:\n- "
                + "\n- ".join(probs) + "\n\nPrevious card:\n" + json.dumps(card, ensure_ascii=False),
                "card", _sc, max_tokens=5000,
            )
            doc["card"] = card
        cands.append(doc)

    if a.n > 1:
        # pick candidate with fewest remaining problems
        scored = [(len(l1_check(d) + l3_check(d)), i, d) for i, d in enumerate(cands)]
        scored.sort(key=lambda t: t[0])
        doc = scored[0][2]
        report["loops"]["L1L3_final"] = l1_check(doc) + l3_check(doc)
        print(f"  best candidate: #{scored[0][1]} ({scored[0][0]} problems)")
    else:
        doc = cands[0]

    # ---- save card JSON
    cards_dir = HERE / "cards"
    cards_dir.mkdir(exist_ok=True)
    cpath = cards_dir / f"{a.slug}.json"
    cpath.write_text(json.dumps(doc, indent=2, ensure_ascii=False))
    print(f"[card] saved → {cpath}")

    # ---- render (L2 fit loop)
    import render as R
    out = pathlib.Path(a.outdir)
    out.mkdir(exist_ok=True)
    brand = json.loads((HERE / "brand.json").read_text())
    hp, png = out / f"{a.slug}.html", out / f"{a.slug}.png"
    card = doc["card"]
    print("[render] fit loop…")
    log = []
    fs, hero_h, tweaks, _w = R.fit(doc, brand, hp, log)
    hp.write_text(R.render_html(doc, brand, fs, hero_h=hero_h, tweaks=tweaks))
    w, h = R.CANVAS[card.get("aspect", "4:5")]
    R.to_png(hp, png, w, h, 2)
    report["loops"]["L2"] = {
        "font_scale": fs,
        "iterations": len(log),
        "overflow": log[-1]["content_h"] > h if log else False,
    }
    print(f"  → {png}")

    # ---- critique (L4)
    if not a.no_critique:
        import critique as C
        print("[critique] L4 vision QA…")
        res = C.critique(str(png), doc)
        report["loops"]["L4"] = res
        if res.get("patches") and not res.get("numbers_not_in_facts"):
            doc = C.apply_patches(doc, res["patches"])
            cpath.write_text(json.dumps(doc, indent=2, ensure_ascii=False))
            log = []
            fs, hero_h, tweaks, _w = R.fit(doc, brand, hp, log)
            hp.write_text(R.render_html(doc, brand, fs, hero_h=hero_h, tweaks=tweaks))
            R.to_png(hp, png, w, h, 2)
            report["loops"]["L4_applied"] = len(res["patches"])
            print(f"  applied {len(res['patches'])} patches, re-rendered")

    # ---- report
    report_path = out / f"{a.slug}.report.json"
    report_path.write_text(json.dumps(report, indent=1, ensure_ascii=False))

    l0_ok = not report["loops"].get("L0_repair", report["loops"].get("L0"))
    l1l3_ok = not report["loops"].get("L1L3_final", report["loops"].get("L1L3_round2", []))
    l4_ok = report["loops"].get("L4", {}).get("verdict", "ship") == "ship"
    verdict = "SHIP" if l0_ok and l1l3_ok and l4_ok else "REVIEW"
    print(f"\n{verdict}: {png}\nreport: {report_path}")


if __name__ == "__main__":
    main()
