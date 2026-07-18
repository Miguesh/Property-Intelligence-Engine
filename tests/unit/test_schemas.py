from __future__ import annotations

import pytest
from pydantic import ValidationError

from property_intelligence.interfaces.api.schemas import ListingAnalysisRequest


def valid_payload() -> dict[str, object]:
    return {
        "title": "  Ocean View Condo  ",
        "description": "A bright condo near the beach with fast Wi-Fi.",
        "amenities": ["Wi-Fi", " wifi ", "Kitchen"],
        "property_type": "Condo",
        "location": {"city": "Miami", "country": "US"},
    }


def test_request_normalizes_and_maps_to_domain() -> None:
    request = ListingAnalysisRequest.model_validate(valid_payload())
    listing = request.to_domain()

    assert listing.title == "Ocean View Condo"
    assert listing.amenities == ("Wi-Fi", "Kitchen")
    assert listing.location.display_name == "Miami, US"


def test_request_rejects_unknown_fields() -> None:
    payload = valid_payload()
    payload["unexpected"] = "not allowed"

    with pytest.raises(ValidationError):
        ListingAnalysisRequest.model_validate(payload)


def test_request_rejects_oversized_description() -> None:
    payload = valid_payload()
    payload["description"] = "x" * 10_001

    with pytest.raises(ValidationError):
        ListingAnalysisRequest.model_validate(payload)


def test_request_rejects_oversized_amenity_item() -> None:
    payload = valid_payload()
    payload["amenities"] = ["x" * 121]

    with pytest.raises(ValidationError):
        ListingAnalysisRequest.model_validate(payload)


def test_request_rejects_unsupported_non_english_language() -> None:
    payload = valid_payload()
    payload["language"] = "es"

    with pytest.raises(ValidationError):
        ListingAnalysisRequest.model_validate(payload)
