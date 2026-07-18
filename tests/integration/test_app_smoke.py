from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient
from pydantic import SecretStr

from property_intelligence.bootstrap import create_app
from property_intelligence.infrastructure.config import Settings

REPOSITORY_ROOT = Path(__file__).parents[2]


def test_key_free_application_runs_end_to_end() -> None:
    app = create_app(
        Settings(
            environment="test",
            llm_enabled=False,
            vector_store_enabled=False,
            log_json=False,
        )
    )
    payload = {
        "title": "Ocean View Condo in Miami",
        "description": (
            "Welcome to a bright two-bedroom condo for four guests near Miami Beach. "
            "Enjoy the private balcony, fast Wi-Fi, dedicated workspace, full kitchen, "
            "and one bathroom. Self check-in makes arrival easy, and free parking is "
            "included. The building has stairs, and quiet hours begin at 10 PM."
        ),
        "amenities": [
            "Wi-Fi",
            "Kitchen",
            "Workspace",
            "Free parking",
            "Smoke alarm",
            "Carbon monoxide alarm",
            "Fire extinguisher",
            "First aid kit",
            "Self check-in",
        ],
        "property_type": "Condo",
        "location": {"city": "Miami", "country": "US"},
    }

    with TestClient(app) as client:
        response = client.post("/api/v1/analyses", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert 0 <= body["listing_quality_score"] <= 100
    assert 0 <= body["seo_score"] <= 100
    assert 0 <= body["readability_score"] <= 100
    assert body["generation_source"] == "deterministic"
    assert len(body["better_title_suggestions"]) == 3
    assert len(body["better_descriptions"]) == 2
    assert len(body["suggested_tags"]) >= 8
    assert body["knowledge_references"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-request-id"]


def test_documented_deterministic_response_matches_api() -> None:
    request = json.loads(
        (REPOSITORY_ROOT / "examples" / "listing_request.json").read_text(encoding="utf-8")
    )
    expected = json.loads(
        (REPOSITORY_ROOT / "examples" / "listing_response.deterministic.json").read_text(
            encoding="utf-8"
        )
    )
    app = create_app(
        Settings(
            environment="test",
            llm_enabled=False,
            vector_store_enabled=False,
            log_json=False,
        )
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/analyses", json=request)

    assert response.status_code == 200
    actual = response.json()
    assert str(UUID(actual["analysis_id"])) == actual["analysis_id"]
    actual["analysis_id"] = expected["analysis_id"]
    assert actual == expected


def test_request_size_limit_rejects_oversized_json() -> None:
    app = create_app(
        Settings(
            environment="test",
            llm_enabled=False,
            vector_store_enabled=False,
            max_request_bytes=1_024,
            log_json=False,
        )
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/analyses",
            json={
                "title": "Oversized",
                "description": "x" * 2_000,
                "amenities": [],
                "property_type": "Apartment",
                "location": {"city": "Miami", "country": "US"},
            },
        )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_too_large"


def test_production_app_hides_interactive_docs() -> None:
    app = create_app(
        Settings(
            environment="production",
            docs_enabled=False,
            auth_enabled=True,
            api_key=SecretStr("production-test-secret-32-chars"),
            allowed_hosts=["testserver"],
            llm_enabled=False,
            vector_store_enabled=False,
            log_json=False,
        )
    )
    with TestClient(app) as client:
        docs = client.get("/docs")
        schema = client.get("/openapi.json")

    assert docs.status_code == 404
    assert schema.status_code == 404


def test_unhandled_error_keeps_safe_envelope_correlation_and_security_headers() -> None:
    class ExplodingUseCase:
        async def execute(self, _listing: object) -> None:
            raise RuntimeError("internal failure")

    app = create_app(
        Settings(
            environment="test",
            llm_enabled=False,
            vector_store_enabled=False,
            log_json=False,
        )
    )
    app.state.analyze_listing_use_case = ExplodingUseCase()
    payload = {
        "title": "City apartment",
        "description": "A valid listing description with enough factual detail.",
        "amenities": [],
        "property_type": "Apartment",
        "location": {"city": "Miami", "country": "US"},
    }

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/analyses",
            json=payload,
            headers={"X-Request-ID": "error-request-123"},
        )

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_error",
            "message": "An unexpected error occurred.",
            "details": None,
        },
        "request_id": "error-request-123",
    }
    assert response.headers["x-request-id"] == "error-request-123"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"


def test_unsafe_request_id_is_not_reflected() -> None:
    app = create_app(
        Settings(
            environment="test",
            llm_enabled=False,
            vector_store_enabled=False,
            log_json=False,
        )
    )

    with TestClient(app) as client:
        response = client.get(
            "/health/live",
            headers={"X-Request-ID": "unsafe request id"},
        )

    returned_id = response.headers["x-request-id"]
    assert returned_id != "unsafe request id"
    assert str(UUID(returned_id)) == returned_id
