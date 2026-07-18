"""Bounds for provider-facing retrieval input."""

from property_intelligence.domain.models import Listing, Location
from property_intelligence.infrastructure.knowledge.retriever import VectorKnowledgeRetriever


def test_vector_retrieval_query_has_a_hard_character_budget() -> None:
    listing = Listing(
        title="T" * 200,
        description="description " * 700,
        amenities=tuple(f"{index:02d}-" + ("x" * 117) for index in range(40)),
        property_type="P" * 100,
        location=Location(
            city="C" * 120,
            country="U" * 120,
            region="R" * 120,
            neighborhood="N" * 120,
        ),
    )

    query = VectorKnowledgeRetriever.build_query(listing)

    assert len(query) == 6_000
