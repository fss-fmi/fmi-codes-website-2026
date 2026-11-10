import os
from pathlib import Path

bind = "0.0.0.0:5001"
workers = 4
threads = 8
timeout = 120

# Must be set before any worker imports prometheus_client, which picks its storage at import.
# Only Gunicorn gets multiprocess metrics; run_server.py and the tests keep the plain registry.
os.environ.setdefault("PROMETHEUS_MULTIPROC_DIR", "/tmp/prometheus-multiproc")

# Imported here, not in child_exit: Gunicorn calls child_exit from its SIGCHLD handler, which can
# re-enter it while the first call is still importing, and a half-imported module has no
# mark_process_dead yet.
from prometheus_client import multiprocess  # noqa: E402


def on_starting(server):
    # In k8s this is an emptyDir, which survives a container restart; PIDs restart from 1, so a
    # new worker would add onto a dead one's files. Only prometheus_client's own *.db files go,
    # in case the variable points at a folder that holds anything else.
    multiproc_dir = Path(os.environ["PROMETHEUS_MULTIPROC_DIR"])
    multiproc_dir.mkdir(parents=True, exist_ok=True)
    for db_file in multiproc_dir.glob("*.db"):
        db_file.unlink()


def child_exit(server, worker):
    multiprocess.mark_process_dead(worker.pid)
