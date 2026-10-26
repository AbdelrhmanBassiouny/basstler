"""
The finish summary a whole pass prints: what it left for its developer, in markdown.
"""

from __future__ import annotations

import functools
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlsplit

from basstler.class_property import classproperty
from basstler.github_labels import GitHubLabel
from basstler.maintenance.exceptions import MarkdownLinkTargetError
from basstler.maintenance.promotion import PromotionSummary
from basstler.maintenance.report import MaintenanceReport
from basstler.maintenance.restack_steps import BranchOutcome, RestackOutcome
from basstler.render_common import AllowedUrlScheme
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

    LINK_LABELS_CLEARED = "Spent link labels removed"
    """
    The branches whose link label was dropped because the link was acted on.
    """

    SKIPPED = "Skipped"
    """
    The pull requests whose head the pass cannot maintain.
    """


# %% markdown


@dataclass(frozen=True)
class MarkdownLink:
    """
    A markdown link whose target is a web URL or an anchor on the same page.
    """

    label: str
    """
    The text the link shows.
    """

    target: str
    """
    What the link points at.
    """

    def __post_init__(self) -> None:
        """
        :raises MarkdownLinkTargetError: If the target is neither a web URL nor an
            anchor, or holds whitespace, which ends a markdown link target early.
        """
        if any(character.isspace() for character in self.target):
            raise MarkdownLinkTargetError(self.label, self.target)
        if self.target.startswith("#") and len(self.target) > 1:
            return
        parts = urlsplit(self.target)
        if parts.scheme not in set(AllowedUrlScheme) or not parts.netloc:
            raise MarkdownLinkTargetError(self.label, self.target)

    def __str__(self) -> str:
        """:return: The link, as markdown."""
        return f"[{self.label}]({self.target})"


@dataclass(frozen=True)
class SummarySection:
    """
    One section of the finish summary, and how many things it is about.
    """

    heading: FinishSummaryHeading
    """
    What the section is.
    """

    lines: list[str]
    """
    Its lines below the heading, empty when it has nothing to say.
    """

    item_count: int
    """
    How many branches or pull requests it is about, which a capped list prints fewer of.
    """

    @classmethod
    def of_entries(
        cls, heading: FinishSummaryHeading, lines: list[str]
    ) -> SummarySection:
        """
        :param heading: What the section is.
        :param lines: One line per item.
        :return: The section, counting one item per line.
        """
        return cls(heading, lines, len(lines))

    @property
    def overview_entry(self) -> str:
        """
        The section's heading and count, as the overview line lists it.
        """
        return f"{self.heading} ({self.item_count})"


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

    @classproperty
    def listed_path_limit(cls) -> int:
        """
        How many conflicting files one entry names before counting the rest, which its
        comment lists in full.
        """
        return 5

    @classproperty
    def listed_branch_limit(cls) -> int:
        """
        How many branches a one-line list names before counting the rest.
        """
        return 10

    @staticmethod
    def heading_line(heading: str) -> str:
        """
        :param heading: The section's heading.
        :return: The markdown line opening that section.
        """
        return f"### {heading}"

    @staticmethod
    def abbreviated(items: Sequence[str], limit: int) -> str:
        """
        :param items: Things to list on one line.
        :param limit: How many of them to name.
        :return: The first *limit* of them, then how many more there are.
        """
        named = ", ".join(items[:limit])
        remaining = len(items) - limit
        return f"{named} and {remaining} more" if remaining > 0 else named

    @functools.cached_property
    def branches_by_name(self) -> dict[str, Branch]:
        """
        The stack's branches, by the name a report entry refers to them by.
        """
        return {branch.name: branch for branch in self.stack.branches}

    def sections(self) -> list[SummarySection]:
        """
        :return: Every section that has something in it, in the order of
            :class:`FinishSummaryHeading`.
        """
        restacked = self.restacked()
        withheld = self.branches_with(RestackOutcome.WITHHELD)
        cleared = self.report.promotion_labels_cleared
        sections = [
            SummarySection.of_entries(
                FinishSummaryHeading.PENDING_LINKS, self.pending_links()
            ),
            SummarySection.of_entries(FinishSummaryHeading.REPORTED, self.reported()),
            SummarySection.of_entries(FinishSummaryHeading.REPARENTS, self.reparents()),
            SummarySection(FinishSummaryHeading.FORK_BASE, self.fork_base(), 1),
            SummarySection.of_entries(FinishSummaryHeading.LANDED, self.landed()),
            SummarySection(
                FinishSummaryHeading.RESTACKED,
                restacked,
                sum(
                    outcome.outcome
                    in {RestackOutcome.PUSHED, RestackOutcome.UP_TO_DATE}
                    for outcome in self.report.restacked
                ),
            ),
            SummarySection.of_entries(
                FinishSummaryHeading.UNPUBLISHED, self.unpublished()
            ),
            SummarySection(
                FinishSummaryHeading.WITHHELD, self.code_list(withheld), len(withheld)
            ),
            SummarySection(
                FinishSummaryHeading.LINK_LABELS_CLEARED,
                self.code_list(cleared),
                len(cleared),
            ),
            SummarySection.of_entries(FinishSummaryHeading.SKIPPED, self.skipped()),
        ]
        return [section for section in sections if section.lines]

    def as_markdown(self) -> str:
        """
        :return: The status, then one line naming every section with something in it
            and how many items each holds, then those sections.
        """
        sections = self.sections()
        lines = [f"**Maintenance pass:** {self.report.exit_code.name_for_a_caller}"]
        if sections:
            overview = "; ".join(section.overview_entry for section in sections)
            lines += ["", f"**Sections:** {overview}"]
        for section in sections:
            lines += ["", self.heading_line(section.heading), "", *section.lines]
        return "\n".join(lines)

    def pull_request_link(self, number: int) -> str:
        """
        :param number: A fork pull request.
        :return: A markdown link to it, labelled by its number.
        """
        url = self.stack.configuration.fork_repository.pull_request_url(number)
        return str(MarkdownLink(f"#{number}", url))

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
            earlier pass built that is not yet acted on, built again from its branch
            with no summary.
        """
        entries = []
        for promotion in self.report.promoted:
            branch = self.branches_by_name[promotion.branch]
            entry = f"{self.branch_line(branch)} - {self.create_link(promotion.url)}"
            if promotion.body_was_truncated:
                title_only = MarkdownLink("title only", self.title_only_link(branch))
                entry += f" ({title_only})"
            entries.append(entry)
        promoted = {promotion.branch for promotion in self.report.promoted}
        for branch in self.stack.maintained_branches():
            if (
                branch.name in promoted
                or GitHubLabel.PROMOTION_LINK_SENT not in branch.labels
                or branch.status in {BranchStatus.IN_REVIEW, BranchStatus.MERGED}
            ):
                continue
            link = PromotionSummary().link_for(
                self.stack.configuration, branch, branch.title
            )
            entries.append(f"{self.branch_line(branch)} - {self.create_link(link.url)}")
        return entries

    @staticmethod
    def create_link(url: str) -> MarkdownLink:
        """
        :param url: A compare-and-create URL.
        :return: The link opening the upstream pull request it prefills.
        """
        return MarkdownLink("create upstream pull request", url)

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
                f"addressed {addressed} - "
                f"{MarkdownLink('comment', outcome.reported_at)}"
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

    def outcome_detail(self, outcome: BranchOutcome) -> str:
        """
        :param outcome: What became of a branch the pass could not publish.
        :return: The files, refusals or explanation its owner, or the pass, acts on;
            only the first :attr:`listed_path_limit` conflicting files.
        """
        if outcome.conflicting_paths:
            return "conflicts in " + self.abbreviated(
                [f"`{path}`" for path in outcome.conflicting_paths],
                self.listed_path_limit,
            )
        if outcome.refusals:
            return ", ".join(outcome.refusals)
        if outcome.outcome is RestackOutcome.INTEGRATION_FAILED:
            return f"the pass's own environment, not the branch: {outcome.explanation}"
        return outcome.explanation or ""

    def branches_with(self, outcome: RestackOutcome) -> list[str]:
        """
        :param outcome: The outcome to collect.
        :return: Every branch that had it.
        """
        return [
            entry.branch for entry in self.report.restacked if entry.outcome is outcome
        ]

    def code_list(self, names: Sequence[str]) -> list[str]:
        """
        :param names: Branch names.
        :return: The first :attr:`listed_branch_limit` of them on one line, empty when
            there are none.
        """
        if not names:
            return []
        return [
            self.abbreviated([f"`{name}`" for name in names], self.listed_branch_limit)
        ]

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
