# ClamAV REST Helm chart

[Source](https://github.com/teudanrichard/clamav-rest) · [Docker image](https://hub.docker.com/r/rtlabsio/clamav-rest) · [Artifact Hub](https://artifacthub.io/packages/helm/clamav-rest/clamav-rest)

This chart deploys the gateway and an optional private ClamAV deployment with persistent signature storage. It supports Traefik Ingress, Kubernetes Gateway API, optional Prometheus Operator ServiceMonitor, NetworkPolicy, OIDC configuration, and existing Secret injection.

```sh
helm dependency update charts/clamav-rest
helm lint charts/clamav-rest
helm template clamr charts/clamav-rest --set image.digest=sha256:...
helm install clamr charts/clamav-rest --namespace clamr --create-namespace
```

For production, set `image.digest`, explicit resource limits, a StorageClass for ClamAV signatures, TLS, and an ingress/Gateway policy. Keep `/metrics` private.

NetworkPolicy is opt-in because service routing and DNS behavior differ across CNIs. Enable it only after validating the cluster policy engine:

```sh
helm upgrade --install clamr charts/clamav-rest \
  --set networkPolicy.enabled=true \
  --set networkPolicy.egress=true
```

The chart’s default NetworkPolicy restricts gateway ingress. When egress restrictions are enabled, allow TCP/3310 to the ClamAV pods and DNS/HTTPS egress in the cluster policy engine.

## Quick install

```sh
helm registry login ghcr.io
helm upgrade --install clamav-rest \
  oci://ghcr.io/teudanrichard/charts/clamav-rest \
  --namespace clamav-rest --create-namespace \
  --set image.digest=sha256:<gateway-digest>
```

The chart is published automatically for each semantic release and indexed on [Artifact Hub](https://artifacthub.io/).

## Common configuration

| Value | Purpose | Default |
| --- | --- | --- |
| `image.repository` / `image.digest` | Gateway image and immutable digest | `rtlabsio/clamav-rest` / empty |
| `replicaCount` | Gateway replicas | `1` |
| `service.port` | Cluster service port | `8000` |
| `env.CLAMR_MAX_UPLOAD_SIZE` | Maximum upload bytes | `26214400` |
| `env.CLAMR_MAX_CONCURRENT_SCANS` | Scan concurrency limit | `4` |
| `env.CLAMR_SCAN_TIMEOUT` | Scan timeout in seconds | `120` |
| `env.CLAMR_DOCS_ENABLED` | Enable Swagger/ReDoc | `false` |
| `env.CLAMR_METRICS_ENABLED` | Enable Prometheus metrics | `false` |
| `oidc.enabled` | Enable OIDC authentication | `false` |
| `oidc.issuerUrl` / `oidc.audience` | OIDC discovery issuer and API audience | empty |
| `oidc.requiredScopes` | Scopes required on every protected request | empty |
| `ingress.enabled` | Create an Ingress (Traefik by default) | `false` |
| `gateway.enabled` | Create a Gateway API HTTPRoute | `false` |
| `clamav.persistence.size` | Signature database volume size | `5Gi` |
| `networkPolicy.enabled` | Enable gateway ingress policy | `false` |

For the complete schema, see [`values.yaml`](values.yaml) and [`values.schema.json`](values.schema.json). Sensitive values should be supplied through `existingSecret` rather than committed values files.

## OIDC example

```sh
helm upgrade --install clamav-rest \
  oci://ghcr.io/teudanrichard/charts/clamav-rest \
  --set oidc.enabled=true \
  --set oidc.issuerUrl=https://keycloak.example/realms/platform \
  --set oidc.audience=clamav-rest
```

Keep ClamAV private; never expose service port 3310 through an ingress or public load balancer.
