# FertilityShare evidence card pipeline

Paper → one Wallace-style science card, 1080×1350 px.

Same visual grammar and block library as the evidencebased card pipeline. Adapted for
fertility / reproductive medicine: fertility-specific extract prompt, strength-cap rules,
and hero anatomy vocabulary.

## Graph

```
PDF ──► extract ──► facts.json ──► plan ──► fill ──► card.json ──► render ──► PNG ──► critique ──► ship
          │  L0        │               │        │  L1,L3                │  L2                 │  L4
          │  quotes    │               │        │  numbers, strength    │  fit loop           │  vision QA
          └────────────┘               └────────┘                       └─────────────────────┘
```

| Loop | Gate | Action |
|------|------|--------|
| **L0** | every `quote` appears verbatim (fuzzy 6-gram) in source | re-extract with failures named, ×1 |
| **L1** | every `ref` resolves; `payoff` ⊂ headline; `highlight` ⊂ takeaway | re-fill with failures, ×2 |
| **L3** | `takeaway.strength` ≤ design cap; no causal verb in observational headline | re-fill |
| **L2** | content height 93–100% of canvas | scale global font 0.9–1.1 |
| **L4** | vision model reads every number, checks overlap/clip, one-glance test | patches to card text only |

## Block library

Inherited from the template: `stat_row` · `stat_tiles` · `bar_h` (diverging) · `bar_v` ·
`stacked_100` · `line_area` · `forest` · `funnel` · `waffle` · `isotype` · `dotmatrix` ·
`range_bar` · `pathway` · `before_after` · `state_table` · `timeline`

## Run

```bash
pip install anthropic jinja2 pypdf playwright markupsafe
python -m playwright install chromium
export ANTHROPIC_API_KEY=...

python run.py paper.pdf --slug ivf2024 --brief "patients; live birth rate is the hook"
# → cards/ivf2024.json  out/ivf2024.png  out/ivf2024.report.json

# pieces
python plan.py cards/ivf2024.json          # block decision
python render.py cards/ivf2024.json        # re-render from saved card
python critique.py out/ivf2024.png cards/ivf2024.json --apply
```

## Corpus

`cards/` grows as cards ship. The planner's `retrieve()` scores them by block type,
design, species and domain to surface the most relevant exemplar(s) as few-shot context.

## Model

Default: `claude-sonnet-5-20251101`. Override: `export FS_MODEL=claude-opus-5`.
