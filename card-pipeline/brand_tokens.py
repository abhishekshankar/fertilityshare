#!/usr/bin/env python3
"""
brand_tokens.py — item 99: brand.json is the ONLY source of colours and fonts.

brand.json carries `tokens.light`, `tokens.dark` (CSS custom property name -> value, no leading dashes) and `fonts`
({"cond": [...], "sans": [...], "mono": [...], "files": [{family, weight, path}]}). The template's :root / dark blocks and the
@font-face files are generated from it (`root_css`, `font_files`). DEFAULTS below are the values the template used to hard-code;
a brand.json without tokens still renders (tests pass bare brand dicts), and `python3 brand_tokens.py --write` copies the defaults
into brand.json once. render_lint.py checks template.html has no colour / font literals outside the generated block.
"""
import json, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent

LIGHT = {
    "bg": "#f8f6f1", "panel": "#ffffff", "panel2": "#f1eee7", "ink": "#121417", "ink2": "#44464a", "ink3": "#6b6862", "ink4": "#6b6862",      # r2 (64): >= 4.5:1 on bg, panel and panel2
    "rule": "#e4dfd5", "grid": "#e8e4dc", "axis": "#444444", "shadow": "0 1px 2px rgba(0,0,0,.04)",
    "red": "#c8102e", "red-soft": "#f9e4e4", "amber": "#e09b1a", "amber-soft": "#fbf0d9", "green": "#1a7a43", "green-soft": "#e3f3e8",
    "blue": "#2b5fb3", "blue-soft": "#e6eefb", "purple": "#6b3fb5", "grey-bar": "#b8b4ad", "ochre1": "#d9842a", "ochre2": "#f0a65a",
    "hl-green": "#5fe08f", "hl-red": "#ff6257", "hl-amber": "#f5c75a", "bar-black": "#000000",
    "white": "#ffffff", "black": "#000000",
}
DARK = {
    "bg": "#15161a", "panel": "#1e2025", "panel2": "#262830", "ink": "#f2efe8", "ink2": "#cfcbc3", "ink3": "#9a968f", "ink4": "#9a968f",
    "rule": "#2f3138", "grid": "#2a2c33", "axis": "#9a968f", "shadow": "0 1px 2px rgba(0,0,0,.4)", "grey-bar": "#5d5b57",
    "red-soft": "#3a1a20", "green-soft": "#15301f", "blue-soft": "#16213a", "bar-black": "#000000",
    "red": "#ff6b7f", "green": "#4fcf85", "blue": "#6ea4f0", "purple": "#b08cf0", "amber": "#e0a84a",   # r2 (65): dark-theme accents pass 4.5:1
}
FONTS = {
    "cond": ["TeX Gyre Heros Cn", "Inter Display", "Inter", "sans-serif"],
    "sans": ["Inter", "system-ui", "sans-serif"],
    "mono": ["DejaVu Sans Mono", "ui-monospace", "monospace"],
    "files": [
        {"family": "Inter", "weight": 400, "path": "/usr/share/fonts/opentype/inter/Inter-Regular.otf"},
        {"family": "Inter", "weight": 600, "path": "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf"},
        {"family": "Inter", "weight": 700, "path": "/usr/share/fonts/opentype/inter/Inter-Bold.otf"},
        {"family": "Inter", "weight": 800, "path": "/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf"},
        {"family": "Inter Display", "weight": 800, "path": "/usr/share/fonts/opentype/inter/InterDisplay-ExtraBold.otf"},
        {"family": "Inter Display", "weight": 900, "path": "/usr/share/fonts/opentype/inter/InterDisplay-Black.otf"},
        {"family": "TeX Gyre Heros Cn", "weight": 700, "path": "/usr/share/texmf/fonts/opentype/public/tex-gyre/texgyreheroscn-bold.otf"},
        {"family": "DejaVu Sans Mono", "weight": 400, "path": "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"},
        {"family": "DejaVu Sans Mono", "weight": 700, "path": "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"},
    ],
}

def resolve(brand=None):
    """Tokens for a brand dict: brand.tokens over DEFAULTS. Returns {"light": {...}, "dark": {...}, "fonts": {...}}."""
    b = brand or {}; t = b.get("tokens") or {}; f = dict(FONTS); f.update(b.get("fonts") or {})
    return {"light": {**LIGHT, **(t.get("light") or {})}, "dark": {**DARK, **(t.get("dark") or {})}, "fonts": f}

def _stack(names):
    return ", ".join(f'"{n}"' if (" " in n) else n for n in names)

def root_css(brand=None):
    """The :root and dark-theme blocks, plus the three font stacks as custom properties (--cond, --sans, --mono)."""
    r = resolve(brand)
    light = "; ".join(f"--{k}: {v}" for k, v in r["light"].items())
    fonts = "; ".join(f"--{k}: {_stack(r['fonts'][k])}" for k in ("cond", "sans", "mono"))
    dark = "; ".join(f"--{k}: {v}" for k, v in r["dark"].items())
    return f":root {{ {light}; {fonts}; }}\n  [data-theme=\"dark\"] {{ {dark}; }}"

def font_files(brand_path=None):
    try: b = json.loads(pathlib.Path(brand_path or HERE / "brand.json").read_text())
    except (OSError, ValueError): b = {}
    return [(f["family"], f["weight"], f["path"]) for f in resolve(b)["fonts"]["files"]]

def write_defaults(path=None):
    p = pathlib.Path(path or HERE / "brand.json"); b = json.loads(p.read_text())
    b["tokens"] = {"light": dict(LIGHT), "dark": dict(DARK)}; b["fonts"] = {k: (list(v) if isinstance(v, list) else v) for k, v in FONTS.items()}
    p.write_text(json.dumps(b, indent=1)); return b

if __name__ == "__main__":
    if "--write" in sys.argv: write_defaults(); print("brand.json updated")
    else: print(root_css())
