"""Provider-facing schemas for structured listing generation."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from property_intelligence.domain.models import (
    GENERATED_DESCRIPTION_COUNT,
    GENERATED_TITLE_COUNT,
    MAX_GENERATED_DESCRIPTION_LENGTH,
    MAX_GENERATED_TAG_LENGTH,
    MAX_GENERATED_TAGS,
    MAX_GENERATED_TITLE_LENGTH,
    MIN_GENERATED_TAGS,
)

GeneratedTitle = Annotated[
    str,
    Field(min_length=1, max_length=MAX_GENERATED_TITLE_LENGTH),
]
GeneratedDescription = Annotated[
    str,
    Field(min_length=1, max_length=MAX_GENERATED_DESCRIPTION_LENGTH),
]
GeneratedTag = Annotated[str, Field(min_length=1, max_length=MAX_GENERATED_TAG_LENGTH)]


class ListingGenerationPayload(BaseModel):
    """Strict response requested from the language model.

    The schema deliberately contains only transport primitives. Conversion to
    the provider-neutral :class:`GeneratedContent` model happens in the
    adapter after validation.
    """

    model_config = ConfigDict(extra="forbid")

    titles: Annotated[
        list[GeneratedTitle],
        Field(
            min_length=GENERATED_TITLE_COUNT,
            max_length=GENERATED_TITLE_COUNT,
            description="Exactly three distinct, factual listing title suggestions.",
        ),
    ]
    descriptions: Annotated[
        list[GeneratedDescription],
        Field(
            min_length=GENERATED_DESCRIPTION_COUNT,
            max_length=GENERATED_DESCRIPTION_COUNT,
            description="Exactly two distinct, fact-preserving listing descriptions.",
        ),
    ]
    tags: Annotated[
        list[GeneratedTag],
        Field(
            min_length=MIN_GENERATED_TAGS,
            max_length=MAX_GENERATED_TAGS,
            description="Eight to twelve distinct, factual discovery tags.",
        ),
    ]

    @field_validator("titles", "descriptions", "tags")
    @classmethod
    def normalize_items(cls, values: list[str]) -> list[str]:
        """Trim provider output and reject blank or duplicate values."""

        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("generated values must not be blank")
        if len({value.casefold() for value in normalized}) != len(normalized):
            raise ValueError("generated values must be unique")
        return normalized

    @model_validator(mode="after")
    def enforce_generation_contract(self) -> ListingGenerationPayload:
        """Enforce product constraints not guaranteed by JSON Schema alone."""

        if len(self.titles) != GENERATED_TITLE_COUNT:
            raise ValueError("exactly three title suggestions are required")
        if len(self.descriptions) != GENERATED_DESCRIPTION_COUNT:
            raise ValueError("exactly two description suggestions are required")
        if not MIN_GENERATED_TAGS <= len(self.tags) <= MAX_GENERATED_TAGS:
            raise ValueError("between eight and twelve tags are required")
        if any(len(title) > MAX_GENERATED_TITLE_LENGTH for title in self.titles):
            raise ValueError("title suggestions must be at most 80 characters")
        if any(
            len(description) > MAX_GENERATED_DESCRIPTION_LENGTH for description in self.descriptions
        ):
            raise ValueError("description suggestions must be at most 2,000 characters")
        if any(len(tag) > MAX_GENERATED_TAG_LENGTH for tag in self.tags):
            raise ValueError("tags must be at most 50 characters")
        return self
