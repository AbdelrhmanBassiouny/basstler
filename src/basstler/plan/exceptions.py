"""
The refusals a plan save ends with when the plan changed since the session read it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from basstler.class_property import classproperty
from basstler.exceptions import DataclassException
from basstler.exit_codes import CommandFailure, ManifestToolsExitCode

if TYPE_CHECKING:
    from basstler.plan.merge import PlanPart

# %% the plan changed since it was read


@dataclass
class ConcurrentEditError(CommandFailure, DataclassException, RuntimeError):
    """
    Raised when another writer changed a part of the plan the session also changed,
    since the session read it, to a different value.
    """

    @classproperty
    def exit_code(cls) -> ManifestToolsExitCode:
        """:return: The status this kind of error ends a command with."""
        return ManifestToolsExitCode.CHANGED_SINCE_READ

    plan_identifier: str
    """
    The plan being saved.
    """

    parts: tuple[PlanPart, ...]
    """
    Every part both writers changed, in the order the plan holds them.
    """

    def error_message(self) -> str:
        return (
            f"plan {self.plan_identifier!r} changed since it was read, in parts this "
            f"save also changes: {', '.join(part.description for part in self.parts)}"
        )

    def suggest_correction(self) -> str:
        return (
            "Read the plan again, apply the edit to what is there now, and save that."
        )


@dataclass
class PlanRemovedSinceReadError(CommandFailure, DataclassException, RuntimeError):
    """
    Raised when the plan the session read is no longer on the notes branch.
    """

    @classproperty
    def exit_code(cls) -> ManifestToolsExitCode:
        """:return: The status this kind of error ends a command with."""
        return ManifestToolsExitCode.CHANGED_SINCE_READ

    plan_identifier: str
    """
    The plan being saved.
    """

    def error_message(self) -> str:
        return (
            f"plan {self.plan_identifier!r} was removed from the notes branch since it "
            "was read"
        )

    def suggest_correction(self) -> str:
        return (
            "A plan is removed once every item has landed; check the notes branch "
            "before saving it again."
        )


@dataclass
class MergeDisagreesError(CommandFailure, DataclassException, RuntimeError):
    """
    Raised when the merged manifest does not read back as the merge decided, so writing
    it would change parts neither writer changed.
    """

    @classproperty
    def exit_code(cls) -> ManifestToolsExitCode:
        """:return: The status this kind of error ends a command with."""
        return ManifestToolsExitCode.MERGE_DISAGREES

    plan_identifier: str
    """
    The plan being saved.
    """

    parts: tuple[PlanPart, ...]
    """
    Every part whose merged value differs from the one the merge chose.
    """

    def error_message(self) -> str:
        return (
            f"merging the save of plan {self.plan_identifier!r} would change "
            f"{', '.join(part.description for part in self.parts)} unexpectedly"
        )

    def suggest_correction(self) -> str:
        return (
            "Save from a fresh read of the plan, so there is nothing to merge, and "
            "report the manifest that failed to merge."
        )
