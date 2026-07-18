"""Keep the editable and wheel-packaged guidance corpus copies identical."""

import json
from pathlib import Path


def test_editable_and_packaged_guidance_corpus_are_in_sync() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    editable = repository_root / "knowledge" / "listing_guidance.v1.json"
    packaged = (
        repository_root
        / "src"
        / "property_intelligence"
        / "infrastructure"
        / "knowledge"
        / "data"
        / "listing_guidance.v1.json"
    )

    assert json.loads(editable.read_text(encoding="utf-8")) == json.loads(
        packaged.read_text(encoding="utf-8")
    )
