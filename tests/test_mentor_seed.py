"""The real mentor seed is personal data: it lives only in a SOPS-encrypted Secret per env (#274).

Every worker loads it while it boots, so the loader must also stay quiet when they collide (#191).

The loader tests mock the DB like tests/test_cache_services.py. The Secret, manifest and script
checks read the committed files as text, like tests/test_cloudflare_tunnel.py.
"""

import json
import logging
import re
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

import config
import pytest
from app.services import mentor_service

from tests.k8s_manifests import K8S, ROOT

DEV_SEED = ROOT / "backend" / "database" / "seeds" / "mentors.dev.json"
E2E_MENTOR_EMAILS = {"alpha@mentor.test", "beta@mentor.test", "gamma@mentor.test"}
SEED_SECRETS = {
    "staging": (
        K8S / "overlays" / "staging" / "secrets" / "mentors-seed.enc.yaml",
        "fmi-codes-staging",
    ),
    "prod": (K8S / "secrets" / "mentors-seed.enc.yaml", "fmi-codes"),
}
BACKEND = K8S / "base" / "app" / "backend.yaml"
DEPLOY_APP = K8S / "scripts" / "deploy-app.sh"
BOOTSTRAP = ROOT / "bootstrap.sh"
SOPS_CONFIG = ROOT / ".sops.yaml"

MENTOR = {
    "first_name": "Seed",
    "last_name": "Test",
    "company_name": "Seed Co",
    "email": "seed@mentor.test",
    "phone_number": "0888000000",
}
# Positions in the loader's INSERT parameters.
STATUS_PARAM = 6
HASH_PARAM = 9
_ABSENT = object()


def _seed(tmp_path, entries) -> Path:
    path = tmp_path / "mentors.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    return path


def _capture_inserts(monkeypatch, queries: list | None = None) -> list[tuple]:
    inserts = []

    def execute(query, params):
        if queries is not None:
            queries.append(query)
        inserts.append(params)

    @contextmanager
    def cursor(*_a, **_k):
        cur = MagicMock(rowcount=1)
        cur.execute.side_effect = execute
        yield cur

    monkeypatch.setattr(mentor_service, "get_db_cursor", cursor)
    monkeypatch.setattr(mentor_service, "mentor_exists", lambda *a, **k: False)
    monkeypatch.setattr(mentor_service, "redis_del", lambda *a, **k: None)
    return inserts


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("entry", [MENTOR, {**MENTOR, "password": ""}], ids=["missing", "empty"])
def test_a_mentor_without_a_password_gets_no_hash(app_ctx, monkeypatch, tmp_path, entry):
    """No default password: the mentor onboards through forgot password."""
    inserts = _capture_inserts(monkeypatch)
    monkeypatch.setattr(
        "app.services.auth_service.hash_password",
        lambda *a, **k: pytest.fail("there is no password to hash"),
    )
    assert mentor_service.load_mentors_from_file(_seed(tmp_path, [entry])) == 1
    assert inserts[0][HASH_PARAM] is None


def test_an_explicit_password_is_hashed(app_ctx, monkeypatch, tmp_path):
    inserts = _capture_inserts(monkeypatch)
    monkeypatch.setattr("app.services.auth_service.hash_password", lambda pw, **_: f"hashed:{pw}")
    seed = _seed(tmp_path, [{**MENTOR, "password": "mentor123"}])
    assert mentor_service.load_mentors_from_file(seed) == 1
    assert inserts[0][HASH_PARAM] == "hashed:mentor123"


@pytest.mark.parametrize(
    "content",
    [b"[{not json", b"\xff\xfe not utf-8", b'{"first_name": "A"}'],
    ids=["bad-json", "bad-encoding", "not-a-list"],
)
def test_a_broken_seed_loads_nothing_and_logs(app_ctx, monkeypatch, tmp_path, caplog, content):
    """A typo in an edited Secret must not stop every worker from booting."""
    path = tmp_path / "mentors.json"
    path.write_bytes(content)
    inserts = _capture_inserts(monkeypatch)
    with caplog.at_level(logging.ERROR, logger="app.services.mentor_service"):
        assert mentor_service.load_mentors_from_file(path) == 0
    assert inserts == []
    assert str(path) in caplog.text


def test_an_entry_that_is_not_an_object_is_skipped(app_ctx, monkeypatch, tmp_path):
    inserts = _capture_inserts(monkeypatch)
    monkeypatch.setattr("app.services.auth_service.hash_password", lambda pw, **_: "hashed")
    seed = _seed(tmp_path, ["not a mentor", None, {**MENTOR, "password": "mentor123"}])
    assert mentor_service.load_mentors_from_file(seed) == 1
    assert len(inserts) == 1


def test_a_seed_path_that_is_a_directory_loads_nothing(app_ctx, monkeypatch, tmp_path):
    inserts = _capture_inserts(monkeypatch)
    assert mentor_service.load_mentors_from_file(tmp_path) == 0
    assert inserts == []


def test_the_insert_is_a_no_op_on_a_conflict_on_any_unique_key(app_ctx, monkeypatch, tmp_path):
    """Workers seed at once on a fresh DB, so one can lose the race on the email key (#191)."""
    queries = []
    _capture_inserts(monkeypatch, queries)
    assert mentor_service.load_mentors_from_file(_seed(tmp_path, [MENTOR])) == 1
    query = " ".join(queries[0].split())
    assert "ON CONFLICT DO NOTHING" in query
    assert "ON CONSTRAINT" not in query


@pytest.mark.parametrize("field", ["email", "phone_number"])
@pytest.mark.parametrize(
    "value", [_ABSENT, "", "   ", None], ids=["missing", "empty", "whitespace", "null"]
)
def test_an_entry_without_an_email_or_phone_is_skipped_with_a_warning(
    app_ctx, monkeypatch, tmp_path, caplog, field, value
):
    inserts = _capture_inserts(monkeypatch)
    monkeypatch.setattr(
        mentor_service, "mentor_exists", lambda *a, **k: pytest.fail("skipped before any DB call")
    )
    monkeypatch.setattr(
        "app.services.auth_service.hash_password",
        lambda *a, **k: pytest.fail("skipped before hashing"),
    )
    entry = {**MENTOR, "password": "mentor123"}
    if value is _ABSENT:
        del entry[field]
    else:
        entry[field] = value
    with caplog.at_level(logging.WARNING, logger="app.services.mentor_service"):
        assert mentor_service.load_mentors_from_file(_seed(tmp_path, [entry])) == 0
    assert inserts == []
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "Seed Test" in warnings[0]
    assert field in warnings[0]
    assert MENTOR["email"] not in caplog.text
    assert MENTOR["phone_number"] not in caplog.text


@pytest.mark.parametrize("status", [None, "", "  "], ids=["null", "empty", "whitespace"])
def test_a_blank_status_is_stored_as_active(app_ctx, monkeypatch, tmp_path, status):
    inserts = _capture_inserts(monkeypatch)
    seed = _seed(tmp_path, [{**MENTOR, "status": status}])
    assert mentor_service.load_mentors_from_file(seed) == 1
    assert inserts[0][STATUS_PARAM] == "active"


# ---------------------------------------------------------------------------
# MENTORS_SEED_FILE
# ---------------------------------------------------------------------------


def test_seeding_with_no_file_configured_seeds_nobody(app_ctx, monkeypatch, caplog):
    monkeypatch.setitem(app_ctx.config, "MENTORS_SEED_FILE", None)
    monkeypatch.setattr(
        mentor_service, "load_mentors_from_file", lambda _p: pytest.fail("nothing to load")
    )
    with caplog.at_level(logging.WARNING, logger="app.services.mentor_service"):
        assert mentor_service.seed_mentors_from_config() == 0
    assert "MENTORS_SEED_FILE is not set" in caplog.text


@pytest.mark.parametrize("name", ["missing.json", ""], ids=["missing-file", "directory"])
def test_a_configured_seed_that_is_not_a_file_seeds_nobody(
    app_ctx, monkeypatch, tmp_path, caplog, name
):
    """An optional Secret that was never applied mounts as an empty directory."""
    path = tmp_path / name
    monkeypatch.setitem(app_ctx.config, "MENTORS_SEED_FILE", str(path))
    monkeypatch.setattr(
        mentor_service, "load_mentors_from_file", lambda _p: pytest.fail("nothing to load")
    )
    with caplog.at_level(logging.WARNING, logger="app.services.mentor_service"):
        assert mentor_service.seed_mentors_from_config() == 0
    assert "not found" in caplog.text


def test_the_configured_seed_is_loaded(app_ctx, monkeypatch, tmp_path):
    seed = _seed(tmp_path, [MENTOR])
    loaded = []
    monkeypatch.setitem(app_ctx.config, "MENTORS_SEED_FILE", str(seed))
    monkeypatch.setattr(mentor_service, "load_mentors_from_file", lambda p: loaded.append(p) or 3)
    assert mentor_service.seed_mentors_from_config() == 3
    assert loaded == [seed]


def test_production_has_no_default_seed():
    assert config.ProductionConfig.MENTORS_SEED_FILE is None


@pytest.mark.parametrize(
    "cfg", [config.DevelopmentConfig, config.TestingConfig], ids=["development", "testing"]
)
def test_development_and_testing_seed_the_fake_mentors(cfg):
    assert Path(cfg.MENTORS_SEED_FILE).resolve() == DEV_SEED.resolve()


def test_the_dev_seed_holds_only_fake_mentors():
    mentors = json.loads(DEV_SEED.read_text(encoding="utf-8"))
    assert mentors
    for mentor in mentors:
        assert mentor["email"].endswith("@mentor.test")
        assert mentor["email"] not in E2E_MENTOR_EMAILS, "collides with the e2e seeds fixture"
        assert mentor["phone_number"], "the column is NOT NULL, so the mentor would never load"
        assert mentor["password"], "the dev mentors log in with a known password"
        assert not mentor.get("picture_url"), "the photos belong to the real mentors"


def test_the_real_seed_path_is_gitignored():
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "backend/database/seeds/mentors*.json" in ignore
    assert "!backend/database/seeds/mentors.dev.json" in ignore


# ---------------------------------------------------------------------------
# The Secrets and how they reach the backend
# ---------------------------------------------------------------------------


def _sops_rule_recipient(rel_path: str) -> str:
    """The age key of the first .sops.yaml rule matching the path, the one sops uses."""
    for rule in re.split(r"^  - ", SOPS_CONFIG.read_text(encoding="utf-8"), flags=re.M)[1:]:
        path_regex = re.search(r"path_regex: (\S+)", rule)
        if path_regex and re.search(path_regex[1], rel_path):
            return re.search(r"age: (age1[0-9a-z]+)", rule)[1]
    pytest.fail(f"no .sops.yaml rule matches {rel_path}")


@pytest.mark.parametrize("env", SEED_SECRETS)
def test_each_seed_secret_is_encrypted_to_its_own_environment(env):
    path, namespace = SEED_SECRETS[env]
    secret = path.read_text(encoding="utf-8")
    assert re.search(r"^    name: fmi-codes-mentors-seed$", secret, re.M)
    assert re.search(rf"^    namespace: {namespace}$", secret, re.M)
    assert re.search(r"^    mentors\.json: ENC\[", secret, re.M), "the seed is not encrypted"
    recipients = re.findall(r"recipient: (age1[0-9a-z]+)", secret)
    assert recipients == [_sops_rule_recipient(path.relative_to(ROOT).as_posix())]


def test_the_backend_reads_the_seed_from_the_optional_secret():
    manifest = BACKEND.read_text(encoding="utf-8")
    assert re.search(
        r"- name: mentors-seed\n +secret:\n +secretName: fmi-codes-mentors-seed\n +optional: true$",
        manifest,
        re.M,
    ), "a required Secret not yet applied would block the rollout"
    mount = re.search(
        r"- name: mentors-seed\n +mountPath: (\S+)\n +readOnly: true$", manifest, re.M
    )
    assert mount
    assert re.search(
        rf"- name: MENTORS_SEED_FILE\n +value: {re.escape(mount[1])}/mentors\.json$", manifest, re.M
    )
    assert manifest.count("MENTORS_SEED_FILE") == 1, "only the app container seeds mentors"


def test_deploy_app_applies_the_seed_before_handing_over_to_flux():
    script = DEPLOY_APP.read_text(encoding="utf-8")
    seed = script.index('apply_sops_secret "$MENTORS_SEED_ENC"')
    assert seed < script.index('if flux_owns_app "$FLUX_KUSTOMIZATION"'), (
        "with Flux on, the script exits before anything after this check"
    )
    for env, (path, _) in SEED_SECRETS.items():
        secrets_rel = re.search(rf'^  {env}\).*SECRETS_REL="([^"]+)"', script, re.M)
        assert secrets_rel
        assert K8S / Path(secrets_rel[1]).parent / "mentors-seed.enc.yaml" == path


def test_bootstrap_checks_the_age_key_decrypts_the_seed():
    assert '"$SECRETS_DIR/mentors-seed.enc.yaml"' in BOOTSTRAP.read_text(encoding="utf-8")


def test_only_the_seed_loader_creates_or_deletes_mentors():
    """Mentors come only from the seed (Hari, 2026-11-25): no API may register or delete one."""
    write = re.compile(r"\b(INSERT\s+INTO|DELETE\s+FROM)\s+mentors\b", re.I)
    found = []
    for path in sorted((ROOT / "backend" / "app").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for m in write.finditer(text):
            func = re.findall(r"^def (\w+)", text[: m.start()], re.M)
            found.append((path.name, func[-1] if func else None))
    assert found == [("mentor_service.py", "load_mentors_from_file")]
