"""
Prove the plan site's token by starting the site's build with it, then store it in every
repository the site publishes.

Usage:
    "${BASSTLER_PYTHON}" -m basstler.plan_site.token_storage

It asks for the token at a hidden terminal prompt and stores it with the user's ``gh``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from cyclopts import App

from basstler.github.client import GitHubAttemptClient, GitHubRestClient
from basstler.locations import ClaudeCodeVariable
from basstler.maintenance.constants import GitHubExecutable
from basstler.maintenance.git_commands import GitCommandRunner
from basstler.maintenance.remote_branch import RemoteBranch
from basstler.personal_notes.branch import PersonalNotesLocation
from basstler.plan_site.build_start import BuildStart
from basstler.plan_site.exceptions import (
    NotesRepositoryUnresolvedError,
    PlanSiteUnrecordedError,
)
from basstler.plan_site.hub import PlanHub
from basstler.plan_site.site_repository import SiteRepository
from basstler.plan_site.workflows import GitHubCommandLineOption, PlanSiteSecret
from basstler.repository import Repository
from basstler.setup.steps import resolve_repository
from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""

# %% storing the secret


class SecretStore(ABC):
    """
    Where a repository's Actions secrets are set.
    """

    @abstractmethod
    def store(self, repository: Repository, secret: PlanSiteSecret, value: str) -> str:
        """
        :param repository: The repository.
        :param secret: The secret's name.
        :param value: The secret's value.
        :return: Why it was refused, empty once stored.
        """


@dataclass(frozen=True)
class GitHubCommandLineSecretStore(SecretStore):
    """
    Sets secrets with ``gh secret set``, which encrypts each value with its repository's
    key.
    """

    executable: str = GitHubExecutable.COMMAND_LINE
    """
    The ``gh`` executable, as found on ``PATH``.
    """

    def store(self, repository: Repository, secret: PlanSiteSecret, value: str) -> str:
        if shutil.which(self.executable) is None:
            return f"{self.executable} is not installed"
        completed = subprocess.run(
            [
                self.executable,
                "secret",
                "set",
                secret,
                GitHubCommandLineOption.REPOSITORY,
                repository.full_name,
            ],
            input=value,
            capture_output=True,
            text=True,
        )
        if completed.returncode == 0:
            return ""
        return completed.stderr.strip() or f"exit status {completed.returncode}"


# %% one repository's result


@dataclass(frozen=True)
class StorageResult:
    """
    What storing the token in one repository came to.
    """

    repository: Repository
    """
    The repository.
    """

    refusal: str = ""
    """
    Why storing the token was refused, empty once it was stored.
    """

    def describe(self) -> str:
        """
        :return: One line saying what happened.
        """
        name = self.repository.full_name
        if self.refusal:
            return f"{name}: not stored - {self.refusal}"
        return f"{name}: stored"


# %% proving and storing


@dataclass(frozen=True)
class StorageReport:
    """
    What proving the token and storing it in every repository came to.
    """

    build_start: BuildStart
    """
    The build the token was proven by starting.
    """

    results: list[StorageResult] = field(default_factory=list)
    """
    The result in each repository, empty when the token was not stored anywhere.
    """

    @property
    def succeeded(self) -> bool:
        """:return: Whether the token started the build and every repository stores it."""
        return self.build_start.started and not any(
            result.refusal for result in self.results
        )

    def describe(self) -> list[str]:
        """
        :return: One line for the build, then one for each repository.
        """
        site = self.build_start.site
        if not self.build_start.started:
            return [
                f"{PlanSiteSecret.TOKEN} was stored nowhere: it could not start the plan "
                f"site build in {site.repository.full_name} "
                f"({self.build_start.response.failure.error_message()}). Create it again "
                f"at {site.token_form_url()} with access to "
                f"{site.repository.full_name} alone."
            ]
        return [
            f"The token started the plan site build in {site.repository.full_name}.",
            *(result.describe() for result in self.results),
        ]


@dataclass(frozen=True)
class TokenStorage:
    """
    Proves the plan site's token by starting the site's build with it, then stores it in
    repositories.
    """

    token: str = field(repr=False)
    """
    The token.
    """

    site: SiteRepository
    """
    The repository whose build the token starts.
    """

    secrets: SecretStore = field(default_factory=GitHubCommandLineSecretStore)
    """
    Where the token is stored.
    """

    def store(
        self, repositories: Sequence[Repository], client: GitHubAttemptClient
    ) -> StorageReport:
        """
        :param repositories: The repositories to store the token in.
        :param client: Sends GitHub requests authenticated with :attr:`token`.
        :return: The build started, and the result in each repository in the same
            order, none when the build did not start.
        """
        build_start = BuildStart.attempt(self.site, client)
        if not build_start.started:
            return StorageReport(build_start)
        return StorageReport(
            build_start,
            [
                StorageResult(
                    repository,
                    self.secrets.store(repository, PlanSiteSecret.TOKEN, self.token),
                )
                for repository in repositories
            ],
        )


# %% the command line


app = App(help=__doc__)
"""
The command, which takes no arguments.
"""


@app.default
def store_token() -> int:
    """
    Prove the token, store it in every repository the site publishes and print each
    result.

    :return: 0 once the token started the build and every repository stores it, else 1.
    :raises NotesRepositoryUnresolvedError: If the notes remote is not on GitHub.
    :raises PlanSiteUnrecordedError: If the notes branch records no plan site.
    """
    project_root = Path(
        os.environ.get(ClaudeCodeVariable.PROJECT_DIRECTORY, Path.cwd())
    )
    location = PersonalNotesLocation.resolve(project_root, os.environ)
    notes_repository = resolve_repository(project_root, location.remote)
    if notes_repository is None:
        raise NotesRepositoryUnresolvedError(location.remote)
    notes_branch = RemoteBranch(
        location.branch, GitCommandRunner(project_root), location.remote
    )
    site = SiteRepository.recorded_on(notes_branch)
    if site is None:
        raise PlanSiteUnrecordedError(location.branch)
    repositories = PlanHub.published_repositories(notes_branch, notes_repository)
    token = PlanSiteSecret.TOKEN.read_value()
    report = TokenStorage(token, site).store(
        repositories, GitHubRestClient(token=token)
    )
    for line in report.describe():
        logger.info(line)
    return 0 if report.succeeded else 1


if __name__ == "__main__":
    app()
