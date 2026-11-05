import os
import shutil
from pathlib import Path

bind = "0.0.0.0:5001"
workers = 4
threads = 8
timeout = 120

# Must be set before any worker imports prometheus_client, which picks its storage at import.
# Only Gunicorn gets multiprocess metrics; run_server.py and the tests keep the plain registry.
os.environ.setdefault("PROMETHEUS_MULTIPROC_DIR", "/tmp/prometheus-multiproc")


def on_starting(server):
    # In k8s this is an emptyDir, which survives a container restart; PIDs restart from 1, so a
    # new worker would add onto a dead one's files.
    multiproc_dir = Path(os.environ["PROMETHEUS_MULTIPROC_DIR"])
    multiproc_dir.mkdir(parents=True, exist_ok=True)
    for entry in multiproc_dir.iterdir():
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()


def child_exit(server, worker):
    from prometheus_flask_exporter.multiprocess import GunicornInternalPrometheusMetrics

    GunicornInternalPrometheusMetrics.mark_process_dead_on_child_exit(worker.pid)
