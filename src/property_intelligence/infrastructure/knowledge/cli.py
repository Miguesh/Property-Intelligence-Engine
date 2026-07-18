"""Idempotent command-line ingestion for the guidance vector collection."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from pathlib import Path

from qdrant_client import AsyncQdrantClient

from property_intelligence.application.ports import EmbeddingPort
from property_intelligence.domain.models import KnowledgeSnippet
from property_intelligence.infrastructure.ai.embeddings import (
    DeterministicHashEmbeddingAdapter,
    OpenAIEmbeddingAdapter,
)
from property_intelligence.infrastructure.config import Settings, get_settings
from property_intelligence.infrastructure.knowledge.corpus import (
    build_collection_compatibility_manifest,
    load_guidance_corpus,
)
from property_intelligence.infrastructure.knowledge.qdrant import QdrantVectorStore


async def ingest_guidance(
    snippets: Sequence[KnowledgeSnippet],
    *,
    embeddings: EmbeddingPort,
    vector_store: QdrantVectorStore,
    batch_size: int = 64,
) -> int:
    """Embed and idempotently upsert a complete guidance corpus."""

    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    await vector_store.initialize()
    ingested = 0
    for offset in range(0, len(snippets), batch_size):
        batch = tuple(snippets[offset : offset + batch_size])
        vectors = await embeddings.embed_documents([snippet.content for snippet in batch])
        await vector_store.upsert(batch, vectors)
        ingested += len(batch)
    return ingested


def build_parser(settings: Settings) -> argparse.ArgumentParser:
    """Build the CLI parser using environment-backed runtime defaults."""

    parser = argparse.ArgumentParser(
        prog="pie-ingest",
        description="Embed and upsert the versioned listing-guidance corpus.",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help="Guidance JSON path (default: the corpus bundled in the installed package)",
    )
    parser.add_argument("--qdrant-url", default=settings.qdrant_url)
    parser.add_argument("--collection", default=settings.qdrant_collection)
    parser.add_argument("--embedding-model", default=settings.openai_embedding_model)
    parser.add_argument("--dimensions", type=int, default=settings.embedding_dimensions)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument(
        "--deterministic",
        action="store_true",
        help="Use stable local hash embeddings for a key-free development smoke test.",
    )
    return parser


async def _run(args: argparse.Namespace, settings: Settings) -> int:
    corpus = load_guidance_corpus(args.source)
    snippets = corpus.to_snippets()

    if args.dimensions <= 0:
        raise ValueError("--dimensions must be positive")
    if args.batch_size <= 0:
        raise ValueError("--batch-size must be positive")

    embeddings: EmbeddingPort
    if args.deterministic:
        embeddings = DeterministicHashEmbeddingAdapter(dimensions=args.dimensions)
        embedding_provider = "property-intelligence"
        embedding_model = "deterministic-hash-v1"
    else:
        api_key = settings.openai_key_value
        if not api_key:
            raise ValueError("PIE_OPENAI_API_KEY is required unless --deterministic is selected")
        embeddings = OpenAIEmbeddingAdapter(
            api_key=api_key,
            model=args.embedding_model,
            dimensions=args.dimensions,
            timeout_seconds=min(settings.llm_timeout_seconds, 60.0),
            max_retries=settings.llm_max_retries,
        )
        embedding_provider = "openai"
        embedding_model = args.embedding_model

    if args.qdrant_url == ":memory:":
        client = AsyncQdrantClient(location=":memory:")
    else:
        client = AsyncQdrantClient(
            url=args.qdrant_url,
            api_key=settings.qdrant_key_value,
            timeout=settings.qdrant_timeout_seconds,
            prefer_grpc=False,
        )
    vector_store = QdrantVectorStore(
        client=client,
        collection_name=args.collection,
        vector_size=args.dimensions,
        operation_timeout_seconds=settings.qdrant_timeout_seconds,
        expected_metadata=build_collection_compatibility_manifest(
            corpus,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
            embedding_dimensions=args.dimensions,
        ),
    )

    try:
        return await ingest_guidance(
            snippets,
            embeddings=embeddings,
            vector_store=vector_store,
            batch_size=args.batch_size,
        )
    finally:
        await client.close()


def main() -> None:
    """Run corpus ingestion and return a shell-friendly failure message."""

    settings = get_settings()
    parser = build_parser(settings)
    args = parser.parse_args()
    try:
        ingested = asyncio.run(_run(args, settings))
    except (FileNotFoundError, ValueError) as exc:
        parser.exit(status=2, message=f"configuration error: {exc}\n")
    except Exception:
        parser.exit(
            status=1,
            message="ingestion failed; check OpenAI and Qdrant connectivity\n",
        )
    print(
        f"Ingested {ingested} guidance documents into "
        f"{args.collection!r} from {args.source or 'the bundled corpus'}."
    )


if __name__ == "__main__":
    main()
