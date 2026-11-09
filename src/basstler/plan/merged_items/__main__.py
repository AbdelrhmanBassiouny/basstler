"""
Record every item of a plan done whose pull request GitHub reports merged, or do so for
every plan on the notes branch and push the result.

Usage:
    "${BASSTLER_PYTHON}" -m basstler.plan.merged_items <plan.yaml>
    "${BASSTLER_PYTHON}" -m basstler.plan.merged_items every-plan [--project-root DIRECTORY]
"""

from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path

from cyclopts import App
from cyclopts.types import ExistingDirectory, ExistingFile

from basstler.exit_codes import ExitCode, ManifestToolsExitCode
from basstler.maintenance.git_commands import GitCommandRunner
from basstler.personal_notes.branch import (
    NotesBranchWriter,
    PersonalNotesBranch,
    PersonalNotesLocation,
)
from basstler.plan.merged_items import MergedItems, MergedItemsInEveryPlan
from basstler.pull_request_source import GitHubPullRequestSource
from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""

# %% the command line


class MergedItemsCommand(StrEnum):
    """
    The subcommands this command answers besides its default.
    """

    EVERY_PLAN = "every-plan"
    """
    Record the merged items of every plan on the notes branch, and push them.
    """


app = App(help=__doc__)
"""
The command, which takes the manifest to record the merged items in.
"""


@app.default
def record_merged_items(manifest: ExistingFile) -> ExitCode:
    """
    Record the manifest's merged items done, reading their pull requests from GitHub.

    :param manifest: The ``plan.yaml`` to record them in, rewritten in place.
    :return: The status :meth:`MergedItems.record` ended with.
    """
    return MergedItems.record(manifest, GitHubPullRequestSource.from_environment())


@app.command(name=MergedItemsCommand.EVERY_PLAN.value)
def record_merged_items_in_every_plan(
    *, project_root: ExistingDirectory = Path(), push_attempts: int = 5
) -> ExitCode:
    """
    Record every plan's merged items done on the clone's notes branch, drop the landed
    ones, and push the result.

    :param project_root: The clone whose settings say where the notes are.
    :param push_attempts: How many pushes to make before giving up on a branch that
        keeps moving.
    :return: The status of the first plan whose pull requests could not be read, or
        success.
    """
    branch = PersonalNotesBranch(
        location=PersonalNotesLocation.resolve(project_root, os.environ),
        git=GitCommandRunner(project_root),
    )
    recording = MergedItemsInEveryPlan(GitHubPullRequestSource.from_environment())
    outcome = NotesBranchWriter(branch, push_attempts).write(
        recording, "Record merged plan items"
    )
    logger.info(f"Notes branch '{branch.location.branch}': {outcome}")
    return next(iter(recording.unread_plans.values()), ManifestToolsExitCode.SUCCESS)


if __name__ == "__main__":
    app()
