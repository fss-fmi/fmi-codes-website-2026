# ADR-020: Slack and Docker Hub secrets in `main`-only environments, reviews through a relay

**Status**: accepted.

## Context

`SLACK_BOT_TOKEN`, `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN` and `BOT_APP_PRIVATE_KEY` were repo-level Actions secrets, so any workflow a writer pushed to any branch could read them. `main` needed a PR and green checks but no approving review, so a writer could also merge a workflow that sent them anywhere. The Slack token can post, edit and delete the bot's messages and read history in every channel it is in; the Docker Hub token can push the images both environments deploy.

GitHub hands an environment's secrets only to a job that names the environment, and an environment's branch rule is checked against the run's `GITHUB_REF`. `pull_request_target`, `issue_comment`, `workflow_run` and `schedule` run with the default branch. `pull_request_review` runs with the PR's merge ref, and uses that ref's copy of the workflow. `workflow_dispatch` runs with whatever branch is picked. GitHub never lets a PR author approve their own PR.

## Decision

- **Two environments, `main` only.** `slack` holds `SLACK_BOT_TOKEN`, for the PR feed and CI alerts jobs. `dockerhub` holds the Docker Hub credentials, for the image build. Both jobs name their environment with `deployment: false`, which keeps the branch rule but writes no deployments. The repo-level copies are deleted, since a job sees repo secrets next to its environment's.
- **Reviews come through a relay.** The PR feed drops its `pull_request_review` trigger. A new workflow, **PR review relay**, runs on reviews with no permissions, no secrets, no checkout and one step that does nothing. Its finished run starts the PR feed on `workflow_run`, from `main`.
- **The relay run is only a pointer.** Its file comes from the PR's merge ref, so anything the PR wrote can be in it. The feed takes from the run only which PR it is for (its PR list filtered to this repo, else the head owner and branch, preferring the PR at the reviewed commit) and reads every review from the API, with the same author, reviewer, draft and Flux checks as before. A PR that edits the relay can only stop its own reviews from being posted. Each scan posts every review the thread lacks, from the parent (or the last "ready") on and at most an hour before the run, so a run GitHub cancels while pending is covered by the next and reviews made in a draft never post.
- **`.github/` needs the code owner.** `.github/CODEOWNERS` makes `@Hari-Hristov` the owner of `.github/`, and the `main` ruleset requires a code owner's review and dismisses stale approvals on push. Its bypass list holds the **Repository admin** role in pull-request mode, so an admin's own `.github/` PR merges without that review but still through a PR with green checks.
- **`BOT_APP_PRIVATE_KEY` waits.** `flux-auto-pr` runs on pushes to `flux-image-updates`, and `migrate-database` and `promote-to-prod` can be dispatched from any branch, so a `main`-only environment would break all three. It stays a repo secret until [#313](https://github.com/fss-fmi/fmi-codes-website-2026/issues/313) picks a design.
- **A test holds the line.** `tests/test_workflow_secrets.py` fails when a job reads a secret outside these environments (`BOT_APP_PRIVATE_KEY` and `GITHUB_TOKEN` excepted), when the relay gains a permission, a secret or a checkout, or when the feed hears reviews any other way.

## Consequences

- **Easier**: a workflow pushed to a branch reads the Slack and Docker Hub secrets as empty, and the workflows that do read them can't change without the code owner. Reviews on fork PRs post too, which they couldn't when the review run held the token.
- **Harder**: the bypass covers every repo admin (4 today), not only the code owner, so an admin can still merge a `.github/` change nobody else reviewed. A review posts after two runs instead of one, and a fork PR's relay run may wait for the fork workflow approval. `Build and Push Docker Image` can no longer be dispatched from a branch. A fork of this repo needs both environments for the same protection; repo-level secrets still work, unprotected.
- **Failure mode**: if an environment is missing, GitHub creates it on first use with no branch rule and no secrets, so the job finds no token: the feed and alerts skip quietly and the image build fails its Docker Hub login (and alerts). Nothing about the relay can be tested before it is on `main`, since `workflow_run` only fires for the default branch's copy of the feed.
