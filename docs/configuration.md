# Configuration reference

## Loading and formats

Settings are read from process environment variables and an optional `.env` file. Names are
case-insensitive and use the `PIE_` prefix. Unknown settings are ignored; values are validated at
startup. Copy `.env.example` as a local starting point, but inject secrets through the deployment
platform rather than committing a populated file.

Lists use JSON syntax, for example:

```dotenv
PIE_ALLOWED_HOSTS=["api.example.com"]
PIE_CORS_ORIGINS=["https://console.example.com"]
```

## Runtime settings

| Variable | Default | Purpose |
|---|---|---|
| `PIE_APP_NAME` | `Property Intelligence Engine` | OpenAPI/application display name |
| `PIE_APP_VERSION` | `0.1.0` | Health, OpenAPI, and Sentry release version |
| `PIE_ENVIRONMENT` | `local` | One of `local`, `test`, `staging`, `production` |
| `PIE_API_PREFIX` | `/api/v1` | Prefix for analysis routes |
| `PIE_DOCS_ENABLED` | `true` | Enables `/docs`, `/redoc`, and `/openapi.json` |
| `PIE_AUTH_ENABLED` | `false` | Requires bearer API key on analysis routes |
| `PIE_API_KEY` | unset | Bearer credential; required when auth is enabled |
| `PIE_ALLOWED_HOSTS` | `localhost`, `127.0.0.1`, `testserver` | Trusted HTTP Host values |
| `PIE_CORS_ORIGINS` | empty | Exact browser origins allowed for CORS |
| `PIE_MAX_REQUEST_BYTES` | `65536` | Body-size limit; accepted range 1,024–1,048,576 |
| `PIE_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL` |
| `PIE_LOG_JSON` | `true` | Emits structured JSON application logs |

## Generation and embeddings

| Variable | Default | Purpose |
|---|---|---|
| `PIE_LLM_ENABLED` | `true` | Allows OpenAI generation when a key is present |
| `PIE_LLM_REQUIRED` | `false` | Fails closed instead of using deterministic generation |
| `PIE_OPENAI_API_KEY` | unset | OpenAI generation and embedding credential |
| `PIE_OPENAI_MODEL` | `gpt-5.6-sol` | Structured listing-copy model |
| `PIE_OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | Knowledge embedding model |
| `PIE_EMBEDDING_DIMENSIONS` | `1536` | Vector size; accepted range 256–4,096 |
| `PIE_LLM_TIMEOUT_SECONDS` | `45` | Per-generation timeout; greater than 0, maximum 180 |
| `PIE_LLM_MAX_RETRIES` | `2` | Provider retry count; accepted range 0–5 |

Model availability and compatibility must be confirmed for the deployment’s OpenAI account before
turning on required mode. Changing an embedding model or dimensions requires a versioned Qdrant
collection and re-ingestion.

## Vector retrieval

| Variable | Default | Purpose |
|---|---|---|
| `PIE_VECTOR_STORE_ENABLED` | `true` | Allows OpenAI-embedded Qdrant retrieval when a key is present |
| `PIE_VECTOR_STORE_REQUIRED` | `false` | Fails closed instead of using static corpus retrieval |
| `PIE_QDRANT_URL` | `http://qdrant:6333` | Qdrant HTTP endpoint; `.env.example` uses localhost |
| `PIE_QDRANT_API_KEY` | unset | Optional protected-Qdrant credential |
| `PIE_QDRANT_COLLECTION` | `listing_guidance_v1` | Unnamed dense-vector collection |
| `PIE_QDRANT_TIMEOUT_SECONDS` | `10` | Qdrant operation timeout; accepted range 1–60 |
| `PIE_RETRIEVAL_LIMIT` | `5` | Guidance records passed to generation; accepted range 1–10 |

Vector required mode also requires vector retrieval to be enabled and an OpenAI key to be present.

## Observability

| Variable | Default | Purpose |
|---|---|---|
| `PIE_SENTRY_DSN` | unset | Enables Sentry error/performance reporting |
| `PIE_SENTRY_TRACES_SAMPLE_RATE` | `0.0` | Trace sample rate from 0 to 1 |

Sentry initializes with default PII collection disabled, request-body capture disabled, and local
variable capture disabled. Review organization-side scrubbing and retention before enabling it for
listing data workloads.

## Compose-only settings

| Variable | Default | Purpose |
|---|---|---|
| `PIE_BIND_HOST` | `127.0.0.1` | Host interface used for the published API port |
| `PIE_API_PORT` | `8000` | Host port mapped to API port 8000 |
| `PIE_COMPOSE_QDRANT_URL` | `http://qdrant:6333` | Internal or external Qdrant URL injected into the API container |
| `QDRANT_HTTP_PORT` | `6333` | Host port mapped to Qdrant HTTP |

Compose forwards every documented runtime setting. Its published API and Qdrant HTTP ports bind to
localhost by default, and gRPC is not published. When `PIE_QDRANT_API_KEY` is set, Compose supplies
the same credential to the API client and the Qdrant server. The API has no hard startup dependency
on the Qdrant container, so disabled/optional vector mode retains the documented static fallback.

## Production invariants

`PIE_ENVIRONMENT=production` is rejected unless:

- interactive docs are disabled;
- API authentication is enabled;
- an API key of at least 24 characters is present;
- allowed hosts do not contain `*`;
- CORS origins do not contain `*`.

Auth in any environment requires an API key. LLM required mode requires LLM enabled plus an
OpenAI key. Vector required mode requires vector enabled plus an OpenAI key. These are startup
validation failures, not late request errors.

Example production skeleton (supply secrets from a secret manager):

```dotenv
PIE_ENVIRONMENT=production
PIE_DOCS_ENABLED=false
PIE_AUTH_ENABLED=true
PIE_ALLOWED_HOSTS=["api.example.com"]
PIE_CORS_ORIGINS=["https://console.example.com"]
PIE_LLM_REQUIRED=false
PIE_VECTOR_STORE_REQUIRED=false
```

Leaving providers optional is a deliberate availability choice: absent credentials select local
fallbacks. Set required flags only after ingestion, connectivity, quotas, and alerting are ready.
