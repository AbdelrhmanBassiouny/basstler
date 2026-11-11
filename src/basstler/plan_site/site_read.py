"""
What fixes a failed read of the site repository, chosen by why it failed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import timedelta

from basstler.github.client import GitHubResponse
from basstler.github.exceptions import (
    GitHubCredentialRejected,
    GitHubRepositoryMoved,
    GitHubRequestFailed,
    GitHubUnreachableError,
)
from basstler.plan_site.build_start import SiteAccess
from basstler.repository import GitHubAddress
from basstler.repository_attachment import SessionProxyAnswer

# %% the fixes


@dataclass(frozen=True)
class SiteReadFix(ABC):
    """
    What makes the site repository readable again, so publishing again succeeds.
    """

    @abstractmethod
    def describe(self) -> str:
        """
        :return: Why the read failed and what to do, ending with what to run then.
        """

    @classmethod
    def for_failed_read(
        cls, read: GitHubResponse, access: SiteAccess, in_cloud_session: bool
    ) -> SiteReadFix:
        """
        :param read: GitHub's answer to reading the site repository, which failed.
        :param access: How this session reaches the site repository, and what it runs
            then.
        :param in_cloud_session: Whether this runs in a Claude Code cloud session.
        :return: The fix for why the read failed.
        """
        refusal = read.failure
        if isinstance(refusal, (GitHubCredentialRejected, GitHubRepositoryMoved)):
            return RefusalCorrectionFix(refusal, access.retry_command)
        if isinstance(refusal, GitHubUnreachableError) or read.is_server_error:
            return GitHubOutageFix(read.waits, access.retry_command)
        if SessionProxyAnswer.REPOSITORY_NOT_ATTACHED in refusal.detail:
            return RepositoryAttachmentFix(access)
        return CredentialAccessFix(access, in_cloud_session)


@dataclass(frozen=True)
class RepositoryAttachmentFix(SiteReadFix):
    """
    A cloud session's proxy refused the read in GitHub's place: the repository is not
    attached to the session.
    """

    access: SiteAccess
    """
    How the session attaches the site repository, and what it runs then.
    """

    def describe(self) -> str:
        return (
            f"This session's proxy answers that it is not attached. "
            f"{self.access.remedy(in_cloud_session=True)}"
        )


@dataclass(frozen=True)
class CredentialAccessFix(SiteReadFix):
    """
    GitHub itself refused this session's credential.
    """

    access: SiteAccess
    """
    How the session gets access to the site repository, and what it runs then.
    """

    in_cloud_session: bool
    """
    Whether this runs in a Claude Code cloud session, which gets access by attaching the
    repository rather than by logging gh in.
    """

    def describe(self) -> str:
        return (
            f"GitHub refuses this session's credential, as it does for a private "
            f"repository its account cannot read, an organization that requires SSO, "
            f"or a repository the Claude GitHub App is not installed on. "
            f"{self.access.remedy(self.in_cloud_session)}"
        )


@dataclass(frozen=True)
class GitHubOutageFix(SiteReadFix):
    """
    GitHub did not answer, or answered with a server error: it clears without any change
    to the session's access.
    """

    waits: tuple[timedelta, ...]
    """
    The wait before each time the read was asked again, first first.
    """

    retry_command: str
    """
    The command to run once GitHub or the network recovers.
    """

    def describe(self) -> str:
        waited = sum(self.waits, timedelta()).total_seconds()
        return (
            f"GitHub did not answer, or answered with a server error. Attempts made: "
            f"{len(self.waits) + 1}, with {waited:g} seconds of waiting between them. "
            f"{GitHubAddress.STATUS} shows whether GitHub has an incident; if it has "
            f"none, this session's network may be failing. Run {self.retry_command} "
            f"once it recovers."
        )


@dataclass(frozen=True)
class RefusalCorrectionFix(SiteReadFix):
    """
    GitHub's refusal says how to fix it: the credential is rejected, or the repository
    moved.
    """

    refusal: GitHubRequestFailed
    """
    The refusal, whose own correction is the fix.
    """

    retry_command: str
    """
    The command to run once the refusal is fixed.
    """

    def describe(self) -> str:
        return f"{self.refusal.suggest_correction()} Then run {self.retry_command}."
