"""
Running git with ``gh``'s login lent to it for GitHub.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from basstler.class_property import classproperty
from basstler.git.commands import (
    GitCommandResult,
    GitCommandRunner,
    TransientGitSetting,
)
from basstler.github.repository import GitHubAddress

# %% the runner


@dataclass(frozen=True)
class GitHubLoginLendingRunner(GitCommandRunner):
    """
    Runs git in one checkout, answering its request for a GitHub credential over HTTPS
    with ``gh``'s login, without changing any git configuration.
    """

    @classproperty
    def credential_helper(cls) -> str:
        """
        The credential helper that answers with ``gh``'s login.
        """
        return "!gh auth git-credential"

    def attempt(
        self, *arguments: str, environment: Mapping[str, str] | None = None
    ) -> GitCommandResult:
        """
        :meth:`GitCommandRunner.attempt`, with :attr:`credential_helper` consulted for
        GitHub after every helper git is already configured with.
        """
        lent = TransientGitSetting(
            f"credential.{GitHubAddress.WEB}.helper", self.credential_helper
        ).variables(os.environ)
        return super().attempt(*arguments, environment={**lent, **(environment or {})})
