# ClamAV REST Helm chart

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
