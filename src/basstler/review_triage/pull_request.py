"""
The pull request triaged, as GitHub's REST API describes it, and the files it changes,
as git reads them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Annotated

from pydantic import Field

from basstler.github.client import GitHubReader
from basstler.github.web_page import AbsentAsEmpty
from basstler.json_model import ValidatedJSONModel
from basstler.maintenance.git_commands import GitCommandRunner
from basstler.repository import Repository
from basstler.review_triage.comparison import FileChange

# %% the pull request


class BranchTip(ValidatedJSONModel):
    """
    One end of a pull request: a branch and the commit it points at.
    """

    commit: Annotated[str, Field(alias="sha")]
    """
    The commit the branch points at.
    """

    branch: Annotated[str, Field(alias="ref")]
    """
    The branch's name.
    """


class TriagedPullRequest(ValidatedJSONModel):
    """
    The pull request whose files are triaged.
    """

    number: int
    """
    Its number in its repository.
    """

    node_identifier: Annotated[str, Field(alias="node_id")]
    """
    What GitHub's GraphQL API identifies it by.
    """

    description: Annotated[str, AbsentAsEmpty(), Field(alias="body")]
    """
    Its description, in Markdown; empty when it has none.
    """

    base: BranchTip
    """
    The branch it merges into.
    """

    head: BranchTip
    """
    The branch carrying its changes.
    """

    @property
    def head_reference(self) -> str:
        """
        The ref the base repository keeps the pull request's head commit under.
        """
        return f"refs/pull/{self.number}/head"


# %% the changed files


@dataclass(frozen=True)
class CommitRange:
    """
    The change between a pull request's merge base and its head commit, as GitHub shows
    it.
    """

    git: GitCommandRunner
    """
    The checkout holding both commits.
    """

    base_commit: str
    """
    Where the pull request's branch left its base branch.
    """

    head_commit: str
    """
    The pull request's head commit.
    """

    def changes(self) -> tuple[FileChange, ...]:
        """
        :return: Every file the range changes, in the order git lists them.
        """
        listing = iter(
            self.git.run(
                "diff",
                "--numstat",
                "-z",
                "--find-renames",
                self.base_commit,
                self.head_commit,
            ).split("\0")
        )
        changes: list[FileChange] = []
        for entry in listing:
            if not entry:
                continue
            added, _, path = entry.split("\t", 2)
            previous_path = None
            if not path:
                previous_path = PurePosixPath(next(listing))
                path = next(listing)
            changes.append(
                self.change(PurePosixPath(path), previous_path, added == "-")
            )
        return tuple(changes)

    def change(
        self, path: PurePosixPath, previous_path: PurePosixPath | None, is_binary: bool
    ) -> FileChange:
        """
        :param path: Where the file is in the head commit.
        :param previous_path: Where it was in the base commit, when it moved.
        :param is_binary: Whether git compares it as binary.
        :return: The file's change, its texts read unless it is binary.
        """
        if is_binary:
            return FileChange(path, None, None, previous_path, is_binary)
        return FileChange(
            path,
            self.git.file_at(self.base_commit, previous_path or path),
            self.git.file_at(self.head_commit, path),
            previous_path,
        )


@dataclass(frozen=True)
class PullRequestChanges:
    """
    A pull request and the files it changes, everything a triage reads.
    """

    pull_request: TriagedPullRequest
    """
    The pull request.
    """

    commits: CommitRange
    """
    The commits its change runs between.
    """

    files: tuple[FileChange, ...]
    """
    Every file it changes.
    """


# %% reading a pull request


@dataclass(frozen=True)
class PullRequestReader:
    """
    Reads pull requests of GitHub and their changes in one checkout.
    """

    git: GitCommandRunner
    """
    The checkout the changes are read in.
    """

    github: GitHubReader
    """
    Where the pull request is read from.
    """

    def read(self, repository: Repository, number: int) -> PullRequestChanges:
        """
        :param repository: The repository the pull request is opened on.
        :param number: The pull request's number.
        :return: The pull request and its changes, its commits fetched first when the
            checkout lacks either end.
        """
        pull_request = TriagedPullRequest.from_json(
            self.github.get(repository.pull_request_path(number))
        )
        if None in (
            self.git.commit_or_none(pull_request.base.commit),
            self.git.commit_or_none(pull_request.head.commit),
        ):
            self.git.fetch(
                repository.clone_url,
                pull_request.head_reference,
                pull_request.base.branch,
            )
        merge_base = self.git.run(
            "merge-base", pull_request.base.commit, pull_request.head.commit
        )
        commits = CommitRange(self.git, merge_base, pull_request.head.commit)
        return PullRequestChanges(pull_request, commits, commits.changes())
