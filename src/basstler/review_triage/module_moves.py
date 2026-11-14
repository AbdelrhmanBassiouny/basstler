"""
Finding the modules a pull request moves, as renames of their dotted paths.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from basstler.class_property import classproperty
from basstler.review_triage.commit_tree import CommitTree
from basstler.review_triage.pull_request import PullRequestChanges
from basstler.review_triage.rename_sources import RenameSource
from basstler.review_triage.renames import (
    DOTTED_NAME_SEPARATOR,
    Rename,
    RenameDecisions,
)

# %% module paths

PACKAGE_INITIALIZER = "__init__.py"
"""
The file that makes a directory a package, its own module the package's.
"""

MODULE_SUFFIX = ".py"
"""
The suffix of a Python module's file.
"""


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
            old = self.module_path(base, change.previous_path)
            new = self.module_path(head, change.path)
            if (
                old != new
                and DOTTED_NAME_SEPARATOR in old
                and not head.mentions(old)
                and not base.mentions(new)
            ):
                renames.append(Rename(old, new, self.label))
        return RenameDecisions(tuple(sorted(renames, key=lambda rename: rename.old)))

    @staticmethod
    def module_path(tree: CommitTree, path: PurePosixPath) -> str:
        """
        :param tree: The commit holding the file.
        :param path: A module's file.
        :return: The dotted path the module is imported by, through every enclosing
            directory that is a package.
        """
        components = [] if path.name == PACKAGE_INITIALIZER else [path.stem]
        package = path.parent
        while package != PurePosixPath(".") and tree.holds(
            package / PACKAGE_INITIALIZER
        ):
            components.insert(0, package.name)
            package = package.parent
        return DOTTED_NAME_SEPARATOR.join(components)
