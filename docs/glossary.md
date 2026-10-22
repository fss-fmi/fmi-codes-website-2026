# Glossary

Domain terms used across the code, the API and the UI. General web and framework terms are left out.

## A

### Active (team)

A team with at least 3 members (`ACTIVE_THRESHOLD`). Only active teams can be registered, queued, ranked by mentors or matched. Stored as `teams.status = 'active'`. See **Team status**.

### Admin

The organizer account. A single credential defined in config (`ADMIN_EMAIL` + `ADMIN_PASSWORD_HASH`), with no database row and `user_id` 0 in its token. Runs everything from **Mission Control**. Its password cannot be changed or reset through the app.

### Application

See **Join request**. The UI says "application" (MY APPLICATIONS, APPLY TO JOIN); the code and database say `team_join_requests`.

### Assignment

One (team, mentor) pair produced by **Matching** and stored in `team_mentors`. Teams and mentors only see their assignments after the admin **confirms** matching.

## C

### Captain

The participant who created a team (`participants.is_captain`, `teams.captain_id`). Only the captain sees the join code, accepts or declines join requests, removes members, ranks mentors and disbands the team. If the captain leaves, the team is disbanded. Captaincy cannot be transferred.

### Confirmed (matching)

`matching_state.is_confirmed`. Set by the admin after reviewing a matching run; until then teams and mentors keep seeing their own preferences. Any new matching run resets it to unconfirmed.

### Course

A participant's study year. One of `Bachelor 1st Year` .. `Bachelor 4th Year` or `Masters 1st Year` .. `Masters 6th Year`, enforced by a database CHECK.

## D

### Disband

Deleting a team. Members are released (they become teamless), pending join requests become `invalidated`, preferences and assignments are deleted, and the team's registration slot or queue position is freed.

## F

### Faculty number

The university-issued student ID entered at registration (for example `1MI0700123`). Unique per participant.

### Feature flags

Four booleans set in server config, not in an admin screen:

| Flag                         | When true                                                                 |
| ---------------------------- | ------------------------------------------------------------------------- |
| `REGISTRATION_OPEN`          | Participants can register                                                 |
| `MENTORS_STAY_TUNED`         | The mentors page shows a "coming soon" placeholder                        |
| `RANKINGS_LIVE`              | Scores are public: the live leaderboard and API                           |
| `REQUIRE_EMAIL_VERIFICATION` | Unverified participants cannot create, join or apply to teams (see below) |

## G

### Gale-Shapley

The stable-matching algorithm used in phase 1 of **Matching**. Here it is mentor-proposing and many-to-many: each team holds at most 3 mentors, each mentor at most 3 teams.

### Greedy fill

Phase 2 of **Matching**. Tops up any team still below 3 mentors with the least-loaded mentors that have spare capacity, regardless of preferences.

## J

### Join code

An 8-character uppercase alphanumeric code generated when a team is created (`teams.join_code`). Anyone holding it can join instantly without captain approval, so captains share it only with teammates. UI label: "INVITE CODE" on the join page, "JOIN CODE" on the team page.

### Join request

A teamless participant's request to join a team, created from BROWSE TEAMS or the public TEAMS page. Lifecycle:

`pending` → `accepted` | `declined` | `cancelled` | `invalidated`

- `accepted`: captain accepted; the applicant joins the team and all their other pending requests become `invalidated`.
- `declined`: captain declined.
- `cancelled`: applicant withdrew it.
- `invalidated`: the applicant joined another team first, or the team was disbanded.

Re-applying to the same team reopens the same row as `pending`.

## M

### Matching

The admin-triggered process that assigns mentors to registered teams: **Gale-Shapley** then **Greedy fill**. Target: every team gets 2 or 3 mentors and never more than 3. A mentor can be assigned up to 3 teams. Results are reviewed, optionally exported, then **confirmed**.

### Mentor

An industry volunteer onboarded by the organizers (seeded from `backend/database/seeds/mentors.json`, no self-signup). Has a public profile, ranks 3 teams and helps their assigned teams on site.

### Mentor preferences

A captain's ranking of exactly 3 distinct mentors, ranks 1 to 3 (`team_mentor_preferences`). Rank 1 is the first choice.

### Mission Control

The admin console at `/admin/matching`, with REGISTRATION, PREFERENCES, MATCHING and SCORES tabs.

## P

### Participant

A student who registers on the site. Belongs to at most one team at a time.

### Pending (team)

A team with fewer than 3 members. Not eligible for registration. Shown in the UI with a PENDING badge and the banner "Your team needs at least 3 members to be eligible for the hackathon."

### Promote (queue)

Moving the first team in the **Queue** into a freed **Registration slot**. Happens automatically when a registered team drops below 3 members or is disbanded. Not to be confused with promoting a release to production.

## Q

### Queue

The waiting list for teams that became active after all 18 **registration slots** were taken (`teams.queue_position`, 1-based). Positions shift up when a team ahead leaves the queue.

## R

### Registered (team)

A team holding one of the 18 event slots (`teams.is_registered`). The first 18 teams to become active register automatically; the admin can also register or unregister manually. Only registered teams can be ranked by mentors, matched and scored.

### Registration slot

One of the 18 places at the event (`MAX_REGISTERED_TEAMS`).

### Revocation epoch

`tokens_valid_from` on participants and mentors. Changing or resetting a password sets it to now, which rejects every login token issued before that moment.

## S

### Score

A team's final judged result, 0 to 100, entered by the admin after in-person judging (`teams.score`). The jury scores idea (15), implementation (55) and presentation (30) off-platform; only the total is stored. Ties share a rank on the leaderboard.

### Seed data

Curated universities, specialties and mentors loaded from JSON on every backend start. `is_seed = true` marks curated universities and specialties; "Other" entries typed at registration are stored with `is_seed = false` and do not appear in dropdowns.

### Specialty

A participant's field of study, picked from a curated list or added via "Other".

## T

### Team preferences

A mentor's ranking of exactly 3 distinct registered teams, ranks 1 to 3 (`mentor_team_preferences`).

### Team status

`teams.status`. Code sets only two values:

`pending` (under 3 members) ↔ `active` (3 to 6 members)

The schema also allows `completed` and `disqualified`; nothing in the app sets them, but a `disqualified` team cannot be joined.

## V

### Verified email

`participants.email_verified`. Set when the participant opens the 24-hour link emailed at registration (or a resent one from **PROFILE**). Participants who registered before verification existed count as verified. Only enforced while `REQUIRE_EMAIL_VERIFICATION` is on, and only for creating, joining or applying to a team. Mentors are not verified; organizers create their accounts.

## Synonyms

| Code / database            | UI                                               | Canonical term here |
| -------------------------- | ------------------------------------------------ | ------------------- |
| `team_join_requests`       | Application, APPLY                               | Join request        |
| `join_code`                | INVITE CODE, JOIN CODE                           | Join code           |
| `teams.status = 'pending'` | PENDING badge, "needs at least 3 members" banner | Pending             |
| `is_registered`            | REGISTERED                                       | Registered          |
| `team_mentors`             | MENTORS, ASSIGNED TEAMS                          | Assignment          |
| `/admin/matching`          | ADMIN, MISSION CONTROL                           | Mission Control     |
