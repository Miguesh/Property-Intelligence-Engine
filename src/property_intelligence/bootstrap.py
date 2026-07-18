"""Composition root for the FastAPI application.

This is the only module that chooses concrete provider implementations. Inner
layers depend exclusively on domain objects and application ports.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from property_intelligence.application.ports import (
    KnowledgeRetrieverPort,
    TextGenerationPort,
)
from property_intelligence.application.use_cases import AnalyzeListingUseCase
from property_intelligence.domain.analysis import ListingAnalysisEngine
from property_intelligence.infrastructure.ai import (
    DeterministicListingGenerator,
    LangChainListingGenerator,
    OpenAIEmbeddingAdapter,
)
from property_intelligence.infrastructure.config import Settings, get_settings
from property_intelligence.infrastructure.knowledge import (
    QdrantVectorStore,
    StaticKnowledgeRetriever,
    VectorKnowledgeRetriever,
    build_collection_compatibility_manifest,
    load_guidance_corpus,
)
from property_intelligence.interfaces.api.errors import register_exception_handlers
from property_intelligence.interfaces.api.middleware import (
    RequestContextMiddleware,
    RequestSizeLimitMiddleware,
    configure_logging,
)
from property_intelligence.interfaces.api.routes import analysis_router, health_router

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RuntimeContainer:
    """Resources owned by one application process."""

    analyze_listing: AnalyzeListingUseCase
    component_status: dict[str, str]
    vector_store: QdrantVectorStore | None = None

    async def start(self, *, vector_required: bool) -> None:
        """Warm infrastructure that has an explicit startup lifecycle."""

        if self.vector_store is None:
            return
        try:
            await self.vector_store.initialize()
            self.component_status["retrieval"] = "qdrant_ready"
        except Exception as exc:
            if vector_required:
                raise
            logger.warning(
                "qdrant_startup_unavailable",
                extra={"error_type": type(exc).__name__},
            )
            self.component_status["retrieval"] = "qdrant_unavailable_with_static_fallback"

    async def close(self) -> None:
        """Release owned provider clients."""

        if self.vector_store is not None:
            await self.vector_store.close()


def build_container(settings: Settings) -> RuntimeContainer:
    """Select concrete adapters from validated settings."""

    engine = ListingAnalysisEngine()
    deterministic_generator = DeterministicListingGenerator()
    guidance_corpus = load_guidance_corpus()
    static_retriever = StaticKnowledgeRetriever(guidance_corpus.to_snippets())
    component_status: dict[str, str] = {}

    openai_key = settings.openai_key_value
    if settings.llm_enabled and openai_key:
        generator: TextGenerationPort = LangChainListingGenerator(
            api_key=openai_key,
            model=settings.openai_model,
            timeout_seconds=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )
        fallback_generator: TextGenerationPort | None = deterministic_generator
        component_status["generation"] = f"openai_configured:{settings.openai_model}"
    else:
        generator = deterministic_generator
        fallback_generator = None
        component_status["generation"] = (
            "disabled_deterministic" if not settings.llm_enabled else "deterministic_no_key"
        )

    vector_store: QdrantVectorStore | None = None
    if settings.vector_store_enabled and openai_key:
        embeddings = OpenAIEmbeddingAdapter(
            api_key=openai_key,
            model=settings.openai_embedding_model,
            dimensions=settings.embedding_dimensions,
            timeout_seconds=min(settings.llm_timeout_seconds, 30),
            max_retries=settings.llm_max_retries,
        )
        vector_store = QdrantVectorStore.from_url(
            url=settings.qdrant_url,
            collection_name=settings.qdrant_collection,
            vector_size=settings.embedding_dimensions,
            api_key=settings.qdrant_key_value,
            timeout_seconds=settings.qdrant_timeout_seconds,
            expected_metadata=build_collection_compatibility_manifest(
                guidance_corpus,
                embedding_provider="openai",
                embedding_model=settings.openai_embedding_model,
                embedding_dimensions=settings.embedding_dimensions,
            ),
        )
        retriever: KnowledgeRetrieverPort = VectorKnowledgeRetriever(embeddings, vector_store)
        fallback_retriever: KnowledgeRetrieverPort | None = static_retriever
        component_status["retrieval"] = "qdrant_configured"
    else:
        retriever = static_retriever
        fallback_retriever = None
        component_status["retrieval"] = (
            "disabled_static" if not settings.vector_store_enabled else "static_no_embedding_key"
        )

    use_case = AnalyzeListingUseCase(
        engine=engine,
        generator=generator,
        retriever=retriever,
        fallback_generator=fallback_generator,
        fallback_retriever=fallback_retriever,
        generation_required=settings.llm_required,
        retrieval_required=settings.vector_store_required,
        retrieval_limit=settings.retrieval_limit,
    )
    return RuntimeContainer(
        analyze_listing=use_case,
        component_status=component_status,
        vector_store=vector_store,
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create a fully composed FastAPI application."""

    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level, json_logs=resolved_settings.log_json)
    _configure_sentry(resolved_settings)
    container = build_container(resolved_settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await container.start(vector_required=resolved_settings.vector_store_required)
        try:
            yield
        finally:
            await container.close()

    docs_url = "/docs" if resolved_settings.docs_enabled else None
    openapi_url = "/openapi.json" if resolved_settings.docs_enabled else None
    redoc_url = "/redoc" if resolved_settings.docs_enabled else None
    application = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        description=(
            "Analyze short-term rental listing quality, discoverability, readability, "
            "amenity coverage, and improved copy."
        ),
        docs_url=docs_url,
        openapi_url=openapi_url,
        redoc_url=redoc_url,
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.analyze_listing_use_case = container.analyze_listing
    application.state.component_status = container.component_status

    application.add_middleware(
        RequestSizeLimitMiddleware,
        max_bytes=resolved_settings.max_request_bytes,
    )
    if resolved_settings.cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=resolved_settings.cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        )
    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=resolved_settings.allowed_hosts,
    )
    application.add_middleware(RequestContextMiddleware)

    application.include_router(health_router)
    application.include_router(analysis_router, prefix=resolved_settings.api_prefix)
    register_exception_handlers(application)
    return application


def _configure_sentry(settings: Settings) -> None:
    if settings.sentry_dsn is None or not settings.sentry_dsn.get_secret_value():
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn.get_secret_value(),
        environment=settings.environment,
        release=f"property-intelligence-engine@{settings.app_version}",
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
        max_request_body_size="never",
        include_local_variables=False,
    )


app = create_app()
