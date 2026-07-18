# Scoring methodology

## Decision summary

All numerical scores are computed locally by the versioned deterministic methodology
`deterministic-2026.1`. OpenAI, LangChain, embeddings, and Qdrant cannot change a score. Every score
is rounded to one decimal, bounded to 0–100, and returned with component values, weights, and a
rationale.

Scores are decision aids for improving listing content, not marketplace performance promises.

## Listing quality score

| Component | Weight | Signals |
|---|---:|---|
| Content completeness | 30% | Useful description length, property/location context, configuration facts, audience, and policies |
| Amenity coverage | 20% | Weighted universal and property-type amenity groups; equivalent amenities satisfy a group once |
| Value proposition | 20% | Concrete facts, differentiators, guest benefits, and useful local context |
| Guest clarity | 15% | Capacity/layout, arrival, transport, rules, and expectation-setting |
| Trust and hygiene | 10% | Submitted safety items, mechanics, disclosures, and off-platform contact/payment signals |
| Presentation | 5% | 60% readability score and 40% title utility within this component |

Amenity aliases are normalized and duplicates do not increase coverage. A description mention can
support evidence only when it is affirmative; recognized negated phrases such as “no parking” do
not count as present amenities.

## SEO score

| Component | Weight | Signals |
|---|---:|---|
| Title relevance | 30% | Useful title length, accurate property/location terms, differentiators, and mechanics |
| Description relevance | 40% | Useful length, location/property concepts, amenity details, proximity, audience, and opening summary |
| Search breadth | 20% | Distinct amenity categories, local context, balanced title elements, and lexical variety |
| Structure and hygiene | 10% | Scannable organization and absence of keyword, punctuation, or repeated-title spam |

### SEO caveat

This is an **on-page content quality heuristic**. It does not inspect marketplace algorithms,
competition, listing engagement, price, availability, reviews, photos, platform policy, backlinks,
or real search-result position. A high score does not guarantee impressions, ranking, bookings, or
revenue on Airbnb, Vrbo, Google, or any other platform. Use controlled marketplace experiments and
business metrics to validate outcomes.

## Readability score

| Component | Weight | Signals |
|---|---:|---|
| Flesch Reading Ease | 50% | English word, sentence, and estimated syllable counts |
| Sentence length | 20% | Average and prevalence of sentences over 30 words |
| Paragraph quality | 15% | Number and size of paragraphs |
| Skimmability | 10% | Paragraphs, bullets, and descriptive headings |
| Mechanics | 5% | Capitalization, repeated punctuation, spacing, and sentence endings |

Very short descriptions can appear superficially easy to read, so the score is capped at 25 below
20 words, 50 below 40 words, and 70 below 60 words. The current formula and syllable heuristic are
English-oriented. The current API therefore accepts only `en` and `en-XX` language tags. Adding
another language requires a calibrated readability method, localized claim validation, prompts,
and evaluation cases before the public contract is expanded.

## Strengths, weaknesses, and improvements

These outputs are rule-based interpretations of the same normalized evidence. They are bounded in
count, deduplicated, and phrased as actions. High-impact safety and content gaps are prioritized
before lower-impact presentation work.

## Missing amenities

A missing-amenity suggestion means the submitted amenities and affirmative description text do not
represent that item. It is **not** a physical inspection and must not be reported as proof that the
property lacks it. Safety suggestions explicitly instruct the user to verify installation and list
the item accurately; other suggestions must likewise be verified before publication.

Rules combine universal expectations, property-type relevance, and audience signals. Confidence is
a rule confidence from 0 to 1, not a probability that the property physically lacks the amenity.

## Changing the methodology

A scoring change should include:

1. a documented reason and expected user impact;
2. regression fixtures covering sparse, rich, duplicate, negated, and adversarial copy;
3. comparison against an expert-labeled evaluation set;
4. a new methodology identifier rather than silently reinterpreting prior values;
5. updated API examples and release notes when observed scores change materially.

See [ADR 0001](adr/0001-hybrid-deterministic-scoring.md) for why score ownership is separate from
LLM generation.
