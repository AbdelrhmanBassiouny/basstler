"""
Krrood's ``DataclassException`` and the errors built on it.

``DataclassException`` is copied from krrood :cite:`krrood` until krrood's light core is
released.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from basstler.class_property import classproperty
from basstler.exit_codes import CommandFailure, StackExitCode
from basstler.locations import BasstlerVariable, ClaudeCodeVariable, PluginLocation
from basstler.repository import Repository


class DataclassException(Exception, ABC):
    """
    A base exception class for dataclass-based exceptions.

    Subclasses implement error_message() and suggest_correction(); both are evaluated at
    construction time and composed into the actual exception message (the args passed to
    Exception). A non-empty suggest_correction() is rendered as a trailing "Suggestion:
    ..." line. Subclasses that override __post_init__ must call super().__post_init__()
    at the end.
    """

    def __post_init__(self) -> None:
        # BaseException.__new__ bypasses the usual ABC instantiation check, so enforce it here.
        if getattr(type(self), "__abstractmethods__", None):
            raise TypeError(
                f"Can't instantiate abstract class {type(self).__name__} without an implementation of "
                f"{', '.join(sorted(type(self).__abstractmethods__))}."
            )
        message = self.error_message()
        correction = self.suggest_correction()
        if correction:
            message = f"{message}\nSuggestion: {correction}"
        super().__init__(message)

    def __str__(self) -> str:
        # Stdlib mixins like KeyError override __str__ to repr their args; always render the
        # plain message that __post_init__ baked into the args.
        return Exception.__str__(self)

    @abstractmethod
    def error_message(self) -> str:
        """
        :return: A human-readable description of what went wrong.
        """

    @abstractmethod
    def suggest_correction(self) -> str:
        """
        :return: Advice on how to fix the error, or an empty string if there is no specific advice.
        """


@dataclass
class NotesBranchMissingError(DataclassException, RuntimeError):
    """
    Raised when no remote tried holds the personal-notes branch.
    """

    branch: str
    """
    The personal-notes branch that was looked for.
    """

    attempted_remotes: tuple[str, ...]
    """
    Every remote it was fetched from, in order.
    """

    def error_message(self) -> str:
        return (
            f"branch '{self.branch}' doesn't exist yet (tried: "
            f"{', '.join(self.attempted_remotes)})"
        )

    def suggest_correction(self) -> str:
        return f"run {PluginLocation.PERSONAL_NOTES_BRANCH_CREATION_SCRIPT.path_under_exported_root} first"


@dataclass
class NotesPushRejectedError(DataclassException, RuntimeError):
    """
    Raised when the remote rejected every push of a write to the personal-notes branch.
    """

    branch: str
    """
    The personal-notes branch pushed to.
    """

    attempts: int
    """
    How many pushes were made.
    """

    def error_message(self) -> str:
        return f"every one of {self.attempts} pushes to '{self.branch}' was rejected"

    def suggest_correction(self) -> str:
        return "check that this credential may push to the branch, then run it again"


@dataclass
class UnsafeNotesPathError(DataclassException, ValueError):
    """
    Raised when a path to write on the personal-notes branch could leave it.
    """

    path: PurePosixPath
    """
    The refused path.
    """

    def error_message(self) -> str:
        return f"{self.path} would be written outside the personal-notes branch's root"

    def suggest_correction(self) -> str:
        return "give a path relative to the branch's root, with no '..' component"


@dataclass
class UnresolvableReferenceError(CommandFailure, DataclassException, LookupError):
    """
    Raised when a git reference a decision depends on names no commit in the checkout.
    """

    @classproperty
    def exit_code(cls) -> StackExitCode:
        """:return: The status this kind of error ends a command with."""
        return StackExitCode.GIT_COMMAND_FAILED

    reference: str
    """
    The reference git could not resolve.
    """

    def error_message(self) -> str:
        return f"git cannot resolve '{self.reference}' to a commit in this checkout"

    def suggest_correction(self) -> str:
        return (
            "fetch the branch it names from its remote, and check that the branch "
            "still exists there"
        )


@dataclass
class MissingStatusLineError(DataclassException, ValueError):
    """
    Raised when an item slated for a status correction has no ``status:`` line in its
    plan.yaml block.
    """

    item_identifier: str
    """
    The id of the item whose block has no ``status:`` line.
    """

    def error_message(self) -> str:
        return f"item {self.item_identifier!r} has no status: line to correct"

    def suggest_correction(self) -> str:
        return "give the item a status: line in plan.yaml"


# %% plan validation


@dataclass
class ValidationProblem(DataclassException):
    """A single problem found while validating a plan.yaml - see plan-schema.md.

    One dataclass subclass per validation rule, each carrying the specific
    fields that rule cares about, so a caller can react to one kind of
    problem with ``isinstance()``. :class:`PlanValidator` collects them and
    raises them together as one :class:`PlanValidationError`.
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
    More than one item names the same branch, so a session on it cannot tell which item
    it works.
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
        return (
            "Keep the branch on the item whose work it carries; leave it off the others "
            "and say in their notes that they land on it."
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


@dataclass
class MalformedEmailAddressError(DataclassException, ValueError):
    """
    Raised when text is not an email address in ``local-part@domain`` form.
    """

    text: str
    """
    The value that could not be parsed.
    """

    def error_message(self) -> str:
        return f"expected an email address as 'local-part@domain', got {self.text!r}"

    def suggest_correction(self) -> str:
        return "give the address your commits should carry, e.g. you@example.com"


@dataclass
class BashNotFoundError(DataclassException, FileNotFoundError):
    """
    Raised when no bash a script can run in is found, the Windows launcher for WSL
    aside.
    """

    passed_over: list[Path]
    """
    The bash programs found in the Windows directory, which start WSL rather than the
    bash the scripts are written for.
    """

    def error_message(self) -> str:
        if not self.passed_over:
            return "found no bash to run the plugin's scripts in"
        launchers = ", ".join(str(path) for path in self.passed_over)
        return (
            f"found no bash to run the plugin's scripts in: {launchers} starts WSL, not "
            f"Git Bash"
        )

    def suggest_correction(self) -> str:
        return (
            f"install Git for Windows, or set {ClaudeCodeVariable.GIT_BASH_PATH} to its "
            f"bash.exe"
        )


@dataclass
class PluginRootUnsetError(DataclassException, LookupError):
    """
    Raised when no plugin root is exported, so no plugin script can be found.
    """

    def error_message(self) -> str:
        return (
            f"{BasstlerVariable.PLUGIN_ROOT} is not set, so the plugin cannot be found"
        )

    def suggest_correction(self) -> str:
        return (
            f"source {PluginLocation.PERSONAL_NOTES_CONFIGURATION_SCRIPT} from the "
            f"plugin's root first, or export {BasstlerVariable.PLUGIN_ROOT} as that root"
        )


@dataclass
class PluginRootNotADirectoryError(DataclassException, NotADirectoryError):
    """
    Raised when the exported plugin root is not a directory.
    """

    root: Path
    """
    The plugin root exported.
    """

    def error_message(self) -> str:
        return f"{BasstlerVariable.PLUGIN_ROOT} names {self.root}, which is not a directory"

    def suggest_correction(self) -> str:
        return (
            f"export {BasstlerVariable.PLUGIN_ROOT} as the directory holding the "
            f"plugin's {PluginLocation.HOOKS} directory"
        )


# %% budget violations


@dataclass
class BudgetViolation(DataclassException):
    """
    One way a workflow breaks the Actions budget, carrying what a reader needs to fix
    it.
    """

    workflow: str
    """
    The file name of the workflow that breaks it.
    """

    def error_message(self) -> str:
        return f"{self.workflow}: {self.problem()}"

    @abstractmethod
    def problem(self) -> str:
        """
        :return: What is wrong with the workflow.
        """


@dataclass
class ScheduledWorkflow(BudgetViolation):
    """
    The workflow runs on a schedule, which nothing in this repository may.
    """

    def problem(self) -> str:
        return "runs on a schedule"

    def suggest_correction(self) -> str:
        return "trigger it on the event it is waiting for instead"


@dataclass
class MissingPullRequestCancellation(BudgetViolation):
    """
    The workflow runs on every push to a pull request without cancelling the run for the
    commit before.
    """

    def problem(self) -> str:
        return "runs on every pull-request push without cancel-in-progress concurrency"

    def suggest_correction(self) -> str:
        return "add a concurrency group with cancel-in-progress: true"


@dataclass
class MissingJobTimeout(BudgetViolation):
    """
    A job that takes a runner declares no ``timeout-minutes``, so a hang holds the
    runner for GitHub's six-hour default.
    """

    job: str
    """
    The job's key.
    """

    def problem(self) -> str:
        return f"job {self.job} has no timeout-minutes"

    def suggest_correction(self) -> str:
        return f"set timeout-minutes on job {self.job}"


@dataclass
class JobTimeoutOverCeiling(BudgetViolation):
    """
    A job's ``timeout-minutes`` is above the workflow's ceiling.
    """

    job: str
    """
    The job's key.
    """

    timeout_minutes: int
    """
    The job's timeout.
    """

    ceiling_minutes: int
    """
    The workflow's ceiling.
    """

    def problem(self) -> str:
        return (
            f"job {self.job} times out after {self.timeout_minutes} minutes, "
            f"above the ceiling of {self.ceiling_minutes}"
        )

    def suggest_correction(self) -> str:
        return (
            f"lower the timeout of job {self.job}, or raise the workflow's ceiling "
            "in the budget file"
        )


@dataclass
class MissingForkGuard(BudgetViolation):
    """
    A first job of a workflow answering ``push`` does not skip a push to a fork.
    """

    job: str
    """
    The job's key.
    """

    condition: str
    """
    The condition the job has to carry.
    """

    def problem(self) -> str:
        return f"job {self.job} does not skip a push to a fork"

    def suggest_correction(self) -> str:
        return (
            f"add `if: {self.condition}` to job {self.job}, or run it in one "
            "repository only with `if: github.repository == '<owner>/<name>'`"
        )


@dataclass
class MissingLabelGuard(BudgetViolation):
    """
    A first job of a workflow answering ``labeled`` runs for any label, without
    comparing the one added.
    """

    job: str
    """
    The job's key.
    """

    def problem(self) -> str:
        return f"job {self.job} runs for any label"

    def suggest_correction(self) -> str:
        return f"compare github.event.label.name in the `if:` of job {self.job}"


@dataclass
class TooManyJobsOnEveryPush(BudgetViolation):
    """
    A workflow running on every push takes runners for more jobs a run than its ceiling
    allows.
    """

    jobs: int
    """
    The most jobs one run takes runners for.
    """

    ceiling: int
    """
    The workflow's ceiling.
    """

    def problem(self) -> str:
        return (
            f"runs up to {self.jobs} jobs on every push, above the ceiling of "
            f"{self.ceiling}"
        )

    def suggest_correction(self) -> str:
        return "narrow its triggers or raise its jobs_per_push_run"


@dataclass
class UncountableJobs(BudgetViolation):
    """
    A workflow running on every push has jobs whose number is only known at run time, so
    its ceiling cannot be checked.
    """

    def problem(self) -> str:
        return (
            "runs on every push with a matrix computed at run time or a reusable "
            "workflow from another repository, so its jobs cannot be counted"
        )

    def suggest_correction(self) -> str:
        return "use a literal matrix and reusable workflows from this repository"


@dataclass
class OverrideWithoutWorkflow(BudgetViolation):
    """
    The budget sets limits for a workflow file the repository does not have.
    """

    def problem(self) -> str:
        return "has limits in the budget but no workflow file"

    def suggest_correction(self) -> str:
        return "remove its override"


# %% budget file errors


@dataclass
class BudgetFileExists(DataclassException, FileExistsError):
    """
    A budget file is already where a new one would be written.

    Once written, the file is reviewed by hand, so writing over it would bless whatever
    the workflows do now.
    """

    path: Path
    """
    The existing file.
    """

    def error_message(self) -> str:
        return f"{self.path} already exists"

    def suggest_correction(self) -> str:
        return "edit it instead of writing a new one"


@dataclass
class MissingBudgetFunction(DataclassException, LookupError):
    """
    A budget file does not define the function that returns its budget.
    """

    path: Path
    """
    The budget file.
    """

    function: str
    """
    The name of the function it has to define.
    """

    def error_message(self) -> str:
        return f"{self.path} defines no {self.function}()"

    def suggest_correction(self) -> str:
        return f"define {self.function}() returning its ActionsBudget"


@dataclass
class DuplicateKeyError(DataclassException, TypeError):
    """
    Raised when two fields of a model read the same key of the object it mirrors.
    """

    model: str
    """
    The model's name.
    """

    key: str
    """
    The key both fields read.
    """

    fields: tuple[str, str]
    """
    The two fields reading it.
    """

    def error_message(self) -> str:
        first, second = self.fields
        return f"{self.model}.{first} and {self.model}.{second} both read {self.key!r}"

    def suggest_correction(self) -> str:
        return "Give one of the fields the key it should read instead as its alias."
