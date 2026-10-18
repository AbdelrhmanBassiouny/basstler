"""
Every error a command reports to its caller ends that command with a status of its own,
and every status is an :class:`~basstler.exit_codes.ExitCode`.

The errors are discovered by importing every module of the package, so a new one cannot
be left out of this check by not being listed here.
"""

from __future__ import annotations

import dataclasses
import inspect

import pytest

from basstler.exit_codes import CommandFailure, ExitCode

from .command_failures import command_failure_kinds, command_failures, status_of


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
    assert isinstance(status_of(failure), ExitCode)


@pytest.mark.parametrize(
    "failure", command_failures(), ids=lambda failure: failure.__qualname__
)
def test_the_status_is_not_a_constructor_argument(failure: type[CommandFailure]):
    """
    The status belongs to the kind of error, so no raise site can pick another.
    """
    status = CommandFailure.exit_code.fget.__name__

    assert status not in {field.name for field in dataclasses.fields(failure)}


def test_no_status_is_a_failure():
    """
    Ending a command on an error with status 0 would tell its caller it succeeded.
    """
    assert all(status_of(failure) != 0 for failure in command_failures())
