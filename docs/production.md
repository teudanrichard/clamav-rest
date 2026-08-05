# Production operations

Use the reference `deploy/traefik.yml` and `deploy/traefik-dynamic.yml` as a starting point: enforce TLS, a body limit no larger than `CLAMR_MAX_UPLOAD_SIZE`, request and connection rates, disabled request buffering for `/scan/stream`, and an upstream timeout slightly above `CLAMR_SCAN_TIMEOUT`. Trust forwarded headers only from the ingress network; the example deliberately replaces rather than accepts a client-supplied forwarding chain.

Alert when readiness failures persist for five minutes, `clamr_scan_results_total{result="queue_timeout"}` increases, p95 queue duration approaches `CLAMR_SCAN_QUEUE_TIMEOUT`, or ClamAV signatures are older than your security policy. Scrape `/metrics` only on a private service. Monitor clamd RSS and signature-volume capacity.

Capacity must be measured with representative PDFs, office files, executables, and nested/compressed archives. Run `python scripts/load_test.py sample.zip --requests 100 --concurrency 4`, record p95/p99 and container memory, then set CPU/memory requests and limits with headroom. Total scan concurrency equals replicas × workers × `CLAMR_MAX_CONCURRENT_SCANS`; it must not exceed clamd capacity. Keep one application worker per container unless this multiplication is intentional.

On identity-provider outages, already cached keys remain usable only for `CLAMR_OIDC_JWKS_STALE_TTL`; unknown signing keys fail closed. Plan rotations with an overlap longer than the cache TTL. `/health` and `/health/clamav` stay unauthenticated for orchestrators; scan, version, and documentation routes require a token when OIDC is enabled.

CI audits locked Python dependencies, emits a CycloneDX SBOM for the final image, scans the final image and fails on unfixed HIGH/CRITICAL findings, and retains artifacts. Tagged releases can use GitHub OIDC keyless signing with Cosign; protect release tags and verify the signature and provenance before promotion.
