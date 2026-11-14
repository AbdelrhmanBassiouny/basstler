"""
Finding the definitions a pull request moves from one module to another, as renames of
their dotted paths.
"""

from __future__ import annotations

from collections.abc import Iterator

from basstler.class_property import classproperty
from basstler.review_triage.commit_tree import MODULE_SUFFIX, CommitTree
from basstler.review_triage.comparison import FileChange
from basstler.review_triage.pull_request import PullRequestChanges
from basstler.review_triage.python_source import PythonSource
from basstler.review_triage.rename_sources import RenameSource
from basstler.review_triage.renames import (
    DOTTED_NAME_SEPARATOR,
    Rename,
    RenameDecisions,
)

# %% detection


class DefinitionMoveDetection(RenameSource):
    """
    Detects a top-level definition that leaves a module the head commit keeps and is
    added to exactly one other module, as a rename of its dotted path.
    """

    @classproperty
    def label(cls) -> str:
        return "definition move"

    def decisions(self, changes: PullRequestChanges) -> RenameDecisions:
        base = CommitTree(changes.commits.git, changes.commits.base_commit)
        head = CommitTree(changes.commits.git, changes.commits.head_commit)
        modules = [
            change for change in changes.files if change.path.suffix == MODULE_SUFFIX
        ]
        gained: dict[str, list[str]] = {}
        for change in modules:
            for name in self.added_names(change):
                gained.setdefault(name, []).append(head.module_path(change.path))
        renames = [
            Rename(f"{old_module}.{name}", f"{new_modules[0]}.{name}", self.label)
            for change in modules
            for old_module, name in self.removed_names(change, base)
            if len(new_modules := gained.get(name, [])) == 1
            and DOTTED_NAME_SEPARATOR in old_module
        ]
        return RenameDecisions(tuple(sorted(renames, key=lambda rename: rename.old)))

    @staticmethod
    def added_names(change: FileChange) -> frozenset[str]:
        """
        :param change: A changed module.
        :return: The names its head version defines and its base version did not.
        """
        if change.head_text is None:
            return frozenset()
        head_names = PythonSource(change.head_text).defined_names
        if change.base_text is None:
            return head_names
        return head_names - PythonSource(change.base_text).defined_names

    @staticmethod
    def removed_names(
        change: FileChange, base: CommitTree
    ) -> Iterator[tuple[str, str]]:
        """
        :param change: A changed module.
        :param base: The base commit.
        :return: The module's dotted path with each name its base version defines and
            its head version, at the same path, no longer does.
        """
        if (
            change.base_text is None
            or change.head_text is None
            or change.previous_path is not None
        ):
            return
        module = base.module_path(change.path)
        removed = (
            PythonSource(change.base_text).defined_names
            - PythonSource(change.head_text).defined_names
        )
        for name in sorted(removed):
            yield module, name
