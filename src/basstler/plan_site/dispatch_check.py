"""
Print check-setup.sh's plan site status and detail: whether the notes branch's latest
dispatch run started the plan site's build.

Usage:
    "${BASSTLER_PYTHON}" -m basstler.plan_site.dispatch_check
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from basstler.github.client import GitHubReader, GitHubRestClient
from basstler.locations import ClaudeCodeVariable
from basstler.personal_notes.branch import PersonalNotesLocation
from basstler.plan_site import publication
from basstler.plan_site.exceptions import NotesRepositoryUnresolvedError
from basstler.plan_site.run_listing import RunListing
from basstler.plan_site.workflows import DispatchWorkflow
from basstler.repository import Repository
from basstler.setup.report import CheckResult, CheckStatus
from basstler.setup.steps import resolve_repository
from basstler.upstream_reviews.vocabulary import CheckOutcome

# %% the latest dispatch run


@dataclass(frozen=True)
class DispatchCheck:
    """
    Whether the notes branch's dispatch workflow starts the plan site's build.
    """

    notes_repository: Repository
    """
    The repository whose notes branch runs the dispatch workflow.
    """

    notes_branch: str
    """
    The branch the dispatch workflow runs on.
    """

    github: GitHubReader
    """
    What reads the notes branch's workflow runs.
    """

    def result(self) -> CheckResult:
        """
        :return: :attr:`CheckStatus.OK` only when the latest dispatch run succeeded.
        """
        publish_command = f"{sys.executable} -m {publication.__name__}"
        latest = RunListing.read(
            self.github, self.notes_repository, self.notes_branch
        ).latest(DispatchWorkflow.location)
        if latest is None:
            return CheckResult(
                CheckStatus.NEEDS_SETUP,
                f"'{self.notes_branch}' has never run {DispatchWorkflow.location} - "
                f"for what is left, run: {publish_command}",
            )
        if latest.outcome is not CheckOutcome.SUCCESS:
            return CheckResult(
                CheckStatus.NEEDS_SETUP,
                f"the latest {DispatchWorkflow.location} run on '{self.notes_branch}' "
                f"is {latest.outcome} ({latest.url}) - for what is left, run: "
                f"{publish_command}",
            )
        return CheckResult(
            CheckStatus.OK,
            f"'{self.notes_branch}' starts the plan site's build on every push",
        )


# %% the command


def main() -> int:
    """
    Print this clone's dispatch check.

    See the module docstring.
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
    check = DispatchCheck(notes_repository, location.branch, GitHubRestClient())
    print(check.result().fields)
    return 0


if __name__ == "__main__":
    sys.exit(main())
