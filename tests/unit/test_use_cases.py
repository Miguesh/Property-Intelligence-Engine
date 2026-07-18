from __future__ import annotations

import pytest

from property_intelligence.application.exceptions import GenerationUnavailableError
from property_intelligence.application.ports import GenerationRequest
from property_intelligence.application.use_cases import AnalyzeListingUseCase
from property_intelligence.domain.models import (
    DeterministicAnalysis,
    GeneratedContent,
    KnowledgeSnippet,
    Listing,
    Location,
    Score,
    ScoreComponent,
)
from property_intelligence.infrastructure.ai.fallback import DeterministicListingGenerator
from property_intelligence.infrastructure.ai.schemas import ListingGenerationPayload


def score(name: str, value: float) -> Score:
    return Score(
        value=value,
        components=(ScoreComponent(name=name, score=value, weight=1.0, rationale="fixture"),),
        methodology="test",
    )


class FakeEngine:
    def analyze(self, _listing: Listing) -> DeterministicAnalysis:
        return DeterministicAnalysis(
            listing_quality=score("quality", 72),
            seo=score("seo", 68),
            readability=score("readability", 81),
            strengths=("Clear location context.",),
            weaknesses=("Sleeping layout is not listed.",),
            missing_amenities=(),
            improvements=(),
        )


class FakeRetriever:
    async def retrieve(self, _listing: Listing, *, limit: int = 5) -> list[KnowledgeSnippet]:
        assert limit == 5
        return [
            KnowledgeSnippet(
                identifier="guide-1",
                content="Lead with a verified differentiator.",
                source="fixture",
            )
        ]


class FailingRetriever:
    async def retrieve(self, _listing: Listing, *, limit: int = 5) -> list[KnowledgeSnippet]:
        raise TimeoutError("provider timeout")


class FakeGenerator:
    def __init__(self, source: str = "fake") -> None:
        self.source = source
        self.last_request: GenerationRequest | None = None

    async def generate(self, request: GenerationRequest) -> GeneratedContent:
        self.last_request = request
        return GeneratedContent(
            titles=(
                "Ocean View Condo Near the Beach",
                "Miami Condo with Wi-Fi",
                "Bright Miami Condo",
            ),
            descriptions=(
                "A bright Miami condo near the beach with Wi-Fi and a kitchen.",
                "Enjoy the submitted ocean view, Wi-Fi, and kitchen in this Miami condo.",
            ),
            tags=(
                "ocean view",
                "near beach",
                "condo",
                "Miami",
                "Wi-Fi",
                "kitchen",
                "listing copy",
                "host review",
            ),
            source=self.source,
            prompt_version="test-v1",
        )


class FailingGenerator:
    async def generate(self, _request: GenerationRequest) -> GeneratedContent:
        raise TimeoutError("provider timeout")


class SchemaValidAdversarialGenerator:
    async def generate(self, _request: GenerationRequest) -> GeneratedContent:
        payload = ListingGenerationPayload(
            titles=[
                "Miami Condo with a Private Pool",
                "Mountain-View Condo by the Beach",
                "Luxury Miami Pool Retreat",
            ],
            descriptions=[
                "Swim in the private pool, only a 5-minute walk from the beach.",
                "Wake to mountain views from this polished Miami condo.",
            ],
            tags=[
                "Miami",
                "condo",
                "pool",
                "mountain view",
                "five minutes",
                "beach",
                "luxury",
                "retreat",
            ],
        )
        return GeneratedContent(
            titles=tuple(payload.titles),
            descriptions=tuple(payload.descriptions),
            tags=tuple(payload.tags),
            source="openai:test",
            prompt_version="listing-copy-test",
        )


def listing() -> Listing:
    return Listing(
        title="Ocean View Condo",
        description="A bright condo near the beach with fast Wi-Fi.",
        amenities=("Wi-Fi", "Kitchen"),
        property_type="Condo",
        location=Location(city="Miami", country="US"),
    )


def plain_listing() -> Listing:
    return Listing(
        title="Bright Miami Condo",
        description="A bright condo near the beach with fast Wi-Fi and a kitchen.",
        amenities=("Wi-Fi", "Kitchen"),
        property_type="Condo",
        location=Location(city="Miami", country="US"),
    )


@pytest.mark.asyncio
async def test_use_case_passes_retrieved_evidence_to_generator() -> None:
    generator = FakeGenerator()
    use_case = AnalyzeListingUseCase(
        engine=FakeEngine(),  # type: ignore[arg-type]
        generator=generator,
        retriever=FakeRetriever(),
    )

    result = await use_case.execute(listing())

    assert result.listing_quality.value == 72
    assert result.generated.source == "fake"
    assert result.retrieved_knowledge[0].identifier == "guide-1"
    assert generator.last_request is not None
    assert generator.last_request.knowledge[0].identifier == "guide-1"


@pytest.mark.asyncio
async def test_use_case_falls_back_when_optional_providers_fail() -> None:
    use_case = AnalyzeListingUseCase(
        engine=FakeEngine(),  # type: ignore[arg-type]
        generator=FailingGenerator(),
        retriever=FailingRetriever(),
        fallback_generator=FakeGenerator(source="deterministic_fallback"),
        fallback_retriever=FakeRetriever(),
    )

    result = await use_case.execute(listing())

    assert result.generated.source == "deterministic_fallback"
    assert len(result.warnings) == 2
    assert result.retrieved_knowledge


@pytest.mark.asyncio
async def test_required_generation_fails_closed() -> None:
    use_case = AnalyzeListingUseCase(
        engine=FakeEngine(),  # type: ignore[arg-type]
        generator=FailingGenerator(),
        retriever=FakeRetriever(),
        fallback_generator=FakeGenerator(),
        generation_required=True,
    )

    with pytest.raises(GenerationUnavailableError):
        await use_case.execute(listing())


@pytest.mark.asyncio
async def test_unsupported_ai_claims_use_deterministic_fallback_when_optional() -> None:
    use_case = AnalyzeListingUseCase(
        engine=FakeEngine(),  # type: ignore[arg-type]
        generator=SchemaValidAdversarialGenerator(),
        retriever=FakeRetriever(),
        fallback_generator=DeterministicListingGenerator(),
    )

    result = await use_case.execute(plain_listing())

    assert result.generated.source == "deterministic"
    assert any("factuality validation" in warning for warning in result.warnings)
    combined = " ".join(
        (*result.generated.titles, *result.generated.descriptions, *result.generated.tags)
    ).casefold()
    assert "pool" not in combined
    assert "mountain view" not in combined
    assert "5-minute" not in combined


@pytest.mark.asyncio
async def test_unsupported_ai_claims_fail_closed_when_generation_is_required() -> None:
    use_case = AnalyzeListingUseCase(
        engine=FakeEngine(),  # type: ignore[arg-type]
        generator=SchemaValidAdversarialGenerator(),
        retriever=FakeRetriever(),
        fallback_generator=DeterministicListingGenerator(),
        generation_required=True,
    )

    with pytest.raises(GenerationUnavailableError):
        await use_case.execute(plain_listing())


@pytest.mark.asyncio
async def test_default_deterministic_generation_removes_submitted_contact_channels() -> None:
    contact_listing = Listing(
        title="Bright Miami Condo",
        description=("https://example.com/stay host@example.com +1 (305) 555-0199"),
        amenities=("Wi-Fi", "Kitchen"),
        property_type="Condo",
        location=Location(city="Miami", country="US"),
    )
    use_case = AnalyzeListingUseCase(
        engine=FakeEngine(),  # type: ignore[arg-type]
        generator=DeterministicListingGenerator(),
        retriever=FakeRetriever(),
    )

    result = await use_case.execute(contact_listing)

    combined = " ".join(
        (*result.generated.titles, *result.generated.descriptions, *result.generated.tags)
    )
    assert result.generated.source == "deterministic"
    assert "example.com" not in combined
    assert "host@" not in combined
    assert "555-0199" not in combined
    assert "Review the submitted listing details" in combined
