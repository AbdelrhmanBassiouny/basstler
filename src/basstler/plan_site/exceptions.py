"""
The errors publishing and building the plan site raise.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from basstler.exceptions import DataclassException
from basstler.github.credential import GitHubCommand
from basstler.maintenance.git_commands import GitCommandFailed, GitCommandResult
from basstler.repository import GitHubAddress, Repository

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
