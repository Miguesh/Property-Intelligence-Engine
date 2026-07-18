"""Framework-independent listing boundary invariants."""

import pytest

from property_intelligence.domain.models import GeneratedContent, Listing, Location


def _listing(**overrides: object) -> Listing:
    values: dict[str, object] = {
        "title": "Bounded apartment",
        "description": "A valid listing description.",
        "amenities": (),
        "property_type": "Apartment",
        "location": Location(city="Miami", country="US"),
    }
    values.update(overrides)
    return Listing(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "overrides",
    [
        {"title": "x" * 201},
        {"description": "x" * 10_001},
        {"property_type": "x" * 101},
        {"amenities": ("x" * 121,)},
        {"amenities": tuple(f"amenity-{index}" for index in range(101))},
        {"language": "not-a-language-tag"},
        {"language": "es"},
    ],
)
def test_listing_rejects_out_of_bounds_direct_domain_input(overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        _listing(**overrides)


def test_location_rejects_out_of_bounds_direct_domain_input() -> None:
    with pytest.raises(ValueError):
        Location(city="x" * 121, country="US")


@pytest.mark.parametrize(
    ("titles", "descriptions", "tags"),
    [
        (("One", "Two"), ("First.", "Second."), tuple(f"tag-{i}" for i in range(8))),
        (
            ("One", "Two", "Three"),
            ("First.",),
            tuple(f"tag-{i}" for i in range(8)),
        ),
        (
            ("One", "Two", "Three"),
            ("First.", "Second."),
            tuple(f"tag-{i}" for i in range(7)),
        ),
    ],
)
def test_generated_content_enforces_stable_cardinality(
    titles: tuple[str, ...],
    descriptions: tuple[str, ...],
    tags: tuple[str, ...],
) -> None:
    with pytest.raises(ValueError):
        GeneratedContent(
            titles=titles,
            descriptions=descriptions,
            tags=tags,
            source="fixture",
            prompt_version="fixture-v1",
        )
