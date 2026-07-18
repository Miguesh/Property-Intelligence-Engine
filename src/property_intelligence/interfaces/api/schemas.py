"""Pydantic request and response contracts for the REST API."""

from __future__ import annotations

from typing import Annotated, Any, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from property_intelligence.domain.models import (
    MAX_AMENITIES,
    MAX_AMENITY_LENGTH,
    MAX_DESCRIPTION_LENGTH,
    MAX_LOCATION_PART_LENGTH,
    MAX_PROPERTY_TYPE_LENGTH,
    MAX_TITLE_LENGTH,
    AnalysisResult,
    Listing,
    Location,
)

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
AmenityText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_AMENITY_LENGTH),
]


class ApiSchema(BaseModel):
    """Strict base schema for all external contracts."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LocationRequest(ApiSchema):
    """Structured location without implicit geocoding."""

    city: NonEmptyText = Field(max_length=MAX_LOCATION_PART_LENGTH)
    country: NonEmptyText = Field(max_length=MAX_LOCATION_PART_LENGTH)
    region: str | None = Field(default=None, max_length=MAX_LOCATION_PART_LENGTH)
    neighborhood: str | None = Field(default=None, max_length=MAX_LOCATION_PART_LENGTH)


class ListingAnalysisRequest(ApiSchema):
    """Listing content accepted by the analysis endpoint."""

    title: NonEmptyText = Field(max_length=MAX_TITLE_LENGTH)
    description: NonEmptyText = Field(max_length=MAX_DESCRIPTION_LENGTH)
    amenities: list[AmenityText] = Field(default_factory=list, max_length=MAX_AMENITIES)
    property_type: NonEmptyText = Field(max_length=MAX_PROPERTY_TYPE_LENGTH)
    location: LocationRequest
    language: str = Field(default="en", pattern=r"^[Ee][Nn](?:-[A-Za-z]{2})?$")

    @field_validator("amenities")
    @classmethod
    def normalize_amenities(cls, amenities: list[str]) -> list[str]:
        """Deduplicate amenities without losing their submitted spelling."""

        unique: dict[str, str] = {}
        for amenity in amenities:
            normalized = " ".join(amenity.split())
            unique.setdefault(normalized.casefold(), normalized)
        return list(unique.values())

    def to_domain(self) -> Listing:
        """Map the transport schema into the framework-independent domain."""

        return Listing(
            title=self.title,
            description=self.description,
            amenities=tuple(self.amenities),
            property_type=self.property_type,
            location=Location(**self.location.model_dump()),
            language=self.language,
        )


class ScoreComponentResponse(ApiSchema):
    name: str
    score: float
    weight: float
    rationale: str


class ScoreResponse(ApiSchema):
    value: float
    components: list[ScoreComponentResponse]
    methodology: str


class AmenitySuggestionResponse(ApiSchema):
    name: str
    priority: str
    reason: str
    confidence: float


class ImprovementResponse(ApiSchema):
    category: str
    priority: str
    recommendation: str
    rationale: str


class KnowledgeReferenceResponse(ApiSchema):
    identifier: str
    source: str
    score: float | None = None


class AnalysisResponse(ApiSchema):
    """Stable public analysis response with all requested outputs."""

    analysis_id: str
    listing_quality_score: float
    seo_score: float
    readability_score: float
    score_details: dict[str, ScoreResponse]
    strengths: list[str]
    weaknesses: list[str]
    missing_amenities: list[AmenitySuggestionResponse]
    recommended_improvements: list[ImprovementResponse]
    better_title_suggestions: list[str]
    better_descriptions: list[str]
    suggested_tags: list[str]
    generation_source: str
    prompt_version: str
    knowledge_references: list[KnowledgeReferenceResponse]
    warnings: list[str]

    @classmethod
    def from_domain(cls, result: AnalysisResult) -> Self:
        scores = {
            "listing_quality": result.listing_quality,
            "seo": result.seo,
            "readability": result.readability,
        }
        return cls(
            analysis_id=result.analysis_id,
            listing_quality_score=result.listing_quality.value,
            seo_score=result.seo.value,
            readability_score=result.readability.value,
            score_details={
                name: ScoreResponse(
                    value=score.value,
                    components=[
                        ScoreComponentResponse(
                            name=component.name,
                            score=component.score,
                            weight=component.weight,
                            rationale=component.rationale,
                        )
                        for component in score.components
                    ],
                    methodology=score.methodology,
                )
                for name, score in scores.items()
            },
            strengths=list(result.strengths),
            weaknesses=list(result.weaknesses),
            missing_amenities=[
                AmenitySuggestionResponse(
                    name=item.name,
                    priority=item.priority.value,
                    reason=item.reason,
                    confidence=item.confidence,
                )
                for item in result.missing_amenities
            ],
            recommended_improvements=[
                ImprovementResponse(
                    category=item.category,
                    priority=item.priority.value,
                    recommendation=item.recommendation,
                    rationale=item.rationale,
                )
                for item in result.improvements
            ],
            better_title_suggestions=list(result.generated.titles),
            better_descriptions=list(result.generated.descriptions),
            suggested_tags=list(result.generated.tags),
            generation_source=result.generated.source,
            prompt_version=result.generated.prompt_version,
            knowledge_references=[
                KnowledgeReferenceResponse(
                    identifier=item.identifier,
                    source=item.source,
                    score=item.score,
                )
                for item in result.retrieved_knowledge
            ],
            warnings=list(result.warnings),
        )


class ErrorItem(ApiSchema):
    code: str
    message: str
    details: list[dict[str, Any]] | None = None


class ErrorResponse(ApiSchema):
    error: ErrorItem
    request_id: str


class HealthResponse(ApiSchema):
    status: str
    version: str
    environment: str
    components: dict[str, str] = Field(default_factory=dict)
