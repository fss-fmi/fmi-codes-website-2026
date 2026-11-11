"""Typed reads of a JSON request body, whose shape the client controls.

A body or field of the wrong type raises InvalidJsonFieldError, which the app answers with a
400 naming the field. Calling a str method on a number would be a 500 instead.
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


def string_field(data: dict, key: str, *, strip: bool = True) -> str:
    """The field's text, or "" when it is absent or null."""
    value = data.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise InvalidJsonFieldError(f"{key} must be a string")
    return value.strip() if strip else value


def is_row_id(value) -> bool:
    """A positive whole number that fits a Postgres `integer` column.

    bool is excluded although Python counts it as an int. A larger number would reach
    the database and fail there as a 500.
    """
    return isinstance(value, int) and not isinstance(value, bool) and 0 < value <= _MAX_INTEGER
