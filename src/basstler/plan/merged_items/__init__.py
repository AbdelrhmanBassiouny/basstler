"""
Recording in a plan's manifest that an item is done once GitHub reports its pull request
merged, so a save drops it as landed, and doing so for every plan on a notes branch.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

from basstler.exit_codes import CommandFailure, ExitCode, ManifestToolsExitCode
from basstler.locations import ProjectLocation
from basstler.personal_notes.branch import NotesEdit
from basstler.plan.manifest_tools import BranchIndex
from basstler.plan.model import ItemStatus, PlanDocument, PlanItem, PlanManifest
from basstler.plan.size_limits import PlanFiles
from basstler.pull_request_source import PullRequestSource
from basstler.repository import PullRequestReference
from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""

# %% merged items


@dataclass(frozen=True)
class MergedItems:
    """
    The items of one plan whose pull requests GitHub reports merged, though the plan
    does not record them done.
    """

    manifest: PlanManifest
    """
    The plan whose items are looked up.
    """

    pull_request_source: PullRequestSource
    """
    Where the items' pull requests are read from.
    """

    @cached_property
    def items(self) -> list[PlanItem]:
        """
        :return: The merged items, in manifest order.
        :raises CommandFailure: If a pull request could not be read.
        """
        merged = []
        for item in self.manifest.items:
            if item.status is ItemStatus.DONE or item.pull_request_number is None:
                continue
            record = self.pull_request_source.pull_request(
                PullRequestReference(
                    self.manifest.repository_of(item), item.pull_request_number
                )
            )
            if record is not None and record.was_merged:
                merged.append(item)
        return merged

    @property
    def recorded_manifest(self) -> PlanManifest:
        """
        :return: The manifest with every merged item's status set to done.
        """
        return self.manifest.with_items_done({item.identifier for item in self.items})

    @classmethod
    def record(
        cls, manifest_path: Path, pull_request_source: PullRequestSource
    ) -> ExitCode:
        """
        Set the status of every merged item of the manifest at *manifest_path* to done,
        printing one line per item; a read that fails is printed and changes nothing.

        :param manifest_path: The ``plan.yaml`` to record the merged items in.
        :param pull_request_source: Where the items' pull requests are read from.
        :return: :attr:`ManifestToolsExitCode.SUCCESS`, or the status of the failed
            read.
        """
        merged_items = cls(PlanManifest.from_file(manifest_path), pull_request_source)
        try:
            items = merged_items.items
        except CommandFailure as failure:
            logger.error(f"Could not read which items' pull requests merged: {failure}")
            return failure.exit_code
        if not items:
            return ManifestToolsExitCode.SUCCESS
        merged_items.recorded_manifest.write(manifest_path)
        for item in items:
            logger.info(
                f"{item.identifier}: pull request #{item.pull_request_number} merged, "
                f"recorded done"
            )
        return ManifestToolsExitCode.SUCCESS


# %% every plan on a notes branch


@dataclass
class MergedItemsInEveryPlan(NotesEdit):
    """
    Records every plan's merged items done and drops its landed items, as a save of each
    plan would.
    """

    pull_request_source: PullRequestSource
    """
    Where the items' pull requests are read from.
    """

    unread_plans: dict[str, ExitCode] = field(default_factory=dict)
    """
    The plans whose pull requests could not be read, each with the status the read
    failed with; they are left as they were.
    """

    def apply(self, root: Path) -> None:
        plans_root = root / ProjectLocation.PLANS
        for manifest_path in sorted(plans_root.glob(f"*/{PlanDocument.MANIFEST}")):
            status = MergedItems.record(manifest_path, self.pull_request_source)
            if status != ManifestToolsExitCode.SUCCESS:
                self.unread_plans[manifest_path.parent.name] = status
                continue
            if PlanManifest.from_file(manifest_path).landed_identifiers:
                self.drop_landed_items(manifest_path.parent)
        index = root / ProjectLocation.PLAN_BRANCH_INDEX
        index.parent.mkdir(parents=True, exist_ok=True)
        index.write_text(
            BranchIndex(root, ProjectLocation.PLANS, PlanDocument.MANIFEST).render()
        )

    @staticmethod
    def drop_landed_items(plan_directory: Path) -> None:
        """
        Save the plan in *plan_directory* again without its landed items, removing it
        once none are left.

        :param plan_directory: The plan's own directory on the notes branch.
        """
        destination = PlanFiles(
            plan_directory / PlanDocument.MANIFEST,
            plan_directory / PlanDocument.ROADMAP,
        )
        with tempfile.TemporaryDirectory() as copy_directory:
            copy = PlanFiles(
                Path(copy_directory) / PlanDocument.MANIFEST,
                Path(copy_directory) / PlanDocument.ROADMAP,
            )
            shutil.copyfile(destination.manifest, copy.manifest)
            copy.roadmap.write_text(
                destination.roadmap.read_text() if destination.roadmap.exists() else ""
            )
            copy.stage(destination)
