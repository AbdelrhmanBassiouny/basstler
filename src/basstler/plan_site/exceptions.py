"""
The errors publishing and building the plan site raise.
"""

from __future__ import annotations

from dataclasses import dataclass

from basstler.exceptions import DataclassException
from basstler.repository import Repository

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
