# ADR-005: Many-to-many Gale-Shapley plus greedy fill for mentor matching

**Status**: accepted. Phase 2 was later changed from topping each team up to 3 in turn to an even fill plus a rebalance, so a mentor shortage spreads across teams instead of leaving some at 0: with at least 12 active mentors for 18 teams, every team gets 2 or 3.

## Context

Mentor assignment used to be done by hand, which was slow and open to favouritism. Both sides have preferences: each captain ranks 3 mentors and each mentor ranks 3 teams. The organizers' requirement is that every registered team ends up with **2 or 3 mentors, never more than 3**. With about 20 mentors and 18 teams there are not enough mentors to give each team 2 or 3 exclusive mentors, so mentors must be able to cover more than one team. Not everyone submits preferences on time.

## Decision

`backend/app/services/matching_service.py` runs two phases:

1. **Mentor-proposing Gale-Shapley, many-to-many**, with `TEAM_CAPACITY = 3` and `MENTOR_CAPACITY = 3`. Teams keep their best-ranked proposers and bump the rest; unranked mentors rank last.
2. **Greedy fill**: mentors with spare capacity go out one at a time, each to the team with the fewest mentors and least-loaded mentors first, regardless of preferences. Then, while a team has fewer than 2 and another has 3, the full team gives the short one the mentor it wants least, and the fill runs again.

Missing preferences and underfilled teams produce warnings, not failures. Results replace `team_mentors` and stay hidden from teams and mentors until the admin confirms them. The algorithm core is a pure function so it can be unit tested without a database.

## Consequences

- **Easier**: matching is fair and repeatable; the admin can re-run it until happy; partial preference data still yields a complete assignment.
- **Harder**: greedy fill can assign a team mentors it never ranked, and a mentor can carry up to 3 teams on site. Phase 1 is not a textbook one-to-one stable matching, so stability guarantees are informal.
- **Technical debt**: each mentor covers at most 3 teams, so filling 18 teams to 3 needs at least 18 active mentors and the 2-mentor floor needs at least 12. Below 12 the floor can't be met and the teams under 2 get only a warning. Re-running after confirming un-confirms the published results; Mission Control's run and confirm dialogs warn about it.
