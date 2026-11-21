"""Prod is served only through the Cloudflare Tunnel, and rate limits still see the visitor (#271).

Reads the committed manifests and deploy-ingress.sh as text, like tests/k8s_manifests.py, and
runs deploy-ingress.sh with kubectl, helm and sops stubbed, like tests/test_k8s_scripts.py.
"""

import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from tests.k8s_manifests import K8S, ROOT

CLOUDFLARED = K8S / "overlays" / "prod" / "ingress" / "cloudflared.yaml"
TUNNEL_CONFIG = K8S / "overlays" / "prod" / "ingress" / "cloudflared-config.yaml"
PROD_INGRESS_KUSTOMIZATION = K8S / "overlays" / "prod" / "ingress" / "kustomization.yaml"
TUNNEL_SECRET = K8S / "secrets" / "cloudflared-tunnel.enc.yaml"
BASE_INGRESS = K8S / "base" / "ingress" / "ingress.yaml"
DEPLOY_INGRESS = K8S / "scripts" / "deploy-ingress.sh"
BOOTSTRAP_K3S = K8S / "scripts" / "bootstrap-k3s.sh"
K3S_DEFAULT_POD_CIDR = "10.42.0.0/16"


def _read(path) -> str:
    return path.read_text(encoding="utf-8")


def _tunnel_config() -> str:
    return _read(TUNNEL_CONFIG)


def _prod_block() -> str:
    block = re.search(r"^  prod\)\n(.*?)^    ;;$", _read(DEPLOY_INGRESS), re.S | re.M)
    assert block, "prod case not found in deploy-ingress.sh"
    return block[1]


def _prod_default(name: str) -> str:
    value = re.search(rf'^    {name}="\$\{{{name}:-([^}}]+)\}}"$', _prod_block(), re.M)
    assert value, f"{name} has no default in deploy-ingress.sh's prod case"
    return value[1]


def _helm_sets() -> dict[str, str]:
    return dict(re.findall(r'--set "controller\.([^=]+)=([^"]*)"', _prod_block()))


def test_the_tunnel_routes_fmicodes_to_the_prod_controller_and_nothing_else():
    rules = re.findall(r"^  - (?:hostname: (\S+)\n    )?service: (\S+)$", _tunnel_config(), re.M)
    controller = (
        f"http://{_prod_default('INGRESS_RELEASE')}-controller."
        f"{_prod_default('INGRESS_NAMESPACE')}.svc.cluster.local:80"
    )
    assert rules == [(_prod_default("HOST"), controller), ("", "http_status:404")]


def test_the_tunnel_and_its_config_are_in_the_prod_ingress_overlay():
    kustomization = _read(PROD_INGRESS_KUSTOMIZATION)
    assert re.search(r"^  - cloudflared\.yaml$", kustomization, re.M)
    generator = re.search(
        r"^configMapGenerator:\n  - name: (\S+)\n(?:    .*\n)+", kustomization, re.M
    )
    assert generator, "the tunnel config must be generated, so a change to it rolls the pods"
    assert "      - config.yaml=cloudflared-config.yaml\n" in generator[0]
    assert re.search(
        rf"^          configMap:\n            name: {generator[1]}$", _read(CLOUDFLARED), re.M
    )


def test_cloudflared_reads_the_secret_deploy_ingress_applies():
    secret = _read(TUNNEL_SECRET)
    assert re.search(r"^    name: cloudflared-tunnel$", secret, re.M)
    assert re.search(r"^    namespace: fmi-codes$", secret, re.M)
    assert re.search(r"^    credentials\.json: ENC\[", secret, re.M), "credentials not encrypted"
    manifest = _read(CLOUDFLARED)
    assert re.search(r"^            secretName: cloudflared-tunnel$", manifest, re.M)
    mount = re.search(r"- name: creds\n +mountPath: (\S+)", manifest)
    assert mount
    assert re.search(
        rf"^credentials-file: {re.escape(mount[1])}/credentials\.json$", _tunnel_config(), re.M
    )
    assert "cloudflared-tunnel.enc.yaml" in _read(DEPLOY_INGRESS)


def test_cloudflared_is_ready_only_while_connected_and_pinned():
    manifest = _read(CLOUDFLARED)
    port = re.search(r"^metrics: 0\.0\.0\.0:(\d+)$", _tunnel_config(), re.M)
    assert port
    assert re.search(rf"- name: metrics\n +containerPort: {port[1]}$", manifest, re.M)
    readiness = re.search(r"readinessProbe:\n +httpGet:\n +path: (\S+)\n +port: metrics", manifest)
    assert readiness and readiness[1] == "/ready"
    assert re.search(r"image: docker\.io/cloudflare/cloudflared:\d{4}\.\d+\.\d+$", manifest, re.M)


def test_a_cloudflared_rollout_keeps_every_pod_ready():
    """CloudflareTunnelDown reads available replicas, so a rollout must never drop to 0."""
    manifest = _read(CLOUDFLARED)
    assert re.search(r"^      maxUnavailable: 0$", manifest, re.M)
    assert int(re.search(r"^  replicas: (\d+)$", manifest, re.M)[1]) >= 2


def test_the_prod_controller_binds_no_host_ports():
    sets = _helm_sets()
    assert sets.get("service.type") == "ClusterIP"
    assert "service.externalTrafficPolicy" not in sets


def test_the_visitor_address_is_trusted_only_from_the_pod_network():
    sets = _helm_sets()
    assert sets.get("config.enable-real-ip") == "true"
    assert sets.get("config.forwarded-for-header") == "CF-Connecting-IP"
    assert sets.get("config.proxy-real-ip-cidr") == "$POD_CIDR"
    assert _prod_default("POD_CIDR") == K3S_DEFAULT_POD_CIDR
    # Either would let a client pick its own rate-limit bucket or forwarded headers.
    assert "config.use-forwarded-headers" not in sets
    assert "config.compute-full-forwarded-for" not in sets


def test_k3s_keeps_its_default_pod_cidr():
    assert "cluster-cidr" not in _read(BOOTSTRAP_K3S)


@pytest.mark.parametrize("needle", ["cert-manager", "letsencrypt", "jetstack", "ClusterIssuer"])
def test_no_cert_manager_is_left(needle):
    for path in sorted(K8S.rglob("*")):
        if path.suffix in {".yaml", ".sh"}:
            assert needle not in _read(path), f"{needle} still in {path.relative_to(K8S)}"


def test_the_ingress_serves_plain_http_to_the_tunnel():
    ingress = _read(BASE_INGRESS)
    assert not re.search(r"^  tls:", ingress, re.M)
    assert re.search(r'^    nginx\.ingress\.kubernetes\.io/ssl-redirect: "false"$', ingress, re.M)


@pytest.mark.parametrize(
    ("script", "first_step"),
    [
        (K8S / "scripts" / "init-linux.sh", 'run_step 1 "install tooling"'),
        (ROOT / "bootstrap.sh", 'log "Pre-flight: tools (sops, age)"'),
    ],
)
def test_a_mistyped_opt_in_stops_the_run_before_anything_is_installed(script, first_step):
    text = _read(script)
    check = text.find("SERVE_PROD_TUNNEL must be 'true' or 'false'")
    assert check != -1, f"{script.name} doesn't check SERVE_PROD_TUNNEL"
    assert check < text.index(first_step)


def test_the_failed_tunnel_hint_names_the_file_with_the_tunnel_id():
    hint = re.search(
        r"'Failed to get tunnel'.*?\n.*?(overlays/prod/ingress/\S+\.yaml)", _read(DEPLOY_INGRESS)
    )
    assert hint
    assert re.search(r"^tunnel: \S+$", _read(K8S / hint[1]), re.M)


# The script reads these from the environment; a caller's shell must not leak them in.
DEPLOY_ENV = (
    "ENV",
    "NAMESPACE",
    "HOST",
    "INGRESS_NAMESPACE",
    "INGRESS_RELEASE",
    "POD_CIDR",
    "READY_TIMEOUT",
    "TUNNEL_SECRET_ENC",
    "SERVE_PROD_TUNNEL",
    "HEADERS_CONFIGMAP",
)

KUBECTL_STUB = """#!/usr/bin/env bash
printf 'kubectl %s\\n' "$*" >> "$FAKE_LOG"
case " $* " in
  *" apply -f - "*) cat >> "$FAKE_LOG.stdin" ;;
  *" get secret cloudflared-tunnel "*)
    case "$FAKE_SECRET" in
      present) echo secret/cloudflared-tunnel ;;
      error) echo 'Unable to connect to the server: i/o timeout' >&2; exit 1 ;;
    esac ;;
esac
"""

SOPS_STUB = """#!/usr/bin/env bash
printf 'sops %s\\n' "$*" >> "$FAKE_LOG"
printf 'kind: Secret\\nmetadata:\\n    name: cloudflared-tunnel\\n    namespace: fmi-codes\\n'
"""

needs_bash = pytest.mark.skipif(
    sys.platform == "win32", reason="runs deploy-ingress.sh under a POSIX bash"
)


@pytest.fixture
def deploy(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (
        ("kubectl", KUBECTL_STUB),
        ("helm", "#!/usr/bin/env bash\n"),
        ("sops", SOPS_STUB),
    ):
        stub = bin_dir / name
        stub.write_text(body, newline="\n")
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    log = tmp_path / "calls.log"
    stdin_log = Path(f"{log}.stdin")

    def _run(secret="absent", **env):
        log.write_text("")
        stdin_log.write_text("")
        base_env = {k: v for k, v in os.environ.items() if k not in DEPLOY_ENV}
        result = subprocess.run(
            ["bash", str(DEPLOY_INGRESS)],
            capture_output=True,
            text=True,
            env={
                **base_env,
                "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                "FAKE_LOG": str(log),
                "FAKE_SECRET": secret,
                "ENV": "prod",
                **env,
            },
        )
        result.calls = log.read_text().splitlines()
        result.applied = stdin_log.read_text()
        return result

    return _run


@needs_bash
def test_prod_without_the_opt_in_never_applies_the_tunnel_credentials(deploy):
    result = deploy()
    assert result.returncode == 0, result.stderr
    assert not [c for c in result.calls if c.startswith("sops ")]
    assert "kubectl apply -f -" not in result.calls
    assert result.applied == ""
    assert any(
        c.startswith("kubectl apply -k ") and c.endswith("overlays/prod/ingress")
        for c in result.calls
    )
    assert not [c for c in result.calls if "deployment/cloudflared" in c]
    assert "not on the internet" in result.stdout


@needs_bash
def test_prod_with_the_opt_in_applies_the_credentials_and_waits(deploy):
    result = deploy(SERVE_PROD_TUNNEL="true")
    assert result.returncode == 0, result.stderr
    assert "kubectl apply -f -" in result.calls
    assert "name: cloudflared-tunnel" in result.applied
    # rollout status fails at once on a Deployment already past its progress deadline.
    assert [c for c in result.calls if "wait --for=condition=Available deployment/cloudflared" in c]
    assert not [c for c in result.calls if "rollout status" in c]
    assert "not on the internet" not in result.stdout


@needs_bash
def test_a_failed_secret_check_is_not_taken_as_no_secret(deploy):
    result = deploy(secret="error")
    assert result.returncode != 0
    assert "could not check whether this cluster holds the tunnel's Secret" in result.stderr
    assert "not on the internet" not in result.stdout


@needs_bash
def test_a_cluster_still_holding_the_credentials_is_warned_it_serves(deploy):
    result = deploy(secret="present")
    assert result.returncode == 0, result.stderr
    assert "kubectl apply -f -" not in result.calls
    assert "still serves fmicodes.com" in result.stderr
    assert "not on the internet" not in result.stdout


@needs_bash
@pytest.mark.parametrize("value", ["yes", "1", "TRUE"])
def test_an_unknown_opt_in_value_is_refused_before_touching_the_cluster(deploy, value):
    result = deploy(SERVE_PROD_TUNNEL=value)
    assert result.returncode != 0
    assert "SERVE_PROD_TUNNEL must be 'true' or 'false'" in result.stderr
    assert result.calls == []
