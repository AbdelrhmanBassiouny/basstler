"""
Record every item of a plan done whose pull request GitHub reports merged, or do so for
every plan on the notes branch and push the result.

Usage:
    "${BASSTLER_PYTHON}" -m basstler.plan.merged_items <plan.yaml>
    "${BASSTLER_PYTHON}" -m basstler.plan.merged_items every-plan [--project-root DIRECTORY]
"""

from __future__ import annotations

from pathlib import Path

from cyclopts import App
from cyclopts.types import ExistingDirectory, ExistingFile

from basstler.exit_codes import ExitCode
from basstler.github.pull_request_source import GitHubPullRequestSource
from basstler.plan.merged_items.every_plan import (
    MergedItemsCommand,
    MergedItemsInEveryPlan,
)
from basstler.plan.merged_items.plan_items import MergedItems
from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""

# %% the command line


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
    return MergedItems.record(
        manifest, GitHubPullRequestSource.from_environment(reads_check_states=False)
    )


@app.command(name=MergedItemsCommand.EVERY_PLAN.value)
def record_merged_items_in_every_plan(
    *, project_root: ExistingDirectory = Path(), push_attempts: int = 5
) -> None:
    """
    Record every plan's merged items done on the clone's notes branch, drop the landed
    ones, push the result and print what was done.

    :param project_root: The clone whose settings say where the notes are.
    :param push_attempts: How many pushes to make before giving up on a branch that
        keeps moving.
    """
    recording = MergedItemsInEveryPlan(
        GitHubPullRequestSource.from_environment(reads_check_states=False)
    )
    logger.info(
        recording.record_on_notes_branch(project_root, push_attempts=push_attempts)
    )


if __name__ == "__main__":
    app()
