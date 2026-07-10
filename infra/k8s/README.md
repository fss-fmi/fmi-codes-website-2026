# Kubernetes migration (see issue #25)

Tracks the phased move off `docker-compose.yml` onto a locally-hosted k3s cluster.
Sub-issues: #26 (cluster), #27 (Postgres + Redis Sentinel), #28 (app tier),
#29 (ingress/TLS), #30 (CI/CD), #31 (config/secrets).

## Phase 1 — local cluster (#26)

Two scripts, run inside a **WSL2 Ubuntu** shell:

| Script | What it does |
| --- | --- |
| `install-tools-wsl2.sh` | Installs the CLIs — `kubectl`, `helm`, `k9s`. The "npm install" of this workflow. |
| `bootstrap-wsl2-k3s.sh` | Stands up k3s (Traefik disabled — Phase 4 installs `ingress-nginx`), wires up `kubectl`/Helm, and creates the app namespace from `namespace.yaml`. |

```bash
# 1. Get the tooling (one-shot, idempotent)
bash infra/k8s/install-tools-wsl2.sh

# 2. Stand up the cluster + namespace (idempotent)
bash infra/k8s/bootstrap-wsl2-k3s.sh
```

Re-running either is safe — every step is idempotent. Override the namespace
with `NAMESPACE=my-ns bash infra/k8s/bootstrap-wsl2-k3s.sh` if needed (that path
uses an on-the-fly namespace instead of `namespace.yaml`).

### Why k3s (not kind)

Both are fine local Kubernetes distros; they optimise for different things:

- **k3s** — a single lightweight binary that installs as a system service, so the
  cluster comes back after a reboot. Closest to a "real" cluster and meant to
  stay up — the right fit for a semi-persistent local deployment.
- **kind** — Kubernetes-in-Docker, great for disposable per-test dev clusters you
  spin up and throw away. Doesn't naturally persist across reboots.

Because this deployment is meant to stay running, **k3s is the default.** It ships
the Flannel CNI and a bundled kubectl, so there's nothing extra to install for
networking in this phase.

## Test the cluster

After bootstrapping, confirm it's healthy:

```bash
kubectl config current-context   # confirm it points at the k3s cluster (usually "default")
kubectl get nodes -o wide        # a single node, STATUS Ready
kubectl get pods -A              # core k3s pods (coredns, metrics-server, local-path) Running
kubectl get namespace fmi-codes  # STATUS Active
```

Nothing is deployed into `fmi-codes` yet — that starts in Phase 2 (#27). For now a
Ready node + the `fmi-codes` namespace is the whole deliverable.

### Verify the acceptance criteria (#26)

- **A node is Ready** — `kubectl get nodes` shows `STATUS Ready`.
- **The namespace exists** — `kubectl get namespace fmi-codes` shows `Active`.
- **Survives a host reboot** — k3s installs as a service, so it restarts on boot:

  ```bash
  sudo systemctl is-enabled k3s   # -> enabled
  sudo systemctl status k3s       # -> active (running)
  ```

  In WSL2 there's no full systemd unless it's enabled (`/etc/wsl.conf` →
  `[boot] systemd=true`, then `wsl --shutdown` from Windows). Without it, k3s
  won't auto-start on WSL relaunch — just re-run `bootstrap-wsl2-k3s.sh`, which
  is idempotent.

## Connect k9s

[k9s](https://k9scli.io/) is a terminal UI for the cluster — browse pods, tail
logs, exec into containers, all from the keyboard. It reads the same
`~/.kube/config` the bootstrap sets up, so once the cluster is running:

```bash
k9s                 # opens on the current context
k9s -n fmi-codes    # jump straight to the app namespace
```

Handy keys once inside: `:pods`, `:svc`, `:ns` to switch resource views, `l` to
tail logs on a selected pod, `s` to shell in, `d` to describe, `Ctrl-C`/`:q` to
quit. If it opens against the wrong cluster, fix `kubectl config current-context`
first — k9s follows kubectl.

## Tear down

```bash
# k3s ships an uninstaller that removes the service and all cluster state.
/usr/local/bin/k3s-uninstall.sh
```

Manifests/Helm values for later phases will land in this directory as each phase
is implemented.
