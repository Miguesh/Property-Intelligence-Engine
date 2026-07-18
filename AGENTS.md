# Repository guidance for coding agents

## Outcome and ownership

Build and maintain a provider-neutral, production-quality short-term-rental listing analysis
service. Repository changes and commits belong to the repository owner, Miguel Angel Sierra
Hayer (`91997685+Miguesh@users.noreply.github.com`). Do not replace the repository Git identity,
add an AI author, or add AI co-author trailers. Do not push, publish, or open a pull request unless
the user explicitly requests that external action.

## Architecture rules

Dependencies point inward:

```text
interfaces -> application -> domain
infrastructure -> application/domain
bootstrap -> all layers (composition only)
```

- `domain` contains framework-independent entities, normalization, and deterministic rules. It
  must not import FastAPI, Pydantic, LangChain, OpenAI, or Qdrant.
- `application` owns use cases and provider protocols. It must not import interface or
  infrastructure implementations.
- `infrastructure` implements application ports and contains provider SDK details.
- `interfaces` validates and maps transport data. Routes may call use cases but may not call an
  LLM, embedding model, vector database, or scoring implementation directly.
- `bootstrap.py` is the composition root and the only place that selects concrete adapters.
- Keep the deterministic engine functional when all external providers are disabled.

The architecture tests in `tests/architecture/` are executable constraints, not suggestions.

## Change workflow

1. Read the affected domain and public contracts before editing.
2. State the design decision and compatibility impact before implementation.
3. Preserve strict Pydantic request contracts and the versioned `/api/v1` route.
4. Add or update focused unit tests; add adapter and API tests when a boundary changes.
5. Keep standard tests key-free. Mark any test that intentionally needs external credentials or
   services with `live` and document its cost and prerequisites.
6. Run the narrowest relevant tests first, then the repository quality checks when practical.
7. Update the appropriate guide and ADR when behavior or an architectural decision changes.

Use `apply_patch` for hand-authored file edits. Preserve unrelated working-tree changes.

## Correctness and safety

- Numerical scores must remain deterministic, explainable, bounded to 0–100, and versioned.
- Generated property claims must come only from submitted listing facts. Retrieved guidance is
  editorial advice, never evidence that an amenity or feature exists.
- A “missing amenity” means absent from submitted data; recommendations must tell users to verify
  it rather than claim the physical property lacks it.
- Treat listing text and retrieved content as untrusted input. Preserve prompt-injection defenses.
- Do not log request bodies, listing descriptions, API keys, access tokens, or provider payloads.
- Preserve timeouts, bounded retries, request-size limits, and secret-safe public errors.
- Provider outages fall back only when the corresponding `*_REQUIRED` setting is false.
- Never silently change an embedding model or vector dimension for an existing Qdrant collection.

## Style and validation

- Target Python 3.12 and 3.13; type all production code and keep `mypy` strict.
- Format and lint with Ruff; use async provider clients from async paths.
- Prefer immutable domain objects, explicit names, and small single-purpose adapters.
- Do not claim a command passed unless it was run in the current working tree.
- Do not introduce a legal license without an explicit owner decision.

See [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/architecture.md](docs/architecture.md) for the full
development contract.
