"""
Tests for lending git ``gh``'s login for GitHub, so a push over HTTPS needs no setup.
"""

from __future__ import annotations

import pytest

from basstler.environment import GitVariable
from basstler.git.commands import GitHubLoginLendingRunner
from basstler.github.repository import GitHubAddress

from ..scratch_repository import ScratchRepository

# %% the credential helper git sees


def test_git_asks_gh_for_a_github_credential(scratch_repository: ScratchRepository):
    """
    A GitHub URL is answered by ``gh``'s login, without any global git configuration.
    """
    runner = GitHubLoginLendingRunner(scratch_repository.project_root)

    helpers = runner.run(
        "config", "--get-urlmatch", "credential.helper", f"{GitHubAddress.WEB}/o/n.git"
    )

    assert helpers.splitlines()[-1] == runner.credential_helper


def test_git_asks_gh_only_for_github(scratch_repository: ScratchRepository):
    """
    ``gh``'s login is never offered to another host.
    """
    runner = GitHubLoginLendingRunner(scratch_repository.project_root)

    helpers = runner.attempt(
        "config", "--get-urlmatch", "credential.helper", "https://example.com/o/n.git"
    )

    assert runner.credential_helper not in helpers.output.splitlines()


@pytest.mark.parametrize("configured_before", [0, 2])
def test_lending_keeps_configuration_the_caller_set(
    scratch_repository: ScratchRepository,
    monkeypatch: pytest.MonkeyPatch,
    configured_before: int,
):
    """
    Configuration already passed to git through its environment stays in force.
    """
    monkeypatch.setenv(GitVariable.CONFIGURATION_COUNT, str(configured_before))
    for index in range(configured_before):
        monkeypatch.setenv(
            f"{GitVariable.CONFIGURATION_KEY_PREFIX}{index}", f"basstler.test{index}"
        )
        monkeypatch.setenv(
            f"{GitVariable.CONFIGURATION_VALUE_PREFIX}{index}", str(index)
        )
    runner = GitHubLoginLendingRunner(scratch_repository.project_root)

    kept = [
        runner.run("config", f"basstler.test{index}")
        for index in range(configured_before)
    ]

    assert kept == [str(index) for index in range(configured_before)]
