"""
Tests for the maintenance executor's command line, whose exit status a caller acts on.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass, field as dataclasses_field

import pytest

import basstler.maintenance.__main__
from basstler.environment import GitHubCredentialVariable
from basstler.exit_codes import StackExitCode
from basstler.github.constants import MaintenanceNotice
from basstler.github.pull_request_state import PullRequestState
from basstler.github.repository_access import ForkPullRequests, PullRequestListState
from basstler.locations import RepositoryStateLocation
from basstler.maintenance.board import BoardExport
from basstler.upstream_reviews.action.open_pull_requests import UpstreamPullRequests
from basstler.maintenance.commands import (
    BoardCommand,
    MaintenanceCommand,
    MaintenancePass,
    PrepareCommand,
    RestackCommand,
    RunReportCommand,
)
from basstler.maintenance.restack_steps import RestackStep
from basstler.maintenance.upstream_read_route import UpstreamReadRoute
from basstler.stack.model import PullRequest

from ..constants.stack import RemoteName, StackBranch
from .fork import (
    ForkCheckout,
    a_parent_and_child,
    make_configuration,
    make_own_remote_configuration,
    the_board,
)
from .recorded_fork import (
    maintenance_runner,
    run_maintenance,
)

# %% the command line a caller acts on the exit status of


def test_an_unknown_command_is_a_usage_error(fork_checkout: ForkCheckout):
    fork_checkout.name_the_upstream()

    result = maintenance_runner(fork_checkout).run("not-a-command")

    assert result.returncode == StackExitCode.USAGE


def test_every_command_class_is_one_reachable_command():
    """
    Commands are found from their own subclasses, so a class that exists is a command -
    and two answering to the same name would make one of them unreachable.
    """
    commands = MaintenanceCommand.every_command()
    assert {type(command) for command in commands} == set(
        MaintenanceCommand.__subclasses__()
    )
    assert len({command.invoked_as for command in commands}) == len(commands)


def test_a_command_names_itself_without_being_instantiated():
    """
    The parser reads both to build the command line before any command is constructed,
    so they have to answer on the class.
    """
    assert BoardCommand.invoked_as == "board"
    assert isinstance(BoardCommand.description, str)


def test_a_command_that_omits_its_description_cannot_be_built():
    """
    A command stays abstract until it says what it does, and every_command builds every
    subclass - so one that never says cannot reach the parser at all.
    """

    @dataclass(frozen=True)
    class CommandWithoutADescription(MaintenanceCommand):
        def run(self, maintenance, arguments):
            return StackExitCode.SUCCESS

    with pytest.raises(TypeError, match="description"):
        CommandWithoutADescription()


def test_a_fork_client_that_cannot_make_one_of_the_writes_cannot_be_built():
    """
    The reading and the writing halves are inherited rather than matched by shape, so a
    client that could not post the comment a conflict is reported in is refused when it
    is built, rather than when the first conflict needs reporting.
    """

    @dataclass(frozen=True)
    class ForkThatCannotComment(ForkPullRequests):
        def open_pull_requests(self) -> list[dict]:
            return []

        def pull_request(self, number: int) -> dict:
            return {}

        def replace_labels(self, number: int, labels: Sequence[str]) -> None:
            """
            Recorded nowhere, since this fork is never expected to be built.
            """

        def set_description(self, number: int, body: str) -> None:
            """
            Recorded nowhere, since this fork is never expected to be built.
            """

    with pytest.raises(TypeError, match="add_comment"):
        ForkThatCannotComment()


def test_a_restack_step_that_does_nothing_cannot_be_built():
    """
    A step is only ever reached through restack_steps, where one that concludes nothing
    would silently pass every branch along to the next step.
    """

    @dataclass(frozen=True)
    class StepWithoutAnAttempt(RestackStep):
        pass

    with pytest.raises(TypeError, match="attempt"):
        StepWithoutAnAttempt()


def test_every_command_is_reachable_from_the_command_line(fork_checkout: ForkCheckout):
    """
    A command in the enum that the parser never registers is unreachable, and nothing
    else would notice.
    """
    for command in MaintenanceCommand.every_command():
        result = run_maintenance(fork_checkout, command, "--help")
        assert result.returncode == StackExitCode.SUCCESS, result.stderr


@pytest.mark.parametrize("command", [PrepareCommand, RunReportCommand])
def test_a_whole_pass_command_takes_the_branch_whose_stack_it_passes_over(
    command: type[MaintenanceCommand],
):
    arguments = basstler.maintenance.__main__._argument_parser().parse_args(
        [command.invoked_as, "--stacked-on", StackBranch.CHILD]
    )

    assert arguments.stacked_on == StackBranch.CHILD


def test_a_run_needing_a_credential_it_has_not_got_is_its_own_exit_status(
    fork_checkout: ForkCheckout,
):
    """
    Distinguishable from a missing board, since the fix is a token rather than a fetch.
    """
    fork_checkout.run_git("remote", "remove", RemoteName.UPSTREAM)

    assert (
        run_maintenance(fork_checkout, BoardCommand()).returncode
        == StackExitCode.CREDENTIAL_UNAVAILABLE
    )


@dataclass(frozen=True)
class PassCountingItsExports(MaintenancePass):
    """
    A pass whose export is served from memory, counting how often it is asked for.
    """

    exported_pull_requests: tuple[PullRequest, ...] = ()
    """
    The pull requests every export returns.
    """

    exports_made: list[int] = dataclasses_field(default_factory=list)
    """
    One entry per export made.
    """

    def export_board(self) -> BoardExport:
        """
        :return: The recorded pull requests, counting the export.
        """
        self.exports_made.append(len(self.exports_made) + 1)
        return BoardExport(self.exported_pull_requests)


def test_each_stack_is_derived_from_an_export_made_for_it_never_from_the_board_file(
    fork_checkout: ForkCheckout, monkeypatch: pytest.MonkeyPatch
):
    """
    A board file left on disk by an earlier command may describe a stack that a push or a
    restack has since changed, so :meth:`MaintenancePass.fresh_stack` never reads it.
    """
    a_parent_and_child(fork_checkout)
    fork_checkout.name_the_upstream()
    monkeypatch.chdir(fork_checkout.project_root)
    board = fork_checkout.project_root / RepositoryStateLocation.BOARD.name
    board.write_text("not a board")
    maintenance = PassCountingItsExports(
        configuration=make_configuration(),
        git=fork_checkout.git,
        board=board,
        exported_pull_requests=tuple(the_board()),
    )

    maintenance.fresh_stack()
    maintenance.fresh_stack()

    assert len(maintenance.exports_made) == 2
    assert board.read_text() == "not a board"


@pytest.mark.parametrize(
    ("list_state", "states"),
    [
        (PullRequestListState.OPEN, (PullRequestState.OPEN,)),
        (PullRequestListState.CLOSED, (PullRequestState.CLOSED,)),
        (PullRequestListState.ALL, tuple(PullRequestState)),
    ],
)
def test_each_list_filter_names_the_pull_request_states_it_covers(
    list_state: PullRequestListState, states: tuple[PullRequestState, ...]
) -> None:
    assert list_state.states == states


@pytest.mark.parametrize(
    "list_state",
    [list_state for list_state in PullRequestListState if len(list_state.states) == 1],
)
def test_a_single_state_list_filter_asks_for_that_state(
    list_state: PullRequestListState,
) -> None:
    (state,) = list_state.states
    assert list_state.query == state.value


def test_a_board_whose_upstream_the_fork_s_action_cannot_read_is_its_own_exit_status(
    fork_checkout: ForkCheckout, monkeypatch: pytest.MonkeyPatch
):
    """
    The fork has no upstream-reviews Action branch, so the read never starts; the fix
    is installing or enabling the Action, not a token or a fetch.
    """
    fork_checkout.run_git("remote", "remove", RemoteName.UPSTREAM)
    fork_checkout.name_the_upstream()
    monkeypatch.chdir(fork_checkout.project_root)
    monkeypatch.setenv(GitHubCredentialVariable.GH_TOKEN, "a-token")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            basstler.maintenance.__main__.__name__,
            "--upstream-read",
            UpstreamReadRoute.ACTION,
            BoardCommand.invoked_as,
        ],
    )

    assert basstler.maintenance.__main__.main() is StackExitCode.UPSTREAM_UNREADABLE


# %% a repository naming no upstream


def a_checkout_naming_no_upstream(fork_checkout: ForkCheckout) -> ForkCheckout:
    """
    :param fork_checkout: The checkout to strip of its upstream.
    :return: The same checkout, with no upstream remote and no settings naming one, as a
        repository that is not a fork is.
    """
    fork_checkout.run_git("remote", "remove", RemoteName.UPSTREAM)
    return fork_checkout


@pytest.mark.parametrize("command", [BoardCommand, RestackCommand])
def test_a_command_in_a_repository_naming_no_upstream_runs_on_its_own_remote(
    fork_checkout: ForkCheckout,
    command: type[MaintenanceCommand],
):
    """
    No upstream is a supported setup, so each command goes on to ask for the credential
    it needs next rather than stopping for the upstream.
    """
    a_checkout_naming_no_upstream(fork_checkout)

    result = maintenance_runner(fork_checkout).run(command.invoked_as)

    assert result.returncode == StackExitCode.CREDENTIAL_UNAVAILABLE, result.stderr


def test_a_board_in_a_repository_naming_no_upstream_reads_no_upstream(
    fork_checkout: ForkCheckout, capsys: pytest.CaptureFixture[str]
):
    """
    The read would go through the fork's Action, which this fork has not got - so the
    board is only exported because nothing upstream is read.
    """
    configuration = make_own_remote_configuration()
    maintenance = MaintenancePass(
        configuration=configuration,
        git=fork_checkout.git,
        board=fork_checkout.project_root / RepositoryStateLocation.BOARD.name,
        upstream_read=UpstreamReadRoute.ACTION,
    )

    upstream_pull_requests = maintenance.upstream_pull_requests()

    assert upstream_pull_requests == UpstreamPullRequests(
        configuration.fork_repository, {}
    )
    assert MaintenanceNotice.NO_UPSTREAM in capsys.readouterr().err
