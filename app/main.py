"""FastAPI application exposing safe ClamAV operations over HTTP."""

import asyncio
import logging
import re
import time
from collections.abc import AsyncIterable, AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import JSONResponse
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from app.auth import require_auth
from app.config import Settings, get_settings
from app.models import (
    ClamAVHealth,
    ErrorResponse,
    HealthStatus,
    ScanResult,
    VersionInfo,
    VersionParts,
)
from app.observability import (
    SCAN_DURATION,
    SCAN_QUEUE_DURATION,
    SCAN_RESULTS,
    SCANS_IN_PROGRESS,
    ObservabilityMiddleware,
    configure_logging,
    current_request_id,
    metrics_app,
)
from app.socket_client import BackendSocketClient, ClamAVUnavailable, UploadTooLarge

VERSION_RE = re.compile(r"ClamAV\s+(\d+)\.(\d+)\.(\d+)(?:/(\d+))?")
BACKEND_ERROR = {503: {"model": ErrorResponse, "description": "ClamAV is unavailable"}}
SCAN_ERRORS = {
    413: {"model": ErrorResponse, "description": "Upload exceeds the configured limit"},
    429: {"model": ErrorResponse, "description": "The scan queue is full"},
    502: {"model": ErrorResponse, "description": "ClamAV rejected or could not scan the data"},
    504: {"model": ErrorResponse, "description": "The scan exceeded its deadline"},
    **BACKEND_ERROR,
}
MULTIPART_OVERHEAD_ALLOWANCE = 1024 * 1024


class MultipartBodyTooLarge(MultiPartException):
    """Signal a bounded multipart parser overflow while preserving tempfile cleanup."""


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build an application instance, allowing isolated settings in tests."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    logger = logging.getLogger("clamr.scan")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.clamav = BackendSocketClient(settings)
        app.state.scan_slots = asyncio.Semaphore(settings.max_concurrent_scans)
        app.state.upload_slots = asyncio.Semaphore(settings.max_concurrent_uploads)
        app.state.authenticator = None
        try:
            if settings.oidc_enabled:
                from app.auth.oidc import OIDCAuthenticator

                app.state.authenticator = OIDCAuthenticator(settings)
                await app.state.authenticator.start()
            yield
        finally:
            if app.state.authenticator is not None:
                await app.state.authenticator.close()

    app = FastAPI(
        title=settings.project_name,
        version=settings.version,
        description="Asynchronous HTTP gateway for scanning data with ClamAV.",
        debug=settings.debug,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    protected = APIRouter(dependencies=[Depends(require_auth)])
    app.add_middleware(ObservabilityMiddleware)
    if settings.metrics_enabled:
        app.mount("/metrics", metrics_app)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["Accept", "Content-Type", "X-Filename"],
        )

    def get_client(request: Request) -> BackendSocketClient:
        return request.app.state.clamav

    ClamAVClient = Annotated[BackendSocketClient, Depends(get_client)]

    @app.get("/health", response_model=HealthStatus, tags=["health"])
    async def health() -> HealthStatus:
        """Report API process liveness without depending on ClamAV."""
        return HealthStatus()

    @app.get(
        "/health/clamav", response_model=ClamAVHealth, responses=BACKEND_ERROR, tags=["health"]
    )
    async def clamav_health(clamav: ClamAVClient) -> ClamAVHealth:
        """Report readiness after checking the ClamAV daemon."""
        try:
            response = await clamav.ping()
            if response != "PONG":
                raise ClamAVUnavailable(f"unexpected PING response: {response}")
            return ClamAVHealth(clamav=response)
        except ClamAVUnavailable as exc:
            logger.warning("ClamAV readiness check failed", exc_info=exc)
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "ClamAV is unavailable"
            ) from exc

    @protected.get(
        "/clamav/version", response_model=VersionInfo, responses=BACKEND_ERROR, tags=["clamav"]
    )
    async def clamav_version(clamav: ClamAVClient) -> VersionInfo:
        """Return raw and parsed engine/signature database version information."""
        try:
            raw = await clamav.version()
        except ClamAVUnavailable as exc:
            logger.warning("ClamAV version check failed", exc_info=exc)
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "ClamAV is unavailable"
            ) from exc
        match = VERSION_RE.search(raw)
        parsed = (
            VersionParts(
                major=int(match[1]),
                minor=int(match[2]),
                patch=int(match[3]),
                database_version=int(match[4]) if match[4] else None,
            )
            if match
            else None
        )
        return VersionInfo(engine_version=raw.split("/")[0], parsed=parsed, raw=raw)

    async def perform_scan(
        request: Request,
        clamav: BackendSocketClient,
        chunks: AsyncIterable[bytes],
        filename: str | None,
    ) -> ScanResult:
        queue_started = time.monotonic()
        try:
            await asyncio.wait_for(
                request.app.state.scan_slots.acquire(), timeout=settings.scan_queue_timeout
            )
        except TimeoutError as exc:
            SCAN_QUEUE_DURATION.observe(time.monotonic() - queue_started)
            SCAN_RESULTS.labels("queue_timeout").inc()
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS, "scan capacity is currently exhausted"
            ) from exc
        queue_duration = time.monotonic() - queue_started
        SCAN_QUEUE_DURATION.observe(queue_duration)
        scan_started = time.monotonic()
        SCANS_IN_PROGRESS.inc()
        try:
            async with asyncio.timeout(settings.scan_timeout):
                raw, size = await clamav.scan_stream(chunks, settings.max_upload_size)
        except UploadTooLarge as exc:
            SCAN_RESULTS.labels("too_large").inc()
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(exc)) from exc
        except ClamAVUnavailable as exc:
            logger.warning("ClamAV unavailable during scan", exc_info=exc)
            SCAN_RESULTS.labels("unavailable").inc()
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "ClamAV is unavailable"
            ) from exc
        except TimeoutError as exc:
            SCAN_RESULTS.labels("timeout").inc()
            raise HTTPException(
                status.HTTP_504_GATEWAY_TIMEOUT,
                f"scan exceeded the {settings.scan_timeout:g}-second deadline",
            ) from exc
        finally:
            SCANS_IN_PROGRESS.dec()
            SCAN_DURATION.observe(time.monotonic() - scan_started)
            request.app.state.scan_slots.release()

        if raw.endswith(" OK"):
            result, signature = "clean", None
        elif raw.endswith(" FOUND"):
            result = "infected"
            signature = raw.removesuffix(" FOUND").partition(": ")[2] or "unknown"
        elif raw.endswith(" ERROR"):
            logger.warning("ClamAV returned a scan error")
            SCAN_RESULTS.labels("error").inc()
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "ClamAV could not scan the data")
        else:
            logger.error("ClamAV returned an unexpected protocol response")
            SCAN_RESULTS.labels("protocol_error").inc()
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "invalid response from ClamAV")
        SCAN_RESULTS.labels(result).inc()
        logger.info(
            "scan completed",
            extra={
                "request_id": current_request_id(),
                "result": result,
                "size": size,
                "queue_duration_ms": round(queue_duration * 1000, 2),
            },
        )
        return ScanResult(
            status=result,
            filename=filename,
            size=size,
            signature=signature,
        )

    @protected.post("/scan/file", response_model=ScanResult, responses=SCAN_ERRORS, tags=["scan"])
    async def scan_file(request: Request, clamav: ClamAVClient) -> ScanResult:
        """Scan one bounded multipart file after acquiring upload admission capacity."""
        try:
            await asyncio.wait_for(
                request.app.state.upload_slots.acquire(), timeout=settings.scan_queue_timeout
            )
        except TimeoutError as exc:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS, "upload capacity is currently exhausted"
            ) from exc
        try:
            body_limit = settings.max_upload_size + MULTIPART_OVERHEAD_ALLOWANCE

            async def bounded_body() -> AsyncIterator[bytes]:
                received = 0
                async for chunk in request.stream():
                    received += len(chunk)
                    if received > body_limit:
                        raise MultipartBodyTooLarge(
                            f"multipart body exceeds the {body_limit}-byte transport limit"
                        )
                    yield chunk

            parser = MultiPartParser(
                headers=request.headers,
                stream=bounded_body(),
                max_files=1,
                max_fields=0,
                max_part_size=settings.max_upload_size,
            )
            try:
                form = await parser.parse()
            except MultipartBodyTooLarge as exc:
                raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(exc)) from exc
            except MultiPartException as exc:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
            try:
                candidate = form.get("file")
                if not isinstance(candidate, UploadFile):
                    raise HTTPException(
                        status.HTTP_422_UNPROCESSABLE_CONTENT,
                        "multipart request must contain one file field named file",
                    )
                file = candidate

                async def chunks() -> AsyncIterator[bytes]:
                    while chunk := await file.read(settings.stream_chunk_size):
                        yield chunk

                return await perform_scan(request, clamav, chunks(), file.filename)
            finally:
                await form.close()
        finally:
            request.app.state.upload_slots.release()

    @protected.post("/scan/stream", response_model=ScanResult, responses=SCAN_ERRORS, tags=["scan"])
    async def scan_stream(
        request: Request,
        clamav: ClamAVClient,
        x_filename: Annotated[str | None, Header()] = None,
    ) -> ScanResult:
        """Scan a raw request body with constant gateway memory and no multipart spooling."""
        content_length = request.headers.get("content-length")
        try:
            declared_size = int(content_length) if content_length else None
        except ValueError as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "invalid Content-Length header"
            ) from exc
        if declared_size is not None and declared_size > settings.max_upload_size:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE,
                f"file exceeds the {settings.max_upload_size}-byte upload limit",
            )
        return await perform_scan(request, clamav, request.stream(), x_filename)

    if settings.docs_enabled:

        @protected.get("/openapi.json", include_in_schema=False)
        async def openapi_schema() -> JSONResponse:
            return JSONResponse(app.openapi())

        @protected.get("/docs", include_in_schema=False)
        async def swagger_docs():
            return get_swagger_ui_html(
                openapi_url="/openapi.json", title=f"{app.title} - Swagger UI"
            )

        @protected.get("/redoc", include_in_schema=False)
        async def redoc_docs():
            return get_redoc_html(openapi_url="/openapi.json", title=f"{app.title} - ReDoc")

    app.include_router(protected)
    return app


app = create_app()
