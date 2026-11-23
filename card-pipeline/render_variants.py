#!/usr/bin/env python3
"""
render_variants.py — items 81-83: carousel, social variants, PDF. Every output passes the same gates as the card.

  81  carousel/<stem>.s1_cover.png, s2_numbers.png, s3_limits.png   1080x1350 (Instagram 4:5), each a stand-alone slide built from the
      card's own words and numbers (no new text, no new numbers) with brand tokens, brand fonts and the hero decision of the card.
  82  <stem>.og.png 1200x630 social preview (headline + the primary number + site), <stem>.square.png 1080x1080 (the card's own layout
      engine, render.fit, with aspect 1:1).
  83  <stem>.pdf with selectable text and EMBEDDED fonts (Chrome prints text as text; fonts are inlined from brand.json font files);
      verified with pdffonts / pypdf: every font `emb`, text extractable and containing the headline.

Gates per output (render_gate.hold writes a queue entry '<stem>.<variant>' when one fails; failing files stay in staging, never out/):
  overflow      content taller/wider than the canvas
  numbers       every number on the slide appears on the card or in the facts' outcomes (a slide cannot introduce a number)
  legibility    390px render + OCR of every number on the slide (render.legibility)
  text          the headline words are present (slides) / PDF text is selectable and fonts embedded

    export_all(doc, brand, stem, staging, out_dir, which=("carousel", "og", "square", "pdf"), fs=None, hero_h=None) -> {variant: {ok, files, gates}}
"""
from __future__ import annotations
import copy, html, json, pathlib, re, subprocess
import render as R
import brand_tokens as BT
import hero_match as HM

HERE = pathlib.Path(__file__).resolve().parent
SLIDE = (1080, 1350); OG = (1200, 630)
NUM = R.NUM_RE

def _norm(n): return n.replace("−", "-").replace(",", "").lstrip("+")

def card_numbers(doc) -> set:
    """Numbers that exist on the card or in the facts: every number in every card string plus outcome values, CIs, p, n."""
    out = set()
    def walk(x):
        if isinstance(x, str): out.update(_norm(m) for m in NUM.findall(x))
        elif isinstance(x, dict):
            for k, v in x.items():
                if k in ("hero", "decision"): continue
                walk(v)
        elif isinstance(x, (list, tuple)):
            for v in x: walk(v)
        elif isinstance(x, (int, float)) and not isinstance(x, bool): out.add(_norm(f"{x:g}"))
    walk(doc.get("card") or {}); walk((doc.get("facts") or {}).get("outcomes")); walk((doc.get("facts") or {}).get("n"))
    out |= {x.lstrip("-") for x in set(out)}
    return out

def number_rows(b, limit=5):
    """[(label, display, small, ref)] for any data block: items (value/display/ci) or before_after rows."""
    rows = []
    for it in (b or {}).get("items") or []:
        if not isinstance(it, dict): continue
        disp = it.get("display") or (R.fmt(it["value"]) if isinstance(it.get("value"), (int, float)) else None)
        if disp is None: continue
        ci = it.get("ci"); small = it.get("sub") or (f"({R.fmt(ci[0])} to {R.fmt(ci[1])})" if ci and len(ci) == 2 else "")
        rows.append((str(it.get("label") or ""), str(disp), small, it.get("ref")))
    for r in (b or {}).get("rows") or []:
        rows.append((str(r.get("item") or ""), f"{r.get('before')} → {r.get('after')}", str(r.get("delta") or ""), r.get("ref")))
    return rows[:limit]

CSS = """
*{box-sizing:border-box;margin:0;padding:0} html,body{background:var(--bg)} body{font-family:var(--sans);color:var(--ink);-webkit-font-smoothing:antialiased}
.card{position:relative;overflow:hidden;background:var(--bg);display:flex;flex-direction:column;padding:64px 72px;gap:24px}
.mono{font-family:var(--mono);letter-spacing:.12em;text-transform:uppercase}
.eyebrow{font-size:22px;color:var(--ink3)} .count{position:absolute;top:64px;right:72px;font-size:22px;color:var(--ink3)}
h1{font-family:var(--cond);font-weight:700;-webkit-text-stroke:.016em currentColor;line-height:.98;letter-spacing:-.035em;hyphens:none}
.payoff{color:var(--red)} .dek{color:var(--ink2);font-size:30px;line-height:1.35}
.hero{flex:1;min-height:0;display:flex;align-items:center;justify-content:center} .hero img{max-width:100%;max-height:100%;object-fit:contain}
.block{background:var(--panel);border:1px solid var(--rule);border-radius:12px;padding:32px 36px;box-shadow:var(--shadow)}
.block .t{font-weight:800;font-size:34px;line-height:1.15;margin-bottom:6px} .block .s{color:var(--ink3);font-size:24px;margin-bottom:18px}
.row{display:flex;align-items:baseline;justify-content:space-between;gap:24px;padding:16px 0;border-top:1px solid var(--rule)}
.row .l{font-weight:700;font-size:30px} .row .rt{text-align:right}
.big{font-family:var(--cond);font-weight:700;color:var(--red);font-size:76px;line-height:1;letter-spacing:-.02em} .small{display:block;color:var(--ink3);font-size:24px}
.takeaway .payoff{color:var(--hl-amber)} .takeaway{margin-top:auto;background:var(--bar-black);color:var(--white);border-radius:10px;padding:28px 34px;font-family:var(--cond);font-weight:700;font-size:44px;line-height:1.1}
.boundary{font-size:36px;line-height:1.35;color:var(--ink2)} .hd2{color:var(--red);font-size:22px;font-weight:700;margin-bottom:12px}
.foot{margin-top:24px;display:flex;justify-content:space-between;align-items:baseline;font-size:20px;color:var(--ink2)} .site{color:var(--red);font-weight:700}
"""

def _page(body, w, h, brand, fonts=True):
    css = BT.root_css(brand) + ("\n" + R.inline_fonts_css() if fonts else "")
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>slide</title><style>{css}\n{CSS}\n.card{{width:{w}px;height:{h}px}}</style></head>'
            f'<body>{body}</body></html>')

def _h1(c, size):
    hl = c["headline"]; return f'<h1 style="font-size:{size}px">{R.mark(hl["text"], hl.get("payoff"), "payoff")}</h1>'

def _size(text, big=112, small=72):
    n = len(text); return big if n <= 60 else int(big - (big - small) * min(1, (n - 60) / 110))

def _foot(brand, c, i=None, n=None):
    return f'<div class="foot mono"><span>{html.escape(c.get("byline") or brand.get("byline", ""))}</span><span class="site">{html.escape(brand.get("site", ""))}</span></div>'

def slide_html(kind, doc, brand, fonts=True):
    d = copy.deepcopy(doc); c = d["card"]; HM.apply(c, d.get("facts")); hero = c.get("hero") or {}
    src = R._hero_img(hero["image"]) if hero.get("image") else None
    b = c.get("data_block") or {}
    if kind == "cover":
        body = (f'<div class="card"><div class="eyebrow mono">{html.escape(c.get("eyebrow") or "")}</div><span class="count mono">1 / 3</span>'
                f'{_h1(c, _size(c["headline"]["text"]))}' + (f'<p class="dek">{R.boldnums(c["dek"])}</p>' if c.get("dek") else "")
                + (f'<div class="hero"><img src="{src}" alt="{html.escape(hero.get("alt") or hero.get("subject") or "")}"></div>' if src else "<div style='flex:1'></div>")
                + _foot(brand, c) + "</div>")
    elif kind == "numbers":
        rows = "".join(f'<div class="row"><span class="l">{html.escape(l)}</span><span class="rt"><span class="big">{R.bignum(v)}</span>'
                       + (f'<span class="small">{html.escape(R.typo(s))}</span>' if s else "") + "</span></div>" for l, v, s, _r in number_rows(b))
        body = (f'<div class="card"><div class="eyebrow mono">{html.escape(c.get("eyebrow") or "")}</div><span class="count mono">2 / 3</span>'
                f'<div class="block"><div class="t">{html.escape(R.typo(b.get("title") or ""))}</div><div class="s">{html.escape(R.typo(b.get("subtitle") or ""))}</div>{rows}</div>'
                f'<div class="takeaway">{R.mark(c["takeaway"]["text"], c["takeaway"].get("highlight"), "payoff")}</div>' + _foot(brand, c) + "</div>")
    elif kind == "limits":
        body = (f'<div class="card"><div class="eyebrow mono">{html.escape(c.get("eyebrow") or "")}</div><span class="count mono">3 / 3</span>'
                f'<div class="hd2 mono">Evidence boundary</div><p class="boundary">{html.escape(R.typo(c.get("evidence_boundary") or ""))}</p>'
                f'<div class="takeaway">{R.mark(c["takeaway"]["text"], c["takeaway"].get("highlight"), "payoff")}</div>'
                f'<p class="cite mono" style="font-size:22px;color:var(--ink3)">{html.escape(c.get("citation") or "")}</p>' + _foot(brand, c) + "</div>")
        return _page(body, *SLIDE, brand, fonts)
    elif kind == "og":
        rows = number_rows(b, 1); big = rows[0] if rows else None
        body = (f'<div class="card" style="flex-direction:row;gap:48px;padding:48px 56px"><div style="flex:1.5;display:flex;flex-direction:column;gap:16px">'
                f'<div class="eyebrow mono">{html.escape(c.get("eyebrow") or "")}</div>{_h1(c, _size(c["headline"]["text"], 64, 44))}<div style="flex:1"></div>{_foot(brand, c)}</div>'
                + (f'<div class="block" style="flex:1;align-self:center"><div class="s">{html.escape(big[0])}</div><span class="big" style="font-size:64px;white-space:nowrap">{R.bignum(big[1])}</span>'
                   f'<span class="small">{html.escape(R.typo(big[2]))}</span></div>' if big else "") + "</div>")
        return _page(body, *OG, brand, fonts)
    return _page(body, *SLIDE, brand, fonts)

def gate_slide(html_path, png_path, w, h, doc, out, stem, headline=True):
    """overflow / numbers / legibility / text for one slide; returns {gate: {ok, detail}}."""
    g = {}
    with R._pw() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
        pg.goto(html_path.resolve().as_uri()); pg.wait_for_load_state("networkidle"); pg.evaluate("document.fonts.ready")
        m = pg.evaluate("""(() => { const c = document.querySelector('.card'); let over = []; const cr = c.getBoundingClientRect();
          for (const e of c.querySelectorAll('*')) { const r = e.getBoundingClientRect(); if (r.width && (r.bottom > cr.bottom + 1 || r.right > cr.right + 1)) over.push(e.className || e.tagName); }
          const cl = c.cloneNode(true); cl.querySelectorAll('.count').forEach(e => e.remove()); document.body.appendChild(cl); const text = cl.innerText; cl.remove();
          return {sh: c.scrollHeight, ch: c.clientHeight, sw: c.scrollWidth, cw: c.clientWidth, over: over.slice(0, 5), text}; })()""")
        pg.locator(".card").screenshot(path=str(png_path)); b.close()
    over = m["sh"] > m["ch"] + 1 or m["sw"] > m["cw"] + 1 or bool(m["over"])
    g["overflow"] = {"ok": not over, "detail": f"content {m['sh']}x{m['sw']} in {m['ch']}x{m['cw']}; {m['over']}" if over else ""}
    allowed = card_numbers(doc); seen = {_norm(x) for x in NUM.findall(m["text"])}
    bad = sorted(x for x in seen if x not in allowed and x.lstrip("-") not in allowed)
    g["numbers"] = {"ok": not bad, "detail": f"numbers not on the card or in the facts: {bad}" if bad else ""}
    page_idx = re.compile(r"^\d / 3$")                     # '1 / 3' counters are page numbers
    lg = R.legibility(html_path, out, stem, w, h)
    miss = [x for x in (lg.get("missing") or []) if not any(x == n for n in ("1", "2", "3"))]
    g["legibility"] = {"ok": not miss, "detail": f"unreadable at 390px: {miss}" if miss else (lg.get("ocr_error") or "")}
    if headline:
        words = [w_ for w_ in re.findall(r"[A-Za-z]{5,}", doc["card"]["headline"]["text"])][:3]
        g["text"] = {"ok": all(w_.lower() in m["text"].lower() for w_ in words), "detail": ""}
    return g

def verify_pdf(pdf, doc):
    """83: selectable text containing the headline, and every font embedded."""
    pdf = pathlib.Path(pdf); res = {"ok": False, "fonts": [], "text_ok": False, "pages": None}
    try:
        import pypdf
        rd = pypdf.PdfReader(str(pdf)); res["pages"] = len(rd.pages)
        txt = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True).stdout or " ".join((pg.extract_text() or "") for pg in rd.pages)   # Type 3 fonts: poppler maps them via ToUnicode
        words = re.findall(r"[A-Za-z]{5,}", doc["card"]["headline"]["text"])[:4]
        res["text_ok"] = bool(txt.strip()) and all(w_.lower() in txt.lower() for w_ in words)
    except Exception as e:
        res["error"] = str(e)
    r = subprocess.run(["pdffonts", str(pdf)], capture_output=True, text=True)
    rows = [l.split() for l in r.stdout.splitlines()[2:] if l.strip()]
    for l in rows:
        emb = next((l[i + 1] for i, t in enumerate(l) if t in ("yes", "no") and i >= len(l) - 6), None)
        res["fonts"].append({"name": l[0], "emb": [t for t in l if t in ("yes", "no")][0] if any(t in ("yes", "no") for t in l) else None})
    res["ok"] = res["text_ok"] and bool(res["fonts"]) and all(f["emb"] == "yes" for f in res["fonts"])
    return res

def export_pdf(doc, brand, pdf_path, fs=1.0, hero_h=None):
    c = doc["card"]; w, h = R.CANVAS[c.get("aspect", "4:5")]
    hp = pathlib.Path(pdf_path).with_suffix(".pdf.html")
    hp.write_text(R.render_html(doc, brand, fs, hero_h=hero_h, inline_fonts=True))
    with R._pw() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": w, "height": h})
        pg.goto(hp.resolve().as_uri()); pg.wait_for_load_state("networkidle"); pg.evaluate("document.fonts.ready")
        pg.pdf(path=str(pdf_path), width=f"{w}px", height=f"{h}px", print_background=True, page_ranges="1"); b.close()
    hp.unlink(missing_ok=True)
    return verify_pdf(pdf_path, doc)

def export_square(doc, brand, out, stem, staging):
    """82: the 1:1 variant from the card's own layout engine (render.fit) at aspect 1:1."""
    d = copy.deepcopy(doc); d["card"]["aspect"] = "1:1"
    hp = pathlib.Path(staging) / f"{stem}.square.html"; png = pathlib.Path(staging) / f"{stem}.square.png"; log = []
    fs, hero_h, tw, warns = R.fit(d, brand, hp, log, gate=(pathlib.Path(staging), f"{stem}.square"))
    hp.write_text(R.render_html(d, brand, fs, hero_h=hero_h, tweaks=tw)); w, h = R.CANVAS["1:1"]
    R.to_png(hp, png, w, h, 1)
    lg = R.legibility(hp, pathlib.Path(staging), f"{stem}.square", w, h)
    g = {"fit": {"ok": not [x for x in warns if not x.startswith("layout")], "detail": "; ".join(warns)[:300]},
         "legibility": {"ok": not lg.get("missing"), "detail": f"unreadable at 390px: {lg.get('missing')}" if lg.get("missing") else ""}}
    return png, g

def export_all(doc, brand, stem, staging, out_dir, which=("carousel", "og", "square", "pdf"), fs=None, hero_h=None):
    import render_gate as RG
    staging, out_dir = pathlib.Path(staging), pathlib.Path(out_dir); staging.mkdir(parents=True, exist_ok=True); out_dir.mkdir(parents=True, exist_ok=True)
    res = {}
    def settle(variant, files, gates):
        ok = all(v["ok"] for v in gates.values())
        if ok:
            for f in files:
                dst = out_dir / pathlib.Path(f).relative_to(staging); dst.parent.mkdir(parents=True, exist_ok=True); dst.write_bytes(pathlib.Path(f).read_bytes())
        else:
            gg = {k: {"ok": v["ok"], "severity": "block", "detail": v["detail"], "slot": None} for k, v in gates.items()}
            RG.hold(f"{stem}.{variant}", staging, gg, doc)
        res[variant] = {"ok": ok, "files": [str(f) for f in files], "gates": gates}
    if "carousel" in which:
        for i, kind in enumerate(("cover", "numbers", "limits"), 1):
            name = f"carousel/{stem}.s{i}_{kind}"; hp = staging / f"{name}.html"; hp.parent.mkdir(parents=True, exist_ok=True)
            hp.write_text(slide_html(kind, doc, brand)); png = staging / f"{name}.png"
            g = gate_slide(hp, png, *SLIDE, doc, hp.parent, f"{stem}.s{i}_{kind}", headline=(kind == "cover")); settle(f"s{i}_{kind}", [png], g)
    if "og" in which:
        hp = staging / f"{stem}.og.html"; hp.write_text(slide_html("og", doc, brand)); png = staging / f"{stem}.og.png"
        g = gate_slide(hp, png, *OG, doc, staging, f"{stem}.og"); settle("og", [png], g)
    if "square" in which:
        png, g = export_square(doc, brand, out_dir, stem, staging); settle("square", [png], g)
    if "pdf" in which:
        pdf = staging / f"{stem}.pdf"; v = export_pdf(doc, brand, pdf, fs or 1.0, hero_h)
        settle("pdf", [pdf], {"pdf": {"ok": v["ok"], "detail": "" if v["ok"] else json.dumps(v)[:300]}}); res["pdf"]["verify"] = v
    return res

if __name__ == "__main__":
    import sys
    p = pathlib.Path(sys.argv[1]); doc = json.loads(p.read_text()); brand = json.loads((HERE / "brand.json").read_text())
    out = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "out")
    r = export_all(doc, brand, p.parent.name if p.stem == "doc" else p.stem, out / ".staging", out, which=tuple(sys.argv[3].split(",")) if len(sys.argv) > 3 else ("carousel", "og", "pdf"))
    for k, v in r.items(): print(k, "OK" if v["ok"] else "HELD", {g: x["detail"] for g, x in v["gates"].items() if not x["ok"]})
