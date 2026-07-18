"""Validated runtime configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "test", "staging", "production"]


class Settings(BaseSettings):
    """Application settings with secure production invariants."""

    model_config = SettingsConfigDict(
        env_prefix="PIE_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Property Intelligence Engine"
    app_version: str = "0.1.0"
    environment: Environment = "local"
    api_prefix: str = "/api/v1"
    docs_enabled: bool = True
    auth_enabled: bool = False
    api_key: SecretStr | None = None

    allowed_hosts: list[str] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "testserver"]
    )
    cors_origins: list[str] = Field(default_factory=list)
    max_request_bytes: int = Field(default=65_536, ge=1_024, le=1_048_576)

    llm_enabled: bool = True
    llm_required: bool = False
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-5.6-sol"
    openai_embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = Field(default=1_536, ge=256, le=4_096)
    llm_timeout_seconds: float = Field(default=45.0, gt=0, le=180)
    llm_max_retries: int = Field(default=2, ge=0, le=5)

    vector_store_enabled: bool = True
    vector_store_required: bool = False
    qdrant_url: str = "http://qdrant:6333"
    qdrant_api_key: SecretStr | None = None
    qdrant_collection: str = "listing_guidance_v1"
    qdrant_timeout_seconds: int = Field(default=10, ge=1, le=60)
    retrieval_limit: int = Field(default=5, ge=1, le=10)

    sentry_dsn: SecretStr | None = None
    sentry_traces_sample_rate: float = Field(default=0.0, ge=0, le=1)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_json: bool = True

    @model_validator(mode="after")
    def enforce_runtime_invariants(self) -> Self:
        """Reject production settings that would expose unsafe defaults."""

        if self.environment == "production":
            if self.docs_enabled:
                raise ValueError("interactive API docs must be disabled in production")
            if not self.auth_enabled:
                raise ValueError("API authentication must be enabled in production")
            if self.api_key is None or not self.api_key.get_secret_value():
                raise ValueError("PIE_API_KEY is required when authentication is enabled")
            if len(self.api_key.get_secret_value()) < 24:
                raise ValueError("PIE_API_KEY must contain at least 24 characters in production")
            if any("*" in host for host in self.allowed_hosts):
                raise ValueError("wildcard allowed hosts are forbidden in production")
            if any("*" in origin for origin in self.cors_origins):
                raise ValueError("wildcard CORS origins are forbidden in production")

        if self.auth_enabled and (self.api_key is None or not self.api_key.get_secret_value()):
            raise ValueError("PIE_API_KEY is required when authentication is enabled")
        if self.llm_required and (
            not self.llm_enabled
            or self.openai_api_key is None
            or not self.openai_api_key.get_secret_value()
        ):
            raise ValueError("an OpenAI API key is required when LLM generation is required")
        if self.vector_store_required and not self.vector_store_enabled:
            raise ValueError("the vector store cannot be disabled when it is required")
        if self.vector_store_required and (
            self.openai_api_key is None or not self.openai_api_key.get_secret_value()
        ):
            raise ValueError("an OpenAI API key is required for the configured vector embeddings")
        return self

    @property
    def openai_key_value(self) -> str | None:
        """Reveal the OpenAI key only at the provider composition boundary."""

        value = self.openai_api_key.get_secret_value() if self.openai_api_key else ""
        return value or None

    @property
    def qdrant_key_value(self) -> str | None:
        """Reveal the Qdrant key only at the provider composition boundary."""

        value = self.qdrant_api_key.get_secret_value() if self.qdrant_api_key else ""
        return value or None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide validated settings instance."""

    return Settings()
