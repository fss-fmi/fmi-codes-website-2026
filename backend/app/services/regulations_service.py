"""Regulations data management — cached in memory to avoid file I/O on every request"""

import json
import threading
import time
from pathlib import Path

from flask import current_app

_cache_lock = threading.Lock()
_cached_regulations = None
_cache_ts = 0
_CACHE_TTL = 60  # seconds


def get_regulations() -> list:
    """Get regulations from regulations.json.

    Cached in memory for up to 60 seconds.
    """
    global _cached_regulations, _cache_ts

    now = time.monotonic()
    if _cached_regulations is not None and (now - _cache_ts) < _CACHE_TTL:
        return _cached_regulations

    with _cache_lock:
        if _cached_regulations is not None and (time.monotonic() - _cache_ts) < _CACHE_TTL:
            return _cached_regulations

        result = _load_regulations()
        _cached_regulations = result
        _cache_ts = time.monotonic()
        return result


def _load_regulations() -> list:
    try:
        possible_paths = [
            # __file__-relative path is always correct regardless of CWD or root_path
            Path(__file__).resolve().parent.parent.parent / "database" / "seeds" / "regulations.json",
            Path(current_app.root_path).parent / "database" / "seeds" / "regulations.json",
            Path(current_app.root_path).parent / "regulations.json",
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
            q = str(item.get("question", "")).strip()
            a = str(item.get("answer", "")).strip()
            if q or a:
                normalized.append({"question": q, "answer": a})

        return normalized

    except Exception as e:
        raise Exception(f"Failed to load regulations: {str(e)}") from e
