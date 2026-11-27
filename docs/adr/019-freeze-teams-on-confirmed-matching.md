# ADR-019: Confirmed matching freezes teams; the admin edits them by hand

**Status**: accepted. Narrows [ADR-004](004-advisory-lock-registration-queue.md): lock 2 now queues with team changes on one row.

## Context

Confirming matching publishes each team's mentors, but it froze nothing. Afterwards a participant could still leave, join, be removed or disband, the queue still promoted teams into freed slots and both sides could still re-rank. A team promoted after the confirmation had no mentors, a team that lost its slot kept its assignments and its mentors still listed it, and a re-run silently undid the whole published result. The only way out was a new matching run, which also replaced every assignment the organizers had told people about.

During the event the organizers still need to change things: a mentor falls ill, a captain goes home, a team turns out not to exist.

## Decision

- **The confirmed bit is the freeze.** While `matching_state.is_confirmed` is true, the server refuses with 403 every participant change to a team's members: create, join by code, apply, leave, a captain's remove, disband and accept. The text is "Teams are locked while the event runs. For any changes, contact the organizers." Both preference saves are refused too ("Matching is confirmed, so preferences can no longer change."), checked before the closed flag, since the admin closes submissions before the final run. Declining and withdrawing an application stay open: they change no team.
- **A new run lifts it.** Running matching clears the confirmation, as before, so the freeze ends until the next confirm. The RUN MATCHING dialog says a run replaces the hand edits and reopens team changes.
- **The escape hatch is targeted admin edits, not an unlock switch.** Mission Control's TEAMS tab adds a participant to a team by email (up to 6, skipping the email verification gate), removes one (a captain only with a successor picked in the same action; never the last member, and never a disband) and replaces a registered team's mentors. Mentor edits may go past 3 per team or 3 teams per mentor; the answer warns and the export's violations list them.
- **After confirmation nothing moves a slot by itself.** A team that drops below 3 keeps its slot and stays `active`, and nobody is promoted; a pending team that reaches 3 becomes active and joins the end of the queue, but is never registered (left out of the queue, it could never get in once the freeze lifts). The queue only ever promotes a team with its 3 members. A team taken below 3 keeps its slot after a re-run too; the admin unregisters it by hand. Register and unregister stay manual. Before confirmation the usual rules apply to admin edits too.
- **Every unregister releases the team's mentors**, automatic or by the admin, in the same transaction. The reads that show assignments also skip unregistered teams.
- **The SPA reads the bit as `MATCHING_CONFIRMED` in `/api/config`**, which open pages already poll every 30 s, so every page locks and unlocks within one poll. It is cached under the flags' versioned key and retired by the same bump ([ADR-013](013-feature-flags-in-database.md)); a refused change refetches it at once.
- **Lock order.** Every transaction that takes advisory lock 1 reads `matching_state ... FOR SHARE` as its next statement, before any row lock; the preference saves read it first. The writers of `team_mentors` (a matching save, an admin mentor edit) take lock 2 and then `matching_state ... FOR UPDATE` before touching that table. An insert into `team_mentors` takes a key-share lock on its `teams` row through the foreign key, so a lock-1 transaction holding a team row and then deleting assignments could deadlock against a save; with `matching_state` first, every writer queues on one row instead. A save also writes only the pairs whose team is still registered and active, since the run read its teams outside any transaction.

## Consequences

- **Easier**: what the organizers announce stays true until they change it, and every change is theirs, named in the event feed by team and count. A confirmation can be undone only on purpose, by a re-run.
- **Harder**: lock 2 now waits on team changes and the reverse, through `matching_state`; at event scale that is a few milliseconds. Every new lock-1 function has to call `frozen_locked` first, like taking lock 1 itself. An admin who wants teams open again for a while has to re-run matching, which replaces the hand edits.
- **Failure mode**: the SPA's lock note can trail the server by one poll (30 s); the server refuses either way, and the refusal refetches the flags.
