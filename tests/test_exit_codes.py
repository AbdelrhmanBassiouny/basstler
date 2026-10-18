"""
Every error a command reports to its caller ends that command with a status of its own,
and every status is an :class:`~basstler.exit_codes.ExitCode`.

The errors are discovered by importing every module of the package, so a new one cannot
be left out of this check by not being listed here.
"""

from __future__ import annotations

import dataclasses
import importlib
import inspect

import pytest

from basstler.exit_codes import CommandFailure, ExitCode
from basstler.package_layout import package_modules


def command_failures() -> list[type[CommandFailure]]:
    """
    :return: Every concrete :class:`CommandFailure` the package defines.
    """
    for module in package_modules():
        importlib.import_module(module.import_path)
    found: list[type[CommandFailure]] = []
    pending = list(CommandFailure.__subclasses__())
    while pending:
        failure = pending.pop()
        pending.extend(failure.__subclasses__())
        if not inspect.isabstract(failure):
            found.append(failure)
    return sorted(set(found), key=lambda failure: failure.__qualname__)


@pytest.mark.parametrize(
    "failure", command_failures(), ids=lambda failure: failure.__qualname__
)
def test_every_command_failure_declares_its_status(failure: type[CommandFailure]):
    assert isinstance(failure.exit_code, ExitCode)


@pytest.mark.parametrize(
    "failure", command_failures(), ids=lambda failure: failure.__qualname__
)
def test_the_status_is_not_a_constructor_argument(failure: type[CommandFailure]):
    """
    The status belongs to the kind of error, so no raise site can pick another.
    """
    exit_code = next(
        field for field in dataclasses.fields(failure) if field.name == "exit_code"
    )

    assert not exit_code.init


def test_no_status_is_a_failure():
    """
    Ending a command on an error with status 0 would tell its caller it succeeded.
    """
    assert all(failure.exit_code != 0 for failure in command_failures())
