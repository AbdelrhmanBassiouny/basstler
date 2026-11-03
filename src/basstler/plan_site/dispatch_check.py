"""
Print check-setup.sh's plan site status and detail: whether every repository the plan
site publishes stores the token and starts the site's build from its notes branch.

Usage:
    "${BASSTLER_PYTHON}" -m basstler.plan_site.dispatch_check
"""

from __future__ import annotations

import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from http import HTTPStatus
from pathlib import Path
from typing import Any

from cyclopts import App

from basstler.environment import GitHubCredentialVariable
from basstler.github.client import GitHubAttemptReader, GitHubRestClient
from basstler.github.exceptions import (
    GitHubCallFailed,
    GitHubCredentialRejected,
    GitHubRequestFailed,
)
from basstler.locations import ClaudeCodeVariable, ProjectLocation
from basstler.maintenance.git_commands import GitCommandRunner
from basstler.maintenance.remote_branch import RemoteBranch
from basstler.personal_notes.branch import PersonalNotesLocation
from basstler.plan_site import publication
from basstler.plan_site.exceptions import NotesRepositoryUnresolvedError
from basstler.plan_site.hub import PlanHub
from basstler.plan_site.run_listing import ListedRun, RunListing
from basstler.plan_site.site_repository import SiteRepository
from basstler.plan_site.workflows import DispatchWorkflow, PlanSiteSecret
from basstler.repository import GitHubAddress, Repository
from basstler.setup.report import CheckResult, CheckStatus
from basstler.setup.steps import resolve_repository
from basstler.upstream_reviews.vocabulary import CheckOutcome, JSONModel

# %% a read GitHub refused


@dataclass(frozen=True)
class ReadRefusal:
    """
    A read of GitHub the check could not make, explained on one report line.
    """

    failure: GitHubCallFailed
    """
    Why the read failed.
    """

    def describe(self) -> str:
        """
        :return: The failure, and that a rejected token is not
            :attr:`PlanSiteSecret.TOKEN`, without line breaks.
        """
        parts = [self.failure.error_message()]
        if isinstance(self.failure, GitHubCredentialRejected):
            parts.append(
                f"it is this session's own credential, not the {PlanSiteSecret.TOKEN} "
                "secret"
            )
        parts.append(self.failure.suggest_correction())
        # A report row is one line, and GitHub's error bodies may span several.
        return " ".join("; ".join(part for part in parts if part).split())


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

    refusal: GitHubCallFailed | None = None
    """
    Why it could not be read, ``None`` unless :attr:`SecretState.UNREADABLE`.
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
        return cls(SecretState.UNREADABLE, refusal=answer.failure)

    def describe(self, repository: Repository) -> str:
        """
        :param repository: The repository it belongs to.
        :return: Whether the repository stores it, in a sentence that names both.
        """
        name = repository.full_name
        match self.state:
            case SecretState.STORED:
                return (
                    f"{name} stores {PlanSiteSecret.TOKEN}, set "
                    f"{self.updated_at:%Y-%m-%d}"
                )
            case SecretState.MISSING:
                return (
                    f"{name} stores no {PlanSiteSecret.TOKEN} secret, so its dispatch "
                    f"runs gh with an empty {GitHubCredentialVariable.GH_TOKEN}"
                )
            case SecretState.UNREADABLE:
                return (
                    f"whether {name} stores {PlanSiteSecret.TOKEN} could not be read: "
                    f"{ReadRefusal(self.refusal).describe()}"
                )


# %% one repository's dispatch


class FailureAfterSuccessCause(StrEnum):
    """
    What makes a dispatch that used to start the build fail, as its run log shows it.
    """

    TOKEN_EXPIRED = (
        f"{PlanSiteSecret.TOKEN} expired or was revoked - the log shows 'HTTP 401' or "
        f"'Bad credentials'; store a new token"
    )
    """
    The token no longer authenticates.
    """

    ACCESS_LOST = (
        f"{PlanSiteSecret.TOKEN} lost access to the site's repository - the log shows "
        "'HTTP 403' or 'HTTP 404'; give the token Actions write access to it again"
    )
    """
    The token authenticates, but may no longer start the site's workflow.
    """

    GITHUB_UNAVAILABLE = (
        "GitHub was unavailable - the log shows 'HTTP 500', 'HTTP 502' or 'HTTP "
        "503', or https://www.githubstatus.com lists an incident then; re-run the run"
    )
    """
    The run failed on GitHub's side, which re-running it fixes.
    """


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

    TOKEN_STORED_AFTER_FAILURE = "token stored after failure"
    """
    The latest run did not succeed, but the token was set after it started, so no run
    has used the token yet.
    """

    STOPPED_STARTING_BUILD = "stopped starting build"
    """
    The latest run did not succeed with the token as it is stored, but an earlier one
    did.
    """

    RUN_FAILED = "run failed"
    """
    No listed run succeeded with the token as it is stored.
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
        if self is DispatchState.TOKEN_STORED_AFTER_FAILURE:
            return CheckStatus.UNVERIFIED
        return CheckStatus.NEEDS_SETUP


@dataclass(frozen=True)
class DispatchReading(ABC):
    """
    What reading one published repository's dispatch from GitHub found.
    """

    repository: Repository
    """
    The repository the plan site publishes.
    """

    @property
    @abstractmethod
    def status(self) -> CheckStatus:
        """
        :return: The status this repository gives the plan site check.
        """

    @abstractmethod
    def describe(self) -> str:
        """
        :return: What was found, in a sentence that names the repository.
        """

    @classmethod
    def read(
        cls,
        runs: GitHubAttemptReader,
        secrets: GitHubAttemptReader,
        repository: Repository,
        notes_branch: str,
    ) -> DispatchReading:
        """
        :param runs: What reads the workflow runs.
        :param secrets: What reads the secret's metadata.
        :param repository: The repository.
        :param notes_branch: The branch its dispatch workflow runs on.
        :return: Its dispatch as GitHub reports it, or why its runs could not be read.
        """
        answer = runs.attempt_get(RunListing.path(repository, notes_branch))
        if answer.failure is not None:
            return UnreadableDispatch(repository, answer.failure)
        return RepositoryDispatch(
            repository,
            notes_branch,
            TokenSecret.read(secrets, repository),
            RunListing.from_json(answer.body).select(DispatchWorkflow.location),
        )


@dataclass(frozen=True)
class UnreadableDispatch(DispatchReading):
    """
    A repository whose dispatch runs GitHub would not list.
    """

    failure: GitHubCallFailed
    """
    Why the listing failed.
    """

    @property
    def status(self) -> CheckStatus:
        return CheckStatus.UNVERIFIED

    def describe(self) -> str:
        return (
            f"the dispatch runs of {self.repository.full_name} could not be read: "
            f"{ReadRefusal(self.failure).describe()} - read them at "
            f"{self.repository.url}/actions/workflows/{DispatchWorkflow.location.name}"
        )


@dataclass(frozen=True)
class RepositoryDispatch(DispatchReading):
    """
    One repository's token secret and its notes branch's dispatch runs.
    """

    notes_branch: str
    """
    The branch its dispatch workflow runs on.
    """

    token: TokenSecret
    """
    Its token secret.
    """

    runs: RunListing
    """
    Its latest dispatch runs, newest first.
    """

    @property
    def latest_run(self) -> ListedRun | None:
        """
        :return: Its latest dispatch run, ``None`` when it has none.
        """
        return self.runs.latest(DispatchWorkflow.location)

    @property
    def latest_success(self) -> ListedRun | None:
        """
        :return: Its latest dispatch run that succeeded, ``None`` when none listed did.
        """
        return self.runs.latest_success(DispatchWorkflow.location)

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
            return DispatchState.TOKEN_STORED_AFTER_FAILURE
        if self.latest_success is not None:
            return DispatchState.STOPPED_STARTING_BUILD
        return DispatchState.RUN_FAILED

    @property
    def status(self) -> CheckStatus:
        return self.state.status

    @property
    def run_history(self) -> str:
        """
        :return: How many of its listed dispatch runs failed, and its latest run.
        """
        if self.latest_run is None:
            return f"it has no dispatch run on '{self.notes_branch}'"
        return (
            f"{self.runs.count(CheckOutcome.FAILURE)} of its {len(self.runs.runs)} "
            f"latest dispatch runs failed, the latest is {self.latest_run.outcome} "
            f"({self.latest_run.url})"
        )

    def describe(self) -> str:
        name = self.repository.full_name
        match self.state:
            case DispatchState.TOKEN_MISSING:
                return (
                    f"{self.token.describe(self.repository)}; {self.run_history} - "
                    f"store the token with: gh secret set {PlanSiteSecret.TOKEN} "
                    f"--repo {name}"
                )
            case DispatchState.NEVER_RAN:
                return (
                    f"{name} has never run {DispatchWorkflow.location} on "
                    f"'{self.notes_branch}'; {self.token.describe(self.repository)}"
                )
            case DispatchState.TOKEN_STORED_AFTER_FAILURE:
                return (
                    f"{name}'s {PlanSiteSecret.TOKEN} was set after its latest "
                    f"dispatch run ({self.latest_run.url}), and takes effect at the "
                    f"next push to '{self.notes_branch}'; {self.run_history}"
                )
            case DispatchState.STOPPED_STARTING_BUILD:
                causes = "; or ".join(FailureAfterSuccessCause)
                return (
                    f"{name}'s latest dispatch run is {self.latest_run.outcome} "
                    f"({self.latest_run.url}), though {self.latest_success.url} "
                    f"succeeded on {self.latest_success.created_at:%Y-%m-%d}; "
                    f"{self.run_history}; {self.token.describe(self.repository)}. "
                    f"Open the failed run's log to see which happened: {causes}"
                )
            case DispatchState.RUN_FAILED:
                return (
                    f"{name}'s latest dispatch run is {self.latest_run.outcome} "
                    f"({self.latest_run.url}); {self.run_history}; "
                    f"{self.token.describe(self.repository)}"
                )
            case DispatchState.STARTS_BUILD:
                return f"{name} starts the plan site's build on every push"


# %% every repository the plan site publishes


UNVERIFIED_PREFIX = "not verified"
"""
What the detail of an unverified plan site check opens with.
"""


@dataclass(frozen=True)
class DispatchCheck:
    """
    Whether every repository the plan site publishes starts its build.
    """

    dispatches: list[DispatchReading]
    """
    What was read of each published repository's dispatch.
    """

    site: SiteRepository | None = None
    """
    The site repository the notes branch records, ``None`` when it records none.
    """

    @property
    def publication_command(self) -> str:
        """
        :return: The command that lists what is left, naming the recorded site.
        """
        command = f"{sys.executable} -m {publication.__name__}"
        if self.site is None:
            return command
        return (
            f"{command} {publication.PublicationOption.SITE_REPOSITORY} "
            f"{self.site.repository.full_name}"
        )

    def result(self) -> CheckResult:
        """
        :return: :attr:`CheckStatus.OK` only when every repository's latest dispatch
            run succeeded with its token stored; :attr:`CheckStatus.UNVERIFIED` when no
            run shows whether a repository starts its build and none needs setup.
        """
        statuses = {dispatch.status for dispatch in self.dispatches}
        if statuses <= {CheckStatus.OK}:
            return CheckResult(
                CheckStatus.OK,
                "every repository on the plan site starts its build on every push",
            )
        status = next(
            status
            for status in (
                CheckStatus.NEEDS_SETUP,
                CheckStatus.UNVERIFIED,
                CheckStatus.INFORMATIONAL,
            )
            if status in statuses
        )
        unfinished = "; ".join(
            dispatch.describe()
            for dispatch in self.dispatches
            if dispatch.status is not CheckStatus.OK
        )
        detail = f"{unfinished} - for what is left, run: {self.publication_command}"
        if status is CheckStatus.UNVERIFIED:
            detail = f"{UNVERIFIED_PREFIX} - {detail}"
        return CheckResult(status, detail)


# %% the command


def published_repositories(
    project_root: Path,
    location: PersonalNotesLocation,
    notes_repository: Repository,
    remote_root: str = GitHubAddress.WEB,
) -> list[Repository]:
    """
    :param project_root: The clone to read the notes branch from.
    :param location: Where its notes are kept.
    :param notes_repository: The repository its notes branch is on.
    :param remote_root: Where the registry is fetched from, as
        :meth:`Repository.clone_url_under` takes it.
    :return: The notes repository, then every other repository the registry's hub file
        lists.
    """
    # Only the registry's copy lists every repository; this one names the registry.
    own_copy = PlanHub.from_text(
        RemoteBranch(
            location.branch, GitCommandRunner(project_root), location.remote
        ).read_latest(ProjectLocation.PLAN_HUB)
    )
    if own_copy is None:
        return [notes_repository]
    hub = (
        PlanHub.from_registry(Repository.parse(own_copy.registry), remote_root)
        or own_copy
    )
    listed = [Repository.parse(name) for name in hub.repositories]
    return list(dict.fromkeys([notes_repository, *listed]))


app = App(help=__doc__)
"""
The command, which takes no arguments.
"""


@app.default
def report_dispatch() -> int:
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
            DispatchReading.read(client, client, repository, location.branch)
            for repository in published_repositories(
                project_root, location, notes_repository
            )
        ],
        SiteRepository.recorded_on(
            RemoteBranch(
                location.branch, GitCommandRunner(project_root), location.remote
            )
        ),
    )
    print(check.result().fields)
    return 0


if __name__ == "__main__":
    app()
