"""
Tests for reading and reporting the checks on branches a pass pushed, against a real
scratch fork.
"""

from __future__ import annotations

import pytest

from basstler.exit_codes import StackExitCode
from basstler.maintenance.check_results import CheckResult, CheckState, CommitChecks
from basstler.maintenance.commands import RunReportCommand
from basstler.maintenance.constants import MaintenanceText
from basstler.maintenance.finish_summary import FinishSummaryHeading
from basstler.maintenance.promotion import PromotionSummaries
from basstler.maintenance.pushed_branch_checks import (
    BranchChecks,
    PushedBranchChecks,
)
from basstler.maintenance.restack_procedure import restack
from basstler.stack.label_write import LabelWrite
from basstler.stack.model import Stack

from ..constants.stack import RemoteName, StackBranch, StackLabel

from .fork import (
    A_SESSION_LINK,
    UPSTREAM_BASE,
    ForkCheckout,
    StackPullRequestNumber,
    a_board_entry,
    a_parent_and_child,
    a_stack,
)
from .recorded_fork import AlreadyResolvedPass, RecordingPullRequests
from .test_finish_summary import section_of

FAILING_CHECK = CheckResult("pytest", CheckState.FAILING)
"""
The check a failing tip reports as failed.
"""

PASSING_CHECK = CheckResult("lint", CheckState.PASSING)
"""
A check every tip reports as passed.
"""


# %% a stack whose child a pass has pushed


def a_board_with_a_session() -> list:
    """
    :return: The two-branch board, the child's description naming a session.
    """
    return [
        a_board_entry(StackPullRequestNumber.PARENT, StackBranch.PARENT, UPSTREAM_BASE),
        a_board_entry(
            StackPullRequestNumber.CHILD,
            StackBranch.CHILD,
            StackBranch.PARENT,
            session=A_SESSION_LINK,
        ),
    ]


def a_child_restacked_by_a_pass(fork_checkout: ForkCheckout) -> Stack:
    """
    Move the parent and restack, so the child's tip on the fork is a restack merge.

    :param fork_checkout: The checkout to build the stack in.
    :return: The stack, as the next pass derives it.
    """
    a_parent_and_child(fork_checkout)
    fork_checkout.commit_on(StackBranch.PARENT, "a-later-file", "the parent moved\n")
    restack(
        a_stack(fork_checkout, a_board_with_a_session()),
        fork_checkout.git,
        RecordingPullRequests(),
    )
    return a_stack(fork_checkout, a_board_with_a_session())


def checks_on_the_child_tip(
    fork_checkout: ForkCheckout, *results: CheckResult
) -> CommitChecks:
    """
    :param fork_checkout: The checkout the child was restacked in.
    :param results: The checks to report on its tip.
    :return: Those checks, on the child's tip on the fork.
    """
    return CommitChecks(
        fork_checkout.published_commit(RemoteName.ORIGIN, StackBranch.CHILD), results
    )


# %% reading


def test_only_a_branch_whose_tip_a_pass_pushed_is_read(fork_checkout: ForkCheckout):
    stack = a_child_restacked_by_a_pass(fork_checkout)
    checks = checks_on_the_child_tip(fork_checkout, PASSING_CHECK)
    fork = RecordingPullRequests(checks={checks.commit: checks})

    read = PushedBranchChecks(stack, fork_checkout.git, fork).read(stack.branches)

    assert read == [
        BranchChecks(StackBranch.CHILD, StackPullRequestNumber.CHILD, checks)
    ]


# %% reporting


def test_failing_checks_label_the_branch_and_name_the_checks_in_one_comment(
    fork_checkout: ForkCheckout,
):
    stack = a_child_restacked_by_a_pass(fork_checkout)
    checks = checks_on_the_child_tip(fork_checkout, FAILING_CHECK, PASSING_CHECK)
    fork = RecordingPullRequests(checks={checks.commit: checks})
    reader = PushedBranchChecks(stack, fork_checkout.git, fork)

    (reported,) = reader.report_failures(reader.read(stack.branches))

    (comment,) = fork.comments
    assert comment.pull_request_number == StackPullRequestNumber.CHILD
    assert comment.body == reported.failure_report(A_SESSION_LINK)
    assert reported.reported_at is not None
    assert [write.labels for write in fork.label_writes] == [
        LabelWrite.replacing([], added=[StackLabel.NEEDS_RESOLUTION]).labels
    ]


def test_a_failing_tip_already_reported_is_not_commented_on_again(
    fork_checkout: ForkCheckout,
):
    stack = a_child_restacked_by_a_pass(fork_checkout)
    checks = checks_on_the_child_tip(fork_checkout, FAILING_CHECK)
    earlier = BranchChecks(StackBranch.CHILD, StackPullRequestNumber.CHILD, checks)
    fork = RecordingPullRequests(
        checks={checks.commit: checks},
        labels={StackPullRequestNumber.CHILD: [StackLabel.NEEDS_RESOLUTION]},
        earlier_comments={
            StackPullRequestNumber.CHILD: [earlier.failure_report(A_SESSION_LINK)]
        },
    )
    reader = PushedBranchChecks(stack, fork_checkout.git, fork)

    (reported,) = reader.report_failures(reader.read(stack.branches))

    assert fork.comments == []
    assert fork.label_writes == []
    assert reported.reported_at is None


@pytest.mark.parametrize("result", [PASSING_CHECK, CheckResult("docs", CheckState.PENDING)])
def test_checks_that_do_not_fail_are_reported_to_nobody(
    fork_checkout: ForkCheckout, result: CheckResult
):
    stack = a_child_restacked_by_a_pass(fork_checkout)
    checks = checks_on_the_child_tip(fork_checkout, result)
    fork = RecordingPullRequests(checks={checks.commit: checks})
    reader = PushedBranchChecks(stack, fork_checkout.git, fork)

    reader.report_failures(reader.read(stack.branches))

    assert fork.comments == []
    assert fork.label_writes == []


def test_the_failure_report_opens_with_the_prefix_and_names_the_tip():
    checks = CommitChecks("a-commit", (FAILING_CHECK,))

    body = BranchChecks(
        StackBranch.CHILD, StackPullRequestNumber.CHILD, checks
    ).failure_report(None)

    assert body.startswith(MaintenanceText.NEEDS_RESOLUTION_COMMENT_PREFIX)
    assert checks.commit in body
    assert f"`{FAILING_CHECK.check_name}`" in body


# %% the whole pass


def test_a_pass_reports_the_failing_checks_an_earlier_pass_left_behind(
    fork_checkout: ForkCheckout, capsys: pytest.CaptureFixture[str]
):
    a_child_restacked_by_a_pass(fork_checkout)
    checks = checks_on_the_child_tip(fork_checkout, FAILING_CHECK)
    maintenance = AlreadyResolvedPass.over(fork_checkout, a_board_with_a_session())
    maintenance.recorded_fork.checks[checks.commit] = checks

    report = RunReportCommand().perform(
        maintenance, as_json=False, summaries=PromotionSummaries()
    )

    assert [branch_checks.branch for branch_checks in report.failing_checks] == [
        StackBranch.CHILD
    ]
    assert report.exit_code is StackExitCode.BRANCH_NEEDS_ATTENTION
    (entry,) = section_of(capsys.readouterr().out, FinishSummaryHeading.FAILING_CHECKS)
    assert f"`{FAILING_CHECK.check_name}`" in entry


def test_a_pass_does_not_read_checks_on_what_it_pushed_itself(
    fork_checkout: ForkCheckout,
):
    """
    A tip pushed a moment ago is still being checked, so reading it would only report
    it as running; the next pass reads it once it has finished.
    """
    a_parent_and_child(fork_checkout)
    fork_checkout.commit_on(StackBranch.PARENT, "a-later-file", "the parent moved\n")
    maintenance = AlreadyResolvedPass.over(fork_checkout, a_board_with_a_session())

    report = RunReportCommand().perform(
        maintenance, as_json=False, summaries=PromotionSummaries()
    )

    assert report.checks == ()
