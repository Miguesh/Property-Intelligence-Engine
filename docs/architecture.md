# Architecture

## Decision summary

The system uses Clean Architecture so deterministic analysis, orchestration, and external
providers can evolve independently. FastAPI is a transport adapter; OpenAI/LangChain and Qdrant
are replaceable infrastructure; the domain remains usable as a Python library without either.

```text
HTTP request
    |
    v
interfaces/api  -- validates and maps transport data
    |
    v
application     -- orchestrates one use case through ports
    |
    v
domain          -- immutable models, normalization, deterministic scoring

infrastructure  -- implements generation, embedding, retrieval, and vector ports
    ^
    |
bootstrap.py    -- selects and wires concrete adapters
```

## Layers and dependency rules

| Layer | Owns | May depend on | Must not depend on |
|---|---|---|---|
| `domain` | Listings, scores, analysis rules, normalization | Python standard library | FastAPI, Pydantic, LangChain, OpenAI, Qdrant, outer layers |
| `application` | Use cases, provider protocols, application failures | Domain | Interfaces, infrastructure, provider SDKs |
| `infrastructure` | OpenAI/LangChain, embeddings, Qdrant, corpus adapters, settings | Application and domain | Interfaces/routes |
| `interfaces` | Pydantic HTTP schemas, auth, middleware, errors, routes | Application and domain mapping | Provider SDKs and concrete infrastructure behavior |
| `bootstrap.py` | Process composition, lifecycle, middleware registration | All layers | Business rules |

`tests/architecture/test_dependency_rules.py` checks that inner layers do not import framework or
provider packages and that routes do not call provider SDKs.

## Request lifecycle

1. Middleware validates the request size, establishes a correlation ID, and adds security headers.
2. The route applies optional bearer authentication and validates a strict Pydantic request.
3. The transport schema maps to immutable domain objects.
4. `AnalyzeListingUseCase` runs the deterministic domain engine.
5. The use case retrieves relevant editorial guidance through `KnowledgeRetrieverPort`.
6. It passes listing facts, deterministic evidence, and guidance to `TextGenerationPort`.
7. Optional provider failures use configured fallback adapters; required failures become a stable
   `503` response.
8. The route maps the domain result to the versioned response schema.

Neither the route nor the LLM decides numerical scores. The LLM receives those scores as evidence
for editing copy.

## Ports and adapters

The application defines four protocols:

- `TextGenerationPort`: creates titles, descriptions, and tags.
- `KnowledgeRetrieverPort`: supplies relevant editorial guidance.
- `EmbeddingPort`: embeds documents and queries.
- `VectorStorePort`: stores and searches provider-neutral vectors.

Production adapters currently include LangChain/OpenAI generation, OpenAI embeddings, native
async Qdrant, static lexical retrieval, deterministic generation, and deterministic hash
embeddings for tests/smoke checks. Tests inject fakes at these protocols without patching a route.

## Runtime composition and degradation

`bootstrap.py` is the single composition root. With no OpenAI key, it selects deterministic copy
generation and static retrieval. With a key, it composes OpenAI generation and embeddings plus
Qdrant, retaining deterministic/static adapters as fallbacks unless the corresponding provider is
configured as required.

This behavior keeps domain analysis available during provider outages while making degradation
visible through `generation_source`, `warnings`, `knowledge_references`, logs, and readiness
component labels.

## Adding or replacing a provider

1. Implement the relevant application protocol under `infrastructure/`.
2. Translate provider errors into application-safe behavior; never leak SDK exceptions or payloads.
3. Add adapter contract tests with an injected fake client.
4. Select the adapter only in `bootstrap.py`, controlled by validated settings.
5. Document configuration, operations, privacy, and fallback behavior.

No domain, use-case, or route change should be required merely to replace a provider.

## Architectural decisions

The rationale and tradeoffs are recorded in [the ADR index](adr/README.md). A new ADR is expected
when changing score ownership, provider abstraction, vector-client concurrency, or API execution
semantics.
