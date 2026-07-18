# Contributing

Property Intelligence Engine accepts changes that preserve deterministic scoring, provider
independence, and the Clean Architecture dependency direction. Start with
[the architecture guide](docs/architecture.md) before changing a public or provider boundary.

## Development setup

Use Python 3.12 or 3.13. Locked dependency files are the reproducible installation path:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --requirement requirements-dev.lock
python -m pip install --no-deps --editable .
Copy-Item .env.example .env
```

On macOS or Linux, use `source .venv/bin/activate` and `cp .env.example .env`.

For ordinary development, leave `PIE_OPENAI_API_KEY` unset. The complete API then runs with
deterministic generation and the bundled static retriever:

```bash
uvicorn property_intelligence.bootstrap:app --reload
```

## Design before implementation

Before a non-trivial change, document:

- the behavior and user outcome;
- the layer that owns the behavior;
- the affected public contract, if any;
- fallback and failure behavior;
- test and migration strategy.

Record durable, cross-cutting decisions under `docs/adr/`. Do not put business logic in a route or
provider SDK types in the domain/application layers.

## Quality gates

Run focused tests while iterating, then use the full key-free checks:

```bash
ruff format --check .
ruff check .
mypy
pytest -m "not live" --cov=property_intelligence --cov-report=term-missing
```

Coverage is configured with branch measurement and an 85% minimum when coverage is collected.
The CI matrix targets Python 3.12 and 3.13. Normal tests must not need OpenAI, a network Qdrant
instance, or any secret; the Qdrant adapter integration tests use an in-memory client.

When adding a genuinely live test, mark it `@pytest.mark.live`, skip it unless its explicit
credentials are present, and keep it out of the default suite. Never expose a provider key in
fixtures, snapshots, logs, or failure messages.

## Dependency changes

Declare dependency ranges in `pyproject.toml`, then regenerate the applicable lock files with the
documented `uv pip compile --universal` commands in their headers. Install
[uv](https://docs.astral.sh/uv/getting-started/installation/) outside the project environment,
review the resolved diff, and install with `--no-deps` from the lock before running checks. Do not
hand-edit generated lock contents.

## Public contract changes

The current contract is `/api/v1`. Backward-compatible fields may be added deliberately; removal,
renaming, meaning changes, or validation tightening require a versioning decision and an ADR.
Update `docs/api.md`, the request/response examples, and API integration tests together.

## Scoring and prompts

- Scoring changes require fixtures that explain changed outcomes and a new methodology version.
- Prompt changes require a new prompt version, structured-output tests, and factuality/injection
  evaluation cases.
- Corpus changes require a corpus-version decision and consistent packaged/source copies. See
  [AI and retrieval](docs/ai-and-retrieval.md).

## Commits and authorship

Keep commits focused and describe the outcome in imperative language. Repository changes must be
authored under the owner’s configured Git identity, Miguel Angel Sierra Hayer
(`<91997685+Miguesh@users.noreply.github.com>`). Do not change Git identity, add an AI author, or
add an AI co-author trailer. External publication remains an explicit owner action.
