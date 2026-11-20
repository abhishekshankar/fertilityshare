#!/usr/bin/env python3
"""
render_meta.py — PNG metadata, C2PA, stable file names (RENDER_100 items 84, 85, 87).

    context_for(doc, gate_report=None, decision=None) -> dict   facts hash, card hash, gate/render version, PMID, decision
    stamp_png(path, site=None, ctx=None) -> str                 write the metadata as PNG iTXt chunks, byte level, no re-encode
    read_png_meta(path) -> dict
    has_c2pa(path) -> bool                                      a signed PNG is never rewritten
    stable_name(slug, variant, width) -> "<slug>.<variant>.<width>.png"
    publish_png(src, out_dir, slug, variant, width, ctx, card_json=None) -> dict
                                                                stable name, previous file archived as .vN (never overwritten),
                                                                C2PA signed or sidecar written (publish/c2pa.py)

Deterministic: no timestamps; the same facts, card and renderer give the same metadata bytes.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import shutil
import struct
import zlib
from typing import Optional

HERE = pathlib.Path(__file__).parent
RENDER_VERSION = "render-2"
PNG_SIG = b"\x89PNG\r\n\x1a\n"
KEYS = ("FactsHash", "CardHash", "GateVersion", "RenderVersion", "PMID", "GateDecision", "Variant")


def _sha(o) -> str:
    return hashlib.sha256(json.dumps(o, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str).encode()).hexdigest()


def render_version() -> str:
    """RENDER_VERSION plus a hash of the renderer and template source: a template change changes the version."""
    h = hashlib.sha1()
    for n in ("render.py", "template.html"):
        try: h.update((HERE / n).read_bytes())
        except OSError: pass
    return f"{RENDER_VERSION}+{h.hexdigest()[:10]}"


def context_for(doc: dict, report=None, decision=None) -> dict:
    f = doc.get("facts") or {}
    ids = (f.get("coverage") or {}).get("ids") or {}
    pmid = ids.get("pmid") or next((s.get("pmid") for s in (f.get("sources") or []) if isinstance(s, dict) and s.get("pmid")), "") or ""
    try:
        from render_gates import GATE_VERSION
    except Exception:
        GATE_VERSION = "none"
    ctx = {"FactsHash": _sha(f)[:32], "CardHash": _sha(doc.get("card") or {})[:32], "GateVersion": GATE_VERSION,
           "RenderVersion": render_version(), "PMID": str(pmid)}
    action = getattr(decision, "action", None) or (doc.get("gate_decision") or {}).get("action")
    if action: ctx["GateDecision"] = action
    return ctx


# ------------------------------------------------------------------ PNG chunks
def _chunks(b: bytes):
    i = 8
    while i < len(b):
        ln, = struct.unpack(">I", b[i:i + 4]); typ = b[i + 4:i + 8]
        yield typ, b[i + 8:i + 8 + ln]
        i += 12 + ln

def _chunk(typ: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + typ + data + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)

def _itxt(key: str, val: str) -> bytes:
    return _chunk(b"iTXt", key.encode("latin-1") + b"\0\0\0\0\0" + val.encode("utf-8"))

def _text_key(typ: bytes, data: bytes) -> Optional[str]:
    if typ in (b"tEXt", b"iTXt", b"zTXt"): return data.split(b"\0", 1)[0].decode("latin-1", "replace")
    return None

def has_c2pa(path) -> bool:
    b = pathlib.Path(path).read_bytes()
    return b[:8] == PNG_SIG and any(t == b"caBX" for t, _d in _chunks(b))

def read_png_meta(path) -> dict:
    b = pathlib.Path(path).read_bytes(); out = {}
    if b[:8] != PNG_SIG: return out
    for typ, d in _chunks(b):
        if typ == b"tEXt":
            k, _, v = d.partition(b"\0"); out[k.decode("latin-1")] = v.decode("latin-1")
        elif typ == b"iTXt":
            k, rest = d.split(b"\0", 1)
            # compression flag, method, then language tag and translated keyword (both NUL terminated)
            v = rest[2:].split(b"\0", 2)[-1]
            out[k.decode("latin-1")] = v.decode("utf-8", "replace")
    return out

def stamp_png(path, site: Optional[str] = None, ctx: Optional[dict] = None) -> str:
    """Add the metadata as iTXt chunks before IDAT (existing chunks with the same keys are replaced; pixels and any other
    chunk untouched).  A C2PA-signed PNG is left alone: editing it would break the signature (stamp before signing)."""
    p = pathlib.Path(path); b = p.read_bytes()
    if b[:8] != PNG_SIG: return "skipped: not a png"
    if has_c2pa(p): return "kept: C2PA manifest present"
    new = {}
    if site: new.update({"Source": site, "Copyright": site})
    new.update({k: str(v) for k, v in (ctx or {}).items() if v not in (None, "")})
    if not new: return "skipped: nothing to write"
    out, done = [PNG_SIG], False
    for typ, d in _chunks(b):
        if _text_key(typ, d) in new: continue
        if typ == b"IDAT" and not done:
            out.extend(_itxt(k, new[k]) for k in sorted(new)); done = True
        out.append(_chunk(typ, d))
    p.write_bytes(b"".join(out))
    return "stamped"


# ------------------------------------------------------------------ stable names, versions, C2PA
def stable_name(slug: str, variant: str = "card", width: int = 1080) -> str:
    v = re.sub(r"[^a-z0-9\-]+", "-", str(variant).lower()).strip("-") or "card"
    return f"{slug}.{v}.{int(width)}.png"

def publish_png(src, out_dir, slug: str, variant: str = "card", width: int = 1080, ctx: Optional[dict] = None,
                card_json=None, site: Optional[str] = None, sign: bool = True) -> dict:
    """Copy src to <out_dir>/<slug>.<variant>.<width>.png.  If that file exists with different bytes it is archived as
    <slug>.<variant>.<width>.v<N>.png first (the stable name always holds the newest, nothing is overwritten)."""
    out_dir = pathlib.Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / (stable_name(slug, variant, width) + ".tmp")
    shutil.copyfile(src, tmp)
    stamp_png(tmp, site=site, ctx=dict(ctx or {}, Variant=variant))                       # metadata first, signature last
    dest = out_dir / stable_name(slug, variant, width)
    archived = None
    if dest.exists():
        if dest.read_bytes() == tmp.read_bytes():
            tmp.unlink(); return {"path": str(dest), "archived": None, "c2pa": c2pa_state(dest), "changed": False}
        n = 1
        while (out_dir / dest.name.replace(".png", f".v{n}.png")).exists(): n += 1
        archived = out_dir / dest.name.replace(".png", f".v{n}.png"); dest.replace(archived)
        for ext in (".c2pa.json",):
            sc = dest.with_suffix(ext)
            if sc.exists(): sc.replace(archived.with_suffix(ext))
    tmp.replace(dest)
    res = {"path": str(dest), "archived": str(archived) if archived else None, "changed": True}
    res["c2pa"] = ensure_c2pa(dest, card_json) if sign and card_json else c2pa_state(dest)
    return res

def c2pa_state(png) -> dict:
    png = pathlib.Path(png)
    if has_c2pa(png): return {"status": "signed"}
    sc = png.with_suffix(".c2pa.json")
    return {"status": "unsigned", "sidecar": str(sc) if sc.exists() else None}

def ensure_c2pa(png, card_json) -> dict:
    """85. Every published PNG has a manifest: signed when C2PA_CERT/C2PA_KEY are set, else the sidecar manifest that would be
    signed, with the reason. Never a self-claimed credential (publish/c2pa.py)."""
    try:
        from publish import c2pa as C
        r = C.embed(card_json, png)
    except Exception as e:
        return {"status": "failed", "why": f"{type(e).__name__}: {e}"}
    return {"status": r.get("status"), "sidecar": r.get("sidecar"), "why": r.get("why")}
