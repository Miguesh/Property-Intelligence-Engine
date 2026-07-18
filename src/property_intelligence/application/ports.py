"""Ports implemented by external provider adapters."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from property_intelligence.domain.models import (
    DeterministicAnalysis,
    GeneratedContent,
    KnowledgeSnippet,
    Listing,
)


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    """Structured evidence supplied to a text-generation provider."""

    listing: Listing
    analysis: DeterministicAnalysis
    knowledge: tuple[KnowledgeSnippet, ...]


class TextGenerationPort(Protocol):
    """Generate improved listing copy without exposing a provider SDK."""

    async def generate(self, request: GenerationRequest) -> GeneratedContent:
        """Generate titles, descriptions, and tags."""


class GeneratedContentValidatorPort(Protocol):
    """Validate generated copy against submitted listing facts."""

    def validate(self, listing: Listing, generated: GeneratedContent) -> None:
        """Raise when generated copy violates the active claim policy."""


class KnowledgeRetrieverPort(Protocol):
    """Retrieve listing guidance from any knowledge implementation."""

    async def retrieve(self, listing: Listing, *, limit: int = 5) -> Sequence[KnowledgeSnippet]:
        """Return the most relevant guidance snippets."""


class EmbeddingPort(Protocol):
    """Convert text to provider-neutral embedding vectors."""

    async def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Embed a batch of knowledge documents."""

    async def embed_query(self, text: str) -> Sequence[float]:
        """Embed a single retrieval query."""


class VectorStorePort(Protocol):
    """Store and search vectors without exposing database-specific types."""

    async def upsert(
        self,
        snippets: Sequence[KnowledgeSnippet],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        """Insert or replace knowledge records and their vectors."""

    async def search(
        self,
        vector: Sequence[float],
        *,
        limit: int,
        filters: Mapping[str, str] | None = None,
    ) -> Sequence[KnowledgeSnippet]:
        """Find the nearest knowledge records."""


class HealthCheckPort(Protocol):
    """Optional readiness contract for an external adapter."""

    async def is_ready(self) -> bool:
        """Return whether the adapter can accept requests."""
