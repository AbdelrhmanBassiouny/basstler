"""
The item a branch carries, and the blockers one owner writes on it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from basstler.class_property import classproperty
from basstler.plan.item_bootstrap.documents import PlanDocuments, ProjectCheckout
from basstler.plan.item_bootstrap.report import OperationReport
from basstler.plan.item_bootstrap.update import ItemUpdateRequest
from basstler.plan.item_bootstrap.vocabulary import PlanItemBootstrapExitCode, ReportKey
from basstler.plan.model import (
    ItemStatus,
    ManifestKey,
    PlanManifest,
)

# %% the item a branch carries


@dataclass(frozen=True)
class TrackedItem:
    """
    The item a branch carries, as the manifest records it right now.
    """

    item_identifier: str
    """
    The item's id.
    """

    status: ItemStatus
    """
    The status the manifest records for it.
    """

    blockers: tuple[str, ...]
    """
    What the manifest records as blocking it.
    """

    def to_json(self) -> dict[str, Any]:
        """
        Render the item as the JSON a caller reads.
        """
        return {
            ReportKey.ITEM: self.item_identifier,
            ManifestKey.STATUS.key: self.status.value,
            ManifestKey.BLOCKERS.key: list(self.blockers),
        }


@dataclass(frozen=True)
class ItemWrite(TrackedItem):
    """
    One item's recorded state after a write, and the status it carried before it.
    """

    previous_status: ItemStatus
    """
    The status the manifest recorded before the write.
    """

    def to_json(self) -> dict[str, Any]:
        return {
            **super().to_json(),
            ReportKey.PREVIOUS_STATUS: self.previous_status.value,
        }


@dataclass(frozen=True)
class BranchReport(OperationReport):
    """
    The item a branch carries, as an operation keyed on that branch found or left it.
    """

    branch: str
    """
    The branch that was looked up.
    """

    plan_identifier: str | None
    """
    The plan tracking it, or ``None`` when no plan claims the branch.
    """

    item: TrackedItem | None
    """
    The item recording that branch, or ``None`` when no plan claims the branch.
    """

    @classmethod
    def of_branch(cls, branch: str, project_root: Path) -> BranchReport:
        """
        Find the plan and the item a branch belongs to.

        :param branch: The branch to resolve.
        :param project_root: The repository to run within.
        :raises UnknownPlanError: If the index names a plan with no manifest.
        :return: What the branch belongs to.
        """
        plan_identifier = ProjectCheckout(project_root).plan_tracking(branch)
        if plan_identifier is None:
            return cls(branch=branch, plan_identifier=None, item=None)
        manifest = PlanManifest(
            PlanDocuments.load(plan_identifier, project_root).manifest
        )
        item = next(
            (
                TrackedItem(
                    item_identifier=entry.content[ManifestKey.IDENTIFIER.key],
                    status=entry.status,
                    blockers=tuple(entry.content.get(ManifestKey.BLOCKERS.key) or ()),
                )
                for entry in manifest.items
                if entry.branch == branch
            ),
            None,
        )
        return cls(branch=branch, plan_identifier=plan_identifier, item=item)

    @property
    def exit_code(self) -> PlanItemBootstrapExitCode:
        if self.item is None:
            return PlanItemBootstrapExitCode.BRANCH_TRACKS_NO_ITEM
        return PlanItemBootstrapExitCode.SUCCESS

    def to_json(self) -> dict[str, Any]:
        return {
            ReportKey.STATUS: self.exit_code.name_for_a_caller,
            ReportKey.EXIT_CODE: int(self.exit_code),
            ManifestKey.BRANCH.key: self.branch,
            ReportKey.PLAN: self.plan_identifier,
            ReportKey.TRACKED_ITEM: None if self.item is None else self.item.to_json(),
        }


@dataclass(frozen=True)
class OwnedBlocker:
    """
    One owner's blocker on the item a branch carries, set or withdrawn.

    Written as ``<owner>: <reason>``, so the owner replaces and withdraws only its own
    entries and never one a person wrote.
    """

    branch: str
    """
    The branch whose item is written.
    """

    owner: str
    """
    Who the blocker belongs to.
    """

    reason: str | None = None
    """
    Why the branch is blocked, or ``None`` to withdraw the owner's blocker.
    """

    @classproperty
    def owner_separator(cls) -> str:
        """
        What separates a written blocker's owner from its reason.
        """
        return ": "

    def write(self, project_root: Path) -> BranchReport:
        """
        Rewrite the branch's item with the owner's blocker set or withdrawn, then derive
        its status from what is left blocking it.

        Only fields that change are written, so withdrawing a blocker the item never
        carried leaves it untouched.

        :param project_root: The repository to run within.
        :return: What was written.
        """
        resolution = BranchReport.of_branch(self.branch, project_root)
        item = resolution.item
        if item is None:
            return resolution
        prefix = f"{self.owner}{self.owner_separator}"
        blockers = tuple(
            blocker for blocker in item.blockers if not blocker.startswith(prefix)
        )
        if self.reason is not None:
            blockers += (f"{prefix}{self.reason}",)
        status = self.status_beside(blockers, item.status)
        changed = {
            manifest_key: value
            for manifest_key, value, recorded in (
                (ManifestKey.STATUS, status, item.status),
                (ManifestKey.BLOCKERS, blockers, item.blockers),
            )
            if value != recorded
        }
        if changed:
            ItemUpdateRequest(
                plan_identifier=resolution.plan_identifier,
                item_identifier=item.item_identifier,
                values_by_key=changed,
            ).update(project_root)
        return replace(
            resolution,
            item=ItemWrite(
                item_identifier=item.item_identifier,
                status=status,
                blockers=blockers,
                previous_status=item.status,
            ),
        )

    @staticmethod
    def status_beside(blockers: tuple[str, ...], previous: ItemStatus) -> ItemStatus:
        """
        The status an item carries given what is now blocking it.

        An item nothing blocks keeps what it recorded, unless that was
        :attr:`ItemStatus.BLOCKED`, which the blockers it no longer has were the reason
        for.

        :param blockers: What blocks the item now.
        :param previous: The status it recorded before.
        :return: The status to record.
        """
        if blockers:
            return ItemStatus.BLOCKED
        if previous is ItemStatus.BLOCKED:
            return ItemStatus.IN_PROGRESS
        return previous
