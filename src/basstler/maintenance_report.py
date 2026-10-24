"""
What a pass did, as a document, as printed lines, and as an exit status.

Every command that produces a report derives its status through the same function, so no
two can disagree about what a clean pass is - a refused fast-forward reported as success
is exactly the silence this exists to prevent.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from basstler.exit_codes import StackExitCode
from basstler.maintenance_board import BoardExport
from basstler.maintenance_fast_forward import FastForwardOutcome, FastForwardReport
from basstler.maintenance_promotion import Promotion
from basstler.maintenance_restack_steps import BranchOutcome, RestackOutcome
from basstler.stack import Reparent, Stack
from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""

# %% the report a caller renders or emits


@dataclass(frozen=True)
class MaintenanceReport:
    """
    Everything one pass did, and the one thing it leaves for its caller.

    ``reparents`` is that one thing: retargeting a base is the single write GitHub
    refuses to the credential this runs on, so it is reported rather than performed.

    Every field defaults to nothing done, so a single command reports the part of the
    pass it performed through the same object - and therefore through the same exit
    status - as a whole pass does.
    """

    fast_forward: FastForwardReport | None = None
    """
    What became of the fork's base branch, absent when it was not attempted.
    """

    restacked: tuple[BranchOutcome, ...] = ()
    """
    What became of each branch in the restack plan.
    """

    promoted: tuple[Promotion, ...] = ()
    """
    The branches whose upstream link was built and recorded this pass.
    """

    promotion_labels_cleared: tuple[str, ...] = ()
    """
    The branches whose spent link label was removed this pass.
    """

    reparents: tuple[Reparent, ...] = ()
    """The children whose base has landed, for the caller to retarget - the one step
    this cannot perform itself."""

    landed: tuple[str, ...] = ()
    """
    The branches whose own commits are already in the upstream base.
    """

    promotable: tuple[str, ...] = ()
    """
    The branches approved and unblocked, whether or not a link was built this pass.
    """

    def as_json(self) -> str:
        """:return: The report as one machine-readable document."""
        status = exit_code_for(self)
        return json.dumps(
            {
                "status": status.name_for_a_caller,
                "exit_code": int(status),
                **asdict(self),
            },
            indent=2,
        )

    @property
    def branches_left_unpublished(self) -> tuple[BranchOutcome, ...]:
        """:return: Every branch the pass could not leave in the state it wanted."""
        return tuple(
            outcome
            for outcome in self.restacked
            if outcome.outcome not in {RestackOutcome.PUSHED, RestackOutcome.UP_TO_DATE}
        )

    @property
    def fast_forward_was_refused(self) -> bool:
        """:return: Whether the fork's base was left behind the upstream."""
        return (
            self.fast_forward is not None
            and self.fast_forward.outcome is FastForwardOutcome.REFUSED_NOT_FAST_FORWARD
        )


def build_report(
    stack: Stack,
    fast_forward_report: FastForwardReport | None,
    restacked: Sequence[BranchOutcome],
    promoted: Sequence[Promotion] = (),
    promotion_labels_cleared: Sequence[str] = (),
) -> MaintenanceReport:
    """
    Assemble one pass's outcomes and its leftovers into a single report.

    :param stack: The derived stack, read for what the caller still has to do.
    :param fast_forward_report: What became of the fork's base branch, if attempted.
    :param restacked: What became of each branch in the restack plan.
    :param promoted: The branches whose upstream link was built this pass.
    :param promotion_labels_cleared: The branches whose spent link label was removed.
    :return: The report.
    """
    return MaintenanceReport(
        fast_forward=fast_forward_report,
        restacked=tuple(restacked),
        promoted=tuple(promoted),
        promotion_labels_cleared=tuple(promotion_labels_cleared),
        reparents=tuple(stack.reparents()),
        landed=tuple(branch.name for branch in stack.landed_branches()),
        promotable=tuple(branch.name for branch in stack.promotion_order()),
    )


# %% printing


def print_board_export(export: BoardExport, written_to: Path | None) -> None:
    """
    Report what the export contains, and where it went.

    :param export: The export.
    :param written_to: Where it was written, or ``None`` when it was only printed.
    """
    if written_to is None:
        logger.info(export.as_json())
        return
    logger.info(f"{len(export.pull_requests)} open pull request(s) -> {written_to}")


def print_fast_forward(report: FastForwardReport) -> None:
    """:param report: What became of the fork's base branch."""
    logger.info(f"{report.fork_reference}\t{report.outcome}\t{report.commit}")
    if report.explanation:
        logger.error(report.explanation)


def print_restack(outcomes: Sequence[BranchOutcome]) -> None:
    """:param outcomes: What became of each branch."""
    for outcome in outcomes:
        detail = (
            ",".join(outcome.conflicting_paths)
            or ",".join(outcome.refusals)
            or outcome.pushed_commit
            or outcome.explanation
            or ""
        )
        logger.info(f"{outcome.branch}\t{outcome.outcome}\t{detail}")


def print_promotions(promoted: Sequence[Promotion], cleared: Sequence[str]) -> None:
    """:param promoted: The branches whose link was built this pass.
    :param cleared: The branches whose spent link label was removed."""
    for promotion in promoted:
        logger.info(
            f"{promotion.branch}\t#{promotion.pull_request_number}\t{promotion.url}"
        )
        if promotion.body_was_truncated:
            logger.error(
                f"{promotion.branch}: the prefilled description was shortened to fit "
                f"the URL limit"
            )
    for branch in cleared:
        logger.info(f"{branch}\tlink-label-cleared\t")


# %% the exit status


def exit_code_for(report: MaintenanceReport) -> StackExitCode:
    """
    Decide one pass's exit status from what it actually left behind.

    Shared by every command that produces a report, so none of them can disagree about
    what counts as a clean pass - a refused fast-forward reported as success is exactly
    the kind of silence this exists to prevent.

    :param report: What the pass did.
    :return: The process exit code.
    """
    if report.fast_forward_was_refused:
        return StackExitCode.NOT_FAST_FORWARD
    unpublished = report.branches_left_unpublished
    if any(outcome.outcome is RestackOutcome.REFUSED for outcome in unpublished):
        return StackExitCode.MOVE_REFUSED
    if unpublished:
        return StackExitCode.BRANCH_NEEDS_ATTENTION
    return StackExitCode.SUCCESS
