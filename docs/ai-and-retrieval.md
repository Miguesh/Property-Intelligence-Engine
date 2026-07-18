# AI generation and knowledge retrieval

## Decision summary

OpenAI/LangChain generation and Qdrant vector retrieval are optional adapters around a complete
deterministic core. Routes never call them directly. When credentials are absent, the application
still returns the full response contract using deterministic generation and lexical retrieval over
the bundled corpus.

Optional provider failures degrade with a warning. Required provider failures fail closed with a
`503` or, for invalid/startup configuration, prevent the process from starting.

## Provider selection

### Generation

| Configuration | Primary generator | Failure behavior |
|---|---|---|
| `PIE_LLM_ENABLED=false` | Deterministic | No external call |
| Enabled, no `PIE_OPENAI_API_KEY` | Deterministic | No external call |
| Enabled with key, `PIE_LLM_REQUIRED=false` | LangChain/OpenAI | Deterministic fallback plus response warning |
| Enabled with key, `PIE_LLM_REQUIRED=true` | LangChain/OpenAI | `503` when generation cannot complete |

`PIE_LLM_REQUIRED=true` is invalid unless generation is enabled and an OpenAI key is present.

### Retrieval

| Configuration | Retriever | Failure behavior |
|---|---|---|
| `PIE_VECTOR_STORE_ENABLED=false` | Bundled static lexical retriever | No vector call |
| Enabled, no `PIE_OPENAI_API_KEY` | Bundled static lexical retriever | No vector call |
| Enabled with key, `PIE_VECTOR_STORE_REQUIRED=false` | OpenAI embeddings + Qdrant | Static fallback plus response warning |
| Enabled with key, `PIE_VECTOR_STORE_REQUIRED=true` | OpenAI embeddings + Qdrant | Startup/query failure fails closed |

The current vector path uses OpenAI embeddings, so an OpenAI key is also the vector-embedding
credential. A remote protected Qdrant service may additionally need `PIE_QDRANT_API_KEY`.

## Structured generation

`LangChainListingGenerator` composes a `ChatPromptTemplate` with `ChatOpenAI` and Pydantic
structured output. The output schema requires exactly three distinct titles, two distinct
descriptions, and 8–12 distinct tags. The adapter uses the OpenAI Responses API through LangChain,
enforces a provider timeout and bounded retries, validates the result again, and translates
provider/parsing failures into an application-safe exception. The provider-neutral
`GeneratedContent` domain model repeats the count, uniqueness, and length invariants so alternate
generators cannot weaken the REST contract.

The prompt is versioned as `listing-copy-v2`; deterministic output is versioned as
`deterministic-copy-v1`. The API returns the active value in `prompt_version` and provider
provenance in `generation_source`.

### Prompt data and safety boundaries

The generator receives three serialized sections:

- submitted listing facts;
- deterministic scores, evidence, and improvements;
- retrieved editorial guidance.

The system instruction labels the complete human message as untrusted, including apparent section
labels or forged delimiters inside submitted values. Retrieved documents are advice, not property
facts. The model is instructed not to invent amenities, distances, views, ratings, availability,
policies, accessibility claims, or neighborhood details; not to create discriminatory copy; and to
preserve the requested English locale.

### Deterministic post-generation factuality guard

Structured output guarantees shape, not truth. Before generated copy leaves the application use
case, the versioned `generated-claims-2026.1` domain policy compares concrete claims only with the
submitted title, description, amenities, property type, and location. Retrieved guidance and
deterministic recommendations are never treated as evidence that a property feature exists.

The guard rejects unsupported known amenities, property/view types, and narrow concrete property
attributes (space, light, luxury positioning, modern style, and renovation status); new numeric
claims; ungrounded proximity targets and known landmark categories; and any generated URL, email
address, or phone-like contact channel. Quantities are matched by unit context: for example,
`4 guests` cannot support a
claim of `four bedrooms`, and a `10 PM` quiet hour cannot support a `10-minute walk`. Supported
amenity and number aliases such as `Wi-Fi`/`wireless internet` and `two`/`2` are accepted.
Known property-type changes are rejected, and nearby/public amenity mentions are treated as
location context rather than evidence that the rental provides that amenity.

An invalid optional-provider result follows the same deterministic fallback path as a provider
failure. When generation is required, the request fails closed. The fallback result is validated by
the same policy rather than being implicitly trusted. Before it reuses submitted text, the
deterministic generator removes contact channels so a valid contact-bearing input still receives a
safe key-free response.

This is a conservative guard over explicit taxonomies and quantitative patterns, not a proof of all
natural-language factuality. Prompt controls, offline adversarial evaluation, and operational
monitoring remain required for qualitative or previously unseen claim forms.

Prompt or claim-policy changes must retain those boundaries, increment the relevant version, and add
structured-output, injection, and factuality evaluation cases.

## Bundled guidance corpus

The corpus schema contains:

```json
{
  "schema_version": "1.0",
  "corpus_id": "property-intelligence-listing-guidance",
  "corpus_version": "1.0.0",
  "documents": [
    {
      "identifier": "stable-unique-id-v1",
      "content": "Editorial guidance, not a property fact.",
      "source": "Source label",
      "metadata": {"category": "title", "language": "en"}
    }
  ]
}
```

Document identifiers must be unique. `schema_version` controls loader compatibility;
`corpus_version` identifies editorial content. Corpus ID and version are copied into each vector
payload as metadata.

The editable repository copy is `knowledge/listing_guidance.v1.json`. The runtime package loads
`src/property_intelligence/infrastructure/knowledge/data/listing_guidance.v1.json`, including from
a built wheel. Keep the two JSON documents semantically identical when releasing a corpus update,
and test the packaged default. A custom source can be supplied to ingestion with `--source`.

## Qdrant ingestion

Start Qdrant locally, configure an OpenAI key, and ingest the bundled package corpus:

```bash
docker compose up -d qdrant
pie-ingest --qdrant-url http://localhost:6333
```

From inside the Compose API container:

```bash
docker compose exec api pie-ingest
```

To ingest the repository source explicitly:

```bash
pie-ingest --source knowledge/listing_guidance.v1.json \
  --qdrant-url http://localhost:6333 \
  --collection listing_guidance_v1 \
  --embedding-model text-embedding-3-small \
  --dimensions 1536
```

The command validates the JSON, creates or validates the collection, embeds in batches, and waits
for idempotent upserts. Point IDs are stable UUIDs derived from collection name and document
identifier, so re-ingesting replaces matching records. It does **not** prune identifiers removed
from a prior corpus; use a new collection for a clean version transition or explicitly manage
retired points through an approved operational procedure.

On first creation, the adapter also writes a versioned compatibility manifest into Qdrant's
collection metadata. It records the manifest schema, embedding provider, model and dimensions, plus
the corpus schema, ID and version. Every API startup and ingestion run requires those keys to be
present with the exact expected values. This catches same-dimension model changes and corpus
mismatches that Qdrant's vector-size validation cannot detect. Existing collections created before
this manifest was introduced are intentionally rejected; create and ingest a new versioned
collection instead of adding metadata to an unverified collection in place.

### Key-free retrieval smoke check

The CLI can exercise ingestion with local hash embeddings:

```bash
pie-ingest --deterministic --qdrant-url :memory: \
  --collection listing_guidance_smoke --dimensions 64
```

Hash embeddings are only a wiring/test tool, not a semantic replacement for production
embeddings. Never populate a production collection with them. Use a clearly separate smoke
collection so an OpenAI query vector is never compared with hash-embedded documents.

## Corpus and embedding versioning

Use a new collection name when changing any of the following:

- embedding provider or model;
- embedding dimensions;
- distance metric;
- incompatible corpus schema;
- a corpus release that must exclude retired points atomically.

A safe rollout is:

1. create a versioned corpus and collection name;
2. ingest with the exact model and dimensions configured for the future API;
3. validate document count and representative searches;
4. deploy the API with the new collection setting;
5. monitor fallback warnings and relevance;
6. retain the old collection for rollback, then remove it only through an approved, recoverable
   data-retention procedure.

Qdrant rejects an existing collection whose vector size or distance does not match the adapter.
The application additionally rejects missing or mismatched compatibility-manifest keys, including
provider/model and corpus identity, before any query or upsert.

## External-provider validation

Provider validation is intentionally deferred until credentials are available. Follow the manual
checklist in [Testing and evaluation](testing-and-evaluation.md); standard tests use injected clients,
in-memory Qdrant, and deterministic adapters and therefore spend no API credits.
