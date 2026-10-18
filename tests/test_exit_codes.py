"""
Every error a command reports to its caller ends that command with a status of its own,
and every status is an :class:`~basstler.exit_codes.ExitCode`.

The errors are discovered by importing every module of the package, so a new one cannot
be left out of this check by not being listed here.
"""

from __future__ import annotations

import inspect

import pytest

from basstler.exit_codes import CommandFailure, ExitCode

from .command_failures import command_failure_kinds, command_failures


@pytest.mark.parametrize(
    "failure", command_failure_kinds(), ids=lambda failure: failure.__qualname__
)
def test_every_error_nothing_extends_can_be_raised(failure: type[CommandFailure]):
    """
    An error with no status of its own stays abstract, and raising it would fail with a
    ``TypeError`` instead of reporting what went wrong.

    Only a kind other errors extend may leave the status to them.
    """
    assert failure.__subclasses__() or not inspect.isabstract(failure)


@pytest.mark.parametrize(
    "failure", command_failures(), ids=lambda failure: failure.__qualname__
)
def test_every_command_failure_declares_its_status(failure: type[CommandFailure]):
    assert isinstance(failure.exit_code, ExitCode)


def test_no_status_is_a_failure():
    """
    Ending a command on an error with status 0 would tell its caller it succeeded.
    """
    assert all(failure.exit_code != 0 for failure in command_failures())
