"""Request metrics: aggregated across Gunicorn workers, probes left out, bounded labels.

Every app here is built in its own process: prometheus_client picks its storage at import,
and the exporter attaches no request hooks to a second app in a process that already has one.
"""

import os
import re
import runpy
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

# Imported here, with no PROMETHEUS_MULTIPROC_DIR set: importing it first under the patched
# env below would switch this whole test process to file-backed metrics.
from prometheus_client import multiprocess as prom_multiprocess

BACKEND_DIR = Path(__file__).parent.parent / "backend"
GUNICORN_CONF = BACKEND_DIR / "gunicorn.conf.py"

APP = """
import sys
from unittest.mock import patch
with patch("app.database.init_database"):
    from app import create_app
    app = create_app("testing")
client = app.test_client()
"""

WORKER = (
    APP
    + """
for i in range(int(sys.argv[1])):
    assert client.get(f"/no-such-page-{i}").status_code == 404
    assert client.get("/api/health").status_code == 200
"""
)

SCRAPER = APP + 'print(client.get("/metrics").get_data(as_text=True))\n'

# One process that serves and scrapes, without the multiprocess folder.
SINGLE = WORKER + 'print(client.get("/metrics").get_data(as_text=True))\n'


def _run(code, *args, multiproc_dir=None):
    env = {k: v for k, v in os.environ.items() if k != "PROMETHEUS_MULTIPROC_DIR"}
    if multiproc_dir is not None:
        env["PROMETHEUS_MULTIPROC_DIR"] = str(multiproc_dir)
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


def _request_totals(body):
    return re.findall(r"^flask_http_request_total\{([^}]*)\} (\S+)$", body, re.MULTILINE)


def test_counters_sum_across_worker_processes(tmp_path):
    _run(WORKER, "7", multiproc_dir=tmp_path)
    _run(WORKER, "5", multiproc_dir=tmp_path)

    body = _run(SCRAPER, multiproc_dir=tmp_path)

    assert _request_totals(body) == [('method="GET",status="404"', "12.0")]


def test_unknown_urls_share_one_latency_label(tmp_path):
    _run(WORKER, "6", multiproc_dir=tmp_path)

    body = _run(SCRAPER, multiproc_dir=tmp_path)

    counts = re.findall(
        r"^flask_http_request_duration_seconds_count\{([^}]*)\} (\S+)$", body, re.MULTILINE
    )
    assert counts == [('method="GET",status="404",url_rule="None"', "6.0")]
    assert "no-such-page" not in body


def test_health_probes_are_not_counted_in_multiprocess_mode(tmp_path):
    _run(WORKER, "3", multiproc_dir=tmp_path)

    body = _run(SCRAPER, multiproc_dir=tmp_path)

    assert _request_totals(body) == [('method="GET",status="404"', "3.0")]
    assert "/api/health" not in body


def test_health_probes_are_not_counted_without_gunicorn():
    body = _run(SINGLE, "2")

    assert _request_totals(body) == [('method="GET",status="404"', "2.0")]
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


def test_on_starting_removes_only_metric_files(tmp_path):
    (tmp_path / "counter_1.db").write_bytes(b"stale")
    (tmp_path / "histogram_1.db").write_bytes(b"stale")
    (tmp_path / "notes.txt").write_text("keep")
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "counter_2.db").write_bytes(b"keep")

    with patch.dict(os.environ, {"PROMETHEUS_MULTIPROC_DIR": str(tmp_path)}):
        _load_conf()["on_starting"](None)

    assert sorted(p.name for p in tmp_path.iterdir()) == ["notes.txt", "subdir"]
    assert (tmp_path / "subdir" / "counter_2.db").exists()


def test_on_starting_creates_a_missing_multiproc_dir(tmp_path):
    target = tmp_path / "missing"

    with patch.dict(os.environ, {"PROMETHEUS_MULTIPROC_DIR": str(target)}):
        _load_conf()["on_starting"](None)

    assert target.is_dir()


def test_child_exit_marks_the_worker_dead(tmp_path):
    with (
        patch.dict(os.environ, {"PROMETHEUS_MULTIPROC_DIR": str(tmp_path)}),
        patch.object(prom_multiprocess, "mark_process_dead") as mark_dead,
    ):
        _load_conf()["child_exit"](None, SimpleNamespace(pid=4242))

    mark_dead.assert_called_once_with(4242)


def test_child_exit_imports_nothing(tmp_path):
    """Gunicorn's SIGCHLD handler can re-enter child_exit while a first call is mid-import."""
    with patch.dict(os.environ, {"PROMETHEUS_MULTIPROC_DIR": str(tmp_path)}):
        child_exit = _load_conf()["child_exit"]
    with (
        patch.object(prom_multiprocess, "mark_process_dead") as mark_dead,
        patch("builtins.__import__", side_effect=AssertionError("child_exit imported a module")),
    ):
        child_exit(None, SimpleNamespace(pid=4242))

    mark_dead.assert_called_once_with(4242)
