"""
Setting a repository's Actions up to mark files viewed, and the steps left to the user.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Any

import pytest

from basstler.github.client import (
    GitHubAttemptClient,
    GitHubResponse,
    GitHubWrite,
    HttpMethod,
)
from basstler.github.repository_details import RepositoryDetails
from basstler.github.token_form import RepositoryPermission
from basstler.locations import WorkflowLocation
from basstler.repository import BASSTLER_REPOSITORY, Repository
from basstler.review_triage.exceptions import MarkViewedWorkflowRefused
from basstler.review_triage.viewed_request import ReviewTriageSecret
from basstler.review_triage.viewed_setup import (
    ActionsEnabling,
    FileUpdate,
    FileWrite,
    MarkViewedSetup,
    SetupState,
    WorkflowEnabling,
    WorkflowState,
)

from ..constants.paths import RepositoryLocation
from .conftest import WORKFLOW_REPOSITORY_DETAILS, refusal

# %% a stand-in for GitHub

FORK = Repository("a-reviewer", "project")
"""
The repository whose Actions are set up.
"""

UPSTREAM = Repository("an-organisation", "project")
"""
The repository the fork was made from, where the pull requests are opened.
"""


class Resource:
    """
    The REST paths the setup reads on the fork.
    """

    WORKFLOW_FILE = (
        f"{FORK.api_path}/contents/{WorkflowLocation.MARK_VIEWED.as_posix()}"
        f"?ref={RepositoryDetails.from_json(WORKFLOW_REPOSITORY_DETAILS).default_branch}"
    )
    ACTIONS = f"{FORK.api_path}/actions/permissions"
    WORKFLOW = WorkflowEnabling.workflow_path(FORK, WorkflowLocation.MARK_VIEWED)
    SECRET = f"{FORK.api_path}/actions/secrets/{ReviewTriageSecret.VIEWER_TOKEN}"


def fork_details(is_fork: bool = True) -> dict[str, Any]:
    """
    :param is_fork: Whether the repository is a fork of :data:`UPSTREAM`.
    :return: Its REST resource.
    """
    details = dict(WORKFLOW_REPOSITORY_DETAILS, fork=is_fork)
    if is_fork:
        details["parent"] = {"full_name": UPSTREAM.full_name}
    return details


@dataclass
class ForkAnswers(GitHubAttemptClient):
    """
    Answers each path the setup reads, refusing a path it has no answer for, and accepts
    every write.
    """

    answers: dict[str, Any] = field(default_factory=dict)
    """
    The body each readable path is answered with.
    """

    sent: list[GitHubWrite] = field(default_factory=list)
    """
    Every write sent, oldest first.
    """

    def attempt_get(self, path: str) -> GitHubResponse:
        if path in self.answers:
            return GitHubResponse(self.answers[path])
        return refusal(HTTPStatus.NOT_FOUND, HttpMethod.GET, path)

    def attempt_send(self, write: GitHubWrite) -> GitHubResponse:
        self.sent.append(write)
        return GitHubResponse(None)


INSTALLED_BLOB = "a-blob"
"""
The blob the installed workflow file holds.
"""


def installed_workflow(setup: MarkViewedSetup) -> dict[str, Any]:
    """
    :param setup: The setup whose workflow is installed.
    :return: The contents API's answer for that workflow file.
    """
    content = base64.encodebytes(setup.caller_workflow.encode()).decode()
    return {"sha": INSTALLED_BLOB, "content": content}


def answers(**overrides: Any) -> ForkAnswers:
    """
    :param overrides: Answers replacing the fully set-up fork's, ``None`` to refuse
        that path.
    :return: The fork answering as fully set up, apart from *overrides*.
    """
    readable = {
        FORK.api_path: fork_details(),
        Resource.WORKFLOW_FILE: installed_workflow(MarkViewedSetup(FORK)),
        Resource.ACTIONS: {"enabled": True},
        Resource.WORKFLOW: {"state": WorkflowState.ACTIVE},
        Resource.SECRET: {"name": ReviewTriageSecret.VIEWER_TOKEN},
    }
    readable |= {getattr(Resource, name): answer for name, answer in overrides.items()}
    return ForkAnswers({path: body for path, body in readable.items() if body})


# %% taking the steps


def test_a_set_up_fork_is_left_alone():
    client = answers()
    setup = MarkViewedSetup(FORK)
    setup.run(client)
    assert (client.sent, setup.user_steps) == ([], [])
    assert {step.state for step in setup.steps} == {SetupState.ALREADY_DONE}


def test_the_workflow_is_committed_to_a_fork_s_default_branch():
    client = answers(WORKFLOW_FILE=None, WORKFLOW=None)
    setup = MarkViewedSetup(FORK)
    setup.run(client)
    written = [write for write in client.sent if isinstance(write, FileWrite)]
    assert [
        (write.branch, base64.b64decode(write.content).decode()) for write in written
    ] == [
        (
            RepositoryDetails.from_json(WORKFLOW_REPOSITORY_DETAILS).default_branch,
            setup.caller_workflow,
        )
    ]


def test_a_repository_that_is_no_fork_gets_the_workflow_as_a_step_left():
    client = answers(WORKFLOW_FILE=None)
    client.answers[FORK.api_path] = fork_details(is_fork=False)
    setup = MarkViewedSetup(FORK)
    setup.run(client)
    assert [write for write in client.sent if isinstance(write, FileWrite)] == []
    assert [step.text for step in setup.user_steps] == [setup.caller_workflow]


def test_actions_turned_off_are_turned_on():
    client = answers(ACTIONS={"enabled": False})
    MarkViewedSetup(FORK).run(client)
    assert client.sent == [ActionsEnabling(FORK)]


def test_a_disabled_workflow_is_enabled():
    client = answers(WORKFLOW={"state": "disabled_fork"})
    MarkViewedSetup(FORK).run(client)
    assert client.sent == [WorkflowEnabling(FORK, WorkflowLocation.MARK_VIEWED)]


def test_a_missing_secret_leaves_creating_and_storing_the_token():
    setup = MarkViewedSetup(FORK)
    setup.run(answers(SECRET=None))
    create, store = setup.user_steps
    assert f"={UPSTREAM.owner}&" in create.browser_steps[0]
    assert RepositoryPermission.PULL_REQUESTS in create.browser_steps[0]
    assert store.command == (
        f"gh secret set {ReviewTriageSecret.VIEWER_TOKEN} --repo {FORK.full_name}"
    )


def test_an_unreadable_repository_is_raised():
    client = ForkAnswers()
    with pytest.raises(MarkViewedWorkflowRefused):
        MarkViewedSetup(FORK).run(client)


def test_the_report_names_every_step_left_as_written():
    """
    Each step left is in the report, only its first letter capitalised.
    """
    setup = MarkViewedSetup(FORK)
    report = setup.run(answers(SECRET=None))
    named = [
        f"{step.description[0].upper()}{step.description[1:]}:" in report
        for step in setup.user_steps
    ]
    assert named == [True, True]


def test_the_settings_of_a_repository_that_is_no_fork_are_never_changed():
    client = answers(
        ACTIONS={"enabled": False}, WORKFLOW={"state": "disabled_manually"}
    )
    client.answers[FORK.api_path] = fork_details(is_fork=False)
    MarkViewedSetup(FORK).run(client)
    assert client.sent == []


def test_unreadable_actions_settings_are_never_changed_or_called_off():
    client = answers(ACTIONS=None)
    setup = MarkViewedSetup(FORK)
    setup.run(client)
    assert client.sent == []
    actions = f"Actions on {FORK.full_name}"
    assert [step.state for step in setup.steps if step.description == actions] == [
        SetupState.REFUSED
    ]


def test_basstler_s_own_caller_is_the_one_the_setup_installs():
    """
    Basstler's own repository marks files viewed with the workflow the setup writes.
    """
    installed = (RepositoryLocation.ROOT / WorkflowLocation.MARK_VIEWED).read_text()
    assert installed == MarkViewedSetup(BASSTLER_REPOSITORY).caller_workflow


# %% every pull request


def test_a_fork_s_other_workflow_version_is_replaced():
    client = answers(WORKFLOW_FILE=installed_workflow(MarkViewedSetup(FORK)))
    setup = MarkViewedSetup(FORK, on_every_pull_request=True)
    setup.run(client)
    updates = [write for write in client.sent if isinstance(write, FileUpdate)]
    assert [
        (write.sha, base64.b64decode(write.content).decode()) for write in updates
    ] == [(INSTALLED_BLOB, setup.caller_workflow)]


def test_the_workflow_runs_on_every_pull_request_only_when_asked():
    triggers = [
        "pull_request_target"
        in MarkViewedSetup(FORK, on_every_pull_request=asked).caller_workflow
        for asked in (False, True)
    ]
    assert triggers == [False, True]


def test_a_fork_cannot_run_on_its_parent_s_pull_requests():
    setup = MarkViewedSetup(FORK, on_every_pull_request=True)
    setup.run(answers(WORKFLOW_FILE=installed_workflow(setup)))
    assert [
        step.state for step in setup.steps if UPSTREAM.full_name in step.reason
    ] == [SetupState.LEFT_TO_USER]
