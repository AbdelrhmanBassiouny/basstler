"""
A repository's rules as its personal-notes branch holds them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from basstler.class_property import classproperty
from basstler.locations import ProjectLocation
from basstler.maintenance.git_commands import GitCommandRunner
from basstler.personal_notes.branch import (
    NotesBranchWriter,
    NotesFileChanges,
    NotesWriteOutcome,
    PersonalNotesBranch,
    PersonalNotesLocation,
)
from basstler.plan.repository_rules import RepositoryRules
from basstler.shell_configuration import FetchedBranchReference


@dataclass(frozen=True)
class RepositoryRulesStore:
    """
    Reads and writes one repository's rules on its notes branch.
    """

    branch: PersonalNotesBranch
    """
    The notes branch holding the rules.
    """

    @classproperty
    def rules_path(cls) -> PurePosixPath:
        """
        The rules file's path, relative to the notes branch's root.
        """
        return PurePosixPath(ProjectLocation.PLAN_RULES)

    @classmethod
    def from_project_root(cls, project_root: Path) -> RepositoryRulesStore:
        """
        :param project_root: The clone whose settings say where the notes are.
        :return: The store over that clone's notes branch.
        """
        return cls(
            PersonalNotesBranch(
                location=PersonalNotesLocation.resolve(project_root, os.environ),
                git=GitCommandRunner(project_root),
            )
        )

    def read_fetched(self) -> RepositoryRules:
        """
        :return: The rules on the notes branch as last fetched; none if it holds no
            rules file.
        """
        file = FetchedBranchReference.PERSONAL_NOTES.file_at(self.rules_path)
        if not self.branch.git.attempt("cat-file", "-e", file).succeeded:
            return RepositoryRules()
        return RepositoryRules.from_yaml(self.branch.git.run("show", file))

    def read(self) -> RepositoryRules:
        """
        Fetch the notes branch, then read its rules.

        :raises NotesBranchMissingError: If no remote has the notes branch.
        :return: The latest rules.
        """
        self.branch.fetch()
        return self.read_fetched()

    def write(self, rules: RepositoryRules, message: str) -> NotesWriteOutcome:
        """
        Replace the rules on the notes branch and push it.

        :param rules: The rules the branch is to hold.
        :param message: The commit message.
        :return: Whether anything was pushed.
        """
        return NotesBranchWriter(self.branch).write(
            NotesFileChanges({self.rules_path: rules.render()}), message
        )
