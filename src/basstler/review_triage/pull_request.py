"""
The pull request triaged, as GitHub's REST API describes it, its description's
declarations, and the files it changes, as git reads them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Annotated

import yaml
from pydantic import Field

from basstler.github.web_page import AbsentAsEmpty
from basstler.json_model import ValidatedJSONModel
from basstler.maintenance.git_commands import GitCommandRunner
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


# %% what the description declares

DECLARATION_MARKER = "review-triage"
"""
The word opening the HTML comment of a description that holds its declarations.
"""


class TriageDeclaration(ValidatedJSONModel):
    """
    What a pull request's description states about its renames, as YAML inside an ``<!--
    review-triage ...

    -->`` comment.
    """

    renames: dict[str, str] = Field(default_factory=dict)
    """
    The new identifier of each old identifier the pull request renames throughout.
    """

    rejected_renames: tuple[str, ...] = ()
    """
    Old identifiers whose detected rename is not a rename.
    """

    @classmethod
    def of_description(cls, description: str) -> TriageDeclaration:
        """
        :param description: A pull request's description.
        :return: Its declarations, none when it holds no declaration comment.
        :raises yaml.YAMLError: If the comment does not hold YAML.
        :raises pydantic.ValidationError: If the YAML does not have the model's shape.
        """
        match = re.search(
            rf"<!--\s*{re.escape(DECLARATION_MARKER)}\s*\n(.*?)-->",
            description,
            re.DOTALL,
        )
        if match is None:
            return cls()
        return cls.from_json(yaml.safe_load(match.group(1)) or {})


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

    @classmethod
    def of(cls, git: GitCommandRunner, pull_request: TriagedPullRequest) -> CommitRange:
        """
        :param git: A checkout holding both ends of the pull request.
        :param pull_request: The pull request.
        :return: Its change, from the merge base of its two ends.
        """
        merge_base = git.run(
            "merge-base", pull_request.base.commit, pull_request.head.commit
        )
        return cls(git, merge_base, pull_request.head.commit)

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
                previous_path = next(listing)
                path = next(listing)
            changes.append(self.change(path, previous_path, added == "-"))
        return tuple(changes)

    def change(
        self, path: str, previous_path: str | None, is_binary: bool
    ) -> FileChange:
        """
        :param path: Where the file is in the head commit.
        :param previous_path: Where it was in the base commit, when it moved.
        :param is_binary: Whether git compares it as binary.
        :return: The file's change, its texts read unless it is binary.
        """
        if is_binary:
            return FileChange(
                PurePosixPath(path),
                None,
                None,
                PurePosixPath(previous_path) if previous_path else None,
                True,
            )
        return FileChange(
            PurePosixPath(path),
            self.git.file_at(self.base_commit, previous_path or path),
            self.git.file_at(self.head_commit, path),
            PurePosixPath(previous_path) if previous_path else None,
        )
