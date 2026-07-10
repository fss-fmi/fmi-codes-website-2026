# Kubernetes deployment

This directory holds the Kubernetes manifests for the FMI Codes 2026 app. It's
being filled in over the six phases tracked in [#25](https://github.com/fss-fmi/fmi-codes-website-2026/issues/25)
as the app moves off the single-host `docker-compose` setup onto a locally-hosted
cluster.

**This is Phase 1 ([#26](https://github.com/fss-fmi/fmi-codes-website-2026/issues/26)):
stand up the local cluster and create the namespace.** Later phases add the
stateful tier (Postgres + Redis Sentinel), the app tier, Ingress + TLS, config
& secrets, and the CI/CD deploy step.

## Why k3s (not kind)

Both are fine local Kubernetes distros; they optimise for different things:

- **k3s** — a single lightweight binary that installs as a **systemd service**,
  so the cluster comes back automatically after a host reboot. Closest to a
  "real" cluster and meant to stay up. Good fit for a semi-persistent local /
  self-hosted deployment, which is what this migration targets.
- **kind** — Kubernetes-in-Docker, great for disposable, per-test dev clusters
  that you spin up and throw away. Doesn't naturally persist across reboots.

Because this deployment is meant to stay running rather than be recreated on
demand, **k3s is the default here.** k3s ships with the Flannel CNI and a
built-in kubectl, so there's nothing extra to install for networking in this
phase.

## Contents

| File             | Purpose                                                        |
| ---------------- | -------------------------------------------------------------- |
| `namespace.yaml` | The `fmi-codes` namespace everything else in the app deploys into. |

The bootstrap script lives at [`../scripts/k8s-bootstrap.sh`](../scripts/k8s-bootstrap.sh).

## Bring up the cluster

> **Platform note:** k3s is Linux-only. On macOS or Windows, run the script
> inside a Linux VM. (kind works cross-platform if you'd rather go that route,
> but the systemd-service / survives-reboot acceptance criterion below assumes k3s.)

```bash
# From the repo root. Installs k3s as a systemd service, waits for the node to
# be Ready, and applies the namespace. Safe to re-run — it's idempotent.
./scripts/k8s-bootstrap.sh
```

Pin a specific k3s release channel if you need to:

```bash
K3S_CHANNEL=v1.30 ./scripts/k8s-bootstrap.sh
```

## Verify the acceptance criteria

The script runs these checks at the end, but you can confirm them manually too.

**1. A node is Ready:**

```bash
kubectl get nodes
# NAME       STATUS   ROLES                  AGE   VERSION
# <host>     Ready    control-plane,master   1m    v1.30.x+k3s1
```

**2. The namespace exists:**

```bash
kubectl get namespace fmi-codes
# NAME        STATUS   AGE
# fmi-codes   Active   1m
```

**3. The cluster survives a host reboot** — verify k3s is enabled as a service
(so systemd restarts it on boot), not a manual foreground process:

```bash
systemctl is-enabled k3s     # -> enabled
sudo systemctl status k3s     # -> active (running)
```

If you want to actually test it, reboot the host and re-run steps 1 and 2 — the
node should return to Ready and the namespace should still be there without
running the script again.

## kubectl access

k3s writes its kubeconfig to `/etc/rancher/k3s/k3s.yaml`. The bootstrap installs
k3s with `--write-kubeconfig-mode 644` so a non-root user can read it. To use a
standalone `kubectl` against the cluster, point `KUBECONFIG` at it (or merge it
into `~/.kube/config`):

```bash
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
kubectl get nodes
```

Without a standalone `kubectl`, use the one k3s bundles: `k3s kubectl get nodes`.

## Tearing down

```bash
# k3s ships an uninstaller that removes the service and cluster state.
/usr/local/bin/k3s-uninstall.sh
```
