# API Reference

Base URL: same origin as the SPA (`https://fmicodes.com`). Local: `http://localhost:5001`, or through the Vite dev proxy at `http://localhost:5173`.

All bodies are JSON. Every route lives under `/api`. The contract is hand maintained; the frontend types in `frontend/src/types/` mirror these shapes manually.

## Conventions

**Response envelope.** Most endpoints return `{"success": true, ...}` or `{"success": false, "error": "<message>"}`. Exceptions: `/api/health`, `/api/health/ready` and `/api/config` return bare objects.

**Authentication.** Login and registration set an httpOnly cookie named `token` (JWT, HS256, 3-day expiry, `SameSite=Lax`, `Secure` in production). Send it back with every request (`credentials: 'include'`). For scripts, `Authorization: Bearer <token>` works on every protected route.

| Guard       | Meaning                                                                                  | Failure   |
| ----------- | ---------------------------------------------------------------------------------------- | --------- |
| public      | No token needed                                                                          | n/a       |
| any         | Any valid token                                                                          | 401       |
| participant | Token role `participant`                                                                 | 401 / 403 |
| captain     | Participant who is captain; most routes also require the path `team_id` to be their team | 401 / 403 |
| mentor      | Token role `mentor`                                                                      | 401 / 403 |
| admin       | Token role `admin`                                                                       | 401 / 403 |

401 bodies: `Authentication required`, `Token expired`, `Invalid token`, `Token has been revoked`.

**Rate limits.** Default 200 requests per minute per IP, shared across workers when Redis is configured. Tighter limits are listed per endpoint. Exceeding a limit returns 429.

**Feature flags.** `REGISTRATION_OPEN`, `MENTORS_STAY_TUNED`, `RANKINGS_LIVE` and `REQUIRE_EMAIL_VERIFICATION` come from server config. Three are enforced by the API: `REGISTRATION_OPEN` (registration returns 403 when closed), `RANKINGS_LIVE` (team scores stay hidden from everyone but the admin until rankings are live) and `REQUIRE_EMAIL_VERIFICATION` (see below). `MENTORS_STAY_TUNED` only changes what the SPA renders.

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

Public. Feature flags for the SPA.

```json
{
  "REGISTRATION_OPEN": false,
  "MENTORS_STAY_TUNED": false,
  "RANKINGS_LIVE": false,
  "REQUIRE_EMAIL_VERIFICATION": false
}
```

### GET /metrics

Prometheus exposition from `prometheus_flask_exporter`, at the backend root (not under `/api`). Only reachable in-cluster; the public ingress sends `/metrics` to the frontend.

---

## Auth

### POST /api/auth/register

Public, 10/min. Creates a participant and logs them in (sets the `token` cookie). Returns 403 `Registration is closed` when `REGISTRATION_OPEN` is false. Also emails a 24-hour verification link to `<FRONTEND_ORIGIN>/verify-email?token=...` in the background; a failed send does not fail registration.

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

Rules: names may not contain `< > & ; " \`; email must look like an address (stored lowercased); `course` must be one of `Bachelor 1st Year` to `Bachelor 4th Year` or `Masters 1st Year` to `Masters 6th Year`; password at least 12 characters; email and faculty number must be unique.

**"Other" university or specialty.** Send `"university_id": "other"` with `university_other`, or `"specialty_id": "other"` with `specialty_other`:

```json
{
  "university_id": "other",
  "university_other": { "name": "...", "city": "...", "country": "..." },
  "specialty_id": "other",
  "specialty_other": { "name": "..." }
}
```

Every field is required and follows the same name rules. The entry is created with `is_seed = false` in the same transaction as the participant, so it only exists if the registration succeeds. If the name already exists in any letter case, that row is reused, and a curated row wins over a typed one. "Other" entries are never shown in the dropdowns (those list curated rows only). This is the only way to add a university or specialty.

| Code | Meaning                                                                                 |
| ---- | --------------------------------------------------------------------------------------- |
| 201  | `{"success": true, "user_id": 7, "role": "participant", "user": {...profile}}`          |
| 400  | Missing fields or validation error                                                      |
| 403  | Registration is closed                                                                  |
| 409  | `An account with these details already exists.` (deliberately does not say which field) |

The `user` profile shape is the same as `GET /api/auth/me`.

### POST /api/auth/login

Public, 15/min.

```json
{ "email": "ivan@example.com", "password": "...", "role": "participant" }
```

`role` is `participant` (default), `mentor` or `admin`. Admin credentials are checked against `ADMIN_EMAIL` / `ADMIN_PASSWORD_HASH`; the admin token has `user_id` 0.

| Code | Meaning                                                                                     |
| ---- | ------------------------------------------------------------------------------------------- |
| 200  | `{"success": true, "user_id": 7, "role": "participant", "user": {...}}` plus `token` cookie |
| 400  | Missing email/password or invalid role                                                      |
| 401  | `Invalid email or password` / `Invalid admin credentials`                                   |
| 503  | Admin login attempted but `ADMIN_PASSWORD_HASH` is unset                                    |

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

Mentor: `id, first_name, last_name, email, phone_number, company_name, bio, status, role`. Admin: `{"role": "admin"}`. 404 if the participant/mentor row no longer exists.

### PATCH /api/auth/change-password

Participant or mentor, 10/min.

```json
{ "current_password": "...", "new_password": "at-least-12-chars" }
```

Revokes the current token, invalidates every other session for the user and sets a fresh `token` cookie so the caller stays logged in.

| Code | Meaning                                            |
| ---- | -------------------------------------------------- |
| 200  | `Password changed successfully`                    |
| 400  | Missing fields or new password under 12 characters |
| 401  | `Current password is incorrect`                    |
| 403  | Admin (admin password is config-only)              |

### POST /api/auth/reset-password

Public, 5/hour. Emails a one-hour reset link to `<FRONTEND_ORIGIN>/reset-password?token=...&role=...`.

```json
{ "email": "ivan@example.com", "role": "participant" }
```

Always 200 with the same generic message whether or not the account exists. 400 if `email` is missing or `role` is not `participant`/`mentor`. If SMTP fails the token is deleted so the user can retry.

### POST /api/auth/reset-password/confirm

Public, 10/hour.

```json
{ "token": "<from the link>", "role": "participant", "new_password": "at-least-12-chars" }
```

| Code | Meaning                                                                                         |
| ---- | ----------------------------------------------------------------------------------------------- |
| 200  | `Password has been reset. You can now log in.` (all existing sessions are invalidated)          |
| 400  | Missing fields, password too short, `Invalid or expired reset token`, `Reset token has expired` |

### POST /api/auth/verify-email

Public, 20/hour. No login needed, so the link works on any device. The SPA's `/verify-email` page sends the token from the emailed link.

```json
{ "token": "<from the link>" }
```

| Code | Meaning                                                                                                                     |
| ---- | --------------------------------------------------------------------------------------------------------------------------- |
| 200  | `Your email address is verified.` The token is spent.                                                                       |
| 400  | Missing token, `This verification link is invalid or was already used.`, `This verification link has expired.` (after 24 h) |

### POST /api/auth/resend-verification

Participant, 3/hour. Emails a fresh link and invalidates the previous unused one.

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

Public. First and last names of a registered team's active members (captain first). 404 for unregistered teams.

### GET /api/teams/{team_id}

Any role. Team detail with `members` and assigned `mentors` (`mentor_id`, `mentor_name`, `company_name`). Member emails and `join_code` are only included for team members and admins. `score` and `score_updated_at` are only included for the admin until `RANKINGS_LIVE` is on.

There is no public list of all teams. The admin gets every team from `GET /api/admin/teams/registration-status`.

### POST /api/teams

Participant. Creates a team with the caller as captain.

```json
{ "team_name": "Code Wizards" }
```

201 `{"success": true, "message": "Team created successfully", "team": {...}}`. 400 for a blank or taken name, HTML characters, or if the caller is already on a team. 403 `email_unverified` while email verification is required.

### POST /api/teams/join

Participant. `{"join_code": "K7Q2ZP9M"}` (case-insensitive). 200 with the updated team. 400 for an invalid code, a full team (6), a disqualified team, or if the caller already has a team. 403 `email_unverified` while email verification is required. Reaching 3 members activates the team and registers or queues it.

### POST /api/teams/{team_id}/leave

Participant. Leaves the caller's current team (the path id is not checked). A captain leaving disbands the team. Dropping below 3 members deactivates the team and frees its slot or queue position.

### DELETE /api/teams/{team_id}

Captain of `team_id`. Disbands the team: members are released, pending join requests invalidated, preferences and mentor assignments deleted.

### DELETE /api/teams/{team_id}/members/{member_id}

Captain of `team_id`. Removes a member. The captain cannot remove themselves.

### GET /api/teams/available

Participant. Teams with fewer than 6 members that are not disqualified, each with `already_applied`.

### GET /api/teams/my-applications

Participant. The caller's join requests: `request_id, team_id, team_name, team_status, participant_count, status, created_at`. Status is one of `pending`, `accepted`, `declined`, `invalidated`, `cancelled`.

### POST /api/teams/{team_id}/apply

Participant without a team. Creates (or re-opens) a pending join request and emails the captain in the background. 201 `Application submitted`. 400 if already on a team, the team is full, or a request is already pending. 403 `email_unverified` while email verification is required.

### GET /api/teams/{team_id}/requests

Captain of `team_id`. Pending requests with applicant `first_name, last_name, email, specialty, university, created_at`.

### POST /api/teams/requests/{request_id}/accept

Captain of the request's team. Adds the applicant, invalidates their other pending requests, activates/registers the team at 3 members. 400 if the request is no longer pending, the applicant already joined elsewhere, or the team is full.

### POST /api/teams/requests/{request_id}/decline

Captain of the request's team. Marks it `declined`.

### POST /api/teams/requests/{request_id}/cancel

Participant who owns the request. Marks it `cancelled`.

---

## Mentors and preferences

### GET /api/mentors

Public. Active mentors, cached about 30 min and invalidated when mentors are added or removed (including by the startup seeder).

```json
{
  "success": true,
  "mentors": [
    {
      "mentor_id": 4,
      "name": "Maria Petrova",
      "first_name": "Maria",
      "last_name": "Petrova",
      "email": "...",
      "phone_number": "...",
      "company_name": "...",
      "bio": "...",
      "status": "active",
      "technologies": ["Python", "Kubernetes"],
      "picture_url": "/static/mentorPictures/maria.jpg",
      "picture_filename": "maria.jpg",
      "availability_text": "...",
      "created_at": "..."
    }
  ]
}
```

Note: this public response includes mentor email and phone number.

### GET /api/mentors/{mentor_id}/picture

Public. Intended to stream the mentor photo. Known bug: `picture_url` holds a path string, which this handler cannot wrap, so it returns 500 for seeded mentors. The SPA's mentor cards use `picture_url` directly instead (served from `/static/mentorPictures/`).

### GET /api/teams/{team_id}/available-mentors

Captain of `team_id`. Active mentors to rank: `mentor_id, name, company_name, bio, picture_url, picture_filename, availability_text`.

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

Exactly 3 distinct active mentors with ranks 1, 2 and 3, otherwise 400.

### GET /api/teams/{team_id}/mentor-preferences

Captain of `team_id`. `[{rank, mentor_id, mentor_name, company_name, picture_url}]` ordered by rank.

### GET /api/mentors/available-teams

Mentor. Active registered teams to rank: `team_id, team_name, participant_count`.

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

Exactly 3 distinct teams that are active and registered, ranks 1 to 3, otherwise 400.

### GET /api/mentors/team-preferences

Mentor. `[{rank, team_id, team_name}]`.

### GET /api/mentors/assigned-teams

Mentor. Teams assigned by the last matching run: `team_id, team_name, participant_count`. The SPA only calls this after the admin confirms.

### GET /api/matching-status

Public. `{"success": true, "confirmed": false}`.

---

## Rankings and regulations

### GET /api/teams/rankings

Public once `RANKINGS_LIVE` is on; until then 403 `Rankings are not live yet` for every caller, so scores entered before the reveal stay hidden (the admin reviews them through `GET /api/admin/teams/scores`). Registered teams by score, ties share a rank (`RANK()`), unscored teams last. Cached about 60 s and invalidated on every score change. The SPA polls it every 30 s when `RANKINGS_LIVE` is on.

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

Public. Legacy rankings read from `backend/database/seeds/rankings.json` (`[{team, points, image}]`). Not used by the SPA.

### GET /api/regulations

Public. FAQ-style rulebook from `backend/database/seeds/regulations.json`, cached about 300 s: `{"success": true, "regulations": [{"question": "...", "answer": "..."}]}`.

---

## Bug reports

### POST /api/bug-report

Public, optional auth, 10/min. Queues a Discord webhook post and returns immediately.

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

Runs matching, replaces all assignments and resets confirmation. Always attempts to run; missing preferences produce warnings, not errors.

```json
{
  "success": true,
  "message": "Matching complete: 54 assignments across 18 teams and 20 mentors",
  "assignment_count": 54,
  "assignments": { "3": [4, 9, 2] },
  "warnings": ["2 team(s) have not submitted mentor preferences"]
}
```

400 if there are no active registered teams or no active mentors. 500 if saving fails.

### POST /api/admin/confirm-matching

Marks the current results final; teams and mentors start seeing assignments. A later `run-matching` resets this.

### GET /api/admin/matching-results

`[{team_id, team_name, mentor_id, mentor_name, company_name, assigned_at}]`.

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

Registered teams for the scoring UI: `team_id, team_name, score, score_updated_at, participant_count`.

### PUT /api/admin/teams/{team_id}/score

```json
{ "score": 87.5 }
```

Finite number from 0 to 100. Invalidates the public rankings cache. 400 for invalid scores, 404 for an unknown team.
