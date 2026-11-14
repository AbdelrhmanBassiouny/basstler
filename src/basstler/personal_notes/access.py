"""
Print how a Claude Code cloud session gets the personal-notes repository attached when
it is not the checkout's own and the session cannot reach it, and nothing otherwise.

Usage:
    "${BASSTLER_PYTHON}" -m basstler.personal_notes.access --retry <command>
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from cyclopts import App

from basstler.exit_codes import StackExitCode
from basstler.git.commands import GitCommandRunner
from basstler.github.client import GitHubAttemptClient, GitHubRestClient
from basstler.github.repository import Repository
from basstler.github.repository_attachment import RepositoryAttachment
from basstler.locations import ClaudeCodeVariable
from basstler.personal_notes.branch import PersonalNotesLocation
from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""

# %% the access


@dataclass(frozen=True)
class NotesRepositoryAccess:
    """
    Whether this session reaches :attr:`notes_repository`, and how to make it reach it.
    """

    notes_repository: Repository
    """
    The repository the personal-notes branch is fetched from and pushed to.
    """

    checkout_repository: Repository | None
    """
    The repository the session's checkout is a clone of, ``None`` when its ``origin``
    names none.
    """

    @classmethod
    def of_clone(
        cls, project_root: Path, environment: Mapping[str, str], origin: str = "origin"
    ) -> NotesRepositoryAccess | None:
        """
        :param project_root: The clone whose remotes to read.
        :param environment: The environment the notes settings are read from.
        :param origin: The remote whose repository is the checkout's own.
        :return: The clone's notes and checkout repositories, ``None`` when the notes
            remote names no repository.
        """
        git = GitCommandRunner(project_root)
        notes_remote = PersonalNotesLocation.resolve(project_root, environment).remote
        notes_url = git.configured_remote_url(notes_remote) or notes_remote
        if not Repository.names_a_repository(notes_url):
            return None
        origin_url = git.configured_remote_url(origin)
        checkout_repository = (
            Repository.from_remote_url(origin_url)
            if origin_url and Repository.names_a_repository(origin_url)
            else None
        )
        return cls(Repository.from_remote_url(notes_url), checkout_repository)

    def attachment(self, retry_command: str) -> RepositoryAttachment:
        """
        :param retry_command: The command that does what failed, once attached.
        :return: How the session gets :attr:`notes_repository` attached.
        """
        return RepositoryAttachment(
            self.notes_repository,
            retry_command=retry_command,
            benefit="this session then reads and saves the personal notes, plans and "
            "PR progress kept there",
        )

    def missing_access(
        self, client: GitHubAttemptClient, retry_command: str
    ) -> str | None:
        """
        :param client: Reads the notes repository.
        :param retry_command: The command that does what failed, once attached.
        :return: Why the session cannot reach the notes repository and how it gets it
            attached, ``None`` when it is the checkout's own or the session reaches it.
        """
        if self.notes_repository == self.checkout_repository:
            return None
        read = client.attempt_get(self.notes_repository.api_path)
        if read.failure is None:
            return None
        return (
            f"This session cannot reach the personal-notes repository "
            f"{self.notes_repository.full_name} yet ({read.failure.error_message()}). "
            f"{self.attachment(retry_command).instruction()}"
        )


# %% the command line

app = App(help=__doc__)
"""
The command, which takes the retry command.
"""


@app.default
def check_access(*, retry: str) -> StackExitCode:
    """
    Print how this cloud session gets the notes repository attached, when it has to.

    :param retry: The command that does what failed, once the repository is attached.
    :return: :attr:`StackExitCode.SUCCESS`, also when the access is missing: the line
        printed is the answer.
    """
    if not ClaudeCodeVariable.REMOTE.is_true():
        return StackExitCode.SUCCESS
    project_root = Path(
        os.environ.get(ClaudeCodeVariable.PROJECT_DIRECTORY, Path.cwd())
    )
    access = NotesRepositoryAccess.of_clone(project_root, os.environ)
    if access is None:
        return StackExitCode.SUCCESS
    missing = access.missing_access(GitHubRestClient(), retry)
    if missing is not None:
        logger.info(missing)
    return StackExitCode.SUCCESS


if __name__ == "__main__":
    app()
