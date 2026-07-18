"""Deterministic copy generation used when an LLM is unavailable."""

from __future__ import annotations

from collections.abc import Iterable

from property_intelligence.application.ports import GenerationRequest, TextGenerationPort
from property_intelligence.domain.claim_validation import strip_contact_channels
from property_intelligence.domain.models import (
    GENERATED_TITLE_COUNT,
    MAX_GENERATED_DESCRIPTION_LENGTH,
    MAX_GENERATED_TAG_LENGTH,
    MAX_GENERATED_TAGS,
    MAX_GENERATED_TITLE_LENGTH,
    GeneratedContent,
)

FALLBACK_PROMPT_VERSION = "deterministic-copy-v1"


class DeterministicListingGenerator(TextGenerationPort):
    """Create fact-preserving recommendations without external services."""

    async def generate(self, request: GenerationRequest) -> GeneratedContent:
        listing = request.listing
        property_type = _display_value(strip_contact_channels(listing.property_type)) or "Property"
        city = strip_contact_channels(listing.location.city) or "the local area"
        neighborhood = (
            strip_contact_channels(listing.location.neighborhood)
            if listing.location.neighborhood
            else None
        )
        safe_amenities = tuple(
            safe for amenity in listing.amenities if (safe := strip_contact_channels(amenity))
        )
        primary_amenity = _display_value(safe_amenities[0]) if safe_amenities else None

        title_candidates = [
            f"{property_type} Stay in {city}",
            (
                f"{primary_amenity} {property_type} in {city}"
                if primary_amenity
                else f"Explore {city} from This {property_type}"
            ),
            (
                f"{property_type} in {neighborhood}, {city}"
                if neighborhood
                else f"Your {city} {property_type} Getaway"
            ),
            f"Discover {city} from a {property_type}",
        ]
        title_reserve = (
            f"A Place to Stay in {city}",
            f"Rental Stay in {city}",
            f"Short-Term Stay in {city}",
            f"Travel Stay in {city}",
        )
        titles = tuple(
            _unique(_shorten_title(title) for title in (*title_candidates, *title_reserve))[
                :GENERATED_TITLE_COUNT
            ]
        )

        safe_description = strip_contact_channels(listing.description)
        original = _as_sentence(safe_description or "Review the submitted listing details")
        safe_location = ", ".join(
            value
            for raw_value in (
                listing.location.neighborhood,
                listing.location.city,
                listing.location.region,
                listing.location.country,
            )
            if raw_value and (value := strip_contact_channels(raw_value))
        )
        location_sentence = (
            f"The property is located in {safe_location}."
            if safe_location
            else "Review the submitted listing for location details."
        )
        amenity_sentence = (
            "Included amenities: " + ", ".join(safe_amenities[:8]) + "."
            if safe_amenities
            else "Review the listing details for the amenities included with the stay."
        )
        description_one = _shorten_description(
            " ".join((original, location_sentence, amenity_sentence))
        )
        description_two = _shorten_description(
            " ".join(
                (
                    f"Make this {property_type.casefold()} your base for a stay in {city}.",
                    original,
                    amenity_sentence,
                    "Book with confidence after reviewing the complete listing details "
                    "and policies.",
                )
            )
        )

        tag_candidates = [
            strip_contact_channels(listing.property_type),
            city,
            neighborhood,
            strip_contact_channels(listing.location.region or "") or None,
            strip_contact_channels(listing.location.country) or None,
            *safe_amenities[:7],
            "short-term rental",
            "vacation stay",
            "local stay",
            "rental accommodation",
            "guest stay",
            "travel lodging",
            "holiday accommodation",
            "short stay",
            "travel rental",
            "rental listing",
            "property stay",
            "temporary accommodation",
        ]
        tags = _unique(
            _shorten_tag(candidate) if candidate is not None else None
            for candidate in tag_candidates
        )

        return GeneratedContent(
            titles=titles,
            descriptions=(description_one, description_two),
            tags=tuple(tags[:MAX_GENERATED_TAGS]),
            source="deterministic",
            prompt_version=FALLBACK_PROMPT_VERSION,
        )


def _display_value(value: str) -> str:
    return " ".join(part.capitalize() for part in value.split())


def _shorten_title(value: str, limit: int = MAX_GENERATED_TITLE_LENGTH) -> str:
    if len(value) <= limit:
        return value
    shortened = value[: limit + 1].rsplit(" ", 1)[0].rstrip(" -,:;")
    return shortened if 0 < len(shortened) <= limit else value[:limit]


def _as_sentence(value: str, limit: int = 700) -> str:
    compact = " ".join(value.split())
    if len(compact) > limit:
        compact = compact[: limit + 1].rsplit(" ", 1)[0].rstrip(" ,;:")
    return compact if compact.endswith((".", "!", "?")) else f"{compact}."


def _shorten_description(value: str, limit: int = MAX_GENERATED_DESCRIPTION_LENGTH) -> str:
    compact = " ".join(value.split())
    if len(compact) > limit:
        compact = compact[: limit + 1].rsplit(" ", 1)[0].rstrip(" ,;:") or compact[:limit]
    if compact.endswith((".", "!", "?")):
        return compact
    if len(compact) >= limit:
        compact = compact[: limit - 1].rstrip(" ,;:")
    return f"{compact}."


def _shorten_tag(value: str, limit: int = MAX_GENERATED_TAG_LENGTH) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    shortened = compact[: limit + 1].rsplit(" ", 1)[0].rstrip(" -,:;")
    return shortened if 0 < len(shortened) <= limit else compact[:limit]


def _unique(values: Iterable[str | None]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        normalized = " ".join(value.split()).strip()
        key = normalized.casefold()
        if normalized and key not in seen:
            seen.add(key)
            result.append(normalized)
    return result
