"""Authentication boundary with no optional OIDC imports."""

from typing import Annotated, Protocol

from fastapi import Header, HTTPException, Request, status


class Authenticator(Protocol):
    async def authenticate(self, authorization: str | None) -> dict[str, object]: ...

    async def close(self) -> None: ...


async def require_auth(
    request: Request, authorization: Annotated[str | None, Header()] = None
) -> None:
    """Authenticate protected routes when an authenticator is configured."""
    authenticator: Authenticator | None = request.app.state.authenticator
    if authenticator is None:
        return
    try:
        request.state.claims = await authenticator.authenticate(authorization)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "authentication service unavailable"
        ) from exc
