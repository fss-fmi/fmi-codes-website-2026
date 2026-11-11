"""Slack mrkdwn helpers."""


def escape_mrkdwn(text: str) -> str:
    """Escape the three characters Slack reads as markup, so user text can't
    become a link or a mention such as <!channel>."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
