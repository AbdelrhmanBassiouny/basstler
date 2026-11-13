"""
Recording the merged items of every plan on a notes branch and dropping the landed ones.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from basstler.locations import ProjectLocation
from basstler.maintenance.git_commands import GitCommandRunner
from basstler.personal_notes.branch import (
    NotesBranchWriter,
    NotesEdit,
    PersonalNotesBranch,
    PersonalNotesLocation,
)
from basstler.plan.manifest_tools import BranchIndex
from basstler.plan.merged_items.plan_items import MergedItems
from basstler.plan.model import PlanDocument, PlanManifest
from basstler.plan.size_limits import PlanFiles
from basstler.pull_request_source import PullRequestSource
from basstler.repository import Repository

# %% every plan on a notes branch


class MergedItemsCommand(StrEnum):
    """
    The subcommands this command answers besides its default.
    """

    EVERY_PLAN = "every-plan"
    """
    Record the merged items of every plan on the notes branch, and push them.
    """


class MergedItemsLine(StrEnum):
    """
    The parts of the line that says what recording every plan's merged items did.
    """

    NONE = "none - every plan records each merged pull request done"
    """
    No plan had a merged item it did not record done.
    """

    DROPPED = "recorded done and dropped: {items}"
    """
    Names every item dropped, as ``<plan-id>/<item-id>``.
    """

    UNREADABLE = "; not read, so left as they are: {repositories}"
    """
    Names every repository whose pull requests this credential may not read.
    """


@dataclass
class MergedItemsSummary:
    """
    What recording every plan's merged items did.
    """

    dropped_items: list[str] = field(default_factory=list)
    """
    Every item dropped as landed, as ``<plan-id>/<item-id>``.
    """

    unreadable_repositories: set[Repository] = field(default_factory=set)
    """
    The repositories whose pull requests could not be read, whose plans' items stay.
    """

    @property
    def line(self) -> str:
        """
        :return: The summary in one line.
        """
        line = (
            MergedItemsLine.DROPPED.format(items=", ".join(self.dropped_items))
            if self.dropped_items
            else MergedItemsLine.NONE.value
        )
        if not self.unreadable_repositories:
            return line
        repositories = ", ".join(sorted(map(str, self.unreadable_repositories)))
        return line + MergedItemsLine.UNREADABLE.format(repositories=repositories)


@dataclass
class MergedItemsInEveryPlan(NotesEdit):
    """
    Records every plan's newly merged items done and saves that plan without its landed
    items; a pull request it cannot read stops it before anything is changed.
    """

    pull_request_source: PullRequestSource
    """
    Where the items' pull requests are read from.
    """

    summary: MergedItemsSummary = field(default_factory=MergedItemsSummary)
    """
    What the latest :meth:`apply` did.
    """

    def apply(self, root: Path) -> None:
        summary = MergedItemsSummary()
        plans_root = root / ProjectLocation.PLANS
        recorded_manifests = {}
        for manifest_path in sorted(plans_root.glob(f"*/{PlanDocument.MANIFEST}")):
            manifest = PlanManifest.from_file(manifest_path)
            summary.unreadable_repositories.update(
                repository
                for repository in manifest.repositories
                if self.pull_request_source.read_failure_of(repository) is not None
            )
            merged_items = MergedItems(manifest, self.pull_request_source)
            if merged_items.items:
                recorded_manifests[manifest_path] = merged_items.recorded_manifest
        self.summary = summary
        if not recorded_manifests:
            return
        for manifest_path, recorded in recorded_manifests.items():
            recorded.write(manifest_path)
            summary.dropped_items.extend(
                f"{recorded.identifier}/{identifier}"
                for identifier in sorted(recorded.landed_identifiers)
            )
            self.save_without_landed_items(manifest_path.parent)
        index = root / ProjectLocation.PLAN_BRANCH_INDEX
        index.parent.mkdir(parents=True, exist_ok=True)
        index.write_text(
            BranchIndex(root, ProjectLocation.PLANS, PlanDocument.MANIFEST).render()
        )

    @staticmethod
    def save_without_landed_items(plan_directory: Path) -> None:
        """
        Save the plan in *plan_directory* again through :meth:`PlanFiles.stage`, which
        leaves out its landed items and removes the plan once none are left.

        :param plan_directory: The plan's own directory on the notes branch.
        """
        destination = PlanFiles(
            plan_directory / PlanDocument.MANIFEST,
            plan_directory / PlanDocument.ROADMAP,
        )
        # stage reads its source while it writes its destination, so it saves a copy.
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

    def record_on_notes_branch(self, project_root: Path, *, push_attempts: int) -> str:
        """
        Apply this edit to the latest notes branch of *project_root* and push it.

        :param project_root: The clone whose settings say where the notes are.
        :param push_attempts: How many pushes to make before giving up on a branch that
            keeps moving.
        :raises NotesPushRejectedError: If every push was rejected.
        :return: The line saying what was recorded.
        """
        branch = PersonalNotesBranch(
            location=PersonalNotesLocation.resolve(project_root, os.environ),
            git=GitCommandRunner(project_root),
        )
        NotesBranchWriter(branch, push_attempts).write(self, "Record merged plan items")
        return self.summary.line
