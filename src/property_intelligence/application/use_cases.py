"""Application orchestration for listing analysis."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from uuid import uuid4

from property_intelligence.application.exceptions import (
    GenerationUnavailableError,
    RetrievalUnavailableError,
)
from property_intelligence.application.ports import (
    GeneratedContentValidatorPort,
    GenerationRequest,
    KnowledgeRetrieverPort,
    TextGenerationPort,
)
from property_intelligence.domain.analysis import ListingAnalysisEngine
from property_intelligence.domain.claim_validation import GeneratedContentClaimValidator
from property_intelligence.domain.models import (
    AnalysisResult,
    GeneratedContent,
    KnowledgeSnippet,
    Listing,
)

logger = logging.getLogger(__name__)


class AnalyzeListingUseCase:
    """Orchestrate deterministic evidence, retrieval, and copy generation."""

    def __init__(
        self,
        *,
        engine: ListingAnalysisEngine,
        generator: TextGenerationPort,
        retriever: KnowledgeRetrieverPort,
        fallback_generator: TextGenerationPort | None = None,
        fallback_retriever: KnowledgeRetrieverPort | None = None,
        claim_validator: GeneratedContentValidatorPort | None = None,
        generation_required: bool = False,
        retrieval_required: bool = False,
        retrieval_limit: int = 5,
    ) -> None:
        self._engine = engine
        self._generator = generator
        self._retriever = retriever
        self._fallback_generator = fallback_generator
        self._fallback_retriever = fallback_retriever
        self._claim_validator = (
            claim_validator if claim_validator is not None else GeneratedContentClaimValidator()
        )
        self._generation_required = generation_required
        self._retrieval_required = retrieval_required
        self._retrieval_limit = retrieval_limit

    async def execute(self, listing: Listing) -> AnalysisResult:
        """Return a complete listing analysis with graceful optional fallbacks."""

        deterministic = self._engine.analyze(listing)
        warnings = list(getattr(deterministic, "warnings", ()))
        knowledge = await self._retrieve(listing, warnings)
        generated = await self._generate(
            GenerationRequest(
                listing=listing,
                analysis=deterministic,
                knowledge=tuple(knowledge),
            ),
            warnings,
        )
        return AnalysisResult(
            analysis_id=str(uuid4()),
            listing_quality=deterministic.listing_quality,
            seo=deterministic.seo,
            readability=deterministic.readability,
            strengths=deterministic.strengths,
            weaknesses=deterministic.weaknesses,
            missing_amenities=deterministic.missing_amenities,
            improvements=deterministic.improvements,
            generated=generated,
            warnings=tuple(warnings),
            retrieved_knowledge=tuple(knowledge),
        )

    async def _retrieve(self, listing: Listing, warnings: list[str]) -> Sequence[KnowledgeSnippet]:
        try:
            return await self._retriever.retrieve(listing, limit=self._retrieval_limit)
        except Exception as exc:  # Provider errors must not cross the application boundary.
            logger.warning(
                "knowledge_retrieval_failed",
                extra={"error_type": type(exc).__name__},
            )
            if self._retrieval_required:
                raise RetrievalUnavailableError from None
            warnings.append(
                "Vector retrieval was unavailable; versioned built-in guidance was used."
            )
            if self._fallback_retriever is None:
                return ()
            try:
                return await self._fallback_retriever.retrieve(listing, limit=self._retrieval_limit)
            except Exception as fallback_exc:
                logger.warning(
                    "fallback_retrieval_failed",
                    extra={"error_type": type(fallback_exc).__name__},
                )
                return ()

    async def _generate(self, request: GenerationRequest, warnings: list[str]) -> GeneratedContent:
        try:
            generated = await self._generator.generate(request)
            self._claim_validator.validate(request.listing, generated)
            return generated
        except Exception as exc:  # Generation/validation details must not cross this boundary.
            logger.warning(
                "text_generation_failed",
                extra={"error_type": type(exc).__name__},
            )
            if self._generation_required:
                raise GenerationUnavailableError from None
            if self._fallback_generator is None:
                raise GenerationUnavailableError from None
            warnings.append(
                "LLM generation was unavailable or failed factuality validation; "
                "deterministic copy suggestions were returned."
            )
            try:
                generated = await self._fallback_generator.generate(request)
                self._claim_validator.validate(request.listing, generated)
                return generated
            except Exception as fallback_exc:
                logger.error(
                    "fallback_generation_failed",
                    extra={"error_type": type(fallback_exc).__name__},
                )
                raise GenerationUnavailableError from None
