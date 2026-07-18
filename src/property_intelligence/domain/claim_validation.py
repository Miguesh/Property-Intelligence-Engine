"""Deterministic factuality checks for generated listing copy.

Generated prose is an untrusted proposal, even when a provider returned it
through a strict structured-output schema.  This module checks concrete claim
classes that can be verified mechanically against the submitted listing.  It
does not use retrieved editorial guidance as evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .models import GeneratedContent, Listing
from .normalization import (
    AMENITY_ALIASES,
    PROPERTY_TYPE_ALIASES,
    canonical_property_type,
    contains_positive_phrase,
    normalize_for_match,
    words,
)

CLAIM_POLICY_VERSION = "generated-claims-2026.1"

_NUMBER_WORDS: dict[str, str] = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
    "thirteen": "13",
    "fourteen": "14",
    "fifteen": "15",
    "sixteen": "16",
    "seventeen": "17",
    "eighteen": "18",
    "nineteen": "19",
    "twenty": "20",
    "thirty": "30",
    "forty": "40",
    "fifty": "50",
    "sixty": "60",
    "seventy": "70",
    "eighty": "80",
    "ninety": "90",
    "hundred": "100",
    "thousand": "1000",
    "first": "1",
    "second": "2",
    "third": "3",
    "fourth": "4",
    "fifth": "5",
    "sixth": "6",
    "seventh": "7",
    "eighth": "8",
    "ninth": "9",
    "tenth": "10",
    "eleventh": "11",
    "twelfth": "12",
}

_NUMBER_WORD_PATTERN = "|".join(
    re.escape(value) for value in sorted(_NUMBER_WORDS, key=len, reverse=True)
)
_NUMBER_EXPRESSION = rf"(?:\d{{1,3}}(?:,\d{{3}})+(?:\.\d+)?|\d+(?:\.\d+)?|{_NUMBER_WORD_PATTERN})"

_DIGIT_NUMBER_RE = re.compile(
    r"(?<!\w)(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?:st|nd|rd|th)?(?!\w)",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
_URL_RE = re.compile(
    r"(?i)(?:\b(?:https?://|www\.)[^\s<]+|"
    r"(?<![@\w])[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?)*"
    r"\.(?:ai|app|biz|co|com|dev|info|io|net|org|rentals|travel|uk|us)"
    r"(?:/(?:[^\s<]*))?)"
)
_PHONE_CANDIDATE_RE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{5,}\d(?!\w)")


def _quantity_pattern(suffix: str, *, prefix: str = "") -> re.Pattern[str]:
    return re.compile(
        rf"\b{prefix}(?P<number>{_NUMBER_EXPRESSION})(?:st|nd|rd|th)?{suffix}\b",
        re.IGNORECASE,
    )


_QUANTITY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("bedrooms", _quantity_pattern(r"\s*[- ]?\s*(?:bedrooms?|brs?)")),
    ("bathrooms", _quantity_pattern(r"\s*[- ]?\s*(?:bathrooms?|baths?)")),
    (
        "beds",
        _quantity_pattern(r"\s*[- ]?\s*(?:(?:king|queen|twin|sofa|bunk)\s+)?beds?"),
    ),
    (
        "capacity",
        _quantity_pattern(r"\s*[- ]?\s*(?:guests?|people|persons?|occupants?)"),
    ),
    (
        "capacity",
        _quantity_pattern("", prefix=r"(?:sleeps?|accommodates?|hosts?)\s+"),
    ),
    (
        "proximity_minutes",
        _quantity_pattern(
            r"\s*[- ]?\s*(?:minutes?|mins?)\s*[- ]?\s*"
            r"(?:walk|drive|ride|away|from|to)"
        ),
    ),
    (
        "proximity_hours",
        _quantity_pattern(
            r"\s*[- ]?\s*(?:hours?|hrs?)\s*[- ]?\s*"
            r"(?:walk|drive|ride|away|from|to)"
        ),
    ),
    (
        "distance",
        _quantity_pattern(
            r"\s*[- ]?\s*(?:miles?|mi|kilometers?|kilometres?|km|meters?|metres?|"
            r"feet|ft|blocks?)"
        ),
    ),
    (
        "area",
        _quantity_pattern(r"\s*[- ]?\s*(?:square\s+(?:feet|foot|meters?|metres?)|sq\.?\s*ft|sqm)"),
    ),
    ("floor", _quantity_pattern(r"\s*[- ]?\s*(?:floors?|storeys?|stories?)")),
    ("rating", _quantity_pattern(r"\s*[- ]?\s*(?:stars?|rating)")),
    ("clock_time", _quantity_pattern(r"\s*(?:a\.?m\.?|p\.?m\.?)")),
)

_PROXIMITY_TARGET_RE = re.compile(
    rf"\b(?:near|close\s+to|steps?\s+from|by\s+the|"
    rf"walking\s+distance\s+(?:to|from|of)|"
    rf"(?:short|easy|quick)\s+(?:walk|drive|ride)\s+(?:to|from)|"
    rf"{_NUMBER_EXPRESSION}\s*[- ]?\s*(?:minutes?|mins?|hours?|hrs?)\s*[- ]?\s*"
    rf"(?:walk|drive|ride)?\s*(?:to|from))\s+(?:the\s+)?"
    rf"(?P<target>[^\n.!?;,]{{2,80}})",
    re.IGNORECASE,
)

_LANDMARK_ALIASES: dict[str, tuple[str, ...]] = {
    "airport": ("airport",),
    "beach": ("beach",),
    "bus_stop": ("bus stop",),
    "city_center": ("city center", "city centre"),
    "convention_center": ("convention center", "convention centre"),
    "downtown": ("downtown",),
    "hospital": ("hospital",),
    "metro": ("metro",),
    "park": ("park",),
    "public_transit": ("public transit", "public transport"),
    "ski_lift": ("ski lift", "ski lifts"),
    "stadium": ("stadium",),
    "subway": ("subway",),
    "train_station": ("train station", "railway station"),
    "university": ("university",),
}

# Generic view wording is deliberately included here even though scoring uses
# narrower view aliases.  "Views" is still a concrete property claim and must
# be grounded before generated copy can use it.
_FEATURE_ALIASES: dict[str, tuple[str, ...]] = {
    **AMENITY_ALIASES,
    "attribute_bright": ("bright", "sunlit", "sun-filled", "light-filled"),
    "attribute_luxury": ("luxury", "luxurious", "upscale"),
    "attribute_modern": ("modern", "contemporary"),
    "attribute_renovated": (
        "renovated",
        "newly renovated",
        "remodeled",
        "remodelled",
        "refurbished",
    ),
    "attribute_spacious": ("spacious", "roomy"),
    "balcony": ("balcony", "balconies"),
    "bathroom": ("bathroom", "bathrooms", "full bath", "half bath"),
    "bed": ("bed", "beds"),
    "bedroom": ("bedroom", "bedrooms"),
    "elevator": ("elevator", "building lift", "passenger lift"),
    "entire_place": ("entire place", "entire home", "entire apartment", "entire unit"),
    "full_kitchen": ("full kitchen",),
    "garage": ("garage",),
    "garden": ("garden",),
    "kitchenette": ("kitchenette",),
    "paid_parking": ("paid parking",),
    "patio": ("patio",),
    "private_hot_tub": ("private hot tub", "private jacuzzi"),
    "private_pool": ("private pool",),
    "shared_hot_tub": ("shared hot tub", "shared jacuzzi"),
    "shared_pool": ("shared pool",),
    "step_free": ("step-free", "step free"),
    "terrace": ("terrace",),
    "view": (*AMENITY_ALIASES["view"], "view", "views", "scenic view", "scenic views"),
    "view_city": (
        "city view",
        "city views",
    ),
    "view_lake": ("lake view", "lake views"),
    "view_mountain": ("mountain view", "mountain views"),
    "view_ocean": ("ocean view", "ocean views", "sea view", "sea views"),
    "view_water": ("water view", "water views"),
    "wheelchair_accessible": ("wheelchair accessible", "wheelchair-accessible"),
    "yard": ("yard",),
}

# Ambiguous conversational words (notably "home" and "room") are omitted so
# ordinary prose does not become a property-type claim.
_PROPERTY_TYPE_CLAIM_ALIASES: dict[str, tuple[str, ...]] = {
    canonical: tuple(alias for alias in aliases if alias not in {"home", "room"})
    for canonical, aliases in PROPERTY_TYPE_ALIASES.items()
}


@dataclass(frozen=True, slots=True)
class ClaimViolation:
    """One unsupported claim category found in generated content."""

    code: str
    claim: str


class UnsupportedGeneratedClaimError(ValueError):
    """Raised when generated copy contains facts absent from submitted data."""

    def __init__(self, violations: tuple[ClaimViolation, ...]) -> None:
        self.violations = violations
        super().__init__("generated content contains unsupported concrete claims")


class GeneratedContentClaimValidator:
    """Reject mechanically verifiable claims that lack listing evidence."""

    version = CLAIM_POLICY_VERSION

    def validate(self, listing: Listing, generated: GeneratedContent) -> None:
        """Raise when generated content adds an unsupported concrete claim."""

        violations = find_claim_violations(listing, generated)
        if violations:
            raise UnsupportedGeneratedClaimError(violations)


def find_claim_violations(
    listing: Listing,
    generated: GeneratedContent,
) -> tuple[ClaimViolation, ...]:
    """Return deterministic violations without disclosing provider details."""

    evidence = _listing_evidence_text(listing)
    proposal = _generated_text(generated)
    supported_features = _extract_features(evidence)
    claimed_features = _extract_features(proposal)
    supported_numbers = _extract_numbers(evidence)
    claimed_numbers = _extract_numbers(proposal)
    supported_quantities = _extract_typed_quantities(evidence)
    claimed_quantities = _extract_typed_quantities(proposal)
    supported_landmarks = _extract_landmarks(evidence)
    claimed_landmarks = _extract_landmarks(proposal)
    supported_proximity_targets = _extract_proximity_targets(evidence)
    claimed_proximity_targets = _extract_proximity_targets(proposal)
    supported_property_types = _supported_property_types(listing)
    claimed_property_types = _extract_property_types(proposal)

    violations = [
        ClaimViolation(code="unsupported_feature", claim=feature)
        for feature in sorted(claimed_features - supported_features)
    ]
    violations.extend(
        ClaimViolation(code="unsupported_number", claim=number)
        for number in sorted(claimed_numbers - supported_numbers)
    )
    violations.extend(
        ClaimViolation(code="unsupported_quantity", claim=f"{kind}:{number}")
        for kind, number in sorted(claimed_quantities - supported_quantities)
    )
    violations.extend(
        ClaimViolation(code="unsupported_landmark", claim=landmark)
        for landmark in sorted(claimed_landmarks - supported_landmarks)
    )
    violations.extend(
        ClaimViolation(code="unsupported_proximity", claim=target)
        for target in sorted(claimed_proximity_targets)
        if not any(
            _targets_equivalent(target, supported) for supported in supported_proximity_targets
        )
    )
    violations.extend(
        ClaimViolation(code="unsupported_property_type", claim=property_type)
        for property_type in sorted(claimed_property_types - supported_property_types)
    )
    if _EMAIL_RE.search(proposal):
        violations.append(ClaimViolation(code="contact_email", claim="email address"))
    if _URL_RE.search(proposal):
        violations.append(ClaimViolation(code="contact_url", claim="URL"))
    if any(_is_phone_like(match.group(0)) for match in _PHONE_CANDIDATE_RE.finditer(proposal)):
        violations.append(ClaimViolation(code="contact_phone", claim="phone number"))

    return tuple(violations)


def strip_contact_channels(value: str) -> str:
    """Remove contact channels before deterministic copy reuses submitted text."""

    cleaned = _EMAIL_RE.sub(" ", value)
    cleaned = _URL_RE.sub(" ", cleaned)
    cleaned = _PHONE_CANDIDATE_RE.sub(
        lambda match: " " if _is_phone_like(match.group(0)) else match.group(0),
        cleaned,
    )
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    return cleaned.strip(" \t\r\n,;:-")


def _listing_evidence_text(listing: Listing) -> str:
    location = listing.location
    values = (
        listing.title,
        listing.description,
        *listing.amenities,
        listing.property_type,
        location.city,
        location.country,
        location.region or "",
        location.neighborhood or "",
    )
    return "\n".join(values).replace("_", " ")


def _generated_text(generated: GeneratedContent) -> str:
    return "\n".join((*generated.titles, *generated.descriptions, *generated.tags)).replace(
        "_", " "
    )


def _extract_features(value: str) -> frozenset[str]:
    return frozenset(
        canonical
        for canonical, aliases in _FEATURE_ALIASES.items()
        if any(contains_positive_phrase(value, alias) for alias in aliases)
    )


def _supported_property_types(listing: Listing) -> frozenset[str]:
    canonical = canonical_property_type(listing.property_type)
    known = set(_extract_property_types(listing.property_type))
    if canonical in _PROPERTY_TYPE_CLAIM_ALIASES:
        known.add(canonical)
    compatible_types = {
        "studio": {"apartment"},
        "guest_suite": {"studio"},
    }
    known.update(compatible_types.get(canonical, set()))
    return frozenset(known)


def _extract_property_types(value: str) -> frozenset[str]:
    return frozenset(
        canonical
        for canonical, aliases in _PROPERTY_TYPE_CLAIM_ALIASES.items()
        if any(contains_positive_phrase(value, alias) for alias in aliases)
    )


def _extract_numbers(value: str) -> frozenset[str]:
    numbers = {
        canonical
        for match in _DIGIT_NUMBER_RE.finditer(value)
        if (canonical := _canonical_number(match.group(0))) is not None
    }
    numbers.update(
        _NUMBER_WORDS[token] for token in words(value.replace("-", " ")) if token in _NUMBER_WORDS
    )
    return frozenset(numbers)


def _extract_typed_quantities(value: str) -> frozenset[tuple[str, str]]:
    claims: set[tuple[str, str]] = set()
    for kind, pattern in _QUANTITY_PATTERNS:
        for match in pattern.finditer(value):
            number = _canonical_claim_number(match.group("number"))
            if number is not None:
                claims.add((kind, number))
    return frozenset(claims)


def _extract_landmarks(value: str) -> frozenset[str]:
    return frozenset(
        canonical
        for canonical, aliases in _LANDMARK_ALIASES.items()
        if any(contains_positive_phrase(value, alias) for alias in aliases)
    )


def _extract_proximity_targets(value: str) -> frozenset[str]:
    targets: set[str] = set()
    for match in _PROXIMITY_TARGET_RE.finditer(value):
        target = normalize_for_match(match.group("target"))
        for separator in (" with ", " while ", " where ", " offering ", " that "):
            target = target.split(separator, 1)[0]
        target = re.sub(r"^(?:a|an|the)\s+", "", target).strip()
        if target:
            targets.add(target)
    return frozenset(targets)


def _targets_equivalent(first: str, second: str) -> bool:
    if first == second:
        return True
    shorter, longer = sorted((first, second), key=len)
    return len(shorter) >= 4 and f" {shorter} " in f" {longer} "


def _canonical_claim_number(value: str) -> str | None:
    normalized = value.casefold().strip()
    if normalized in _NUMBER_WORDS:
        return _NUMBER_WORDS[normalized]
    return _canonical_number(normalized)


def _canonical_number(value: str) -> str | None:
    cleaned = re.sub(r"(?i)(?:st|nd|rd|th)$", "", value).replace(",", "")
    try:
        number = Decimal(cleaned)
    except InvalidOperation:
        return None
    if not number.is_finite():
        return None
    if number == number.to_integral():
        return str(int(number))
    return format(number.normalize(), "f")


def _is_phone_like(value: str) -> bool:
    return sum(character.isdigit() for character in value) >= 7


__all__ = [
    "CLAIM_POLICY_VERSION",
    "ClaimViolation",
    "GeneratedContentClaimValidator",
    "UnsupportedGeneratedClaimError",
    "find_claim_violations",
    "strip_contact_channels",
]
