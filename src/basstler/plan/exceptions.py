"""
The problems a plan.yaml can be invalid for, and the refusals a plan save ends with when
the plan changed since the session read it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from basstler.class_property import classproperty
from basstler.exceptions import DataclassException
from basstler.exit_codes import CommandFailure, ManifestToolsExitCode
from basstler.github.repository import Repository

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


# %% the repository's rules


@dataclass
class UnknownRepositoryRuleError(DataclassException, LookupError):
    """
    Raised when a rule is asked for that the repository's rules do not hold.
    """

    identifier: str
    """
    The id that was asked for.
    """

    known_identifiers: tuple[str, ...]
    """
    The ids the repository's rules hold, in order.
    """

    def error_message(self) -> str:
        return f"the repository's plan rules hold no rule {self.identifier!r}"

    def suggest_correction(self) -> str:
        return f"Use one of: {', '.join(self.known_identifiers) or 'none yet'}."


# %% plan validation


@dataclass
class ValidationProblem(DataclassException):
    """A single problem found while validating a plan.yaml - see plan-schema.md.

    One subclass per validation rule, carrying the fields that rule cares about;
    :class:`PlanValidator` raises them together as one :class:`PlanValidationError`.
    """

    def suggest_correction(self) -> str:
        """
        No validation rule suggests a correction of its own.
        """
        return ""


@dataclass
class InvalidManifestRoot(ValidationProblem):
    """The manifest didn't parse to a mapping - an empty file (``yaml.safe_load``
    returns ``None``) or a manifest whose top level is a list or scalar."""

    actual_value: Any
    """
    Whatever the manifest actually parsed to.
    """

    def error_message(self) -> str:
        return f"plan.yaml must parse to a mapping, got {type(self.actual_value).__name__}: {self.actual_value!r}"


@dataclass
class InvalidSchemaVersion(ValidationProblem):
    """
    The manifest's ``schema_version`` is missing or not :attr:`supported_version`.
    """

    actual_value: Any
    """
    Whatever ``schema_version`` actually held.
    """

    @classproperty
    def supported_version(cls) -> int:
        """
        The only ``schema_version`` a plan.yaml may declare.
        """
        return 1

    def error_message(self) -> str:
        return (
            f"schema_version must be {self.supported_version}, "
            f"got {self.actual_value!r}"
        )


@dataclass
class InvalidLandedItemCount(ValidationProblem):
    """
    The manifest's ``landed_item_count`` is not a whole number of at least zero.
    """

    actual_value: Any
    """
    Whatever ``landed_item_count`` actually held.
    """

    def error_message(self) -> str:
        return (
            f"landed_item_count must be a whole number of at least 0, "
            f"got {self.actual_value!r}"
        )


@dataclass
class DuplicateItemId(ValidationProblem):
    """
    Two or more items resolve to the same effective id.
    """

    duplicate_identifiers: list[str]
    """
    Every identifier that occurred more than once.
    """

    def error_message(self) -> str:
        return f"duplicate item id(s): {sorted(self.duplicate_identifiers)}"


@dataclass
class SharedBranch(ValidationProblem):
    """
    More than one item names the same branch, though a branch carries the work of
    exactly one item.
    """

    branch: str
    """
    The branch named more than once.
    """

    claiming_items: list[str]
    """
    Every item naming it: a bare id for an item of the validated plan, a ``<plan-
    id>/<item- id>`` reference for one in another plan.
    """

    def error_message(self) -> str:
        return (
            f"branch {self.branch!r} is named by several items: {self.claiming_items}"
        )

    def suggest_correction(self) -> str:
        """
        Unlike :meth:`ValidationProblem.suggest_correction`, names the item to keep the
        branch on.
        """
        return (
            "Keep the branch on the one item that owns it; fold each other item into "
            "it, or leave the branch off that item and say in its notes that it lands "
            "there."
        )


@dataclass
class UnknownTrack(ValidationProblem):
    """
    An item's ``track`` doesn't resolve to a declared track.
    """

    item_identifier: str
    """
    The offending item's effective id.
    """

    track: Any
    """
    Whatever ``track`` actually held.
    """

    def error_message(self) -> str:
        return f"item {self.item_identifier!r} has unknown track {self.track!r}"


@dataclass
class UnknownStatus(ValidationProblem):
    """
    An item's ``status`` isn't one of :class:`ItemStatus`'s values.
    """

    item_identifier: str
    """
    The offending item's effective id.
    """

    status: Any
    """
    Whatever ``status`` actually held.
    """

    def error_message(self) -> str:
        return f"item {self.item_identifier!r} has unknown status {self.status!r}"


@dataclass
class InvalidDependsOn(ValidationProblem):
    """
    An item's ``depends_on`` isn't a list.

    A plain string is iterable character-by-character in Python, so without this check a
    string ``depends_on`` would silently be misread as one dependency per character
    instead of failing loudly.
    """

    item_identifier: str
    """
    The offending item's effective id.
    """

    actual_type: type
    """
    The type ``depends_on`` actually held, instead of ``list``.
    """

    def error_message(self) -> str:
        return f"item {self.item_identifier!r} depends_on must be a list, got {self.actual_type.__name__}"


@dataclass
class InvalidBlockers(ValidationProblem):
    """
    An item's ``blockers`` isn't a list.

    A plain string is iterable character-by-character in Python, so without this check a
    string ``blockers`` would silently be misread as one blocker per character instead
    of failing loudly.
    """

    item_identifier: str
    """
    The offending item's effective id.
    """

    actual_type: type
    """
    The type ``blockers`` actually held, instead of ``list``.
    """

    def error_message(self) -> str:
        return f"item {self.item_identifier!r} blockers must be a list, got {self.actual_type.__name__}"


@dataclass
class UnknownDependency(ValidationProblem):
    """
    An item's ``depends_on`` names an id that doesn't resolve to another item.
    """

    item_identifier: str
    """
    The offending item's effective id.
    """

    dependency_identifier: str
    """
    The unresolvable id named in ``depends_on``.
    """

    def error_message(self) -> str:
        return f"item {self.item_identifier!r} depends_on unknown id {self.dependency_identifier!r}"


@dataclass
class UnknownDependencyPlan(ValidationProblem):
    """
    An item's ``depends_on`` names a plan that isn't in the plans directory.
    """

    item_identifier: str
    """
    The offending item's effective id.
    """

    dependency_identifier: str
    """
    The whole reference, as the manifest wrote it.
    """

    def error_message(self) -> str:
        return f"item {self.item_identifier!r} depends_on {self.dependency_identifier!r}, whose plan is not in the plans directory"


@dataclass
class SelfPlanReference(ValidationProblem):
    """
    An item's ``depends_on`` qualifies an id with this plan's own id.

    The bare id already names that item, so admitting the qualified form would give one
    edge two spellings.
    """

    item_identifier: str
    """
    The offending item's effective id.
    """

    dependency_identifier: str
    """
    The whole reference, as the manifest wrote it.
    """

    def error_message(self) -> str:
        return f"item {self.item_identifier!r} depends_on {self.dependency_identifier!r}, which is this plan - name it by its bare id"


@dataclass
class MalformedDependencyReference(ValidationProblem):
    """
    An item's ``depends_on`` entry is neither a bare id nor ``<plan-id>/<item-id>``.
    """

    item_identifier: str
    """
    The offending item's effective id.
    """

    dependency_identifier: str
    """
    The entry, as the manifest wrote it.
    """

    def error_message(self) -> str:
        return f"item {self.item_identifier!r} depends_on malformed reference {self.dependency_identifier!r}"


@dataclass
class MissingPlanDirectory(ValidationProblem):
    """
    An item's ``depends_on`` reaches into another plan, with no plans directory given to
    resolve it against.

    Accepting it unchecked would let a reference nothing can resolve count as satisfied,
    which is the fault this form exists to remove.
    """

    item_identifier: str
    """
    The offending item's effective id.
    """

    dependency_identifier: str
    """
    The reference that could not be resolved.
    """

    def error_message(self) -> str:
        return f"item {self.item_identifier!r} depends_on {self.dependency_identifier!r} in another plan, but no plans directory was given to resolve it against"


@dataclass
class UnknownWave(ValidationProblem):
    """
    A track's ``wave`` doesn't resolve to a declared wave.
    """

    track_identifier: str
    """
    The offending track's id.
    """

    wave: Any
    """
    Whatever ``wave`` actually held.
    """

    def error_message(self) -> str:
        return f"track {self.track_identifier!r} has unknown wave {self.wave!r}"


@dataclass
class PlanInAnotherRepository(ValidationProblem):
    """
    The plan is saved from a checkout of a repository other than the one its work is
    for.
    """

    plan_identifier: Any
    """
    The plan's id.
    """

    default_repository: Repository
    """
    The repository the plan's work is for, its ``default_repository``.
    """

    checkout_repository: Repository
    """
    The repository the ``origin`` of the checkout saving the plan names.
    """

    def error_message(self) -> str:
        return (
            f"plan {self.plan_identifier!r} is for {self.default_repository} but was "
            f"to be saved from a checkout of {self.checkout_repository}"
        )

    def suggest_correction(self) -> str:
        """
        Unlike :meth:`ValidationProblem.suggest_correction`, names the checkout to save
        from.
        """
        return f"Save the plan from a checkout of {self.default_repository}."


@dataclass
class OriginNamesNoRepository(ValidationProblem):
    """
    The ``origin`` of the checkout saving the plan names no ``owner/name``, so the
    repository the plan is for cannot be compared against it.
    """

    origin_url: str
    """
    The URL of ``origin``, as configured; empty when the checkout has no ``origin``.
    """

    def error_message(self) -> str:
        return (
            f"this checkout's origin {self.origin_url!r} names no owner/name repository"
        )

    def suggest_correction(self) -> str:
        """
        Unlike :meth:`ValidationProblem.suggest_correction`, names the remote to set.
        """
        return "Set origin to the GitHub URL of the plan's repository."


@dataclass
class DependencyCycle(ValidationProblem):
    """
    A ``depends_on`` chain loops back on itself.

    Undetected, a cycle causes affected items to silently disappear from the rendered
    dependency stack instead of being reported.
    """

    cycle_identifiers: list[str]
    """
    The item ids forming the cycle, in order, with the first id repeated at the end to
    show where it closes.
    """

    def error_message(self) -> str:
        return f"depends_on cycle: {' -> '.join(self.cycle_identifiers)}"


@dataclass
class PlanValidationError(DataclassException):
    """Raised when a plan.yaml fails schema validation - see plan-schema.md."""

    problems: list[ValidationProblem]
    """
    Every problem found, so a broken manifest is reported in one pass rather than one
    problem at a time.
    """

    def error_message(self) -> str:
        return "; ".join(problem.error_message() for problem in self.problems)

    def suggest_correction(self) -> str:
        return ""
