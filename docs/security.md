# Security and privacy

## Security posture

The API treats listing content, retrieved guidance, and model output as untrusted. It uses strict
schemas, bounded requests and provider calls, optional bearer authentication, host/CORS controls,
metadata-only access logs, prompt isolation, and secret-safe errors. Production configuration
fails startup when basic exposure controls are not enabled.

This guide is an operational baseline, not a substitute for a deployment-specific threat model,
legal review, privacy assessment, or penetration test.

## Data handled

Requests may contain commercially sensitive property descriptions and approximate locations.
Avoid submitting guest names, contact details, access codes, exact private addresses, payment
instructions, or other unnecessary personal/sensitive data.

When OpenAI generation or embeddings are enabled, submitted listing facts and/or a bounded listing
query are sent to the configured provider. When Qdrant is enabled, editorial corpus content,
metadata, and vectors are stored in that service. Review each provider’s current data-processing,
retention, regional, and contractual controls for the deployment.

## Existing controls

- Request models reject unknown fields and enforce string/list limits.
- Middleware rejects bodies over the configured byte limit before normal processing.
- Analysis routes use constant-time bearer-token comparison when authentication is enabled.
- Production forbids unauthenticated analysis, interactive docs, wildcard hosts, and wildcard CORS.
- Provider calls use timeouts and bounded retries; public errors omit provider details.
- Listing input and retrieved guidance are delimited as untrusted prompt data.
- Structured LLM output is validated with Pydantic before entering the domain response.
- Logs record request metadata, status, duration, and correlation ID, not request bodies.
- Responses disable caching and add `nosniff`, frame, referrer, and browser-permission headers.
- Sentry default PII transmission is disabled by configuration.
- The Docker API runs as a non-root user on a read-only filesystem, drops Linux capabilities, and
  sets `no-new-privileges`.

## Deployment requirements

1. Terminate TLS at a trusted proxy/load balancer; do not expose plaintext service traffic to the
   public internet.
2. Store `PIE_API_KEY`, `PIE_OPENAI_API_KEY`, `PIE_QDRANT_API_KEY`, and `PIE_SENTRY_DSN` in a secret
   manager. Rotate them and scope them to the deployment.
3. Use a high-entropy API key and add gateway-level rate limits, abuse detection, and identity-aware
   controls where multiple clients need independent revocation/auditability.
4. Restrict allowed hosts and CORS to exact deployed origins. CORS is not authentication.
5. Keep Qdrant on a private network or require its API key and TLS. Compose binds Qdrant HTTP to
   `127.0.0.1` and does not publish gRPC by default; do not broaden that binding automatically in
   production. Setting `PIE_QDRANT_API_KEY` configures both sides of the local Compose connection.
6. Define retention and deletion procedures for logs, traces, vectors, and any upstream request
   capture. The application itself is stateless and does not persist analysis requests.
7. Pin, scan, and regularly update container images and Python dependencies through reviewed pull
   requests.
8. Monitor `401`, `413`, `422`, `500`, `503`, provider fallback warnings, latency, and usage/cost.

## Prompt injection and factuality

Listing descriptions can contain instructions designed to redirect the model. The system prompt
explicitly treats listing, analysis, and guidance sections as data and forbids following embedded
instructions. Keep these defenses whenever prompts change and evaluate direct, indirect, encoded,
and multilingual injection attempts.

Model output is a suggestion, not verified property truth. Hosts must review generated titles,
descriptions, tags, and amenity recommendations before publishing. Never automatically publish
generated copy without an approval and factual-verification step.

## Known boundaries

- The built-in bearer key is one shared service credential, not per-user authorization, tenancy,
  quota allocation, or a full identity system.
- Application middleware limits body size but does not replace gateway rate limiting.
- Readiness reports composed modes and startup state; it deliberately avoids billable provider
  probes and therefore cannot guarantee that the next OpenAI request will succeed.
- Fallbacks favor availability. Set providers to required only when failing closed is the business
  requirement.
- Readability and claim validation are English-oriented, so the API currently rejects non-English
  language tags. Generated copy remains subject to platform rules and fair
  housing/anti-discrimination review applicable to the deployment.

## Incident response

If a secret or listing payload may have been exposed:

1. revoke/rotate affected credentials;
2. restrict ingress and preserve relevant metadata logs without spreading sensitive payloads;
3. identify affected providers, stores, environments, and time ranges;
4. follow contractual and legal notification procedures;
5. remediate the control gap and validate with key-free tests plus targeted external checks;
6. document the incident and prevention action without committing secrets or private data.
