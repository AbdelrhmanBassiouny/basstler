"""
Tests for :mod:`basstler.command_line`.
"""

from __future__ import annotations

from dataclasses import dataclass


from basstler.command_line import Command

# %% the name a command is invoked by


@dataclass(frozen=True)
class ReadBackLogCommand(Command):
    """
    A command whose class name runs to several words.
    """


@dataclass(frozen=True)
class Refresh(Command):
    """
    A command whose class name does not end in the word every other one ends in.
    """


def test_a_command_is_invoked_by_its_class_name_in_hyphenated_lower_case_without_its_ending():
    assert ReadBackLogCommand.invoked_as == "read-back-log"


def test_a_class_name_without_the_command_ending_is_kept_whole():
    assert Refresh.invoked_as == "refresh"
