"""The backend's database connections fit Postgres, and probes don't kill a busy pod (#219).

Reads the committed manifests with targeted patterns rather than a YAML parser, which the
backend requirements don't include. A pattern that stops matching fails loudly.
"""

import math
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
K8S = ROOT / "infra" / "k8s"
# Superuser slots (Postgres keeps 3), the migrate initContainer or Job, a backup and an operator.
RESERVED_CONNECTIONS = 10
POSTGRES_DEFAULT_MAX_CONNECTIONS = 100


def _int(path: Path, pattern: str) -> int:
    match = re.search(pattern, path.read_text(encoding="utf-8"), re.MULTILINE)
    assert match, f"{pattern!r} not found in {path.relative_to(ROOT)}"
    return int(match.group(1))


def _replicas(env: str) -> int:
    patch = K8S / "overlays" / env / "backend-capacity-patch.yaml"
    if patch.exists():
        return _int(patch, r"^  replicas: (\d+)$")
    return _int(K8S / "base" / "app" / "backend.yaml", r"^  replicas: (\d+)$")


def _max_connections(env: str) -> int:
    values = {
        "prod": K8S / "helm-values" / "postgresql-values.yaml",
        "staging": K8S / "overlays" / "staging" / "postgresql-values.yaml",
    }[env]
    match = re.search(r"^\s*max_connections = (\d+)$", values.read_text(encoding="utf-8"), re.M)
    return int(match.group(1)) if match else POSTGRES_DEFAULT_MAX_CONNECTIONS


@pytest.mark.parametrize("env", ["prod", "staging"])
def test_backend_connections_fit_postgres(env):
    replicas = _replicas(env)
    # A rolling update adds maxSurge pods (25%, rounded up) while the old ones still serve.
    pods = replicas + math.ceil(replicas / 4)
    workers = _int(ROOT / "backend" / "gunicorn.conf.py", r"^workers = (\d+)$")
    pool = _int(K8S / "base" / "app" / "backend.yaml", r'^  DB_POOL_MAX: "(\d+)"$')
    needed = pods * workers * pool + RESERVED_CONNECTIONS
    assert needed <= _max_connections(env), (
        f"{env}: {pods} pods x {workers} workers x {pool} + {RESERVED_CONNECTIONS} reserved = "
        f"{needed} connections, Postgres allows {_max_connections(env)}"
    )


def _probe(name: str) -> dict[str, int]:
    text = (K8S / "base" / "app" / "backend.yaml").read_text(encoding="utf-8")
    block = re.search(rf"^ +{name}:\n((?: {{12,}}.*\n)+)", text, re.MULTILINE)
    assert block, f"{name} not found"
    return {k: int(v) for k, v in re.findall(r"(\w+Seconds|failureThreshold): (\d+)", block[1])}


@pytest.mark.parametrize("name", ["livenessProbe", "readinessProbe"])
def test_a_busy_pod_is_not_restarted_or_dropped(name):
    """A probe queued behind password hashing gets 10 s, and a minute passes before it acts."""
    probe = _probe(name)
    assert probe["timeoutSeconds"] >= 10
    assert probe["periodSeconds"] * probe["failureThreshold"] >= 60
