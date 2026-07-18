# ADR 0004: Expose stateless synchronous analysis

- Status: Accepted
- Date: 2026-07-18

## Context

The initial product accepts one bounded listing and returns one complete analysis. Introducing job
storage, queues, polling, callbacks, and retention would materially increase operational and privacy
scope. Provider calls can usually complete within a bounded request timeout, and deterministic mode
is fast enough for interactive use.

## Decision

Expose `POST /api/v1/analyses` as a synchronous, stateless operation. Generate a per-invocation
analysis UUID for correlation but do not persist jobs or results. Bound input size, provider timeout,
and retries. Scale independent API replicas behind a load balancer; use Qdrant only for shared
editorial knowledge, not analysis records.

## Consequences

- Clients receive one simple request/response contract with no job lifecycle.
- The application stores less customer data and replicas require no session affinity.
- Load balancing and rollback remain straightforward.
- Client and proxy timeouts must exceed the bounded analysis duration.
- Long-running batch analysis, durable history, webhooks, and cancellation are not provided.
- If workload evidence later requires asynchronous jobs, that should be a new versioned endpoint
  and ADR with explicit persistence, idempotency, tenancy, retention, and authorization decisions.

## Alternatives considered

- Queue-backed async jobs from launch: rejected as premature operational and privacy complexity.
- Fire-and-forget generation: rejected because it weakens delivery guarantees and error visibility.
- Persist every analysis automatically: rejected because storage is not needed for the current
  outcome and would introduce data-governance obligations.
