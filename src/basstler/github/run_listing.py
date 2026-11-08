"""
The workflow runs a repository's branch has had, read from GitHub.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode

from pydantic import Field

from basstler.locations import WorkflowLocation
from basstler.repository import Repository
from basstler.standard_streams import StandardStreamHandler
from basstler.github.client import (
    GitHubReader,
)
from basstler.github.workflow_run import WorkflowRun
from basstler.upstream_reviews.vocabulary import (
    CheckOutcome,
    ValidatedJSONModel,
    WebPage,
)

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""

MAXIMUM_RUNS_PER_PAGE = 100
"""
The most runs GitHub lists on one page.
"""

# %% the runs that confirm a step


class ListedRun(WorkflowRun, WebPage):
    """
    One run, as a repository's run listing describes it.
    """

    workflow_file_path: Annotated[Path, Field(alias="path")]
    """
    The workflow file it ran, relative to its repository's root.
    """

    created_at: datetime
    """
    When it was started.
    """


class RunListing(ValidatedJSONModel):
    """
    The latest runs on one branch of a repository, newest first.
    """

    workflow_runs: list[ListedRun]
    """
    The runs.
    """

    @staticmethod
    def path(
        repository: Repository, branch: str, runs_per_page: int = MAXIMUM_RUNS_PER_PAGE
    ) -> str:
        """
        :param repository: The repository.
        :param branch: The branch the runs ran on.
        :param runs_per_page: How many of the latest runs to list.
        :return: The REST path listing them.
        """
        query = urlencode(
            {
                "branch": branch,
                "per_page": runs_per_page,
            }
        )
        return f"{repository.api_path}/actions/runs?{query}"

    @classmethod
    def read(
        cls, client: GitHubReader, repository: Repository, branch: str
    ) -> RunListing:
        """
        :param client: What reads the listing.
        :param repository: The repository.
        :param branch: The branch the runs ran on.
        :return: The listing.
        """
        return cls.from_json(client.get(cls.path(repository, branch)))

    def run_for_commit(self, commit: str) -> ListedRun | None:
        """
        :param commit: The commit a run was started for.
        :return: The latest run started for it, ``None`` when none was.
        """
        return next((run for run in self.workflow_runs if run.commit == commit), None)

    def select(self, workflow: WorkflowLocation) -> RunListing:
        """
        :param workflow: The workflow.
        :return: The listing of its runs alone.
        """
        return RunListing(
            [run for run in self.workflow_runs if run.workflow_file_path == workflow]
        )

    def count(self, outcome: CheckOutcome) -> int:
        """
        :param outcome: How a run ended.
        :return: How many listed runs ended so.
        """
        return sum(run.outcome is outcome for run in self.workflow_runs)

    def latest(self, workflow: WorkflowLocation) -> ListedRun | None:
        """
        :param workflow: The workflow.
        :return: Its latest run, ``None`` when the listing holds none.
        """
        return next(
            (run for run in self.workflow_runs if run.workflow_file_path == workflow),
            None,
        )

    def latest_success(self, workflow: WorkflowLocation) -> ListedRun | None:
        """
        :param workflow: The workflow.
        :return: Its latest run that succeeded, ``None`` when the listing holds none.
        """
        return next(
            (
                run
                for run in self.workflow_runs
                if run.workflow_file_path == workflow
                and run.outcome is CheckOutcome.SUCCESS
            ),
            None,
        )

    def succeeded(self, workflow: WorkflowLocation) -> bool:
        """
        :param workflow: The workflow.
        :return: Whether its latest run succeeded.
        """
        latest = self.latest(workflow)
        return latest is not None and latest.outcome is CheckOutcome.SUCCESS
