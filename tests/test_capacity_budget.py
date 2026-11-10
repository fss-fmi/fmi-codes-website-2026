"""The backend's database connections fit Postgres, and probes don't drop a busy pod (#219).

Reads the committed manifests with targeted patterns rather than a YAML parser, which the
backend requirements don't include. A pattern that stops matching fails loudly. Values an
overlay's patches set win over the base, as they do when Kustomize renders it.
"""

import math
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
K8S = ROOT / "infra" / "k8s"
BASE = K8S / "base" / "app" / "backend.yaml"
GUNICORN = ROOT / "backend" / "gunicorn.conf.py"
# Superuser slots (Postgres keeps 3), the migrate initContainer or Job, a backup and an operator.
RESERVED_CONNECTIONS = 10
POSTGRES_VALUES = {
    "prod": K8S / "helm-values" / "postgresql-values.yaml",
    "staging": K8S / "overlays" / "staging" / "postgresql-values.yaml",
}


def _int(path: Path, pattern: str, default: int | None = None) -> int:
    match = re.search(pattern, path.read_text(encoding="utf-8"), re.MULTILINE)
    if match:
        return int(match.group(1))
    assert default is not None, f"{pattern!r} not found in {path.relative_to(ROOT)}"
    return default


def _overlay_value(env: str, pattern: str) -> int:
    """The base's value unless a patch the overlay lists sets its own."""
    overlay = K8S / "overlays" / env
    kustomization = (overlay / "kustomization.yaml").read_text(encoding="utf-8")
    value = _int(BASE, pattern)
    for patch in re.findall(r"^\s*-? *path: (\S+)$", kustomization, re.MULTILINE):
        value = _int(overlay / patch, pattern, default=value)
    return value


def _budget(env: str) -> tuple[int, int]:
    replicas = _overlay_value(env, r"^  replicas: (\d+)$")
    # A rollout runs up to maxSurge new pods (25%, rounded up) while old pods, terminating
    # ones included, still hold their connections. Counting the surge twice covers both.
    pods = replicas + 2 * math.ceil(replicas / 4)
    workers = _int(GUNICORN, r"^workers = (\d+)$")
    pool = _overlay_value(env, r'^  DB_POOL_MAX: "(\d+)"$')
    max_connections = _int(POSTGRES_VALUES[env], r"^\s*max_connections = (\d+)$", default=100)
    return pods * workers * pool + RESERVED_CONNECTIONS, max_connections


@pytest.mark.parametrize("env", ["prod", "staging"])
def test_backend_connections_fit_postgres(env):
    needed, allowed = _budget(env)
    assert needed <= allowed, (
        f"{env}: the backend can hold {needed} connections, Postgres allows {allowed}"
    )


@pytest.mark.parametrize("env", ["prod", "staging"])
def test_every_thread_can_get_a_connection(env):
    """With fewer connections than threads, a thread waits DB_POOL_TIMEOUT and fails, and team
    changes hold theirs while queued on the global advisory lock."""
    threads = _int(GUNICORN, r"^threads = (\d+)$")
    assert _overlay_value(env, r'^  DB_POOL_MAX: "(\d+)"$') >= threads


def _probe(name: str) -> dict[str, int]:
    block = re.search(rf"^ +{name}:\n((?: {{12,}}.*\n)+)", BASE.read_text(encoding="utf-8"), re.M)
    assert block, f"{name} not found"
    return {k: int(v) for k, v in re.findall(r"(\w+Seconds|failureThreshold): (\d+)", block[1])}


@pytest.mark.parametrize(("name", "acts_after"), [("readinessProbe", 30), ("livenessProbe", 60)])
def test_a_busy_pod_is_not_dropped_or_restarted(name, acts_after):
    """A probe queued behind password hashing gets 10 s, and several misses before it acts."""
    probe = _probe(name)
    assert probe["timeoutSeconds"] >= 10
    assert probe["periodSeconds"] * probe["failureThreshold"] >= acts_after
