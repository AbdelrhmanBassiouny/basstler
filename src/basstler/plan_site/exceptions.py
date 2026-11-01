"""
The reasons publishing the plan site stops before it starts.
"""

from __future__ import annotations

from dataclasses import dataclass

from basstler.exceptions import DataclassException


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
