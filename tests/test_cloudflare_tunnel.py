"""Prod is served only through the Cloudflare Tunnel, and rate limits still see the visitor (#271).

Reads the committed manifests and deploy-ingress.sh as text, like tests/k8s_manifests.py.
"""

import re

import pytest

from tests.k8s_manifests import K8S

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
