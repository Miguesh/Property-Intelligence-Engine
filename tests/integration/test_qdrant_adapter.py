"""In-memory integration tests for the native async Qdrant adapter."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

qdrant_client = pytest.importorskip("qdrant_client")
from qdrant_client import AsyncQdrantClient  # noqa: E402

from property_intelligence.domain.models import KnowledgeSnippet, Listing, Location  # noqa: E402
from property_intelligence.infrastructure.ai import (  # noqa: E402
    DeterministicHashEmbeddingAdapter,
)
from property_intelligence.infrastructure.knowledge import (  # noqa: E402
    QdrantVectorStore,
    VectorKnowledgeRetriever,
    VectorStoreConfigurationError,
)


@pytest.fixture
async def client() -> AsyncIterator[AsyncQdrantClient]:
    qdrant = AsyncQdrantClient(location=":memory:")
    try:
        yield qdrant
    finally:
        await qdrant.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_qdrant_upsert_search_and_metadata_filter(
    client: AsyncQdrantClient,
) -> None:
    store = QdrantVectorStore(
        client=client,
        collection_name="adapter_test",
        vector_size=3,
    )
    snippets = (
        KnowledgeSnippet(
            identifier="wifi",
            content="Describe verified Wi-Fi details.",
            source="test",
            metadata={"category": "amenity"},
        ),
        KnowledgeSnippet(
            identifier="title",
            content="Lead the title with the strongest verified feature.",
            source="test",
            metadata={"category": "title"},
        ),
    )
    await store.upsert(snippets, ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)))

    all_results = await store.search((0.99, 0.01, 0.0), limit=2)
    filtered_results = await store.search(
        (0.99, 0.01, 0.0),
        limit=2,
        filters={"category": "title"},
    )

    assert [result.identifier for result in all_results] == ["wifi", "title"]
    assert [result.identifier for result in filtered_results] == ["title"]
    assert await store.is_ready() is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_vector_retriever_composes_key_free_adapters(
    client: AsyncQdrantClient,
) -> None:
    embeddings = DeterministicHashEmbeddingAdapter(dimensions=64)
    store = QdrantVectorStore(
        client=client,
        collection_name="retriever_test",
        vector_size=64,
    )
    snippets = (
        KnowledgeSnippet(
            identifier="wifi-workspace",
            content="Mention verified fast Wi-Fi and a dedicated workspace for remote work.",
            source="test",
        ),
        KnowledgeSnippet(
            identifier="parking",
            content="Clarify whether parking is reserved, paid, shared, or street-based.",
            source="test",
        ),
    )
    vectors = await embeddings.embed_documents([snippet.content for snippet in snippets])
    await store.upsert(snippets, vectors)
    retriever = VectorKnowledgeRetriever(embeddings, store)
    listing = Listing(
        title="Loft with fast Wi-Fi and workspace",
        description="A downtown loft designed for remote work.",
        amenities=("Wi-Fi", "Dedicated workspace"),
        property_type="loft",
        location=Location(city="Austin", country="United States"),
    )

    results = await retriever.retrieve(listing, limit=1)

    assert results[0].identifier == "wifi-workspace"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_qdrant_persists_and_validates_collection_compatibility_metadata(
    client: AsyncQdrantClient,
) -> None:
    manifest = {
        "pie_manifest_schema": "property-intelligence-qdrant-manifest/v1",
        "embedding_provider": "openai",
        "embedding_model": "text-embedding-test",
        "embedding_dimensions": 3,
        "corpus_schema_version": "1.0",
        "corpus_id": "test-guidance",
        "corpus_version": "1.2.0",
    }
    store = QdrantVectorStore(
        client=client,
        collection_name="manifest_test",
        vector_size=3,
        expected_metadata=manifest,
    )

    await store.initialize()

    collection = await client.get_collection("manifest_test")
    assert collection.config.metadata == manifest
    matching_store = QdrantVectorStore(
        client=client,
        collection_name="manifest_test",
        vector_size=3,
        expected_metadata=manifest,
    )
    await matching_store.initialize()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("existing_metadata", "message"),
    [
        ({}, "missing 'embedding_model'"),
        ({"embedding_model": "different-model"}, "does not match for 'embedding_model'"),
    ],
)
async def test_qdrant_rejects_missing_or_mismatched_compatibility_metadata(
    client: AsyncQdrantClient,
    existing_metadata: dict[str, str],
    message: str,
) -> None:
    await client.create_collection(
        collection_name="incompatible_manifest_test",
        vectors_config=qdrant_client.models.VectorParams(
            size=3,
            distance=qdrant_client.models.Distance.COSINE,
        ),
        metadata=existing_metadata,
    )
    store = QdrantVectorStore(
        client=client,
        collection_name="incompatible_manifest_test",
        vector_size=3,
        expected_metadata={"embedding_model": "expected-model"},
    )

    with pytest.raises(VectorStoreConfigurationError, match=message):
        await store.initialize()
