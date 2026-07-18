# Operations and troubleshooting

## Deployment model

The API process is stateless: each request is analyzed synchronously and no analysis record is
stored by the application. Replicas may be added behind a load balancer without session affinity.
Qdrant is shared retrieval infrastructure and has its own persistence, backup, and capacity needs.

OpenAI and Qdrant are optional by default. Without credentials the service intentionally starts in
deterministic/static mode. If an optional configured provider becomes unavailable, a response
warning exposes the fallback. Required providers instead fail startup or return `503`.

## Local operations

Start a key-free development process:

```bash
uvicorn property_intelligence.bootstrap:app --host 127.0.0.1 --port 8000
```

Start the Docker stack:

```bash
docker compose up --build -d
docker compose ps
docker compose logs --tail 100 api
```

Stop while retaining vectors:

```bash
docker compose down
```

The Qdrant named volume is `property-intelligence-qdrant-data`. Removing volumes is destructive and
is not part of normal shutdown; confirm backup, environment, and exact target before any removal.

## Health and readiness

`GET /health/live` answers whether the process can serve HTTP. Use it for container liveness.

`GET /health/ready` reports provider composition without making billable calls. Common component
values include:

| Component | Value | Meaning |
|---|---|---|
| Generation | `deterministic_no_key` | LLM enabled but key absent; local generator selected |
| Generation | `disabled_deterministic` | LLM explicitly disabled |
| Generation | `openai_configured:<model>` | OpenAI adapter composed; not a live quota probe |
| Retrieval | `static_no_embedding_key` | Vector mode enabled but embedding key absent |
| Retrieval | `disabled_static` | Vector retrieval explicitly disabled |
| Retrieval | `qdrant_ready` | Collection initialized and configuration validated |
| Retrieval | `qdrant_unavailable_with_static_fallback` | Optional Qdrant startup failed; static retrieval remains |

An optional fallback is degraded capability but still a usable API. Alert on component-state
changes, response warnings, `500`/`503` rates, and latency rather than relying on the top-level
health status alone.

## Production startup checklist

1. Build an immutable image from a reviewed revision and scan it.
2. Supply secrets from a secret manager; never bake `.env` into the image.
3. Set `PIE_ENVIRONMENT=production`, disable docs, enable auth, and configure exact allowed hosts.
4. Decide explicitly whether generation and vector retrieval are optional or required.
5. If using Qdrant, ingest a versioned collection with the exact embedding model/dimensions before
   switching required mode on.
6. Put the API and Qdrant behind private/TLS network controls; add gateway rate limits.
7. Configure resource requests/limits, termination grace, replica count, and disruption policy.
8. Verify liveness/readiness and one fact-checked analysis request.
9. Confirm logs do not contain bodies/secrets and dashboards expose fallback/error/cost signals.
10. Exercise rollback to the prior API image and prior Qdrant collection setting.

## Graceful shutdown and scaling

The application lifespan closes owned Qdrant clients on shutdown. Compose supplies an init process
and a 30-second stop grace period. A production orchestrator should stop routing new traffic before
termination and allow in-flight OpenAI requests up to the configured timeout.

The native async provider paths avoid blocking worker threads. Scale replicas based on request
latency, concurrent provider limits, CPU used by deterministic analysis, and upstream quotas.
Statelessness does not remove the need for global rate/cost control.

## Logs and correlation

Application logs are JSON by default and contain timestamp, level, logger, message, request ID,
method, path, status, and duration where applicable. Request bodies are not logged. Clients may send
an ASCII `X-Request-ID` up to 128 characters; otherwise the service creates one and returns it in
the response header.

Use the ID to correlate gateway and application events. Treat exception traces as sensitive
operational data even though public errors are scrubbed.

## Qdrant backup and rollout

Back up Qdrant according to the deployed service’s supported snapshot procedure and test restore in
a separate environment. The local named volume is not itself a backup.

Use versioned collection names for embedding or incompatible corpus changes. Ingest and validate a
new collection before updating `PIE_QDRANT_COLLECTION`; retain the old one for rollback. Ingestion
upserts stable IDs but does not prune retired IDs, so avoid treating a repeated ingest as an exact
collection replacement.

Each managed collection carries a compatibility manifest in Qdrant collection metadata. API
startup verifies the embedding provider, model, dimensions, and bundled corpus schema/ID/version.
Do not edit this metadata to bypass a mismatch: create, ingest, and verify a new collection because
metadata alone cannot prove that existing vectors were produced by the declared model and corpus.

## Troubleshooting

### The service starts without OpenAI

This is expected when providers are optional. Check readiness for `deterministic_no_key` and
`static_no_embedding_key`; responses should show `generation_source: deterministic`. Supply a key
only when external generation/embeddings are desired.

### Startup validation fails

Read the configuration error and check these invariants:

- production requires docs off, auth on, an API key, and no wildcard host/CORS entries;
- auth enabled requires `PIE_API_KEY`;
- LLM required requires LLM enabled and `PIE_OPENAI_API_KEY`;
- vector required requires vector enabled and `PIE_OPENAI_API_KEY`.

JSON-list settings must use valid JSON array syntax.

### `401 authentication_failed`

Confirm analysis auth is enabled intentionally and send `Authorization: Bearer <PIE_API_KEY>`.
Health routes remain public. Do not print the key while debugging.

### `413 request_too_large`

Reduce the body below `PIE_MAX_REQUEST_BYTES`. The description is independently limited to 10,000
characters and amenities to 100 entries. Increase the byte limit only after reviewing abuse and
memory impact.

### `422 validation_error`

Inspect `error.details`: unknown fields, blank required strings, invalid language tags, and length
limits are rejected. Compare the request with `examples/listing_request.json`.

### Qdrant connection fails

For a host-run API, `.env.example` uses `http://localhost:6333`. Inside Compose, the service name is
`http://qdrant:6333`. Check `docker compose ps`, network policy, credentials, and the collection.
Optional mode falls back; required mode prevents a healthy startup/request.

### Qdrant collection compatibility error

The collection was created for different vector settings, embedding model, or corpus, or it predates
the compatibility manifest. Do not mutate it in place. Create a new versioned collection, ingest
with the configured provider/model/dimensions and intended corpus, validate, and switch the API
setting.

### OpenAI generation falls back

Look for the response warning and correlated server exception, then check key scope, model access,
quota, network, timeout, and structured-output compatibility. Do not expose provider error payloads
to clients. In required mode the same condition returns `503`.

### Retrieval is empty but no error is reported

An initialized collection may contain no documents. Run the versioned ingestion command, validate
that the API and CLI use the same collection/model/dimensions, and perform representative searches.

### Host header is rejected

Add the exact external hostname to `PIE_ALLOWED_HOSTS`. Do not use `*` in production.

## Rollback

Rollback the API image and configuration together. If retrieval changed, also point back to the
prior versioned Qdrant collection. Because analysis is stateless there is no application database
migration to reverse, but clients may still depend on response shape and scoring methodology;
preserve the `/api/v1` contract and methodology identifiers during rollback.
