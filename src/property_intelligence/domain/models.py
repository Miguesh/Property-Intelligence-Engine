"""Core domain models for listing analysis.

These objects deliberately avoid Pydantic, FastAPI, LangChain, and provider
SDKs. Validation at the API boundary is repeated here for invariants that must
hold regardless of the caller.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

MAX_TITLE_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 10_000
MAX_AMENITIES = 100
MAX_AMENITY_LENGTH = 120
MAX_PROPERTY_TYPE_LENGTH = 100
MAX_LOCATION_PART_LENGTH = 120
GENERATED_TITLE_COUNT = 3
GENERATED_DESCRIPTION_COUNT = 2
MIN_GENERATED_TAGS = 8
MAX_GENERATED_TAGS = 12
MAX_GENERATED_TITLE_LENGTH = 80
MAX_GENERATED_DESCRIPTION_LENGTH = 2_000
MAX_GENERATED_TAG_LENGTH = 50
_LANGUAGE_PATTERN = re.compile(r"^en(?:-[a-z]{2})?$")


class Priority(StrEnum):
    """Business priority assigned to a recommendation."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True, slots=True)
class Location:
    """Structured property location used for relevant recommendations."""

    city: str
    country: str
    region: str | None = None
    neighborhood: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("city", "country"):
            value = getattr(self, field_name).strip()
            if not value:
                raise ValueError(f"{field_name} must not be empty")
            if len(value) > MAX_LOCATION_PART_LENGTH:
                raise ValueError(
                    f"{field_name} must be at most {MAX_LOCATION_PART_LENGTH} characters"
                )
            object.__setattr__(self, field_name, value)
        for field_name in ("region", "neighborhood"):
            value = getattr(self, field_name)
            cleaned = value.strip() if value else None
            if cleaned and len(cleaned) > MAX_LOCATION_PART_LENGTH:
                raise ValueError(
                    f"{field_name} must be at most {MAX_LOCATION_PART_LENGTH} characters"
                )
            object.__setattr__(self, field_name, cleaned)

    @property
    def display_name(self) -> str:
        """Return a concise human-readable location."""

        parts = [self.neighborhood, self.city, self.region, self.country]
        return ", ".join(part for part in parts if part)


@dataclass(frozen=True, slots=True)
class Listing:
    """A short-term rental listing submitted for analysis."""

    title: str
    description: str
    amenities: tuple[str, ...]
    property_type: str
    location: Location
    language: str = "en"

    def __post_init__(self) -> None:
        title = self.title.strip()
        description = self.description.strip()
        property_type = self.property_type.strip()
        language = self.language.strip().lower()
        if not title:
            raise ValueError("title must not be empty")
        if not description:
            raise ValueError("description must not be empty")
        if not property_type:
            raise ValueError("property_type must not be empty")
        if not language:
            raise ValueError("language must not be empty")
        if len(title) > MAX_TITLE_LENGTH:
            raise ValueError(f"title must be at most {MAX_TITLE_LENGTH} characters")
        if len(description) > MAX_DESCRIPTION_LENGTH:
            raise ValueError(f"description must be at most {MAX_DESCRIPTION_LENGTH} characters")
        if len(property_type) > MAX_PROPERTY_TYPE_LENGTH:
            raise ValueError(f"property_type must be at most {MAX_PROPERTY_TYPE_LENGTH} characters")
        if not _LANGUAGE_PATTERN.fullmatch(language):
            raise ValueError("language must be English ('en' or an 'en-XX' locale)")
        if len(self.amenities) > MAX_AMENITIES:
            raise ValueError(f"amenities must contain at most {MAX_AMENITIES} items")

        amenities: list[str] = []
        seen_amenities: set[str] = set()
        for item in self.amenities:
            cleaned = item.strip()
            if len(cleaned) > MAX_AMENITY_LENGTH:
                raise ValueError(f"amenities must be at most {MAX_AMENITY_LENGTH} characters each")
            key = "".join(
                character
                for character in unicodedata.normalize("NFKC", cleaned).casefold()
                if character.isalnum()
            )
            if cleaned and key not in seen_amenities:
                seen_amenities.add(key)
                amenities.append(cleaned)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "description", description)
        object.__setattr__(self, "property_type", property_type)
        object.__setattr__(self, "language", language)
        object.__setattr__(self, "amenities", tuple(amenities))


@dataclass(frozen=True, slots=True)
class ScoreComponent:
    """One explainable component of a score."""

    name: str
    score: float
    weight: float
    rationale: str

    def __post_init__(self) -> None:
        if not 0 <= self.score <= 100:
            raise ValueError("component score must be between 0 and 100")
        if not 0 < self.weight <= 1:
            raise ValueError("component weight must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class Score:
    """A normalized score with a transparent component breakdown."""

    value: float
    components: tuple[ScoreComponent, ...]
    methodology: str

    def __post_init__(self) -> None:
        if not 0 <= self.value <= 100:
            raise ValueError("score must be between 0 and 100")


@dataclass(frozen=True, slots=True)
class AmenitySuggestion:
    """An amenity absent from submitted data but valuable for this listing."""

    name: str
    priority: Priority
    reason: str
    confidence: float

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class Improvement:
    """A concrete, prioritized improvement to listing content."""

    category: str
    priority: Priority
    recommendation: str
    rationale: str


@dataclass(frozen=True, slots=True)
class KnowledgeSnippet:
    """A retrieved piece of guidance used to ground generation."""

    identifier: str
    content: str
    source: str
    score: float | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class GeneratedContent:
    """Provider-generated listing copy with a stable output contract."""

    titles: tuple[str, ...]
    descriptions: tuple[str, ...]
    tags: tuple[str, ...]
    source: str
    prompt_version: str

    def __post_init__(self) -> None:
        titles = tuple(value.strip() for value in self.titles)
        descriptions = tuple(value.strip() for value in self.descriptions)
        tags = tuple(value.strip() for value in self.tags)
        if len(titles) != GENERATED_TITLE_COUNT:
            raise ValueError(f"generated content requires exactly {GENERATED_TITLE_COUNT} titles")
        if len(descriptions) != GENERATED_DESCRIPTION_COUNT:
            raise ValueError(
                f"generated content requires exactly {GENERATED_DESCRIPTION_COUNT} descriptions"
            )
        if not MIN_GENERATED_TAGS <= len(tags) <= MAX_GENERATED_TAGS:
            raise ValueError(
                f"generated content requires {MIN_GENERATED_TAGS} to {MAX_GENERATED_TAGS} tags"
            )
        self._validate_unique_values(titles, "titles", MAX_GENERATED_TITLE_LENGTH)
        self._validate_unique_values(
            descriptions,
            "descriptions",
            MAX_GENERATED_DESCRIPTION_LENGTH,
        )
        self._validate_unique_values(tags, "tags", MAX_GENERATED_TAG_LENGTH)
        if not self.source.strip():
            raise ValueError("generated content source must not be blank")
        if not self.prompt_version.strip():
            raise ValueError("generated content prompt_version must not be blank")
        object.__setattr__(self, "titles", titles)
        object.__setattr__(self, "descriptions", descriptions)
        object.__setattr__(self, "tags", tags)
        object.__setattr__(self, "source", self.source.strip())
        object.__setattr__(self, "prompt_version", self.prompt_version.strip())

    @staticmethod
    def _validate_unique_values(values: tuple[str, ...], name: str, max_length: int) -> None:
        if any(not value for value in values):
            raise ValueError(f"generated {name} must not be blank")
        if any(len(value) > max_length for value in values):
            raise ValueError(f"generated {name} exceed their maximum length")
        if len({value.casefold() for value in values}) != len(values):
            raise ValueError(f"generated {name} must be unique")


@dataclass(frozen=True, slots=True)
class DeterministicAnalysis:
    """Provider-independent evidence produced before any LLM invocation."""

    listing_quality: Score
    seo: Score
    readability: Score
    strengths: tuple[str, ...]
    weaknesses: tuple[str, ...]
    missing_amenities: tuple[AmenitySuggestion, ...]
    improvements: tuple[Improvement, ...]


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    """Complete analysis returned by the application use case."""

    analysis_id: str
    listing_quality: Score
    seo: Score
    readability: Score
    strengths: tuple[str, ...]
    weaknesses: tuple[str, ...]
    missing_amenities: tuple[AmenitySuggestion, ...]
    improvements: tuple[Improvement, ...]
    generated: GeneratedContent
    warnings: tuple[str, ...] = ()
    retrieved_knowledge: tuple[KnowledgeSnippet, ...] = ()
