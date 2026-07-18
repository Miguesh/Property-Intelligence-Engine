"""Explainable, provider-independent short-term-rental listing analysis."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from statistics import mean

from .models import (
    AmenitySuggestion,
    DeterministicAnalysis,
    Improvement,
    Listing,
    Priority,
    Score,
    ScoreComponent,
)
from .normalization import (
    AMENITY_CATEGORIES,
    PROPERTY_TYPE_ALIASES,
    STOPWORDS,
    NormalizedListing,
    contains_phrase,
    extract_amenities,
    normalize_for_match,
    normalize_listing,
    words,
)

METHODOLOGY = "deterministic-2026.1"

_DIFFERENTIATORS = frozenset(
    {
        "bbq",
        "ev_charger",
        "fireplace",
        "hot_tub",
        "outdoor_space",
        "parking",
        "pet_friendly",
        "pool",
        "ski_access",
        "view",
        "waterfront",
        "workspace",
    }
)
_SAFETY_AMENITIES = frozenset(
    {"smoke_alarm", "carbon_monoxide_alarm", "fire_extinguisher", "first_aid_kit"}
)
_CAPS_ALLOWLIST = frozenset({"AC", "BBQ", "EV", "TV", "USA", "UK"})

_AUDIENCE_PHRASES: dict[str, tuple[str, ...]] = {
    "family": ("family", "families", "children", "kids"),
    "couples": ("couple", "couples", "romantic getaway"),
    "groups": ("group", "groups", "friends"),
    "business": ("business travel", "business traveler", "work trip"),
    "remote_work": ("remote work", "work from home", "digital nomad"),
    "extended_stay": ("extended stay", "long stay", "monthly stay"),
}

_PROXIMITY_RE = re.compile(
    r"\b(?:\d+(?:\.\d+)?\s*(?:minutes?|mins?|miles?|kilometers?|kilometres?|km)"
    r"|walking distance|steps from|nearby|close to|downtown|beach|airport|transit|"
    r"metro|subway)\b",
    re.IGNORECASE,
)
_ARRIVAL_RE = re.compile(
    r"\b(?:check[ -]?in|self check[ -]?in|smart lock|keypad|lockbox|key code|"
    r"private entrance|guest access|door code)\b",
    re.IGNORECASE,
)
_RULES_RE = re.compile(
    r"\b(?:house rules?|quiet hours?|no smoking|smoking is not|no parties|"
    r"pets? (?:allowed|welcome|not allowed)|check[ -]?out|minimum age)\b",
    re.IGNORECASE,
)
_TRANSPORT_RE = re.compile(
    r"\b(?:parking|garage|carport|bus|metro|subway|station|transit|walk(?:ing)?|"
    r"drive|rideshare|taxi)\b",
    re.IGNORECASE,
)
_EXPECTATIONS_RE = re.compile(
    r"\b(?:stairs?|shared|noise|noisy|construction|accessible|accessibility|"
    r"elevator|no parking|limited parking|steep|camera|doorbell camera|"
    r"may hear|please note)\b",
    re.IGNORECASE,
)
_OFF_PLATFORM_RE = re.compile(
    r"(?:\b(?:whatsapp|venmo|cashapp|paypal|wire transfer)\b|"
    r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|"
    r"(?:\+?\d[\d ()-]{8,}\d))",
    re.IGNORECASE,
)


def _round_score(value: float) -> float:
    return float(
        Decimal(str(max(0.0, min(100.0, value)))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    )


def _make_score(components: Iterable[ScoreComponent], *, value_cap: float | None = None) -> Score:
    component_tuple = tuple(components)
    value = sum(item.score * item.weight for item in component_tuple)
    if value_cap is not None:
        value = min(value, value_cap)
    return Score(
        value=_round_score(value),
        components=component_tuple,
        methodology=METHODOLOGY,
    )


def _component(name: str, score: float, weight: float, rationale: str) -> ScoreComponent:
    return ScoreComponent(
        name=name,
        score=_round_score(score),
        weight=weight,
        rationale=rationale,
    )


def _description_length_score(word_count: int) -> float:
    if word_count == 0:
        return 0
    if word_count < 40:
        return 20
    if word_count < 70:
        return 50
    if word_count < 100:
        return 75
    if word_count <= 350:
        return 100
    if word_count <= 500:
        return 85
    if word_count <= 700:
        return 60
    return 40


def _title_length_score(character_count: int) -> float:
    if character_count == 0:
        return 0
    if 30 <= character_count <= 60:
        return 100
    if 20 <= character_count <= 70:
        return 75
    if 10 <= character_count <= 80:
        return 40
    return 10


def _phrase_present(value: str, phrases: Iterable[str]) -> bool:
    return any(contains_phrase(value, phrase) for phrase in phrases)


def _property_type_present(normalized: NormalizedListing, value: str) -> bool:
    aliases = PROPERTY_TYPE_ALIASES.get(
        normalized.property_type, (normalized.listing.property_type,)
    )
    return _phrase_present(value, aliases)


def _location_present(normalized: NormalizedListing, value: str) -> bool:
    location = normalized.listing.location
    phrases = [location.neighborhood, location.city]
    if location.region and len(normalize_for_match(location.region)) > 3:
        phrases.append(location.region)
    return any(phrase and contains_phrase(value, phrase) for phrase in phrases)


def _audience_signals(value: str) -> frozenset[str]:
    return frozenset(
        audience
        for audience, phrases in _AUDIENCE_PHRASES.items()
        if _phrase_present(value, phrases)
    )


def _configuration_facts(value: str) -> frozenset[str]:
    normalized = normalize_for_match(value)
    patterns = {
        "capacity": r"\b(?:sleeps|accommodates)\s+\d+\b|\b\d+\s+guests?\b",
        "bedrooms": r"\b\d+\s+(?:bedrooms?|br)\b",
        "beds": r"\b\d+\s+(?:beds?|king beds?|queen beds?|twin beds?)\b",
        "bathrooms": r"\b\d+(?:\.\d+)?\s+(?:bathrooms?|baths?)\b",
    }
    return frozenset(name for name, pattern in patterns.items() if re.search(pattern, normalized))


_CONFIGURATION_REQUIREMENTS: tuple[tuple[frozenset[str], str], ...] = (
    (frozenset({"capacity"}), "verified guest capacity"),
    (frozenset({"bedrooms", "beds"}), "a verified bedroom or bed layout"),
    (frozenset({"bathrooms"}), "a verified bathroom count"),
)


def _missing_configuration_details(facts: frozenset[str]) -> tuple[str, ...]:
    return tuple(
        label
        for alternatives, label in _CONFIGURATION_REQUIREMENTS
        if facts.isdisjoint(alternatives)
    )


def _format_detail_list(details: tuple[str, ...]) -> str:
    if len(details) < 2:
        return "".join(details)
    if len(details) == 2:
        return " and ".join(details)
    return f"{', '.join(details[:-1])}, and {details[-1]}"


def _has_bullets(value: str) -> bool:
    return bool(re.search(r"(?m)^\s*(?:[-*•]|\d+[.)])\s+", value))


def _has_heading(value: str) -> bool:
    return bool(
        re.search(
            r"(?im)^\s*(?:#{1,6}\s+|(?:the space|amenities|location|guest access|"
            r"house rules|sleeping arrangements|about this space)\s*:?\s*$)",
            value,
        )
    )


def _mechanics_score(value: str, *, sentence_check: bool = True) -> float:
    score = 100.0
    alpha_words = re.findall(r"\b[A-Za-z][A-Za-z'-]*\b", value)
    caps = [
        token
        for token in alpha_words
        if len(token) > 1 and token.isupper() and token not in _CAPS_ALLOWLIST
    ]
    if alpha_words and len(caps) / len(alpha_words) > 0.10:
        score -= 25
    if re.search(r"[!?]{3,}", value):
        score -= 20
    if len(re.findall(r"(?<!\n) {2,}", value)) >= 3:
        score -= 15
    if sentence_check:
        non_bullet_lines = [
            line.strip()
            for line in value.splitlines()
            if line.strip() and not re.match(r"^(?:[-*•]|\d+[.)])\s+", line.strip())
        ]
        if len(non_bullet_lines) >= 2:
            terminated = sum(line.endswith((".", "!", "?", ":")) for line in non_bullet_lines)
            if terminated / len(non_bullet_lines) < 0.80:
                score -= 20
    return max(0.0, score)


def _count_syllables(token: str) -> int:
    token = re.sub(r"[^a-z]", "", normalize_for_match(token))
    if not token:
        return 0
    groups = len(re.findall(r"[aeiouy]+", token))
    if token.endswith("e") and not re.search(r"[^aeiou]le$", token) and groups > 1:
        groups -= 1
    return max(1, groups)


def _readability(normalized: NormalizedListing) -> Score:
    alphabetic_words = tuple(
        token for token in normalized.description_words if any(char.isalpha() for char in token)
    )
    word_count = len(alphabetic_words)
    sentence_count = max(1, len(normalized.sentences))
    syllables = sum(_count_syllables(token) for token in alphabetic_words)
    if word_count:
        flesch = 206.835 - 1.015 * (word_count / sentence_count) - 84.6 * (syllables / word_count)
    else:
        flesch = 0.0
    flesch = max(0.0, min(100.0, flesch))

    sentence_lengths = [len(words(sentence)) for sentence in normalized.sentences]
    average_length = mean(sentence_lengths) if sentence_lengths else 0.0
    if 10 <= average_length <= 20:
        sentence_score = 100.0
    elif 8 <= average_length < 10 or 20 < average_length <= 24:
        sentence_score = 85.0
    elif 5 <= average_length < 8 or 24 < average_length <= 30:
        sentence_score = 65.0
    elif 0 < average_length < 5 or 30 < average_length <= 35:
        sentence_score = 45.0
    else:
        sentence_score = 20.0 if average_length else 0.0
    if (
        sentence_lengths
        and sum(length > 30 for length in sentence_lengths) / len(sentence_lengths) > 0.25
    ):
        sentence_score = max(0.0, sentence_score - 20)

    paragraph_lengths = [len(words(paragraph)) for paragraph in normalized.paragraphs]
    if 2 <= len(paragraph_lengths) <= 6 and max(paragraph_lengths, default=0) <= 100:
        paragraph_score = 100.0
    elif 2 <= len(paragraph_lengths) <= 10:
        paragraph_score = 80.0
    elif len(paragraph_lengths) == 1 and paragraph_lengths[0] <= 100:
        paragraph_score = 60.0
    elif paragraph_lengths:
        paragraph_score = 30.0
    else:
        paragraph_score = 0.0

    skimmability = 40.0 if word_count else 0.0
    skimmability += 20 if len(normalized.paragraphs) > 1 else 0
    skimmability += 20 if _has_bullets(normalized.listing.description) else 0
    skimmability += 20 if _has_heading(normalized.listing.description) else 0
    mechanics = _mechanics_score(normalized.listing.description)

    components = (
        _component(
            "flesch_reading_ease",
            flesch,
            0.50,
            f"English Flesch Reading Ease is {flesch:.1f}.",
        ),
        _component(
            "sentence_length",
            sentence_score,
            0.20,
            f"Average sentence length is {average_length:.1f} words.",
        ),
        _component(
            "paragraph_quality",
            paragraph_score,
            0.15,
            f"The description has {len(normalized.paragraphs)} paragraph(s).",
        ),
        _component(
            "skimmability",
            skimmability,
            0.10,
            "Rewards useful paragraphs, bullets, and descriptive headings.",
        ),
        _component(
            "mechanics",
            mechanics,
            0.05,
            "Checks capitalization, repeated punctuation, spacing, and sentence endings.",
        ),
    )
    cap = None
    if word_count < 20:
        cap = 25
    elif word_count < 40:
        cap = 50
    elif word_count < 60:
        cap = 70
    return _make_score(components, value_cap=cap)


def _title_utility(normalized: NormalizedListing) -> float:
    title = normalized.listing.title
    title_amenities = extract_amenities(title)
    points = 0.25 * _title_length_score(len(title))
    points += 20 if _property_type_present(normalized, title) else 0
    points += 15 if _location_present(normalized, title) else 0
    points += 25 if title_amenities & _DIFFERENTIATORS else 0
    points += 0.15 * _mechanics_score(title, sentence_check=False)
    return max(0.0, min(100.0, points))


def _is_keyword_stuffed(normalized: NormalizedListing) -> bool:
    tokens = [
        token
        for token in normalized.description_words
        if token not in STOPWORDS and len(token) > 2 and not token.isdigit()
    ]
    if len(tokens) < 40:
        return False
    threshold = max(5, math.ceil(len(tokens) * 0.06))
    frequencies = {token: tokens.count(token) for token in set(tokens)}
    if any(count >= threshold for count in frequencies.values()):
        return True
    bigrams = list(zip(tokens, tokens[1:], strict=False))
    if not bigrams:
        return False
    bigram_threshold = max(4, math.ceil(len(bigrams) * 0.03))
    return any(bigrams.count(item) >= bigram_threshold for item in set(bigrams))


def _lexical_variety(normalized: NormalizedListing) -> float:
    significant = [
        token
        for token in normalized.description_words
        if token not in STOPWORDS and len(token) > 2 and not token.isdigit()
    ]
    if not significant:
        return 0.0
    ratio = len(set(significant)) / len(significant)
    if ratio >= 0.45:
        return 100.0
    if ratio >= 0.30:
        return 50.0
    return 0.0


def _seo(normalized: NormalizedListing) -> Score:
    listing = normalized.listing
    title_features = extract_amenities(listing.title)
    description_features = normalized.prose_amenities
    has_proximity = bool(_PROXIMITY_RE.search(listing.description))
    audiences = _audience_signals(listing.description)

    title_points = 0.06 * _title_length_score(len(listing.title))
    title_points += 6 if _property_type_present(normalized, listing.title) else 0
    title_points += 5 if _location_present(normalized, listing.title) else 0
    title_points += 8 if title_features & _DIFFERENTIATORS else 0
    title_points += 0.05 * _mechanics_score(listing.title, sentence_check=False)

    description_points = 0.08 * _description_length_score(len(normalized.description_words))
    description_points += 5 if _property_type_present(normalized, listing.description) else 0
    description_points += 6 if _location_present(normalized, listing.description) else 0
    description_points += 8 * min(len(description_features) / 3, 1)
    description_points += 5 if has_proximity else 0
    description_points += 3 if audiences else 0
    opening = listing.description[:200]
    opening_has_summary = _property_type_present(normalized, opening) and (
        _location_present(normalized, opening)
        or bool(extract_amenities(opening) & _DIFFERENTIATORS)
    )
    description_points += 5 if opening_has_summary else 0

    categories = {AMENITY_CATEGORIES[item] for item in description_features}
    search_points = 8 * min(len(categories) / 4, 1)
    search_points += 4 if has_proximity else 0
    title_elements = sum(
        (
            _property_type_present(normalized, listing.title),
            _location_present(normalized, listing.title),
            bool(title_features & _DIFFERENTIATORS),
        )
    )
    search_points += 4 if title_elements == 3 else 2 if title_elements == 2 else 0
    search_points += 0.04 * _lexical_variety(normalized)

    stuffed = _is_keyword_stuffed(normalized)
    normalized_title = normalize_for_match(listing.title)
    repeated_title = (
        bool(normalized_title)
        and normalize_for_match(listing.description).count(normalized_title) >= 3
    )
    spam = _mechanics_score(f"{listing.title}\n{listing.description}", sentence_check=False) < 80
    structure_points = 3 if 2 <= len(normalized.paragraphs) <= 6 else 0
    structure_points += (
        2 if _has_bullets(listing.description) or _has_heading(listing.description) else 0
    )
    structure_points += 3 if not stuffed else 0
    structure_points += 2 if not spam and not repeated_title else 0

    return _make_score(
        (
            _component(
                "title_relevance",
                title_points / 30 * 100,
                0.30,
                "Measures title length, property/location relevance, "
                "differentiators, and mechanics.",
            ),
            _component(
                "description_relevance",
                description_points / 40 * 100,
                0.40,
                "Measures useful search concepts in the description and opening summary.",
            ),
            _component(
                "search_breadth",
                search_points / 20 * 100,
                0.20,
                "Measures distinct amenity categories, local context, and lexical variety.",
            ),
            _component(
                "structure_and_hygiene",
                structure_points / 10 * 100,
                0.10,
                "Rewards scannable structure and absence of keyword or punctuation spam.",
            ),
        )
    )


_UNIVERSAL_REQUIREMENTS: tuple[tuple[frozenset[str], int], ...] = (
    (frozenset({"wifi"}), 3),
    (frozenset({"smoke_alarm"}), 4),
    (frozenset({"carbon_monoxide_alarm"}), 3),
    (frozenset({"fire_extinguisher"}), 3),
    (frozenset({"first_aid_kit"}), 2),
    (frozenset({"air_conditioning", "heating", "fan"}), 2),
    (frozenset({"self_check_in", "private_entrance"}), 2),
)

_PROFILE_REQUIREMENTS: dict[str, tuple[tuple[frozenset[str], int], ...]] = {
    "apartment": (
        (frozenset({"kitchen"}), 4),
        (frozenset({"refrigerator"}), 2),
        (frozenset({"cooking_basics"}), 2),
        (frozenset({"washer", "dryer"}), 2),
    ),
    "condo": (
        (frozenset({"kitchen"}), 4),
        (frozenset({"refrigerator"}), 2),
        (frozenset({"cooking_basics"}), 2),
        (frozenset({"washer", "dryer"}), 2),
    ),
    "house": (
        (frozenset({"kitchen"}), 4),
        (frozenset({"refrigerator"}), 2),
        (frozenset({"cooking_basics"}), 2),
        (frozenset({"washer", "dryer"}), 2),
    ),
    "townhouse": (
        (frozenset({"kitchen"}), 4),
        (frozenset({"refrigerator"}), 2),
        (frozenset({"cooking_basics"}), 2),
        (frozenset({"washer", "dryer"}), 2),
    ),
    "studio": (
        (frozenset({"kitchen"}), 4),
        (frozenset({"refrigerator"}), 2),
        (frozenset({"cooking_basics"}), 2),
        (frozenset({"washer", "dryer"}), 2),
    ),
    "loft": (
        (frozenset({"kitchen"}), 4),
        (frozenset({"refrigerator"}), 2),
        (frozenset({"cooking_basics"}), 2),
        (frozenset({"washer", "dryer"}), 2),
    ),
    "villa": (
        (frozenset({"kitchen"}), 3),
        (frozenset({"washer", "dryer"}), 2),
        (frozenset({"parking"}), 2),
        (frozenset({"outdoor_space"}), 2),
    ),
    "cabin": (
        (frozenset({"kitchen"}), 3),
        (frozenset({"heating"}), 3),
        (frozenset({"parking"}), 2),
        (frozenset({"outdoor_space"}), 2),
    ),
    "cottage": (
        (frozenset({"kitchen"}), 3),
        (frozenset({"heating"}), 3),
        (frozenset({"parking"}), 2),
        (frozenset({"outdoor_space"}), 2),
    ),
    "private_room": (
        (frozenset({"private_bathroom"}), 3),
        (frozenset({"private_entrance"}), 2),
        (frozenset({"refrigerator"}), 2),
        (frozenset({"coffee_maker"}), 1),
    ),
    "guest_suite": (
        (frozenset({"private_bathroom"}), 3),
        (frozenset({"private_entrance"}), 2),
        (frozenset({"refrigerator"}), 2),
        (frozenset({"coffee_maker"}), 1),
    ),
    "hotel_room": (
        (frozenset({"private_bathroom"}), 3),
        (frozenset({"refrigerator"}), 2),
        (frozenset({"coffee_maker"}), 1),
    ),
}


def _weighted_coverage(
    present: frozenset[str], requirements: tuple[tuple[frozenset[str], int], ...]
) -> float:
    maximum = sum(weight for _, weight in requirements)
    if not maximum:
        return 100.0
    earned = sum(weight for alternatives, weight in requirements if present & alternatives)
    return earned / maximum * 100


@dataclass(frozen=True, slots=True)
class _Evidence:
    audiences: frozenset[str]
    facts: frozenset[str]
    proximity: bool
    arrival: bool
    policies: bool
    transport: bool
    expectations: bool
    differentiators: frozenset[str]
    universal_coverage: float
    title_utility: float
    stuffed: bool


def _quality(normalized: NormalizedListing, readability: Score) -> tuple[Score, _Evidence]:
    listing = normalized.listing
    word_count = len(normalized.description_words)
    audiences = _audience_signals(listing.description)
    facts = _configuration_facts(listing.description)
    proximity = bool(_PROXIMITY_RE.search(listing.description))
    arrival = bool(_ARRIVAL_RE.search(listing.description))
    policies = bool(_RULES_RE.search(listing.description))
    transport = bool(_TRANSPORT_RE.search(listing.description))
    expectations = bool(_EXPECTATIONS_RE.search(listing.description))
    differentiators = normalized.amenities & _DIFFERENTIATORS

    content = 0.20 * _description_length_score(word_count)
    content += 5  # Listing guarantees non-empty property-type metadata.
    content += 5 if normalized.property_type_mentioned else 0
    content += 5  # Location is a validated domain value.
    content += 5 if normalized.location_mentioned else 0
    content += 5 if proximity else 0
    content += 5 * len(facts)
    content += 5 * min(len(audiences), 2)
    content += 5 if arrival else 0
    content += 5 if policies else 0
    content += 5 * min(len(differentiators), 3)

    universal_coverage = _weighted_coverage(normalized.amenities, _UNIVERSAL_REQUIREMENTS)
    profile = _PROFILE_REQUIREMENTS.get(normalized.property_type, ())
    profile_coverage = _weighted_coverage(normalized.amenities, profile)
    amenity_coverage = (
        0.70 * universal_coverage + 0.30 * profile_coverage if profile else universal_coverage
    )

    prose_categories = {AMENITY_CATEGORIES[item] for item in normalized.prose_amenities}
    value_proposition = 30 * min(len(differentiators) / 3, 1)
    value_proposition += 25 * min(len(facts) / 3, 1)
    value_proposition += 20 * min(len(prose_categories) / 4, 1)
    value_proposition += 10 * min(len(audiences) / 2, 1)
    value_proposition += 15 if proximity else 0

    guest_clarity = 25 * min(len(facts) / 2, 1)
    guest_clarity += 20 if arrival else 0
    guest_clarity += 15 if transport else 0
    guest_clarity += 20 if policies else 0
    guest_clarity += 20 if expectations else 0

    safety_ratio = len(normalized.amenities & _SAFETY_AMENITIES) / len(_SAFETY_AMENITIES)
    trust = 35 * safety_ratio
    trust += 25 if expectations else 0
    trust += 0.20 * _mechanics_score(
        f"{listing.title}\n{listing.description}", sentence_check=False
    )
    trust += 0 if _OFF_PLATFORM_RE.search(listing.description) else 20

    title_utility = _title_utility(normalized)
    presentation = 0.60 * readability.value + 0.40 * title_utility

    score = _make_score(
        (
            _component(
                "content_completeness",
                content,
                0.30,
                "Checks substantive copy, property/location context, configuration, "
                "audience, and policies.",
            ),
            _component(
                "amenity_coverage",
                amenity_coverage,
                0.20,
                "Uses weighted universal and property-type amenity groups; "
                "alternatives satisfy a group once.",
            ),
            _component(
                "value_proposition",
                value_proposition,
                0.20,
                "Rewards concrete facts, relevant features, guest benefits, and "
                "useful local context.",
            ),
            _component(
                "guest_clarity",
                guest_clarity,
                0.15,
                "Checks layout, arrival, transport, rules, and expectation-setting information.",
            ),
            _component(
                "trust_and_hygiene",
                trust,
                0.10,
                "Checks listed safety items, professional mechanics, disclosures, "
                "and off-platform signals.",
            ),
            _component(
                "presentation",
                presentation,
                0.05,
                "Combines readability (60%) and title utility (40%).",
            ),
        )
    )
    evidence = _Evidence(
        audiences=audiences,
        facts=facts,
        proximity=proximity,
        arrival=arrival,
        policies=policies,
        transport=transport,
        expectations=expectations,
        differentiators=differentiators,
        universal_coverage=universal_coverage,
        title_utility=title_utility,
        stuffed=_is_keyword_stuffed(normalized),
    )
    return score, evidence


@dataclass(frozen=True, slots=True)
class _AmenityRule:
    canonical_id: str
    name: str
    priority: Priority
    reason: str
    confidence: float
    property_types: frozenset[str] = frozenset()
    audiences: frozenset[str] = frozenset()


_AMENITY_SUGGESTION_RULES = (
    _AmenityRule(
        "wifi",
        "Wi-Fi",
        Priority.HIGH,
        "Reliable connectivity is a core search and booking consideration.",
        0.95,
    ),
    _AmenityRule(
        "smoke_alarm",
        "Smoke alarm",
        Priority.HIGH,
        "Guests expect clearly documented smoke-safety equipment.",
        0.98,
    ),
    _AmenityRule(
        "carbon_monoxide_alarm",
        "Carbon monoxide alarm",
        Priority.HIGH,
        "This safety item should be verified and disclosed where applicable.",
        0.93,
    ),
    _AmenityRule(
        "fire_extinguisher",
        "Fire extinguisher",
        Priority.HIGH,
        "Clearly documented fire-safety equipment improves guest confidence.",
        0.96,
    ),
    _AmenityRule(
        "first_aid_kit",
        "First-aid kit",
        Priority.MEDIUM,
        "A listed first-aid kit provides useful safety reassurance.",
        0.90,
    ),
    _AmenityRule(
        "self_check_in",
        "Self check-in",
        Priority.MEDIUM,
        "A clear independent arrival option reduces guest uncertainty.",
        0.82,
    ),
    _AmenityRule(
        "kitchen",
        "Kitchen or kitchenette",
        Priority.MEDIUM,
        "Cooking facilities are especially relevant for self-contained stays.",
        0.88,
        frozenset(
            {
                "apartment",
                "condo",
                "house",
                "townhouse",
                "studio",
                "loft",
                "villa",
                "cabin",
                "cottage",
            }
        ),
    ),
    _AmenityRule(
        "washer",
        "Laundry facilities",
        Priority.MEDIUM,
        "Laundry details help guests evaluate longer and family stays.",
        0.78,
        frozenset({"apartment", "condo", "house", "townhouse", "studio", "loft", "villa"}),
    ),
    _AmenityRule(
        "private_bathroom",
        "Private bathroom",
        Priority.MEDIUM,
        "Bathroom privacy is an important decision point for room and suite listings.",
        0.86,
        frozenset({"private_room", "guest_suite", "hotel_room"}),
    ),
    _AmenityRule(
        "workspace",
        "Dedicated workspace",
        Priority.MEDIUM,
        "A verified workspace supports business and remote-work positioning.",
        0.84,
        audiences=frozenset({"business", "remote_work"}),
    ),
    _AmenityRule(
        "crib",
        "Crib or travel cot",
        Priority.LOW,
        "Family-focused copy makes infant sleeping equipment relevant.",
        0.78,
        audiences=frozenset({"family"}),
    ),
    _AmenityRule(
        "high_chair",
        "High chair",
        Priority.LOW,
        "Family-focused copy makes child dining equipment relevant.",
        0.74,
        audiences=frozenset({"family"}),
    ),
)


def _missing_amenities(
    normalized: NormalizedListing, evidence: _Evidence
) -> tuple[AmenitySuggestion, ...]:
    audiences = evidence.audiences
    suggestions: list[AmenitySuggestion] = []
    for rule in _AMENITY_SUGGESTION_RULES:
        if rule.canonical_id in normalized.amenities:
            continue
        if rule.property_types and normalized.property_type not in rule.property_types:
            continue
        if rule.audiences and not audiences.intersection(rule.audiences):
            continue
        safety_caveat = (
            " Verify whether it is installed and list it; if absent, consider installing it."
            if rule.canonical_id in _SAFETY_AMENITIES
            else " Verify that it is available before adding it to the listing."
        )
        suggestions.append(
            AmenitySuggestion(
                name=rule.name,
                priority=rule.priority,
                reason=f"Not listed: {rule.reason}{safety_caveat}",
                confidence=rule.confidence,
            )
        )
    priority_order = {Priority.HIGH: 0, Priority.MEDIUM: 1, Priority.LOW: 2}
    return tuple(
        sorted(
            suggestions,
            key=lambda item: (priority_order[item.priority], -item.confidence, item.name),
        )[:8]
    )


def _unique_messages(messages: Iterable[str], limit: int = 5) -> tuple[str, ...]:
    return tuple(dict.fromkeys(messages))[:limit]


def _strengths(
    normalized: NormalizedListing,
    quality: Score,
    seo: Score,
    readability: Score,
    evidence: _Evidence,
) -> tuple[str, ...]:
    messages: list[str] = []
    facts = evidence.facts
    missing_configuration = _missing_configuration_details(facts)
    differentiators = evidence.differentiators
    if 100 <= len(normalized.description_words) <= 350:
        messages.append("The description is substantive without being excessively long.")
    if normalized.property_type_mentioned and normalized.location_mentioned:
        messages.append("The copy clearly identifies both the property type and location.")
    if not missing_configuration:
        messages.append(
            "Concrete details about guest capacity, the sleeping layout, and the "
            "bathroom count support booking decisions."
        )
    if len(differentiators) >= 2:
        readable = ", ".join(sorted(item.replace("_", " ") for item in differentiators)[:3])
        messages.append(f"Distinctive features are clearly listed: {readable}.")
    if evidence.universal_coverage >= 75:
        messages.append(
            "The submitted amenities cover most core connectivity and safety expectations."
        )
    if readability.value >= 75:
        messages.append("The description is easy to scan and read.")
    if seo.value >= 75:
        messages.append("The title and description provide strong content-discoverability signals.")
    if quality.value >= 80 and not messages:
        messages.append("The listing provides a strong, balanced set of guest-facing details.")
    return _unique_messages(messages)


def _weaknesses(
    normalized: NormalizedListing,
    readability: Score,
    evidence: _Evidence,
) -> tuple[str, ...]:
    messages: list[str] = []
    word_count = len(normalized.description_words)
    facts = evidence.facts
    missing_configuration = _missing_configuration_details(facts)
    differentiators = evidence.differentiators
    safety_missing = _SAFETY_AMENITIES - normalized.amenities
    if safety_missing:
        messages.append("One or more core safety amenities are not listed and should be verified.")
    if word_count < 70:
        messages.append("The description is too short to answer common guest questions.")
    elif word_count > 500:
        messages.append("The description is long enough to obscure its strongest selling points.")
    if not normalized.property_type_mentioned:
        messages.append("The copy does not explicitly identify the property type.")
    if not normalized.location_mentioned:
        messages.append(
            "The copy does not mention the city or neighborhood supplied with the listing."
        )
    if missing_configuration:
        messages.append(
            f"The description does not state {_format_detail_list(missing_configuration)}."
        )
    if not differentiators:
        messages.append("No distinctive, verifiable property feature is emphasized.")
    if readability.value < 60:
        messages.append("The description needs clearer sentences or more scannable formatting.")
    if evidence.stuffed:
        messages.append("Repeated words or phrases resemble keyword stuffing.")
    return _unique_messages(messages)


def _improvements(
    normalized: NormalizedListing,
    readability: Score,
    evidence: _Evidence,
) -> tuple[Improvement, ...]:
    items: list[Improvement] = []
    word_count = len(normalized.description_words)
    facts = evidence.facts
    missing_configuration = _missing_configuration_details(facts)
    safety_missing = _SAFETY_AMENITIES - normalized.amenities
    if safety_missing:
        names = ", ".join(sorted(item.replace("_", " ") for item in safety_missing))
        items.append(
            Improvement(
                category="amenities",
                priority=Priority.HIGH,
                recommendation=f"Verify and accurately list the following safety items: {names}.",
                rationale=(
                    "Safety details are high-impact trust signals; never claim "
                    "equipment that is not installed."
                ),
            )
        )
    if word_count < 100:
        items.append(
            Improvement(
                category="description",
                priority=Priority.HIGH,
                recommendation=(
                    "Expand the description to roughly 100 to 350 useful words covering "
                    "layout, experience, arrival, and location."
                ),
                rationale=(
                    "The current copy does not provide enough evidence for a confident "
                    "guest decision."
                ),
            )
        )
    elif word_count > 500:
        items.append(
            Improvement(
                category="description",
                priority=Priority.MEDIUM,
                recommendation=(
                    "Trim repeated details and lead with the most decision-relevant "
                    "100 to 350 words."
                ),
                rationale="Concise copy is easier to scan and keeps differentiators visible.",
            )
        )
    if missing_configuration:
        items.append(
            Improvement(
                category="content",
                priority=Priority.HIGH,
                recommendation=(f"State {_format_detail_list(missing_configuration)} explicitly."),
                rationale=(
                    "Concrete configuration details reduce ambiguity and improve search relevance."
                ),
            )
        )
    if not normalized.location_mentioned or not evidence.proximity:
        items.append(
            Improvement(
                category="seo",
                priority=Priority.MEDIUM,
                recommendation=(
                    "Mention the city or neighborhood and add verified walk/drive "
                    "times to two nearby points of interest."
                ),
                rationale=(
                    "Useful local context improves discoverability without exposing "
                    "an exact address."
                ),
            )
        )
    if not normalized.property_type_mentioned:
        items.append(
            Improvement(
                category="seo",
                priority=Priority.MEDIUM,
                recommendation=(
                    "Use the accurate property-type term naturally in the title or "
                    "opening sentence."
                ),
                rationale="Guests and search systems need a clear property category.",
            )
        )
    if readability.value < 60 or len(normalized.paragraphs) == 1:
        items.append(
            Improvement(
                category="readability",
                priority=Priority.MEDIUM,
                recommendation=(
                    "Use short paragraphs and descriptive sections for the space, "
                    "amenities, access, and location."
                ),
                rationale="Scannable structure helps guests find important details quickly.",
            )
        )
    if not evidence.arrival:
        items.append(
            Improvement(
                category="guest_clarity",
                priority=Priority.MEDIUM,
                recommendation=(
                    "Explain the arrival and property-access process without publishing "
                    "private access codes."
                ),
                rationale="Arrival clarity reduces pre-booking uncertainty.",
            )
        )
    if evidence.stuffed:
        items.append(
            Improvement(
                category="seo",
                priority=Priority.HIGH,
                recommendation=(
                    "Remove repeated keywords and describe each relevant feature once "
                    "in natural language."
                ),
                rationale=(
                    "Repetition harms readability and does not provide additional scoring credit."
                ),
            )
        )
    return tuple(items[:8])


class ListingAnalysisEngine:
    """Analyze listing content without network calls or framework dependencies."""

    methodology = METHODOLOGY

    def analyze(self, listing: Listing) -> DeterministicAnalysis:
        normalized = normalize_listing(listing)
        readability = _readability(normalized)
        seo = _seo(normalized)
        quality, evidence = _quality(normalized, readability)
        return DeterministicAnalysis(
            listing_quality=quality,
            seo=seo,
            readability=readability,
            strengths=_strengths(normalized, quality, seo, readability, evidence),
            weaknesses=_weaknesses(normalized, readability, evidence),
            missing_amenities=_missing_amenities(normalized, evidence),
            improvements=_improvements(normalized, readability, evidence),
        )


def analyze_listing(listing: Listing) -> DeterministicAnalysis:
    """Convenience entry point for callers that do not need engine reuse."""

    return ListingAnalysisEngine().analyze(listing)


__all__ = ["ListingAnalysisEngine", "METHODOLOGY", "analyze_listing"]
