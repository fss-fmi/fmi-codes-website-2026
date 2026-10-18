# ADR-005: Many-to-many Gale-Shapley plus greedy fill for mentor matching

**Status**: accepted

## Context

Mentor assignment used to be done by hand, which was slow and open to favouritism. Both sides have preferences: each captain ranks 3 mentors and each mentor ranks 3 teams. The organizers' requirement is that every registered team ends up with **2 or 3 mentors, never more than 3**. With about 20 mentors and 18 teams there are not enough mentors to give each team 2 or 3 exclusive mentors, so mentors must be able to cover more than one team. Not everyone submits preferences on time.

## Decision

`backend/app/services/matching_service.py` runs two phases:

1. **Mentor-proposing Gale-Shapley, many-to-many**, with `TEAM_CAPACITY = 3` and `MENTOR_CAPACITY = 3`. Teams keep their best-ranked proposers and bump the rest; unranked mentors rank last.
2. **Greedy fill**: teams with the fewest mentors are topped up to 3 with the least-loaded mentors that still have capacity, regardless of preferences.

Missing preferences and underfilled teams produce warnings, not failures. Results replace `team_mentors` and stay hidden from teams and mentors until the admin confirms them. The algorithm core is a pure function so it can be unit tested without a database.

## Consequences

- **Easier**: matching is fair and repeatable; the admin can re-run it until happy; partial preference data still yields a complete assignment.
- **Harder**: greedy fill can assign a team mentors it never ranked, and a mentor can carry up to 3 teams on site. Phase 1 is not a textbook one-to-one stable matching, so stability guarantees are informal.
- **Technical debt**: each mentor covers at most 3 teams, so filling 18 teams to 3 needs at least 18 active mentors and the 2-mentor floor needs at least 12. Below that, some teams end up short with only a warning; nothing enforces the 2-mentor minimum. Greedy fill also tops each team all the way to 3 before moving to the next, so a shortage lands unevenly (some teams at 3, the last ones at 0 or 1) instead of spreading everyone at 2. Re-running after confirming silently un-confirms the published results.
