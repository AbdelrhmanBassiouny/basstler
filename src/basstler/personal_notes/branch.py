"""
The personal-notes branch: where it lives, fetching it, and writing files onto it.

Every write goes through a scratch worktree of the fetched branch, so the checkout a
session works in is never switched or touched.
"""

from __future__ import annotations

import shutil
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path, PurePosixPath
from types import TracebackType

from basstler.exceptions import (
    NotesBranchMissingError,
    NotesPushRejectedError,
    UnsafeNotesPathError,
)
from basstler.git.commands import GitCommandRunner
from basstler.setup.steps import PersonalNotesSetting
from basstler.shell_configuration import FetchedBranchReference

NO_HOOKS_DIRECTORY = "/dev/null"
"""
A hooks directory holding no hooks, so git runs none.
"""

# %% where the notes live


@dataclass(frozen=True)
class PersonalNotesLocation:
    """
    Where a clone's personal notes are kept.
    """

    remote: str
    """
    The remote the notes branch is fetched from and pushed to: a name or a URL.
    """

    branch: str
    """
    The branch holding the notes.
    """

    notes_path: str
    """
    The personal-notes file, relative to the branch's root.
    """

    @classmethod
    def resolve(
        cls, project_root: Path, environment: Mapping[str, str]
    ) -> PersonalNotesLocation:
        """
        :param project_root: The clone whose git config to read.
        :param environment: The environment to read the settings' variables from.
        :return: The location the hooks resolve for that clone.
        """
        return cls(
            remote=PersonalNotesSetting.REMOTE.resolve(project_root, environment),
            branch=PersonalNotesSetting.BRANCH.resolve(project_root, environment),
            notes_path=PersonalNotesSetting.PATH.resolve(project_root, environment),
        )


# %% fetching


@dataclass(frozen=True)
class PersonalNotesBranch:
    """
    The personal-notes branch, as one clone reaches it.
    """

    location: PersonalNotesLocation
    """
    Where the notes are kept.
    """

    git: GitCommandRunner
    """
    The clone that fetches the branch.
    """

    def candidate_remotes(self) -> list[str]:
        """
        :return: The configured remote, then the current branch's upstream remote when
            that is a different one.
        """
        remotes = [self.location.remote]
        upstream = self.git.attempt(
            "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"
        )
        upstream_remote = upstream.output.split("/", 1)[0] if upstream.succeeded else ""
        if upstream_remote and upstream_remote not in remotes:
            remotes.append(upstream_remote)
        return remotes

    def fetch(self) -> str:
        """
        Fetch the branch into :attr:`FetchedBranchReference.PERSONAL_NOTES` from the
        first remote that has it.

        :return: That remote.
        :raises NotesBranchMissingError: If no candidate remote has the branch.
        """
        remotes = self.candidate_remotes()
        for remote in remotes:
            if self.git.attempt(
                "fetch",
                "--quiet",
                "--no-write-fetch-head",
                remote,
                f"+refs/heads/{self.location.branch}:"
                f"{FetchedBranchReference.PERSONAL_NOTES}",
            ).succeeded:
                return remote
        raise NotesBranchMissingError(self.location.branch, tuple(remotes))


# %% writing


class NotesWriteOutcome(StrEnum):
    """
    What a write did to the notes branch.
    """

    PUSHED = "pushed"
    """
    The changes were committed and pushed.
    """

    UNCHANGED = "unchanged"
    """
    The branch already held every change, so nothing was committed.
    """


@dataclass
class ScratchWorktree:
    """
    A detached worktree of :attr:`FetchedBranchReference.PERSONAL_NOTES` in a temporary
    directory, removed on exit.
    """

    git: GitCommandRunner
    """
    The clone the worktree belongs to.
    """

    directory: Path = field(init=False)
    """
    The worktree's root, once entered.
    """

    def __enter__(self) -> GitCommandRunner:
        """
        :return: A runner for the new worktree.
        """
        self.directory = Path(tempfile.mkdtemp())
        self.git.run(
            "worktree",
            "add",
            "--detach",
            "--quiet",
            str(self.directory),
            FetchedBranchReference.PERSONAL_NOTES,
        )
        return GitCommandRunner(self.directory)

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """
        Remove the worktree, whether or not the write succeeded.
        """
        self.git.attempt("worktree", "remove", "--force", str(self.directory))
        shutil.rmtree(self.directory, ignore_errors=True)


class NotesEdit(ABC):
    """
    A change made to a checkout of the notes branch, which a writer commits and pushes.
    """

    @abstractmethod
    def apply(self, root: Path) -> None:
        """
        Make the change.

        :param root: The root of a checkout of the latest notes branch.
        """


@dataclass(frozen=True)
class NotesFileChanges(NotesEdit):
    """
    New contents for files on the notes branch.
    """

    changes: Mapping[PurePosixPath, str | None]
    """
    Each path relative to the branch's root, with its new content, or ``None`` to remove
    the file or directory there.
    """

    def __post_init__(self) -> None:
        """
        :raises UnsafeNotesPathError: If a path is absolute or contains ``..``.
        """
        for path in self.changes:
            if path.is_absolute() or ".." in path.parts:
                raise UnsafeNotesPathError(path)

    def apply(self, root: Path) -> None:
        for path, content in self.changes.items():
            target = root / path
            if content is None and target.is_dir():
                shutil.rmtree(target)
                continue
            if content is None:
                target.unlink(missing_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)


@dataclass(frozen=True)
class NotesBranchWriter:
    """
    Commits edits onto the personal-notes branch and pushes them.
    """

    branch: PersonalNotesBranch
    """
    The branch written to.
    """

    push_attempts: int = 1
    """
    How many times an edit is applied to the latest branch and pushed before a push the
    remote keeps rejecting is given up on.
    """

    def write(self, edit: NotesEdit, message: str) -> NotesWriteOutcome:
        """
        Apply *edit* to the latest notes branch in one commit, and push it to the remote
        it was fetched from; a rejected push is retried from a fresh fetch. The
        project's commit hooks do not run: the notes branch carries none of the
        project's files they check.

        :param edit: The change to make.
        :param message: The commit message.
        :raises NotesBranchMissingError: If no remote has the branch.
        :raises NotesPushRejectedError: If every push attempt was rejected.
        :return: Whether anything was pushed.
        """
        for _ in range(self.push_attempts):
            remote = self.branch.fetch()
            with ScratchWorktree(self.branch.git) as worktree:
                edit.apply(worktree.working_directory)
                worktree.run("add", "--all")
                if worktree.attempt("diff", "--cached", "--quiet").succeeded:
                    return NotesWriteOutcome.UNCHANGED
                worktree.run(
                    "-c",
                    f"core.hooksPath={NO_HOOKS_DIRECTORY}",
                    "commit",
                    "--quiet",
                    "-m",
                    message,
                )
                if worktree.attempt(
                    "push", "--quiet", remote, f"HEAD:{self.branch.location.branch}"
                ).succeeded:
                    return NotesWriteOutcome.PUSHED
        raise NotesPushRejectedError(self.branch.location.branch, self.push_attempts)
