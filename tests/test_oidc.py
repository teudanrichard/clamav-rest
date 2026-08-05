import base64
import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from app.auth.oidc import OIDCAuthenticator
from app.config import Settings

ISSUER = "https://id.example/realms/clamr"
AUDIENCE = "clamr-api"


def encoded(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def keypair(kid: str):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = private.public_key().public_numbers()
    return private, {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": kid,
        "n": encoded(numbers.n),
        "e": encoded(numbers.e),
    }


def token(private, kid="key-1", **overrides):
    now = int(time.time())
    claims = {
        "sub": "user-1",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + 300,
        **overrides,
    }
    return jwt.encode(claims, private, algorithm="RS256", headers={"kid": kid})


def settings(**overrides):
    return Settings(oidc_enabled=True, oidc_issuer_url=ISSUER, oidc_audience=AUDIENCE, **overrides)


def transport_for(jwks_sequences, issuer=ISSUER):
    calls = {"jwks": 0}

    async def handler(request):
        if request.url.path.endswith("openid-configuration"):
            return httpx.Response(200, json={"issuer": issuer, "jwks_uri": f"{ISSUER}/keys"})
        if request.url.path.endswith("/keys"):
            index = min(calls["jwks"], len(jwks_sequences) - 1)
            calls["jwks"] += 1
            value = jwks_sequences[index]
            if isinstance(value, Exception):
                raise value
            return httpx.Response(200, json={"keys": value})
        return httpx.Response(404)

    return httpx.MockTransport(handler), calls


@pytest.mark.asyncio
async def test_valid_keycloak_shaped_token_and_client_id():
    private, public = keypair("key-1")
    transport, _ = transport_for([[public]])
    async with httpx.AsyncClient(transport=transport) as client:
        auth = OIDCAuthenticator(settings(oidc_client_id="clamr-client"), client)
        await auth.start()
        claims = await auth.authenticate("Bearer " + token(private, azp="clamr-client"))
    assert claims["sub"] == "user-1"


@pytest.mark.asyncio
@pytest.mark.parametrize("headers", [None, "Basic abc", "Bearer", "Bearer a b"])
async def test_missing_or_malformed_authorization_is_401(headers):
    private, public = keypair("key-1")
    transport, _ = transport_for([[public]])
    async with httpx.AsyncClient(transport=transport) as client:
        auth = OIDCAuthenticator(settings(), client)
        await auth.start()
        with pytest.raises(HTTPException) as error:
            await auth.authenticate(headers)
    assert error.value.status_code == 401
    assert error.value.headers["WWW-Authenticate"].startswith("Bearer")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"aud": "wrong"},
        {"iss": "https://other.example"},
        {"exp": 1},
        {"iat": int(time.time()) + 600},
        {"nbf": int(time.time()) + 600},
    ],
)
async def test_invalid_claims_are_rejected(changes):
    private, public = keypair("key-1")
    transport, _ = transport_for([[public]])
    async with httpx.AsyncClient(transport=transport) as client:
        auth = OIDCAuthenticator(settings(oidc_clock_skew=0), client)
        await auth.start()
        with pytest.raises(HTTPException) as error:
            await auth.authenticate("Bearer " + token(private, **changes))
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_unknown_kid_triggers_rotation_refresh():
    old_private, old_public = keypair("old")
    new_private, new_public = keypair("new")
    transport, calls = transport_for([[old_public], [old_public, new_public]])
    async with httpx.AsyncClient(transport=transport) as client:
        auth = OIDCAuthenticator(settings(), client)
        await auth.start()
        claims = await auth.authenticate("Bearer " + token(new_private, kid="new"))
    assert claims["sub"] == "user-1"
    assert calls["jwks"] == 2
    assert old_private


@pytest.mark.asyncio
async def test_stale_keys_survive_temporary_provider_outage():
    private, public = keypair("key-1")
    transport, _ = transport_for([[public], httpx.ConnectError("offline")])
    async with httpx.AsyncClient(transport=transport) as client:
        auth = OIDCAuthenticator(settings(oidc_jwks_cache_ttl=30), client)
        await auth.start()
        auth._refreshed_at -= 31
        claims = await auth.authenticate("Bearer " + token(private))
    assert claims["sub"] == "user-1"


@pytest.mark.asyncio
async def test_required_scopes_are_enforced():
    private, public = keypair("key-1")
    transport, _ = transport_for([[public]])
    async with httpx.AsyncClient(transport=transport) as client:
        auth = OIDCAuthenticator(settings(oidc_required_scopes=["scan"]), client)
        await auth.start()
        with pytest.raises(HTTPException) as error:
            await auth.authenticate("Bearer " + token(private, scope="profile"))
        claims = await auth.authenticate("Bearer " + token(private, scope="profile scan"))
    assert error.value.status_code == 403
    assert claims["sub"] == "user-1"


@pytest.mark.asyncio
async def test_discovery_issuer_mismatch_fails_startup():
    _, public = keypair("key-1")
    transport, _ = transport_for([[public]], issuer="https://evil.example")
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(RuntimeError, match="issuer"):
            await OIDCAuthenticator(settings(), client).start()
