"""
Store the plan site's token in every repository the site publishes, then start each
one's dispatch workflow and report whether it started the site's build.

Usage:
    "${BASSTLER_PYTHON}" -m basstler.plan_site.token_storage

It asks for the token, or reads it from standard input when that is not a terminal.
Storing a secret needs the user's own ``gh`` login.
"""

from __future__ import annotations

import getpass
import os
import shutil
import subprocess
import sys
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from cyclopts import App

from basstler.github.client import GitHubClient, GitHubRestClient, HttpMethod
from basstler.locations import ClaudeCodeVariable, WorkflowLocation
from basstler.maintenance.constants import GitHubExecutable
from basstler.personal_notes.branch import PersonalNotesLocation
from basstler.plan_site.build_start import DispatchKey
from basstler.plan_site.exceptions import (
    NotesRepositoryUnresolvedError,
    PlanSiteTokenEmptyError,
)
from basstler.plan_site.hub import published_repositories
from basstler.plan_site.run_listing import ListedRun, RunListing
from basstler.plan_site.workflows import GitHubCommandLineOption, PlanSiteSecret
from basstler.repository import Repository
from basstler.setup.steps import resolve_repository
from basstler.upstream_reviews.vocabulary import CheckOutcome

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
    What storing the token in one repository, and proving it, came to.
    """

    repository: Repository
    """
    The repository.
    """

    refusal: str = ""
    """
    Why storing the token or starting the dispatch workflow was refused, empty when
    neither was.
    """

    run: ListedRun | None = None
    """
    The dispatch run that was started, ``None`` when none finished in time.
    """

    @property
    def proven(self) -> bool:
        """:return: Whether the dispatch run started the site's build."""
        return self.run is not None and self.run.outcome is CheckOutcome.SUCCESS

    def describe(self, wait: timedelta) -> str:
        """
        :param wait: How long the run was waited for.
        :return: One line saying what happened.
        """
        name = self.repository.full_name
        if self.refusal:
            return f"{name}: not done - {self.refusal}"
        if self.run is None:
            return (
                f"{name}: stored, but no dispatch run finished within {wait}; see "
                f"{self.repository.url}/actions"
            )
        if self.proven:
            return f"{name}: done - {self.run.url} started the plan site build"
        return (
            f"{name}: stored, but the dispatch run is {self.run.outcome} - its log "
            f"says why: {self.run.url}"
        )


# %% storing and proving


@dataclass(frozen=True)
class TokenStorage:
    """
    Stores the plan site's token in repositories and proves each copy by starting that
    repository's dispatch workflow.
    """

    notes_branch: str
    """
    The branch every repository's dispatch workflow runs on.
    """

    secrets: SecretStore
    """
    Where the token is stored.
    """

    github: GitHubClient
    """
    Starts the dispatch workflows and reads their runs.
    """

    wait: timedelta = timedelta(minutes=5)
    """
    How long to wait for each dispatch run to finish.
    """

    interval: timedelta = timedelta(seconds=5)
    """
    How long to wait between two reads of a repository's runs.
    """

    pause: Callable[[float], None] = field(default=time.sleep)
    """
    Waits the given number of seconds.
    """

    def store(
        self, repositories: Sequence[Repository], token: str
    ) -> list[StorageResult]:
        """
        :param repositories: The repositories to store the token in.
        :param token: The token.
        :return: The result in each repository, in the same order.
        """
        results = []
        for repository in repositories:
            refusal = self.secrets.store(repository, PlanSiteSecret.TOKEN, token)
            results.append(
                StorageResult(repository, refusal)
                if refusal
                else self.prove(repository)
            )
        return results

    def prove(self, repository: Repository) -> StorageResult:
        """
        Start the repository's dispatch workflow and wait for the run it started.

        :param repository: A repository storing the token.
        :return: The result, with the run once it finished.
        """
        workflow = WorkflowLocation.PLAN_SITE_DISPATCH
        earlier = {run.url for run in self.listing(repository).select(workflow).runs}
        dispatch = self.github.attempt_send(
            HttpMethod.POST,
            f"{repository.api_path}/actions/workflows/{workflow.name}/dispatches",
            {DispatchKey.REF: self.notes_branch},
        )
        if dispatch.failure is not None:
            return StorageResult(repository, dispatch.failure.error_message())
        for _ in range(int(self.wait / self.interval)):
            self.pause(self.interval.total_seconds())
            started = next(
                (
                    run
                    for run in self.listing(repository).select(workflow).runs
                    if run.url not in earlier
                ),
                None,
            )
            if started is not None and started.outcome is not CheckOutcome.PENDING:
                return StorageResult(repository, run=started)
        return StorageResult(repository)

    def listing(self, repository: Repository) -> RunListing:
        """
        :param repository: A repository.
        :return: Its latest runs on :attr:`notes_branch`.
        """
        return RunListing.read(self.github, repository, self.notes_branch)


# %% the command line


def read_token() -> str:
    """
    :return: The token, asked for without echo on a terminal, else read from standard
        input.
    :raises PlanSiteTokenEmptyError: If none was given.
    """
    token = (
        getpass.getpass(f"{PlanSiteSecret.TOKEN}: ")
        if sys.stdin.isatty()
        else sys.stdin.read()
    ).strip()
    if not token:
        raise PlanSiteTokenEmptyError(PlanSiteSecret.TOKEN)
    return token


app = App(help=__doc__)
"""
The command, which takes no arguments.
"""


@app.default
def store_token() -> int:
    """
    Store the token in every repository the site publishes and print each result.

    :return: 0 once every repository's dispatch run started the build, else 1.
    :raises NotesRepositoryUnresolvedError: If the notes remote is not on GitHub.
    """
    project_root = Path(
        os.environ.get(ClaudeCodeVariable.PROJECT_DIRECTORY, Path.cwd())
    )
    location = PersonalNotesLocation.resolve(project_root, os.environ)
    notes_repository = resolve_repository(project_root, location.remote)
    if notes_repository is None:
        raise NotesRepositoryUnresolvedError(location.remote)
    repositories = published_repositories(project_root, location, notes_repository)
    token = read_token()
    storage = TokenStorage(
        location.branch, GitHubCommandLineSecretStore(), GitHubRestClient()
    )
    results = storage.store(repositories, token)
    for result in results:
        print(result.describe(storage.wait))
    return 0 if all(result.proven for result in results) else 1


if __name__ == "__main__":
    app()
