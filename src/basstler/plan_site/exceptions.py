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

    def error_message(self) -> str:
        return f"cannot fetch {self.notes_branch} from the registry {self.registry}"

    def suggest_correction(self) -> str:
        return (
            f"Check that {self.registry} exists, that it has a {self.notes_branch} "
            f"branch, and that the build's credential can read it."
        )
