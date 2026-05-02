"""Utility functions and decorators"""

import re

# C7: Characters that can be weaponised for HTML/script injection in name fields.
# Allows apostrophes (O'Brien) and hyphens (hyphenated surnames) but blocks
# the minimal set needed to start any HTML tag, entity, or inline script.
_HTML_INJECTION_RE = re.compile(r"[<>&;\"\\]")


def contains_html(value: str) -> bool:
    """Return True if *value* contains characters used in HTML/XSS injection."""
    return bool(_HTML_INJECTION_RE.search(value))


def validate_name_field(value: str, field_label: str) -> tuple[bool, str]:
    """Validate a human-readable name field (first name, last name, team name, etc.).

    Returns (True, stripped_value) on success, or (False, error_message) on failure.
    """
    stripped = value.strip()
    if not stripped:
        return False, f"{field_label} is required"
    if contains_html(stripped):
        return False, f"{field_label} contains invalid characters"
    return True, stripped
