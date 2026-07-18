from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from property_intelligence.infrastructure.config import Settings


def test_local_settings_are_safe_and_provider_optional() -> None:
    settings = Settings(environment="local")

    assert settings.auth_enabled is False
    assert settings.openai_key_value is None
    assert "*" not in settings.allowed_hosts


def test_production_requires_disabled_docs_and_authentication() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="production")


def test_valid_production_configuration() -> None:
    settings = Settings(
        environment="production",
        docs_enabled=False,
        auth_enabled=True,
        api_key=SecretStr("a-long-production-api-key"),
        allowed_hosts=["api.example.com"],
    )

    assert settings.environment == "production"
    assert settings.docs_enabled is False


def test_production_rejects_short_service_api_key() -> None:
    with pytest.raises(ValidationError, match="at least 24 characters"):
        Settings(
            environment="production",
            docs_enabled=False,
            auth_enabled=True,
            api_key=SecretStr("short-service-key"),
            allowed_hosts=["api.example.com"],
        )


@pytest.mark.parametrize("field", ["allowed_hosts", "cors_origins"])
def test_production_forbids_wildcard_host_configuration(field: str) -> None:
    values = {
        "environment": "production",
        "docs_enabled": False,
        "auth_enabled": True,
        "api_key": SecretStr("a-long-production-api-key"),
        "allowed_hosts": ["api.example.com"],
        field: ["*"],
    }
    with pytest.raises(ValidationError):
        Settings(**values)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("allowed_hosts", "*.example.com"),
        ("cors_origins", "https://*.example.com"),
    ],
)
def test_production_forbids_embedded_wildcards(field: str, value: str) -> None:
    values = {
        "environment": "production",
        "docs_enabled": False,
        "auth_enabled": True,
        "api_key": SecretStr("a-long-production-api-key"),
        "allowed_hosts": ["api.example.com"],
        field: [value],
    }

    with pytest.raises(ValidationError):
        Settings(**values)


def test_required_llm_needs_credentials() -> None:
    with pytest.raises(ValidationError):
        Settings(llm_required=True, openai_api_key=None)
