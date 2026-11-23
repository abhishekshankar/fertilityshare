#!/usr/bin/env python3
"""
render_lint.py — item 99: template.html may not hold colour or font literals; brand.json (brand_tokens.py) is the only source.

  python3 render_lint.py                 # report; exit 1 if literals exceed the ratchet baseline (eval/golden/render_frozen/lint_baseline.json)
  python3 render_lint.py --strict        # exit 1 on any literal
  python3 render_lint.py --suggest       # for every literal: the token whose value equals it, or 'add token'
  python3 render_lint.py --fix           # rewrite exact-match literals to var(--token) in place (run once after merging the render branches)
  python3 render_lint.py --baseline      # record the current count as the allowed maximum (the ratchet only goes down)

Literals: #hex, rgb()/rgba()/hsl(), and font-family names outside var(--...). Allowed: transparent, currentColor, inherit, and
anything inside `var(...)` / `color-mix(in srgb, var(...) ..., #fff|#000)` mixing keywords (counted separately as 'mix').
"""
import json, pathlib, re, sys
import brand_tokens as BT

HERE = pathlib.Path(__file__).resolve().parent
BASELINE = HERE / "eval" / "golden" / "render_frozen" / "lint_baseline.json"
HEX = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b")
FUNC = re.compile(r"\b(?:rgba?|hsla?)\([^)]*\)")
FONTDECL = re.compile(r"font-family\s*:\s*([^;}]+)")
# jinja-defined literals inside the template body (macros passing colours): the same rule applies
HTML_ENTITY = re.compile(r"&#[0-9a-fA-F]+;")

def _norm(v):
    v = v.lower().strip()
    if re.fullmatch(r"#[0-9a-f]{3}", v): v = "#" + "".join(c * 2 for c in v[1:])
    return v

def token_values(brand=None):
    r = BT.resolve(brand); return {_norm(v): k for k, v in r["light"].items() if v.startswith("#") or v.startswith("rgb")}

def scan(text=None, path=None):
    """[{line, kind, literal, context}] for every colour / font literal outside a `var(--x)` reference."""
    text = text if text is not None else pathlib.Path(path or HERE / "template.html").read_text()
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        scrub = HTML_ENTITY.sub("", line)
        for m in list(HEX.finditer(scrub)) + list(FUNC.finditer(scrub)):
            lit = m.group(0)
            ctx = scrub[max(0, m.start() - 40): m.end() + 10].strip()
            kind = "mix" if "color-mix(" in scrub[max(0, m.start() - 120): m.start()] and re.search(r"(?:#fff|#000)\b", lit) else "colour"
            out.append({"line": n, "kind": kind, "literal": lit, "context": ctx})
        for m in FONTDECL.finditer(scrub):
            decl = m.group(1).strip()
            if not decl.startswith("var("):
                out.append({"line": n, "kind": "font", "literal": decl, "context": scrub[max(0, m.start() - 20): m.end()].strip()})
    return out

def suggest(findings, brand=None):
    tv = token_values(brand); res = []
    for f in findings:
        tok = tv.get(_norm(f["literal"])) if f["kind"] in ("colour", "mix") else None
        if f["kind"] == "font":
            names = [x.strip().strip('"\'') for x in f["literal"].split(",")]
            fonts = BT.resolve(brand)["fonts"]; tok = next((k for k in ("cond", "sans", "mono") if names[0] == fonts[k][0]), None)
        res.append({**f, "token": tok, "action": f"var(--{tok})" if tok else "add a token to brand.json"})
    return res

def fix(path=None, brand=None):
    """Rewrite exact-match literals to var(--token). Only touches colour literals that equal a token value and font stacks that start
    with a token's first family. Returns the number of replacements."""
    p = pathlib.Path(path or HERE / "template.html"); text = p.read_text(); tv = token_values(brand); n = 0
    def hexsub(m):
        nonlocal n
        tok = tv.get(_norm(m.group(0)))
        if tok: n += 1; return f"var(--{tok})"
        return m.group(0)
    lines = []
    in_gen = False
    for line in text.splitlines():
        if "{% set" in line and "var(" not in line.split("{% set")[0]: lines.append(line); continue      # jinja colour lists feed SVG attributes: fixed by hand + a visual check
        if "x.tokens_css" in line or HTML_ENTITY.search(line) and "&#" in line and "<" not in line: lines.append(line); continue
        keep = HTML_ENTITY.findall(line)
        line2 = HEX.sub(lambda m: m.group(0) if "color-mix(" in line[max(0, m.start() - 120): m.start()] and _norm(m.group(0)) in ("#ffffff", "#000000") else hexsub(m), line)
        def fsub(m):
            nonlocal n
            decl = m.group(1).strip(); names = [x.strip().strip('"\'') for x in decl.split(",")]
            fonts = BT.resolve(brand)["fonts"]; tok = next((k for k in ("cond", "sans", "mono") if names[0] == fonts[k][0]), None)
            if decl.startswith("var(") or not tok: return m.group(0)
            n += 1; return f"font-family: var(--{tok})"
        lines.append(FONTDECL.sub(fsub, line2))
    p.write_text("\n".join(lines) + ("\n" if text.endswith("\n") else "")); return n

def counts(findings):
    c = {"colour": 0, "font": 0, "mix": 0}
    for f in findings: c[f["kind"]] += 1
    c["total"] = c["colour"] + c["font"]; return c

def main(argv):
    f = scan(); c = counts(f)
    base = json.loads(BASELINE.read_text()) if BASELINE.exists() else None
    if "--baseline" in argv:
        BASELINE.parent.mkdir(parents=True, exist_ok=True); BASELINE.write_text(json.dumps({"max_total": c["total"], "counts": c}, indent=1)); print("baseline", c); return 0
    if "--fix" in argv:
        print("rewrote", fix(), "literals"); f = scan(); c = counts(f)
    if "--suggest" in argv:
        for s in suggest(f): print(f"template.html:{s['line']} {s['kind']:6} {s['literal'][:40]:40} -> {s['action']}")
    print("literals:", c, "baseline:", base and base["max_total"])
    if "--strict" in argv: return 1 if c["total"] else 0
    if base is not None and c["total"] > base["max_total"]:
        print(f"FAIL: {c['total']} literals > baseline {base['max_total']} (new colour/font literal in template.html; add a token to brand.json)"); return 1
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
