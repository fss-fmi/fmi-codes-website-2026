"""Unit tests for .github/scripts/flux_bump_gate.py (no network)."""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / ".github" / "scripts"))

import flux_bump_gate as gate_mod  # noqa: E402

ROOT = Path(__file__).parent.parent
REPO = "fss-fmi/fmi-codes-website-2026"
OLD = "1794174723-7d90357"
NEW = "1794186205-72434e8"
NEWER = "1794190000-abcdef1"


def overlay(backend: str, frontend: str) -> str:
    return (
        "images:\n"
        "  - name: fssfmi/fmi-codes-backend\n"
        "    newName: fssfmi/fmi-codes-backend\n"
        f'    newTag: {backend} # {{"$imagepolicy": "flux-system:fmi-codes-backend-staging:tag"}}\n'
        "  - name: fssfmi/fmi-codes-frontend\n"
        "    newName: fssfmi/fmi-codes-frontend\n"
        f'    newTag: {frontend} # {{"$imagepolicy": "flux-system:fmi-codes-frontend-staging:tag"}}\n'
    )


class FakeGh:
    """The repo as the gate sees it: main, the bump branch and at most one open bump PR."""

    def __init__(self, main=(OLD, OLD), branch=(NEW, NEW), pr=None, fail_enable=False):
        self.files = {gate_mod.BASE: overlay(*main)}
        if branch:
            self.files[gate_mod.BRANCH] = overlay(*branch)
        self.pr = pr
        self.fail_enable = fail_enable
        self.calls = []

    def push(self, backend, frontend):
        self.files[gate_mod.BRANCH] = overlay(backend, frontend)

    def branch_exists(self, branch):
        return branch in self.files

    def file(self, ref, path):
        assert path == gate_mod.OVERLAY
        return self.files[ref]

    def open_pr(self):
        return dict(self.pr) if self.pr else None

    def create_pr(self, title):
        self.calls.append(("create", title))
        self.pr = {"url": "https://github.com/x/pull/7", "title": title, "autoMergeRequest": None}
        return dict(self.pr)

    def set_title(self, pr, title):
        self.calls.append(("title", title))
        self.pr["title"] = title

    def enable_auto_merge(self, pr):
        self.calls.append(("enable", pr["url"]))
        if self.fail_enable:
            raise gate_mod.AutoMergeError("Could not enable auto-merge")
        self.pr["autoMergeRequest"] = {"mergeMethod": "SQUASH"}

    def disable_auto_merge(self, pr):
        self.calls.append(("disable", pr["url"]))
        self.pr["autoMergeRequest"] = None


def open_pr(title=f"deploy: bump {OLD} -> {NEW}", auto=True):
    return {
        "url": "https://github.com/x/pull/5",
        "title": title,
        "autoMergeRequest": {"mergeMethod": "SQUASH"} if auto else None,
    }


# --- tag parsing and titles ---


def test_overlay_tags_reads_every_marker():
    assert gate_mod.overlay_tags(overlay(OLD, NEW)) == {
        "fmi-codes-backend-staging": OLD,
        "fmi-codes-frontend-staging": NEW,
    }


def test_overlay_tags_matches_the_real_staging_overlay():
    """Fails if the overlay's marker format drifts from what the gate parses."""
    text = (ROOT / gate_mod.OVERLAY).read_text(encoding="utf-8")
    assert set(gate_mod.overlay_tags(text)) == {
        "fmi-codes-backend-staging",
        "fmi-codes-frontend-staging",
    }


def test_overlay_tags_without_markers_raises():
    with pytest.raises(ValueError):
        gate_mod.overlay_tags("images:\n  - name: x\n    newTag: 1-abc\n")


def test_title_is_one_pair_when_both_images_moved_together():
    old = gate_mod.overlay_tags(overlay(OLD, OLD))
    new = gate_mod.overlay_tags(overlay(NEW, NEW))
    assert gate_mod.bump_title(old, new) == f"deploy: bump {OLD} -> {NEW}"


def test_title_lists_each_distinct_change():
    old = gate_mod.overlay_tags(overlay(OLD, NEW))
    new = gate_mod.overlay_tags(overlay(NEWER, NEWER))
    assert gate_mod.bump_title(old, new) == f"deploy: bump {OLD} -> {NEWER} {NEW} -> {NEWER}"


def test_title_skips_an_image_that_did_not_move():
    old = gate_mod.overlay_tags(overlay(OLD, NEW))
    new = gate_mod.overlay_tags(overlay(NEW, NEW))
    assert gate_mod.bump_title(old, new) == f"deploy: bump {OLD} -> {NEW}"


# --- the gate ---


def test_matching_tags_open_the_pr_and_enable_auto_merge():
    gh = FakeGh()
    assert gate_mod.gate(gh) == "ready"
    assert gh.calls == [
        ("create", f"deploy: bump {OLD} -> {NEW}"),
        ("enable", "https://github.com/x/pull/7"),
    ]


def test_matching_tags_reuse_the_open_pr():
    gh = FakeGh(pr=open_pr(auto=False))
    assert gate_mod.gate(gh) == "ready"
    assert gh.calls == [("enable", "https://github.com/x/pull/5")]


def test_matching_tags_leave_an_already_armed_pr_alone():
    gh = FakeGh(pr=open_pr(auto=True))
    assert gate_mod.gate(gh) == "ready"
    assert gh.calls == []


def test_mismatched_tags_open_nothing(capsys):
    gh = FakeGh(branch=(NEW, OLD))
    assert gate_mod.gate(gh) == "waiting"
    assert gh.calls == []
    assert gh.pr is None
    out = capsys.readouterr().out
    assert out.startswith("::notice::")
    assert f"fmi-codes-backend-staging {NEW}" in out
    assert f"fmi-codes-frontend-staging {OLD}" in out


def test_mismatched_tags_disarm_an_open_pr():
    gh = FakeGh(branch=(NEW, OLD), pr=open_pr(auto=True))
    assert gate_mod.gate(gh) == "waiting"
    assert gh.calls == [("disable", "https://github.com/x/pull/5")]
    assert gh.pr["autoMergeRequest"] is None


def test_mismatched_tags_with_a_disarmed_pr_change_nothing():
    gh = FakeGh(branch=(NEW, OLD), pr=open_pr(auto=False))
    assert gate_mod.gate(gh) == "waiting"
    assert gh.calls == []


def test_split_release_opens_one_pr_once_whole():
    """The #208/#209 case: a scan sees the backend before the frontend is pushed."""
    gh = FakeGh(branch=(NEW, OLD))
    assert gate_mod.gate(gh) == "waiting"
    gh.push(NEW, NEW)
    assert gate_mod.gate(gh) == "ready"
    assert gh.calls == [
        ("create", f"deploy: bump {OLD} -> {NEW}"),
        ("enable", "https://github.com/x/pull/7"),
    ]


def test_second_release_while_a_pr_is_open():
    """Release NEW's PR is armed when NEWER's backend lands, then its frontend."""
    gh = FakeGh(pr=open_pr(auto=True))
    gh.push(NEWER, NEW)
    assert gate_mod.gate(gh) == "waiting"
    assert gh.pr["autoMergeRequest"] is None
    gh.push(NEWER, NEWER)
    assert gate_mod.gate(gh) == "ready"
    assert gh.calls == [
        ("disable", "https://github.com/x/pull/5"),
        ("title", f"deploy: bump {OLD} -> {NEWER}"),
        ("enable", "https://github.com/x/pull/5"),
    ]
    assert gh.pr["autoMergeRequest"]


def test_runs_out_of_order_still_end_on_the_live_branch():
    """A queued run for the half-bump commit that starts after the whole bump keeps the PR armed."""
    gh = FakeGh(branch=(NEW, NEW))
    gate_mod.gate(gh)
    # The run triggered by the earlier backend-only push reads the live branch, not its commit.
    assert gate_mod.gate(gh) == "ready"
    assert gh.pr["autoMergeRequest"]
    assert ("disable", "https://github.com/x/pull/7") not in gh.calls


def test_deleted_branch_does_nothing():
    gh = FakeGh(branch=None)
    assert gate_mod.gate(gh) == "gone"
    assert gh.calls == []


def test_branch_already_on_main_opens_nothing():
    gh = FakeGh(main=(NEW, NEW), branch=(NEW, NEW))
    assert gate_mod.gate(gh) == "current"
    assert gh.calls == []


def test_main_fails_when_auto_merge_cannot_be_enabled(monkeypatch, capsys):
    gh = FakeGh(fail_enable=True)
    monkeypatch.setenv("GITHUB_REPOSITORY", REPO)
    monkeypatch.setattr(gate_mod, "Gh", lambda repo: gh)
    assert gate_mod.main() == 1
    assert "::error::Could not enable auto-merge" in capsys.readouterr().out


def test_main_succeeds_while_waiting(monkeypatch):
    gh = FakeGh(branch=(NEW, OLD))
    monkeypatch.setenv("GITHUB_REPOSITORY", REPO)
    monkeypatch.setattr(gate_mod, "Gh", lambda repo: gh)
    assert gate_mod.main() == 0


# --- the gh wrapper ---


class Runner:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.result = subprocess.CompletedProcess([], returncode, stdout, stderr)
        self.args = []

    def __call__(self, args, **kwargs):
        self.args.append(args)
        return self.result


def test_gh_branch_missing_is_a_404():
    gh = gate_mod.Gh(REPO, Runner(1, stderr="gh: Branch not found (HTTP 404)"))
    assert gh.branch_exists(gate_mod.BRANCH) is False


def test_gh_branch_check_raises_on_other_errors():
    gh = gate_mod.Gh(REPO, Runner(1, stderr="gh: Bad credentials (HTTP 401)"))
    with pytest.raises(gate_mod.GhError):
        gh.branch_exists(gate_mod.BRANCH)


def test_gh_reads_the_file_from_the_given_ref():
    runner = Runner(stdout=overlay(NEW, NEW))
    assert gate_mod.Gh(REPO, runner).file(gate_mod.BRANCH, gate_mod.OVERLAY) == overlay(NEW, NEW)
    assert runner.args[0][-1] == f"repos/{REPO}/contents/{gate_mod.OVERLAY}?ref={gate_mod.BRANCH}"


def test_gh_open_pr_parses_the_first_result():
    runner = Runner(stdout='[{"number": 5, "url": "u", "title": "t", "autoMergeRequest": null}]')
    assert gate_mod.Gh(REPO, runner).open_pr() == {
        "number": 5,
        "url": "u",
        "title": "t",
        "autoMergeRequest": None,
    }
    assert gate_mod.Gh(REPO, Runner(stdout="[]")).open_pr() is None


def test_gh_enable_failure_explains_the_settings():
    gh = gate_mod.Gh(REPO, Runner(1, stderr="auto-merge is not allowed"))
    with pytest.raises(gate_mod.AutoMergeError, match="Allow auto-merge"):
        gh.enable_auto_merge({"url": "u"})
