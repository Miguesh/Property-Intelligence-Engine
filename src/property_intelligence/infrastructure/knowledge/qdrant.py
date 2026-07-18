"""Native async Qdrant implementation of the vector-store port."""

from __future__ import annotations

import asyncio
import math
import uuid
from collections.abc import Mapping, Sequence
from typing import Any, Self

from qdrant_client import AsyncQdrantClient, models

from property_intelligence.application.exceptions import RetrievalUnavailableError
from property_intelligence.application.ports import VectorStorePort
from property_intelligence.domain.models import KnowledgeSnippet

_POINT_NAMESPACE = uuid.UUID("68e4481f-225a-4f4f-88a7-bdce2eb24bfd")
_RESERVED_PAYLOAD_KEYS = frozenset({"identifier", "content", "source", "metadata"})


class VectorStoreConfigurationError(RuntimeError):
    """Raised when a collection is incompatible with configured embeddings."""


class QdrantVectorStore(VectorStorePort):
    """Store and query unnamed dense vectors using Qdrant's native async client."""

    def __init__(
        self,
        *,
        client: AsyncQdrantClient,
        collection_name: str,
        vector_size: int = 1_536,
        distance: models.Distance = models.Distance.COSINE,
        auto_create: bool = True,
        operation_timeout_seconds: int = 10,
        score_threshold: float | None = None,
        owns_client: bool = False,
        expected_metadata: Mapping[str, str | int] | None = None,
    ) -> None:
        if not collection_name.strip():
            raise ValueError("collection_name must not be blank")
        if vector_size <= 0:
            raise ValueError("vector_size must be positive")
        if operation_timeout_seconds <= 0:
            raise ValueError("operation_timeout_seconds must be positive")
        if score_threshold is not None and not -1 <= score_threshold <= 1:
            raise ValueError("score_threshold must be between -1 and 1")

        self._client = client
        self._collection_name = collection_name.strip()
        self._vector_size = vector_size
        self._distance = distance
        self._auto_create = auto_create
        self._operation_timeout_seconds = operation_timeout_seconds
        self._score_threshold = score_threshold
        self._owns_client = owns_client
        self._expected_metadata = dict(expected_metadata) if expected_metadata is not None else None
        self._initialized = False
        self._initialization_lock = asyncio.Lock()

    @classmethod
    def from_url(
        cls,
        *,
        url: str,
        collection_name: str,
        vector_size: int = 1_536,
        api_key: str | None = None,
        timeout_seconds: int = 10,
        prefer_grpc: bool = False,
        auto_create: bool = True,
        score_threshold: float | None = None,
        expected_metadata: Mapping[str, str | int] | None = None,
    ) -> Self:
        """Construct an adapter that owns its async Qdrant client."""

        client = AsyncQdrantClient(
            url=url,
            api_key=api_key,
            timeout=timeout_seconds,
            prefer_grpc=prefer_grpc,
        )
        return cls(
            client=client,
            collection_name=collection_name,
            vector_size=vector_size,
            auto_create=auto_create,
            operation_timeout_seconds=timeout_seconds,
            score_threshold=score_threshold,
            owns_client=True,
            expected_metadata=expected_metadata,
        )

    async def initialize(self) -> None:
        """Create a missing collection and validate an existing collection."""

        if self._initialized:
            return
        async with self._initialization_lock:
            if self._initialized:
                return
            try:
                exists = await self._client.collection_exists(self._collection_name)
                if not exists:
                    if not self._auto_create:
                        raise VectorStoreConfigurationError(
                            f"Qdrant collection {self._collection_name!r} does not exist"
                        )
                    try:
                        await self._client.create_collection(
                            collection_name=self._collection_name,
                            vectors_config=models.VectorParams(
                                size=self._vector_size,
                                distance=self._distance,
                            ),
                            timeout=self._operation_timeout_seconds,
                            metadata=self._expected_metadata,
                        )
                    except Exception:
                        # Multiple service replicas may race on first startup.
                        # Only tolerate the failure if another replica created
                        # the collection successfully.
                        if not await self._client.collection_exists(self._collection_name):
                            raise
                await self._validate_collection()
                self._initialized = True
            except VectorStoreConfigurationError:
                raise
            except Exception:
                raise RetrievalUnavailableError("Vector store initialization failed") from None

    async def _validate_collection(self) -> None:
        info = await self._client.get_collection(self._collection_name)
        vectors = info.config.params.vectors
        if vectors is None:
            raise VectorStoreConfigurationError(
                "Qdrant collection does not define a dense vector configuration"
            )
        if isinstance(vectors, dict):
            raise VectorStoreConfigurationError(
                "named-vector Qdrant collections are not supported by this adapter"
            )
        if vectors.size != self._vector_size:
            raise VectorStoreConfigurationError(
                "Qdrant collection vector size does not match the embedding configuration"
            )
        if vectors.distance != self._distance:
            raise VectorStoreConfigurationError(
                "Qdrant collection distance does not match the adapter configuration"
            )
        if self._expected_metadata is not None:
            collection_metadata = info.config.metadata or {}
            for key, expected_value in self._expected_metadata.items():
                if key not in collection_metadata:
                    raise VectorStoreConfigurationError(
                        f"Qdrant collection compatibility metadata is missing {key!r}"
                    )
                if collection_metadata[key] != expected_value:
                    raise VectorStoreConfigurationError(
                        f"Qdrant collection compatibility metadata does not match for {key!r}"
                    )

    async def upsert(
        self,
        snippets: Sequence[KnowledgeSnippet],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        if len(snippets) != len(vectors):
            raise ValueError("each knowledge snippet must have exactly one vector")
        if not snippets:
            return
        normalized_vectors = [self._validate_vector(vector) for vector in vectors]
        if len({snippet.identifier for snippet in snippets}) != len(snippets):
            raise ValueError("knowledge snippet identifiers must be unique within a batch")

        await self.initialize()
        points = [
            models.PointStruct(
                id=self._point_id(snippet.identifier),
                vector=vector,
                payload={
                    "identifier": snippet.identifier,
                    "content": snippet.content,
                    "source": snippet.source,
                    "metadata": dict(snippet.metadata),
                },
            )
            for snippet, vector in zip(snippets, normalized_vectors, strict=True)
        ]
        try:
            await self._client.upsert(
                collection_name=self._collection_name,
                points=points,
                wait=True,
                timeout=self._operation_timeout_seconds,
            )
        except Exception:
            raise RetrievalUnavailableError("Vector store upsert failed") from None

    async def search(
        self,
        vector: Sequence[float],
        *,
        limit: int,
        filters: Mapping[str, str] | None = None,
    ) -> tuple[KnowledgeSnippet, ...]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        normalized_vector = self._validate_vector(vector)
        await self.initialize()
        try:
            response = await self._client.query_points(
                collection_name=self._collection_name,
                query=normalized_vector,
                query_filter=self._build_filter(filters),
                limit=limit,
                with_payload=True,
                with_vectors=False,
                score_threshold=self._score_threshold,
                timeout=self._operation_timeout_seconds,
            )
            return tuple(self._to_snippet(point) for point in response.points)
        except Exception:
            raise RetrievalUnavailableError("Vector store query failed") from None

    async def is_ready(self) -> bool:
        """Return readiness without creating or mutating a collection."""

        try:
            if not await self._client.collection_exists(self._collection_name):
                return False
            await self._validate_collection()
        except Exception:
            return False
        return True

    async def close(self) -> None:
        """Close the Qdrant client when this adapter created it."""

        if self._owns_client:
            await self._client.close()

    def _validate_vector(self, vector: Sequence[float]) -> list[float]:
        if len(vector) != self._vector_size:
            raise ValueError(
                f"expected a {self._vector_size}-dimension vector, received {len(vector)}"
            )
        normalized = [float(value) for value in vector]
        if not all(math.isfinite(value) for value in normalized):
            raise ValueError("vectors must contain only finite numeric values")
        return normalized

    def _point_id(self, identifier: str) -> str:
        return str(uuid.uuid5(_POINT_NAMESPACE, f"{self._collection_name}:{identifier}"))

    @staticmethod
    def _build_filter(filters: Mapping[str, str] | None) -> models.Filter | None:
        if not filters:
            return None
        conditions: list[models.Condition] = []
        for key, value in filters.items():
            normalized_key = key if key in _RESERVED_PAYLOAD_KEYS else f"metadata.{key}"
            conditions.append(
                models.FieldCondition(
                    key=normalized_key,
                    match=models.MatchValue(value=value),
                )
            )
        return models.Filter(must=conditions)

    @staticmethod
    def _to_snippet(point: Any) -> KnowledgeSnippet:
        payload = point.payload
        if not isinstance(payload, dict):
            raise ValueError("Qdrant point is missing its knowledge payload")
        metadata = payload.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ValueError("Qdrant point contains invalid knowledge metadata")
        return KnowledgeSnippet(
            identifier=str(payload["identifier"]),
            content=str(payload["content"]),
            source=str(payload["source"]),
            score=float(point.score) if point.score is not None else None,
            metadata={str(key): str(value) for key, value in metadata.items()},
        )


QdrantVectorStoreAdapter = QdrantVectorStore
