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
from basstler.github.file_proposal import FileUpdate, FileWrite, NewBranch
from basstler.github.pull_request import NewPullRequest
from basstler.github.pull_request_form import PullRequestForm
from basstler.github.repository_details import RepositoryDetails
from basstler.github.token_form import PermissionLevel, RepositoryPermission, TokenUse
from basstler.locations import WorkflowLocation
from basstler.repository import BASSTLER_REPOSITORY, Repository
from basstler.review_triage.exceptions import MarkViewedWorkflowRefused
from basstler.review_triage.viewed_request import ReviewTriageSecret
from basstler.review_triage.viewed_setup import (
    ActionsEnabling,
    MarkViewedSetup,
    ProposalBranch,
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
    OPEN_PROPOSALS = (
        f"{FORK.pull_requests_path}?state=open"
        f"&head={FORK.owner}:{ProposalBranch.MARK_VIEWED}"
    )
    PROPOSAL_BRANCH = f"{FORK.api_path}/git/ref/heads/{ProposalBranch.MARK_VIEWED}"
    DEFAULT_BRANCH = (
        f"{FORK.api_path}/git/ref/heads/"
        f"{RepositoryDetails.from_json(WORKFLOW_REPOSITORY_DETAILS).default_branch}"
    )
    PROPOSED_FILE = (
        f"{FORK.api_path}/contents/{WorkflowLocation.MARK_VIEWED.as_posix()}"
        f"?ref={ProposalBranch.MARK_VIEWED}"
    )
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

    forbidden: set[str] = field(default_factory=set)
    """
    The paths refused as forbidden rather than as not found.
    """

    write_answers: dict[str, Any] = field(default_factory=dict)
    """
    The body each write path is answered with, ``None`` for any other.
    """

    write_refusal: HTTPStatus | None = None
    """
    The status every write is refused with, ``None`` to accept them.
    """

    refused_writes: set[str] = field(default_factory=set)
    """
    The write paths refused as forbidden, whatever :attr:`write_refusal` is.
    """

    sent: list[GitHubWrite] = field(default_factory=list)
    """
    Every write sent, oldest first.
    """

    def attempt_get(self, path: str) -> GitHubResponse:
        if path in self.forbidden:
            return refusal(HTTPStatus.FORBIDDEN, HttpMethod.GET, path)
        if path in self.answers:
            return GitHubResponse(self.answers[path])
        return refusal(HTTPStatus.NOT_FOUND, HttpMethod.GET, path)

    def attempt_send(self, write: GitHubWrite) -> GitHubResponse:
        self.sent.append(write)
        if write.path in self.refused_writes:
            return refusal(HTTPStatus.FORBIDDEN, write.method, write.path)
        if self.write_refusal is not None:
            return refusal(self.write_refusal, write.method, write.path)
        return GitHubResponse(self.write_answers.get(write.path))


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
    return ForkAnswers(
        {path: body for path, body in readable.items() if body is not None}
    )


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


# %% a repository that is no fork


BASE_COMMIT = "a-base-commit"
"""
The commit the default branch points at.
"""

PROPOSAL = {"number": 7, "html_url": f"{FORK.url}/pull/7"}
"""
The pull request proposing the workflow.
"""


def unforked_answers(**overrides: Any) -> ForkAnswers:
    """
    :param overrides: Answers replacing the unset-up repository's, as for
        :func:`answers`.
    :return: A repository that is no fork, lacking the workflow and any proposal of it.
    """
    unset_up = {
        "WORKFLOW_FILE": None,
        "OPEN_PROPOSALS": [],
        "DEFAULT_BRANCH": {"object": {"sha": BASE_COMMIT}},
    }
    client = answers(**(unset_up | overrides))
    client.answers[FORK.api_path] = fork_details(is_fork=False)
    client.write_answers[FORK.pull_requests_path] = PROPOSAL
    return client


def test_a_repository_that_is_no_fork_gets_a_pull_request_adding_the_workflow():
    client = unforked_answers()
    setup = MarkViewedSetup(FORK)
    setup.run(client)
    default_branch = RepositoryDetails.from_json(WORKFLOW_REPOSITORY_DETAILS)
    assert [
        write
        for write in client.sent
        if isinstance(write, (NewBranch, FileWrite, NewPullRequest))
    ] == [
        NewBranch(
            FORK, ref=f"refs/heads/{ProposalBranch.MARK_VIEWED}", sha=BASE_COMMIT
        ),
        FileWrite(
            FORK,
            file=WorkflowLocation.MARK_VIEWED.as_posix(),
            message=setup.workflow_proposal(default_branch).title,
            content=base64.b64encode(setup.caller_workflow.encode()).decode(),
            branch=ProposalBranch.MARK_VIEWED,
        ),
        NewPullRequest(
            FORK,
            title=setup.workflow_proposal(default_branch).title,
            head=ProposalBranch.MARK_VIEWED,
            base=default_branch.default_branch,
            body=setup.workflow_proposal(default_branch).body,
            draft=False,
        ),
    ]


def test_merging_the_proposal_is_the_step_left():
    setup = MarkViewedSetup(FORK)
    setup.run(unforked_answers())
    assert setup.user_steps[0].browser_steps[0] == f"Open {PROPOSAL['html_url']}."


def test_an_open_proposal_is_not_opened_again():
    setup = MarkViewedSetup(FORK)
    proposed = installed_workflow(setup)
    client = unforked_answers(
        OPEN_PROPOSALS=[PROPOSAL],
        PROPOSAL_BRANCH={"object": {"sha": BASE_COMMIT}},
        PROPOSED_FILE=proposed,
    )
    setup.run(client)
    assert client.sent == []


def test_a_proposal_branch_holding_another_version_is_updated():
    setup = MarkViewedSetup(FORK, on_every_pull_request=True)
    client = unforked_answers(
        PROPOSAL_BRANCH={"object": {"sha": BASE_COMMIT}},
        PROPOSED_FILE=installed_workflow(MarkViewedSetup(FORK)),
    )
    setup.run(client)
    updates = [write for write in client.sent if isinstance(write, FileUpdate)]
    assert [(write.branch, write.sha) for write in updates] == [
        (ProposalBranch.MARK_VIEWED, INSTALLED_BLOB)
    ]


def test_a_refused_proposal_leaves_the_filled_in_page_adding_the_workflow():
    client = unforked_answers()
    client.write_refusal = HTTPStatus.FORBIDDEN
    setup = MarkViewedSetup(FORK)
    setup.run(client)
    page = setup.workflow_proposal(
        RepositoryDetails.from_json(fork_details(is_fork=False))
    ).new_file_page
    assert setup.user_steps[0].browser_steps[0].startswith(f"Open {page} ")


def test_a_refused_proposal_replacing_another_version_leaves_the_file_to_paste():
    client = unforked_answers(WORKFLOW_FILE=installed_workflow(MarkViewedSetup(FORK)))
    client.write_refusal = HTTPStatus.FORBIDDEN
    setup = MarkViewedSetup(FORK, on_every_pull_request=True)
    setup.run(client)
    assert [step.text for step in setup.user_steps if step.text] == [
        setup.caller_workflow
    ]


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
        SetupState.UNREADABLE
    ]


def test_an_unreadable_secret_is_reported_unread_with_the_token_steps_left():
    client = answers()
    client.forbidden.add(Resource.SECRET)
    setup = MarkViewedSetup(FORK)
    setup.run(client)
    secret = f"{ReviewTriageSecret.VIEWER_TOKEN} stored on {FORK.full_name}"
    assert (
        [step.state for step in setup.steps if step.description == secret],
        len(setup.user_steps),
    ) == (
        [SetupState.UNREADABLE],
        len(setup.token_steps(RepositoryDetails.from_json(fork_details()))),
    )


def test_basstler_s_own_caller_marks_every_pull_request():
    """
    Basstler's own repository marks files viewed on every pull request with the workflow
    the setup writes.
    """
    installed = (RepositoryLocation.ROOT / WorkflowLocation.MARK_VIEWED).read_text()
    assert (
        installed
        == MarkViewedSetup(
            BASSTLER_REPOSITORY, on_every_pull_request=True
        ).caller_workflow
    )


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


# %% one token for several jobs


def shared_use(owner: str) -> TokenUse:
    """
    :param owner: The owner of the repository the other job reaches.
    :return: Another job of basstler's, starting a workflow there.
    """
    return TokenUse(
        "starts a build",
        (Repository(owner, "site"),),
        {RepositoryPermission.ACTIONS: PermissionLevel.WRITE},
        "BUILD_TOKEN",
        (FORK,),
    )


def test_a_job_on_the_pull_requests_owner_shares_the_token():
    other = shared_use(UPSTREAM.owner)
    setup = MarkViewedSetup(FORK, shared_uses=(other,))
    setup.run(answers(SECRET=None))
    create, store = setup.user_steps
    assert (
        f"{RepositoryPermission.ACTIONS}={PermissionLevel.WRITE}"
        in create.browser_steps[0],
        store.command.count("gh secret set"),
    ) == (True, 2)


def test_a_job_on_another_owner_s_repositories_gets_a_token_of_its_own():
    alone = MarkViewedSetup(FORK)
    alone.run(answers(SECRET=None))
    shared = MarkViewedSetup(FORK, shared_uses=(shared_use("someone-else"),))
    shared.run(answers(SECRET=None))
    assert shared.user_steps == alone.user_steps


def test_a_secret_that_may_be_stored_already_says_its_token_steps_may_be_skipped():
    missing = MarkViewedSetup(FORK)
    missing.run(answers(SECRET=None))
    client = answers()
    client.forbidden.add(Resource.SECRET)
    unread = MarkViewedSetup(FORK)
    unread.run(client)
    assert [
        (left.description == right.description)
        for left, right in zip(missing.user_steps, unread.user_steps, strict=True)
    ] == [False, False]


def test_a_token_left_to_the_user_is_reported_as_left():
    setup = MarkViewedSetup(FORK)
    setup.run(answers(SECRET=None))
    assert setup.token_left


def test_a_stored_token_is_not_reported_as_left():
    setup = MarkViewedSetup(FORK)
    setup.run(answers())
    assert not setup.token_left


# %% a pull request already carrying the workflow, or one that cannot be opened


ALL_OPEN = f"{FORK.pull_requests_path}?state=open&per_page=100"
"""
The listing of every open pull request on the repository.
"""


def carrying_pull_request(base: str) -> dict[str, Any]:
    """
    :param base: The branch it merges into.
    :return: An open pull request from another branch, as the listing gives it.
    """
    return {
        "number": 9,
        "html_url": f"{FORK.url}/pull/9",
        "head": {"ref": "another-branch", "sha": "a-head-commit"},
        "base": {"ref": base, "sha": "a-base-commit"},
    }


def carried_workflow(setup: MarkViewedSetup, base: str, text: str) -> ForkAnswers:
    """
    :param setup: The setup whose workflow another pull request holds.
    :param base: The branch that pull request merges into.
    :param text: The workflow file its head holds.
    :return: A repository that is no fork, with that pull request open.
    """
    client = unforked_answers()
    client.answers[ALL_OPEN] = [carrying_pull_request(base)]
    client.answers[
        setup.workflow_proposal(
            RepositoryDetails.from_json(fork_details(is_fork=False))
        ).contents_path("a-head-commit")
    ] = {"sha": INSTALLED_BLOB, "content": base64.encodebytes(text.encode()).decode()}
    return client


def test_an_open_pull_request_carrying_the_workflow_is_reported_and_nothing_written():
    setup = MarkViewedSetup(FORK)
    default_branch = RepositoryDetails.from_json(WORKFLOW_REPOSITORY_DETAILS)
    client = carried_workflow(
        setup, default_branch.default_branch, setup.caller_workflow
    )
    setup.run(client)
    assert (client.sent, setup.user_steps[0].browser_steps[0]) == (
        [],
        f"Open {carrying_pull_request('')['html_url']}.",
    )


def test_a_pull_request_carrying_another_version_is_not_taken_for_it():
    setup = MarkViewedSetup(FORK)
    client = carried_workflow(setup, "main", "another workflow\n")
    setup.run(client)
    assert (
        len([write for write in client.sent if isinstance(write, NewPullRequest)]) == 1
    )


def test_a_carrying_pull_request_on_another_base_says_what_it_merges_into():
    setup = MarkViewedSetup(FORK)
    client = carried_workflow(setup, "a-stacked-base", setup.caller_workflow)
    setup.run(client)
    installed = f"the {WorkflowLocation.MARK_VIEWED.name} workflow on"
    (reason,) = [
        step.reason for step in setup.steps if step.description.startswith(installed)
    ]
    assert "merging into a-stacked-base" in reason


def test_a_refused_pull_request_gets_the_form_with_everything_filled_in():
    client = unforked_answers()
    client.refused_writes.add(FORK.pull_requests_path)
    setup = MarkViewedSetup(FORK)
    setup.run(client)
    proposal = setup.workflow_proposal(
        RepositoryDetails.from_json(fork_details(is_fork=False))
    )
    expected = PullRequestForm(
        FORK, proposal.base, proposal.branch, proposal.title, proposal.body
    ).link
    assert setup.user_steps[0].browser_steps[0].startswith(f"Open {expected.url} ")


def test_of_two_stacked_pull_requests_carrying_the_workflow_the_lower_is_reported():
    setup = MarkViewedSetup(FORK)
    client = carried_workflow(setup, "a-stacked-base", setup.caller_workflow)
    lower = carrying_pull_request("a-stacked-base")
    upper = dict(
        carrying_pull_request(lower["head"]["ref"]),
        number=10,
        html_url=f"{FORK.url}/pull/10",
        head={"ref": "an-upper-branch", "sha": "a-head-commit"},
    )
    client.answers[ALL_OPEN] = [upper, lower]
    setup.run(client)
    assert setup.user_steps[0].browser_steps[0] == f"Open {lower['html_url']}."
