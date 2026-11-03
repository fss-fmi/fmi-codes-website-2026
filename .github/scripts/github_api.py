"""Minimal GitHub REST client for the notification workflows (stdlib only)."""

import json
import logging
import urllib.parse
import urllib.request

logger = logging.getLogger("github_api")

API = "https://api.github.com"
PUSH_PERMISSIONS = {"admin", "write"}


def can_push(get, repo: str, user: dict, head_repo: str | None) -> bool:
    """Whether *user* may push to *repo*. Only their PRs, reviews and runs reach Slack.

    The repo is public and pull_request_target needs no approval, so without this
    anyone on GitHub could make the bot post text of their choosing. Always asks
    the permission API: author_association can't be used, because MEMBER and
    COLLABORATOR include read-only access. Any failure counts as untrusted.
    """
    if user.get("type") == "Bot":
        # This repo's own apps (Flux bumps, migration PRs) open PRs from its branches.
        return head_repo == repo
    if get is None:
        return False
    login = urllib.parse.quote(user["login"], safe="")
    try:
        permission = get(f"/repos/{repo}/collaborators/{login}/permission").get("permission")
    except Exception as e:
        logger.warning("Could not check %s's permission, treating as untrusted: %s", login, e)
        return False
    return permission in PUSH_PERMISSIONS


class _SameHostAuthRedirect(urllib.request.HTTPRedirectHandler):
    """Follow redirects, carrying the token only while they stay on the same host.

    API redirects (a renamed or transferred repo) stay on api.github.com and need
    it; job logs redirect to blob storage, which must never receive it.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        auth = req.unredirected_hdrs.get("Authorization")
        same_host = (
            urllib.parse.urlsplit(newurl).hostname == urllib.parse.urlsplit(req.full_url).hostname
        )
        if new is not None and auth and same_host:
            new.add_unredirected_header("Authorization", auth)
        return new


class GitHub:
    def __init__(self, token: str, opener=None):
        self._token = token
        self._open = opener or urllib.request.build_opener(_SameHostAuthRedirect).open

    def _request(self, path: str, params: dict) -> urllib.request.Request:
        query = f"?{urllib.parse.urlencode(params)}" if params else ""
        req = urllib.request.Request(f"{API}{path}{query}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        req.add_unredirected_header("Authorization", f"Bearer {self._token}")
        return req

    def get(self, path: str, **params):
        with self._open(self._request(path, params), timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def text(self, path: str, **params) -> str:
        with self._open(self._request(path, params), timeout=30) as resp:
            return resp.read().decode("utf-8", errors="replace")
