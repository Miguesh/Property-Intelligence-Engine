# ADR 0001: Use deterministic scoring with LLM-assisted copy

- Status: Accepted
- Date: 2026-07-18

## Context

The product must score listing quality, SEO, and readability while also producing nuanced improved
copy. Scores need to be reproducible, explainable, inexpensive to test, and available when an AI
provider is unavailable. Free-form model scoring would vary by model/version and make regressions,
audits, and customer explanations difficult.

## Decision

Compute all numerical scores and their evidence in the provider-independent domain with a versioned
deterministic methodology. Use an LLM only to generate titles, descriptions, and tags from submitted
facts, deterministic analysis, and editorial guidance. Return score components/rationales plus
generation provenance and prompt version.

## Consequences

- Identical normalized input and methodology produce identical scores.
- Scoring works without credentials and cannot drift merely because a model changes.
- Every score can be decomposed and regression-tested.
- The LLM can improve editorial quality without becoming the source of truth.
- Rules require ongoing calibration against expert labels and may miss nuance.
- Non-English readability needs separate calibrated methods.
- Methodology changes need explicit versioning and comparative evaluation.

## Alternatives considered

- LLM-only scoring: rejected because of variability, cost, weak auditability, and outage coupling.
- Rules-only product: rejected because polished rewriting and language-sensitive editing benefit
  materially from a constrained model.
- Blended numeric score including model judgment: deferred until there is a separately labeled,
  calibrated, and versioned model-evaluation signal that does not obscure deterministic evidence.
