"""
The finish summary a whole pass prints: what it left for its developer, in markdown.
"""

from __future__ import annotations

import functools
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from basstler.github_labels import GitHubLabel
from basstler.maintenance.report import MaintenanceReport
from basstler.maintenance.restack_steps import BranchOutcome, RestackOutcome
from basstler.stack.model import Branch, BranchStatus, Stack
from basstler.stack.promotion_link import PromotionLink

# %% vocabulary


class FinishSummaryHeading(StrEnum):
    """
    The sections of the finish summary, in the order it prints them.
    """

    PENDING_LINKS = "Upstream pull requests waiting to be created"
    """
    Every create-link not yet acted on, built this pass or an earlier one.
    """

    REPORTED = "Reported to their owners"
    """
    The branches whose owner was told, in a comment, that their branch needs them.
    """

    REPARENTS = "Reparents still to make"
    """
    The pull requests whose base has landed and still has to be retargeted.
    """

    FORK_BASE = "The fork's base"
    """
    What became of the fork's base branch.
    """

    LANDED = "Landed but still open"
    """
    The pull requests whose commits are already in the upstream base.
    """

    RESTACKED = "Restacked"
    """
    The branches published, and how many were already up to date.
    """

    UNPUBLISHED = "Left unpublished"
    """
    The branches the pass could not publish and told nobody about.
    """

    WITHHELD = "Withheld"
    """
    The branches still conflicted from an earlier pass, left untouched.
    """

    FAILING_CHECKS = "Withheld for failing checks"
    """
    The approved branches promotion would take but for their failed checks.
    """

    LINK_LABELS_CLEARED = "Spent link labels removed"
    """
    The branches whose link label was dropped because the link was acted on.
    """

    REVIEW_MIRROR = "In-review labels and upstream links updated"
    """
    The pull requests whose in-review label or upstream link was written to match the
    upstream.
    """

    SKIPPED = "Skipped"
    """
    The pull requests whose head the pass cannot maintain.
    """


# %% the summary


@dataclass(frozen=True)
class FinishSummary:
    """
    One pass's report, written for the developer who reads it once.
    """

    report: MaintenanceReport
    """
    What the pass did.
    """

    stack: Stack
    """
    The stack the pass ran over, read for each pull request's number, title and session.
    """

    @staticmethod
    def heading_line(heading: str) -> str:
        """
        :param heading: The section's heading.
        :return: The markdown line opening that section.
        """
        return f"### {heading}"

    @functools.cached_property
    def branches_by_name(self) -> dict[str, Branch]:
        """
        The stack's branches, by the name a report entry refers to them by.
        """
        return {branch.name: branch for branch in self.stack.branches}

    def as_markdown(self) -> str:
        """
        :return: The status, then every section that has something in it, in the order
            of :class:`FinishSummaryHeading`.
        """
        sections = {
            FinishSummaryHeading.PENDING_LINKS: self.pending_links(),
            FinishSummaryHeading.REPORTED: self.reported(),
            FinishSummaryHeading.REPARENTS: self.reparents(),
            FinishSummaryHeading.FORK_BASE: self.fork_base(),
            FinishSummaryHeading.LANDED: self.landed(),
            FinishSummaryHeading.RESTACKED: self.restacked(),
            FinishSummaryHeading.UNPUBLISHED: self.unpublished(),
            FinishSummaryHeading.WITHHELD: self.branch_list(RestackOutcome.WITHHELD),
            FinishSummaryHeading.FAILING_CHECKS: self.failing_checks(),
            FinishSummaryHeading.LINK_LABELS_CLEARED: self.code_list(
                self.report.promotion_labels_cleared
            ),
            FinishSummaryHeading.REVIEW_MIRROR: self.review_mirror_changes(),
            FinishSummaryHeading.SKIPPED: self.skipped(),
        }
        lines = [f"**Maintenance pass:** {self.report.exit_code.name_for_a_caller}"]
        for heading, entries in sections.items():
            if entries:
                lines += ["", self.heading_line(heading), "", *entries]
        return "\n".join(lines)

    def pull_request_link(self, number: int) -> str:
        """
        :param number: A fork pull request.
        :return: A markdown link to it, labelled by its number.
        """
        url = self.stack.configuration.fork_repository.pull_request_url(number)
        return f"[#{number}]({url})"

    def branch_line(self, branch: Branch) -> str:
        """
        :param branch: A branch of the stack.
        :return: Its pull request, title and name, as an entry opens.
        """
        return (
            f"- {self.pull_request_link(branch.pull_request_number)} "
            f"{branch.title or branch.name} - `{branch.name}`"
        )

    def title_only_link(self, branch: Branch) -> str:
        """
        :param branch: A branch to promote.
        :return: The create-link prefilling only its title.
        """
        return PromotionLink.build(
            self.stack.configuration, branch.name, branch.title or branch.name, ""
        ).url

    def pending_links(self) -> list[str]:
        """
        :return: One entry per create-link built this pass, then one per link an
            earlier pass built that is not yet acted on.
        """
        entries = []
        for promotion in self.report.promoted:
            branch = self.branches_by_name[promotion.branch]
            entry = (
                f"{self.branch_line(branch)} - "
                f"[create upstream pull request]({promotion.url})"
            )
            if promotion.body_was_truncated:
                entry += f" ([title only]({self.title_only_link(branch)}))"
            entries.append(entry)
        promoted = {promotion.branch for promotion in self.report.promoted}
        for branch in self.stack.maintained_branches():
            if (
                branch.name in promoted
                or GitHubLabel.PROMOTION_LINK_SENT not in branch.labels
                or branch.status in {BranchStatus.IN_REVIEW, BranchStatus.MERGED}
            ):
                continue
            url = branch.promotion_link or self.title_only_link(branch)
            entries.append(
                f"{self.branch_line(branch)} - [create upstream pull request]({url})"
            )
        return entries

    def reported(self) -> list[str]:
        """
        :return: One entry per branch whose owner was told about it in a comment.
        """
        entries = []
        for outcome in self.report.restacked:
            if outcome.reported_at is None:
                continue
            branch = self.branches_by_name[outcome.branch]
            addressed = branch.session or "the description names no session"
            entries.append(
                f"{self.branch_line(branch)}: {self.outcome_detail(outcome)} - "
                f"addressed {addressed} - [comment]({outcome.reported_at})"
            )
        return entries

    def reparents(self) -> list[str]:
        """
        :return: One entry per pull request still to retarget, from base to base.
        """
        return [
            f"- {self.pull_request_link(reparent.pull_request_number)} "
            f"`{reparent.branch}`: `{reparent.current_base}` -> `{reparent.target_base}`"
            for reparent in self.report.reparents
        ]

    def fork_base(self) -> list[str]:
        """
        :return: What became of the fork's base, and why when it was refused.
        """
        report = self.report.fast_forward
        if report is None:
            return []
        lines = [f"`{report.fork_reference}`: {report.outcome} at `{report.commit}`"]
        return lines + ([report.explanation] if report.explanation else [])

    def landed(self) -> list[str]:
        """
        :return: One entry per landed branch whose pull request is still open.
        """
        return [
            self.branch_line(self.branches_by_name[name]) for name in self.report.landed
        ]

    def restacked(self) -> list[str]:
        """
        :return: One entry per branch published, then how many were already up to date.
        """
        entries = [
            f"{self.branch_line(self.branches_by_name[outcome.branch])}: pushed "
            f"`{outcome.pushed_commit}`"
            for outcome in self.report.restacked
            if outcome.outcome is RestackOutcome.PUSHED
        ]
        up_to_date = sum(
            outcome.outcome is RestackOutcome.UP_TO_DATE
            for outcome in self.report.restacked
        )
        return entries + ([f"{up_to_date} already up to date"] if up_to_date else [])

    def unpublished(self) -> list[str]:
        """
        :return: One entry per branch left unpublished that no comment told anyone
            about.
        """
        return [
            f"{self.branch_line(self.branches_by_name[outcome.branch])}: "
            f"{outcome.outcome} - {self.outcome_detail(outcome)}"
            for outcome in self.report.branches_left_unpublished
            if outcome.reported_at is None
            and outcome.outcome is not RestackOutcome.WITHHELD
        ]

    @staticmethod
    def outcome_detail(outcome: BranchOutcome) -> str:
        """
        :param outcome: What became of a branch the pass could not publish.
        :return: The files, refusals or explanation its owner, or the pass, acts on.
        """
        if outcome.conflicting_paths:
            return "conflicts in " + ", ".join(
                f"`{path}`" for path in outcome.conflicting_paths
            )
        if outcome.refusals:
            return ", ".join(outcome.refusals)
        if outcome.outcome is RestackOutcome.INTEGRATION_FAILED:
            return f"the pass's own environment, not the branch: {outcome.explanation}"
        return outcome.explanation or ""

    def failing_checks(self) -> list[str]:
        """
        :return: One entry per approved branch withheld for its failed checks, with the
            verdict over them.
        """
        return [
            f"{self.branch_line(branch)}: {branch.check_state}"
            for branch in self.stack.withheld_by_failing_checks()
        ]

    def review_mirror_changes(self) -> list[str]:
        """
        :return: One entry per in-review label or upstream link written.
        """
        return [
            f"{self.branch_line(self.branches_by_name[change.branch])}: {change.action}"
            for change in self.report.review_mirror_changes
        ]

    def branch_list(self, outcome: RestackOutcome) -> list[str]:
        """
        :param outcome: The outcome to collect.
        :return: Every branch that had it, on one line.
        """
        return self.code_list(
            [
                entry.branch
                for entry in self.report.restacked
                if entry.outcome is outcome
            ]
        )

    @staticmethod
    def code_list(names: Sequence[str]) -> list[str]:
        """
        :param names: Branch names.
        :return: All of them on one line, empty when there are none.
        """
        return [", ".join(f"`{name}`" for name in names)] if names else []

    def skipped(self) -> list[str]:
        """
        :return: One entry per pull request the pass left alone, with why and where its
            head lives.
        """
        entries = []
        for skipped in self.report.skipped:
            pull_request = skipped.pull_request
            where = pull_request.head_repository or "deleted"
            entries.append(
                f"- {self.pull_request_link(pull_request.number)} "
                f"`{pull_request.head}`: {skipped.reason} ({where})"
            )
        return entries
