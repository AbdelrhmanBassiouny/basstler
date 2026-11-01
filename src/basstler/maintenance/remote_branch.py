"""
One branch of a remote, read and written without touching the working tree.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from basstler.class_property import classproperty
from basstler.maintenance.git_commands import GitCommandRunner, ProposedPush
from basstler.repository import Repository

# %% the branch


@dataclass(frozen=True)
class RemoteBranch:
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

    name: str
    """
    The branch's name on that remote.
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
    def repository(self) -> Repository | None:
        """
        :return: The repository the remote points at, ``None`` when it names none - a
            remote given as a local path.
        """
        url = self.git.attempt("remote", "get-url", self.remote).output or self.remote
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
            f"+refs/heads/{self.name}:{self.local_reference}",
        )
        return self.git.commit_at(self.local_reference)

    def read(self, commit: str, path: str) -> str | None:
        """
        :param commit: The commit to read from.
        :param path: The file's path from the branch's root.
        :return: Its text without the final newline, or ``None`` when the commit has
            no such file.
        """
        shown = self.git.attempt("show", f"{commit}:{path}")
        return shown.output if shown.succeeded else None

    def commit(self, parent: str | None, files: dict[str, str], message: str) -> str:
        """
        Commit files on top of the branch, keeping every file not given.

        :param parent: The commit to build on, ``None`` for the branch's first.
        :param files: What to write, by path, each without its final newline.
        :param message: The commit message.
        :return: The new commit.
        """
        with tempfile.TemporaryDirectory() as scratch:
            index = {"GIT_INDEX_FILE": str(Path(scratch) / "index")}
            if parent is None:
                self.git.run("read-tree", "--empty", environment=index)
            else:
                self.git.run("read-tree", parent, environment=index)
            for path, text in files.items():
                blob_file = Path(scratch) / "blob"
                blob_file.write_text(text + "\n")
                blob = self.git.run("hash-object", "-w", str(blob_file))
                self.git.run(
                    "update-index",
                    "--add",
                    "--cacheinfo",
                    f"100644,{blob},{path}",
                    environment=index,
                )
            tree = self.git.run("write-tree", environment=index)
        parents = ["-p", parent] if parent else []
        return self.git.run("commit-tree", tree, *parents, "-m", message)

    def write(self, files: dict[str, str], message: str, attempts: int = 3) -> str:
        """
        Commit files onto the branch's latest tip and push them, again on top of another
        writer's commit when that landed first.

        :param files: What to write, by path, each without its final newline.
        :param message: The commit message.
        :param attempts: How many times to commit and push before giving up.
        :return: The pushed commit.
        :raises GitCommandFailed: If the last push is refused too.
        """
        for _ in range(attempts):
            commit = self.commit(self.fetch(), files, message)
            pushed = self.git.push(
                ProposedPush(self.remote, f"{commit}:refs/heads/{self.name}")
            )
            if pushed.succeeded:
                return commit
        pushed.raise_if_failed()
        return commit
