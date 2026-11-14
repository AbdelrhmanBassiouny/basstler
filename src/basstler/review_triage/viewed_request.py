"""
Asking a repository's Actions to mark a pull request's mechanical files viewed, for
sessions that cannot reach GitHub's GraphQL API themselves.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from basstler.github.client import GitHubAttemptClient
from basstler.github.repository_details import RepositoryDetails
from basstler.github.workflow_run import WorkflowDispatch
from basstler.json_model import ValidatedJSONModel
from basstler.locations import WorkflowLocation
from basstler.repository import PullRequestReference, Repository
from basstler.review_triage.exceptions import MarkViewedWorkflowRefused

# %% names the workflow reads


class ReviewTriageSecret(StrEnum):
    """
    The Actions secrets the review triage's workflows read.
    """

    VIEWER_TOKEN = "REVIEW_TRIAGE_VIEWER_TOKEN"
    """
    The token of the account files are marked viewed for, stored on the repository
    whose Actions mark them.
    """


# %% the dispatch


class MarkViewedInputs(ValidatedJSONModel):
    """
    The inputs of the workflow marking a pull request's mechanical files viewed.
    """

    pull_request: str
    """
    The pull request's number, as text like every dispatched input.
    """

    repository: str
    """
    The repository the pull request is opened on, as ``owner/name``.
    """


class MarkViewedDispatch(WorkflowDispatch):
    """
    A request to run the workflow marking a pull request's mechanical files viewed.
    """

    inputs: MarkViewedInputs
    """
    Which pull request it marks.
    """


@dataclass(frozen=True)
class MarkViewedRequest:
    """
    Asks the workflow of one repository to mark one pull request's mechanical files
    viewed for the account whose token that repository stores.
    """

    workflow_repository: Repository
    """
    The repository whose workflow marks the files.
    """

    pull_request: PullRequestReference
    """
    The pull request whose files are marked.
    """

    def send(self, client: GitHubAttemptClient) -> str:
        """
        :param client: Reads the workflow repository and sends the dispatch.
        :return: The page listing the workflow's runs, where this one's outcome shows.
        :raises MarkViewedWorkflowRefused: If GitHub refuses either call.
        """
        details = client.attempt_get(self.workflow_repository.api_path)
        if details.failure is not None:
            raise MarkViewedWorkflowRefused(
                self.workflow_repository, details.failure.error_message()
            )
        dispatch = client.attempt_send(
            MarkViewedDispatch(
                self.workflow_repository,
                WorkflowLocation.MARK_VIEWED,
                RepositoryDetails.from_json(details.body).default_branch,
                MarkViewedInputs(
                    str(self.pull_request.number),
                    self.pull_request.repository.full_name,
                ),
            )
        )
        if dispatch.failure is not None:
            raise MarkViewedWorkflowRefused(
                self.workflow_repository, dispatch.failure.error_message()
            )
        return (
            f"{self.workflow_repository.url}/actions/workflows/"
            f"{WorkflowLocation.MARK_VIEWED.name}"
        )
