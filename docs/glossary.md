# Glossary

Domain terms used across the code, the API and the UI. General web and framework terms are left out.

## A

### Active (team)

A team with at least 3 members (`ACTIVE_THRESHOLD`). Only active teams can be registered, queued, ranked by mentors or matched. Stored as `teams.status = 'active'`. After matching is **confirmed**, a team the admin takes below 3 members stays active (see **Freeze**). See **Team status**.

### Admin

The organizer account. A single credential defined in config (`ADMIN_EMAIL` + `ADMIN_PASSWORD_HASH`), with no database row and `user_id` 0 in its token. Runs everything from **Mission Control**. Its password cannot be changed or reset through the app. Rotating it (`rotate-secret.sh ADMIN_PASSWORD_HASH`) does not end admin sessions already open, so after a leak `JWT_SECRET_KEY` must be rotated too, which logs everyone out (see [Rotate a secret](runbook/secrets.md#rotate-a-secret)).

### Application

See **Join request**. The UI says "application" (MY APPLICATIONS, APPLY TO JOIN); the code and database say `team_join_requests`.

### Assignment

One (team, mentor) pair produced by **Matching** and stored in `team_mentors`. Teams and mentors only see their assignments after the admin **confirms** matching.

## C

### Captain

The participant who created a team (`participants.is_captain`, `teams.captain_id`). Only the captain sees the join code, accepts or declines join requests, removes members, ranks mentors and disbands the team. If the captain leaves, the team is disbanded. Participants can't transfer captaincy; the admin can, by removing the captain in Mission Control's TEAMS tab and picking another member, who takes over in the same step.

### Confirmed (matching)

`matching_state.is_confirmed`. Set by the admin after reviewing a matching run; until then teams and mentors keep seeing their own preferences. While set, teams are under the **Freeze**. Any new matching run resets it to unconfirmed. `/api/config` exposes it as `MATCHING_CONFIRMED`.

### Course

A participant's study year. One of `Bachelor 1st Year` .. `Bachelor 4th Year`, `Masters 1st Year` or `Masters 2nd Year`, enforced by a database CHECK.

## D

### Disband

Deleting a team. Members are released (they become teamless), its join requests, preferences and assignments are deleted with it and the team's registration slot or queue position is freed. Only the captain disbands, by DISBAND TEAM or by leaving, and not during the **Freeze**; the admin's member removals never disband a team.

## F

### Faculty number

The university-issued student ID entered at registration (for example `1MI0700123`). Unique per participant.

### Feature flags

Five booleans. Four live in the `feature_flags` table and are switched or scheduled by the admin on the **Mission Control** SITE tab; `/api/config` exposes them in upper case. The fifth is server config:

| Flag                         | Where           | When true                                                                 |
| ---------------------------- | --------------- | ------------------------------------------------------------------------- |
| `registration_open`          | Mission Control | Participants can register                                                 |
| `preferences_open`           | Mission Control | Captains and mentors can submit and change their rankings                 |
| `mentors_stay_tuned`         | Mission Control | The mentors page shows a "coming soon" placeholder                        |
| `rankings_live`              | Mission Control | Scores are public: the live leaderboard and API                           |
| `REQUIRE_EMAIL_VERIFICATION` | Server config   | Unverified participants cannot create, join or apply to teams (see below) |

A flag holds at most one **scheduled change** (`scheduled_value` at `scheduled_at`), applied by the first request after its time. Every change is posted to the environment's event feed in Slack.

### Freeze

What a **confirmed** matching does to teams. Participants can't create, join, apply to, leave or disband a team, captains can't remove members or accept applications, and nobody can change a ranking; declining and withdrawing an application still work. The pages say "Teams are locked while the event runs. For any changes, contact the organizers." Nothing moves a **Registration slot** by itself: a team below 3 keeps its slot and nobody is promoted, and a team the admin fills to 3 joins the end of the **Queue**. The admin changes members and mentors by hand in Mission Control's TEAMS tab. A new matching run lifts it until the next confirm ([ADR-019](adr/019-freeze-teams-on-confirmed-matching.md)).

## G

### Gale-Shapley

The stable-matching algorithm used in phase 1 of **Matching**. Here it is mentor-proposing and many-to-many: each team holds at most 3 mentors, each mentor at most 3 teams.

### Greedy fill

Phase 2 of **Matching**. Hands out the mentors with spare capacity one at a time, each to the team with the fewest mentors and from the least-loaded mentors first, regardless of preferences, so a shortage spreads across teams instead of leaving some at 0. If a team is still under 2 and another has 3, the full team gives up the mentor it wants least and the fill runs again. Every team gets 2 or 3 whenever there are at least 2 mentors and 3 x mentors >= 2 x teams (12 mentors for 18 teams).

## J

### Join code

An 8-character uppercase alphanumeric code generated when a team is created (`teams.join_code`). Anyone holding it can join instantly without captain approval, so only the captain (and the admin) gets it from the API, and captains share it only with teammates. UI label: "INVITE CODE" on the join page, "JOIN CODE" on the captain's team page and PROFILE.

### Join request

A teamless participant's request to join a team, created from BROWSE TEAMS or the public TEAMS page. Lifecycle:

`pending` → `accepted` | `declined` | `cancelled` | `invalidated`

- `accepted`: captain accepted; the applicant joins the team.
- `declined`: captain declined.
- `cancelled`: applicant withdrew it.
- `invalidated`: the applicant got onto a team first: accepted elsewhere, joined with a code or created a team. Each of those invalidates all their other pending requests.

Re-applying to the same team reopens the same row as `pending`. Disbanding a team deletes every request to it.

## M

### Matching

The admin-triggered process that assigns mentors to registered teams: **Gale-Shapley** then **Greedy fill**. Target: every team gets 2 or 3 mentors and never more than 3. A mentor can be assigned up to 3 teams. Results are reviewed, optionally exported, then **confirmed**.

### Mentor

An industry volunteer onboarded by the organizers (seeded from the encrypted mentor seed Secret only: no self-signup and no API that creates or deletes mentors; see [Seed data](data.md#seed-data)). Has a public profile without their contacts, ranks 3 teams and helps their assigned teams on site. A mentor seeded without a password sets one through forgot password before their first login.

### Mentor preferences

A registered team's ranking of exactly 3 distinct mentors, set by its captain, ranks 1 to 3 (`team_mentor_preferences`). Rank 1 is the first choice. Teams that are not registered cannot submit one.

### Mission Control

The admin console at `/admin/matching`, with SITE, REGISTRATION, TEAMS, PREFERENCES, MATCHING and SCORES tabs.

## P

### Participant

A student who registers on the site. Belongs to at most one team at a time.

### Pending (team)

A team with fewer than 3 members. Not eligible for registration. Shown in the UI with a PENDING badge and the banner "Your team needs at least 3 members to be eligible for the hackathon."

### Promote (queue)

Moving the first team in the **Queue** that has its 3 members into a freed **Registration slot**. Happens automatically when a registered team drops below 3 members or is disbanded, until matching is confirmed (see **Freeze**). Not to be confused with promoting a release to production.

## Q

### Queue

The waiting list for teams that became active after all 18 **registration slots** were taken (`teams.queue_position`, 1-based). Positions shift up when a team ahead leaves the queue.

## R

### Registered (team)

A team holding one of the 18 event slots (`teams.is_registered`). The first 18 teams to become active register automatically; the admin can also register or unregister manually. Only registered teams can be ranked by mentors, matched, assigned mentors and scored; losing the slot releases the team's mentors.

### Registration slot

One of the 18 places at the event (`MAX_REGISTERED_TEAMS`).

### Revocation epoch

`tokens_valid_from` on participants and mentors. Changing or resetting a password sets it to now, which rejects every login token issued before that moment.

## S

### Score

A team's final judged result, 0 to 100, entered by the admin after in-person judging (`teams.score`). The jury scores idea (15), implementation (55) and presentation (30) off-platform; only the total is stored. Ties share a rank on the leaderboard.

### Seed data

Curated universities, specialties and mentors loaded from JSON on every backend start (the mentors from an encrypted Secret in the cluster, since they are personal data). `is_seed = true` marks curated universities and specialties; "Other" entries typed at registration are stored with `is_seed = false` and do not appear in dropdowns.

### Specialty

A participant's field of study, picked from a curated list or added via "Other".

## T

### Team preferences

A mentor's ranking of exactly 3 distinct registered teams, ranks 1 to 3 (`mentor_team_preferences`).

### Team status

`teams.status`. Code sets only two values:

`pending` (under 3 members) ↔ `active` (3 to 6 members)

The schema also allows `completed` and `disqualified`; nothing in the app sets them, but a `disqualified` team cannot be joined, applied to or have a request accepted.

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
