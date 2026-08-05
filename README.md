<p align="center">
  <img src="assets/branding/02-primary-dark.svg" alt="ClamAV REST" width="720">
</p>

# ClamAV HTTP Gateway

An asynchronous HTTP gateway for scanning untrusted data with ClamAV.

[GitHub](https://github.com/teudanrichard/clamav-rest) · [Docker Hub](https://hub.docker.com/r/rtlabsio/clamav-rest) · [Artifact Hub](https://artifacthub.io/packages/helm/clamav-rest/clamav-rest)

The API speaks ClamAV's framed `INSTREAM` protocol over TCP or a Unix socket, applies bounded concurrency and upload limits, and returns typed clean/infected results.

## Architecture

```text
client -> ingress/auth/rate limit -> gateway (non-root) -> clamd
                                      stateless          signature volume
```

The application and ClamAV run as separate containers. Each has one responsibility and its own lifecycle; the ClamAV signature database persists independently. The gateway never exposes the clamd port publicly in the supplied Compose configuration.

## Capabilities

- True constant-memory raw request streaming (`POST /scan/stream`)
- Conventional multipart file uploads (`POST /scan/file`)
- Configurable file-size, concurrency, queue, connect, and scan timeouts
- Detection signature reporting and ClamAV engine/database version reporting
- Separate liveness and dependency-readiness probes
- Unix socket support for same-pod sidecars and TCP support for separate services
- Non-root, read-only API container with dropped Linux capabilities
- Unit/protocol tests, dependency audit, linting, image build, and registry push in GitHub Actions
- Structured JSON request/scan logs, correlation IDs, and opt-in Prometheus metrics
- Real ClamAV clean/EICAR integration testing and hashed transitive dependency lock
- Runtime OpenAPI, Swagger UI, and ReDoc documentation

## Docker image

The published image is [`rtlabsio/clamav-rest`](https://hub.docker.com/r/rtlabsio/clamav-rest). See [DOCKERHUB_README.md](DOCKERHUB_README.md) for a ready-to-run Compose example.

## Start with Docker Compose

```sh
cp .env.example .env
docker compose up --build --wait
curl http://localhost:8000/health
curl http://localhost:8000/health/clamav
curl -F 'file=@document.pdf' http://localhost:8000/scan/file
curl --data-binary @document.pdf \
  -H 'Content-Type: application/octet-stream' \
  -H 'X-Filename: document.pdf' \
  http://localhost:8000/scan/stream
```

The first ClamAV startup can take several minutes while signatures are downloaded and loaded. Compose waits for the official ClamAV image health check before starting the gateway. API documentation is available at `http://localhost:8000/docs`.

Stop the stack without deleting signatures:

```sh
docker compose down
```

Use `docker compose down --volumes` only when you intentionally want to delete the signature database.

## API contract

| Method | Path | Meaning |
|---|---|---|
| `GET` | `/health` | Gateway process liveness; never checks ClamAV |
| `GET` | `/health/clamav` | Readiness check using ClamAV `PING` |
| `GET` | `/clamav/version` | Engine and signature database version |
| `GET` | `/metrics` | Prometheus metrics when explicitly enabled; keep private |
| `POST` | `/scan/stream` | Preferred raw-body streaming scan; optional `X-Filename` |
| `POST` | `/scan/file` | Multipart compatibility endpoint |

Clean and infected scans both return HTTP `200`; callers must inspect `status`:

```json
{
  "status": "infected",
  "engine": "clamav",
  "filename": "eicar.com",
  "size": 68,
  "signature": "Eicar-Test-Signature"
}
```

Errors use `{"detail":"..."}`. Important statuses are `413` for the gateway limit, `429` for an exhausted scan queue, `502` for a clamd scan/protocol error, `503` when clamd is unavailable, and `504` when the total scan deadline expires.

### Multipart versus raw streaming

Use `/scan/stream` for large or untrusted inputs. It forwards request chunks directly to clamd and enforces the byte limit while reading. `/scan/file` acquires bounded upload admission before parsing, accepts exactly one file field, and uses a spooled temporary file. The supplied container bounds temporary storage with `/tmp` tmpfs; the application and ingress both enforce limits.

## Configuration

Copy `.env.example`; all settings use environment variables.

New deployments should use the service-specific `CLAMR_` prefix. Legacy unprefixed names remain accepted for migration; when both are set, the prefixed value wins.

| Variable | Default | Description |
|---|---:|---|
| `CLAMR_BACKEND_SOCKET_PATH` | unset | Unix socket; when set, overrides TCP |
| `CLAMR_BACKEND_HOST` | `127.0.0.1` | clamd TCP hostname |
| `CLAMR_BACKEND_PORT` | `3310` | clamd TCP port |
| `CLAMR_SOCKET_CONNECT_TIMEOUT` | `3` | Connection timeout in seconds |
| `CLAMR_SOCKET_READ_TIMEOUT` | `30` | clamd response timeout in seconds |
| `CLAMR_SCAN_TIMEOUT` | `120` | Total upload and scan deadline in seconds |
| `CLAMR_MAX_UPLOAD_SIZE` | `26214400` | Maximum bytes forwarded per scan (25 MiB) |
| `CLAMR_STREAM_CHUNK_SIZE` | `65536` | ClamAV frame size |
| `CLAMR_MAX_CONCURRENT_SCANS` | `4` | Per-process scan concurrency |
| `CLAMR_MAX_CONCURRENT_UPLOADS` | `4` | Multipart parsers admitted per process |
| `CLAMR_SCAN_QUEUE_TIMEOUT` | `10` | Seconds to wait for capacity before `429` |
| `CLAMR_CORS_ORIGINS` | empty | Comma-separated browser origins; disabled when empty |
| `CLAMR_DOCS_ENABLED` | `true` | Serve OpenAPI and interactive documentation |
| `CLAMR_LOG_LEVEL` | `INFO` | Application log level |
| `CLAMR_METRICS_ENABLED` | `false` | Expose Prometheus metrics at `/metrics`; keep private |
| `CLAMR_OIDC_ENABLED` | `false` | Enable generic discovery-based bearer authentication |
| `CLAMR_OIDC_ISSUER_URL` | unset | Exact issuer and discovery base URL; required when enabled |
| `CLAMR_OIDC_AUDIENCE` | unset | Required API audience |
| `CLAMR_OIDC_CLIENT_ID` | unset | Optional required `azp` claim (useful with Keycloak) |
| `CLAMR_OIDC_ALLOWED_ALGORITHMS` | `RS256` | Comma-separated asymmetric JWT algorithms |
| `CLAMR_OIDC_JWKS_CACHE_TTL` | `300` | Seconds before JWKS refresh |
| `CLAMR_OIDC_JWKS_STALE_TTL` | `900` | Maximum stale-key fallback during provider outage |
| `CLAMR_OIDC_CLOCK_SKEW` | `30` | JWT clock-skew allowance in seconds |
| `CLAMR_OIDC_HTTP_TIMEOUT` | `5` | Discovery and JWKS HTTP timeout |

`CLAMR_MAX_UPLOAD_SIZE` must not exceed clamd's `StreamMaxLength`. If the gateway has multiple worker processes or replicas, total possible concurrency is workers × replicas × `CLAMR_MAX_CONCURRENT_SCANS`; size clamd's `MaxThreads` and memory accordingly.

## Optional OIDC authentication

OIDC is completely inactive (and its module is not imported) unless `CLAMR_OIDC_ENABLED=true`. When enabled, discovery must report the exact configured issuer and an HTTPS JWKS URI. The service verifies signature, algorithm allowlist, issuer, audience, expiry, issued-at time, and optional `azp`. Key rotation refreshes on an unknown `kid`; bounded stale keys preserve availability during short provider outages. Liveness and ClamAV readiness remain public for orchestrators; scan, version, and documentation routes require `Authorization: Bearer <token>`.

Generic providers and Keycloak realm issuers are supported. For Keycloak, set the issuer to `https://keycloak.example/realms/<realm>`, audience to the API audience mapper value, and optionally client ID to enforce `azp`. Startup fails closed if discovery or initial keys cannot be loaded.

## Kubernetes Helm deployment

A Helm chart is provided at `charts/clamav-rest` for the gateway, optional ClamAV sidecar service, persistent signatures, OIDC settings, Traefik Ingress, Gateway API, and optional monitoring/network policies. Run `helm lint charts/clamav-rest` and set an immutable image digest before production deployment.

Semantic-version tags (`vX.Y.Z`) publish the chart automatically to `oci://ghcr.io/teudanrichard/charts`. The chart repository is indexed by [Artifact Hub](https://artifacthub.io/) after the one-time repository registration.

## Production deployment

- Terminate TLS and enforce request-body and rate limits at ingress; `deploy/traefik.yml` and `deploy/traefik-dynamic.yml` is a reference. OIDC bearer validation is optional and enabled only with `CLAMR_OIDC_ENABLED=true`.
- Use `/health` as the liveness probe and `/health/clamav` as readiness. Do not restart a healthy API merely because signature loading is temporarily slow.
- Prefer `/scan/stream` and enforce the same or a smaller body limit at ingress.
- Keep ClamAV on a private network. Never publish port `3310` to an untrusted network; the clamd protocol has no authentication.
- Persist `/var/lib/clamav`, monitor signature freshness, and alert on repeated readiness or update failures.
- Disable interactive docs in externally exposed production deployments with `CLAMR_DOCS_ENABLED=false` if they are not needed.
- Pin images by digest in deployment manifests when reproducible promotion is required, and update those digests through an automated dependency process.

For Kubernetes, deploy clamd as a same-pod sidecar with a shared Unix socket or as a private service. Apply CPU/memory requests and limits based on representative archive scans; ClamAV is memory intensive and compressed inputs can be much more expensive than their upload size.

## Development

Python 3.11+ and a reachable clamd are required for live scans. Unit tests mock clamd; protocol tests validate exact framing.

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.lock
# Regenerate after intentional dependency updates:
# pip-compile --generate-hashes --strip-extras -o requirements.lock requirements.txt
# pip-compile --generate-hashes --strip-extras --allow-unsafe -o requirements-dev.lock requirements-dev.txt
cp .env.example .env
ruff check .
ruff format --check .
pytest
pip-audit --requirement requirements.lock
```

Run the API locally with `uvicorn app.main:app --reload`. GitHub Actions runs quality checks, real-ClamAV integration tests, builds and smoke-tests a commit-SHA image, audits dependencies, generates an SBOM, fails on HIGH/CRITICAL image findings, publishes to Docker Hub, and signs tagged releases. See `docs/production.md` for ingress, alerts, identity outages, and measured capacity guidance.

## Security

See `SECURITY.md`. Virus scanning reduces risk but does not prove that content is safe. Apply file-type validation, sandboxing, and content handling rules appropriate to the consuming system after a clean result.

## License

This project is licensed under the Apache License 2.0. See [LICENSE](LICENSE).

### Image versions and releases

The repository uses Semantic Versioning. `VERSION` is the source of truth for the application release and must match a release tag such as `v1.0.0`. Release pipelines publish the immutable commit-SHA image plus `1.0.0` and `v1.0.0` tags, attach the version to OCI metadata and the API version, generate an SBOM, scan the image, and sign both SemVer tags. Do not use `latest` for production promotion; deploy an exact SemVer or commit-SHA tag and verify its signature.
