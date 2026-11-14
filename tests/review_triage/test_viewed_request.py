"""
Asking a repository's Actions to mark a pull request's mechanical files viewed.
"""

from __future__ import annotations

from http import HTTPStatus

import pytest

from basstler.github.repository_details import RepositoryDetails
from basstler.locations import WorkflowLocation
from basstler.repository import PullRequestReference, Repository
from basstler.review_triage.exceptions import MarkViewedWorkflowRefused
from basstler.review_triage.viewed_request import (
    MarkViewedDispatch,
    MarkViewedInputs,
    MarkViewedRequest,
)

from .conftest import (
    SAMPLE_REPOSITORY,
    WORKFLOW_REPOSITORY_DETAILS,
    WorkflowRepositoryClient,
)

# %% the request

FORK = Repository("a-reviewer", "project")
"""
The repository whose workflow marks the files.
"""

REQUEST = MarkViewedRequest(FORK, PullRequestReference(SAMPLE_REPOSITORY, 7))
"""
A request for the fork's workflow to mark a pull request of the sample repository.
"""

DEFAULT_BRANCH = RepositoryDetails.from_json(WORKFLOW_REPOSITORY_DETAILS).default_branch
"""
The branch the stand-in workflow repository reports as its default.
"""


def test_the_workflow_runs_on_the_default_branch_for_the_pull_request():
    """
    One dispatch is sent to the workflow repository's default branch, naming the pull
    request and the repository it is opened on.
    """
    client = WorkflowRepositoryClient()

    REQUEST.send(client)

    assert client.sent == [
        MarkViewedDispatch(
            FORK,
            WorkflowLocation.MARK_VIEWED,
            DEFAULT_BRANCH,
            MarkViewedInputs(
                str(REQUEST.pull_request.number), SAMPLE_REPOSITORY.full_name
            ),
        )
    ]


def test_the_dispatch_sends_the_branch_and_the_inputs():
    """
    The body is the branch under GitHub's ``ref`` and the inputs by the workflow's
    names.
    """
    inputs = MarkViewedInputs("7", SAMPLE_REPOSITORY.full_name)
    dispatch = MarkViewedDispatch(
        FORK, WorkflowLocation.MARK_VIEWED, DEFAULT_BRANCH, inputs
    )

    assert dispatch.to_json() == {"ref": DEFAULT_BRANCH, "inputs": inputs.to_json()}


def test_the_answer_points_to_the_workflow_s_runs():
    """
    The page returned lists the runs of the workflow in the workflow repository.
    """
    runs = REQUEST.send(WorkflowRepositoryClient())

    assert runs == f"{FORK.url}/actions/workflows/{WorkflowLocation.MARK_VIEWED.name}"


def test_an_unreadable_workflow_repository_dispatches_nothing():
    """
    When the workflow repository cannot be read, the refusal is raised and nothing is
    sent.
    """
    client = WorkflowRepositoryClient(read_refusal=HTTPStatus.NOT_FOUND)

    with pytest.raises(MarkViewedWorkflowRefused):
        REQUEST.send(client)
    assert client.sent == []


def test_a_refused_dispatch_is_raised():
    """
    A workflow GitHub will not start, such as one not on the default branch, is raised.
    """
    client = WorkflowRepositoryClient(write_refusal=HTTPStatus.NOT_FOUND)

    with pytest.raises(MarkViewedWorkflowRefused):
        REQUEST.send(client)
