"""
The failures reading a plan stored as issues ends with.
"""

from __future__ import annotations

from dataclasses import dataclass

from basstler.exceptions import DataclassException

# %% an item issue that does not parse


@dataclass
class MalformedDependencyError(DataclassException, ValueError):
    """
    Raised when a line of an item issue's dependency list is not an issue reference.
    """

    line: str
    """
    The line that is not an issue reference.
    """

    def error_message(self) -> str:
        return f"the dependency line {self.line!r} is not an issue reference"

    def suggest_correction(self) -> str:
        return "Write each dependency as '- #<number>' or '- <owner>/<name>#<number>'."
