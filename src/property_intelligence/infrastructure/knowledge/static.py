"""Key-free lexical retrieval over the bundled guidance corpus."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from pathlib import Path

from property_intelligence.application.ports import KnowledgeRetrieverPort
from property_intelligence.domain.models import KnowledgeSnippet, Listing
from property_intelligence.infrastructure.knowledge.corpus import load_guidance_corpus

_TOKEN_PATTERN = re.compile(r"[\w'-]+", re.UNICODE)
_STOP_WORDS = frozenset(
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
        "that",
        "the",
        "this",
        "to",
        "with",
        "your",
    }
)


class StaticKnowledgeRetriever(KnowledgeRetrieverPort):
    """Rank in-process guidance deterministically using lexical overlap."""

    def __init__(self, snippets: Sequence[KnowledgeSnippet]) -> None:
        if not snippets:
            raise ValueError("at least one knowledge snippet is required")
        self._snippets = tuple(snippets)

    @classmethod
    def from_corpus(cls, path: str | Path | None = None) -> StaticKnowledgeRetriever:
        """Build the fallback retriever from the validated JSON corpus."""

        return cls(load_guidance_corpus(path).to_snippets())

    async def retrieve(self, listing: Listing, *, limit: int = 5) -> tuple[KnowledgeSnippet, ...]:
        if limit <= 0:
            raise ValueError("limit must be positive")

        query_tokens = _tokens(
            " ".join(
                (
                    listing.title,
                    listing.description,
                    listing.property_type,
                    listing.location.display_name,
                    " ".join(listing.amenities),
                )
            )
        )
        ranked = sorted(
            enumerate(self._snippets),
            key=lambda item: (
                -self._score(item[1], query_tokens, listing),
                item[0],
            ),
        )

        results: list[KnowledgeSnippet] = []
        for _, snippet in ranked[:limit]:
            results.append(
                KnowledgeSnippet(
                    identifier=snippet.identifier,
                    content=snippet.content,
                    source=snippet.source,
                    score=self._score(snippet, query_tokens, listing),
                    metadata=snippet.metadata,
                )
            )
        return tuple(results)

    @staticmethod
    def _score(snippet: KnowledgeSnippet, query_tokens: set[str], listing: Listing) -> float:
        document_tokens = _tokens(" ".join((snippet.content, " ".join(snippet.metadata.values()))))
        overlap = len(query_tokens & document_tokens)
        lexical = overlap / math.sqrt(max(len(document_tokens), 1))

        metadata = snippet.metadata
        property_type = metadata.get("property_type", "all").casefold()
        property_boost = 0.2 if property_type == listing.property_type.casefold() else 0.0
        if property_type == "all":
            property_boost = 0.05

        amenity = metadata.get("amenity")
        amenity_boost = (
            0.15
            if amenity and amenity.casefold() in {item.casefold() for item in listing.amenities}
            else 0.0
        )
        return round(lexical + property_boost + amenity_boost, 6)


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in _TOKEN_PATTERN.findall(value.casefold())
        if len(token) > 1 and token not in _STOP_WORDS
    }
