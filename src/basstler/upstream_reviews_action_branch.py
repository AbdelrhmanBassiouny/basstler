"""
The branch of the fork the upstream-reviews Action lives on, and installing it.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from basstler.repository import MalformedRepositoryError, Repository
from basstler.upstream_reviews_errors import UpstreamReadError
from basstler.upstream_reviews_vocabulary import (
    ActionBranch,
    ActionFile,
    BasstlerSource,
)

# %% the branch


@dataclass
class GitCommandFailed(UpstreamReadError):
    """
    Raised when a git command this module runs exits non-zero.
    """

    arguments: list[str]
    """
    What git was given.
    """

    error_output: str
    """
    What it wrote to standard error.
    """

    def describe(self) -> str:
        """:return: The message a caller should see."""
        return f"git {' '.join(self.arguments)} failed: {self.error_output}"


WORKFLOW_TEMPLATE = """\
# Written by basstler's /setup-personal-notes (python -m basstler.setup_steps
# install-upstream-reviews-action); re-run that to update it rather than editing it here.
name: Upstream reviews

on:
  push:
    branches: [{branch}]
    paths: [{request}]

permissions:
  contents: write

concurrency:
  group: basstler-upstream-reviews
  cancel-in-progress: false

jobs:
  read:
    uses: {repository}/{reusable_workflow}@{branch_or_tag}
    with:
      basstler_branch_or_tag: {branch_or_tag}
"""
"""
The caller workflow, filled in by :meth:`ActionInstallation.workflow`.
"""

README_TEXT = f"""\
# basstler upstream reviews

Kept by basstler's `/upstream-reviews` skill. Pushing a new `{ActionFile.REQUEST}` runs
`{ActionFile.WORKFLOW}`, which reads the upstream pull request it names and commits
`{ActionFile.RESULT}`. Nothing on this branch is ever merged anywhere.

Install or update it with `/setup-personal-notes`, which runs
`python -m basstler.setup_steps install-upstream-reviews-action`.
"""
"""
What a reader browsing the fork's branches finds there.
"""

WORKFLOW_REFERENCE = re.compile(
    r"^\s*basstler_branch_or_tag:\s*(?P<branch_or_tag>\S+)\s*$", re.MULTILINE
)
"""
The line of an installed workflow naming the basstler branch or tag it runs.
"""


@dataclass(frozen=True)
class Git:
    """
    Runs git in one clone.
    """

    project_root: Path
    """
    The clone.
    """

    def run(
        self,
        *arguments: str,
        environment: dict[str, str] | None = None,
        check: bool = True,
    ) -> str:
        """
        :param arguments: What to pass git.
        :param environment: Variables to add to the process's own.
        :param check: Whether a non-zero exit is an error.
        :return: What git printed, stripped.
        :raises GitCommandFailed: If it exits non-zero and *check* is set.
        """
        completed = subprocess.run(
            ["git", *arguments],
            cwd=self.project_root,
            capture_output=True,
            text=True,
            env={**os.environ, **(environment or {})},
        )
        if check and completed.returncode != 0:
            raise GitCommandFailed(list(arguments), completed.stderr.strip())
        return completed.stdout.strip() if completed.returncode == 0 else ""


@dataclass(frozen=True)
class RemoteBranch:
    """
    The Action branch on one remote, read and written without touching the working tree.
    """

    git: Git
    """
    The clone to work in.
    """

    remote: str
    """
    The fork's remote.
    """

    @property
    def fork(self) -> Repository | None:
        """
        :return: The repository the remote points at, ``None`` when it names none - a
            remote given as a local path.
        """
        url = self.git.run("remote", "get-url", self.remote, check=False) or self.remote
        try:
            return Repository.from_remote_url(url)
        except MalformedRepositoryError:
            return None

    @property
    def description(self) -> str:
        """:return: The fork's name, or the remote's where it names none."""
        fork = self.fork
        return fork.full_name if fork else self.remote

    def fetch(self) -> str | None:
        """
        :return: The branch's tip commit, or ``None`` when the remote has no such branch.
        """
        if not self.git.run(
            "ls-remote", "--heads", self.remote, ActionBranch.NAME, check=False
        ):
            return None
        self.git.run(
            "fetch",
            "--quiet",
            "--no-tags",
            self.remote,
            f"+refs/heads/{ActionBranch.NAME}:{ActionBranch.LOCAL_REFERENCE}",
        )
        return self.git.run("rev-parse", ActionBranch.LOCAL_REFERENCE)

    def read(self, commit: str, path: ActionFile) -> str | None:
        """
        :param commit: The commit to read from.
        :param path: The file.
        :return: Its text, or ``None`` when the commit has no such file.
        """
        shown = subprocess.run(
            ["git", "show", f"{commit}:{path}"],
            cwd=self.git.project_root,
            capture_output=True,
            text=True,
        )
        return shown.stdout if shown.returncode == 0 else None

    def commit(
        self, parent: str | None, files: dict[ActionFile, str], message: str
    ) -> str:
        """
        Commit files on top of the branch, keeping every file not given.

        :param parent: The commit to build on, ``None`` for the branch's first.
        :param files: What to write, by path.
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
                blob_file.write_text(text)
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

    def push(self, commit: str) -> None:
        """
        Move the branch to *commit*, which has to descend from where it is now.

        :param commit: The new tip.
        """
        self.git.run(
            "push", "--quiet", self.remote, f"{commit}:refs/heads/{ActionBranch.NAME}"
        )

    def write(self, files: dict[ActionFile, str], message: str) -> str:
        """
        Commit files onto the branch's latest tip and push them, once more if a run's
        own commit landed first.

        :param files: What to write, by path.
        :param message: The commit message.
        :return: The pushed commit.
        """
        for attempt in range(3):
            commit = self.commit(self.fetch(), files, message)
            try:
                self.push(commit)
                return commit
            except GitCommandFailed:
                if attempt == 2:
                    raise
        raise AssertionError("unreachable")


# %% installing


class InstallationState(StrEnum):
    """
    How the fork's Action compares with the release installing it.
    """

    MISSING = "missing"
    STALE = "stale"
    CURRENT = "current"


@dataclass(frozen=True)
class ActionInstallation:
    """
    The Action as one basstler release writes it.
    """

    branch_or_tag: str
    """
    The basstler branch or release tag the workflow runs.
    """

    @property
    def workflow(self) -> str:
        """:return: The caller workflow."""
        return WORKFLOW_TEMPLATE.format(
            branch=ActionBranch.NAME,
            request=ActionFile.REQUEST,
            repository=BasstlerSource.REPOSITORY,
            reusable_workflow=BasstlerSource.REUSABLE_WORKFLOW,
            branch_or_tag=self.branch_or_tag,
        )

    @property
    def files(self) -> dict[ActionFile, str]:
        """:return: What installing writes."""
        return {ActionFile.WORKFLOW: self.workflow, ActionFile.README: README_TEXT}

    def state(self, branch: RemoteBranch) -> tuple[InstallationState, str | None]:
        """
        :param branch: The fork's branch.
        :return: How it compares, and the branch or tag it runs when it is installed at
            all.
        """
        tip = branch.fetch()
        workflow = branch.read(tip, ActionFile.WORKFLOW) if tip else None
        if workflow is None:
            return InstallationState.MISSING, None
        match = WORKFLOW_REFERENCE.search(workflow)
        installed = match["branch_or_tag"] if match else None
        if workflow == self.workflow:
            return InstallationState.CURRENT, installed
        return InstallationState.STALE, installed

    def install(self, branch: RemoteBranch) -> bool:
        """
        :param branch: The fork's branch.
        :return: Whether anything had to be pushed.
        """
        if self.state(branch)[0] is InstallationState.CURRENT:
            return False
        branch.write(
            self.files, f"Run basstler {self.branch_or_tag}'s upstream-reviews Action"
        )
        return True
