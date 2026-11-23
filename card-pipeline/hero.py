#!/usr/bin/env python3
"""
hero.py — the illustration node. Fills `card.hero.image` (and stat_row icons) from an image model,
through a LIBRARY so the same brain / heart / gut recurs across cards the way Wallace's do.

Two modes:
  library  : python hero.py build-library            # generates assets/library/*.png once (~30 subjects)
  card     : python hero.py cards/stairs.json         # picks from library by subject tag, or generates
                                                      #   a bespoke one from card.hero.prompt, sets hero.image
  dry run  : python hero.py cards/stairs.json --dry-run   # no API call: writes out/hero_prompts.json (prompt list)
  normalize: python hero.py normalize assets/*.png     # PIL autocontrast on existing images
  gate     : python hero.py gate [files]              # OCR no-text gate + style drift vs the library atlas
  organs   : python hero.py organs "B12 deficiency"   # concept -> organ tags (CONCEPT_ORGANS)

Backends (pick with HERO_BACKEND=gemini|openai; default gemini):
  gemini : GEMINI_API_KEY   model gemini-2.5-flash-image  (the "nano banana" look his cards have)
  openai : OPENAI_API_KEY   model gpt-image-1

Style is a fixed constant so every image matches (the AIA "constitution" idea). Prompts are physical
descriptions only and always end with the no-text clause; labels are drawn in HTML by the template.
"""
import json, os, sys, pathlib, base64, hashlib, re

HERE = pathlib.Path(__file__).parent
LIB = HERE / "assets" / "library"; LIB.mkdir(parents=True, exist_ok=True)
MANIFEST = LIB / "manifest.json"

STYLE = ("Scientific textbook illustration in watercolor and fine ink line, the style of a classic anatomy atlas "
         "redrawn for a modern health magazine. Soft naturalistic color, warm reds and ochres for tissue, "
         "muted blues for veins, cream off-white background #f7f5f0, no frame, no drop shadow, subject centered "
         "with generous margin, isolated, no background scene. ABSOLUTELY NO TEXT, NO LETTERS, NO LABELS, "
         "NO NUMBERS, NO ARROWS, NO LEADER LINES anywhere in the image.")

# subject tag -> physical description. Add to this as the corpus grows.
LIBRARY = {
  "brain_sagittal":   "a human brain in mid-sagittal section showing the corpus callosum, thalamus, brainstem and cerebellum",
  "brain_lateral":    "a human brain seen from the left side, gyri and sulci clearly drawn",
  "brain_coronal_sn": "a coronal section of the human midbrain with the substantia nigra as two dark pigmented bands",
  "heart_whole":      "a whole human heart with aorta, pulmonary trunk and coronary arteries, anterior view",
  "heart_atrium_cut": "a cutaway of the human left atrium with the sinus node region and conduction fibres glowing faintly amber",
  "artery_plaque":    "a cross-section of a coronary artery with a yellow lipid plaque narrowing the lumen, red blood cells inside",
  "vein_forearm":     "a cross-section of forearm tissue showing a blue vein under skin and fat, beside an upright glass blood collection tube with a red cap",
  "muscle_fibre":     "a single lens-shaped red skeletal muscle fibre with visible striations, four small golden spheres descending into it",
  "muscle_arm":       "the muscles of the human upper arm and shoulder, deltoid and biceps, skin removed, anterior view",
  "stairs":           "a short flight of six concrete steps with a steel handrail on the left, isometric view",
  "gut_villi":        "a cross-section of the human small intestine wall with finger-like villi, pink and layered",
  "gut_microbes":     "a cutaway of the colon lining with a magnifying circle showing purple rod-shaped bacteria among villi",
  "liver_kidneys":    "the human liver above two kidneys with the aorta and vena cava between them, anterior view",
  "skin_sun":         "a block cross-section of human skin with epidermis, dermis, hair follicle and fat layer, a small sun above",
  "bone_vertebra":    "a lumbar vertebra cut open to show trabecular bone like a sponge, beside an ovary in cross-section with follicles",
  "myelin_axon":      "a nerve axon wrapped in concentric myelin sheath layers, cut away to show the layers, with an oligodendrocyte above",
  "blueberries":      "a sprig of blueberries with leaves, botanical plate style",
  "coffee_plant":     "a coffee branch with red cherries, one cherry cut open showing the bean, botanical plate style",
  "rice_bowl":        "a ceramic bowl of steamed white rice, steam rising",
  "potato_halved":    "a baked potato cut in half, fluffy inside",
  "pasta_bowl":       "a ceramic bowl of penne pasta",
  "stomach":          "the human stomach with the lower esophagus and duodenum, anterior view",
  "lungs":            "a pair of human lungs with the trachea and bronchi, anterior view",
  "eye":              "a human eye in sagittal section showing lens, retina and optic nerve",
  "pancreas":         "the human pancreas with duodenum and spleen, anterior view",
  "sleep_bed":        "a person asleep in a simple bed seen from the side, a crescent moon through a small window, soft blue evening light",
  "caffeine_cup":     "a ceramic cup of black coffee with rising steam, two roasted coffee beans beside it, botanical plate style",
  "weighted_vest":    "a plain weighted vest with small pockets across the chest and back, front view on a mannequin torso",
  "kidney":           "a single human kidney cut in coronal section showing cortex, medulla, pelvis and ureter, with the renal artery and vein",
  "blood_pressure_cuff": "an upper arm with an inflatable blood pressure cuff and a round dial gauge beside it, anterior view",
  "dopamine_neuron":  "a purple astrocyte and a grey dopamine neuron side by side, golden cholesterol droplets passing between them",
}

def _gemini(prompt, out):
    import requests
    key = os.environ["GEMINI_API_KEY"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent?key={key}"
    r = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseModalities": ["IMAGE"]}}, timeout=120)
    r.raise_for_status()
    for part in r.json()["candidates"][0]["content"]["parts"]:
        if "inlineData" in part:
            out.write_bytes(base64.b64decode(part["inlineData"]["data"])); return out
    raise RuntimeError("no image in response")

def _openai(prompt, out):
    import requests
    r = requests.post("https://api.openai.com/v1/images/generations", headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
                      json={"model": "gpt-image-1", "prompt": prompt, "size": "1024x1024", "background": "opaque", "quality": "high"}, timeout=180)
    r.raise_for_status(); out.write_bytes(base64.b64decode(r.json()["data"][0]["b64_json"])); return out

def normalize(path):
    """Illustration contrast normalization: PIL autocontrast (clip 1%) + flatten alpha onto the card background."""
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return path
    im = Image.open(path)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA"); bg = Image.new("RGBA", im.size, (247, 245, 240, 255)); im = Image.alpha_composite(bg, im)
    im = ImageOps.autocontrast(im.convert("RGB"), cutoff=1)
    im.save(path); return path

def generate(description, out):
    prompt = f"{description}. {STYLE}"
    if DRY_RUN is not None:
        DRY_RUN.append({"out": str(out), "prompt": prompt}); return out
    be = os.environ.get("HERO_BACKEND", "gemini")
    (_gemini if be == "gemini" else _openai)(prompt, out)
    normalize(out)
    ok, txt = ocr_check(out)
    if ok is False:
        rej = out.with_name(out.stem + ".REJECTED_text" + out.suffix); out.rename(rej)
        raise RuntimeError(f"OCR gate: generated image contains text {txt!r}; moved to {rej.name}. Regenerate.")
    return out

DRY_RUN = None   # list when --dry-run: prompts are collected instead of sent

def build_library(only=None):
    man = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    for tag, desc in LIBRARY.items():
        if only and tag not in only: continue
        have = lib_path(tag)
        if have: man[tag] = str(have); continue
        out = LIB / f"{tag}.png"
        print("generating", tag, file=sys.stderr); generate(desc, out); man[tag] = str(out)
        MANIFEST.write_text(json.dumps(man, indent=1))
    MANIFEST.write_text(json.dumps(man, indent=1)); return man

EXTS = (".png", ".jpg", ".jpeg", ".webp")

def _manifest():
    try: return json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    except ValueError: return {}

def lib_path(tag):
    """Library file for a tag, any of the accepted extensions (png first), then a manifest entry whose file exists, or None."""
    for ext in EXTS:
        q = LIB / f"{tag}{ext}"
        if q.exists(): return q
    ent = _manifest().get(tag)
    f = ent.get("file") if isinstance(ent, dict) else ent
    if f:
        q = pathlib.Path(f); q = q if q.is_absolute() else HERE / q
        if q.exists(): return q
    return None

def register(tag, file=None, prompt=None, status=None):
    """72. Manifest entry mechanism: add or update a library subject without generating anything. An entry without an
    existing file is 'pending' (a prompt waiting for an image); cards using it fall back to the full-width layout until
    the file lands. Drop a watercolor into assets/library/<tag>.jpg or point `file` at it."""
    man = _manifest(); ent = man.get(tag) if isinstance(man.get(tag), dict) else {"file": man.get(tag)} if man.get(tag) else {}
    if file: ent["file"] = str(file)
    if prompt or tag in LIBRARY: ent["prompt"] = prompt or f"{LIBRARY[tag]}. {STYLE}"
    f = ent.get("file"); have = bool(f and (pathlib.Path(f) if pathlib.Path(f).is_absolute() else HERE / f).exists())
    ent["status"] = status or ("ready" if have or lib_path(tag) else "pending")
    man[tag] = ent; MANIFEST.write_text(json.dumps(man, indent=1)); return ent

def missing():
    """Library subjects (and manifest entries) that have no image file yet."""
    tags = list(LIBRARY) + [t for t in _manifest() if t not in LIBRARY]
    return [t for t in tags if not lib_path(t)]

# Concept -> organ tags (item 18). A disease, nutrient or outcome named on a card maps to the anatomy that
# shows where it acts; the first tag is the stat_row icon, the full list is for band / multi-organ heroes.
CONCEPT_ORGANS = {
    "dementia": ["brain_sagittal"], "alzheimer": ["brain_sagittal"], "cognit": ["brain_lateral"], "memory": ["brain_sagittal"],
    "stroke": ["brain_lateral", "artery_plaque"], "parkinson": ["brain_coronal_sn", "dopamine_neuron"], "depress": ["brain_lateral"],
    "heart failure": ["heart_whole"], "atrial fibrillation": ["heart_atrium_cut"], "arrhythm": ["heart_atrium_cut"],
    "ischemic heart": ["artery_plaque"], "coronary": ["artery_plaque"], "myocardial": ["artery_plaque", "heart_whole"],
    "blood pressure": ["blood_pressure_cuff", "heart_whole", "artery_plaque"], "hypertension": ["blood_pressure_cuff", "heart_whole", "artery_plaque"], "cholesterol": ["artery_plaque", "liver_kidneys"],
    "diabetes": ["pancreas"], "glucose": ["pancreas", "muscle_fibre"], "insulin": ["pancreas"],
    "fatty liver": ["liver_kidneys"],
    "osteopor": ["bone_vertebra"], "fracture": ["bone_vertebra"], "bone": ["bone_vertebra"], "menopause": ["bone_vertebra"],
    "muscle": ["muscle_arm", "muscle_fibre"], "sarcopenia": ["muscle_arm"], "protein synthesis": ["muscle_fibre"],
    "gut": ["gut_villi", "gut_microbes"], "bowel": ["gut_villi"], "microbiome": ["gut_microbes"], "ibs": ["gut_villi"], "colorectal": ["gut_microbes"],
    "stomach": ["stomach"], "reflux": ["stomach"], "lung": ["lungs"], "copd": ["lungs"], "asthma": ["lungs"],
    "eye": ["eye"], "macular": ["eye"], "skin": ["skin_sun"], "melanoma": ["skin_sun"],
    "vitamin d": ["skin_sun", "bone_vertebra"], "b12": ["brain_sagittal", "stomach", "skin_sun"], "b12 deficiency": ["brain_sagittal", "stomach", "skin_sun"],
    "myelin": ["myelin_axon"], "multiple sclerosis": ["myelin_axon"], "neuropathy": ["myelin_axon"],
    "inflammation": ["artery_plaque"], "blood test": ["vein_forearm"], "fasting": ["vein_forearm"],
    "sleep": ["sleep_bed"], "insomnia": ["sleep_bed"], "caffeine": ["caffeine_cup", "coffee_plant"], "vest": ["weighted_vest"],
    "renal": ["kidney"], "ckd": ["kidney"], "kidney": ["kidney", "liver_kidneys"], "liver": ["liver_kidneys"],
    "blueberr": ["blueberries"], "coffee": ["coffee_plant"], "rice": ["rice_bowl"], "potato": ["potato_halved"], "pasta": ["pasta_bowl"], "stairs": ["stairs"],
}

def organs_for(concept: str):
    """All organ tags for a concept (longest matching key wins, then any others that also match)."""
    s = concept.lower(); hits = []
    for k in sorted(CONCEPT_ORGANS, key=len, reverse=True):
        if re.search(r"(?<![a-z])" + re.escape(k), s):          # word start: "ibs" no longer matches "exhibits", "eye" not "eyebrow"
            for t in CONCEPT_ORGANS[k]:
                if t not in hits: hits.append(t)
    return hits

def pick(subject: str):
    """Library path for a card subject or label: concept map first, then the crude tag-word match. Accepts .png/.jpg."""
    for tag in organs_for(subject):
        q = lib_path(tag)
        if q: return q
    return None

# ---------------------------------------------------------------- gates on generated art (item 19)
def ocr_check(path, max_chars=2):
    """Reject leaked text: tesseract on the image; fail when it finds more than `max_chars` confident letters/digits.
    Returns (ok, found_text). Without pytesseract the gate reports (None, reason)."""
    try:
        import pytesseract
        from PIL import Image, ImageOps
    except ImportError as e:
        return None, f"pytesseract unavailable: {e}"
    im = ImageOps.autocontrast(Image.open(path).convert("L"))
    d = pytesseract.image_to_data(im, output_type=pytesseract.Output.DICT, config="--psm 11")
    words = [w for w, c in zip(d["text"], d["conf"]) if w.strip() and float(c) >= 70 and sum(ch.isalnum() for ch in w) >= 2]
    found = " ".join(words)
    return (sum(ch.isalnum() for ch in found) <= max_chars), found

def fingerprint(path):
    """Style fingerprint: mean Lab-ish colour, saturation and edge density on a 128px thumbnail."""
    from PIL import Image, ImageFilter, ImageStat
    im = Image.open(path).convert("RGB"); im.thumbnail((128, 128))
    hsv = im.convert("HSV"); st = ImageStat.Stat(im); sh = ImageStat.Stat(hsv)
    edges = ImageStat.Stat(im.convert("L").filter(ImageFilter.FIND_EDGES)).mean[0]
    return [round(v, 2) for v in (*st.mean, sh.mean[1], sh.mean[2], edges)]

def drift_check(path, tol=2.5):
    """Compare an image's fingerprint with the library atlas (mean ± sd per feature). Flags features > tol sd away."""
    import statistics
    lib = [q for q in LIB.iterdir() if q.suffix.lower() in EXTS and q.resolve() != pathlib.Path(path).resolve()]
    if len(lib) < 3: return None, "atlas too small for a drift check"
    fps = [fingerprint(q) for q in lib]; me = fingerprint(path)
    names = ["R", "G", "B", "sat", "val", "edges"]; bad = []
    for i, n in enumerate(names):
        col = [f[i] for f in fps]; mu = statistics.mean(col); sd = statistics.pstdev(col) or 1.0
        if abs(me[i] - mu) / sd > tol: bad.append(f"{n} {me[i]} vs atlas {mu:.1f}±{sd:.1f}")
    return (not bad), bad

def gate(path):
    """Both gates; returns a dict and prints a one-line verdict."""
    ok_t, txt = ocr_check(path); ok_d, drift = drift_check(path)
    r = {"path": str(path), "no_text": ok_t, "text_found": txt, "style_ok": ok_d, "drift": drift}
    print(("PASS" if ok_t is not False and ok_d is not False else "FAIL"), path, "| text:", repr(txt)[:60], "| drift:", drift)
    return r

def hero_image(p, pad=0.06, tol=18):
    """59. Hero crop: background tint -> transparent (no faint box edge on the card), crop to the subject, then the SAME margin
    on all four sides (pad = fraction of the subject's longer side), cached under assets/.trim/. Returns a file:// URI or None."""
    if not p or re.match(r"^(https?:|data:)", str(p)): return None
    src = pathlib.Path(str(p).replace("file://", "")); src = src if src.is_absolute() else HERE / src
    if not src.exists(): return None
    cache = HERE / "assets" / ".trim"; cache.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f"hero:{src.resolve()}:{src.stat().st_mtime_ns}:{pad}:{tol}".encode()).hexdigest()[:12]
    out = cache / f"{src.stem}.hero.{key}.png"
    if not out.exists():
        from PIL import Image, ImageChops, ImageFilter
        im = Image.open(src).convert("RGB"); w, h = im.size
        corners = [im.getpixel(xy) for xy in ((2, 2), (w - 3, 2), (2, h - 3), (w - 3, h - 3))]
        bg = tuple(sorted(c[i] for c in corners)[2] for i in range(3))
        diff = ImageChops.difference(im, Image.new("RGB", im.size, bg)).convert("L")
        alpha = diff.point(lambda v: 0 if v < tol * 0.5 else 255 if v > tol * 2 else int((v - tol * 0.5) / (tol * 1.5) * 255)).filter(ImageFilter.GaussianBlur(1.0))
        mask = diff.point(lambda v: 255 if v > tol else 0).filter(ImageFilter.MedianFilter(5))      # specks do not widen the box
        box = mask.getbbox() or (0, 0, w, h)
        m = int(max(box[2] - box[0], box[3] - box[1]) * pad)
        rgba = im.copy(); rgba.putalpha(alpha)
        cw, ch = box[2] - box[0] + 2 * m, box[3] - box[1] + 2 * m
        canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0)); canvas.paste(rgba.crop(box), (m, m)); canvas.save(out)
    return out.resolve().as_uri()

def fill_card(card_path):
    """Sets hero.image from the tagged match (hero_match.decide) and the stat_row icons. NEVER generates an image: a card whose
    outcome has no library image gets no hero and a recorded reason; missing library images are listed by `python hero.py needs`."""
    import hero_match
    doc = json.loads(pathlib.Path(card_path).read_text()); c = doc["card"]
    hero_match.apply(c, doc.get("facts"))
    db = c["data_block"]
    if db["type"] == "stat_row" and not db.get("icons"):
        icons = []
        for it in db["items"]:
            p = pick(it["label"])
            icons.append(os.path.relpath(p, HERE) if p else None)
        db["icons"] = icons
    if DRY_RUN is not None:
        print("dry run: hero:", c["hero"].get("image"), "|", hero_match.explain(c["hero"]["decision"])); return
    pathlib.Path(card_path).write_text(json.dumps(doc, indent=2, ensure_ascii=False))
    print(hero_match.explain(c["hero"]["decision"]), "icons:", db.get("icons"))

def needs():
    """Library images that would be used if they existed: pending manifest entries, with their prompts (for a human to supply)."""
    import hero_match
    return {t: {"sites": e.get("sites"), "prompt": e.get("prompt"), "note": e.get("note")} for t, e in hero_match.tagged_library().items() if not e["usable"]}

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    if "--dry-run" in sys.argv:
        DRY_RUN = []
    if not args: print(__doc__); sys.exit(1)
    if args[0] == "build-library": build_library(args[1:] or None)
    elif args[0] == "gate":
        rs = [gate(pathlib.Path(q)) for q in (args[1:] or sorted(str(q) for q in LIB.iterdir() if q.suffix.lower() in EXTS))]
        if any(r["no_text"] is False or r["style_ok"] is False for r in rs): sys.exit(1)
    elif args[0] == "needs": print(json.dumps(needs(), indent=1))
    elif args[0] == "organs":
        print(json.dumps({q: [str(lib_path(t) or t + " (missing)") for t in organs_for(q)] for q in args[1:]}, indent=1))
    elif args[0] == "normalize":
        for q in args[1:]: normalize(pathlib.Path(q)); print("normalized", q)
    else: fill_card(args[0])
    if DRY_RUN is not None:
        outp = HERE / "out" / "hero_prompts.json"; outp.parent.mkdir(exist_ok=True)
        outp.write_text(json.dumps(DRY_RUN, indent=1)); print(f"dry run: {len(DRY_RUN)} prompt(s) written to {outp}")
