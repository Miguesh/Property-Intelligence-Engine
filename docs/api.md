# REST API contract

## Contract summary

The public analysis operation is synchronous and stateless:

```http
POST /api/v1/analyses
Content-Type: application/json
```

It returns `200 OK` with deterministic scores and generated recommendations. Authentication is
disabled locally by default. When `PIE_AUTH_ENABLED=true`, send the configured API key as
`Authorization: Bearer <key>`.

## Request

```json
{
  "title": "Ocean View Condo in Miami",
  "description": "Welcome to a bright two-bedroom condo for four guests near Miami Beach. Enjoy the private balcony, fast Wi-Fi, dedicated workspace, full kitchen, and one bathroom. Self check-in makes arrival easy, and free parking is included. The building has stairs, and quiet hours begin at 10 PM.",
  "amenities": [
    "Wi-Fi",
    "Kitchen",
    "Dedicated workspace",
    "Free parking",
    "Smoke alarm",
    "Carbon monoxide alarm",
    "Fire extinguisher",
    "First aid kit",
    "Self check-in"
  ],
  "property_type": "Condo",
  "location": {
    "city": "Miami",
    "country": "US",
    "region": "Florida",
    "neighborhood": "Miami Beach"
  },
  "language": "en"
}
```

The same body is available at [`examples/listing_request.json`](../examples/listing_request.json).

### Validation

| Field | Requirement |
|---|---|
| `title` | Required non-blank string, maximum 200 characters |
| `description` | Required non-blank string, maximum 10,000 characters |
| `amenities` | Optional array, maximum 100 non-blank strings of at most 120 characters each; case-insensitive duplicates are removed |
| `property_type` | Required non-blank string, maximum 100 characters |
| `location.city` | Required non-blank string, maximum 120 characters |
| `location.country` | Required non-blank string, maximum 120 characters |
| `location.region` | Optional string, maximum 120 characters |
| `location.neighborhood` | Optional string, maximum 120 characters |
| `language` | Optional English language tag (`en` or `en-XX`); defaults to `en` |

Unknown fields are rejected. The complete request body is also bounded by
`PIE_MAX_REQUEST_BYTES` (65,536 bytes by default).

## Request with curl

```bash
curl -X POST http://localhost:8000/api/v1/analyses \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: example-001" \
  --data @examples/listing_request.json
```

With authentication enabled, add:

```bash
-H "Authorization: Bearer ${PIE_API_KEY}"
```

Do not place real API keys in shell history, source-controlled scripts, or example files.

## Response

The response contract contains:

| Field | Meaning |
|---|---|
| `analysis_id` | New UUID for this invocation; not a durable database identifier |
| `listing_quality_score` | Deterministic 0–100 overall content score |
| `seo_score` | Deterministic 0–100 content-discoverability score |
| `readability_score` | Deterministic 0–100 English readability/presentation score |
| `score_details` | Per-score value, weighted components, rationales, and methodology version |
| `strengths` / `weaknesses` | Evidence-backed content observations |
| `missing_amenities` | Amenities absent from submitted data, with priority, reason, and confidence |
| `recommended_improvements` | Prioritized actions and rationales |
| `better_title_suggestions` | Three fact-preserving candidate titles |
| `better_descriptions` | Two candidate descriptions |
| `suggested_tags` | Eight to twelve factual classification/search tags |
| `generation_source` | `deterministic` or `openai:<model>` |
| `prompt_version` | Generator/prompt contract version |
| `knowledge_references` | Guidance identifiers, sources, and optional relevance scores |
| `warnings` | Explicit optional-provider fallback notices |

[`examples/listing_response.deterministic.json`](../examples/listing_response.deterministic.json)
shows a key-free response. `analysis_id` changes on every call, and scores change with input or a
methodology version.

“Missing” does not prove that a property lacks an amenity. It means the amenity was not found in
the submitted amenities or description and should be verified before being added to a listing.

## Errors

All handled errors use a stable envelope:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed.",
    "details": []
  },
  "request_id": "example-001"
}
```

| Status | Code | Cause |
|---|---|---|
| `401` | `authentication_failed` | Bearer credential missing or invalid when auth is enabled |
| `413` | `request_too_large` or `invalid_content_length` | Body limit exceeded or malformed length header |
| `422` | `validation_error` | Request does not satisfy the strict schema |
| `503` | `service_unavailable` | A provider configured as required could not complete analysis |
| `500` | `internal_error` | Unexpected server failure |

Provider details and secrets are intentionally absent from public errors. Every response includes
an `X-Request-ID` header for correlation.

## Health endpoints

```http
GET /health/live
GET /health/ready
```

Both are public, including when analysis authentication is enabled. Liveness reports process
availability. Readiness reports selected provider modes without making billable OpenAI calls. An
optional provider may report a fallback component state while the overall service remains usable.

Interactive Swagger UI (`/docs`), ReDoc (`/redoc`), and `/openapi.json` exist only when
`PIE_DOCS_ENABLED=true`; validated production configuration requires them to be disabled.
