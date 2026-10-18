"""
The errors the package's commands report to their caller, found by importing every
module of the package, and the status each one ends a command with.
"""

from __future__ import annotations

import importlib
import inspect

from basstler.exit_codes import CommandFailure, ExitCode
from basstler.package_layout import package_modules


def command_failure_kinds() -> list[type[CommandFailure]]:
    """
    :return: Every :class:`CommandFailure` the package defines, abstract or not.
    """
    for module in package_modules():
        importlib.import_module(module.import_path)
    found: set[type[CommandFailure]] = set()
    pending = list(CommandFailure.__subclasses__())
    while pending:
        failure = pending.pop()
        pending.extend(failure.__subclasses__())
        found.add(failure)
    return sorted(found, key=lambda failure: failure.__qualname__)


def command_failures() -> list[type[CommandFailure]]:
    """
    :return: Every concrete :class:`CommandFailure` the package defines.
    """
    return [
        failure
        for failure in command_failure_kinds()
        if not inspect.isabstract(failure)
    ]


def status_of(failure: type[CommandFailure]) -> ExitCode:
    """
    :param failure: A concrete kind of error.
    :return: The status it ends a command with, read off an instance made without its
        constructor, since the status belongs to the kind rather than to any one raise.
    """
    return failure.__new__(failure).exit_code
