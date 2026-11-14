"""
Finding the files a pull request moves, as renames of the paths prose refers to them by.
"""

from __future__ import annotations

from collections import Counter
from pathlib import PurePosixPath

from basstler.class_property import classproperty
from basstler.review_triage.pull_request import PullRequestChanges
from basstler.review_triage.rename_sources import RenameSource
from basstler.review_triage.renames import Rename, RenameDecisions

# %% detection


class FileMoveDetection(RenameSource):
    """
    Detects a moved file as a rename of its path from the first directory the move
    changes, the directories both paths share left out.

    .. note:: A path that is a bare file name is renamed only when no other file of the
        base commit has that name, and a path without a separator or a suffix never.
    """

    @classproperty
    def label(cls) -> str:
        return "file path move"

    def decisions(self, changes: PullRequestChanges) -> RenameDecisions:
        base_files = changes.commits.git.run(
            "ls-tree", "-r", "--name-only", changes.commits.base_commit
        ).splitlines()
        file_names = Counter(PurePosixPath(file).name for file in base_files)
        found: dict[str, set[str]] = {}
        for change in changes.files:
            if change.previous_path is None:
                continue
            old, new = self.differing_paths(change.previous_path, change.path)
            if old.name == str(old) and file_names[old.name] > 1:
                continue
            if not old.suffix and old.name == str(old):
                continue
            found.setdefault(str(old), set()).add(str(new))
        renames = [
            Rename(old, next(iter(news)), self.label, is_file_path=True)
            for old, news in sorted(found.items())
            if len(news) == 1
        ]
        return RenameDecisions(tuple(renames))

    @staticmethod
    def differing_paths(
        old: PurePosixPath, new: PurePosixPath
    ) -> tuple[PurePosixPath, PurePosixPath]:
        """
        :param old: Where the file was.
        :param new: Where it is.
        :return: Both paths without the leading directories they share.
        """
        shared = 0
        while (
            shared < min(len(old.parts), len(new.parts)) - 1
            and old.parts[shared] == new.parts[shared]
        ):
            shared += 1
        return PurePosixPath(*old.parts[shared:]), PurePosixPath(*new.parts[shared:])
