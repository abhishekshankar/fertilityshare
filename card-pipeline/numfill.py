"""
numfill.py — the card model never has the last word on a digit.

After the card is filled and before the audit, copy every number that has a `ref` from facts.outcomes[ref]
(value, ci, display at the printed precision), and repair a free-text number that is one digit away from exactly one
allowed fact number (a retyped 7.62 -> 7.52). Anything else is left for the audit to fail. Every change is logged.
Never touches facts.
"""
from __future__ import annotations
import re, copy

NUM = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w])")
TEXT_FIELDS = (("headline", "text"), ("headline", "payoff"), ("dek",), ("takeaway", "text"), ("takeaway", "highlight"))

def _dec(x) -> int:
    s = repr(x)
    return len(s.split(".")[1].rstrip("0")) if "." in s else 0

def _walk(blk):
    if isinstance(blk, dict):
        if isinstance(blk.get("value"), (int, float)): yield blk
        for k in ("items", "rows", "series", "steps"):
            for it in blk.get(k) or []: yield from _walk(it)

def allowed_numbers(facts: dict) -> set[str]:
    out = set()
    def add(v):
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            d = _dec(v); out.add(f"{abs(v):.{d}f}")
            if d == 0 and float(v).is_integer(): out.add(str(int(abs(v))))
    for o in facts.get("outcomes", []):
        for k in ("value", "total", "n", "baseline", "p"): add(o.get(k))
        for v in o.get("ci") or []: add(v)
        add((o.get("raw_stat") or {}).get("value"))
        for g in o.get("groups") or []:
            if isinstance(g, dict): add(g.get("n")); add(g.get("value"))
    for k in ("n", "n_analyzed", "n_randomized", "n_derived", "n_enrolled"): add(facts.get(k))
    return out

def _near(tok: str, allowed: set[str]):
    c = [a for a in allowed if len(a) == len(tok) and a != tok and sum(x != y for x, y in zip(a, tok)) == 1 and a.replace(".", "") != tok.replace(".", "") or
         (len(a) == len(tok) and a != tok and sum(x != y for x, y in zip(a, tok)) == 1)]
    return c[0] if len(set(c)) == 1 else None

def fill(card: dict, facts: dict) -> tuple[dict, list[str]]:
    card = copy.deepcopy(card); log: list[str] = []
    outs = facts.get("outcomes", [])
    for bk in ("data_block", "secondary_block"):
        blk = card.get(bk)
        if not blk: continue
        for it in _walk(blk):
            r = it.get("ref")
            if not isinstance(r, int) or not 0 <= r < len(outs): continue
            o = outs[r]; fv = o.get("value"); rv = (o.get("raw_stat") or {}).get("value")
            if o.get("kind") == "of_total" or "series" in it or fv is None: continue
            cur = it["value"]
            ok = abs(abs(cur) - abs(fv)) <= 1e-6 or (rv is not None and abs(abs(cur) - abs(rv)) <= 1e-6)
            if not ok:
                new = (-1 if cur < 0 and fv > 0 else 1) * abs(fv)
                log.append(f"{bk}: {cur} -> {new} (ref {r})"); it["value"] = new
                if "display" in it: it["display"] = f"{abs(new):.{_dec(fv)}f}"
            ci = o.get("ci")
            if ci and isinstance(it.get("ci"), list) and len(it["ci"]) == 2 and it["ci"] != ci and abs(abs(it["value"]) - abs(fv)) <= 1e-6:
                log.append(f"{bk}: ci {it['ci']} -> {ci} (ref {r})"); it["ci"] = list(ci)
    allowed = allowed_numbers(facts)
    def fix(s):
        def rep(m):
            t = m.group(1)
            if t in allowed or len(t) < 3: return t
            n = _near(t, allowed)
            if n: log.append(f"text: {t} -> {n}"); return n
            return t
        return NUM.sub(rep, s)
    for path in TEXT_FIELDS:
        node = card
        for k in path[:-1]: node = node.get(k) or {}
        k = path[-1]
        if isinstance(node, dict) and isinstance(node.get(k), str): node[k] = fix(node[k])
    # keep substring invariants (payoff in text, highlight in text) intact
    h = card.get("headline") or {}
    if h.get("payoff") and h["payoff"] not in h.get("text", ""): log.append("headline: payoff no longer in text — left for audit")
    return card, log
