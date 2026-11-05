"""
Tests for :mod:`basstler.environment`: reading the environment variables this package
reads.
"""

from __future__ import annotations

import pytest

from basstler.environment import EnvironmentFlag
from basstler.locations import ClaudeCodeVariable

# %% reading a flag


def test_a_flag_set_to_true_reads_as_true(monkeypatch: pytest.MonkeyPatch):
    """
    A variable set to :attr:`EnvironmentFlag.TRUE` is true.
    """
    monkeypatch.setenv(ClaudeCodeVariable.REMOTE, EnvironmentFlag.TRUE)

    assert ClaudeCodeVariable.REMOTE.is_true()


def test_an_unset_flag_reads_as_false(monkeypatch: pytest.MonkeyPatch):
    """
    A variable that is not set is not true.
    """
    monkeypatch.delenv(ClaudeCodeVariable.REMOTE, raising=False)

    assert not ClaudeCodeVariable.REMOTE.is_true()
