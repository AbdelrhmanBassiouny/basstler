"""
A whole pull request triaged: its renames and the verdict on each file it changes.
"""

from __future__ import annotations

from dataclasses import dataclass

from basstler.class_property import classproperty
from basstler.github.client import GitHubReader
from basstler.locations import ReviewTriageLocation
from basstler.maintenance.git_commands import GitCommandRunner
from basstler.render_common import TemplatePage
from basstler.repository import Repository
from basstler.review_triage.comparison import (
    FileNeedingReview,
    FileTriage,
    FileTriager,
    MechanicalFile,
)
from basstler.review_triage.detection import CommitTree, RenameDetection
from basstler.review_triage.pull_request import (
    DECLARATION_MARKER,
    CommitRange,
    TriageDeclaration,
    TriagedPullRequest,
)
from basstler.review_triage.renames import RenameMap

# %% the triage


@dataclass(frozen=True)
class PullRequestTriage(TemplatePage):
    """
    Which of a pull request's files a reviewer has to read.
    """

    pull_request: TriagedPullRequest
    """
    The pull request triaged.
    """

    renames: RenameMap
    """
    The renames applied in judging its files.
    """

    files: tuple[FileTriage, ...]
    """
    The verdict on each file it changes.
    """

    @classmethod
    def of(
        cls, git: GitCommandRunner, pull_request: TriagedPullRequest
    ) -> PullRequestTriage:
        """
        :param git: A checkout holding both ends of the pull request.
        :param pull_request: The pull request.
        :return: The verdict on each of its files.
        """
        commits = CommitRange.of(git, pull_request)
        changes = commits.changes()
        declaration = TriageDeclaration.of_description(pull_request.description)
        detection = RenameDetection(
            CommitTree(git, commits.base_commit), CommitTree(git, commits.head_commit)
        )
        renames = RenameMap.combined(
            detection.detected(changes).items(),
            declaration.renames,
            declaration.rejected_renames,
        )
        triager = FileTriager(renames)
        return cls(
            pull_request, renames, tuple(triager.triage(change) for change in changes)
        )

    @property
    def mechanical_files(self) -> tuple[MechanicalFile, ...]:
        """
        The files a reviewer need not read.
        """
        return tuple(file for file in self.files if isinstance(file, MechanicalFile))

    @property
    def files_needing_review(self) -> tuple[FileNeedingReview, ...]:
        """
        The files a reviewer has to read.
        """
        return tuple(file for file in self.files if isinstance(file, FileNeedingReview))

    @classproperty
    def template(cls) -> str:
        return ReviewTriageLocation.REPORT_TEMPLATE.name

    def render(self) -> str:
        """
        :return: The triage as a Markdown report.
        """
        return self.render_template(triage=self, marker=DECLARATION_MARKER)


# %% reading a pull request's triage


@dataclass(frozen=True)
class PullRequestTriageReader:
    """
    Triages pull requests of GitHub in one checkout.
    """

    git: GitCommandRunner
    """
    The checkout the files are compared in.
    """

    github: GitHubReader
    """
    Where the pull request is read from.
    """

    def read(self, repository: Repository, number: int) -> PullRequestTriage:
        """
        :param repository: The repository the pull request is opened on.
        :param number: The pull request's number.
        :return: The pull request triaged, its commits fetched first when the checkout
            lacks either end.
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
        return PullRequestTriage.of(self.git, pull_request)
