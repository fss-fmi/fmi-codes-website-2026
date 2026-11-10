"""Each deploy pulls only what changed: no layer is stored twice and every build keeps its cache.

A `chown -R` or `chmod -R` over files an earlier `COPY` added writes every one of them into a
new layer, so the image ships them twice and each deploy pulls them twice. A shared GitHub
Actions cache scope makes each build overwrite the other's cache, so the backend reinstalls
its dependencies into a new layer every time. On a slow link either one pushes an image pull
past the Deployment's 10-minute progress deadline.
"""

import re
import shlex
from pathlib import Path, PurePosixPath

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCKERFILES = [ROOT / "backend" / "Dockerfile", ROOT / "frontend" / "Dockerfile"]
WORKFLOW = ROOT / ".github" / "workflows" / "docker-cd.yaml"
RECURSIVE = {"-R", "--recursive"}


def _instructions(text: str) -> list[tuple[str, str]]:
    """(KEYWORD, arguments) per instruction, continuations joined and comments dropped."""
    result, pending = [], ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith("\\"):
            pending += line[:-1] + " "
            continue
        keyword, _, args = (pending + line).partition(" ")
        result.append((keyword.upper(), args.strip()))
        pending = ""
    assert not pending, "unterminated line continuation"
    return result


def _final_stage(text: str) -> list[tuple[str, str]]:
    steps = _instructions(text)
    last_from = max(i for i, (keyword, _) in enumerate(steps) if keyword == "FROM")
    return steps[last_from + 1 :]


def _resolve(path: str, workdir: PurePosixPath) -> PurePosixPath:
    return PurePosixPath(path) if path.startswith("/") else workdir / path


def _overlaps(a: PurePosixPath, b: PurePosixPath) -> bool:
    return a == b or a in b.parents or b in a.parents


def _recursive_targets(command: str) -> list[str]:
    """Paths a shell command chowns, chgrps or chmods recursively."""
    targets = []
    for part in re.split(r"&&|\|\||;", command):
        words = shlex.split(part)
        if not words or words[0] not in {"chown", "chgrp", "chmod"}:
            continue
        flags = [w for w in words[1:] if w.startswith("-")]
        if not any(f in RECURSIVE or (not f.startswith("--") and "R" in f) for f in flags):
            continue
        operands = [w for w in words[1:] if not w.startswith("-")]
        targets.extend(operands[1:])
    return targets


def _rewrites_copied_files(text: str) -> list[str]:
    workdir = PurePosixPath("/")
    copied: list[PurePosixPath] = []
    problems = []
    for keyword, args in _final_stage(text):
        if keyword == "WORKDIR":
            workdir = _resolve(args, workdir)
        elif keyword in {"COPY", "ADD"}:
            copied.append(_resolve(shlex.split(args)[-1], workdir))
        elif keyword == "RUN":
            for target in _recursive_targets(args):
                path = _resolve(target, workdir)
                problems += [
                    f"{path} after COPY to {dest}" for dest in copied if _overlaps(path, dest)
                ]
    return problems


@pytest.mark.parametrize("dockerfile", DOCKERFILES, ids=lambda p: p.parent.name)
def test_no_layer_rewrites_copied_files(dockerfile):
    problems = _rewrites_copied_files(dockerfile.read_text(encoding="utf-8"))
    assert not problems, (
        f"{dockerfile.relative_to(ROOT)}: a recursive chown/chmod stores the copied files a "
        f"second time; use COPY --chown (or run it before the COPY): {problems}"
    )


@pytest.mark.parametrize(
    ("dockerfile", "copy"),
    [
        (DOCKERFILES[0], "COPY --chown=app:app . ."),
        (DOCKERFILES[1], "COPY --from=builder --chown=nginx:nginx /app/dist "),
    ],
    ids=["backend", "frontend"],
)
def test_the_app_is_copied_owned_by_the_runtime_user(dockerfile, copy):
    """The files stay owned by the user the container runs as, as they were before."""
    steps = _final_stage(dockerfile.read_text(encoding="utf-8"))
    assert any(f"{k} {a}".startswith(copy) for k, a in steps), f"{copy!r} not found"


@pytest.mark.parametrize(
    ("dockerfile", "chown"),
    [
        (DOCKERFILES[0], "chown app:app /app"),
        (DOCKERFILES[1], "chown -R nginx:nginx /usr/share/nginx/html "),
    ],
    ids=["backend", "frontend"],
)
def test_the_copy_destination_stays_owned_by_the_runtime_user(dockerfile, chown):
    """COPY --chown leaves a directory that already exists owned by root, so it is chowned first."""
    steps = _final_stage(dockerfile.read_text(encoding="utf-8"))
    first_app_copy = next(i for i, (k, a) in enumerate(steps) if k == "COPY" and "--chown" in a)
    assert any(k == "RUN" and chown in a for k, a in steps[:first_app_copy])


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("FROM x\nCOPY . /app\nRUN chown -R a:a /app", 1),
        ("FROM x\nWORKDIR /app\nCOPY . .\nRUN chown -R a:a /app", 1),
        ("FROM x\nWORKDIR /app\nCOPY . .\nRUN chmod -Rf 755 .", 1),
        ("FROM x\nCOPY dist /srv/html\nRUN true \\\n    && chown --recursive a /srv", 1),
        ("FROM x\nCOPY dist /srv/html\nRUN chown -R a /srv/html/assets", 1),
        ("FROM x\nRUN chown -R a /srv/html\nCOPY dist /srv/html", 0),
        ("FROM x\nCOPY dist /srv/html\nRUN chown -R a /var/cache/nginx", 0),
        ("FROM x\nCOPY . /app\nRUN chown a:a /app", 0),
        (
            "FROM b AS build\nCOPY . /app\nRUN chown -R a /app\nFROM x\nCOPY --from=build /app /app",
            0,
        ),
    ],
)
def test_the_rewrite_check_itself(text, expected):
    assert len(_rewrites_copied_files(text)) == expected


def _build_steps() -> dict[str, dict[str, str]]:
    text = WORKFLOW.read_text(encoding="utf-8")
    steps = {}
    for block in re.split(r"^      - name: ", text, flags=re.MULTILINE)[1:]:
        if "docker/build-push-action" not in block:
            continue
        name = block.splitlines()[0]
        steps[name] = dict(re.findall(r"^          ([\w-]+): (.+)$", block, re.MULTILINE))
    assert len(steps) == 2, f"expected the backend and frontend builds, found {list(steps)}"
    return steps


def _scope(cache: str) -> str | None:
    match = re.search(r"(?:^|,)scope=([\w.-]+)", cache)
    return match[1] if match else None


def test_each_build_has_its_own_cache_scope():
    scopes = []
    for name, inputs in _build_steps().items():
        assert inputs.get("cache-from", "").startswith("type=gha"), name
        assert inputs.get("cache-to", "").startswith("type=gha"), name
        scope = _scope(inputs["cache-from"])
        assert scope, f"{name}: without a scope the builds overwrite each other's cache"
        assert _scope(inputs["cache-to"]) == scope, f"{name}: writes a cache it never reads"
        scopes.append(scope)
    assert len(set(scopes)) == len(scopes), f"builds share a cache scope: {scopes}"


def test_the_monthly_rebuild_skips_the_cache():
    """Unpinned dependencies (`>=` in requirements.txt) refresh at least once a month."""
    for name, inputs in _build_steps().items():
        assert inputs.get("no-cache") == "${{ github.event_name == 'schedule' }}", name
    assert re.search(r"^  schedule:\n    - cron: ", WORKFLOW.read_text(encoding="utf-8"), re.M)
