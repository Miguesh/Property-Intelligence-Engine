"""Focused tests for the provider-independent listing analysis engine."""

from __future__ import annotations

import pytest

from property_intelligence.domain.analysis import ListingAnalysisEngine
from property_intelligence.domain.models import Listing, Location, Priority
from property_intelligence.domain.normalization import normalize_listing


@pytest.fixture
def engine() -> ListingAnalysisEngine:
    return ListingAnalysisEngine()


def _listing(
    *,
    title: str = "Nice Place",
    description: str = "A nice place to stay.",
    amenities: tuple[str, ...] = (),
    property_type: str = "Apartment",
) -> Listing:
    return Listing(
        title=title,
        description=description,
        amenities=amenities,
        property_type=property_type,
        location=Location(city="Miami", region="Florida", country="USA"),
    )


def _rich_listing() -> Listing:
    return _listing(
        title="Waterfront Miami Condo with Pool & Workspace",
        description=(
            "Modern waterfront condo in Miami with an ocean view, private balcony, "
            "pool, fast Wi-Fi, and a dedicated workspace. This 2 bedroom, 2 bathroom "
            "home has 3 beds and sleeps 6 guests, making it ideal for families and "
            "remote work.\n\n"
            "Guest access:\n"
            "- Self check-in with a smart lock.\n"
            "- Free parking and a full kitchen.\n"
            "- Washer, dryer, air conditioning, and cooking basics.\n\n"
            "Walk 5 minutes to the beach and drive 15 minutes to Miami International "
            "Airport. Please note that the building has an elevator and quiet hours "
            "after 10 p.m. No parties or smoking. Safety amenities include a smoke "
            "alarm, carbon monoxide alarm, fire extinguisher, and first-aid kit."
        ),
        amenities=(
            "Wi-Fi",
            "Smoke detector",
            "CO detector",
            "Fire extinguisher",
            "First aid kit",
            "Air conditioning",
            "Smart lock",
            "Full kitchen",
            "Refrigerator",
            "Cooking basics",
            "Washer",
            "Dryer",
            "Free parking",
            "Pool",
            "Ocean view",
            "Balcony",
            "Dedicated workspace",
        ),
        property_type="Condo",
    )


def test_rich_listing_substantially_outscores_sparse_listing(
    engine: ListingAnalysisEngine,
) -> None:
    rich = engine.analyze(_rich_listing())
    sparse = engine.analyze(_listing())

    assert rich.listing_quality.value >= 85
    assert rich.seo.value >= 80
    assert rich.readability.value >= 70
    assert rich.listing_quality.value > sparse.listing_quality.value + 50
    assert rich.seo.value > sparse.seo.value + 40
    assert rich.weaknesses == ()
    assert sparse.weaknesses


def test_analysis_is_deterministic_and_explainable(
    engine: ListingAnalysisEngine,
) -> None:
    listing = _rich_listing()

    first = engine.analyze(listing)
    second = engine.analyze(listing)

    assert first == second
    for score in (first.listing_quality, first.seo, first.readability):
        assert 0 <= score.value <= 100
        assert sum(component.weight for component in score.components) == pytest.approx(1)
        assert all(component.rationale for component in score.components)
        assert score.methodology == engine.methodology


def test_amenity_aliases_are_deduplicated_and_negated_mentions_do_not_count() -> None:
    normalized = normalize_listing(
        _listing(
            description=(
                "This apartment in Miami has wireless internet. "
                "There is no parking available and no swimming pool."
            ),
            amenities=("Wi-Fi", "wifi", "High speed internet"),
        )
    )

    assert normalized.amenities == frozenset({"wifi"})
    assert "parking" not in normalized.amenities
    assert "pool" not in normalized.amenities


@pytest.mark.parametrize(
    "description",
    [
        "The pool is unavailable during this stay.",
        "A smoke alarm is not installed in the apartment.",
        "Parking is currently under repair.",
        "The elevator isn't available to guests.",
    ],
)
def test_postposed_negations_do_not_count_as_available_amenities(description: str) -> None:
    normalized = normalize_listing(_listing(description=description))

    assert normalized.amenities == frozenset()


def test_qualified_positive_amenities_are_not_mistaken_for_absent_ones() -> None:
    normalized = normalize_listing(
        _listing(
            description=(
                "Not only a pool is provided, but it is also not heated. "
                "Wi-Fi is available, not shared with another unit."
            )
        )
    )

    assert {"pool", "wifi"} <= normalized.amenities


def test_public_off_property_amenity_is_not_counted_as_a_listing_amenity() -> None:
    normalized = normalize_listing(
        _listing(
            description=(
                "Fast Wi-Fi is included. The public swimming pool is a five-minute walk away."
            )
        )
    )

    assert "wifi" in normalized.amenities
    assert "pool" not in normalized.amenities


def test_described_amenity_is_not_recommended_as_missing(
    engine: ListingAnalysisEngine,
) -> None:
    analysis = engine.analyze(
        _listing(
            description=(
                "This Miami apartment includes wireless internet and self check-in. "
                "It is a comfortable option for a short city visit."
            )
        )
    )

    names = {suggestion.name for suggestion in analysis.missing_amenities}
    assert "Wi-Fi" not in names
    assert "Self check-in" not in names
    assert all(
        suggestion.reason.startswith("Not listed:") for suggestion in analysis.missing_amenities
    )


def test_missing_safety_items_are_prioritized_and_truth_safe(
    engine: ListingAnalysisEngine,
) -> None:
    analysis = engine.analyze(_listing())

    first_names = {item.name for item in analysis.missing_amenities[:4]}
    assert {"Smoke alarm", "Fire extinguisher", "Carbon monoxide alarm"} <= first_names
    assert all(
        item.priority is Priority.HIGH
        for item in analysis.missing_amenities
        if item.name in first_names
    )
    assert any("Verify" in item.reason for item in analysis.missing_amenities)
    assert any(
        improvement.category == "amenities" and "accurately list" in improvement.recommendation
        for improvement in analysis.improvements
    )


def test_short_copy_has_readability_cap(engine: ListingAnalysisEngine) -> None:
    short = engine.analyze(_listing(description="Bright, calm, easy."))
    expanded = engine.analyze(
        _listing(
            description=(
                "This bright Miami apartment offers a calm base for couples visiting "
                "the city. The living area has comfortable seating, a dining table, "
                "and fast Wi-Fi for planning each day.\n\n"
                "Guests can use self check-in and reach downtown by bus in 10 minutes. "
                "The bedroom has one queen bed, and the bathroom has a walk-in shower. "
                "Please note the quiet hours after 10 p.m."
            ),
            amenities=("Wi-Fi", "Self check-in"),
        )
    )

    assert short.readability.value <= 25
    assert expanded.readability.value > short.readability.value


def test_repeated_amenities_do_not_inflate_scores(
    engine: ListingAnalysisEngine,
) -> None:
    once = engine.analyze(
        _listing(
            description="This Miami apartment includes Wi-Fi and a pool for guests.",
            amenities=("Wi-Fi", "Pool"),
        )
    )
    repeated = engine.analyze(
        _listing(
            description="This Miami apartment includes Wi-Fi and a pool for guests.",
            amenities=("Wi-Fi", "wifi", "Wireless internet", "Pool", "Swimming pool"),
        )
    )

    assert repeated.listing_quality.value == once.listing_quality.value
    assert repeated.seo.value == once.seo.value


def test_audience_signals_only_enable_relevant_optional_suggestions(
    engine: ListingAnalysisEngine,
) -> None:
    core_amenities = (
        "Wi-Fi",
        "Smoke alarm",
        "CO alarm",
        "Fire extinguisher",
        "First aid kit",
        "Air conditioning",
        "Self check-in",
        "Kitchen",
        "Washer",
    )
    generic = engine.analyze(
        _listing(
            description="A Miami apartment with a comfortable living room.",
            amenities=core_amenities,
        )
    )
    targeted = engine.analyze(
        _listing(
            description=(
                "A Miami apartment designed for families and remote work, with space "
                "for children and business travelers."
            ),
            amenities=core_amenities,
        )
    )

    generic_names = {item.name for item in generic.missing_amenities}
    targeted_names = {item.name for item in targeted.missing_amenities}
    assert "Crib or travel cot" not in generic_names
    assert "Dedicated workspace" not in generic_names
    assert "Crib or travel cot" in targeted_names
    assert "Dedicated workspace" in targeted_names


def test_configuration_feedback_requires_bathroom_count_even_with_three_other_facts(
    engine: ListingAnalysisEngine,
) -> None:
    analysis = engine.analyze(
        _listing(
            description=(
                "This Miami apartment sleeps 6 guests and has 2 bedrooms with 3 beds. "
                "It offers a comfortable base for a city stay."
            )
        )
    )

    assert not any("bathroom count" in strength for strength in analysis.strengths)
    assert "The description does not state a verified bathroom count." in analysis.weaknesses
    content_improvement = next(
        improvement for improvement in analysis.improvements if improvement.category == "content"
    )
    assert content_improvement.recommendation == ("State a verified bathroom count explicitly.")


def test_configuration_feedback_names_missing_capacity_without_repeating_present_facts(
    engine: ListingAnalysisEngine,
) -> None:
    analysis = engine.analyze(
        _listing(
            description=(
                "This Miami apartment has 2 bedrooms, 3 beds, and 2 bathrooms. "
                "It offers a comfortable base for a city stay."
            )
        )
    )

    assert not any("sleeping layout" in strength for strength in analysis.strengths)
    assert "The description does not state verified guest capacity." in analysis.weaknesses
    content_improvement = next(
        improvement for improvement in analysis.improvements if improvement.category == "content"
    )
    assert content_improvement.recommendation == "State verified guest capacity explicitly."
