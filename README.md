# Property Intelligence Engine

Property Intelligence Engine is a reusable FastAPI service that analyzes short-term-rental
listing content and returns explainable quality, SEO, and readability scores alongside
prioritized recommendations and improved copy.

The engine is useful without external services. Numerical scoring is always deterministic;
when no OpenAI key is configured, copy generation uses a fact-preserving local generator and
retrieval uses the bundled, versioned guidance corpus. OpenAI and Qdrant become active only
when their prerequisites are configured.

## What it returns

- Listing quality, SEO, and readability scores from 0 to 100, each with weighted evidence
- Strengths, weaknesses, and prioritized improvements
- Amenities that are not represented in the submitted listing and should be verified
- Three improved titles, two improved descriptions, and 8–12 tags
- Generation provenance, prompt version, retrieved guidance references, and fallback warnings

The SEO score measures content-discoverability signals; it does **not** predict or guarantee
ranking on Airbnb, Vrbo, Google, or another marketplace. See [Scoring](docs/scoring.md).

## Quick start: local, no API key

Prerequisites: Python 3.12 or 3.13.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --requirement requirements-dev.lock
python -m pip install --no-deps --editable .
Copy-Item .env.example .env
uvicorn property_intelligence.bootstrap:app --reload
```

On macOS or Linux, activate with `source .venv/bin/activate` and copy the environment file with
`cp .env.example .env`.

In another terminal:

```bash
curl -X POST http://localhost:8000/api/v1/analyses \
  -H "Content-Type: application/json" \
  --data @examples/listing_request.json
```

PowerShell users can substitute `curl.exe` for `curl`. Interactive OpenAPI documentation is at
`http://localhost:8000/docs` in the default local configuration.

No key is required for this flow. With `PIE_OPENAI_API_KEY` absent, `generation_source` is
`deterministic`, retrieval is local, and the response still contains every documented field.

## Quick start: Docker

Prerequisites: Docker Engine with Docker Compose.

```powershell
Copy-Item .env.example .env
docker compose up --build -d
docker compose ps
```

On macOS or Linux, use `cp .env.example .env`. The Compose stack starts the API and Qdrant, but
the API remains key-free until credentials are supplied. Inspect its public health endpoints:

```bash
curl http://localhost:8000/health/live
curl http://localhost:8000/health/ready
```

Stop the stack with `docker compose down`. This preserves the named Qdrant volume. See
[Operations](docs/operations.md) before deleting data or deploying to production.

## Optional OpenAI and vector retrieval

Set `PIE_OPENAI_API_KEY` in `.env` to activate OpenAI structured generation and OpenAI
embeddings. Populate Qdrant with the same embedding model and dimensions used by the API:

```bash
docker compose exec api pie-ingest
```

LLM and vector services are optional by default. If a configured provider fails, the service
falls back to deterministic generation or static retrieval and records a warning. Set
`PIE_LLM_REQUIRED=true` and/or `PIE_VECTOR_STORE_REQUIRED=true` only when the deployment should
fail closed instead. Full details are in [AI and retrieval](docs/ai-and-retrieval.md).

## Quality checks

The default suite is deliberately key-free and does not make billable provider calls:

```bash
ruff format --check .
ruff check .
mypy
pytest -m "not live" --cov=property_intelligence --cov-report=term-missing
```

See [Testing and evaluation](docs/testing-and-evaluation.md) for test boundaries and the final
external-provider validation checklist.

## Documentation

- [Architecture and dependency rules](docs/architecture.md)
- [REST API contract](docs/api.md)
- [Scoring methodology](docs/scoring.md)
- [OpenAI, LangChain, embeddings, and Qdrant](docs/ai-and-retrieval.md)
- [Configuration reference](docs/configuration.md)
- [Security and privacy](docs/security.md)
- [Operations and troubleshooting](docs/operations.md)
- [Testing and evaluation](docs/testing-and-evaluation.md)
- [Architecture decision records](docs/adr/README.md)
- [Contributing](CONTRIBUTING.md)
