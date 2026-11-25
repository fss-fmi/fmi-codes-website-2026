"""A pod caps the password hashes it runs at once and sheds the rest with a 429 (#269).

The slot tests take real flock locks, so they run where fcntl exists (Linux, CI) and skip on a
Windows dev machine. The route tests replace the gate with one that always sheds, so they run
everywhere; one more runs a route against the real gate on Linux.
"""

import contextlib
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import bcrypt
import pytest
from app.services import auth_service, feature_flag_service, mentor_service
from app.services.auth_service import generate_token
from app.utils import hash_slots
from app.utils.hash_slots import HashSlotsFullError, hash_slot
from prometheus_client import REGISTRY

BACKEND_DIR = Path(__file__).parent.parent / "backend"
needs_flock = pytest.mark.skipif(hash_slots.fcntl is None, reason="flock needs Linux")
RIGHT_GUESS = "right-guess-1234"
NEW_GUESS = "brand-new-guess-5678"
FAST_HASH = bcrypt.hashpw(RIGHT_GUESS.encode(), bcrypt.gensalt(rounds=4)).decode()
BUSY = "The server is busy. Wait a moment and try again."


@pytest.fixture()
def slots(monkeypatch, tmp_path):
    """Turns the cap on with `count` slots in a fresh folder and a short wait."""
    monkeypatch.setattr(hash_slots, "SLOTS_DIR", str(tmp_path / "slots"))
    monkeypatch.setattr(hash_slots, "WAIT_SECONDS", 0.3)

    def configure(count):
        monkeypatch.setenv("HASH_SLOTS", str(count))
        return Path(hash_slots.SLOTS_DIR)

    return configure


def _shed_count(reason):
    return REGISTRY.get_sample_value("password_hash_shed_total", {"reason": reason}) or 0.0


@contextlib.contextmanager
def _locked(path):
    """Holds a flock on `path` the way another worker's thread would."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        hash_slots.fcntl.flock(fd, hash_slots.fcntl.LOCK_EX | hash_slots.fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def _hold_in_thread(started, release):
    def hold():
        with hash_slot():
            started.set()
            release.wait(10)

    thread = threading.Thread(target=hold)
    thread.start()
    assert started.wait(5)
    return thread


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [None, "", "  "])
def test_no_hash_slots_means_no_cap(monkeypatch, tmp_path, value):
    monkeypatch.setattr(hash_slots, "SLOTS_DIR", str(tmp_path / "slots"))
    if value is None:
        monkeypatch.delenv("HASH_SLOTS", raising=False)
    else:
        monkeypatch.setenv("HASH_SLOTS", value)
    assert hash_slots.check_config() == 0
    with hash_slot():
        pass
    assert not (tmp_path / "slots").exists()


@pytest.mark.parametrize("value", ["0", "-1", "abc", "1.5", "500m"])
def test_a_bad_slot_count_refuses_to_boot(monkeypatch, value):
    monkeypatch.setenv("HASH_SLOTS", value)
    with pytest.raises(ValueError, match="HASH_SLOTS"):
        hash_slots.check_config()


def test_a_cap_without_flock_refuses_to_boot(monkeypatch):
    monkeypatch.setenv("HASH_SLOTS", "3")
    monkeypatch.setattr(hash_slots, "fcntl", None)
    with pytest.raises(RuntimeError, match="flock"):
        hash_slots.check_config()


def test_the_app_refuses_to_boot_with_a_bad_slot_count(monkeypatch):
    from app import create_app

    monkeypatch.setenv("HASH_SLOTS", "zero")
    with patch("app.database.init_database"), pytest.raises(ValueError, match="HASH_SLOTS"):
        create_app("testing")


# ---------------------------------------------------------------------------
# The slots (real flock locks)
# ---------------------------------------------------------------------------


@needs_flock
def test_threads_of_one_worker_exclude_each_other(slots):
    slots(1)
    started, release = threading.Event(), threading.Event()
    holder = _hold_in_thread(started, release)
    before = _shed_count("wait_timeout")
    try:
        begun = time.monotonic()
        with pytest.raises(HashSlotsFullError), hash_slot():
            pass
        assert time.monotonic() - begun >= hash_slots.WAIT_SECONDS
    finally:
        release.set()
        holder.join()
    assert _shed_count("wait_timeout") == before + 1


@needs_flock
def test_a_waiter_takes_the_slot_once_it_frees(slots):
    slots(1)
    started, release = threading.Event(), threading.Event()
    holder = _hold_in_thread(started, release)
    threading.Timer(0.1, release.set).start()
    begun = time.monotonic()
    with hash_slot():
        waited = time.monotonic() - begun
    holder.join()
    assert 0.05 <= waited < hash_slots.WAIT_SECONDS


@needs_flock
def test_a_full_waiting_room_sheds_at_once(slots):
    folder = slots(1)
    before = _shed_count("waiting_room_full")
    with _locked(folder / "hash-0"), _locked(folder / "wait-0"), _locked(folder / "wait-1"):
        begun = time.monotonic()
        with pytest.raises(HashSlotsFullError), hash_slot():
            pass
        assert time.monotonic() - begun < 0.1
    assert _shed_count("waiting_room_full") == before + 1


@needs_flock
def test_two_waiting_slots_per_hash_slot(slots):
    folder = slots(2)
    held = [folder / "hash-0", folder / "hash-1"] + [folder / f"wait-{i}" for i in range(3)]
    with contextlib.ExitStack() as stack:
        for path in held:
            stack.enter_context(_locked(path))
        begun = time.monotonic()
        with pytest.raises(HashSlotsFullError), hash_slot():
            pass
        # wait-3 was still free, so this one waited out the budget instead of leaving at once.
        assert time.monotonic() - begun >= hash_slots.WAIT_SECONDS


@needs_flock
def test_every_slot_can_hash_at_once(slots):
    slots(3)
    inside = threading.Barrier(3, timeout=5)
    errors = []

    def hash_together():
        try:
            with hash_slot():
                inside.wait()
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=hash_together) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []


@needs_flock
def test_a_slot_frees_when_the_hash_raises(slots):
    slots(1)
    with pytest.raises(RuntimeError), hash_slot():
        raise RuntimeError("bcrypt failed")
    begun = time.monotonic()
    with hash_slot():
        pass
    assert time.monotonic() - begun < 0.1


@needs_flock
def test_a_killed_worker_frees_its_slot(slots):
    folder = slots(1)
    folder.mkdir(parents=True)
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import fcntl, os, sys, time\n"
            "fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o600)\n"
            "fcntl.flock(fd, fcntl.LOCK_EX)\n"
            "print('held', flush=True)\n"
            "time.sleep(60)\n",
            str(folder / "hash-0"),
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout.readline().strip() == "held"
        with pytest.raises(HashSlotsFullError), hash_slot():
            pass
        holder.send_signal(signal.SIGKILL)
        holder.wait(5)
        begun = time.monotonic()
        with hash_slot():
            pass
        assert time.monotonic() - begun < 0.1
    finally:
        holder.kill()
        holder.wait(5)


def test_a_waiter_tries_for_a_slot_before_it_sleeps(monkeypatch, tmp_path):
    """A slot can free while a request takes its waiting slot; it shouldn't sleep past it."""
    fds = []

    def take(kind, count):
        fds.append(os.open(tmp_path / f"{kind}-{len(fds)}", os.O_RDWR | os.O_CREAT, 0o600))
        return fds[-1]

    sleeps = []
    monkeypatch.setattr(hash_slots, "_take", take)
    clock = SimpleNamespace(monotonic=time.monotonic, sleep=sleeps.append)
    monkeypatch.setattr(hash_slots, "time", clock)
    held = hash_slots._wait_for_slot(1)
    os.close(held)
    assert sleeps == []


def test_shed_counters_are_exported_before_any_shed(client):
    body = client.get("/metrics").get_data(as_text=True)
    for reason in ("waiting_room_full", "wait_timeout"):
        assert f'password_hash_shed_total{{reason="{reason}"}}' in body


# ---------------------------------------------------------------------------
# The routes: a shed answers 429 before anything is written
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def _always_shed():
    raise HashSlotsFullError("wait_timeout")
    yield


class _Db:
    """Records every statement the routes run, answering the reads they need."""

    def __init__(self):
        self.statements = []

    def execute_query(self, _app, sql, params=None, fetch_one=False, **_):
        self.statements.append(" ".join(sql.split()))
        if sql.lstrip().startswith("SELECT"):
            return {"id": 1, "password_hash": FAST_HASH}
        return None

    @contextlib.contextmanager
    def get_db_cursor(self, *_a, **_k):
        db = self

        class Cursor:
            def execute(self, sql, params=None):
                db.statements.append(" ".join(sql.split()))

            def fetchone(self):
                expires = datetime.now(UTC) + timedelta(hours=1)
                return {"id": 9, "user_id": 1, "expires_at": expires}

        yield Cursor()

    @property
    def writes(self):
        return [s for s in self.statements if not s.startswith("SELECT")]


@pytest.fixture()
def db(monkeypatch):
    fake = _Db()
    monkeypatch.setattr("app.routes.auth.execute_query", fake.execute_query)
    monkeypatch.setattr("app.routes.auth.get_db_cursor", fake.get_db_cursor)
    # The auth decorators: a participant with no revocation epoch.
    monkeypatch.setattr(
        "app.database.execute_query", lambda *a, **k: {"id": 1, "tokens_valid_from": None}
    )
    monkeypatch.setattr(feature_flag_service, "is_enabled", lambda name: True)
    return fake


REQUESTS = {
    "register": (
        "POST",
        "/api/auth/register",
        {
            "first_name": "Ana",
            "last_name": "Petrova",
            "email": "ana@example.com",
            "password": NEW_GUESS,
            "phone_number": "0700123456",
            "faculty_number": "1MI0700123",
            "course": "Bachelor 1st Year",
            "specialty_id": "1",
            "university_id": "1",
        },
    ),
    "login": (
        "POST",
        "/api/auth/login",
        {"email": "ana@example.com", "password": RIGHT_GUESS, "role": "participant"},
    ),
    "admin_login": (
        "POST",
        "/api/auth/login",
        {"email": "admin@example.com", "password": RIGHT_GUESS, "role": "admin"},
    ),
    "change_password": (
        "PATCH",
        "/api/auth/change-password",
        {"current_password": RIGHT_GUESS, "new_password": NEW_GUESS},
    ),
    "reset_confirm": (
        "POST",
        "/api/auth/reset-password/confirm",
        {"token": "abc", "new_password": NEW_GUESS, "role": "participant"},
    ),
}


def _send(app, client, name):
    method, path, body = REQUESTS[name]
    headers = {}
    if name == "change_password":
        with app.app_context():
            headers["Authorization"] = f"Bearer {generate_token(1, 'participant')}"
    return client.open(path, method=method, json=body, headers=headers)


def _expect_shed(response):
    assert response.status_code == 429, response.get_data(as_text=True)
    assert response.get_json() == {"success": False, "error": BUSY}
    assert response.headers["Retry-After"] == str(hash_slots.RETRY_AFTER_SECONDS)


@pytest.mark.parametrize("name", REQUESTS)
def test_a_shed_hash_answers_429_and_writes_nothing(app, client, db, monkeypatch, name):
    monkeypatch.setitem(app.config, "ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setitem(app.config, "ADMIN_PASSWORD_HASH", FAST_HASH)
    monkeypatch.setattr(auth_service, "hash_slot", _always_shed)
    _expect_shed(_send(app, client, name))
    assert db.writes == []


def test_an_admin_login_hashes_whatever_the_email(app, client, db, monkeypatch):
    """Otherwise only the real admin email could be shed, and the 429 would confirm it."""
    monkeypatch.setitem(app.config, "ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setitem(app.config, "ADMIN_PASSWORD_HASH", FAST_HASH)
    body = {"email": "guess@example.com", "password": RIGHT_GUESS, "role": "admin"}
    assert client.post("/api/auth/login", json=body).status_code == 401
    monkeypatch.setattr(auth_service, "hash_slot", _always_shed)
    _expect_shed(client.post("/api/auth/login", json=body))


def test_a_malformed_admin_hash_answers_503_whatever_the_email(app, client, monkeypatch):
    monkeypatch.setitem(app.config, "ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setitem(app.config, "ADMIN_PASSWORD_HASH", "not-a-bcrypt-hash")
    for email in ("admin@example.com", "guess@example.com"):
        body = {"email": email, "password": RIGHT_GUESS, "role": "admin"}
        response = client.post("/api/auth/login", json=body)
        assert response.status_code == 503
        assert response.get_json()["error"] == "Admin login not configured"


def test_a_change_shed_after_its_check_still_writes_nothing(app, client, db, monkeypatch):
    calls = []

    @contextlib.contextmanager
    def shed_second():
        calls.append(1)
        if len(calls) == 2:
            raise HashSlotsFullError("wait_timeout")
        yield

    monkeypatch.setattr(auth_service, "hash_slot", shed_second)
    _expect_shed(_send(app, client, "change_password"))
    assert len(calls) == 2
    assert db.writes == []


@needs_flock
def test_a_login_sheds_on_the_real_gate(app, client, db, slots):
    slots(1)
    started, release = threading.Event(), threading.Event()
    holder = _hold_in_thread(started, release)
    try:
        _expect_shed(_send(app, client, "login"))
    finally:
        release.set()
        holder.join()
    assert _send(app, client, "login").status_code == 200


# ---------------------------------------------------------------------------
# Hashes a booting worker runs are never shed
# ---------------------------------------------------------------------------


def test_an_uncapped_hash_skips_the_gate(monkeypatch):
    monkeypatch.setattr(auth_service, "hash_slot", _always_shed)
    hashed = auth_service.hash_password(RIGHT_GUESS, shed=False)
    assert bcrypt.checkpw(RIGHT_GUESS.encode(), hashed.encode())
    with pytest.raises(HashSlotsFullError):
        auth_service.hash_password(RIGHT_GUESS)
    with pytest.raises(HashSlotsFullError):
        auth_service.verify_password(RIGHT_GUESS, hashed)


def test_the_mentor_seed_is_never_shed(app_ctx, monkeypatch, tmp_path):
    """Every worker loads the seed while it boots (wsgi.py)."""
    seed = tmp_path / "mentors.json"
    seed.write_text(
        '[{"first_name": "A", "last_name": "B", "company_name": "C", "email": "a@mentor.test",'
        ' "phone_number": "0000000000", "password": "x"}]'
    )

    @contextlib.contextmanager
    def cursor(*_a, **_k):
        yield MagicMock(rowcount=1)

    monkeypatch.setattr(auth_service, "hash_slot", _always_shed)
    monkeypatch.setattr(mentor_service, "mentor_exists", lambda *a, **k: False)
    monkeypatch.setattr(mentor_service, "get_db_cursor", cursor)
    monkeypatch.setattr(mentor_service, "redis_del", lambda *a, **k: None)
    assert mentor_service.load_mentors_from_file(seed) == 1


def test_a_worker_boots_while_every_slot_is_busy():
    """The login route's timing dummy is hashed at import, inside every booting worker."""
    code = (
        "import contextlib\n"
        "from unittest.mock import patch\n"
        "from app.services import auth_service\n"
        "@contextlib.contextmanager\n"
        "def busy():\n"
        "    raise RuntimeError('every slot is busy')\n"
        "    yield\n"
        "auth_service.hash_slot = busy\n"
        "with patch('app.database.init_database'):\n"
        "    from app import create_app\n"
        "    create_app('testing')\n"
        "print('booted')\n"
    )
    env = {
        k: v for k, v in os.environ.items() if k not in ("HASH_SLOTS", "PROMETHEUS_MULTIPROC_DIR")
    }
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("booted")
