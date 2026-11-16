"""The k8s scripts against a cluster where Flux owns the app (#187), with kubectl and flux stubbed."""

import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SCRIPTS = ROOT / "infra" / "k8s" / "scripts"
APPLY_CONFIG = SCRIPTS / "apply-config.sh"

# The managers kustomize-controller strips on every apply, matched as name prefixes.
FLUX_STRIPPED_PREFIXES = ("kubectl", "before-first-apply", "kustomize-controller")

RESTART = "kubectl -n fmi-codes-staging rollout restart deployment/backend --field-manager=fmi-codes-scripts"
RECONCILE = "flux reconcile kustomization fmi-codes-staging -n flux-system --with-source"

KUBECTL_STUB = """#!/usr/bin/env bash
printf 'kubectl %s\\n' "$*" >> "$FAKE_LOG"
case " $* " in
  *" get kustomizations.kustomize.toolkit.fluxcd.io "*)
    [ "$FAKE_FLUX" != none ] || exit 1
    case " $* " in *" -o "*) [ "$FAKE_FLUX" != suspended ] || printf true ;; esac ;;
esac
exit 0
"""

FLUX_STUB = """#!/usr/bin/env bash
printf 'flux %s\\n' "$*" >> "$FAKE_LOG"
"""

needs_bash = pytest.mark.skipif(
    sys.platform == "win32", reason="runs the scripts under a POSIX bash"
)


@pytest.fixture
def run(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("kubectl", KUBECTL_STUB), ("flux", FLUX_STUB)):
        stub = bin_dir / name
        stub.write_text(body, newline="\n")
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    log = tmp_path / "calls.log"

    def _run(*args, flux="none", **env):
        log.write_text("")
        result = subprocess.run(
            ["bash", str(APPLY_CONFIG), *args],
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                "FAKE_LOG": str(log),
                "FAKE_FLUX": flux,
                "ENV": "staging",
                **env,
            },
        )
        result.calls = log.read_text().splitlines()
        return result

    return _run


def mutating(calls):
    return [c for c in calls if re.search(r" (patch|apply|rollout restart|reconcile) ", c)]


@needs_bash
class TestApplyConfigWithFlux:
    def test_a_patch_is_refused_and_names_the_file_to_edit(self, run):
        result = run("REQUIRE_EMAIL_VERIFICATION", "true", flux="active")
        assert result.returncode == 1
        assert "infra/k8s/base/app/backend.yaml" in result.stderr
        assert "flux suspend kustomization fmi-codes-staging -n flux-system" in result.stderr
        assert mutating(result.calls) == []

    def test_an_env_specific_key_points_at_the_overlay(self, run):
        result = run("DB_HOST", "db.example", flux="active")
        assert result.returncode == 1
        assert "infra/k8s/overlays/staging/backend-config-patch.yaml" in result.stderr

    def test_prod_keys_all_live_in_the_base(self, run):
        result = run("DB_HOST", "db.example", flux="active", ENV="prod")
        assert result.returncode == 1
        assert "infra/k8s/base/app/backend.yaml" in result.stderr

    def test_secrets_are_still_refused_as_secrets(self, run):
        result = run("JWT_SECRET_KEY", "x", flux="active")
        assert result.returncode == 1
        assert "is a secret" in result.stderr

    def test_a_patch_holds_while_suspended(self, run):
        result = run("REQUIRE_EMAIL_VERIFICATION", "true", flux="suspended")
        assert result.returncode == 0, result.stderr
        assert mutating(result.calls) == [
            "kubectl -n fmi-codes-staging patch configmap fmi-codes-backend-config "
            '--type merge -p {"data":{"REQUIRE_EMAIL_VERIFICATION":"true"}}',
            RESTART,
        ]
        assert "flux resume kustomization fmi-codes-staging -n flux-system" in result.stdout

    def test_no_arguments_applies_git_main_not_the_disk(self, run):
        result = run(flux="active")
        assert result.returncode == 0, result.stderr
        assert mutating(result.calls) == [RECONCILE, RESTART]

    def test_no_arguments_refuses_while_suspended(self, run):
        result = run(flux="suspended")
        assert result.returncode == 1
        assert "flux resume kustomization fmi-codes-staging -n flux-system" in result.stderr
        assert mutating(result.calls) == []


@needs_bash
class TestApplyConfigWithoutFlux:
    def test_a_patch_is_applied_live(self, run):
        result = run("REQUIRE_EMAIL_VERIFICATION", "true")
        assert result.returncode == 0, result.stderr
        assert [c for c in mutating(result.calls) if "patch configmap" in c]
        assert mutating(result.calls)[-1] == RESTART
        assert "infra/k8s/base/app/backend.yaml" in result.stdout

    def test_no_arguments_applies_the_overlay_from_disk(self, run):
        result = run()
        assert result.returncode == 0, result.stderr
        calls = mutating(result.calls)
        assert calls[0].startswith("kubectl apply -k ")
        assert calls[0].endswith("overlays/staging")
        assert calls[1:] == [RESTART]

    def test_restart_false_prints_a_restart_that_survives_flux(self, run):
        result = run("REQUIRE_EMAIL_VERIFICATION", "true", RESTART="false")
        assert result.returncode == 0, result.stderr
        assert not [c for c in result.calls if "rollout restart" in c]
        assert "--field-manager=fmi-codes-scripts" in result.stdout


def test_the_restart_field_manager_is_not_one_flux_strips():
    lib = (SCRIPTS / "lib" / "rollout.sh").read_text()
    manager = re.search(r'^ROLLOUT_FIELD_MANAGER="([^"]+)"', lib, re.M).group(1)
    assert not manager.startswith(FLUX_STRIPPED_PREFIXES)


def test_every_scripted_restart_sets_the_field_manager():
    command = re.compile(
        r'rollout restart\s+("?\$|(deployment|deploy|statefulset|sts|daemonset|ds)/)'
    )
    offenders = []
    for script in sorted(SCRIPTS.rglob("*.sh")):
        for n, line in enumerate(script.read_text().splitlines(), 1):
            if (
                command.search(line)
                and not line.lstrip().startswith("#")
                and "--field-manager" not in line
            ):
                offenders.append(f"{script.relative_to(ROOT)}:{n}")
    assert offenders == []
