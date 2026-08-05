"""Typed public API response models."""

from typing import Literal

from pydantic import BaseModel, Field


class HealthStatus(BaseModel):
    status: Literal["ok"] = "ok"


class ClamAVHealth(HealthStatus):
    clamav: str = Field(examples=["PONG"])


class VersionParts(BaseModel):
    major: int
    minor: int
    patch: int
    database_version: int | None = None


class VersionInfo(BaseModel):
    engine_version: str
    parsed: VersionParts | None
    raw: str


class ScanResult(BaseModel):
    status: Literal["clean", "infected"]
    engine: Literal["clamav"] = "clamav"
    filename: str | None
    size: int = Field(ge=0)
    signature: str | None = None


class ErrorResponse(BaseModel):
    detail: str
