# Kubernetes migration (see issue #25)

Tracks the phased move off `docker-compose.yml` onto a locally-hosted k3s cluster.
Sub-issues: #26 (cluster), #27 (Postgres + Redis Sentinel), #28 (app tier),
#29 (ingress/TLS), #30 (CI/CD), #31 (config/secrets).

## Phase 1 — local cluster (#26)

`bootstrap-wsl2-k3s.sh` sets up k3s inside WSL2 Ubuntu: installs k3s with
Traefik disabled (Phase 4 installs `ingress-nginx` instead), wires up
`kubectl`/Helm, and creates the app namespace.

Run it inside a WSL2 Ubuntu shell:

```bash
bash infra/k8s/bootstrap-wsl2-k3s.sh
```

Re-running is safe — every step is idempotent. Override the namespace with
`NAMESPACE=my-ns bash infra/k8s/bootstrap-wsl2-k3s.sh` if needed.

Manifests/Helm values for later phases will land in this directory as each
phase is implemented.
