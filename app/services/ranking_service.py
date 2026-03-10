"""Ranking data management — cached in memory to avoid file I/O on every request"""

import json
import threading
import time
from pathlib import Path

from flask import current_app

_cache_lock = threading.Lock()
_cached_rankings = None
_cache_ts = 0
_CACHE_TTL = 60  # seconds


def get_rankings() -> list:
    """Get rankings from rankings.json sorted by points descending.

    Results are cached in memory for up to 60 seconds so 500 concurrent
    requests don't each open + parse the file independently.
    """
    global _cached_rankings, _cache_ts

    now = time.monotonic()
    if _cached_rankings is not None and (now - _cache_ts) < _CACHE_TTL:
        return _cached_rankings

    with _cache_lock:
        # Double-check inside the lock
        if _cached_rankings is not None and (time.monotonic() - _cache_ts) < _CACHE_TTL:
            return _cached_rankings

        result = _load_rankings()
        _cached_rankings = result
        _cache_ts = time.monotonic()
        return result


def _load_rankings() -> list:
    try:
        possible_paths = [
            Path(current_app.root_path).parent / "rankings.json",
            Path(current_app.root_path).parent / "database" / "seeds" / "rankings.json",
        ]

        path = None
        for p in possible_paths:
            if p.exists():
                path = p
                break

        if not path:
            return []

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            data = []

        normalized = []
        for item in data:
            team = str(item.get("team", "")).strip()
            pts = item.get("points", 0)
            img = item.get("image")
            if team:
                try:
                    pts = int(pts)
                except Exception:
                    pts = 0
                normalized.append({"team": team, "points": pts, "image": img})

        normalized.sort(key=lambda x: x["points"], reverse=True)
        return normalized

    except Exception as e:
        raise Exception(f"Failed to load rankings: {str(e)}") from e
