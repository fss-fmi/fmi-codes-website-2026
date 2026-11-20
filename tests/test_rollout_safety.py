"""A rollout keeps every pod's worth of capacity and stops pods only once the ingress has let go (#267).

Reads the committed manifests with targeted patterns, like test_capacity_budget.py. Values a patch
in the overlay sets for that Deployment win over the base, as they do when Kustomize renders it.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
K8S = ROOT / "infra" / "k8s"
GUNICORN = ROOT / "backend" / "gunicorn.conf.py"
NGINX = ROOT / "frontend" / "nginx.conf"
INDEX_HTML = ROOT / "frontend" / "index.html"
DEPLOYMENTS = {
    "backend": K8S / "base" / "app" / "backend.yaml",
    "frontend": K8S / "base" / "app" / "frontend.yaml",
}
ENVS = ["prod", "staging"]
# ingress-nginx picks up an endpoint change within a second or two; the sleep leaves room.
MIN_PRESTOP_SECONDS = 5
DEFAULT_GRACE_SECONDS = 30


def _find(text: str, pattern: str) -> int | None:
    match = re.search(pattern, text, re.MULTILINE)
    return int(match.group(1)) if match else None


def _value(env: str, deployment: str, pattern: str, default: int | None = None) -> int:
    """The base's value unless a patch the overlay applies to this Deployment sets its own."""
    value = _find(DEPLOYMENTS[deployment].read_text(encoding="utf-8"), pattern)
    overlay = K8S / "overlays" / env
    kustomization = (overlay / "kustomization.yaml").read_text(encoding="utf-8")
    for patch, target in re.findall(
        r"^\s*-? *path: (\S+)\n\s+target:\n(?:\s+(?!name:)\w+: \S+\n)*\s+name: (\S+)$",
        kustomization,
        re.MULTILINE,
    ):
        if target == deployment:
            patched = _find((overlay / patch).read_text(encoding="utf-8"), pattern)
            value = patched if patched is not None else value
    if value is None:
        assert default is not None, f"{pattern!r} not set for {deployment} in {env}"
        value = default
    return value


def _prestop(env: str, deployment: str) -> int:
    return _value(env, deployment, r"^ +preStop:\n +sleep:\n +seconds: (\d+)$")


def _grace(env: str, deployment: str) -> int:
    return _value(
        env,
        deployment,
        r"^      terminationGracePeriodSeconds: (\d+)$",
        default=DEFAULT_GRACE_SECONDS,
    )


@pytest.mark.parametrize("env", ENVS)
@pytest.mark.parametrize("deployment", DEPLOYMENTS)
def test_a_rollout_never_runs_on_fewer_pods(env, deployment):
    assert _value(env, deployment, r"^      maxUnavailable: (\d+)$") == 0
    assert _value(env, deployment, r"^      maxSurge: (\d+)$") >= 1


@pytest.mark.parametrize("env", ENVS)
@pytest.mark.parametrize("deployment", DEPLOYMENTS)
def test_a_stopping_pod_serves_until_the_ingress_drops_it(env, deployment):
    assert _prestop(env, deployment) >= MIN_PRESTOP_SECONDS


@pytest.mark.parametrize("env", ENVS)
def test_the_backend_drains_before_it_is_killed(env):
    """The grace period starts with the preStop sleep, so Gunicorn's drain has to fit after it."""
    graceful = _find(GUNICORN.read_text(encoding="utf-8"), r"^graceful_timeout = (\d+)$")
    assert graceful is not None, "graceful_timeout not set in gunicorn.conf.py"
    assert _grace(env, "backend") > _prestop(env, "backend") + graceful


@pytest.mark.parametrize("env", ENVS)
def test_the_frontend_drains_before_it_is_killed(env):
    assert _grace(env, "frontend") > _prestop(env, "frontend")


def _location(name: str) -> str:
    block = re.search(
        rf"^    location {re.escape(name)} \{{\n(.*?)^    \}}$",
        NGINX.read_text(encoding="utf-8"),
        re.S | re.M,
    )
    assert block, f"location {name} not found in frontend/nginx.conf"
    return block[1]


def test_a_missing_build_file_is_a_404_and_build_files_are_immutable():
    assets = _location("/assets/")
    assert re.search(r"^\s*try_files \$uri =404;$", assets, re.M)
    assert re.search(
        r'^\s*add_header Cache-Control "public, max-age=\d+, immutable";$', assets, re.M
    )


@pytest.mark.parametrize("name", ["= /index.html", "= /asset-guard.js"])
def test_html_and_the_guard_are_revalidated(name):
    assert re.search(r'^\s*add_header Cache-Control "no-cache";$', _location(name), re.M)


def test_the_guard_loads_before_anything_vite_injects():
    """Vite puts the bundle's script and stylesheet at the end of <head>."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    guard = html.find('<script src="/asset-guard.js"></script>')
    assert guard != -1
    assert guard < html.find("<link")
    assert guard < html.find("</head>")
