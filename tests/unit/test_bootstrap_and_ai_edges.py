"""Key-free edge tests for provider composition and AI adapter contracts."""

from __future__ import annotations

import math
from typing import Any, cast

import pytest
from pydantic import SecretStr, ValidationError

from property_intelligence.application.exceptions import (
    GenerationUnavailableError,
    RetrievalUnavailableError,
)
from property_intelligence.application.use_cases import AnalyzeListingUseCase
from property_intelligence.bootstrap import RuntimeContainer, _configure_sentry, build_container
from property_intelligence.infrastructure.ai.embeddings import (
    DeterministicHashEmbeddingAdapter,
    OpenAIEmbeddingAdapter,
)
from property_intelligence.infrastructure.ai.generator import LangChainListingGenerator
from property_intelligence.infrastructure.ai.schemas import ListingGenerationPayload
from property_intelligence.infrastructure.config import Settings


def _payload_values() -> dict[str, list[str]]:
    return {
        "titles": [
            "East Austin Loft with Workspace",
            "Sunny Austin Loft with Fast Wi-Fi",
            "Bright Loft Stay in East Austin",
        ],
        "descriptions": [
            "Stay in a bright East Austin loft with fast Wi-Fi and a dedicated workspace.",
            "Use this sunny loft as your Austin base, with a kitchen and quiet workspace.",
        ],
        "tags": [
            "Austin",
            "East Austin",
            "loft",
            "Wi-Fi",
            "workspace",
            "kitchen",
            "city stay",
            "remote work",
        ],
    }


class _LifecycleVectorStore:
    def __init__(self, *, initialize_error: Exception | None = None) -> None:
        self.initialize_error = initialize_error
        self.initialize_calls = 0
        self.close_calls = 0

    async def initialize(self) -> None:
        self.initialize_calls += 1
        if self.initialize_error is not None:
            raise self.initialize_error

    async def close(self) -> None:
        self.close_calls += 1


def _runtime_container(
    store: _LifecycleVectorStore | None,
) -> RuntimeContainer:
    return RuntimeContainer(
        analyze_listing=cast(AnalyzeListingUseCase, object()),
        component_status={},
        vector_store=cast(Any, store),
    )


@pytest.mark.asyncio
async def test_runtime_container_initializes_and_closes_vector_store() -> None:
    store = _LifecycleVectorStore()
    container = _runtime_container(store)

    await container.start(vector_required=True)
    await container.close()

    assert store.initialize_calls == 1
    assert store.close_calls == 1
    assert container.component_status["retrieval"] == "qdrant_ready"


@pytest.mark.asyncio
async def test_runtime_container_marks_optional_vector_startup_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = _LifecycleVectorStore(initialize_error=RuntimeError("connection details"))
    container = _runtime_container(store)

    await container.start(vector_required=False)

    assert container.component_status["retrieval"] == ("qdrant_unavailable_with_static_fallback")
    assert "qdrant_startup_unavailable" in caplog.text


@pytest.mark.asyncio
async def test_runtime_container_propagates_required_vector_startup_failure() -> None:
    failure = RuntimeError("connection details")
    container = _runtime_container(_LifecycleVectorStore(initialize_error=failure))

    with pytest.raises(RuntimeError) as captured:
        await container.start(vector_required=True)

    assert captured.value is failure


@pytest.mark.asyncio
async def test_runtime_container_without_vector_store_has_no_lifecycle_work() -> None:
    container = _runtime_container(None)

    await container.start(vector_required=False)
    await container.close()

    assert container.component_status == {}


class _FakeLangChainGenerator:
    created_with: dict[str, Any] | None = None

    def __init__(self, **kwargs: Any) -> None:
        type(self).created_with = kwargs


class _FakeEmbeddingAdapter:
    created_with: dict[str, Any] | None = None

    def __init__(self, **kwargs: Any) -> None:
        type(self).created_with = kwargs


class _FakeQdrantStore:
    created_with: dict[str, Any] | None = None
    instance: _FakeQdrantStore | None = None

    @classmethod
    def from_url(cls, **kwargs: Any) -> _FakeQdrantStore:
        cls.created_with = kwargs
        cls.instance = cls()
        return cls.instance


class _FakeVectorRetriever:
    created_with: tuple[object, object] | None = None

    def __init__(self, embeddings: object, vector_store: object) -> None:
        type(self).created_with = (embeddings, vector_store)


def test_build_container_composes_configured_provider_adapters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import property_intelligence.bootstrap as bootstrap

    monkeypatch.setattr(bootstrap, "LangChainListingGenerator", _FakeLangChainGenerator)
    monkeypatch.setattr(bootstrap, "OpenAIEmbeddingAdapter", _FakeEmbeddingAdapter)
    monkeypatch.setattr(bootstrap, "QdrantVectorStore", _FakeQdrantStore)
    monkeypatch.setattr(bootstrap, "VectorKnowledgeRetriever", _FakeVectorRetriever)
    settings = Settings(
        openai_api_key=SecretStr("test-openai-key"),
        openai_model="test-generation-model",
        openai_embedding_model="test-embedding-model",
        embedding_dimensions=256,
        qdrant_url="http://vector.test:6333",
        qdrant_api_key=SecretStr("test-qdrant-key"),
        qdrant_collection="test-guidance",
        qdrant_timeout_seconds=7,
        retrieval_limit=4,
    )

    container = build_container(settings)

    assert container.vector_store is _FakeQdrantStore.instance
    assert container.component_status == {
        "generation": "openai_configured:test-generation-model",
        "retrieval": "qdrant_configured",
    }
    assert _FakeLangChainGenerator.created_with == {
        "api_key": "test-openai-key",
        "model": "test-generation-model",
        "timeout_seconds": 45.0,
        "max_retries": 2,
    }
    assert _FakeEmbeddingAdapter.created_with == {
        "api_key": "test-openai-key",
        "model": "test-embedding-model",
        "dimensions": 256,
        "timeout_seconds": 30,
        "max_retries": 2,
    }
    assert _FakeQdrantStore.created_with == {
        "url": "http://vector.test:6333",
        "collection_name": "test-guidance",
        "vector_size": 256,
        "api_key": "test-qdrant-key",
        "timeout_seconds": 7,
        "expected_metadata": {
            "pie_manifest_schema": "property-intelligence-qdrant-manifest/v1",
            "embedding_provider": "openai",
            "embedding_model": "test-embedding-model",
            "embedding_dimensions": 256,
            "corpus_schema_version": "1.0",
            "corpus_id": "property-intelligence-listing-guidance",
            "corpus_version": "1.0.0",
        },
    }
    assert _FakeVectorRetriever.created_with is not None
    assert _FakeVectorRetriever.created_with[1] is container.vector_store


@pytest.mark.parametrize(
    ("settings", "generation_status", "retrieval_status"),
    [
        (
            Settings(llm_enabled=False, vector_store_enabled=False),
            "disabled_deterministic",
            "disabled_static",
        ),
        (
            Settings(llm_enabled=True, vector_store_enabled=True),
            "deterministic_no_key",
            "static_no_embedding_key",
        ),
    ],
)
def test_build_container_reports_key_free_provider_modes(
    settings: Settings,
    generation_status: str,
    retrieval_status: str,
) -> None:
    container = build_container(settings)

    assert container.vector_store is None
    assert container.component_status == {
        "generation": generation_status,
        "retrieval": retrieval_status,
    }


def test_sentry_configuration_excludes_request_bodies_and_local_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def record_init(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr("property_intelligence.bootstrap.sentry_sdk.init", record_init)
    settings = Settings(
        environment="staging",
        app_version="1.2.3",
        sentry_dsn=SecretStr("https://public@example.invalid/1"),
        sentry_traces_sample_rate=0.25,
    )

    _configure_sentry(settings)

    assert captured["send_default_pii"] is False
    assert captured["max_request_body_size"] == "never"
    assert captured["include_local_variables"] is False
    assert captured["environment"] == "staging"
    assert captured["release"] == "property-intelligence-engine@1.2.3"


def test_sentry_configuration_is_disabled_without_a_dsn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def record_init(**_kwargs: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr("property_intelligence.bootstrap.sentry_sdk.init", record_init)

    _configure_sentry(Settings(sentry_dsn=None))

    assert called is False


def test_generation_payload_normalizes_whitespace() -> None:
    values = _payload_values()
    values["titles"][0] = "  East Austin Loft with Workspace  "

    payload = ListingGenerationPayload.model_validate(values)

    assert payload.titles[0] == "East Austin Loft with Workspace"


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("titles", ["same", "SAME", "different"]),
        ("descriptions", ["  ", "valid"]),
        ("tags", ["tag"] * 8),
    ],
)
def test_generation_payload_rejects_blank_or_duplicate_values(
    field: str,
    replacement: list[str],
) -> None:
    values = _payload_values()
    values[field] = replacement

    with pytest.raises(ValidationError, match="generated values"):
        ListingGenerationPayload.model_validate(values)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("titles", ["one", "two"]),
        ("descriptions", ["one"]),
        ("tags", [str(index) for index in range(7)]),
        ("titles", ["x" * 81, "two", "three"]),
        ("descriptions", ["x" * 2_001, "two"]),
        ("tags", ["x" * 51, *[str(index) for index in range(7)]]),
    ],
)
def test_generation_payload_rejects_cardinality_and_length_violations(
    field: str,
    replacement: list[str],
) -> None:
    values = _payload_values()
    values[field] = replacement

    with pytest.raises(ValidationError):
        ListingGenerationPayload.model_validate(values)


def test_generation_payload_forbids_unknown_fields() -> None:
    values: dict[str, object] = _payload_values()
    values["provider_notes"] = "must not enter the domain result"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ListingGenerationPayload.model_validate(values)


class _ResponseChain:
    def __init__(self, response: object = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error

    async def ainvoke(self, _input: dict[str, Any], config: dict[str, Any] | None = None) -> object:
        del config
        if self.error is not None:
            raise self.error
        return self.response


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"timeout_seconds": 0}, "timeout_seconds must be positive"),
        ({"max_retries": -1}, "max_retries must not be negative"),
    ],
)
def test_langchain_generator_validates_runtime_bounds(
    kwargs: dict[str, int],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        LangChainListingGenerator(chain=cast(Any, _ResponseChain()), **kwargs)


def test_langchain_generator_requires_key_without_injected_chain() -> None:
    with pytest.raises(ValueError, match="api_key is required"):
        LangChainListingGenerator()


@pytest.mark.parametrize(
    "response",
    [
        object(),
        {"parsed": None, "parsing_error": None},
        {"parsed": _payload_values(), "parsing_error": ValueError("bad output")},
        {"parsed": {"titles": []}, "parsing_error": None},
    ],
)
def test_langchain_generator_rejects_malformed_provider_responses(response: object) -> None:
    with pytest.raises(GenerationUnavailableError, match="invalid response"):
        LangChainListingGenerator._extract_payload(response)


@pytest.mark.asyncio
async def test_langchain_generator_hides_provider_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_failure = RuntimeError("provider payload must remain private")
    generator = LangChainListingGenerator(
        timeout_seconds=1,
        chain=cast(Any, _ResponseChain(error=provider_failure)),
    )
    monkeypatch.setattr(
        LangChainListingGenerator,
        "_prompt_input",
        staticmethod(lambda _request: {}),
    )

    with pytest.raises(GenerationUnavailableError, match="temporarily unavailable") as captured:
        await generator.generate(cast(Any, object()))

    assert captured.value.__cause__ is None
    assert "provider payload" not in str(captured.value)


class _EmbeddingClient:
    def __init__(
        self,
        *,
        documents: list[list[float]] | None = None,
        query: list[float] | None = None,
        documents_error: Exception | None = None,
        query_error: Exception | None = None,
    ) -> None:
        self.documents = documents if documents is not None else [[1.0, 0.0, 0.5]]
        self.query = query if query is not None else [1.0, 0.0, 0.5]
        self.documents_error = documents_error
        self.query_error = query_error
        self.document_calls = 0

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        del texts
        self.document_calls += 1
        if self.documents_error is not None:
            raise self.documents_error
        return self.documents

    async def aembed_query(self, text: str) -> list[float]:
        del text
        if self.query_error is not None:
            raise self.query_error
        return self.query


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"dimensions": 0}, "dimensions must be positive"),
        ({"timeout_seconds": 0}, "timeout_seconds must be positive"),
        ({"max_retries": -1}, "max_retries must not be negative"),
        ({"chunk_size": 0}, "chunk_size must be positive"),
    ],
)
def test_openai_embedding_adapter_validates_runtime_bounds(
    kwargs: dict[str, int],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        OpenAIEmbeddingAdapter(client=_EmbeddingClient(), **kwargs)


def test_openai_embedding_adapter_requires_key_without_injected_client() -> None:
    with pytest.raises(ValueError, match="api_key is required"):
        OpenAIEmbeddingAdapter()


@pytest.mark.asyncio
async def test_openai_embedding_adapter_handles_empty_and_blank_inputs() -> None:
    client = _EmbeddingClient()
    adapter = OpenAIEmbeddingAdapter(dimensions=3, client=client)

    assert await adapter.embed_documents([]) == ()
    assert client.document_calls == 0
    with pytest.raises(ValueError, match="documents.*blank"):
        await adapter.embed_documents(["valid", "  "])
    with pytest.raises(ValueError, match="query.*blank"):
        await adapter.embed_query("  ")


@pytest.mark.parametrize("operation", ["documents", "query"])
@pytest.mark.asyncio
async def test_openai_embedding_adapter_hides_provider_failures(operation: str) -> None:
    failure = RuntimeError("private provider detail")
    client = _EmbeddingClient(
        documents_error=failure if operation == "documents" else None,
        query_error=failure if operation == "query" else None,
    )
    adapter = OpenAIEmbeddingAdapter(dimensions=3, timeout_seconds=1, client=client)

    with pytest.raises(RetrievalUnavailableError, match="temporarily unavailable") as captured:
        if operation == "documents":
            await adapter.embed_documents(["listing guidance"])
        else:
            await adapter.embed_query("listing guidance")

    assert captured.value.__cause__ is None
    assert "private provider detail" not in str(captured.value)


@pytest.mark.parametrize(
    ("documents", "query", "operation", "message"),
    [
        ([], None, "documents", "unexpected number"),
        ([[1.0, 2.0]], None, "documents", "wrong dimensions"),
        (None, [1.0, 2.0], "query", "wrong dimensions"),
        (None, [1.0, math.inf, 0.5], "query", "non-finite"),
    ],
)
@pytest.mark.asyncio
async def test_openai_embedding_adapter_rejects_invalid_vectors(
    documents: list[list[float]] | None,
    query: list[float] | None,
    operation: str,
    message: str,
) -> None:
    client = _EmbeddingClient(documents=documents, query=query)
    adapter = OpenAIEmbeddingAdapter(dimensions=3, client=client)

    with pytest.raises(RetrievalUnavailableError, match=message):
        if operation == "documents":
            await adapter.embed_documents(["listing guidance"])
        else:
            await adapter.embed_query("listing guidance")


@pytest.mark.asyncio
async def test_openai_embedding_adapter_hides_non_numeric_vector_values() -> None:
    client = _EmbeddingClient(query=cast(Any, [1.0, "private-provider-value", 0.5]))
    adapter = OpenAIEmbeddingAdapter(dimensions=3, client=client)

    with pytest.raises(RetrievalUnavailableError, match="invalid numeric values") as captured:
        await adapter.embed_query("listing guidance")

    assert "private-provider-value" not in str(captured.value)


@pytest.mark.asyncio
async def test_deterministic_embeddings_are_normalized_and_blank_safe() -> None:
    adapter = DeterministicHashEmbeddingAdapter(dimensions=8)

    blank = await adapter.embed_query("...")
    vector = await adapter.embed_query("fast wifi workspace")

    assert blank == (0.0,) * 8
    assert math.isclose(math.sqrt(sum(value * value for value in vector)), 1.0)
    assert await adapter.embed_documents(["fast wifi workspace"]) == (vector,)


def test_deterministic_embedding_adapter_requires_positive_dimensions() -> None:
    with pytest.raises(ValueError, match="dimensions must be positive"):
        DeterministicHashEmbeddingAdapter(dimensions=0)
