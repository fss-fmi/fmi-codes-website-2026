"""Gunicorn multiprocess metrics: counters aggregated across worker processes."""

import os
import re
import runpy
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

BACKEND_DIR = Path(__file__).parent.parent / "backend"
GUNICORN_CONF = BACKEND_DIR / "gunicorn.conf.py"

# prometheus_client picks its storage at import, so each "worker" must be its own process.
WORKER = """
import sys
from unittest.mock import patch
with patch("app.database.init_database"):
    from app import create_app
    app = create_app("testing")
client = app.test_client()
for _ in range(int(sys.argv[1])):
    assert client.get("/no-such-page").status_code == 404
    assert client.get("/api/health").status_code == 200
"""

SCRAPER = """
from unittest.mock import patch
with patch("app.database.init_database"):
    from app import create_app
    app = create_app("testing")
print(app.test_client().get("/metrics").get_data(as_text=True))
"""


def _run(code, multiproc_dir, *args):
    env = {**os.environ, "PROMETHEUS_MULTIPROC_DIR": str(multiproc_dir)}
    result = subprocess.run(
        [sys.executable, "-c", code, *args],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_counters_sum_across_worker_processes(tmp_path):
    _run(WORKER, tmp_path, "7")
    _run(WORKER, tmp_path, "5")

    body = _run(SCRAPER, tmp_path)

    series = re.findall(r"^flask_http_request_total\{([^}]*)\} (\S+)$", body, re.MULTILINE)
    assert series == [('method="GET",status="404"', "12.0")]
    assert "pid=" not in "".join(labels for labels, _ in series)


def test_health_probes_are_not_counted_in_multiprocess_mode(tmp_path):
    _run(WORKER, tmp_path, "3")

    body = _run(SCRAPER, tmp_path)

    assert 'path="/no-such-page"' in body
    assert "/api/health" not in body


def test_health_probes_are_not_counted(client):
    assert client.get("/api/health").status_code == 200

    body = client.get("/metrics").get_data(as_text=True)

    assert "/api/health" not in body


def _load_conf():
    return runpy.run_path(str(GUNICORN_CONF))


def test_conf_defaults_the_multiproc_dir():
    with patch.dict(os.environ):
        os.environ.pop("PROMETHEUS_MULTIPROC_DIR", None)
        _load_conf()
        assert os.environ["PROMETHEUS_MULTIPROC_DIR"] == "/tmp/prometheus-multiproc"


def test_conf_keeps_an_explicit_multiproc_dir(tmp_path):
    with patch.dict(os.environ, {"PROMETHEUS_MULTIPROC_DIR": str(tmp_path)}):
        _load_conf()
        assert os.environ["PROMETHEUS_MULTIPROC_DIR"] == str(tmp_path)


def test_on_starting_empties_the_multiproc_dir(tmp_path):
    (tmp_path / "counter_1.db").write_bytes(b"stale")
    (tmp_path / "leftover").mkdir()
    (tmp_path / "leftover" / "x.db").write_bytes(b"stale")

    with patch.dict(os.environ, {"PROMETHEUS_MULTIPROC_DIR": str(tmp_path)}):
        _load_conf()["on_starting"](None)

    assert tmp_path.is_dir()
    assert list(tmp_path.iterdir()) == []


def test_on_starting_creates_a_missing_multiproc_dir(tmp_path):
    target = tmp_path / "missing"

    with patch.dict(os.environ, {"PROMETHEUS_MULTIPROC_DIR": str(target)}):
        _load_conf()["on_starting"](None)

    assert target.is_dir()


def test_child_exit_marks_the_worker_dead(tmp_path):
    with (
        patch.dict(os.environ, {"PROMETHEUS_MULTIPROC_DIR": str(tmp_path)}),
        patch("prometheus_flask_exporter.multiprocess.pc_mark_process_dead") as mark_dead,
    ):
        _load_conf()["child_exit"](None, SimpleNamespace(pid=4242))

    mark_dead.assert_called_once_with(4242)
