# ADR 0005: Validate generated claims in the deterministic domain

- Status: Accepted
- Date: 2026-07-18

## Context

A strict structured-output schema can constrain titles, descriptions, and tags while still allowing
an LLM to invent a property feature. Prompt instructions reduce this risk but cannot establish that
generated copy is factually grounded. Retrieved guidance is editorial advice and must never become
evidence that a submitted property has an amenity, view, capacity, or proximity.

## Decision

Apply a versioned, deterministic claim validator after every primary and fallback generation. Keep
the pure policy in the domain, expose validation through an application protocol for injection, and
orchestrate it inside `AnalyzeListingUseCase`. Build its evidence set only from submitted listing
facts. Reject unsupported known features, view types, and a narrow taxonomy of concrete property
attributes; unit-context quantitative claims;
ungrounded proximity targets and known landmarks; and generated URLs, email addresses, and
phone-like contact channels. Reject property-type substitutions and do not treat a nearby/public
amenity as evidence that the rental provides it. A matching number in a different context is not
supporting evidence.

Treat a primary validation failure like a generation failure: use the deterministic generator only
when generation is optional, and fail closed when it is required. Validate fallback output through
the same policy. Strip contact channels before the deterministic generator reuses submitted text so
contact-bearing inputs continue to produce a safe key-free response.

## Consequences

- Schema-valid hallucinations cannot silently cross the application boundary for covered claim
  classes.
- The key-free deterministic path follows the same factuality contract as an external provider.
- Provider-neutral generated-content invariants enforce exactly three unique titles, two unique
  descriptions, and 8–12 unique tags with bounded lengths.
- The validator is provider-neutral, testable without credentials, and replaceable through a port.
- Conservative matching can reject valid novel wording; alias tables and policy versions must be
  updated deliberately with regression tests.
- Open-ended qualitative and previously unseen claims still require prompt controls and evaluation;
  this conservative taxonomy does not prove every natural-language statement.

## Alternatives considered

- Prompt-only factuality controls: rejected because instruction following is probabilistic.
- Validation inside the OpenAI adapter: rejected because other generators and fallbacks would bypass
  the rule and the application would become provider-dependent.
- Treat retrieved guidance as factual evidence: rejected because guidance describes writing
  practices, not the submitted property.
