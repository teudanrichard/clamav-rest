# Security policy

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Use GitHub's private security advisory feature or contact the project maintainers through an approved private channel. Include affected versions, reproduction steps, impact, and any suggested mitigation. Avoid including real malware or sensitive data; use the EICAR test file where possible.

## Supported versions

Until tagged releases are published, only the current `main` branch receives security fixes. Production deployments should use immutable commit-SHA image tags and regularly rebuild to receive patched base-image packages and ClamAV signatures.

## Security boundaries

This gateway does not provide authentication, authorization, TLS termination, rate limiting, or durable audit storage. Those controls belong at the deployment ingress. Clamd must remain on a private network because its protocol is unauthenticated. A `clean` response is one security signal, not a guarantee that a file is trustworthy.
