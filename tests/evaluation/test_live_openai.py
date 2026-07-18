from __future__ import annotations

import os

import pytest

from property_intelligence.application.ports import GenerationRequest
from property_intelligence.domain.analysis import ListingAnalysisEngine
from property_intelligence.domain.models import Listing, Location
from property_intelligence.infrastructure.ai import LangChainListingGenerator
from property_intelligence.infrastructure.knowledge import StaticKnowledgeRetriever


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_openai_generation_contract() -> None:
    """Opt-in paid smoke test; normal CI never requires external credentials."""

    api_key = os.getenv("PIE_OPENAI_API_KEY")
    if not api_key:
        pytest.skip("PIE_OPENAI_API_KEY is required for the live OpenAI check")

    listing = Listing(
        title="Quiet Asheville Cabin",
        description=(
            "A one-bedroom cabin for two guests with mountain views, a fireplace, "
            "fast Wi-Fi, a full kitchen, and free parking. Downtown Asheville is a "
            "fifteen-minute drive. The gravel path has three steps."
        ),
        amenities=("Wi-Fi", "Fireplace", "Kitchen", "Free parking", "Smoke alarm"),
        property_type="Cabin",
        location=Location(city="Asheville", region="North Carolina", country="USA"),
    )
    analysis = ListingAnalysisEngine().analyze(listing)
    knowledge = await StaticKnowledgeRetriever.from_corpus().retrieve(listing, limit=5)
    generator = LangChainListingGenerator(api_key=api_key)

    generated = await generator.generate(
        GenerationRequest(listing=listing, analysis=analysis, knowledge=knowledge)
    )

    assert len(generated.titles) == 3
    assert all(1 <= len(title) <= 80 for title in generated.titles)
    assert len(generated.descriptions) == 2
    assert all(description.strip() for description in generated.descriptions)
    assert 8 <= len(generated.tags) <= 12
