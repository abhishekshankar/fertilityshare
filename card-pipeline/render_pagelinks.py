#!/usr/bin/env python3
"""
render_pagelinks.py — item 86: the card page links each number to its quote.

publish/permalink.page_html already writes one table row per outcome with id=n<i> (value, outcome, quote, derivation). This module
makes the numbers ON THE CARD (headline, dek, beats, takeaway, data-block values) point at those rows, and adds a "Numbers on the card"
list under the card image, using the same anchors the reviewer view uses (n<i>). A number that matches no outcome row is listed as
'no source row' (never silently unlinked), so the page shows exactly which card numbers lack a quote.

    html2, report = link_numbers(page_html(doc, slug), doc)        # report: {"linked": [...], "unlinked": [...]}
Wiring: publish.permalink.page_html's return value is passed through link_numbers (backlog/RENDER_R5_WIRING.patch).
"""
from __future__ import annotations
import html, re

NUM = re.compile(r"(?<![\w.])[−\-+]?\d[\d,]*(?:\.\d+)?")

def _val(tok):
    try: return float(tok.replace("−", "-").replace(",", "").lstrip("+"))
    except ValueError: return None

def _decimals(tok):
    t = tok.replace(",", ""); return len(t.split(".")[1]) if "." in t else 0

def _cands(o):
    out = []
    for k in ("value", "p"):
        if isinstance(o.get(k), (int, float)): out.append(("value" if k == "value" else "p", o[k]))
    for i, c in enumerate(o.get("ci") or []):
        if isinstance(c, (int, float)): out.append(("ci", c))
    rs = o.get("raw_stat") or {}
    if isinstance(rs.get("value"), (int, float)): out.append(("value", rs["value"]))
    for g in (o.get("group_stats") or []):
        if isinstance(g, dict):
            for k in ("mean", "value", "n", "sd"):
                if isinstance(g.get(k), (int, float)): out.append((k, g[k]))
    return out

def number_map(doc: dict) -> dict:
    """token -> outcome index (first outcome whose value / CI / group stat equals it at the token's precision; |value| for signs)."""
    outs = (doc.get("facts") or {}).get("outcomes") or []
    refs = [it.get("ref") for it in ((doc.get("card") or {}).get("data_block") or {}).get("items") or [] if isinstance(it.get("ref"), int)]
    order = refs + [i for i in range(len(outs)) if i not in refs]            # outcomes the card shows first
    def find(tok):
        v = _val(tok)
        if v is None: return None
        d = _decimals(tok)
        for i in order:
            for _k, c in _cands(outs[i]):
                if (abs(abs(c) - abs(v)) < 1e-9) if d == 0 else (round(abs(c), d) == round(abs(v), d) and len(f"{abs(c):g}".split(".")[-1]) >= d if "." in f"{abs(c):g}" else False):
                    return i
        return None
    return find

def link_numbers(page: str, doc: dict):
    find = number_map(doc); c, f = doc["card"], doc.get("facts") or {}
    linked, unlinked = [], []
    texts = {"headline": c["headline"]["text"], "dek": c.get("dek") or "", "takeaway": c["takeaway"]["text"]}
    for i, b in enumerate(c.get("beats") or []): texts[f"beat {i + 1}"] = f"{b.get('lead', '')} {b.get('detail', '')}".strip()
    n = f.get("n")
    def one(text, where):
        esc = html.escape(text)
        def sub(m):
            tok = m.group(0); i = find(tok)
            if i is None:
                if n is not None and _val(tok) == float(n): linked.append((where, tok, "source")); return f'<a class=nl href="#source">{tok}</a>'
                unlinked.append((where, tok)); return tok
            linked.append((where, tok, f"n{i}")); return f'<a class=nl href="#n{i}">{tok}</a>'
        return NUM.sub(sub, esc), esc
    for where, text in texts.items():
        if not text: continue
        new, esc = one(text, where)
        if new != esc and esc in page: page = page.replace(esc, new, 1)
    rows = []
    for it in (c.get("data_block") or {}).get("items") or []:
        ref = it.get("ref"); val = it.get("display") or it.get("value_text") or it.get("value")
        if isinstance(ref, int) and val is not None: rows.append(f'<li><a class=nl href="#n{ref}">{html.escape(str(val))}</a> {html.escape(str(it.get("label", "")))}</li>'); linked.append(("data block", str(val), f"n{ref}"))
        elif val is not None: rows.append(f'<li>{html.escape(str(val))} {html.escape(str(it.get("label", "")))} <span class=warn>no source row</span></li>'); unlinked.append(("data block", str(val)))
    nav = ('<nav id=cardnums><h2>Numbers on the card</h2><ul>' + "".join(rows) + '</ul></nav>') if rows else ""
    css = "<style>a.nl{color:inherit;text-decoration:underline dotted}tr:target{outline:2px solid var(--red);background:var(--card)}#cardnums ul{columns:2;padding-left:18px}</style>"
    page = page.replace("</style></head>", css.replace("<style>", "").replace("</style>", "") + "</style></head>", 1)
    page = page.replace("<p><b>Takeaway.</b>", nav + "<p><b>Takeaway.</b>", 1) if nav else page
    page = page.replace("<h2>Source</h2>", "<h2 id=source>Source</h2>", 1)
    return page, {"linked": linked, "unlinked": unlinked}
