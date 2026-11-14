"""
Finding the modules a pull request moves, as renames of their dotted paths.
"""

from __future__ import annotations

from basstler.class_property import classproperty
from basstler.review_triage.commit_tree import MODULE_SUFFIX, CommitTree
from basstler.review_triage.pull_request import PullRequestChanges
from basstler.review_triage.rename_sources import RenameSource
from basstler.review_triage.renames import (
    DOTTED_NAME_SEPARATOR,
    Rename,
    RenameDecisions,
)

# %% detection


class ModuleMoveDetection(RenameSource):
    """
    Detects a moved module file as a rename of its dotted path, where the old path is
    gone from the head commit and the new one absent from the base commit.
    """

    @classproperty
    def label(cls) -> str:
        return "file move"

    def decisions(self, changes: PullRequestChanges) -> RenameDecisions:
        base = CommitTree(changes.commits.git, changes.commits.base_commit)
        head = CommitTree(changes.commits.git, changes.commits.head_commit)
        renames: list[Rename] = []
        for change in changes.files:
            if change.previous_path is None or {
                change.previous_path.suffix,
                change.path.suffix,
            } != {MODULE_SUFFIX}:
                continue
            old = base.module_path(change.previous_path)
            new = head.module_path(change.path)
            if (
                old != new
                and DOTTED_NAME_SEPARATOR in old
                and not head.mentions(old)
                and not base.mentions(new)
            ):
                renames.append(Rename(old, new, self.label))
        return RenameDecisions(tuple(sorted(renames, key=lambda rename: rename.old)))
