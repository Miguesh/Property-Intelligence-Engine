"""Embedding adapters for OpenAI and deterministic local execution."""

from __future__ import annotations

import asyncio
import hashlib
import math
import re
from collections.abc import Sequence
from typing import Protocol

from langchain_openai import OpenAIEmbeddings
from pydantic import SecretStr

from property_intelligence.application.exceptions import RetrievalUnavailableError
from property_intelligence.application.ports import EmbeddingPort

_TOKEN_PATTERN = re.compile(r"[\w'-]+", re.UNICODE)


class _AsyncEmbeddingClient(Protocol):
    async def aembed_documents(self, texts: list[str]) -> list[list[float]]: ...

    async def aembed_query(self, text: str) -> list[float]: ...


class OpenAIEmbeddingAdapter(EmbeddingPort):
    """Use LangChain's native async OpenAI embeddings implementation."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "text-embedding-3-small",
        dimensions: int = 1_536,
        timeout_seconds: float = 20.0,
        max_retries: int = 2,
        chunk_size: int = 128,
        client: _AsyncEmbeddingClient | None = None,
    ) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_retries < 0:
            raise ValueError("max_retries must not be negative")
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        self._dimensions = dimensions
        self._timeout_seconds = timeout_seconds
        if client is not None:
            self._client = client
        else:
            if not api_key:
                raise ValueError("api_key is required when no embedding client is injected")
            self._client = OpenAIEmbeddings(
                openai_api_key=SecretStr(api_key),
                model=model,
                dimensions=dimensions,
                request_timeout=timeout_seconds,
                max_retries=max_retries,
                chunk_size=chunk_size,
            )

    @property
    def dimensions(self) -> int:
        """Return the vector size required by the backing collection."""

        return self._dimensions

    async def embed_documents(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        if not texts:
            return ()
        normalized = [text.strip() for text in texts]
        if any(not text for text in normalized):
            raise ValueError("documents to embed must not be blank")
        try:
            async with asyncio.timeout(self._timeout_seconds):
                vectors = await self._client.aembed_documents(normalized)
        except Exception:
            raise RetrievalUnavailableError(
                "Embedding provider is temporarily unavailable"
            ) from None
        return self._validate_vectors(vectors, expected_count=len(normalized))

    async def embed_query(self, text: str) -> tuple[float, ...]:
        normalized = text.strip()
        if not normalized:
            raise ValueError("query to embed must not be blank")
        try:
            async with asyncio.timeout(self._timeout_seconds):
                vector = await self._client.aembed_query(normalized)
        except Exception:
            raise RetrievalUnavailableError(
                "Embedding provider is temporarily unavailable"
            ) from None
        return self._validate_vector(vector)

    def _validate_vectors(
        self, vectors: Sequence[Sequence[float]], *, expected_count: int
    ) -> tuple[tuple[float, ...], ...]:
        if len(vectors) != expected_count:
            raise RetrievalUnavailableError(
                "Embedding provider returned an unexpected number of vectors"
            )
        return tuple(self._validate_vector(vector) for vector in vectors)

    def _validate_vector(self, vector: Sequence[float]) -> tuple[float, ...]:
        if len(vector) != self._dimensions:
            raise RetrievalUnavailableError(
                "Embedding provider returned a vector with the wrong dimensions"
            )
        try:
            normalized = tuple(float(value) for value in vector)
        except (TypeError, ValueError, OverflowError):
            raise RetrievalUnavailableError(
                "Embedding provider returned a vector with invalid numeric values"
            ) from None
        if not all(math.isfinite(value) for value in normalized):
            raise RetrievalUnavailableError("Embedding provider returned a non-finite vector")
        return normalized


class DeterministicHashEmbeddingAdapter(EmbeddingPort):
    """Stable, key-free lexical embeddings for tests and local smoke checks.

    This adapter is intentionally not presented as a semantic replacement for
    a production embedding model. Token hashing makes related texts share
    coordinates, which is sufficient to exercise the complete retrieval path.
    """

    def __init__(self, dimensions: int = 64) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed_documents(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        return tuple(self._embed(text) for text in texts)

    async def embed_query(self, text: str) -> tuple[float, ...]:
        return self._embed(text)

    def _embed(self, text: str) -> tuple[float, ...]:
        vector = [0.0] * self._dimensions
        tokens = _TOKEN_PATTERN.findall(text.casefold())
        if not tokens:
            return tuple(vector)

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return tuple(vector)
        return tuple(value / norm for value in vector)
