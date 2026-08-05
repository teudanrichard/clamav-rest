"""Validated application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import (
    AliasChoices,
    AliasGenerator,
    AnyHttpUrl,
    Field,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.version import __version__


class Settings(BaseSettings):
    """Runtime configuration for the API and its ClamAV connection."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
        alias_generator=AliasGenerator(
            validation_alias=lambda name: AliasChoices(f"CLAMR_{name.upper()}", name.upper())
        ),
    )

    project_name: str = "ClamAV HTTP Gateway"
    version: str = __version__
    debug: bool = False
    docs_enabled: bool = True
    backend_socket_path: str | None = None
    backend_host: str = "127.0.0.1"
    backend_port: int = Field(default=3310, ge=1, le=65535)
    socket_connect_timeout: float = Field(default=3.0, gt=0)
    socket_read_timeout: float = Field(default=30.0, gt=0)
    scan_timeout: float = Field(default=120.0, gt=0)
    max_upload_size: int = Field(default=25 * 1024 * 1024, gt=0)
    stream_chunk_size: int = Field(default=64 * 1024, ge=1024, le=1024 * 1024)
    max_concurrent_scans: int = Field(default=4, ge=1, le=100)
    max_concurrent_uploads: int = Field(default=4, ge=1, le=100)
    scan_queue_timeout: float = Field(default=10.0, gt=0)
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    metrics_enabled: bool = False
    oidc_enabled: bool = False
    oidc_issuer_url: AnyHttpUrl | None = None
    oidc_audience: str | None = None
    oidc_client_id: str | None = None
    oidc_required_scopes: Annotated[list[str], NoDecode] = Field(default_factory=list)
    oidc_allowed_algorithms: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["RS256"]
    )
    oidc_jwks_cache_ttl: int = Field(default=300, ge=30)
    oidc_jwks_stale_ttl: int = Field(default=900, ge=30)
    oidc_clock_skew: int = Field(default=30, ge=0, le=300)
    oidc_http_timeout: float = Field(default=5.0, gt=0)

    @field_validator("oidc_issuer_url", "oidc_audience", "oidc_client_id", mode="before")
    @classmethod
    def empty_optional_oidc_values_are_unset(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator(
        "cors_origins", "oidc_allowed_algorithms", "oidc_required_scopes", mode="before"
    )
    @classmethod
    def parse_origins(cls, value: object) -> object:
        if isinstance(value, str) and not value.lstrip().startswith("["):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def validate_sizes(self) -> "Settings":
        if self.stream_chunk_size > self.max_upload_size:
            raise ValueError("STREAM_CHUNK_SIZE cannot exceed MAX_UPLOAD_SIZE")
        if self.oidc_enabled and (not self.oidc_issuer_url or not self.oidc_audience):
            raise ValueError("OIDC_ISSUER_URL and OIDC_AUDIENCE are required when OIDC is enabled")
        if not self.oidc_allowed_algorithms or any(
            alg not in {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}
            for alg in self.oidc_allowed_algorithms
        ):
            raise ValueError("OIDC_ALLOWED_ALGORITHMS contains an unsafe or unsupported algorithm")
        if any(
            any(character.isspace() for character in scope) for scope in self.oidc_required_scopes
        ):
            raise ValueError("OIDC_REQUIRED_SCOPES entries cannot contain whitespace")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance for the process."""
    return Settings()
