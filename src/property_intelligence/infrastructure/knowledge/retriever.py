"""Vector-backed implementation of the knowledge retrieval port."""

from __future__ import annotations

from property_intelligence.application.ports import (
    EmbeddingPort,
    KnowledgeRetrieverPort,
    VectorStorePort,
)
from property_intelligence.domain.models import KnowledgeSnippet, Listing


class VectorKnowledgeRetriever(KnowledgeRetrieverPort):
    """Compose provider-neutral embedding and vector-store ports."""

    def __init__(self, embeddings: EmbeddingPort, vector_store: VectorStorePort) -> None:
        self._embeddings = embeddings
        self._vector_store = vector_store

    async def retrieve(self, listing: Listing, *, limit: int = 5) -> tuple[KnowledgeSnippet, ...]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        query = self.build_query(listing)
        vector = await self._embeddings.embed_query(query)
        snippets = await self._vector_store.search(vector, limit=limit)
        return tuple(snippets)

    @staticmethod
    def build_query(listing: Listing) -> str:
        """Build a bounded fact-only retrieval query from a listing."""

        description = " ".join(listing.description.split())[:1_500]
        amenities = ", ".join(listing.amenities[:30]) or "not specified"
        query = (
            f"Short-term rental listing guidance. Property type: {listing.property_type}. "
            f"Location: {listing.location.display_name}. Language: {listing.language}. "
            f"Title: {listing.title}. Description: {description}. Amenities: {amenities}."
        )
        return query[:6_000]
