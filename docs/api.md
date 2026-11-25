# API Reference

Base URL: same origin as the SPA (`https://fmicodes.com`). Local: `http://localhost:5001`, or through the Vite dev proxy at `http://localhost:5173`.

All bodies are JSON. Every route lives under `/api`. The contract is hand maintained; the frontend types in `frontend/src/types/` mirror these shapes manually.

## Conventions

**Response envelope.** Most endpoints return `{"success": true, ...}` or `{"success": false, "error": "<message>"}`. Exceptions: `/api/health`, `/api/health/ready` and `/api/config` return bare objects. When a team action or a ranking save fails on the server side, the response is a 500 with a fixed message such as `Could not join the team. Try again.`; the error itself goes only to the server log. A 500 rather than a 400 keeps a database outage visible to the `BackendHighErrorRate` alert.

**Request bodies.** A body must be a JSON object; any other JSON value (an array, a string, a number) returns 400 `Request body must be a JSON object`. A missing or unparsable body counts as `{}`, so it gets the route's usual missing-field 400. A text field sent as anything but a string or `null` returns 400 `<field> must be a string`; `null` counts as missing. Text with a NUL character or an unpaired UTF-16 surrogate escape returns 400 `<field> contains an invalid character`, and text longer than its database column returns 400 `<field> must be at most <n> characters`. Ids and ranks must be JSON integers.

**Authentication.** Login and registration set an httpOnly cookie named `token` (JWT, HS256, 3-day expiry, `SameSite=Lax`, `Secure` in production). Send it back with every request (`credentials: 'include'`). For scripts, `Authorization: Bearer <token>` works on every protected route.

| Guard       | Meaning                                                                                  | Failure   |
| ----------- | ---------------------------------------------------------------------------------------- | --------- |
| public      | No token needed                                                                          | n/a       |
| any         | Any valid token                                                                          | 401       |
| participant | Token role `participant`                                                                 | 401 / 403 |
| captain     | Participant who is captain; most routes also require the path `team_id` to be their team | 401 / 403 |
| mentor      | Token role `mentor`                                                                      | 401 / 403 |
| admin       | Token role `admin`                                                                       | 401 / 403 |

401 bodies: `Authentication required`, `Token expired`, `Invalid token`, `Token is missing required claims`, `Token has been revoked`.

**Rate limits.** Each limit keys on what it protects ([ADR-014](adr/014-rate-limits-keyed-on-account-and-user.md)). The default is 200 requests per minute per signed-in user (from a token with a valid signature) and, for anonymous requests, 3000 per minute per client address on each route and 6000 per minute across all routes together. Login and password reset also key on the account the request names, and a few public routes key on the address alone; each endpoint lists its own. Counters are shared across workers when Redis is configured. Windows move: a request is allowed if fewer than the limit were accepted in the last window length, so "300 per minute" never lets more than 300 through in any 60 s. A request takes a slot in each of its route's limits in turn and stops at the first full one: that limit doesn't count it, but the ones before it do (a login refused for its account still counts against the address). Exceeding a limit returns 429 `{"success": false, "error": "Too many requests. Wait a moment and try again."}` with a `Retry-After` header: the seconds until the oldest request counted against the breached limit is a window old, plus half a second (a request still counts at exactly that moment) rounded up, never more than the limit's own window, or 60 if its window can't be read. Slots free one at a time as earlier requests age out, not all at once. No other response carries rate-limit headers, so a client never sees how much budget is left. The login and registration pages wait out `Retry-After` plus 0 to 3 s of random jitter and send again on their own, up to 3 times, counting down on the button with a note below it that explains the wait; they show the message instead when a wait would be over 60 s. Editing the form during the countdown drops the pending retry, so it never sends the old values. The backend takes the address from the last `X-Forwarded-For` entry, the one its single trusted proxy sets (ingress-nginx in k3s, the frontend's nginx in Compose), so a client can't pick its own bucket by sending the header. Everyone behind one NAT shares an address, which is why address limits are sized for a whole venue and the two polled reads, `GET /api/config` and `GET /api/teams/rankings`, are exempt: at the venue every phone is on the same Wi-Fi. On staging every visitor arrives through the Tailscale proxy and shares one address, so staging multiplies every limit listed here by 10 (`RATELIMIT_MULTIPLIER`).

**Busy server.** Register, login, change-password and reset-password/confirm each run bcrypt, and a backend pod runs only as many hashes at once as its CPU limit has cores ([ADR-016](adr/016-shed-password-hashes.md)). When every slot is taken a request waits up to 2 s for one, or none if the pod already has two waiting for each slot, and then returns 429 `{"success": false, "error": "The server is busy. Wait a moment and try again."}` with `Retry-After: 2`. It comes before the route has written anything, so sending the same request again is safe, and the login and registration pages retry it the same way as a rate-limit 429.

**Feature flags.** `registration_open`, `preferences_open`, `rankings_live` and `mentors_stay_tuned` live in the `feature_flags` table; the admin switches or schedules them through `/api/admin/flags*` and every request reads the current value, so no restart is needed. `REQUIRE_EMAIL_VERIFICATION` comes from server config. Four are enforced by the API: `registration_open` (registration returns 403 when closed), `preferences_open` (both ranking POSTs return 403 when closed), `rankings_live` (team scores stay hidden from everyone but the admin until rankings are live) and `REQUIRE_EMAIL_VERIFICATION` (see below). `mentors_stay_tuned` only changes what the SPA renders.

**Email verification.** While `REQUIRE_EMAIL_VERIFICATION` is on, `POST /api/teams`, `POST /api/teams/join` and `POST /api/teams/{team_id}/apply` return 403 `{"success": false, "error": "Verify your email address before creating or joining a team.", "code": "email_unverified"}` for a participant whose email is not verified.

---

## Health and config

### GET /api/health

Liveness probe. Touches no dependency. Exempt from rate limits.

```json
{ "status": "ok" }
```

### GET /api/health/ready

Readiness probe. Runs a pooled `SELECT 1`; Redis is reported but never fails the check. Exempt from rate limits.

| Code | Body                                                  |
| ---- | ----------------------------------------------------- |
| 200  | `{"db": "ok", "redis": "ok" \| "down" \| "disabled"}` |
| 503  | `{"db": "down", "redis": "unknown"}`                  |

### GET /api/config

Public. Feature flags for the SPA, which polls this every 30 s and on window focus so open pages follow a switch in Mission Control. The first four come from the `feature_flags` table (cached in Redis for up to 10 s, cleared on every change, never past a pending schedule's time); reading them applies any schedule whose time has passed. Exempt from rate limits, because every open page polls it and a full venue shares one NAT address. 503 if the flags can't be read.

```json
{
  "REGISTRATION_OPEN": false,
  "MENTORS_STAY_TUNED": false,
  "RANKINGS_LIVE": false,
  "PREFERENCES_OPEN": false,
  "REQUIRE_EMAIL_VERIFICATION": false
}
```

### GET /metrics

Prometheus exposition from `prometheus_flask_exporter`, at the backend root (not under `/api`). Only reachable in-cluster; the public ingress sends `/metrics` to the frontend. Under Gunicorn the totals cover all workers of the pod. Requests to `/api/health` and `/api/health/ready` are not counted.

---

## Auth

### POST /api/auth/register

Public, 300/min per address. Creates a participant and logs them in (sets the `token` cookie). Returns 403 `Registration is closed` when `registration_open` is off. Also emails a 24-hour verification link to `<FRONTEND_ORIGIN>/verify-email?token=...` in the background; a failed send does not fail registration.

Request (all fields required):

```json
{
  "first_name": "Ivan",
  "last_name": "Ivanov",
  "email": "ivan@example.com",
  "password": "at-least-12-chars",
  "phone_number": "+359888123456",
  "faculty_number": "1MI0700123",
  "course": "Bachelor 2nd Year",
  "specialty_id": 1,
  "university_id": 1
}
```

Rules: names may not contain `< > & ; " \`; email must look like an address (stored lowercased); `course` must be one of `Bachelor 1st Year` to `Bachelor 4th Year`, `Masters 1st Year` or `Masters 2nd Year`; password at least 12 characters; email and faculty number must be unique. At most 100 characters for each name, 255 for the email and 20 for the phone and faculty numbers. `specialty_id` and `university_id` are a positive integer, the same as a string (the form's `"1"`) or `"other"`; anything else returns `Invalid specialty_id` / `Invalid university_id`.

**"Other" university or specialty.** Send `"university_id": "other"` with `university_other`, or `"specialty_id": "other"` with `specialty_other`:

```json
{
  "university_id": "other",
  "university_other": { "name": "...", "city": "...", "country": "..." },
  "specialty_id": "other",
  "specialty_other": { "name": "..." }
}
```

Every field is required and follows the same name rules. A value longer than 200 characters for a university or specialty name, or 100 for city and country, is cut to that length, not refused. The entry is created with `is_seed = false` in the same transaction as the participant, so it only exists if the registration succeeds. If the name already exists in any letter case, that row is reused, and a curated row wins over a typed one. "Other" entries are never shown in the dropdowns (those list curated rows only). This is the only way to add a university or specialty.

| Code | Meaning                                                                                 |
| ---- | --------------------------------------------------------------------------------------- |
| 201  | `{"success": true, "user_id": 7, "role": "participant", "user": {...profile}}`          |
| 400  | Missing fields or validation error                                                      |
| 403  | Registration is closed                                                                  |
| 409  | `An account with these details already exists.` (deliberately does not say which field) |
| 429  | Rate limited, or the server is busy (see Conventions)                                   |

The `user` profile shape is the same as `GET /api/auth/me`.

### POST /api/auth/login

Public. 15 attempts per minute per account (email and role), counted when each arrives, so parallel guesses can't slip past; a successful login clears the count, and a blocked account stays blocked from every address until its oldest counted attempt is a minute old. The admin account is limited the same way. Plus 300 attempts per minute per address.

```json
{ "email": "ivan@example.com", "password": "...", "role": "participant" }
```

`role` is `participant` (default), `mentor` or `admin`. Admin credentials are checked against `ADMIN_EMAIL` / `ADMIN_PASSWORD_HASH`; the admin token has `user_id` 0.

| Code | Meaning                                                                                     |
| ---- | ------------------------------------------------------------------------------------------- |
| 200  | `{"success": true, "user_id": 7, "role": "participant", "user": {...}}` plus `token` cookie |
| 400  | Missing email/password or invalid role                                                      |
| 401  | `Invalid email or password` / `Invalid admin credentials`                                   |
| 429  | Rate limited, or the server is busy (see Conventions)                                       |
| 503  | Admin login attempted but `ADMIN_PASSWORD_HASH` is unset or not a bcrypt hash               |

### POST /api/auth/logout

Public. Revokes the current token's `jti` (when Redis is available) and clears the cookie. Always 200 `{"success": true}`.

### GET /api/auth/me

Any role. Current user profile.

Participant:

```json
{
  "success": true,
  "user": {
    "id": 7,
    "role": "participant",
    "first_name": "Ivan",
    "last_name": "Ivanov",
    "email": "ivan@example.com",
    "phone_number": "+359888123456",
    "faculty_number": "1MI0700123",
    "course": "Bachelor 2nd Year",
    "specialty": "Software Engineering",
    "university": "Sofia University \"St. Kliment Ohridski\"",
    "is_captain": true,
    "team_id": 3,
    "team_name": "Code Wizards",
    "join_code": "K7Q2ZP9M",
    "status": "active",
    "email_verified": true
  }
}
```

`join_code` is `null` unless the participant is the team's captain. Mentor: `id, first_name, last_name, email, phone_number, company_name, bio, status, role`. Admin: `{"role": "admin"}`. 404 if the participant/mentor row no longer exists.

### PATCH /api/auth/change-password

Participant or mentor, 10/min per user.

```json
{ "current_password": "...", "new_password": "at-least-12-chars" }
```

Revokes the current token, invalidates every other session for the user and sets a fresh `token` cookie so the caller stays logged in.

| Code | Meaning                                                                                                                               |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------- |
| 200  | `Password changed successfully`                                                                                                       |
| 400  | Missing fields, new password under 12 characters, or `Current password is incorrect` (not 401, which the SPA reads as a dead session) |
| 403  | Admin (admin password is config-only)                                                                                                 |
| 429  | Rate limited, or the server is busy (see Conventions); a busy 429 after the current password was checked still changes nothing        |

### POST /api/auth/reset-password

Public, 5/hour per email and role, 100/min per address. Emails a one-hour reset link to `<FRONTEND_ORIGIN>/reset-password?token=...&role=...`.

```json
{ "email": "ivan@example.com", "role": "participant" }
```

Always 200 with the same generic message whether or not the account exists. 400 if `email` is missing or `role` is not `participant`/`mentor`. If SMTP fails the token is deleted so the user can retry.

### POST /api/auth/reset-password/confirm

Public, 100/min per address.

```json
{ "token": "<from the link>", "role": "participant", "new_password": "at-least-12-chars" }
```

| Code | Meaning                                                                                         |
| ---- | ----------------------------------------------------------------------------------------------- |
| 200  | `Password has been reset. You can now log in.` (all existing sessions are invalidated)          |
| 400  | Missing fields, password too short, `Invalid or expired reset token`, `Reset token has expired` |
| 429  | Rate limited, or the server is busy (see Conventions); the token stays unused                   |

### POST /api/auth/verify-email

Public, 300/min per address. No login needed, so the link works on any device. The SPA's `/verify-email` page sends the token from the emailed link.

```json
{ "token": "<from the link>" }
```

| Code | Meaning                                                                                                                     |
| ---- | --------------------------------------------------------------------------------------------------------------------------- |
| 200  | `Your email address is verified.` The token is spent.                                                                       |
| 400  | Missing token, `This verification link is invalid or was already used.`, `This verification link has expired.` (after 24 h) |

### POST /api/auth/resend-verification

Participant, 3/hour per user and 30/min per address. Emails a fresh link and invalidates the previous unused one.

| Code | Meaning                                                   |
| ---- | --------------------------------------------------------- |
| 200  | `Verification link sent to <email>.`                      |
| 400  | `Your email address is already verified.`                 |
| 503  | `Could not send the verification email. Try again later.` |

---

## Lookups

### GET /api/universities

Public. Curated (seed) universities only. Cached about 1 h; the startup seeder invalidates it when it inserts rows.

```json
{
  "success": true,
  "universities": [{ "id": 1, "name": "...", "city": "Sofia", "country": "Bulgaria" }]
}
```

### GET /api/specialties

Public. Curated specialties, cached like universities: `{"success": true, "specialties": [{"id": 1, "name": "..."}]}`.

User-submitted "Other" entries are added only through [`POST /api/auth/register`](#post-apiauthregister).

---

## Teams

### GET /api/teams/registered

Public, optional auth. Registered teams in registration order. The team list is cached about 30 s and invalidated by every join, leave, kick, disband, accepted request and admin register/unregister; the per-caller flags below are computed on every request.

```json
{
  "success": true,
  "teams": [
    {
      "team_id": 3,
      "team_name": "Code Wizards",
      "status": "active",
      "participant_count": 4,
      "registered_at": "Sun, 01 Mar 2026 10:00:00 GMT"
    }
  ],
  "can_apply": false,
  "max_registered": 18
}
```

When the caller is a participant without a team, `can_apply` is true and each team gains `already_applied` and `is_full`.

### GET /api/teams/{team_id}/members/public

Public. `members`: first and last names of a registered team's active members (captain first). 404 for unregistered teams.

### GET /api/teams/{team_id}

Any role. `team`: the team row with `members` and assigned `mentors` (`mentor_id`, `mentor_name`, `company_name`, `picture_url`: the photo's path, which the frontend serves, or null), ordered by last and first name. `mentors` is empty until the admin confirms matching, except for the admin. Member emails are only included for team members and admins, and `join_code` only for the team's captain and admins. `score` and `score_updated_at` are only included for the admin until `rankings_live` is on.

There is no public list of all teams. The admin gets every team from `GET /api/admin/teams/registration-status`.

### POST /api/teams

Participant. Creates a team with the caller as captain.

```json
{ "team_name": "Code Wizards" }
```

201 `{"success": true, "message": "Team created successfully", "team": {...}}`, with the `join_code`. The caller's other pending join requests become `invalidated`. 400 for a blank or taken name, a name over 100 characters, HTML characters or if the caller is already on a team. 403 `email_unverified` while email verification is required.

### POST /api/teams/join

Participant. `{"join_code": "K7Q2ZP9M"}` (case-insensitive). 200 with the updated team (without its `join_code`, or its score before `rankings_live`); the caller's pending join request to this team becomes `accepted` and the others become `invalidated`. 400 for an invalid code, a full team (6), a disqualified team or if the caller already has a team. 403 `email_unverified` while email verification is required. Reaching 3 members activates the team and registers or queues it.

### POST /api/teams/{team_id}/leave

Participant. Leaves the caller's current team (the path id is not checked). A captain leaving disbands the team. Dropping below 3 members deactivates the team and frees its slot or queue position.

### DELETE /api/teams/{team_id}

Captain of `team_id`. Disbands the team: members are released, and its join requests, preferences and mentor assignments are deleted with it.

### DELETE /api/teams/{team_id}/members/{member_id}

Captain of `team_id`. Removes a member. The captain cannot remove themselves.

### GET /api/teams/available

Participant. `teams`: every team with fewer than 6 members that is not disqualified, registered or not, each with `team_id, team_name, status, participant_count, already_applied`.

### GET /api/teams/my-applications

Participant. `applications`: the caller's join requests, newest first: `request_id, team_id, team_name, team_status, participant_count, status, created_at`. Status is one of `pending`, `accepted`, `declined`, `invalidated`, `cancelled`.

### POST /api/teams/{team_id}/apply

Participant without a team. Creates (or re-opens) a pending join request and emails the captain in the background. 201 `Application submitted`. 400 if already on a team, the team is full or disqualified or a request is already pending. 403 `email_unverified` while email verification is required.

### GET /api/teams/{team_id}/requests

Captain of `team_id`. `requests`: pending requests, oldest first: `request_id, participant_id, first_name, last_name, email, specialty, university, created_at`.

### POST /api/teams/requests/{request_id}/accept

Captain of the request's team (a request to another team returns 400). Adds the applicant, invalidates their other pending requests, activates/registers the team at 3 members. 400 if the request is no longer pending, the applicant already joined elsewhere or the team is full or disqualified.

### POST /api/teams/requests/{request_id}/decline

Captain of the request's team (a request to another team returns 400). Marks it `declined`.

### POST /api/teams/requests/{request_id}/cancel

Participant who owns the request. Marks it `cancelled`.

---

## Mentors and preferences

### GET /api/mentors

Public. Active mentors, cached about 30 min and invalidated when the startup seeder adds mentors (no API adds or removes one).

```json
{
  "success": true,
  "mentors": [
    {
      "mentor_id": 4,
      "name": "Maria Petrova",
      "first_name": "Maria",
      "last_name": "Petrova",
      "company_name": "...",
      "bio": "...",
      "technologies": ["Python", "Kubernetes"],
      "picture_url": "/mentorPictures/maria.webp",
      "picture_filename": "maria.webp",
      "availability_text": "..."
    }
  ]
}
```

Exactly these fields, newest mentor first. A mentor's email, phone number and account state never reach this public response.

### GET /api/teams/{team_id}/available-mentors

Captain of `team_id`. `mentors`: active mentors to rank: `mentor_id, name, company_name, bio, picture_url, picture_filename, availability_text`.

### POST /api/teams/{team_id}/mentor-preferences

Captain of `team_id`. Replaces the team's ranking.

```json
{
  "preferences": [
    { "mentor_id": 4, "rank": 1 },
    { "mentor_id": 9, "rank": 2 },
    { "mentor_id": 2, "rank": 3 }
  ]
}
```

403 `Preference submission is closed` while `preferences_open` is off, before the body is read (a captain of another team still gets `Not your team` first); nothing is written. The save re-checks the flag inside its transaction under a row lock, counting a schedule that has come due, so a close that commits while the save is under way still refuses it. Exactly 3 distinct active mentors with ranks 1, 2 and 3, otherwise 400. `mentor_id` and `rank` must be JSON integers (`Each preference needs a whole-number mentor_id and rank`). The team must be active and registered, since matching takes only registered teams; otherwise 400 `Only registered teams can rank mentors`.

After the save commits, the event feed gets "submitted" with the teams' progress on a first ranking, or "updated" on a later one. It names the team, never the mentors or ranks.

### GET /api/teams/{team_id}/mentor-preferences

Captain of `team_id`. `preferences`: `[{rank, mentor_id, mentor_name, company_name, picture_url}]` ordered by rank. Works whether or not submissions are open.

### GET /api/mentors/available-teams

Mentor. `teams`: active registered teams to rank: `team_id, team_name, participant_count`.

### POST /api/mentors/team-preferences

Mentor. Replaces the mentor's ranking.

```json
{
  "preferences": [
    { "team_id": 3, "rank": 1 },
    { "team_id": 8, "rank": 2 },
    { "team_id": 11, "rank": 3 }
  ]
}
```

403 `Preference submission is closed` while `preferences_open` is off, before the body is read; nothing is written. Re-checked under a row lock inside the save, as for teams. Exactly 3 distinct teams that are active and registered, ranks 1 to 3, otherwise 400. `team_id` and `rank` must be JSON integers (`Each preference needs a whole-number team_id and rank`). A mentor deactivated after logging in gets 400 `Mentor not found or inactive`.

After the save commits, the event feed gets "submitted" with the mentors' progress, or "updated". It names the mentor, never the teams or ranks.

### GET /api/mentors/team-preferences

Mentor. `preferences`: `[{rank, team_id, team_name}]` ordered by rank. Works whether or not submissions are open.

### GET /api/mentors/assigned-teams

Mentor. `teams`: the teams assigned by the last matching run: `team_id, team_name, participant_count`. Empty until the admin confirms the run.

### GET /api/matching-status

Public. `{"success": true, "confirmed": false}`.

---

## Rankings and regulations

### GET /api/teams/rankings

Public once `rankings_live` is on; until then 403 `Rankings are not live yet` for every caller, so scores entered before the reveal stay hidden (the admin reviews them through `GET /api/admin/teams/scores`). Registered teams by score, ties share a rank (`RANK()`), unscored teams last. Cached about 60 s and invalidated on every score change. The SPA polls it every 30 s when `rankings_live` is on. Exempt from rate limits: results are revealed at the venue, where every open page polls from one NAT address.

```json
{
  "success": true,
  "rankings": [
    {
      "team_id": 3,
      "team_name": "Code Wizards",
      "score": 87.5,
      "score_updated_at": "...",
      "participant_count": 4,
      "rank": 1
    }
  ]
}
```

### GET /api/ranking

Public. `rankings`: legacy rankings read from `backend/database/seeds/rankings.json` (`[{team, points, image}]`, highest points first, cached about 60 s). Not used by the SPA.

### GET /api/regulations

Public. FAQ-style rulebook from `backend/database/seeds/regulations.json`, cached about 300 s: `{"success": true, "regulations": [{"question": "...", "answer": "..."}]}`.

---

## Bug reports

### POST /api/bug-report

Public, optional auth, 10/min per user (per address when anonymous) and 30/min per address. Queues a post to each configured bug-report webhook (Discord `DISCORD_BUG_WEBHOOK_URL`, Slack `SLACK_BUG_WEBHOOK_URL`) and returns immediately.

```json
{ "what_did": "...", "what_happened": "...", "page": "https://fmicodes.com/team" }
```

Fields are truncated to 2000/2000/500 characters. 400 if both descriptions are empty. 202 `Bug report submitted — thank you!`. With a valid session (the `token` cookie, or `Authorization: Bearer`) the report carries the reporter's name, email and role. The token gets the same checks as on protected routes, so an expired, logged-out or password-changed token is treated as no token. Without one the report is still accepted as "Anonymous", for example from the registration page before an account exists.

---

## Admin

All routes in this section require the admin token.

### GET /api/admin/teams/registration-status

```json
{
  "success": true,
  "registered_count": 12,
  "max_registered": 18,
  "queue_count": 2,
  "registered_teams": [{ "id": 3, "team_name": "...", "...": "..." }],
  "queued_teams": [],
  "unregistered_teams": []
}
```

`unregistered_teams` lists active teams that are neither registered nor queued.

### POST /api/admin/teams/{team_id}/register

Registers an active team if a slot is free, removing it from the queue. 400 if not active, already registered, or all 18 slots are taken.

### POST /api/admin/teams/{team_id}/unregister

Unregisters a team. Does not promote anyone from the queue.

### GET /api/admin/preference-status

```json
{
  "success": true,
  "teams": [{ "id": 3, "team_name": "...", "submitted": true }],
  "mentors": [{ "id": 4, "name": "...", "company_name": "...", "submitted": false }],
  "teams_total": 18,
  "teams_submitted": 15,
  "mentors_total": 20,
  "mentors_submitted": 17,
  "all_submitted": false
}
```

### POST /api/admin/run-matching

Runs matching, replaces all assignments and resets confirmation. Always attempts to run; missing preferences produce warnings, not errors. It runs whether or not `preferences_open` is on; Mission Control's confirm dialog warns while it is, since rankings can still change after the run.

```json
{
  "success": true,
  "message": "Matching complete: 54 assignments across 18 teams and 20 mentors",
  "assignment_count": 54,
  "assignments": { "3": [4, 9, 2] },
  "warnings": ["2 team(s) have not submitted mentor preferences"]
}
```

400 if there are no active registered teams or no active mentors. 500 if saving fails. A saved run is posted to the event feed with its counts and warnings, never the pairs, and says so when it cleared a confirmation.

### POST /api/admin/confirm-matching

Marks the current results final; teams and mentors start seeing assignments. A later `run-matching` resets this. Confirming posts to the event feed only when the results were not already confirmed, so a repeat call posts nothing.

### GET /api/admin/matching-results

`results`: `[{team_id, team_name, mentor_id, mentor_name, company_name, assigned_at}]`.

### GET /api/admin/matching-export

Results grouped by team plus constraint checks.

```json
{
  "success": true,
  "teams": [{ "team_name": "...", "mentors": [{ "mentor_name": "...", "company_name": "..." }] }],
  "total_assignments": 54,
  "violations": [],
  "generated_at": "2026-03-14T18:00:00+00:00"
}
```

`violations` flags any team or mentor with more than 3 assignments. The SPA's EXPORT button expects an `export` string field that this endpoint does not return (known bug).

### GET /api/admin/teams/scores

`teams`: registered teams for the scoring UI, by name: `team_id, team_name, score, score_updated_at, participant_count`.

### PUT /api/admin/teams/{team_id}/score

```json
{ "score": 87.5 }
```

Finite number from 0 to 100. Invalidates the public rankings cache. 400 for invalid scores, 404 for an unknown team.

### GET /api/admin/flags

Every feature flag with its value, when the value last changed and any pending schedule. Applies a schedule whose time has passed first.

```json
{
  "success": true,
  "flags": [
    {
      "name": "registration_open",
      "enabled": false,
      "updated_at": "2026-11-09T08:00:00+00:00",
      "scheduled_value": true,
      "scheduled_at": "2026-11-20T08:00:00+00:00"
    }
  ]
}
```

Flags: `registration_open`, `preferences_open`, `rankings_live`, `mentors_stay_tuned`. Any other `{name}` in the routes below returns 404.

### PUT /api/admin/flags/{name}

Switches a flag now. Idempotent: setting the current value returns `changed: false` and posts nothing. A change is posted to the event feed (`SLACK_EVENTS_WEBHOOK_URL`). A pending schedule is kept; if it later sets the value the flag already has, it is cleared without a post.

```json
{ "enabled": true }
```

Response `{"success": true, "changed": true}`. 400 unless `enabled` is a JSON boolean.

### PUT /api/admin/flags/{name}/schedule

Schedules a change; replaces any pending one (one per flag). No scheduler runs it: the first read of the flags after `at` (any visitor's `GET /api/config`, a registration, the admin's list) applies it in a transaction that locks the row, so it is applied and posted to the event feed exactly once. The database clock decides when `at` has passed.

```json
{ "value": true, "at": "2026-11-20T10:00:00+02:00" }
```

400 if `value` is not a boolean, `at` is not ISO 8601 with a UTC offset (`Z` or `+02:00`), `at` is not in the future (`Scheduled time must be in the future`) or `value` is the current value (`The flag is already on` / `off`; when a schedule is pending the message adds that cancelling it keeps the current value).

### DELETE /api/admin/flags/{name}/schedule

Drops the pending schedule. Idempotent: `{"success": true, "cancelled": false}` when there was none.
