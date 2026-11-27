"""Guards for #163: workflow secrets only in main-only environments, and the review relay.

Text-based on purpose: CI installs no YAML parser.
"""

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
GITHUB = ROOT / ".github"
WORKFLOWS = GITHUB / "workflows"
RELAY = WORKFLOWS / "pr-review-relay.yaml"
PR_FEED = WORKFLOWS / "slack-pr-feed.yaml"
CI_ALERTS = WORKFLOWS / "slack-ci-alerts.yaml"

# Their deployment branches are main only, a repo setting (docs/github-automation.md).
MAIN_ONLY_ENVS = {"slack", "dockerhub"}
# Still repo secrets: BOT_APP_PRIVATE_KEY is read on flux-image-updates and from
# dispatches on any branch, so it waits for #313. GITHUB_TOKEN is per run.
REPO_SECRETS = {"BOT_APP_PRIVATE_KEY", "GITHUB_TOKEN"}

SECRET_RE = re.compile(r"\bsecrets\.([A-Za-z_][A-Za-z0-9_]*)")
JOB_RE = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")
ENV_KEY_RE = re.compile(r"^      (\w+):\s*(.*?)\s*$")
FLOW_PAIR_RE = re.compile(r"(\w+):\s*([^,}]+?)\s*(?=[,}])")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def workflow_files() -> list[Path]:
    return sorted([*WORKFLOWS.glob("*.yaml"), *WORKFLOWS.glob("*.yml")])


def jobs(text: str) -> dict[str, list[str]]:
    """Each job under the top-level `jobs:` key, with the lines of its body."""
    lines = text.splitlines()
    found: dict[str, list[str]] = {}
    current = None
    for line in lines[lines.index("jobs:") + 1 :]:
        if line and not line[0].isspace() and not line.startswith("#"):
            break
        m = JOB_RE.match(line)
        if m:
            current = found.setdefault(m.group(1), [])
        elif current is not None:
            current.append(line)
    return found


def environment(job: list[str]) -> dict[str, str]:
    """The job's `environment:` as {key: value}; the string form only has a name."""
    for i, line in enumerate(job):
        if not line.startswith("    environment:"):
            continue
        inline = line.split(":", 1)[1].strip()
        if inline.startswith("{"):
            return dict(FLOW_PAIR_RE.findall(inline))
        if inline:
            return {"name": inline}
        block = {}
        for sub in job[i + 1 :]:
            m = ENV_KEY_RE.match(sub)
            if not m:
                break
            block[m.group(1)] = m.group(2)
        return block
    return {}


def unprotected_secrets(text: str) -> list[str]:
    """'<job>: <SECRET>' for each secret a job reads outside a main-only environment."""
    problems = []
    for job_id, body in jobs(text).items():
        names = set(SECRET_RE.findall("\n".join(body))) - REPO_SECRETS
        env = environment(body)
        protected = env.get("name") in MAIN_ONLY_ENVS and env.get("deployment") == "false"
        if not protected:
            problems += [f"{job_id}: {name}" for name in sorted(names)]
    return problems


def workflow_name(text: str) -> str:
    return re.search(r"^name:\s*(.+?)\s*$", text, re.M).group(1).strip("'\"")


def watched_workflows(text: str) -> list[str]:
    """The `workflow_run.workflows` list, in flow (`[a, b]`) or block form."""
    lines = text.splitlines()
    i = next(n for n, line in enumerate(lines) if line.startswith("    workflows:"))
    inline = lines[i].split(":", 1)[1].strip()
    if inline:
        return [w.strip().strip("'\"") for w in inline.strip("[]").split(",") if w.strip()]
    names = []
    for line in lines[i + 1 :]:
        m = re.match(r"^      - (.+?)\s*$", line)
        if not m:
            break
        names.append(m.group(1).strip("'\""))
    return names


def triggers(text: str) -> list[str]:
    lines = text.splitlines()
    names = []
    for line in lines[lines.index("on:") + 1 :]:
        if line and not line[0].isspace():
            break
        m = re.match(r"^  ([a-z_]+):", line)
        if m:
            names.append(m.group(1))
    return names


class TestSecretsStayOnMain:
    def test_every_secret_sits_in_a_main_only_environment(self):
        problems = {p.name: unprotected_secrets(read(p)) for p in workflow_files()}
        assert {name: found for name, found in problems.items() if found} == {}

    def test_the_moved_secrets_are_still_read(self):
        # Keeps the check above from passing on a parser that finds nothing.
        seen = {n for p in workflow_files() for n in SECRET_RE.findall(read(p))}
        assert {"SLACK_BOT_TOKEN", "DOCKERHUB_USERNAME", "DOCKERHUB_TOKEN"} <= seen

    def test_every_secret_is_inside_a_job(self):
        for path in workflow_files():
            text = read(path)
            in_jobs = sum(len(SECRET_RE.findall("\n".join(b))) for b in jobs(text).values())
            assert len(SECRET_RE.findall(text)) == in_jobs, path.name

    def test_no_secret_reaches_a_job_another_way(self):
        for path in workflow_files():
            text = read(path)
            for pattern in (r"secrets\s*\[", r"secrets:\s*inherit", r"toJSON\(\s*secrets"):
                assert not re.search(pattern, text), (path.name, pattern)

    def test_the_check_catches_an_unprotected_job(self):
        bare = "jobs:\n  leak:\n    runs-on: x\n    steps:\n      - run: echo ${{ secrets.SLACK_BOT_TOKEN }}\n"
        deploying = bare.replace("    runs-on", "    environment:\n      name: slack\n    runs-on")
        other_env = bare.replace(
            "    runs-on",
            "    environment:\n      name: github-pages\n      deployment: false\n    runs-on",
        )
        flow = bare.replace(
            "    runs-on", "    environment: {name: slack, deployment: false}\n    runs-on"
        )
        for text in (bare, deploying, other_env):
            assert unprotected_secrets(text) == ["leak: SLACK_BOT_TOKEN"]
        assert unprotected_secrets(flow) == []


class TestReviewRelay:
    def test_relay_holds_nothing(self):
        text = read(RELAY)
        assert re.search(r"^permissions:\s*\{\}\s*$", text, re.M)
        assert triggers(text) == ["pull_request_review"]
        assert "secrets." not in text
        assert "actions/checkout" not in text

    def test_the_feed_hears_reviews_only_through_the_relay(self):
        text = read(PR_FEED)
        assert "pull_request_review" not in triggers(text)
        assert "workflow_run" in triggers(text)
        assert watched_workflows(text) == [workflow_name(read(RELAY))]

    def test_ci_alerts_watches_neither_the_relay_nor_the_feed(self):
        watched = watched_workflows(read(CI_ALERTS))
        assert "CI" in watched
        assert workflow_name(read(RELAY)) not in watched
        assert workflow_name(read(PR_FEED)) not in watched


def test_codeowners_review_every_github_change():
    lines = [line.strip() for line in read(GITHUB / "CODEOWNERS").splitlines()]
    assert "/.github/ @Hari-Hristov" in lines
