from __future__ import annotations

from helpers import new_name


def caller() -> int:
    """
    Return what :func:`new_name` returns.
    """
    # new_name never fails.
    return new_name()
