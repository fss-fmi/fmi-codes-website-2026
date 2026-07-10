"""Regulations data management — cached in Redis to avoid file I/O on every request"""

import json
from pathlib import Path

from flask import current_app

from app.services.redis_client import jittered_ttl, redis_get, redis_set

_REGULATIONS_CACHE_KEY = "cache:regulations"


def get_regulations() -> list:
    """Get regulations from regulations.json.

    Cached in Redis for ~300s.
    """
    cached = redis_get(_REGULATIONS_CACHE_KEY)
    if cached is not None:
        try:
            return json.loads(cached)
        except (ValueError, TypeError):
            pass  # corrupt cache entry — fall through to reload

    result = _load_regulations()
    redis_set(_REGULATIONS_CACHE_KEY, json.dumps(result, default=str), jittered_ttl(300, 30))
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
