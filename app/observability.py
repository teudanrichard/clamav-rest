"""Structured logging, request correlation, and bounded-cardinality metrics."""

import json
import logging
import re
import time
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime

from prometheus_client import Counter, Gauge, Histogram, make_asgi_app
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_CONTEXT: ContextVar[str | None] = ContextVar("request_id", default=None)
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
HTTP_REQUESTS = Counter("clamr_http_requests_total", "HTTP requests", ("method", "path", "status"))
HTTP_DURATION = Histogram(
    "clamr_http_request_duration_seconds", "HTTP request duration", ("method", "path")
)
HTTP_IN_PROGRESS = Gauge("clamr_http_requests_in_progress", "HTTP requests in progress")
SCAN_QUEUE_DURATION = Histogram("clamr_scan_queue_duration_seconds", "Scan queue wait time")
SCAN_DURATION = Histogram("clamr_scan_duration_seconds", "ClamAV scan duration")
SCANS_IN_PROGRESS = Gauge("clamr_scans_in_progress", "ClamAV scans in progress")
SCAN_RESULTS = Counter("clamr_scan_results_total", "Scan outcomes", ("result",))


class JsonFormatter(logging.Formatter):
    """Format application logs for container log collectors."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in (
            "request_id",
            "method",
            "path",
            "status_code",
            "duration_ms",
            "queue_duration_ms",
            "result",
            "size",
        ):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, separators=(",", ":"))


def configure_logging(level: str) -> None:
    """Configure only this service's logger hierarchy."""
    logger = logging.getLogger("clamr")
    logger.setLevel(level)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)


class ObservabilityMiddleware:
    """Correlate and measure HTTP requests without buffering their bodies."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.logger = logging.getLogger("clamr.http")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        supplied_id = headers.get(b"x-request-id", b"").decode("ascii", errors="ignore")
        request_id = supplied_id if REQUEST_ID_RE.fullmatch(supplied_id) else str(uuid.uuid4())
        method = scope.get("method", "UNKNOWN")
        path = "unmatched"
        status_code = 500
        started = time.monotonic()
        request_id_token = REQUEST_ID_CONTEXT.set(request_id)
        HTTP_IN_PROGRESS.inc()

        async def send_with_context(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_headers = list(message.get("headers", []))
                response_headers.append((b"x-request-id", request_id.encode("ascii")))
                message["headers"] = response_headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_context)
        finally:
            route = scope.get("route")
            path = getattr(route, "path", "unmatched")
            duration = time.monotonic() - started
            REQUEST_ID_CONTEXT.reset(request_id_token)
            HTTP_IN_PROGRESS.dec()
            HTTP_REQUESTS.labels(method, path, str(status_code)).inc()
            HTTP_DURATION.labels(method, path).observe(duration)
            self.logger.info(
                "request completed",
                extra={
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                    "duration_ms": round(duration * 1000, 2),
                },
            )


def current_request_id() -> str | None:
    """Return the correlation ID for the active request, if any."""
    return REQUEST_ID_CONTEXT.get()


metrics_app = make_asgi_app()
