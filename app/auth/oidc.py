"""Lazy-loaded generic OIDC discovery and JWT verification."""

import asyncio
import logging
import time
from typing import Any

import httpx
import jwt
from fastapi import HTTPException, status

from app.config import Settings

LOGGER = logging.getLogger("clamr.auth")


def _unauthorized(error: str = "invalid_token") -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "invalid or missing bearer token",
        headers={"WWW-Authenticate": f'Bearer error="{error}"'},
    )


class OIDCAuthenticator:
    """Validate access tokens using issuer discovery and a bounded JWKS cache."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.client = client or httpx.AsyncClient(timeout=settings.oidc_http_timeout)
        self._owns_client = client is None
        self._jwks_uri = ""
        self._keys: dict[str, Any] = {}
        self._refreshed_at = 0.0
        self._refresh_lock = asyncio.Lock()

    async def start(self) -> None:
        issuer = str(self.settings.oidc_issuer_url).rstrip("/")
        response = await self.client.get(f"{issuer}/.well-known/openid-configuration")
        response.raise_for_status()
        metadata = response.json()
        if metadata.get("issuer", "").rstrip("/") != issuer:
            raise RuntimeError("OIDC discovery issuer does not match configured issuer")
        jwks_uri = metadata.get("jwks_uri")
        if not isinstance(jwks_uri, str) or not jwks_uri.startswith("https://"):
            raise RuntimeError("OIDC discovery returned an invalid JWKS URI")
        self._jwks_uri = jwks_uri
        await self._refresh_keys(required=True)

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def _refresh_keys(self, required: bool) -> None:
        async with self._refresh_lock:
            try:
                response = await self.client.get(self._jwks_uri)
                response.raise_for_status()
                keys = response.json().get("keys", [])
                parsed = {
                    item["kid"]: jwt.PyJWK.from_dict(item)
                    for item in keys
                    if isinstance(item, dict) and isinstance(item.get("kid"), str)
                }
                if not parsed:
                    raise RuntimeError("OIDC provider returned no usable JWKS keys")
                self._keys = parsed
                self._refreshed_at = time.monotonic()
            except Exception:
                stale_age = time.monotonic() - self._refreshed_at
                can_use_stale = self._keys and stale_age <= self.settings.oidc_jwks_stale_ttl
                if required or not can_use_stale:
                    raise
                LOGGER.warning("using stale OIDC keys after refresh failure")

    async def _key(self, kid: str) -> Any:
        age = time.monotonic() - self._refreshed_at
        if age >= self.settings.oidc_jwks_cache_ttl:
            await self._refresh_keys(required=False)
        key = self._keys.get(kid)
        if key is None:
            await self._refresh_keys(required=True)
            key = self._keys.get(kid)
        if key is None:
            raise _unauthorized()
        return key

    async def authenticate(self, authorization: str | None) -> dict[str, object]:
        if not authorization or not authorization.startswith("Bearer "):
            raise _unauthorized("invalid_request")
        token = authorization[7:].strip()
        if not token or " " in token:
            raise _unauthorized("invalid_request")
        try:
            header = jwt.get_unverified_header(token)
            algorithm = header.get("alg")
            kid = header.get("kid")
            if algorithm not in self.settings.oidc_allowed_algorithms or not isinstance(kid, str):
                raise _unauthorized()
            pyjwk = await self._key(kid)
            claims = jwt.decode(
                token,
                key=pyjwk.key,
                algorithms=self.settings.oidc_allowed_algorithms,
                audience=self.settings.oidc_audience,
                issuer=str(self.settings.oidc_issuer_url).rstrip("/"),
                leeway=self.settings.oidc_clock_skew,
                options={"require": ["exp", "iat", "iss", "aud"]},
            )
            if self.settings.oidc_client_id and claims.get("azp") != self.settings.oidc_client_id:
                raise _unauthorized()
            return claims
        except HTTPException:
            raise
        except jwt.PyJWTError as exc:
            raise _unauthorized() from exc
