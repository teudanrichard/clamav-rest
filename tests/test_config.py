import pytest
from pydantic import ValidationError

from app.config import Settings


def test_comma_separated_cors_origins(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://one.example, https://two.example")
    settings = Settings()
    assert settings.cors_origins == ["https://one.example", "https://two.example"]


def test_empty_cors_environment(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "")
    assert Settings().cors_origins == []


def test_prefixed_environment_takes_precedence(monkeypatch):
    monkeypatch.setenv("BACKEND_HOST", "legacy")
    monkeypatch.setenv("CLAMR_BACKEND_HOST", "preferred")
    assert Settings().backend_host == "preferred"


def test_oidc_requires_issuer_and_audience():
    with pytest.raises(ValidationError, match="required"):
        Settings(oidc_enabled=True)


def test_oidc_algorithms_are_parsed_and_restricted(monkeypatch):
    monkeypatch.setenv("CLAMR_OIDC_ALLOWED_ALGORITHMS", "RS256,ES256")
    assert Settings().oidc_allowed_algorithms == ["RS256", "ES256"]
    with pytest.raises(ValidationError, match="unsafe"):
        Settings(oidc_allowed_algorithms=["none"])


def test_chunk_cannot_exceed_upload_limit():
    with pytest.raises(ValidationError):
        Settings(max_upload_size=1024, stream_chunk_size=2048)


def test_application_version_comes_from_version_file():
    from app.version import __version__

    assert Settings().version == __version__
    assert __version__.count(".") == 2
