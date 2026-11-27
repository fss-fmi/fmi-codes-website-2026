# GitHub automation

What runs on GitHub around a merge: the bot app that opens the automated PRs, the secrets only
`main` can use and the two workflows that post PRs and CI results to Slack. What happens in the
cluster after a merge is posted by [Cluster alerts](runbook/alerts.md).

## GitHub bot app for automated PRs

The bump, migrate and promote workflows open their PRs as a GitHub App (`fmi-codes-bot`)
instead of the built-in `GITHUB_TOKEN`. GitHub holds CI on a PR opened with `GITHUB_TOKEN`
until someone clicks **Approve workflows to run**, and that token can't enable auto-merge,
so without the app every staging bump stalls. One-time setup, by an org admin:

1. **Create it:** org **Settings → Developer settings → GitHub Apps → New GitHub App**. Name it,
   set the homepage to the repo URL, untick **Webhook → Active**. Repository permissions:
   **Contents: Read and write** and **Pull requests: Read and write** (Metadata read-only is
   added automatically), nothing else. No events. Installable **only on this account**.
2. **Credentials:** copy the **Client ID** from the app page, then **Generate a private key**
   (a `.pem` downloads).
3. **Install it:** **Install App → Only select repositories →** this repo.
4. **Store them in the repo** (the key goes in through stdin, never as an argument):

   ```bash
   gh variable set BOT_APP_CLIENT_ID --repo fss-fmi/fmi-codes-website-2026 --body "Iv23li..."
   gh secret set BOT_APP_PRIVATE_KEY --repo fss-fmi/fmi-codes-website-2026 < ~/Downloads/<app>.<date>.private-key.pem
   ```

   Keep the `.pem` in a password manager and delete the download. To rotate, generate a new
   key on the app page, set the secret again and delete the old key there.

Also turn on **Settings → General → Allow auto-merge**. The repo's required checks (Lint, Unit
& E2E tests, Frontend tests) still gate every merge; the app gets no bypass.

`BOT_APP_PRIVATE_KEY` is still a repo-level secret, which any workflow on any branch can read:
the bump workflow runs on pushes to `flux-image-updates` and the migrate and promote workflows
can be dispatched from any branch, so it can't move to a `main`-only environment as it is.
Tracked in [#313](https://github.com/fss-fmi/fmi-codes-website-2026/issues/313).

## Secrets only `main` can use

The Slack bot token and the Docker Hub credentials live in two environments, `slack` and
`dockerhub`, whose deployment branches are `main` only ([ADR-020](adr/020-main-only-secret-environments.md)).
A job gets an environment's secrets only when it names the environment and runs with
`GITHUB_REF` on `main`, so a workflow pushed to any other branch reads them as empty. Every job
that reads one names its environment with `deployment: false`, so it adds nothing to the
deployment history:

| Environment | Secrets                                 | Job                                                          |
| ----------- | --------------------------------------- | ------------------------------------------------------------ |
| `slack`     | `SLACK_BOT_TOKEN`                       | `slack-pr-feed.yaml` `post`, `slack-ci-alerts.yaml` `notify` |
| `dockerhub` | `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN` | `docker-cd.yaml` `build`                                     |

Their triggers all run with `main`: `pull_request_target`, `issue_comment`, `workflow_run`,
`schedule` and pushes to `main`. Reviews can't, so the PR feed gets them through a
[relay](#reviews-through-the-relay). Running **Build and Push Docker Image** by hand from a
branch other than `main` is refused, and its failure posts in `#actions-notifications`.
`tests/test_workflow_secrets.py` fails when a job reads a secret outside these environments;
only `BOT_APP_PRIVATE_KEY` (#313) and `GITHUB_TOKEN` are allowed.

The workflows that read them can't change on `main` without review: `.github/CODEOWNERS` makes
`@Hari-Hristov` the code owner of `.github/`, and the "NO merging in main" ruleset requires a
code owner's review and dismisses stale approvals on every push. GitHub never lets an author
approve their own PR, so the ruleset's bypass list holds the **Repository admin** role in
pull-request mode: an admin's own `.github/` PR still needs a PR and green checks, but merges
without that review. That covers every admin of the repo, not only the code owner.

One-time setup, by a repo admin:

1. **Environments:** **Settings → Environments → New environment** `slack`, then **Deployment
   branches and tags → Selected branches and tags → Add deployment branch or tag rule** `main`.
   Add no reviewers, wait timer or custom protection rule (a custom rule fails every
   `deployment: false` job). The same for `dockerhub`.
2. **Secrets** (each prompts, so the value stays out of shell history):

   ```bash
   gh secret set SLACK_BOT_TOKEN --env slack --repo fss-fmi/fmi-codes-website-2026
   gh secret set DOCKERHUB_USERNAME --env dockerhub --repo fss-fmi/fmi-codes-website-2026
   gh secret set DOCKERHUB_TOKEN --env dockerhub --repo fss-fmi/fmi-codes-website-2026
   ```

   The Docker Hub token is a personal access token with Read & Write access, from the account
   that owns the `fssfmi` images (**Docker Hub → Account settings → Personal access tokens**).
   To rotate either token, set the secret again.

3. **Remove the repo-level copies** once the jobs post and push from the environments:
   `gh secret delete <NAME> --repo fss-fmi/fmi-codes-website-2026`. A job sees repo secrets
   next to its environment's, so a copy left behind is still readable from every branch.
4. **Ruleset:** **Settings → Rules → Rulesets → NO merging in main → Require a pull request
   before merging**: tick **Require review from Code Owners** and **Dismiss stale pull request
   approvals when new commits are pushed**. Under **Bypass list**, add **Repository admin**
   and set it to **For pull requests only**.

## Slack PR feed

`.github/workflows/slack-pr-feed.yaml` (logic in `.github/scripts/pr_feed.py`) posts every PR
that is ready for review to `#pr-updates`:

- **One parent message per PR**: status, title + link, number, author, base ← head. It is
  edited in place when the PR is merged, closed, reopened, turned back into a draft or renamed.
- **One-line replies in its thread** for approvals, change requests, "Comment" reviews that
  have a summary, conversation comments (`💬 <comment> by X`), draft/ready changes, merge,
  close and reopen. A "Comment" review with no summary is skipped: every reply in an inline
  review thread is its own review, so posting them would flood the thread. Bots' reviews and
  comments are skipped (bot comments don't even start a job). State replies only post when
  the PR's state really changes, and review and comment replies carry the review or comment
  id, so a re-run never duplicates one.
- **Commits**: the first reply, posted with the parent, lists the commits the PR was posted
  with: `🔨 3 commits in this PR · view changes` (a link to its Files tab). After that, each
  push adds one reply, `🔨 3 new commits by X · view changes`. Both list one line per commit
  (short SHA + first line of the message, at most 72 characters), oldest first. Past 5
  commits the rest collapse into a `+N more` link. The list comes from the PR's own commits,
  so "Update branch" shows as one merge commit, not everything pulled in from `main`. A force
  push (rebase, amend) says `⚠️ force-pushed by X · old → new` instead. A PR with over 250
  commits gets a link without a list (the API limit).
- **Drafts post nothing** until they are marked ready; while a PR is back in draft, reviews
  and pushes are not posted, and reviews made and commits pushed while it was a draft are not
  posted later.
- **Flux bump PRs** (`flux-image-updates`) get a single one-liner with the image names and
  tags, re-rendered when Flux pushes newer tags to the open PR (which drops a `CI failed`
  that belonged to the old head) and edited to `merged ✅` when it auto-merges. No thread.
- **CI results** (`✅ CI pipeline passed successfully · abc1234`, `❌ … pipeline failed`,
  `✅ … pipeline passed successfully again`) in the thread come from
  [Slack CI alerts](#slack-ci-alerts), not from this workflow.
- **Only people who can push to the repo are posted.** The repo is public and
  `pull_request_target` runs for any PR without approval, so without this anyone on GitHub
  could make the bot post text of their choosing (titles can carry links Slack makes
  clickable). A PR, review or comment counts only when the repo permission API says its
  author has `write` or `admin`. `author_association` is not used: `MEMBER` and
  `COLLABORATOR` include read-only access. Bots count only on PRs from this
  repo's own branches (Flux bumps, migration PRs). If the check fails, nothing is posted. The
  same check applies to each reviewer, commenter and pusher. Commit subjects are posted on the
  pusher's word, the way a title is posted on the author's.
- Reviews on PRs from forks are posted too, through the [relay](#reviews-through-the-relay).

The parent is found again through Slack message metadata, so nothing else stores state. Two
runs for the same PR can both find no parent and both post one; each run checks again right
after posting and the newer message deletes itself, so exactly one survives.

Push runs for one PR share a concurrency group, so their replies post in order. GitHub keeps
only the newest pending run in a group and cancels the others, so every push reply records
the head it reached and the next push lists every commit after it, by ancestry rather than
list position (GitHub sorts PR commits by date). The parent records the head it was posted
at, and its opening list stops there, so the first push lists only what came after; a
"ready"/"reopened" reply records the head at that moment and is posted before the
parent turns open. Those runs are outside the push group, so a push run waits up to a minute
for an open parent, which keeps a push right after "Ready for review" from listing the
draft's commits. If the commit list has not caught up with the pushed head after about 10
seconds the run fails; re-run it to post the commits. Push replies are keyed by both ends of
the push and the opening list by the thread, so re-runs and duplicate deliveries post
nothing twice; a re-run of the run that posted the parent finishes a list that failed. The
workflow never checks out PR code (it runs on `pull_request_target`, `issue_comment` and
`workflow_run`, which have secrets even for forks), and its `actions/checkout` is pinned to a
commit SHA. GitHub always runs the default branch's copy of these workflows, so a change can
only be tested after it merges. Of the Slack workflows, only the relay's copy comes from the
PR.

Repo hardening: **Settings → Actions → Fork pull request workflows** requires
approval for all outside contributors (`all_external_contributors`), so no fork PR's
workflows run until someone with write access approves them. `SLACK_BOT_TOKEN` lives in the
`main`-only `slack` environment and `.github/` changes need the code owner's review, per
[Secrets only `main` can use](#secrets-only-main-can-use). The jobs that hold the Slack or
Docker Hub token pin every action by commit SHA (`tests/test_workflow_secrets.py` checks it);
pinning the rest is tracked in
[#164](https://github.com/fss-fmi/fmi-codes-website-2026/issues/164).

It skips quietly until it is configured. One-time setup, in the Slack app that already holds
the migration and bug-report webhooks (a workspace admin may have to approve new scopes):

1. **Scopes:** api.slack.com/apps → the app → **OAuth & Permissions → Bot Token Scopes**: add
   `chat:write` and `channels:history` (also `groups:history` if the channel is private).
   Click **Reinstall to Workspace**; the existing incoming webhooks keep working.
2. **Token:** copy the **Bot User OAuth Token** (`xoxb-…`) and store it in the `slack`
   environment, created as in [Secrets only `main` can use](#secrets-only-main-can-use) (it
   prompts, so the token stays out of shell history):

   ```bash
   gh secret set SLACK_BOT_TOKEN --env slack --repo fss-fmi/fmi-codes-website-2026
   ```

3. **Channel:** run `/invite @<app name>` in `#pr-updates`, then copy its ID from the bottom of
   the channel details (`C0…`; not a secret):

   ```bash
   gh variable set SLACK_PR_CHANNEL_ID --repo fss-fmi/fmi-codes-website-2026 --body C0XXXXXXX
   ```

To rotate the token, reinstall or regenerate it on the app page and set the secret again.

### Reviews through the relay

A `pull_request_review` run runs on the PR's merge ref, which the `slack` environment refuses,
so `.github/workflows/pr-review-relay.yaml` (**PR review relay**) takes the review event
instead: no permissions, no secrets, no checkout and one step that does nothing. When its run
finishes, the feed starts on `workflow_run` from `main` and reads the PR's reviews from the
API. It trusts the relay run only for which PR it points at: the run's PR list, filtered to
this repo, or for a fork PR its head owner and branch. Every PR at the reviewed commit is
scanned (one branch can be PR'd into two bases); when none is there (pushed since the review,
or a reused head branch name), the open PRs and those updated in the last hour are.

Each scan posts every review the thread lacks (keyed by review id, so a review the old
`pull_request_review` path posted is never posted again), with the same checks as before: no
bots, only reviewers who can push, approvals, change requests and "Comment" reviews with a
summary, nothing on a draft or a Flux bump. It leaves out reviews submitted more than an hour
before the relay run, so the first scan of a fork PR doesn't post its whole history. It also
leaves out reviews submitted while the PR was a draft, taken from the PR's `convert_to_draft`
and `ready_for_review` issue events (a PR opened as a draft has only the second; reading them
is why the workflow holds `issues: read`), so a review made while it was open still posts after
a later draft round. A PR opened or made ready in the last 5 minutes may not have its parent
yet, since that run is outside the relay's queue, so the scan waits up to a minute for it.

Relay runs for one head repo and branch queue in order; when GitHub cancels a pending one, the
newest scan posts its reviews. A fork PR's relay run may first wait for the fork workflow
approval in the repo hardening above, so its reviews can post late. The relay's file comes
from the PR's merge ref, so a PR that edits it can only stop its own reviews from being
posted.

## Slack CI alerts

`.github/workflows/slack-ci-alerts.yaml` (logic in `.github/scripts/ci_alerts.py`) is the one
handler for finished runs of CI, Build and Push Docker Image, Docs, Open PR for Flux image
bump, Migrate database and Promote to production. A workflow renamed or added there must be
listed in its `workflow_run.workflows` by its exact `name:`.

- **Failure** (also `timed_out`): one alert in `#actions-notifications` with the workflow,
  where it failed (`main`, a branch or the PR), the failed job and step, the commit, and the
  last lines of that step's log (at most 20 lines / 1,500 characters, no timestamps, colours,
  stack frames, or pytest's per-test `PASSED`/`SKIPPED` lines and session header, since CI
  runs pytest with `-v`). Then a reply in the PR's `#pr-updates` thread linking the alert; a Flux
  bump's one-liner gets `· CI failed ❌` instead (never once it is merged or closed: its final
  state stays).
- **Recovery:** when a run passes and the previous finished run of that workflow on the same
  branch failed (cancelled runs are skipped over; a re-run that passes after a failed attempt
  counts, re-running a run that already passed does not),
  `✅ <workflow> pipeline passed successfully again on <main | #PR>` in
  `#actions-notifications` plus a thread reply; a Flux one-liner drops its `CI failed`.
- **Other passing runs** post only a `✅ <workflow> pipeline passed successfully · <commit>`
  reply in the PR thread.
- Every thread reply names the short commit SHA the run was on, so it lines up with the
  PR feed's commit lists; a failure reads `❌ <workflow> pipeline failed · <commit> · details`.
- Cancelled and skipped runs post nothing; draft PRs get no thread replies.
- Runs on a PR count only when the PR's author passes the same push check as the
  [PR feed](#slack-pr-feed); runs with no PR count only from this repo's own branches. So a
  fork PR can't post its log output, or a workflow it adds under a watched name
  (`workflow_run` matches by name).
- Each alert, and each thread reply, carries Slack message metadata (run id + attempt), so a
  duplicate event never posts twice; duplicate deliveries of one attempt also queue behind
  each other (`concurrency` per run attempt). A re-run that fails again is a new attempt and
  a new alert.

The log tail is taken from the failed step only: the job stops there, so its error is the
last `##[error]` line at or before that step finished. Earlier `##[error]` lines can come
from `continue-on-error` steps and are skipped. The
repo is public, so the excerpt stays short. GitHub masks registered secrets in logs, but not
values derived from them or credentials a step prints that were never registered, so the
excerpt is also redacted: token shapes (Slack, GitHub, AWS, Google, OpenAI, GitLab, Tailscale,
Docker, npm, age keys, JWTs, Slack and Discord webhook URLs), credentials in URLs,
`Authorization` values, `password=` / `api_key:` style assignments, `*_PASSWORD=` / `*_TOKEN=`
style variables, and whole private-key blocks all become `[redacted]`.

Like the PR feed it never runs PR code and only runs once it is on `main`; its job reads the
token from the same `slack` environment. It doesn't watch the review relay or the PR feed.
Setup, on top of the [Slack PR feed](#slack-pr-feed) token:

```bash
# after /invite @<app name> in #actions-notifications:
gh variable set SLACK_ACTIONS_CHANNEL_ID --repo fss-fmi/fmi-codes-website-2026 --body C0YYYYYYY
```

Without `SLACK_ACTIONS_CHANNEL_ID` nothing posts; without `SLACK_PR_CHANNEL_ID` only the
thread replies are skipped.
