"""
One branch of a remote, read and written without touching the working tree.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from basstler.branch import Branch
from basstler.class_property import classproperty
from basstler.maintenance.git_commands import (
    GitCommandResult,
    GitCommandRunner,
    ProposedPush,
)
from basstler.repository import Repository

# %% the branch


@dataclass(frozen=True)
class RemoteBranch(Branch):
    """
    One branch of one remote, read and written without touching the working tree.
    """

    git: GitCommandRunner
    """
    The clone to work in.
    """

    remote: str
    """
    The remote the branch lives on, as a remote name in the clone or a URL.
    """

    @classproperty
    def local_reference_prefix(cls) -> str:
        """
        Where every fetched branch is kept, so a fetch never moves ``FETCH_HEAD`` under
        anyone else.
        """
        return "refs/basstler/remote-branches"

    @property
    def local_reference(self) -> str:
        """
        :return: Where a fetch of this branch is kept.
        """
        return f"{self.local_reference_prefix}/{self.name}"

    @property
    def url(self) -> str:
        """
        :return: The URL the remote points at.
        """
        return self.git.attempt("remote", "get-url", self.remote).output or self.remote

    @property
    def repository(self) -> Repository | None:
        """
        :return: The repository the remote points at, ``None`` when it names none - a
            remote given as a local path.
        """
        url = self.url
        if not Repository.names_a_repository(url):
            return None
        return Repository.from_remote_url(url)

    @property
    def description(self) -> str:
        """:return: The repository's name, or the remote's where it names none."""
        repository = self.repository
        return repository.full_name if repository else self.remote

    def exists(self) -> bool:
        """
        :return: Whether the remote can be reached and has this branch.
        """
        return bool(
            self.git.attempt("ls-remote", "--heads", self.remote, self.name).output
        )

    def fetch(self) -> str | None:
        """
        :return: The branch's tip commit, or ``None`` when the remote has no such branch.
        """
        if not self.exists():
            return None
        self.git.fetch(
            self.remote,
            "--no-tags",
            "--no-write-fetch-head",
            f"+{self.reference}:{self.local_reference}",
        )
        return self.git.commit_at(self.local_reference)

    def read_latest(self, path: str | Path) -> str | None:
        """
        :param path: The file's path from the branch's root.
        :return: Its text at the branch's current tip without the final newline, or
            ``None`` when the remote has no such branch or the branch no such file.
        """
        tip = self.fetch()
        return self.git.file_at(tip, path) if tip else None

    def read_every_latest(self, directory: str | Path, file_name: str) -> list[str]:
        """
        :param directory: A directory from the branch's root.
        :param file_name: The name of the files to read.
        :return: The text of every file of that name anywhere under the directory at
            the branch's current tip, in path order; empty when the remote has no such
            branch.
        """
        tip = self.fetch()
        if tip is None:
            return []
        listed = self.git.run(
            "ls-tree", "-r", "--name-only", tip, "--", Path(directory).as_posix()
        )
        return [
            self.git.file_at(tip, path)
            for path in sorted(listed.splitlines())
            if Path(path).name == file_name
        ]

    def attempt_write(
        self, files: dict[str, str], message: str, attempts: int = 3
    ) -> FileWrite:
        """
        Commit files onto the branch's latest tip and push them, again on top of another
        writer's commit when that landed first.

        :param files: What to write, by path, each without its final newline.
        :param message: The commit message.
        :param attempts: How many times to commit and push before giving up.
        :return: The last commit and its push, failed when every attempt was refused.
        """
        for _ in range(attempts):
            commit = self.git.commit_files(self.fetch(), files, message)
            pushed = self.git.push(
                ProposedPush(self.remote, f"{commit}:{self.reference}")
            )
            if pushed.succeeded:
                break
        return FileWrite(commit, pushed)

    def write(self, files: dict[str, str], message: str, attempts: int = 3) -> str:
        """
        Like :meth:`attempt_write`, but a refused push is an error.

        :return: The pushed commit.
        :raises GitCommandFailed: If the last push is refused too.
        """
        written = self.attempt_write(files, message, attempts)
        written.push.raise_if_failed()
        return written.commit

    def create(self, parent: str, files: dict[str, str], message: str) -> str:
        """
        Commit files on top of another branch's commit and push them as this branch.

        :param parent: The commit to build on.
        :param files: What to write, by path, each without its final newline.
        :param message: The commit message.
        :return: The pushed commit.
        :raises GitCommandFailed: If the remote refuses the push.
        """
        commit = self.git.commit_files(parent, files, message)
        self.git.push(
            ProposedPush(self.remote, f"{commit}:{self.reference}")
        ).raise_if_failed()
        return commit

    def delete(self) -> GitCommandResult:
        """
        Delete the branch from the remote.

        :return: The push deleting it, failed when the remote refused it.
        """
        return self.git.push(ProposedPush(self.remote, f":{self.reference}"))


@dataclass(frozen=True)
class FileWrite:
    """
    One commit of files onto a branch, and its push.
    """

    commit: str
    """
    The commit.
    """

    push: GitCommandResult
    """
    Its push, failed when the remote refused it.
    """
