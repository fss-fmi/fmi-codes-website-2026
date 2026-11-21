"""The backend's database connections fit Postgres, and probes don't drop a busy pod (#219).

Reads the committed manifests through tests/k8s_manifests.py, with targeted patterns rather than
a YAML parser. A pattern that stops matching fails loudly. Values an overlay's patches set for that
object win over the base, as they do when Kustomize renders it.
"""

import re
from pathlib import Path

import pytest

from tests.k8s_manifests import K8S, ROOT, overlay_value

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


def _deployment(env: str, pattern: str) -> int:
    return overlay_value(env, BASE, "Deployment", "backend", pattern)


def _config(env: str, pattern: str) -> int:
    return overlay_value(env, BASE, "ConfigMap", "fmi-codes-backend-config", pattern)


def _budget(env: str) -> tuple[int, int]:
    replicas = _deployment(env, r"^  replicas: (\d+)$")
    # A rollout runs maxSurge new pods on top of the old ones, and an old pod keeps its pool
    # through its preStop sleep and drain. Counting the surge twice covers one terminating pod
    # per step. A rollout under heavy load can overlap more (docs/runbook.md).
    surge = _deployment(env, r"^      maxSurge: (\d+)$")
    pods = replicas + 2 * surge
    workers = _int(GUNICORN, r"^workers = (\d+)$")
    pool = _config(env, r'^  DB_POOL_MAX: "(\d+)"$')
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
    assert _config(env, r'^  DB_POOL_MAX: "(\d+)"$') >= threads


def _probe(name: str) -> dict[str, int]:
    block = re.search(rf"^ +{name}:\n((?: {{12,}}.*\n)+)", BASE.read_text(encoding="utf-8"), re.M)
    assert block, f"{name} not found"
    return {k: int(v) for k, v in re.findall(r"(\w+Seconds|failureThreshold): (\d+)", block[1])}


def _acts_after(name: str) -> int:
    probe = _probe(name)
    return probe["periodSeconds"] * probe["failureThreshold"]


@pytest.mark.parametrize(("name", "acts_after"), [("readinessProbe", 120), ("livenessProbe", 300)])
def test_a_busy_pod_is_not_dropped_or_restarted(name, acts_after):
    """Overload reaches every pod at once, so a probe that acts on a busy pod drops or restarts
    all of them (#269). Shedding keeps the hash paths from queueing; the thresholds cover any
    other pile-up, and liveness only restarts a pod whose every thread is stuck."""
    assert _probe(name)["timeoutSeconds"] >= 10
    assert _acts_after(name) >= acts_after


def test_liveness_acts_only_after_readiness():
    assert _acts_after("livenessProbe") > _acts_after("readinessProbe")


def test_hash_slots_follow_the_cpu_limit():
    """One hash slot per core of the pod's own CPU limit, read through the downward API."""
    env = re.search(
        r"^ +- name: HASH_SLOTS\n +valueFrom:\n +resourceFieldRef:\n((?: {18,}.*\n)+)",
        BASE.read_text(encoding="utf-8"),
        re.M,
    )
    assert env, "HASH_SLOTS not set from a resourceFieldRef"
    fields = dict(re.findall(r"^ +(\w+): \"?([^\"\n]+)\"?$", env[1], re.M))
    assert fields == {"containerName": "backend", "resource": "limits.cpu", "divisor": "1"}


@pytest.mark.parametrize("env", ["prod", "staging"])
def test_backend_cpu_limit_is_whole_cores(env):
    """The downward API rounds a CPU limit up, so half a core would still get a whole slot and
    hash at half prod's speed. Whole cores keep staging's load test a stand-in for prod's."""
    cores = _deployment(env, r'^ {12}limits:\n(?: {14}memory: \S+\n)? {14}cpu: "?(\d+)"?$')
    assert cores >= 1
