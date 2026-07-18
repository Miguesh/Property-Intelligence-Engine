"""Static and vector-backed listing guidance adapters."""

from property_intelligence.infrastructure.knowledge.corpus import (
    COLLECTION_MANIFEST_SCHEMA,
    DEFAULT_CORPUS_PATH,
    DEFAULT_CORPUS_RESOURCE,
    GuidanceCorpus,
    GuidanceDocument,
    build_collection_compatibility_manifest,
    load_guidance_corpus,
)
from property_intelligence.infrastructure.knowledge.qdrant import (
    QdrantVectorStore,
    QdrantVectorStoreAdapter,
    VectorStoreConfigurationError,
)
from property_intelligence.infrastructure.knowledge.retriever import VectorKnowledgeRetriever
from property_intelligence.infrastructure.knowledge.static import StaticKnowledgeRetriever

__all__ = [
    "DEFAULT_CORPUS_PATH",
    "DEFAULT_CORPUS_RESOURCE",
    "COLLECTION_MANIFEST_SCHEMA",
    "GuidanceCorpus",
    "GuidanceDocument",
    "build_collection_compatibility_manifest",
    "QdrantVectorStore",
    "QdrantVectorStoreAdapter",
    "StaticKnowledgeRetriever",
    "VectorKnowledgeRetriever",
    "VectorStoreConfigurationError",
    "load_guidance_corpus",
]
