# ClamAV REST

ClamAV REST is a production-oriented asynchronous HTTP gateway for scanning uploads with ClamAV.

- Source and issue tracker: https://github.com/teudanrichard/clamav-rest
- Helm chart and releases: https://artifacthub.io/
- Image: https://hub.docker.com/r/rtlabsio/clamav-rest

## Contents

- [Quick start](#quick-start)
- [Docker Compose](#docker-compose)
- [API examples](#api-examples)
- [Configuration](#configuration)
- [Security](#security)

## Quick start

Pull a specific semantic version for reproducible deployments:

```sh
docker pull rtlabsio/clamav-rest:1.0.1
```

The image contains the REST gateway only; ClamAV runs as a separate service.

## Docker Compose

```sh
curl -fsSLO https://raw.githubusercontent.com/teudanrichard/clamav-rest/main/compose.yaml
docker compose up -d --wait
curl http://localhost:8000/health
curl -F 'file=@document.pdf' http://localhost:8000/scan/file
```

For a pinned production deployment, replace the gateway image tag with a release digest and keep the ClamAV service on the private Compose network. A complete environment reference is in [`.env.example`](https://github.com/teudanrichard/clamav-rest/blob/main/.env.example).

## API examples

After starting Compose, check both liveness and ClamAV readiness:

```sh
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8000/health/clamav
```

Scan a file using multipart upload:

```sh
curl --fail-with-body -F 'file=@document.pdf' \
  http://localhost:8000/scan/file
```

The streaming endpoint accepts arbitrary request bodies:

```sh
curl --fail-with-body --data-binary @document.pdf \
  -H 'Content-Type: application/octet-stream' \
  http://localhost:8000/scan/stream
```

For interactive API documentation, enable `CLAMR_DOCS_ENABLED=true` and open `http://localhost:8000/docs`.

## Configuration

The gateway uses `CLAMR_*` environment variables. Important settings include `CLAMR_MAX_UPLOAD_SIZE`, `CLAMR_MAX_CONCURRENT_SCANS`, `CLAMR_SCAN_TIMEOUT`, `CLAMR_DOCS_ENABLED`, `CLAMR_METRICS_ENABLED`, and the optional `CLAMR_OIDC_*` settings. OIDC is disabled by default and its module is not loaded unless `CLAMR_OIDC_ENABLED=true`.

## Security

Run the gateway behind TLS termination and authentication in production. Keep ClamAV port `3310` private because the clamd protocol has no authentication. Pin image digests, set upload and timeout limits, and leave CORS empty unless specific origins are required. OIDC is disabled by default and is activated only with `CLAMR_OIDC_ENABLED=true`.

## Health and API

- `GET /health` — liveness
- `GET /health/clamav` — ClamAV readiness
- `POST /scan/file` — multipart upload
- `POST /scan/stream` — streaming upload

See the [project documentation](https://github.com/teudanrichard/clamav-rest) for API details, security guidance, Kubernetes deployment, and release notes. Do not expose ClamAV port 3310 directly.
