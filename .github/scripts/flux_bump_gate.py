"""Opens the Flux staging bump PR only once every image is on the same release.

Run by .github/workflows/flux-auto-pr.yaml on every push to flux-image-updates.
docker-cd builds both images in one job with one tag, but pushes them about a
minute apart, and Flux scans each image repository on its own timer. A scan in
that gap commits a bump for one image only. Merged, staging would run a new
backend against an old frontend, and promote-to-prod would copy the mixed pair.

So every $imagepolicy tag in the staging overlay must match before the PR opens
or auto-merge is on. While they differ, nothing opens and auto-merge is turned
off on an open bump PR, so a half bump can never merge. The gate reads the live
branch, not the commit that triggered the run: runs queue one at a time, so the
last one always sees the newest bump and decides.
"""

import json
import logging
import os
import re
import subprocess
import sys

logger = logging.getLogger("flux_bump_gate")

BRANCH = "flux-image-updates"
BASE = "main"
OVERLAY = "infra/k8s/overlays/staging/kustomization.yaml"
# newTag: <tag> # {"$imagepolicy": "flux-system:<policy>:tag"}
TAG_RE = re.compile(
    r'^\s*newTag:\s*(\S+)\s*#\s*\{"\$imagepolicy":\s*"[^:"]+:([^:"]+):tag"\}', re.MULTILINE
)
PR_BODY = (
    "Automated tag bump by Flux image-automation, opened once every staging image "
    "carries the same release tag. Merges itself once the required checks pass; "
    "staging then redeploys."
)
AUTO_MERGE_HELP = (
    "so this staging bump will not merge by itself. Check that 'Allow auto-merge' is on "
    "in the repo settings and that fmi-codes-bot has Contents and Pull requests write access."
)


class GhError(Exception):
    pass


class NotFoundError(GhError):
    pass


class AutoMergeError(GhError):
    pass


def overlay_tags(text: str) -> dict[str, str]:
    """{policy: tag} for every $imagepolicy-marked newTag."""
    found = {policy: tag for tag, policy in TAG_RE.findall(text)}
    if not found:
        raise ValueError(f"No $imagepolicy newTag lines in {OVERLAY}")
    return found


def bump_title(old: dict[str, str], new: dict[str, str]) -> str:
    """deploy: bump A -> B, one pair per distinct change (Flux's own message repeats them)."""
    pairs = dict.fromkeys(
        f"{old.get(policy, '?')} -> {tag}"
        for policy, tag in sorted(new.items())
        if old.get(policy) != tag
    )
    return "deploy: bump " + " ".join(pairs)


def describe(tags: dict[str, str]) -> str:
    return ", ".join(f"{policy} {tag}" for policy, tag in sorted(tags.items()))


class Gh:
    """The few repo operations the gate needs, through the gh CLI (GH_TOKEN is the bot's)."""

    def __init__(self, repo: str, run=subprocess.run):
        self.repo = repo
        self._run = run

    def _gh(self, *args: str) -> str:
        result = self._run(["gh", *args], capture_output=True, text=True)
        if result.returncode:
            error = NotFoundError if "(HTTP 404)" in result.stderr else GhError
            raise error(f"gh {' '.join(args[:2])} failed: {result.stderr.strip()}")
        return result.stdout

    def file(self, ref: str, path: str) -> str:
        return self._gh(
            "api",
            "-H",
            "Accept: application/vnd.github.raw+json",
            f"repos/{self.repo}/contents/{path}?ref={ref}",
        )

    def open_pr(self) -> dict | None:
        """The open bump PR from this repo's branch, never a fork's branch of the same name.

        --head matches the branch name only, and the repo is public: arming a fork's PR
        would merge outside code once a maintainer approves its workflows.
        """
        prs = json.loads(
            self._gh(
                "pr",
                "list",
                "--repo",
                self.repo,
                "--base",
                BASE,
                "--head",
                BRANCH,
                "--state",
                "open",
                "--json",
                "number,url,title,autoMergeRequest,isCrossRepository",
            )
        )
        return next((pr for pr in prs if pr.get("isCrossRepository") is False), None)

    def create_pr(self, title: str) -> dict:
        url = self._gh(
            "pr",
            "create",
            "--repo",
            self.repo,
            "--base",
            BASE,
            "--head",
            BRANCH,
            "--title",
            title,
            "--body",
            PR_BODY,
        ).strip()
        return {"url": url, "title": title, "autoMergeRequest": None}

    def set_title(self, pr: dict, title: str) -> None:
        self._gh("pr", "edit", pr["url"], "--repo", self.repo, "--title", title)

    def enable_auto_merge(self, pr: dict) -> None:
        try:
            self._gh("pr", "merge", pr["url"], "--repo", self.repo, "--auto", "--squash")
        except GhError as e:
            raise AutoMergeError(
                f"Could not enable auto-merge on {pr['url']}, {AUTO_MERGE_HELP} ({e})"
            ) from e

    def disable_auto_merge(self, pr: dict) -> None:
        self._gh("pr", "merge", pr["url"], "--repo", self.repo, "--disable-auto")


def gate(gh) -> str:
    """Bring the bump PR in line with the live branch. Returns what it found, for logs and tests."""
    try:
        branch_text = gh.file(BRANCH, OVERLAY)
    except NotFoundError:
        # The overlay path itself is checked by the unit tests, so a 404 here is the branch.
        logger.info("%s is gone (the last bump merged); nothing to do", BRANCH)
        return "gone"
    new = overlay_tags(branch_text)
    pr = gh.open_pr()
    if len(set(new.values())) > 1:
        if pr and pr.get("autoMergeRequest"):
            gh.disable_auto_merge(pr)
            logger.info("Turned auto-merge off on %s until the release is whole", pr["url"])
        print(
            f"::notice::{BRANCH} holds part of a release ({describe(new)}); "
            "waiting for Flux to bump the other images to the same tag"
        )
        return "waiting"
    old = overlay_tags(gh.file(BASE, OVERLAY))
    if new == old:
        logger.info("%s already runs %s; nothing to bump", BASE, describe(new))
        return "current"
    title = bump_title(old, new)
    if pr is None:
        pr = gh.create_pr(title)
        logger.info("Opened %s", pr["url"])
    elif pr["title"] != title:
        gh.set_title(pr, title)
    if not pr.get("autoMergeRequest"):
        gh.enable_auto_merge(pr)
    logger.info("%s will merge itself once the checks pass", pr["url"])
    return "ready"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        gate(Gh(os.environ["GITHUB_REPOSITORY"]))
    except (GhError, ValueError) as e:
        print(f"::error::{e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
