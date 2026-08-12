# Production operations

Use the reference `deploy/traefik.yml` and `deploy/traefik-dynamic.yml` as a starting point: enforce TLS, a body limit no larger than `CLAMR_MAX_UPLOAD_SIZE`, request and connection rates, disabled request buffering for `/scan/stream`, and an upstream timeout slightly above `CLAMR_SCAN_TIMEOUT`. Trust forwarded headers only from the ingress network; the example deliberately replaces rather than accepts a client-supplied forwarding chain.

Alert when readiness failures persist for five minutes, `clamr_scan_results_total{result="queue_timeout"}` increases, p95 queue duration approaches `CLAMR_SCAN_QUEUE_TIMEOUT`, or ClamAV signatures are older than your security policy. Scrape `/metrics` only on a private service. Monitor clamd RSS and signature-volume capacity.

Capacity must be measured with representative PDFs, office files, executables, and nested/compressed archives. Run `python scripts/load_test.py sample.zip --requests 100 --concurrency 4`, record p95/p99 and container memory, then set CPU/memory requests and limits with headroom. Total scan concurrency equals replicas × workers × `CLAMR_MAX_CONCURRENT_SCANS`; it must not exceed clamd capacity. Keep one application worker per container unless this multiplication is intentional.

On identity-provider outages, already cached keys remain usable only for `CLAMR_OIDC_JWKS_STALE_TTL`; unknown signing keys fail closed. Plan rotations with an overlap longer than the cache TTL. `/health` and `/health/clamav` stay unauthenticated for orchestrators; scan, version, and documentation routes require a token when OIDC is enabled.

CI audits locked Python dependencies, emits a CycloneDX SBOM for the final image, scans the final image and fails on unfixed HIGH/CRITICAL findings, and retains artifacts. Publishing is isolated in the protected `production` environment. Tagged releases receive GitHub OIDC provenance and SBOM attestations plus a keyless Cosign signature, all bound to the exact immutable image digest.

Verify a release before promotion:

```sh
gh attestation verify oci://docker.io/rtlabsio/clamav-rest:v1.0.4 --owner teudanrichard
cosign verify \
  --certificate-identity-regexp '^https://github.com/teudanrichard/clamav-rest/.github/workflows/ci.yml@refs/tags/v[0-9]+\\.[0-9]+\\.[0-9]+$' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  docker.io/rtlabsio/clamav-rest:v1.0.4
```

Promote and roll back by digest, never by moving an existing release tag. Record the previously deployed digest before promotion; rollback consists of restoring that digest in Compose or `image.digest` in Helm and redeploying. If any publish job fails after a tag is created, do not move or recreate the tag: correct the failure and rerun the original workflow so every artifact remains tied to the same source commit.
