# Kubernetes migration (see issue #25)

Tracks the phased move off `docker-compose.yml` onto a locally-hosted k3s cluster.
Sub-issues: #26 (cluster), #27 (Postgres + Redis Sentinel), #28 (app tier),
#29 (ingress/TLS), #30 (CI/CD), #31 (config/secrets).

## Phase 1 — local cluster (#26)

Two scripts, run inside a **WSL2 Ubuntu** shell:

| Script | What it does |
| --- | --- |
| `install-tools-wsl2.sh` | Installs the CLIs — `kubectl`, `helm`, `k9s` — each pinned to a specific version and checksum-verified. The "npm install" of this workflow. |
| `bootstrap-wsl2-k3s.sh` | Stands up k3s (pinned version, Traefik disabled — Phase 4 installs `ingress-nginx`), wires up `kubectl`/Helm, and creates the app namespace from `namespace.yaml`. |

```bash
# 1. Get the tooling (one-shot, idempotent)
bash infra/k8s/install-tools-wsl2.sh

# 2. Stand up the cluster + namespace (idempotent)
bash infra/k8s/bootstrap-wsl2-k3s.sh
```

Re-running either is safe — every step is idempotent. Override the namespace
with `NAMESPACE=my-ns bash infra/k8s/bootstrap-wsl2-k3s.sh` if needed (that path
labels an on-the-fly namespace instead of applying `namespace.yaml`). Tool and
cluster versions are pinned via `*_VERSION` env vars at the top of each script —
override them to upgrade (e.g. `K3S_VERSION=v1.37.0+k3s1 bash …`).

How long `bootstrap-wsl2-k3s.sh` waits for the cluster is tunable, too:
`API_TIMEOUT` (default 300s) for the API server to serve `/readyz`, `NODE_TIMEOUT`
(default 180s) for the node to go Ready, and `CRASH_LOOP_MAX_RESTARTS` (default 3)
— if the k3s systemd unit restarts that many times while waiting, the script
stops early and prints `systemctl status` + the journal tail, since a
crash-looping k3s won't fix itself by waiting longer.

> **Supply-chain note:** `install-tools-wsl2.sh` downloads each binary pinned to a
> version and verifies it against the vendor-published SHA256 before installing —
> nothing is piped into a shell. `bootstrap-wsl2-k3s.sh` runs the official k3s
> installer from `get.k3s.io` (pinned via `INSTALL_K3S_VERSION`); that installer
> runs under `sudo` and GPG-verifies the k3s binary it fetches. If you'd rather
> not run a remote installer as root, install k3s from a downloaded release binary
> out of band.

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
- **Survives a host reboot — _only if_ WSL2 systemd is enabled.** k3s installs as
  a systemd service, so on a host with systemd it restarts on boot:

  ```bash
  sudo systemctl is-enabled k3s   # -> enabled
  sudo systemctl status k3s       # -> active (running)
  ```

  **But default WSL2 has systemd off**, so out of the box this criterion does
  _not_ hold — k3s won't auto-start when you relaunch WSL. Two options:
  - Enable systemd once (`/etc/wsl.conf` → `[boot]\nsystemd=true`, then
    `wsl --shutdown` from Windows), after which the checks above pass and k3s
    survives relaunch; or
  - Leave systemd off and just re-run `bootstrap-wsl2-k3s.sh` after each WSL
    relaunch — it's idempotent and brings the cluster back in seconds.

## Troubleshooting: bootstrap says the API "did not come up"

`systemctl status k3s` showing **`active (running)`** only means the `k3s server`
process is alive — not that the API server is serving `:6443`. If bootstrap
reports the API didn't come up, check the journal (the script now prints it
automatically on failure):

```bash
sudo systemctl status k3s        # watch "active since … ; Ns ago"
sudo journalctl -u k3s -e --no-pager
```

If the `since … ; Ns ago` uptime keeps resetting to a few seconds — or you see
`activating (auto-restart)` with `Main PID … (code=exited)` — k3s is
**crash-looping**, not just slow. Common WSL2 fixes:

- **Missing iptables tools** (`Host iptables-save/iptables-restore tools not found`
  in the k3s log): `sudo apt-get install -y iptables`.
- **Stale cluster state from a prior boot:** `sudo /usr/local/bin/k3s-killall.sh`
  then `sudo rm -rf /var/lib/rancher/k3s`, and re-run bootstrap.
- **Too little memory for WSL2:** raise the limit in `%USERPROFILE%\.wslconfig`
  (e.g. `[wsl2]` → `memory=4GB`), then `wsl --shutdown` from Windows.

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
