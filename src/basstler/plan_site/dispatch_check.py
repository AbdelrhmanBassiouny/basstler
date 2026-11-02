"""
Print check-setup.sh's plan site status and detail: whether every repository the plan
site publishes stores the token and starts the site's build from its notes branch.

Usage:
    "${BASSTLER_PYTHON}" -m basstler.plan_site.dispatch_check
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from http import HTTPStatus
from pathlib import Path
from typing import Any

from basstler.github.client import (
    GitHubAttemptReader,
    GitHubReader,
    GitHubRestClient,
)
from basstler.github.exceptions import GitHubRequestFailed
from basstler.locations import ClaudeCodeVariable, ProjectLocation
from basstler.maintenance.git_commands import GitCommandRunner
from basstler.maintenance.remote_branch import RemoteBranch
from basstler.personal_notes.branch import PersonalNotesLocation
from basstler.plan_site import publication
from basstler.plan_site.exceptions import NotesRepositoryUnresolvedError
from basstler.plan_site.hub import PlanHub
from basstler.plan_site.run_listing import ListedRun, RunListing
from basstler.plan_site.workflows import DispatchWorkflow, PlanSiteSecret
from basstler.repository import Repository
from basstler.setup.report import CheckResult, CheckStatus
from basstler.setup.steps import resolve_repository
from basstler.upstream_reviews.vocabulary import CheckOutcome, JSONModel

# %% the token each repository stores


class SecretKey(StrEnum):
    """
    Every field read out of a repository secret's REST response.
    """

    UPDATED_AT = "updated_at"
    """
    When the secret's value was last set.
    """


class SecretState(StrEnum):
    """
    What GitHub says about the token secret in one repository.
    """

    STORED = "stored"
    """
    The repository stores it.
    """

    MISSING = "missing"
    """
    The repository does not store it.
    """

    UNREADABLE = "unreadable"
    """
    GitHub did not say, as when the credential may not read secrets.
    """


@dataclass(frozen=True)
class TokenSecret(JSONModel):
    """
    The token secret as one repository stores it, or what keeps it from being known.
    """

    state: SecretState
    """
    Whether it is stored.
    """

    updated_at: datetime | None = None
    """
    When its value was last set, ``None`` unless :attr:`SecretState.STORED`.
    """

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> TokenSecret:
        """
        :param data: A repository secret's REST response.
        :return: The stored secret.
        """
        return cls(
            SecretState.STORED, datetime.fromisoformat(data[SecretKey.UPDATED_AT])
        )

    @staticmethod
    def path(repository: Repository) -> str:
        """
        :param repository: The repository.
        :return: The REST path of its token secret.
        """
        return f"{repository.api_path}/actions/secrets/{PlanSiteSecret.TOKEN}"

    @classmethod
    def read(cls, client: GitHubAttemptReader, repository: Repository) -> TokenSecret:
        """
        :param client: What reads the secret's metadata, never its value.
        :param repository: The repository.
        :return: The secret as GitHub reports it.
        """
        answer = client.attempt_get(cls.path(repository))
        if answer.failure is None:
            return cls.from_json(answer.body)
        if (
            isinstance(answer.failure, GitHubRequestFailed)
            and answer.failure.status == HTTPStatus.NOT_FOUND
        ):
            return cls(SecretState.MISSING)
        return cls(SecretState.UNREADABLE)


# %% one repository's dispatch


class DispatchState(StrEnum):
    """
    Where one repository's start of the plan site's build stands.
    """

    TOKEN_MISSING = "token missing"
    """
    The repository stores no token, so its dispatch cannot start the build.
    """

    NEVER_RAN = "never ran"
    """
    The dispatch has not run on the notes branch.
    """

    TOKEN_STORED_SINCE_FAILURE = "token stored since failure"
    """
    The latest run did not succeed, but the token was set after it started.
    """

    RUN_FAILED = "run failed"
    """
    The latest run did not succeed with the token as it is stored.
    """

    STARTS_BUILD = "starts build"
    """
    The latest run succeeded.
    """

    @property
    def status(self) -> CheckStatus:
        """
        :return: The status a repository in this state gives the plan site check.
        """
        if self is DispatchState.STARTS_BUILD:
            return CheckStatus.OK
        if self is DispatchState.TOKEN_STORED_SINCE_FAILURE:
            return CheckStatus.INFORMATIONAL
        return CheckStatus.NEEDS_SETUP


@dataclass(frozen=True)
class RepositoryDispatch:
    """
    One repository's token secret and its notes branch's latest dispatch run.
    """

    repository: Repository
    """
    The repository the plan site publishes.
    """

    notes_branch: str
    """
    The branch its dispatch workflow runs on.
    """

    token: TokenSecret
    """
    Its token secret.
    """

    latest_run: ListedRun | None
    """
    Its latest dispatch run, ``None`` when it has none.
    """

    @classmethod
    def read(
        cls,
        runs: GitHubReader,
        secrets: GitHubAttemptReader,
        repository: Repository,
        notes_branch: str,
    ) -> RepositoryDispatch:
        """
        :param runs: What reads the workflow runs.
        :param secrets: What reads the secret's metadata.
        :param repository: The repository.
        :param notes_branch: The branch its dispatch workflow runs on.
        :return: Its dispatch as GitHub reports it.
        """
        return cls(
            repository,
            notes_branch,
            TokenSecret.read(secrets, repository),
            RunListing.read(runs, repository, notes_branch).latest(
                DispatchWorkflow.location
            ),
        )

    @property
    def state(self) -> DispatchState:
        """
        :return: Where its start of the build stands.
        """
        if self.token.state is SecretState.MISSING:
            return DispatchState.TOKEN_MISSING
        if self.latest_run is None:
            return DispatchState.NEVER_RAN
        if self.latest_run.outcome is CheckOutcome.SUCCESS:
            return DispatchState.STARTS_BUILD
        if (
            self.token.updated_at is not None
            and self.token.updated_at > self.latest_run.created_at
        ):
            return DispatchState.TOKEN_STORED_SINCE_FAILURE
        return DispatchState.RUN_FAILED

    def describe(self) -> str:
        """
        :return: Its state in a sentence that names the repository.
        """
        name = self.repository.full_name
        match self.state:
            case DispatchState.TOKEN_MISSING:
                return f"{name} stores no {PlanSiteSecret.TOKEN} secret"
            case DispatchState.NEVER_RAN:
                return (
                    f"{name} has never run {DispatchWorkflow.location} on "
                    f"'{self.notes_branch}'"
                )
            case DispatchState.TOKEN_STORED_SINCE_FAILURE:
                return (
                    f"{name}'s {PlanSiteSecret.TOKEN} was set after its latest "
                    f"dispatch run ({self.latest_run.url}), and takes effect at the "
                    f"next push to '{self.notes_branch}'"
                )
            case DispatchState.RUN_FAILED:
                return (
                    f"{name}'s latest dispatch run is {self.latest_run.outcome} "
                    f"({self.latest_run.url})"
                )
            case DispatchState.STARTS_BUILD:
                return f"{name} starts the plan site's build on every push"


# %% every repository the plan site publishes


@dataclass(frozen=True)
class DispatchCheck:
    """
    Whether every repository the plan site publishes starts its build.
    """

    dispatches: list[RepositoryDispatch]
    """
    Each published repository's dispatch.
    """

    def result(self) -> CheckResult:
        """
        :return: :attr:`CheckStatus.OK` only when every repository's latest dispatch
            run succeeded with its token stored.
        """
        states = [dispatch.state for dispatch in self.dispatches]
        if all(state is DispatchState.STARTS_BUILD for state in states):
            return CheckResult(
                CheckStatus.OK,
                "every repository on the plan site starts its build on every push",
            )
        status = (
            CheckStatus.NEEDS_SETUP
            if any(state.status is CheckStatus.NEEDS_SETUP for state in states)
            else CheckStatus.INFORMATIONAL
        )
        unfinished = "; ".join(
            dispatch.describe()
            for dispatch in self.dispatches
            if dispatch.state is not DispatchState.STARTS_BUILD
        )
        return CheckResult(
            status,
            f"{unfinished} - for what is left, run: "
            f"{sys.executable} -m {publication.__name__}",
        )


# %% the command


def published_repositories(
    project_root: Path, location: PersonalNotesLocation, notes_repository: Repository
) -> list[Repository]:
    """
    :param project_root: The clone to read the notes branch from.
    :param location: Where its notes are kept.
    :param notes_repository: The repository its notes branch is on.
    :return: The notes repository, then every other repository the registry's hub file
        lists.
    """
    local_hub = PlanHub.from_text(
        RemoteBranch(
            location.branch, GitCommandRunner(project_root), location.remote
        ).read_latest(ProjectLocation.PLAN_HUB)
    )
    if local_hub is None:
        return [notes_repository]
    registry = Repository.parse(local_hub.registry)
    hub = local_hub if registry == notes_repository else PlanHub.from_registry(registry)
    listed = [Repository.parse(name) for name in (hub or local_hub).repositories]
    return list(dict.fromkeys([notes_repository, *listed]))


def main() -> int:
    """
    Print this clone's dispatch check. See the module docstring.

    :return: 0 once printed.
    :raises NotesRepositoryUnresolvedError: If the notes remote is not on GitHub.
    """
    project_root = Path(
        os.environ.get(ClaudeCodeVariable.PROJECT_DIRECTORY, Path.cwd())
    )
    location = PersonalNotesLocation.resolve(project_root, os.environ)
    notes_repository = resolve_repository(project_root, location.remote)
    if notes_repository is None:
        raise NotesRepositoryUnresolvedError(location.remote)
    client = GitHubRestClient()
    check = DispatchCheck(
        [
            RepositoryDispatch.read(client, client, repository, location.branch)
            for repository in published_repositories(
                project_root, location, notes_repository
            )
        ]
    )
    print(check.result().fields)
    return 0


if __name__ == "__main__":
    sys.exit(main())
