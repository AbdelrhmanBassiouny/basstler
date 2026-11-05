"""
Start the plan site's build with this session's own GitHub credential, after a push to
the notes branch, and print whether it started.

Usage:
    "${BASSTLER_PYTHON}" -m basstler.plan_site.build_start
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from cyclopts import App

from basstler.github.client import (
    GitHubAttemptReader,
    GitHubResponse,
    GitHubRestClient,
    GitHubWriter,
    HttpMethod,
)
from basstler.locations import ClaudeCodeVariable, WorkflowLocation
from basstler.maintenance.git_commands import GitCommandRunner
from basstler.maintenance.remote_branch import RemoteBranch
from basstler.personal_notes.branch import PersonalNotesLocation
from basstler.plan_site.site_repository import SiteRepository
from basstler.plan_site.workflows import PlanSiteSecret

# %% the outcome


class SessionTool(StrEnum):
    """
    The Claude Code tools a session is told to call when the build did not start.
    """

    ATTACH_REPOSITORY = "mcp__claude-code-remote__add_repo"
    """
    Attaches a repository to a cloud session, which lets its proxy answer that
    repository's API.
    """

    ASK_USER = "AskUserQuestion"
    """
    Asks the user to choose between options.
    """


class RepositoryKey(StrEnum):
    """
    The keys read from a repository's REST resource.
    """

    DEFAULT_BRANCH = "default_branch"


class DispatchKey(StrEnum):
    """
    The keys of a workflow dispatch's body.
    """

    REF = "ref"
    """
    The branch the workflow runs on.
    """


@dataclass(frozen=True)
class BuildStart:
    """
    The attempt to start :attr:`site`'s build workflow.
    """

    site: SiteRepository
    """
    The repository whose build is started.
    """

    response: GitHubResponse
    """
    GitHub's answer: to reading the site repository if that was refused, else to the
    dispatch.
    """

    @classmethod
    def attempt(
        cls, site: SiteRepository, reader: GitHubAttemptReader, writer: GitHubWriter
    ) -> BuildStart:
        """
        :param site: The site repository.
        :param reader: Reads the site repository's default branch.
        :param writer: Sends the dispatch.
        :return: The attempt, which never raises for a refusal or a call with no answer.
        """
        repository = site.repository
        read = reader.attempt_get(repository.api_path)
        if read.failure is not None:
            return cls(site, read)
        dispatch = writer.attempt_send(
            HttpMethod.POST,
            f"{repository.api_path}/actions/workflows/"
            f"{WorkflowLocation.PLAN_SITE.name}/dispatches",
            {DispatchKey.REF: read.body[RepositoryKey.DEFAULT_BRANCH]},
        )
        return cls(site, dispatch)

    @property
    def started(self) -> bool:
        """:return: Whether GitHub accepted the dispatch."""
        return self.response.failure is None

    def describe(self, in_cloud_session: bool) -> str:
        """
        :param in_cloud_session: Whether this runs in a Claude Code cloud session.
        :return: What happened, and when the build did not start, how this session
            gets it to start next time.
        """
        repository = self.site.repository
        if self.started:
            return f"Started the plan site build in {repository.full_name}."
        fallback = (
            f"The notes branch's dispatch workflow still starts it if "
            f"{PlanSiteSecret.TOKEN} is stored."
        )
        refused = (
            f"Could not start the plan site build in {repository.full_name}: "
            f"{self.response.failure.error_message()}. {fallback}"
        )
        if not in_cloud_session:
            return f"{refused} Log gh in with access to {repository.full_name}."
        return (
            f"{refused} Attach the site repository to this session: call "
            f"{SessionTool.ATTACH_REPOSITORY} with owner {repository.owner}, repo "
            f"{repository.name} and access push, then run this command again. If the "
            f"attach is refused, ask the user with {SessionTool.ASK_USER} to allow it, with "
            '"Attach it (Recommended)" as the first option: every plan save then '
            "updates the plan site within a minute, without a stored token."
        )


# %% the command line

app = App(help=__doc__)
"""
The command, which takes no arguments.
"""


@app.default
def start_build() -> int:
    """
    Start this clone's plan site build and print what happened.

    :return: 0, also when the build did not start: the notes were saved either way.
    """
    project_root = Path(
        os.environ.get(ClaudeCodeVariable.PROJECT_DIRECTORY, Path.cwd())
    )
    location = PersonalNotesLocation.resolve(project_root, os.environ)
    site = SiteRepository.recorded_on(
        RemoteBranch(location.branch, GitCommandRunner(project_root), location.remote)
    )
    if site is None:
        print("No plan site lists this repository, so no build was started.")
        return 0
    client = GitHubRestClient()
    attempt = BuildStart.attempt(site, client, client)
    print(attempt.describe(ClaudeCodeVariable.REMOTE.read() == "true"))
    return 0


if __name__ == "__main__":
    app()
