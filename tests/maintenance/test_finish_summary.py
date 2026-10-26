"""
Tests for the finish summary a whole pass prints: what it lists, and in what order.
"""

from __future__ import annotations

import argparse

import pytest

from basstler.github_labels import GitHubLabel
from basstler.maintenance.commands import RunReportCommand
from basstler.maintenance.exceptions import MarkdownLinkTargetError
from basstler.maintenance.fast_forward import FastForwardOutcome, FastForwardReport
from basstler.maintenance.finish_summary import (
    FinishSummary,
    FinishSummaryHeading,
    MarkdownLink,
)
from basstler.maintenance.promotion import Promotion, PromotionSummary
from basstler.maintenance.report import MaintenanceReport
from basstler.maintenance.restack_steps import BranchOutcome, RestackOutcome
from basstler.maintenance.upstream_pull_request_synchronization import (
    UpstreamPullRequestSynchronizationAction,
    UpstreamPullRequestSynchronizationChange,
)
from basstler.stack.model import (
    IntegrationStrategy,
    PullRequest,
    Reparent,
    SkippedPullRequest,
    SkipReason,
    Stack,
)
from basstler.stack.promotion_link import PromotionLink
from basstler.upstream_reviews.vocabulary import RollupState

from ..constants.paths import DatasetLocation
from ..constants.stack import StackBranch

from .fork import (
    A_SESSION_LINK,
    UPSTREAM_BASE,
    ForkCheckout,
    PromotionSampleText,
    PullRequestHeadRepository,
    StackPullRequestNumber,
    a_board_entry,
    a_parent_and_child,
    an_api_record,
    an_export,
    make_configuration,
    the_board,
)
from .recorded_fork import AlreadyResolvedPass


# %% the stack a summary is written about


def a_titled_stack(
    child_labels: list[str] | None = None,
    child_upstream_pull_request: int | None = None,
) -> Stack:
    """
    :param child_labels: The labels the child's pull request carries.
    :param child_upstream_pull_request: The open upstream pull request opened from the
        child.
    :return: The two-branch stack, with a title on the parent and a session link on the
        child, and nothing landed.
    """
    return Stack.build(
        make_configuration(),
        [
            a_board_entry(
                StackPullRequestNumber.PARENT,
                StackBranch.PARENT,
                UPSTREAM_BASE,
                title=PromotionSampleText.TITLE,
            ),
            a_board_entry(
                StackPullRequestNumber.CHILD,
                StackBranch.CHILD,
                StackBranch.PARENT,
                labels=child_labels or [],
                session=A_SESSION_LINK,
                upstream_pull_request=child_upstream_pull_request,
            ),
        ],
        lambda branch: False,
    )


def an_outcome(
    branch: str, outcome: RestackOutcome, **details: object
) -> BranchOutcome:
    """
    :param branch: The branch the outcome is about.
    :param outcome: What became of it.
    :param details: Any further :class:`BranchOutcome` fields.
    :return: The outcome, integrating the branch's parent by merge.
    """
    return BranchOutcome(
        branch, UPSTREAM_BASE, IntegrationStrategy.MERGE, outcome, **details
    )


def a_promotion(body_was_truncated: bool = False) -> Promotion:
    """
    :param body_was_truncated: Whether the prefilled description had to be shortened.
    :return: The parent's promotion, built this pass.
    """
    return Promotion(
        branch=StackBranch.PARENT,
        pull_request_number=StackPullRequestNumber.PARENT,
        url=PromotionSampleText.SECOND_LINK,
        body_was_truncated=body_was_truncated,
    )


def section_of(markdown: str, heading: FinishSummaryHeading) -> list[str]:
    """
    :param markdown: The whole summary.
    :param heading: The section to read.
    :return: The section's lines below its heading, empty when it is absent.
    """
    lines = markdown.splitlines()
    marker = FinishSummary.heading_line(heading)
    if marker not in lines:
        return []
    start = lines.index(marker) + 1
    following = [
        index
        for index, line in enumerate(lines[start:], start)
        if line.startswith(FinishSummary.heading_line(""))
    ]
    end = following[0] if following else len(lines)
    return [line for line in lines[start:end] if line]


# %% pending upstream links


def test_a_link_built_this_pass_names_its_number_title_branch_and_link():
    stack = a_titled_stack()
    summary = FinishSummary(MaintenanceReport(promoted=(a_promotion(),)), stack)

    (entry,) = section_of(summary.as_markdown(), FinishSummaryHeading.PENDING_LINKS)

    fork = stack.configuration.fork_repository
    assert entry == (
        f"- [#{StackPullRequestNumber.PARENT}]"
        f"({fork.pull_request_url(StackPullRequestNumber.PARENT)}) "
        f"{PromotionSampleText.TITLE} - `{StackBranch.PARENT}` - "
        f"[create upstream pull request]({PromotionSampleText.SECOND_LINK})"
    )


def test_a_link_sent_by_an_earlier_pass_and_not_yet_acted_on_is_listed_again():
    stack = a_titled_stack(child_labels=[GitHubLabel.PROMOTION_LINK_SENT])
    summary = FinishSummary(MaintenanceReport(), stack)

    (entry,) = section_of(summary.as_markdown(), FinishSummaryHeading.PENDING_LINKS)

    assert f"`{StackBranch.CHILD}`" in entry


def test_a_link_sent_by_an_earlier_pass_is_built_from_the_branch_not_its_description():
    """
    A description is free text: a heading of its own that starts like the promotion
    heading, a sentence or a code fence after it must never become a link target.
    """
    export = an_export(
        [
            an_api_record(
                number=StackPullRequestNumber.CHILD,
                head=StackBranch.CHILD,
                labels=[GitHubLabel.PROMOTION_LINK_SENT],
                body=DatasetLocation.DESCRIPTION_WITH_PROMOTION_PROSE.read_text(),
                title=PromotionSampleText.TITLE,
            )
        ]
    )
    stack = Stack.build(
        make_configuration(), list(export.pull_requests), lambda branch: False
    )

    (entry,) = section_of(
        FinishSummary(MaintenanceReport(), stack).as_markdown(),
        FinishSummaryHeading.PENDING_LINKS,
    )

    (branch,) = stack.branches
    expected = PromotionSummary().link_for(stack.configuration, branch, branch.title)
    assert entry.endswith(f"[create upstream pull request]({expected.url})")


def test_a_link_sent_earlier_that_is_now_in_review_is_not_pending():
    stack = a_titled_stack(
        child_labels=[GitHubLabel.PROMOTION_LINK_SENT],
        child_upstream_pull_request=StackPullRequestNumber.UPSTREAM,
    )
    summary = FinishSummary(MaintenanceReport(), stack)

    assert section_of(summary.as_markdown(), FinishSummaryHeading.PENDING_LINKS) == []


def test_a_shortened_prefill_also_gets_a_link_carrying_only_the_title():
    stack = a_titled_stack()
    summary = FinishSummary(
        MaintenanceReport(promoted=(a_promotion(body_was_truncated=True),)), stack
    )

    (entry,) = section_of(summary.as_markdown(), FinishSummaryHeading.PENDING_LINKS)

    title_only = PromotionLink.build(
        stack.configuration, StackBranch.PARENT, PromotionSampleText.TITLE, ""
    )
    assert entry.endswith(f"([title only]({title_only.url}))")


def test_the_pending_links_come_before_everything_else():
    stack = a_titled_stack()
    report = MaintenanceReport(
        restacked=(an_outcome(StackBranch.CHILD, RestackOutcome.PUSHED),),
        promoted=(a_promotion(),),
    )

    markdown = FinishSummary(report, stack).as_markdown()

    headings = [
        line
        for line in markdown.splitlines()
        if line.startswith(FinishSummary.heading_line(""))
    ]
    assert headings[0] == FinishSummary.heading_line(FinishSummaryHeading.PENDING_LINKS)


# %% markdown links


def test_a_link_target_that_is_neither_a_url_nor_an_anchor_is_refused():
    with pytest.raises(MarkdownLinkTargetError):
        MarkdownLink(
            "create upstream pull request", f"``{PromotionSampleText.FIRST_LINK}"
        )


@pytest.mark.parametrize(
    "target", [PromotionSampleText.FIRST_LINK, "#reported-to-their-owners"]
)
def test_a_url_or_an_anchor_is_a_link_target(target: str):
    assert str(MarkdownLink("label", target)) == f"[label]({target})"


# %% what the pass reported, withheld and skipped


def test_a_reported_branch_names_its_files_the_session_addressed_and_the_comment():
    comment = f"{PromotionSampleText.COMMENT_LINK_PREFIX}1"
    report = MaintenanceReport(
        restacked=(
            an_outcome(
                StackBranch.CHILD,
                RestackOutcome.CONFLICT,
                conflicting_paths=("a.py", "b.py"),
                reported_at=comment,
            ),
        )
    )

    (entry,) = section_of(
        FinishSummary(report, a_titled_stack()).as_markdown(),
        FinishSummaryHeading.REPORTED,
    )

    assert "`a.py`, `b.py`" in entry
    assert A_SESSION_LINK in entry
    assert entry.endswith(f"[comment]({comment})")


def test_a_conflict_in_many_files_names_only_the_first_few():
    """
    The comment the branch's owner reads lists every file; the summary only has to say
    there are more.
    """
    limit = FinishSummary.listed_path_limit
    paths = tuple(f"file-{index}.py" for index in range(limit + 3))
    report = MaintenanceReport(
        restacked=(
            an_outcome(
                StackBranch.CHILD,
                RestackOutcome.CONFLICT,
                conflicting_paths=paths,
                reported_at=f"{PromotionSampleText.COMMENT_LINK_PREFIX}1",
            ),
        )
    )

    (entry,) = section_of(
        FinishSummary(report, a_titled_stack()).as_markdown(),
        FinishSummaryHeading.REPORTED,
    )

    named = ", ".join(f"`{path}`" for path in paths[:limit])
    assert f"conflicts in {named} and 3 more - " in entry
    assert paths[limit] not in entry


def test_a_long_withheld_list_names_only_the_first_few():
    limit = FinishSummary.listed_branch_limit
    branches = [f"branch-{index}" for index in range(limit + 2)]
    report = MaintenanceReport(
        restacked=tuple(
            an_outcome(branch, RestackOutcome.WITHHELD) for branch in branches
        )
    )

    section = section_of(
        FinishSummary(report, a_titled_stack()).as_markdown(),
        FinishSummaryHeading.WITHHELD,
    )

    named = ", ".join(f"`{branch}`" for branch in branches[:limit])
    assert section == [f"{named} and 2 more"]


def test_each_upstream_pull_request_synchronization_change_names_its_pull_request_and_what_was_done():
    report = MaintenanceReport(
        upstream_pull_request_synchronization_changes=(
            UpstreamPullRequestSynchronizationChange(
                StackBranch.PARENT,
                StackPullRequestNumber.PARENT,
                UpstreamPullRequestSynchronizationAction.LABEL_ADDED,
            ),
            UpstreamPullRequestSynchronizationChange(
                StackBranch.CHILD,
                StackPullRequestNumber.CHILD,
                UpstreamPullRequestSynchronizationAction.LABEL_REMOVED,
            ),
        )
    )
    summary = FinishSummary(report, a_titled_stack())

    section = section_of(
        summary.as_markdown(),
        FinishSummaryHeading.UPSTREAM_PULL_REQUEST_SYNCHRONIZATION,
    )

    parent, child = summary.stack.branches
    assert section == [
        f"{summary.branch_line(parent)}: {UpstreamPullRequestSynchronizationAction.LABEL_ADDED}",
        f"{summary.branch_line(child)}: {UpstreamPullRequestSynchronizationAction.LABEL_REMOVED}",
    ]


def test_a_branch_whose_checks_failed_is_listed_as_withheld_from_promotion():
    stack = Stack.build(
        make_configuration(),
        [
            a_board_entry(
                StackPullRequestNumber.PARENT,
                StackBranch.PARENT,
                UPSTREAM_BASE,
                check_state=RollupState.FAILURE,
            )
        ],
        lambda branch: False,
    )
    summary = FinishSummary(MaintenanceReport(), stack)

    section = section_of(summary.as_markdown(), FinishSummaryHeading.FAILING_CHECKS)

    assert section == [
        f"{summary.branch_line(stack.branches[0])}: {RollupState.FAILURE}"
    ]


def test_every_withheld_branch_shares_one_line():
    report = MaintenanceReport(
        restacked=(
            an_outcome(StackBranch.PARENT, RestackOutcome.WITHHELD),
            an_outcome(StackBranch.CHILD, RestackOutcome.WITHHELD),
        )
    )

    section = section_of(
        FinishSummary(report, a_titled_stack()).as_markdown(),
        FinishSummaryHeading.WITHHELD,
    )

    assert section == [f"`{StackBranch.PARENT}`, `{StackBranch.CHILD}`"]


def test_branches_already_up_to_date_are_counted_rather_than_listed():
    report = MaintenanceReport(
        restacked=(
            an_outcome(StackBranch.PARENT, RestackOutcome.UP_TO_DATE),
            an_outcome(StackBranch.CHILD, RestackOutcome.PUSHED, pushed_commit="abc"),
        )
    )

    section = section_of(
        FinishSummary(report, a_titled_stack()).as_markdown(),
        FinishSummaryHeading.RESTACKED,
    )

    assert len(section) == 2
    assert f"`{StackBranch.CHILD}`" in section[0]
    assert StackBranch.PARENT not in section[1]


def test_a_reparent_still_to_make_names_both_bases():
    stack = a_titled_stack()
    reparent = Reparent(
        StackBranch.CHILD,
        StackPullRequestNumber.CHILD,
        StackBranch.PARENT,
        UPSTREAM_BASE,
    )

    (entry,) = section_of(
        FinishSummary(MaintenanceReport(reparents=(reparent,)), stack).as_markdown(),
        FinishSummaryHeading.REPARENTS,
    )

    assert entry.endswith(f"`{StackBranch.PARENT}` -> `{UPSTREAM_BASE}`")


def test_a_skipped_pull_request_names_its_reason_and_where_its_head_lives():
    other_fork = PullRequestHeadRepository.ANOTHER_CONTRIBUTORS_FORK.value.full_name
    skipped = SkippedPullRequest(
        PullRequest(
            number=StackPullRequestNumber.ON_ANOTHER_FORK,
            head=StackBranch.ON_ANOTHER_FORK,
            base=StackBranch.PARENT,
            draft=False,
            head_repository=other_fork,
        ),
        SkipReason.HEAD_ON_ANOTHER_FORK,
    )

    (entry,) = section_of(
        FinishSummary(
            MaintenanceReport(skipped=(skipped,)), a_titled_stack()
        ).as_markdown(),
        FinishSummaryHeading.SKIPPED,
    )

    assert SkipReason.HEAD_ON_ANOTHER_FORK in entry
    assert other_fork in entry


def test_a_refused_fast_forward_is_explained():
    explanation = "the fork's base has commits the upstream does not"
    report = MaintenanceReport(
        fast_forward=FastForwardReport(
            FastForwardOutcome.REFUSED_NOT_FAST_FORWARD,
            "upstream/main",
            "origin/main",
            "a-commit",
            explanation,
        )
    )

    section = section_of(
        FinishSummary(report, a_titled_stack()).as_markdown(),
        FinishSummaryHeading.FORK_BASE,
    )

    assert FastForwardOutcome.REFUSED_NOT_FAST_FORWARD in section[0]
    assert section[1] == explanation


def test_the_status_is_followed_by_every_section_and_its_count():
    """
    A reader who only needs the outcome can stop after the first lines.
    """
    report = MaintenanceReport(
        restacked=(
            an_outcome(StackBranch.PARENT, RestackOutcome.UP_TO_DATE),
            an_outcome(StackBranch.CHILD, RestackOutcome.PUSHED, pushed_commit="abc"),
        ),
        promoted=(a_promotion(),),
    )

    lines = FinishSummary(report, a_titled_stack()).as_markdown().splitlines()

    assert lines[0].endswith(report.exit_code.name_for_a_caller)
    assert lines[2] == (
        f"**Sections:** {FinishSummaryHeading.PENDING_LINKS} (1); "
        f"{FinishSummaryHeading.RESTACKED} (2)"
    )


def test_a_pass_that_did_nothing_still_says_its_status():
    report = MaintenanceReport()

    markdown = FinishSummary(report, a_titled_stack()).as_markdown()

    assert markdown.splitlines()[0].endswith(report.exit_code.name_for_a_caller)


# %% the command


def test_a_whole_pass_prints_the_finish_summary(
    fork_checkout: ForkCheckout, capsys: pytest.CaptureFixture[str]
):
    a_parent_and_child(fork_checkout)
    maintenance = AlreadyResolvedPass.over(fork_checkout, the_board())

    RunReportCommand().run(maintenance, argparse.Namespace(json=False, summaries=None))

    printed = capsys.readouterr().out.splitlines()
    assert FinishSummary.heading_line(FinishSummaryHeading.RESTACKED) in printed
