#!/usr/bin/env python3
"""
critique.py — Loop L4: VISION QA. A model that did not write the card looks at the PNG.

Modeled on PaperVizAgent's Critic (JSON {critic_suggestions, revised_description}) but with
two differences: (1) the source of truth is the `facts` record, not free text, and (2) the
critic returns PATCHES to card.json, not a new description — so the render stays deterministic.

Checks: every number visible in the PNG exists in facts (reads them back = OCR by the model);
no clipped/overlapping text; the "one-glance" test (can you state the finding from headline +
data block alone?); highlight phrase is the payoff; hero image has no garbled text.

Usage: python critique.py out/stairs.png cards/stairs.json [--apply]
Needs ANTHROPIC_API_KEY. Model via MR_MODEL (default claude-sonnet-5-5).
"""
import json, sys, base64, pathlib, os, argparse

CRITIC_SYSTEM = """You are the critic for an evidence-card pipeline. You see the rendered PNG and the JSON that produced it.
Return JSON only:
{
 "numbers_seen": ["every number you can read on the card"],
 "numbers_not_in_facts": ["numbers on the card that do not match any facts.outcomes value"],
 "layout_issues": ["clipped text / overlap / unreadable size / empty regions, with the block name"],
 "one_glance": {"finding_from_headline_and_block": "...", "matches_takeaway": true},
 "honesty": ["places where the visual implies more than facts support (e.g. equal-sized effects with unequal evidence)"],
 "hero_issues": ["garbled text, wrong anatomy, style mismatch"],
 "patches": [{"path": "card.takeaway.text", "value": "..."}, ...],
 "verdict": "ship" | "revise"
}
Patches must be minimal and only to fields in `card`. Never change a number; if a number is wrong, report it under numbers_not_in_facts and set verdict=revise."""

def critique(png, doc):
    import anthropic
    client = anthropic.Anthropic()
    img = base64.b64encode(pathlib.Path(png).read_bytes()).decode()
    r = client.messages.create(model=os.environ.get("MR_MODEL", "claude-sonnet-5-5"), max_tokens=2000, system=CRITIC_SYSTEM,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img}},
            {"type": "text", "text": "facts + card JSON:\n" + json.dumps(doc, ensure_ascii=False)}]}])
    txt = r.content[0].text
    txt = txt[txt.find("{"): txt.rfind("}") + 1]
    return json.loads(txt)

def apply_patches(doc, patches):
    for p in patches:
        parts = p["path"].split("."); cur = doc
        for k in parts[:-1]:
            if "[" in k:
                name, idx = k[:-1].split("["); cur = cur[name][int(idx)]
            else: cur = cur[k]
        cur[parts[-1]] = p["value"]
    return doc

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("png"); ap.add_argument("card"); ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    doc = json.loads(pathlib.Path(a.card).read_text())
    res = critique(a.png, doc)
    print(json.dumps(res, indent=1, ensure_ascii=False))
    if a.apply and res.get("patches"):
        pathlib.Path(a.card).write_text(json.dumps(apply_patches(doc, res["patches"]), indent=2, ensure_ascii=False))
        print(f"applied {len(res['patches'])} patches -> re-run render.py")
    sys.exit(0 if res.get("verdict") == "ship" else 1)
