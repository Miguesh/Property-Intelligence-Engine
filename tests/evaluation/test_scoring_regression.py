from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from property_intelligence.domain.analysis import ListingAnalysisEngine
from property_intelligence.domain.models import Listing, Location

CASES_PATH = Path(__file__).with_name("listing_cases.json")


def load_cases() -> list[dict[str, Any]]:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", load_cases(), ids=lambda case: case["id"])
def test_versioned_scoring_cases(case: dict[str, Any]) -> None:
    raw = case["listing"]
    listing = Listing(
        title=raw["title"],
        description=raw["description"],
        amenities=tuple(raw["amenities"]),
        property_type=raw["property_type"],
        location=Location(**raw["location"]),
    )
    result = ListingAnalysisEngine().analyze(listing)
    expected = case["expect"]

    if "quality_min" in expected:
        assert result.listing_quality.value >= expected["quality_min"]
    if "quality_max" in expected:
        assert result.listing_quality.value <= expected["quality_max"]
    if "seo_min" in expected:
        assert result.seo.value >= expected["seo_min"]
    if "seo_max" in expected:
        assert result.seo.value <= expected["seo_max"]
    if "readability_min" in expected:
        assert result.readability.value >= expected["readability_min"]
    if "minimum_weaknesses" in expected:
        assert len(result.weaknesses) >= expected["minimum_weaknesses"]
    if "must_recommend" in expected:
        names = {item.name for item in result.missing_amenities}
        assert set(expected["must_recommend"]) <= names
    if "must_not_strengthen" in expected:
        strengths = " ".join(result.strengths).casefold()
        assert all(term not in strengths for term in expected["must_not_strengthen"])
