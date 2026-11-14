"""
Whether one branch of a remote merges into another, decided by git from a fresh fetch.

The answer never depends on a hosted service's lazily computed mergeable state: the same
two commits always give the same verdict and the same conflicting paths.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path

from basstler.exit_codes import StackExitCode
from basstler.git.commands import GitCommandFailed, GitCommandRunner
from basstler.stack.checkout import GitArgument, MergeTreeStatus
from basstler.stack.report import MergeVerdict
from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""

# %% where the probed branches are kept


class ProbedReference(StrEnum):
    """
    Where a probe keeps the two branches it fetched, so it never moves a remote-tracking
    branch or ``FETCH_HEAD``.
    """

    BASE = "refs/basstler/merge-probe/base"
    """
    The branch merged into.
    """

    HEAD = "refs/basstler/merge-probe/head"
    """
    The branch merged.
    """


class MergeTreeOption(StrEnum):
    """
    The ``git merge-tree`` flags a probe passes beside :attr:`GitArgument.WRITE_TREE`.
    """

    NAME_ONLY = "--name-only"
    """
    Lists each conflicting path once, without its stages.
    """

    NO_MESSAGES = "--no-messages"
    """
    Leaves out the informational messages after the paths.
    """


# %% the verdict


@dataclass(frozen=True)
class MergeProbeResult:
    """
    What merging one fetched branch into another gives.
    """

    base_location: str
    """
    The remote name or URL the base branch was fetched from.
    """

    base_commit: str
    """
    The commit the base branch pointed at when it was fetched.
    """

    head_commit: str
    """
    The commit the head branch pointed at when it was fetched.
    """

    verdict: MergeVerdict
    """
    Whether the merge is clean.
    """

    conflicting_paths: tuple[str, ...]
    """
    Every path the merge conflicts in, sorted; empty when it is clean.
    """

    @property
    def exit_code(self) -> StackExitCode:
        """
        :return: The status the command ends with for this verdict.
        """
        if self.verdict is MergeVerdict.CLEAN:
            return StackExitCode.SUCCESS
        return StackExitCode.MERGE_CONFLICTS

    def print_report(self) -> None:
        """
        Print the result as one JSON object, and describe a conflict on stderr.
        """
        logger.info(json.dumps(asdict(self), sort_keys=True))
        if self.verdict is MergeVerdict.CLEAN:
            return
        logger.error(
            "%s: commit %s does not merge cleanly into %s's commit %s; it conflicts "
            "in %s",
            self.exit_code.name_for_a_caller,
            self.head_commit,
            self.base_location,
            self.base_commit,
            ", ".join(self.conflicting_paths),
        )


# %% the probe


@dataclass(frozen=True)
class MergeProbe:
    """
    A merge of one branch of a remote into another, run without touching any branch or
    the working tree.
    """

    head_location: str
    """
    The remote name or URL the head branch is fetched from.
    """

    base_location: str
    """
    The remote name or URL the base branch is fetched from.
    """

    base: str
    """
    The branch merged into, such as a pull request's base.
    """

    head: str
    """
    The branch merged, such as a pull request's head.
    """

    def run(self, working_directory: Path) -> MergeProbeResult:
        """
        Fetch both branches and merge them.

        :param working_directory: The checkout to fetch into.
        :return: The verdict on the commits just fetched.
        :raises GitCommandFailed: If either branch cannot be fetched, or git cannot
            merge them for a reason other than a conflict.
        """
        git = GitCommandRunner(working_directory)
        for location, branch, reference in (
            (self.base_location, self.base, ProbedReference.BASE),
            (self.head_location, self.head, ProbedReference.HEAD),
        ):
            git.run(
                GitArgument.FETCH,
                GitArgument.QUIET,
                GitArgument.NO_WRITE_FETCH_HEAD,
                location,
                f"+refs/heads/{branch}:{reference}",
            )
        merge = git.attempt(
            GitArgument.MERGE_TREE,
            GitArgument.WRITE_TREE,
            MergeTreeOption.NAME_ONLY,
            MergeTreeOption.NO_MESSAGES,
            ProbedReference.BASE,
            ProbedReference.HEAD,
        )
        if merge.exit_status not in set(MergeTreeStatus):
            raise GitCommandFailed(
                status=merge.exit_status,
                detail=merge.error_output,
                arguments=merge.arguments,
            )
        clean = merge.exit_status == MergeTreeStatus.CLEAN
        return MergeProbeResult(
            base_location=self.base_location,
            base_commit=git.run(GitArgument.REVISION_PARSE, ProbedReference.BASE),
            head_commit=git.run(GitArgument.REVISION_PARSE, ProbedReference.HEAD),
            verdict=MergeVerdict.CLEAN if clean else MergeVerdict.CONFLICTS,
            conflicting_paths=tuple(sorted(set(merge.output.splitlines()[1:]))),
        )
