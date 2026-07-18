# ADR 0003: Use the native async Qdrant client

- Status: Accepted
- Date: 2026-07-18

## Context

FastAPI routes and application ports are asynchronous. Retrieval must initialize collections,
upsert a versioned corpus, query vectors with metadata filters, validate dimensions/distance, and
close clients cleanly. A synchronous client would block workers or require a thread-pool wrapper.

## Decision

Implement `VectorStorePort` with `AsyncQdrantClient` directly. Use unnamed dense cosine vectors,
stable UUID point IDs, payload metadata, an initialization lock, bounded operation timeouts, and
explicit collection compatibility checks. Keep LangChain out of the vector-store contract; it is
used only where helpful for OpenAI model/embedding adapters.

## Consequences

- Retrieval and ingestion stay non-blocking end to end.
- Collection creation is safe against concurrent initialization by replicas.
- Dimension/distance mismatches fail early rather than corrupt relevance silently.
- The adapter can expose the provider-neutral filter behavior needed by the application.
- Qdrant API changes are owned by one adapter, but that adapter requires focused integration tests.
- Stable upserts do not automatically delete retired corpus identifiers; versioned collection
  rollout remains an operational responsibility.

## Alternatives considered

- Synchronous Qdrant client: rejected because it can block async request execution.
- LangChain vector-store wrapper as the core adapter: rejected because native lifecycle,
  validation, payload, and error behavior are clearer and more controllable directly.
- In-process-only vectors: retained for tests/static fallback but rejected as the production store
  because it lacks shared persistence and operational search capabilities.
