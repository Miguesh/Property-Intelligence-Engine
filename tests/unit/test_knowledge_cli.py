"""Key-free tests for the versioned guidance-ingestion command."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from property_intelligence.domain.models import KnowledgeSnippet
from property_intelligence.infrastructure.config import Settings
from property_intelligence.infrastructure.knowledge import cli


class _RecordingEmbeddings:
    def __init__(self, dimensions: int = 3) -> None:
        self.dimensions = dimensions
        self.batches: list[tuple[str, ...]] = []

    async def embed_documents(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        batch = tuple(texts)
        self.batches.append(batch)
        return tuple(tuple(float(index) for index in range(self.dimensions)) for _ in batch)

    async def embed_query(self, text: str) -> tuple[float, ...]:
        return tuple(float(index) for index in range(self.dimensions))


class _RecordingVectorStore:
    def __init__(self) -> None:
        self.initialize_calls = 0
        self.upserts: list[tuple[tuple[KnowledgeSnippet, ...], tuple[tuple[float, ...], ...]]] = []

    async def initialize(self) -> None:
        self.initialize_calls += 1

    async def upsert(
        self,
        snippets: Sequence[KnowledgeSnippet],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        self.upserts.append(
            (
                tuple(snippets),
                tuple(tuple(vector) for vector in vectors),
            )
        )


def _snippets(count: int) -> tuple[KnowledgeSnippet, ...]:
    return tuple(
        KnowledgeSnippet(
            identifier=f"guidance-{index}",
            content=f"Guidance document {index}",
            source="test corpus",
        )
        for index in range(count)
    )


def _settings(**overrides: Any) -> Settings:
    return Settings(
        _env_file=None,
        qdrant_url="http://qdrant.test:6333",
        qdrant_collection="guidance-test",
        openai_embedding_model="embedding-test",
        openai_api_key=None,
        **overrides,
    )


def _write_corpus(path: Path, *, document_count: int = 2) -> Path:
    payload = {
        "schema_version": "1.0",
        "corpus_id": "cli-test",
        "corpus_version": "1.0.0",
        "documents": [
            {
                "identifier": f"document-{index}",
                "content": f"Editorial guidance {index}",
                "source": "test corpus",
                "metadata": {"topic": "testing"},
            }
            for index in range(document_count)
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _args(source: Path, **overrides: Any) -> argparse.Namespace:
    values: dict[str, Any] = {
        "source": source,
        "qdrant_url": ":memory:",
        "collection": "guidance-cli-test",
        "embedding_model": "embedding-test",
        "dimensions": 8,
        "batch_size": 1,
        "deterministic": True,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


@pytest.mark.asyncio
async def test_ingest_guidance_initializes_once_and_preserves_batch_boundaries() -> None:
    embeddings = _RecordingEmbeddings()
    vector_store = _RecordingVectorStore()
    snippets = _snippets(5)

    ingested = await cli.ingest_guidance(
        snippets,
        embeddings=embeddings,
        vector_store=vector_store,  # type: ignore[arg-type]
        batch_size=2,
    )

    assert ingested == 5
    assert vector_store.initialize_calls == 1
    assert embeddings.batches == [
        ("Guidance document 0", "Guidance document 1"),
        ("Guidance document 2", "Guidance document 3"),
        ("Guidance document 4",),
    ]
    upserted_identifiers = [
        tuple(snippet.identifier for snippet in batch) for batch, _ in vector_store.upserts
    ]
    assert upserted_identifiers == [
        ("guidance-0", "guidance-1"),
        ("guidance-2", "guidance-3"),
        ("guidance-4",),
    ]


@pytest.mark.asyncio
async def test_ingest_guidance_initializes_an_empty_corpus_without_provider_calls() -> None:
    embeddings = _RecordingEmbeddings()
    vector_store = _RecordingVectorStore()

    ingested = await cli.ingest_guidance(
        (),
        embeddings=embeddings,
        vector_store=vector_store,  # type: ignore[arg-type]
    )

    assert ingested == 0
    assert vector_store.initialize_calls == 1
    assert embeddings.batches == []
    assert vector_store.upserts == []


@pytest.mark.asyncio
@pytest.mark.parametrize("batch_size", [0, -1])
async def test_ingest_guidance_rejects_non_positive_batch_size(batch_size: int) -> None:
    with pytest.raises(ValueError, match="batch_size must be positive"):
        await cli.ingest_guidance(
            _snippets(1),
            embeddings=_RecordingEmbeddings(),
            vector_store=_RecordingVectorStore(),  # type: ignore[arg-type]
            batch_size=batch_size,
        )


def test_build_parser_uses_settings_defaults_and_accepts_explicit_overrides(tmp_path: Path) -> None:
    parser = cli.build_parser(_settings(embedding_dimensions=768))

    defaults = parser.parse_args([])
    assert defaults.source is None
    assert defaults.qdrant_url == "http://qdrant.test:6333"
    assert defaults.collection == "guidance-test"
    assert defaults.embedding_model == "embedding-test"
    assert defaults.dimensions == 768
    assert defaults.batch_size == 64
    assert defaults.deterministic is False

    source = tmp_path / "guidance.json"
    overridden = parser.parse_args(
        [
            "--source",
            str(source),
            "--qdrant-url",
            ":memory:",
            "--collection",
            "custom-guidance",
            "--embedding-model",
            "custom-embedding",
            "--dimensions",
            "32",
            "--batch-size",
            "4",
            "--deterministic",
        ]
    )
    assert overridden.source == source
    assert overridden.qdrant_url == ":memory:"
    assert overridden.collection == "custom-guidance"
    assert overridden.embedding_model == "custom-embedding"
    assert overridden.dimensions == 32
    assert overridden.batch_size == 4
    assert overridden.deterministic is True


@pytest.mark.asyncio
async def test_run_ingests_a_custom_corpus_with_in_memory_qdrant(tmp_path: Path) -> None:
    source = _write_corpus(tmp_path / "guidance.json", document_count=3)

    ingested = await cli._run(_args(source, batch_size=2), _settings())

    assert ingested == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"dimensions": 0}, "--dimensions must be positive"),
        ({"batch_size": 0}, "--batch-size must be positive"),
        (
            {"deterministic": False},
            "PIE_OPENAI_API_KEY is required unless --deterministic is selected",
        ),
    ],
)
async def test_run_rejects_invalid_or_unconfigured_provider_options(
    tmp_path: Path,
    overrides: dict[str, Any],
    message: str,
) -> None:
    source = _write_corpus(tmp_path / "guidance.json")

    with pytest.raises(ValueError, match=message):
        await cli._run(_args(source, **overrides), _settings())


def test_main_reports_success_without_exposing_configuration(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def successful_run(args: argparse.Namespace, settings: Settings) -> int:
        assert args.deterministic is True
        assert settings.qdrant_collection == "guidance-test"
        return 7

    monkeypatch.setattr(cli, "get_settings", _settings)
    monkeypatch.setattr(cli, "_run", successful_run)
    monkeypatch.setattr(
        sys,
        "argv",
        ["pie-ingest", "--deterministic", "--collection", "custom-guidance"],
    )

    cli.main()

    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == (
        "Ingested 7 guidance documents into 'custom-guidance' from the bundled corpus.\n"
    )


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_message"),
    [
        (ValueError("missing configuration"), 2, "configuration error: missing configuration"),
        (RuntimeError("provider details must stay private"), 1, "ingestion failed"),
    ],
)
def test_main_maps_failures_to_safe_shell_errors(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
    expected_status: int,
    expected_message: str,
) -> None:
    async def failing_run(args: argparse.Namespace, settings: Settings) -> int:
        raise error

    monkeypatch.setattr(cli, "get_settings", _settings)
    monkeypatch.setattr(cli, "_run", failing_run)
    monkeypatch.setattr(sys, "argv", ["pie-ingest", "--deterministic"])

    with pytest.raises(SystemExit) as raised:
        cli.main()

    assert raised.value.code == expected_status
    captured = capsys.readouterr()
    assert captured.out == ""
    assert expected_message in captured.err
    assert "provider details must stay private" not in captured.err
