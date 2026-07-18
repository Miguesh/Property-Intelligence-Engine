from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).parents[2] / "src" / "property_intelligence"


def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", maxsplit=1)[0])
    return roots


@pytest.mark.parametrize(
    ("layer", "forbidden"),
    [
        (
            "domain",
            {"fastapi", "pydantic", "langchain", "langchain_openai", "openai", "qdrant_client"},
        ),
        (
            "application",
            {"fastapi", "pydantic", "langchain", "langchain_openai", "openai", "qdrant_client"},
        ),
    ],
)
def test_inner_layers_do_not_import_frameworks(layer: str, forbidden: set[str]) -> None:
    violations: dict[str, set[str]] = {}
    for path in (PACKAGE_ROOT / layer).rglob("*.py"):
        invalid = imported_roots(path) & forbidden
        if invalid:
            violations[str(path.relative_to(PACKAGE_ROOT))] = invalid

    assert violations == {}


def test_routes_do_not_call_provider_sdks() -> None:
    roots = imported_roots(PACKAGE_ROOT / "interfaces" / "api" / "routes.py")
    assert roots.isdisjoint({"langchain", "langchain_openai", "openai", "qdrant_client"})
