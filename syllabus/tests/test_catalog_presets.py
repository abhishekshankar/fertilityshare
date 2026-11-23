import json
from pathlib import Path

from syllabus.models.schemas import IntakeData

PRESETS = Path(__file__).resolve().parents[2] / "catalog" / "presets.json"


def test_presets_valid_and_unique():
    presets = json.loads(PRESETS.read_text())
    slugs = [p["slug"] for p in presets]
    assert len(slugs) == len(set(slugs)) >= 5
    for p in presets:
        IntakeData.model_validate(p["intake"])
