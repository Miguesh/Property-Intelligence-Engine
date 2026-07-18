from __future__ import annotations

import pytest

from property_intelligence.application.ports import GenerationRequest
from property_intelligence.domain.analysis import ListingAnalysisEngine
from property_intelligence.domain.claim_validation import (
    GeneratedContentClaimValidator,
    UnsupportedGeneratedClaimError,
    find_claim_violations,
)
from property_intelligence.domain.models import GeneratedContent, Listing, Location
from property_intelligence.infrastructure.ai.fallback import DeterministicListingGenerator


def _generated(
    *,
    titles: tuple[str, ...],
    descriptions: tuple[str, ...],
    tags: tuple[str, ...],
) -> GeneratedContent:
    def padded(values: tuple[str, ...], reserve: tuple[str, ...], count: int) -> tuple[str, ...]:
        unique = list(dict.fromkeys((*values, *reserve)))
        return tuple(unique[:count])

    return GeneratedContent(
        titles=padded(
            titles,
            ("Listing Copy Option", "Alternative Listing Copy", "Additional Listing Copy"),
            3,
        ),
        descriptions=padded(
            descriptions,
            (
                "Review the submitted listing facts before publishing this suggestion.",
                "Compare this draft with the submitted listing details before use.",
            ),
            2,
        ),
        tags=padded(
            tags,
            (
                "editorial suggestion",
                "listing copy",
                "verified facts",
                "host review",
                "travel listing",
                "content draft",
                "property details",
                "listing suggestion",
            ),
            8,
        ),
        source="fixture",
        prompt_version="fixture-v1",
    )


def _listing() -> Listing:
    return Listing(
        title="Two-bedroom loft with a hot tub",
        description=(
            "This loft sleeps 4 guests and has panoramic ocean views, a kitchen, "
            "and wireless internet."
        ),
        amenities=("Jacuzzi", "Wireless internet", "Full kitchen"),
        property_type="loft",
        location=Location(
            city="Austin",
            country="United States",
            region="Texas",
            neighborhood="East Austin",
        ),
    )


def test_validator_allows_supported_aliases_and_equivalent_numbers() -> None:
    generated = _generated(
        titles=("East Austin Loft with Wi-Fi and Hot Tub",),
        descriptions=(
            "A 2-bedroom loft for four guests with ocean views, Wi-Fi, and a full kitchen.",
        ),
        tags=("loft", "hot tub", "Wi-Fi", "4 guests"),
    )

    GeneratedContentClaimValidator().validate(_listing(), generated)


def test_validator_reports_features_numbers_and_contact_channels() -> None:
    generated = _generated(
        titles=("Pool Villa with Mountain Views",),
        descriptions=(
            "A 7-minute walk away. Visit https://example.com, email host@example.com, "
            "or call +1 (305) 555-0199.",
        ),
        tags=("pool", "mountain view"),
    )

    violations = find_claim_violations(_listing(), generated)
    codes = {violation.code for violation in violations}
    unsupported_features = {
        violation.claim for violation in violations if violation.code == "unsupported_feature"
    }

    assert {"pool", "view_mountain"} <= unsupported_features
    assert "unsupported_number" in codes
    assert {"contact_url", "contact_email", "contact_phone"} <= codes
    with pytest.raises(UnsupportedGeneratedClaimError):
        GeneratedContentClaimValidator().validate(_listing(), generated)


def test_quantities_are_grounded_by_unit_and_proximity_context() -> None:
    listing = Listing(
        title="Quiet city retreat",
        description="Sleeps 4 guests. Quiet hours begin at 10 PM.",
        amenities=(),
        property_type="house",
        location=Location(city="Boston", country="US"),
    )
    generated = _generated(
        titles=("A four-bedroom retreat just a 10-minute walk from the convention center.",),
        descriptions=("A quiet city stay.",),
        tags=("retreat",),
    )

    violations = find_claim_violations(listing, generated)
    unsupported_quantities = {
        violation.claim for violation in violations if violation.code == "unsupported_quantity"
    }
    codes = {violation.code for violation in violations}

    assert {"bedrooms:4", "proximity_minutes:10"} <= unsupported_quantities
    assert {"unsupported_landmark", "unsupported_proximity"} <= codes


def test_property_type_cannot_change_and_public_pool_is_not_property_evidence() -> None:
    listing = Listing(
        title="Downtown Loft",
        description="A five-minute walk to the public swimming pool.",
        amenities=("Wi-Fi",),
        property_type="loft",
        location=Location(city="Austin", country="US"),
    )
    generated = _generated(
        titles=(
            "Austin Villa with a Swimming Pool",
            "Villa Stay in Austin",
            "Austin Pool Villa",
        ),
        descriptions=(
            "Enjoy this villa with a swimming pool in Austin.",
            "Make this Austin villa with a pool your next stay.",
        ),
        tags=(
            "villa",
            "swimming pool",
            "Austin",
            "Texas stay",
            "short-term rental",
            "travel lodging",
            "guest stay",
            "local stay",
        ),
    )

    violations = find_claim_violations(listing, generated)
    claims_by_code = {(violation.code, violation.claim) for violation in violations}

    assert ("unsupported_property_type", "villa") in claims_by_code
    assert ("unsupported_feature", "pool") in claims_by_code


def test_concrete_property_attributes_require_submitted_evidence() -> None:
    listing = Listing(
        title="Austin Loft",
        description="A loft with Wi-Fi and a kitchen.",
        amenities=("Wi-Fi", "Kitchen"),
        property_type="loft",
        location=Location(city="Austin", country="US"),
    )
    generated = _generated(
        titles=("Spacious, Bright Luxury Loft",),
        descriptions=("A newly renovated modern loft in Austin.",),
        tags=("upscale", "roomy", "contemporary"),
    )

    unsupported_attributes = {
        violation.claim
        for violation in find_claim_violations(listing, generated)
        if violation.code == "unsupported_feature" and violation.claim.startswith("attribute_")
    }

    assert unsupported_attributes == {
        "attribute_bright",
        "attribute_luxury",
        "attribute_modern",
        "attribute_renovated",
        "attribute_spacious",
    }


def test_property_attribute_aliases_are_allowed_when_grounded() -> None:
    listing = Listing(
        title="Roomy contemporary loft",
        description="A sunlit, refurbished, upscale loft with Wi-Fi.",
        amenities=("Wi-Fi",),
        property_type="loft",
        location=Location(city="Austin", country="US"),
    )
    generated = _generated(
        titles=("Spacious Modern Austin Loft",),
        descriptions=("A bright, renovated luxury loft in Austin.",),
        tags=("loft", "Wi-Fi"),
    )

    GeneratedContentClaimValidator().validate(listing, generated)


@pytest.mark.asyncio
async def test_deterministic_fallback_copy_passes_claim_validation() -> None:
    listing = _listing()
    generator = DeterministicListingGenerator()
    generated = await generator.generate(
        GenerationRequest(
            listing=listing,
            analysis=ListingAnalysisEngine().analyze(listing),
            knowledge=(),
        )
    )

    GeneratedContentClaimValidator().validate(listing, generated)
