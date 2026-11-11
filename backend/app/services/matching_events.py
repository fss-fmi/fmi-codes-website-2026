"""Event feed messages for the mentor-matching phase.

Preferences are private: a message says that a team or mentor submitted, never
what they chose. The builders therefore take only names, counts and the
matching run's warnings (which are counts too), never a ranking or a pair.
"""

from app.utils.slack import escape_mrkdwn


def _progress(noun: str, progress: tuple[int, int] | None) -> str:
    if progress is None:
        return ""
    submitted, total = progress
    return f" {noun}: {submitted} of {total} submitted."


def team_ranking_text(team_name: str, updated: bool, progress: tuple[int, int] | None) -> str:
    name = escape_mrkdwn(team_name)
    if updated:
        return f"🔁 Team *{name}* updated its mentor ranking."
    return f"🗳️ Team *{name}* submitted its mentor ranking.{_progress('Teams', progress)}"


def mentor_ranking_text(mentor_name: str, updated: bool, progress: tuple[int, int] | None) -> str:
    name = escape_mrkdwn(mentor_name)
    if updated:
        return f"🔁 Mentor *{name}* updated their team ranking."
    return f"🗳️ Mentor *{name}* submitted their team ranking.{_progress('Mentors', progress)}"


def matching_run_text(
    assignment_count: int, team_count: int, warnings: list[str], confirmation_cleared: bool
) -> str:
    lines = [
        "🧩 Mentor matching ran (Gale-Shapley, then greedy fill):"
        f" *{assignment_count}* assignments for *{team_count}* teams."
    ]
    lines += [f"• {escape_mrkdwn(w)}" for w in warnings]
    if confirmation_cleared:
        lines.append("The earlier confirmation was cleared.")
    return "\n".join(lines)


def matching_confirmed_text() -> str:
    return "✅ Matching confirmed as final. Teams and mentors now see their assignments."
