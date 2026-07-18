# ADR 0002: Isolate providers behind application ports

- Status: Accepted
- Date: 2026-07-18

## Context

The service uses OpenAI, LangChain, embeddings, and a vector database today but must remain
independent and reusable. Direct SDK calls in routes or use cases would couple public behavior to
provider types, complicate key-free tests, and make replacement expensive.

## Decision

Define generation, retrieval, embedding, and vector-store protocols in the application layer.
Implement provider-specific adapters in infrastructure and select them only in the composition
root. Keep domain and application imports free of framework/provider SDKs. Translate failures at
the adapter/use-case boundary and provide deterministic/static implementations.

## Consequences

- Providers can be replaced without changing routes or domain rules.
- Tests inject fakes and run without credentials or networks.
- Optional fallbacks and required failure semantics are centrally orchestrated.
- Adapter contracts and mapping code add indirection and must be maintained.
- Provider-only capabilities cannot leak casually into the core; exposing one requires an explicit
  port/contract decision.

## Alternatives considered

- Provider SDKs in routes: rejected because it mixes transport and external orchestration.
- LangChain objects as application contracts: rejected because LangChain would become a core
  dependency rather than an adapter tool.
- A single generic provider interface: rejected because generation, embeddings, retrieval, and
  storage have different lifecycle and failure semantics.
