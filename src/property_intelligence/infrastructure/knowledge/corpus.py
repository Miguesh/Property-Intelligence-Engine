"""Loading and validation for the versioned listing-guidance corpus."""

from __future__ import annotations

from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from property_intelligence.domain.models import KnowledgeSnippet

CORPUS_FILENAME = "listing_guidance.v1.json"
COLLECTION_MANIFEST_SCHEMA = "property-intelligence-qdrant-manifest/v1"
DEFAULT_CORPUS_RESOURCE: Traversable = resources.files(__package__).joinpath(
    "data", CORPUS_FILENAME
)
# Backwards-compatible public name. It is a Traversable rather than a concrete
# filesystem Path so loading also works when the package is installed from a
# wheel or imported through a non-filesystem loader.
DEFAULT_CORPUS_PATH = DEFAULT_CORPUS_RESOURCE


class GuidanceDocument(BaseModel):
    """One validated record in the editorial guidance corpus."""

    model_config = ConfigDict(extra="forbid")

    identifier: str = Field(min_length=1)
    content: str = Field(min_length=1)
    source: str = Field(min_length=1)
    metadata: dict[str, str] = Field(default_factory=dict)


class GuidanceCorpus(BaseModel):
    """Versioned, independently loadable collection of guidance records."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    corpus_id: str = Field(min_length=1)
    corpus_version: str = Field(min_length=1)
    documents: list[GuidanceDocument] = Field(min_length=1)

    @model_validator(mode="after")
    def identifiers_must_be_unique(self) -> GuidanceCorpus:
        identifiers = [document.identifier for document in self.documents]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("guidance document identifiers must be unique")
        return self

    def to_snippets(self) -> tuple[KnowledgeSnippet, ...]:
        """Convert transport records to immutable domain objects."""

        return tuple(
            KnowledgeSnippet(
                identifier=document.identifier,
                content=document.content,
                source=document.source,
                metadata={
                    **document.metadata,
                    "corpus_id": self.corpus_id,
                    "corpus_version": self.corpus_version,
                },
            )
            for document in self.documents
        )


def build_collection_compatibility_manifest(
    corpus: GuidanceCorpus,
    *,
    embedding_provider: str,
    embedding_model: str,
    embedding_dimensions: int,
) -> dict[str, str | int]:
    """Describe the embedding/corpus contract persisted with a collection."""

    normalized_provider = embedding_provider.strip()
    normalized_model = embedding_model.strip()
    if not normalized_provider:
        raise ValueError("embedding_provider must not be blank")
    if not normalized_model:
        raise ValueError("embedding_model must not be blank")
    if embedding_dimensions <= 0:
        raise ValueError("embedding_dimensions must be positive")
    return {
        "pie_manifest_schema": COLLECTION_MANIFEST_SCHEMA,
        "embedding_provider": normalized_provider,
        "embedding_model": normalized_model,
        "embedding_dimensions": embedding_dimensions,
        "corpus_schema_version": corpus.schema_version,
        "corpus_id": corpus.corpus_id,
        "corpus_version": corpus.corpus_version,
    }


def load_guidance_corpus(path: str | Path | None = None) -> GuidanceCorpus:
    """Load a guidance corpus and fail fast on malformed source data."""

    corpus_source: Traversable = Path(path) if path is not None else DEFAULT_CORPUS_RESOURCE
    try:
        raw_content = corpus_source.read_text(encoding="utf-8")
    except OSError as exc:
        raise FileNotFoundError(f"guidance corpus could not be read: {corpus_source}") from exc

    corpus = GuidanceCorpus.model_validate_json(raw_content)
    if corpus.schema_version != "1.0":
        raise ValueError(f"unsupported guidance corpus schema: {corpus.schema_version}")
    return corpus
