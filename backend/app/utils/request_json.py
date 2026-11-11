"""Typed reads of a JSON request body, whose shape the client controls.

A body or field of the wrong type raises InvalidJsonFieldError, which the app answers with a
400 naming the field. Calling a str method on a number, or sending text Postgres or UTF-8
can't take, would be a 500 instead.
"""

from flask import request

_MAX_INTEGER = 2**31 - 1


class InvalidJsonFieldError(Exception):
    """Its message is the 400's `error`, which the SPA shows."""


def json_object() -> dict:
    """The body's JSON object, or {} when the body is missing or not JSON."""
    data = request.get_json(silent=True)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise InvalidJsonFieldError("Request body must be a JSON object")
    return data


def is_valid_text(value: str) -> bool:
    """False for a NUL, which Postgres can't store, or a lone surrogate such as "\\ud800",
    which JSON allows but UTF-8 can't encode."""
    if "\x00" in value:
        return False
    try:
        value.encode()
    except UnicodeEncodeError:
        return False
    return True


def string_field(
    data: dict,
    key: str,
    *,
    strip: bool = True,
    max_length: int | None = None,
    label: str | None = None,
) -> str:
    """The field's text, or "" when it is absent or null.

    `max_length` is the column's size; a longer value would fail in Postgres. Errors name
    the field as `label`, which defaults to `key`.
    """
    name = label or key
    value = data.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise InvalidJsonFieldError(f"{name} must be a string")
    if not is_valid_text(value):
        raise InvalidJsonFieldError(f"{name} contains an invalid character")
    if strip:
        value = value.strip()
    if max_length is not None and len(value) > max_length:
        raise InvalidJsonFieldError(f"{name} must be at most {max_length} characters")
    return value


def is_row_id(value) -> bool:
    """A positive whole number that fits a Postgres `integer` column.

    bool is excluded although Python counts it as an int. A larger number would reach
    the database and fail there as a 500.
    """
    return isinstance(value, int) and not isinstance(value, bool) and 0 < value <= _MAX_INTEGER
