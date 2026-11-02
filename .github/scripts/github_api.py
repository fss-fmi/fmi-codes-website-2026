"""Minimal GitHub REST client for the notification workflows (stdlib only)."""

import json
import urllib.parse
import urllib.request

API = "https://api.github.com"


class GitHub:
    def __init__(self, token: str, opener=urllib.request.urlopen):
        self._token = token
        self._open = opener

    def _request(self, path: str, params: dict) -> urllib.request.Request:
        query = f"?{urllib.parse.urlencode(params)}" if params else ""
        req = urllib.request.Request(f"{API}{path}{query}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        # Unredirected: job logs redirect to blob storage, which must not receive the token.
        req.add_unredirected_header("Authorization", f"Bearer {self._token}")
        return req

    def get(self, path: str, **params):
        with self._open(self._request(path, params), timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def text(self, path: str, **params) -> str:
        with self._open(self._request(path, params), timeout=30) as resp:
            return resp.read().decode("utf-8", errors="replace")
