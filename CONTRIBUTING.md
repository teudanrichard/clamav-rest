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
