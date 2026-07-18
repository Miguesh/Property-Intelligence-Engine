"""Deterministic text normalization for the listing-analysis domain.

The helpers in this module intentionally use only the Python standard library.
They trade linguistic sophistication for predictable behaviour that can be
tested, versioned, and explained to API consumers.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .models import Listing

_WORD_RE = re.compile(r"[^\W\d_]+(?:[-'][^\W\d_]+)*|\d+(?:\.\d+)?", re.UNICODE)
_HTML_RE = re.compile(r"<[^>]+>")
_NEGATIONS = frozenset(
    {
        "no",
        "not",
        "without",
        "unavailable",
        "neither",
        "cannot",
        "cant",
        "isnt",
        "isn",
        "arent",
        "aren",
        "doesnt",
        "doesn",
    }
)
_ABSENCE_STATES = frozenset({"absent", "broken", "closed", "removed", "unavailable"})
_ABSENCE_PREDICATES = frozenset(
    {
        "accessible",
        "allowed",
        "available",
        "included",
        "installed",
        "offered",
        "operational",
        "permitted",
        "present",
        "provided",
        "working",
    }
)

STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "our",
        "that",
        "the",
        "this",
        "to",
        "with",
        "your",
    }
)


PROPERTY_TYPE_ALIASES: dict[str, tuple[str, ...]] = {
    "apartment": ("apartment", "apt", "flat"),
    "condo": ("condo", "condominium"),
    "house": ("house", "home", "entire home"),
    "townhouse": ("townhouse", "townhome"),
    "villa": ("villa",),
    "cabin": ("cabin", "chalet"),
    "cottage": ("cottage",),
    "private_room": ("private room", "room"),
    "guest_suite": ("guest suite", "in-law suite", "studio suite"),
    "hotel_room": ("hotel room", "hotel"),
    "loft": ("loft",),
    "studio": ("studio", "studio apartment"),
}


AMENITY_ALIASES: dict[str, tuple[str, ...]] = {
    "wifi": ("wifi", "wi-fi", "wireless internet", "high speed internet"),
    "smoke_alarm": ("smoke alarm", "smoke detector"),
    "carbon_monoxide_alarm": (
        "carbon monoxide alarm",
        "carbon monoxide detector",
        "co alarm",
        "co detector",
    ),
    "fire_extinguisher": ("fire extinguisher",),
    "first_aid_kit": ("first aid kit", "first-aid kit"),
    "air_conditioning": ("air conditioning", "a/c", "ac", "central air"),
    "heating": ("heating", "heater", "central heating"),
    "fan": ("ceiling fan", "fan"),
    "self_check_in": (
        "self check-in",
        "self check in",
        "smart lock",
        "keypad",
        "lockbox",
    ),
    "kitchen": ("kitchen", "full kitchen", "kitchenette"),
    "refrigerator": ("refrigerator", "fridge", "mini fridge", "minibar"),
    "cooking_basics": ("cooking basics", "cookware", "pots and pans"),
    "washer": ("washer", "washing machine", "laundry machine"),
    "dryer": ("dryer", "tumble dryer"),
    "parking": (
        "parking",
        "free parking",
        "paid parking",
        "garage",
        "carport",
    ),
    "private_bathroom": ("private bathroom", "ensuite", "en-suite"),
    "private_entrance": ("private entrance", "separate entrance"),
    "coffee_maker": ("coffee maker", "coffee machine", "espresso machine"),
    "workspace": ("dedicated workspace", "workspace", "work desk", "desk"),
    "pool": ("swimming pool", "private pool", "shared pool", "pool"),
    "hot_tub": ("hot tub", "jacuzzi"),
    "view": (
        "ocean view",
        "sea view",
        "mountain view",
        "city view",
        "lake view",
        "water view",
    ),
    "waterfront": ("waterfront", "beachfront", "lakefront", "riverfront"),
    "fireplace": ("fireplace", "wood stove"),
    "outdoor_space": (
        "outdoor space",
        "patio",
        "terrace",
        "balcony",
        "yard",
        "garden",
    ),
    "bbq": ("bbq", "barbecue", "barbeque", "grill"),
    "pet_friendly": ("pet friendly", "pet-friendly", "pets allowed"),
    "ev_charger": ("ev charger", "electric vehicle charger"),
    "crib": ("crib", "travel cot", "pack and play", "pack 'n play"),
    "high_chair": ("high chair",),
    "ski_access": ("ski-in", "ski-out", "ski in", "ski out"),
}


AMENITY_CATEGORIES: dict[str, str] = {
    "wifi": "connectivity",
    "workspace": "workspace",
    "smoke_alarm": "safety",
    "carbon_monoxide_alarm": "safety",
    "fire_extinguisher": "safety",
    "first_aid_kit": "safety",
    "air_conditioning": "climate",
    "heating": "climate",
    "fan": "climate",
    "self_check_in": "arrival",
    "private_entrance": "arrival",
    "kitchen": "cooking",
    "refrigerator": "cooking",
    "cooking_basics": "cooking",
    "coffee_maker": "cooking",
    "washer": "laundry",
    "dryer": "laundry",
    "parking": "transport",
    "private_bathroom": "bathroom",
    "pool": "leisure",
    "hot_tub": "leisure",
    "view": "location_feature",
    "waterfront": "location_feature",
    "fireplace": "leisure",
    "outdoor_space": "outdoor",
    "bbq": "outdoor",
    "pet_friendly": "pet",
    "ev_charger": "transport",
    "crib": "family",
    "high_chair": "family",
    "ski_access": "location_feature",
}


def normalize_for_match(value: str) -> str:
    """Return accent-insensitive, punctuation-neutral text for exact matching."""

    value = unicodedata.normalize("NFKC", value).casefold()
    value = "".join(
        character
        for character in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(character)
    )
    value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def words(value: str) -> tuple[str, ...]:
    """Tokenize words and numbers without requiring an NLP dependency."""

    return tuple(match.group(0).casefold() for match in _WORD_RE.finditer(value))


def contains_phrase(value: str, phrase: str) -> bool:
    """Match a normalized phrase on token boundaries."""

    normalized_value = normalize_for_match(value)
    normalized_phrase = normalize_for_match(phrase)
    return bool(normalized_phrase) and f" {normalized_phrase} " in f" {normalized_value} "


def contains_positive_phrase(value: str, phrase: str) -> bool:
    """Return true for a non-negated phrase that is not explicitly off-property."""

    needle = normalize_for_match(phrase).split()
    if not needle:
        return False
    # Negation windows must not cross punctuation into a different claim.
    for clause in re.split(r"[.!?;,\r\n]+", value):
        haystack = normalize_for_match(clause).split()
        for start in range(0, len(haystack) - len(needle) + 1):
            if haystack[start : start + len(needle)] != needle:
                continue
            before = haystack[max(0, start - 3) : start]
            end = start + len(needle)
            after = haystack[end : end + 5]
            wider_before = haystack[max(0, start - 8) : start]
            if (
                not _has_preceding_negation(before)
                and not _has_postposed_negation(after)
                and not _has_off_property_context(wider_before, after)
            ):
                return True
    return False


def _has_preceding_negation(tokens: list[str]) -> bool:
    for index, word in enumerate(tokens):
        if word not in _NEGATIONS:
            continue
        # "not only a pool" asserts that the pool exists.
        if word == "not" and index + 1 < len(tokens) and tokens[index + 1] == "only":
            continue
        return True
    return False


def _has_postposed_negation(tokens: list[str]) -> bool:
    if any(token in _ABSENCE_STATES for token in tokens[:4]):
        return True
    joined = " ".join(tokens)
    if "under repair" in joined or "out of service" in joined:
        return True
    for index, word in enumerate(tokens[:4]):
        if word in _NEGATIONS and any(
            predicate in _ABSENCE_PREDICATES for predicate in tokens[index + 1 : index + 4]
        ):
            return True
    return False


def _has_off_property_context(before: list[str], after: list[str]) -> bool:
    before_text = " ".join(before)
    after_text = " ".join(after)
    if any(
        cue in before[-4:]
        for cue in (
            "community",
            "local",
            "municipal",
            "near",
            "nearby",
            "neighborhood",
            "public",
        )
    ):
        return True
    if any(
        cue in before_text
        for cue in (
            "across from",
            "across the street from",
            "close to",
            "drive to",
            "minutes from",
            "minutes to",
            "near the",
            "nearby",
            "next to",
            "ride to",
            "walk to",
            "walking distance to",
        )
    ):
        return True
    return any(
        cue in after_text
        for cue in (
            "is nearby",
            "off property",
            "off site",
            "minutes away",
            "a short walk away",
        )
    )


def canonical_property_type(value: str) -> str:
    """Map common property labels to a stable taxonomy."""

    normalized = normalize_for_match(value)
    for canonical, aliases in PROPERTY_TYPE_ALIASES.items():
        if normalized in {normalize_for_match(alias) for alias in aliases}:
            return canonical
    return normalized.replace(" ", "_") or "unknown"


def _canonicalize_amenity(value: str) -> set[str]:
    normalized = normalize_for_match(value)
    matches: set[str] = set()
    for canonical, aliases in AMENITY_ALIASES.items():
        if any(
            normalized == normalize_for_match(alias) or contains_phrase(normalized, alias)
            for alias in aliases
        ):
            matches.add(canonical)
    return matches


def extract_amenities(value: str) -> frozenset[str]:
    """Extract non-negated canonical amenity mentions from prose."""

    matches: set[str] = set()
    for canonical, aliases in AMENITY_ALIASES.items():
        if any(contains_positive_phrase(value, alias) for alias in aliases):
            matches.add(canonical)
    return frozenset(matches)


def split_sentences(value: str) -> tuple[str, ...]:
    """Split sentences conservatively, treating list lines as boundaries."""

    cleaned = _HTML_RE.sub(" ", value.strip())
    parts = re.split(r"(?<=[.!?])\s+|\n+", cleaned)
    return tuple(part.strip(" -\t") for part in parts if words(part))


def split_paragraphs(value: str) -> tuple[str, ...]:
    """Return paragraphs separated by blank lines."""

    cleaned = _HTML_RE.sub(" ", value.strip())
    parts = re.split(r"(?:\r?\n\s*){2,}", cleaned)
    return tuple(part.strip() for part in parts if words(part))


@dataclass(frozen=True, slots=True)
class NormalizedListing:
    """Precomputed evidence shared by deterministic analyzers."""

    listing: Listing
    title_words: tuple[str, ...]
    description_words: tuple[str, ...]
    sentences: tuple[str, ...]
    paragraphs: tuple[str, ...]
    property_type: str
    property_type_mentioned: bool
    location_mentioned: bool
    structured_amenities: frozenset[str]
    prose_amenities: frozenset[str]

    @property
    def amenities(self) -> frozenset[str]:
        return self.structured_amenities | self.prose_amenities


def normalize_listing(listing: Listing) -> NormalizedListing:
    """Build a normalized, immutable representation of a listing."""

    property_type = canonical_property_type(listing.property_type)
    property_aliases = PROPERTY_TYPE_ALIASES.get(property_type, (listing.property_type,))
    combined_text = f"{listing.title}\n{listing.description}"
    property_mentioned = any(contains_phrase(combined_text, alias) for alias in property_aliases)

    location_phrases = [listing.location.neighborhood, listing.location.city]
    if listing.location.region and len(normalize_for_match(listing.location.region)) > 3:
        location_phrases.append(listing.location.region)
    location_mentioned = any(
        phrase and contains_phrase(combined_text, phrase) for phrase in location_phrases
    )

    structured: set[str] = set()
    for item in listing.amenities:
        structured.update(_canonicalize_amenity(item))

    return NormalizedListing(
        listing=listing,
        title_words=words(listing.title),
        description_words=words(listing.description),
        sentences=split_sentences(listing.description),
        paragraphs=split_paragraphs(listing.description),
        property_type=property_type,
        property_type_mentioned=property_mentioned,
        location_mentioned=location_mentioned,
        structured_amenities=frozenset(structured),
        prose_amenities=extract_amenities(listing.description),
    )
