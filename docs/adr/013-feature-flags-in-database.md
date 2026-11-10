# ADR-013: Registration, rankings and the mentor roster are switched in the database

**Status**: accepted. Narrows [ADR-006](006-self-hosted-k3s-pull-based-gitops.md) for these three switches: git stays the source of truth for config, but these are no longer config.

## Context

Registration opens at an announced minute, and the rankings go public at the end of the event. `REGISTRATION_OPEN`, `RANKINGS_LIVE` and `MENTORS_STAY_TUNED` were environment variables read once at startup, so changing one meant a backend restart. On k3s they sat in the `fmi-codes-backend-config` ConfigMap. `apply-config.sh` patched it and restarted the backend, and Flux reverted the patch to git within 5 minutes (#187). So a real change meant merging a PR, waiting for Flux and then a rolling restart, with no way to land on a given minute. The SPA also read `/api/config` only once per page load. `REQUIRE_EMAIL_VERIFICATION` is different: it depends on SMTP working, not on a moment in the event.

## Decision

- **The three flags are rows in a `feature_flags` table** (migration 017, seeded false as every ConfigMap had them). The environment variables are gone, so the database is the only source. Every reader (`/api/config`, register, the rankings route, the team score gate) asks `feature_flag_service`. `REQUIRE_EMAIL_VERIFICATION` stays an environment variable.
- **The admin switches them in Mission Control** (SITE tab, `/api/admin/flags*`), each action behind a confirm dialog.
- **One pending schedule per flag, and no scheduler.** `scheduled_value` and `scheduled_at` sit on the flag's row. The first read after the time applies the change in a transaction that locks the due rows with `SELECT ... FOR UPDATE`. A concurrent reader waits for that lock, re-checks the row and finds nothing due, so the change is applied and announced exactly once with any number of workers and pods. The database clock decides, not the admin's device. One slot keeps the table and the UI simple: to open and later close registration, the close is scheduled once the open has fired.
- **A switch by hand keeps a pending schedule.** If the schedule later asks for the value the flag already has, it is cleared without a notice. Scheduling the current value, or a time in the past, is refused.
- **Short cache, versioned key.** Reads are cached in Redis for 10 s under `cache:feature_flags:v<N>`, and every write bumps `N` after commit. Deleting a single key instead would let a reader that loaded the old value just before the write put it straight back for another 10 s; with the version fixed before the read, that reader can only refill a key nobody reads any more. While a schedule is pending the TTL is capped at the time left, so a cached value never outlives a due change. With Redis down every read goes to the database ([ADR-003](003-redis-optional-fail-open.md)). The table has three rows, so that read is trivial.
- **Open pages poll.** `ConfigContext` refetches `/api/config` every 30 s and on window focus, so a visitor with the site open sees a change without reloading. `/api/config` is exempt from rate limits: anonymous requests share one bucket per client address, the venue Wi-Fi puts every phone behind one NAT address, and a 429 on first load shows registration as closed.
- **Every change goes to the event feed**: one Slack incoming webhook per environment (`SLACK_EVENTS_WEBHOOK_URL`, `#event-feed-prod` and `#event-feed-staging`), posted by a reusable `event_notifier` from a bounded thread pool, off the request path. Without the webhook, changes are only logged.
- **`matching_state` stays its own table.** It is the confirmation status of the current matching results, reset in the same transaction (under advisory lock 2) that replaces them. It depends on data and makes no sense on a schedule.

## Consequences

- **Easier**: the announced minute is one button or a schedule made in advance, with no deploy, restart or Flux delay, on every pod at once. Flux can no longer revert a flag. Staging and prod are switched independently, and the feed records each change, by hand or scheduled, with its time.
- **Harder**: the values are not in git, so a fresh database starts with registration closed (locally too, see [Onboarding](../onboarding.md)). Recreating an environment means switching the flags again. `/api/config` now reads the database (cached), so it returns 503 when the flags can't be read; the SPA keeps its last values.
- **Failure mode**: a schedule only fires when something reads the flags. With no traffic at all it applies on the next request, which is the first moment anyone could notice it (its Slack post comes then too). If Redis is unreachable at the moment of a write but back for the next reads, the version is not bumped and the old value can be served from cache for up to 10 s.
- **Later**: more than one pending schedule per flag would need a `feature_flag_schedules` table.
