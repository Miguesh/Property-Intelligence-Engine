# Testing and evaluation

## Test strategy

The standard suite is deterministic, key-free, and network-independent. It validates domain rules,
use-case fallback behavior, Pydantic contracts, adapters with injected clients, native Qdrant with
an in-memory client, the assembled FastAPI application, and Clean Architecture import rules.

No standard command should spend OpenAI credits or require an externally running Qdrant instance.

## Local checks

After the locked development install described in [Contributing](../CONTRIBUTING.md), run:

```bash
ruff format --check .
ruff check .
mypy
pytest -m "not live" --cov=property_intelligence --cov-report=term-missing
```

Useful narrower commands:

```bash
pytest tests/unit
pytest tests/architecture
pytest tests/integration -m integration
pytest tests/integration/test_app_smoke.py
```

Coverage is branch-aware and has an 85% minimum when collected. CI runs the non-live suite on
Python 3.12 and 3.13 with LLM and vector adapters disabled through environment settings.

## What each layer proves

| Suite | Purpose |
|---|---|
| `tests/unit/test_analysis_engine.py` | Score bounds/weights, determinism, aliases, negation, missing amenities, short-copy caps, anti-inflation, audience relevance |
| `tests/unit/test_use_cases.py` | Retrieval/generation orchestration, evidence passing, optional fallback, required-provider failure |
| `tests/unit/test_ai_adapters.py` | Structured generation parsing, prompt metadata, fact-only deterministic output, embedding validation, bundled corpus retrieval |
| `tests/unit/test_schemas.py` | Strict request and response mapping behavior |
| `tests/unit/test_config.py` | Safe defaults and production/required-mode invariants |
| `tests/integration/test_api.py` | Public response, validation envelope, auth boundary, health routes |
| `tests/integration/test_qdrant_adapter.py` | Async upsert/search/filter behavior through in-memory Qdrant |
| `tests/integration/test_app_smoke.py` | Full key-free composed application |
| `tests/architecture/` | Dependency direction and absence of provider calls in routes |

## Evaluation beyond correctness tests

Automated correctness is necessary but not enough for content quality. Maintain a versioned,
privacy-safe evaluation set spanning:

- sparse, average, and information-rich listings;
- apartments, houses, rooms, studios, villas, cabins, and unknown property types;
- duplicated amenities, aliases, negated amenities, all-caps/keyword spam, and long/short copy;
- multiple regions and supported English locale tags;
- family, business, accessibility, safety, and longer-stay claims;
- direct/indirect prompt injection and instructions embedded in retrieved guidance;
- provider timeout, invalid structured output, empty collection, and Qdrant outage cases.

Expert reviewers should label factual consistency, usefulness, actionability, tone, non-
discrimination, title uniqueness, and tag relevance. Score-methodology changes should report
distributions and regressions against those labels; prompt/model changes should compare factuality
and editorial quality before rollout.

## Final OpenAI/Qdrant validation

External validation is intentionally left for the final environment because it needs a real API
key, model access, provider quota, and a running/persistent Qdrant service. It is a manual smoke
check unless a separately marked `live` test is added.

1. Start Qdrant and export/inject `PIE_OPENAI_API_KEY` without echoing it.
2. Confirm `PIE_OPENAI_MODEL`, `PIE_OPENAI_EMBEDDING_MODEL`, dimensions, and collection name.
3. Ingest the versioned corpus with `pie-ingest`.
4. Start the API with both providers optional first.
5. Check readiness for `openai_configured:<model>` and `qdrant_ready`.
6. Submit `examples/listing_request.json`.
7. Verify `generation_source` starts with `openai:`, `prompt_version` is expected, knowledge
   references are populated, warnings are empty, and all generated claims are traceable to input.
8. Stop Qdrant and repeat: optional mode should return static references plus a warning rather than
   lose deterministic scores.
9. Restore Qdrant, simulate an invalid/unavailable generation provider, and verify deterministic
   generation plus a warning.
10. In an isolated process, enable each required flag and verify the corresponding outage fails
    closed with startup failure or `503`.
11. Inspect correlated logs/Sentry for metadata only and verify no body, key, or provider payload is
    present.

Do not commit live outputs: model wording can vary and listing text may be sensitive. Record the
revision, environment, model IDs, corpus version, collection name, and pass/fail findings in the
release evidence instead.

## Adding live tests later

Use `@pytest.mark.live`, skip when the explicit credential is absent, bound time and spend, and run
only from an approved workflow. A live test must not be part of `pytest -m "not live"`. It should
assert the stable structured contract and factual constraints, not exact prose.
