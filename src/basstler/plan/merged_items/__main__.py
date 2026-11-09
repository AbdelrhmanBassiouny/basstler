"""
Record every item of a plan done whose pull request GitHub reports merged.

Usage:
    "${BASSTLER_PYTHON}" -m basstler.plan.merged_items <plan.yaml>
"""

from __future__ import annotations

from cyclopts import App
from cyclopts.types import ExistingFile

from basstler.exit_codes import ExitCode
from basstler.plan.merged_items import MergedItems
from basstler.pull_request_source import GitHubPullRequestSource

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
    return MergedItems.record(manifest, GitHubPullRequestSource.from_environment())


if __name__ == "__main__":
    app()
