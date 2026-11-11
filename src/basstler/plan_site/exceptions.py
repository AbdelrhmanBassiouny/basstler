"""
The errors publishing and building the plan site raise.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import Enum, StrEnum

from basstler.class_property import classproperty
from basstler.exceptions import DataclassException
from basstler.exit_codes import CommandFailure, StackExitCode
from basstler.github.credential import GitHubCommand
from basstler.github.client import SERVER_ERROR_STATUSES
from basstler.github.exceptions import (
    GitHubCallFailed,
    GitHubCredentialRejected,
    GitHubRepositoryMoved,
    GitHubUnreachableError,
)
from basstler.maintenance.git_commands import GitCommandFailed, GitCommandResult
from basstler.repository import GitHubAddress, Repository
from basstler.repository_attachment import SessionProxyAnswer

# %% publishing the site


@dataclass
class NotesRepositoryUnresolvedError(DataclassException, LookupError):
    """
    Raised when the notes remote names no GitHub repository, so there is nothing to
    publish the site for.
    """

    notes_remote: str
    """
    The notes remote as configured.
    """

    def error_message(self) -> str:
        return f"the notes remote '{self.notes_remote}' names no GitHub repository"

    def suggest_correction(self) -> str:
        return (
            "point the notes remote at a GitHub repository with /setup-personal-notes"
        )


class SiteReadFailure(Enum):
    """
    Why the site repository could not be read, each with its own fix.
    """

    REPOSITORY_NOT_ATTACHED = "this session's proxy answers that it is not attached"
    """
    A cloud session's proxy refused it in GitHub's place.
    """

    CREDENTIAL_REFUSED = (
        "GitHub refuses this session's credential, as it does for a private repository "
        "its account cannot read, an organization that requires SSO, or a repository "
        "the Claude GitHub App is not installed on"
    )
    """
    GitHub itself refused the credential.
    """

    GITHUB_UNAVAILABLE = "GitHub did not answer, or answered with a server error"
    """
    The network or GitHub failed, which clears without any change here.
    """

    REFUSAL_WITH_ITS_OWN_FIX = "GitHub's refusal says how to fix it"
    """
    The credential is rejected, or the repository moved.
    """

    @classmethod
    def of(cls, refusal: GitHubCallFailed) -> SiteReadFailure:
        """
        :param refusal: Why reading the site repository failed.
        :return: The reason it stands for.
        """
        if isinstance(refusal, (GitHubCredentialRejected, GitHubRepositoryMoved)):
            return cls.REFUSAL_WITH_ITS_OWN_FIX
        if isinstance(refusal, GitHubUnreachableError):
            return cls.GITHUB_UNAVAILABLE
        if refusal.status in SERVER_ERROR_STATUSES:
            return cls.GITHUB_UNAVAILABLE
        if SessionProxyAnswer.REPOSITORY_NOT_ATTACHED in refusal.detail:
            return cls.REPOSITORY_NOT_ATTACHED
        return cls.CREDENTIAL_REFUSED


@dataclass
class SiteRepositoryUnreachableError(CommandFailure, DataclassException):
    """
    Raised when GitHub refuses to show the site repository, so whether it exists, and
    whether creating it would help, is not known.
    """

    @classproperty
    def exit_code(cls) -> StackExitCode:
        """:return: The status this kind of error ends a command with."""
        return StackExitCode.GITHUB_REQUEST_FAILED

    site_repository: Repository
    """
    The repository that builds and serves the plan site.
    """

    refusal: GitHubCallFailed
    """
    Why GitHub would not show it.
    """

    remedy: str
    """
    How this session comes to read the site repository, and the command to run then.
    """

    retry_command: str
    """
    The command that publishes again.
    """

    waits: tuple[timedelta, ...]
    """
    The wait before each time the read was asked again, first first.
    """

    @property
    def cause(self) -> SiteReadFailure:
        """:return: Why the site repository could not be read."""
        return SiteReadFailure.of(self.refusal)

    def error_message(self) -> str:
        return (
            f"cannot read the site repository {self.site_repository.full_name}, "
            f"so whether it exists is not known: {self.refusal.error_message()}"
        )

    def suggest_correction(self) -> str:
        explained = f"Do not create it again: it may exist, but {self.cause.value}."
        if self.cause is SiteReadFailure.GITHUB_UNAVAILABLE:
            waited = sum(self.waits, timedelta()).total_seconds()
            return (
                f"{explained} Attempts made: {len(self.waits) + 1}, with {waited:g} "
                f"seconds of waiting between them. {GitHubAddress.STATUS} shows "
                f"whether GitHub has an incident; if it has none, this session's "
                f"network may be failing. Run {self.retry_command} once it recovers."
            )
        if self.cause is SiteReadFailure.REFUSAL_WITH_ITS_OWN_FIX:
            return (
                f"{explained} {self.refusal.suggest_correction()} Then run "
                f"{self.retry_command}."
            )
        return f"{explained} {self.remedy}"


class PushRefusal(StrEnum):
    """
    Why GitHub refused a push, each member's value the text git reports it with.
    """

    NO_CREDENTIAL = "could not read Username"
    """
    Git has no credential to push to GitHub over HTTPS.
    """

    MISSING_WORKFLOW_SCOPE = "without `workflow` scope"
    """
    The credential's OAuth token may not write workflow files.
    """

    @classmethod
    def read_from(cls, error_output: str) -> PushRefusal | None:
        """
        :param error_output: What git printed refusing a push.
        :return: The refusal it reports, ``None`` when it reports none of these.
        """
        return next((refusal for refusal in cls if refusal in error_output), None)

    @property
    def fix(self) -> GitHubCommand:
        """
        The command that lifts the refusal.
        """
        match self:
            case PushRefusal.NO_CREDENTIAL:
                return GitHubCommand.LOG_IN
            case PushRefusal.MISSING_WORKFLOW_SCOPE:
                return GitHubCommand.REFRESH_WORKFLOW_SCOPE


@dataclass(kw_only=True)
class PublicationPushRefusedError(GitCommandFailed):
    """
    Raised when a repository refuses a push publishing the plan site.
    """

    notes_remote: str
    """
    The notes remote, whose transport publication reaches every repository over.
    """

    notes_repository: Repository
    """
    The repository :attr:`notes_remote` points at.
    """

    @classmethod
    def from_push(
        cls, push: GitCommandResult, notes_remote: str, notes_repository: Repository
    ) -> PublicationPushRefusedError:
        """
        :param push: The refused push.
        :param notes_remote: The notes remote.
        :param notes_repository: The repository the notes remote points at.
        :return: The error reporting it.
        """
        return cls(
            status=push.exit_status,
            detail=push.error_output,
            arguments=push.arguments,
            notes_remote=notes_remote,
            notes_repository=notes_repository,
        )

    @property
    def refusal(self) -> PushRefusal | None:
        """
        Why the push was refused, ``None`` when git does not say.
        """
        return PushRefusal.read_from(self.detail)

    def suggest_correction(self) -> str:
        """
        :return: Unlike :meth:`ExternalCallFailed.suggest_correction`, the fix for
            :attr:`refusal`, every fix when git names none, and reaching GitHub over SSH.
        """
        refusals = [self.refusal] if self.refusal else list(PushRefusal)
        fixes = " or ".join(f"`{refusal.fix}`" for refusal in refusals)
        ssh_url = self.notes_repository.clone_url_under(GitHubAddress.SSH)
        return (
            f"run {fixes}, or reach GitHub over SSH: point the notes remote "
            f"'{self.notes_remote}' at {ssh_url}, and publication pushes every "
            "repository over SSH"
        )


# %% reading the hub file


@dataclass
class RegistryUnreadableError(DataclassException):
    """
    Raised when the registry's notes branch cannot be fetched, so the site cannot know
    which repositories to publish.
    """

    registry: Repository
    """
    The repository whose notes hold the hub file.
    """

    notes_branch: str
    """
    The branch the hub file was looked for on.
    """

    private_repository_correction: str
    """
    How the build comes to read the registry should it be private, as a clause of the
    correction.
    """

    def error_message(self) -> str:
        return f"cannot fetch {self.notes_branch} from the registry {self.registry}"

    def suggest_correction(self) -> str:
        return (
            f"Check that {self.registry} exists, that it has a {self.notes_branch} "
            "branch, and that the build's credential can read it: "
            f"{self.private_repository_correction}."
        )


# %% storing the token


@dataclass
class PlanSiteUnrecordedError(DataclassException, LookupError):
    """
    Raised when the notes branch records no plan site, so a token has no build to start.
    """

    notes_branch: str
    """
    The notes branch that was read.
    """

    def error_message(self) -> str:
        return f"{self.notes_branch} records no plan site"

    def suggest_correction(self) -> str:
        return "set the plan site up with /setup-personal-notes"


@dataclass
class PlanSiteTokenNotEnteredError(DataclassException, ValueError):
    """
    Raised when no token was typed at the hidden terminal prompt that asks for it.
    """

    secret: str
    """
    The secret the token was to be stored as.
    """

    terminal: bool
    """
    Whether a terminal was attached to ask on.
    """

    def error_message(self) -> str:
        if not self.terminal:
            return (
                f"{self.secret} is asked for only at a hidden terminal prompt, and no "
                "terminal is attached"
            )
        return f"no token was entered for {self.secret}"

    def suggest_correction(self) -> str:
        return (
            "run the command in your own terminal and paste the token at its hidden "
            "prompt; never paste it into a chat, a command line or a file"
        )
