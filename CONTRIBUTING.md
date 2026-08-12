# Contributing

Bug reports and focused pull requests are welcome. For security issues, follow [SECURITY.md](SECURITY.md) instead of opening a public issue.

## Development

Use Python 3.13 to match CI, install `requirements-dev.lock` with hashes, and copy `.env.example` to `.env`. Before submitting a change, run:

```sh
pip install --require-hashes -r requirements-dev.lock
ruff check .
ruff format --check .
pytest -W error
docker compose config --quiet
helm lint charts/clamav-rest
helm template clamr charts/clamav-rest > /dev/null
```

Add tests for behavior changes and update the README, example environment, Helm values, schema, and chart documentation when introducing configuration. Keep the gateway stateless: fetching remote files, quarantine storage, and durable job queues are outside its intended boundary.

## Dependency updates

Dependabot checks Python requirements, the pinned Docker base image, and GitHub Actions every Monday. GitHub Actions must remain pinned to full commit SHAs; keep the major-version comment beside each pin so automated updates stay reviewable.

When a Python requirement changes, regenerate both hashed lock files with Python 3.13 and review transitive changes before committing:

```sh
python -m piptools compile --generate-hashes --resolver=backtracking --output-file requirements.lock requirements.txt
python -m piptools compile --generate-hashes --resolver=backtracking --output-file requirements-dev.lock requirements-dev.txt
pip install --require-hashes -r requirements-dev.lock
pip-audit --requirement requirements.lock
pytest -W error
```

CI concurrency is scoped by pull request or Git ref. A newer run cancels an older run for the same pull request, while `main` and semantic-release tag runs are never cancelled. This prevents unrelated release tags from sharing a publication group.

## Reviews and releases

Changes reach `main` through pull requests with the `secrets`, `quality`, and `integration` checks passing. The secret scan examines complete Git history with redacted findings; never add a real credential to an allowlist. CODEOWNERS identifies the personal maintainer account for review; security-sensitive changes to authentication, image publication, dependencies, and deployment defaults need explicit maintainer review.

Semantic releases use annotated `v*.*.*` tags whose version matches `VERSION` and the Helm chart. The protected `production` environment gates Docker Hub publication, chart publication, signing, attestations, and GitHub Release creation. Never bypass a waiting deployment by publishing the same tag manually.
