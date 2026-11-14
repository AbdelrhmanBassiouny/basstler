"""
Returns a command line that runs bash by its name.
"""

from __future__ import annotations


def command(script: str) -> tuple[str, ...]:
    """
    :return: bash, running *script*.
    """
    return ("bash", script)
