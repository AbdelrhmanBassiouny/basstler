"""
Krrood's ``DataclassException`` and the errors built on it.

``DataclassException`` is copied from krrood :cite:`krrood` until krrood's light core is
released.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath

from basstler.class_property import classproperty
from basstler.exit_codes import CommandFailure, StackExitCode
from basstler.locations import BasstlerVariable, ClaudeCodeVariable, PluginLocation


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


# %% calls to git and GitHub


@dataclass
class ExternalCallFailed(DataclassException, RuntimeError):
    """
    Base for a call to git or GitHub that the caller depended on and did not get.

    Both carry what was called, the status it came back with and what it said, and
    differ only in how they name the call.
    """

    status: int
    """The status the call came back with."""

    detail: str
    """
    What the far side said about it.
    """

    @property
    def call(self) -> str:
        """:return: The call that failed, named the way its own caller named it."""
        raise NotImplementedError

    def error_message(self) -> str:
        return f"{self.call} failed with {self.status}: {self.detail}"

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


class PackageMapInconsistency(StrEnum):
    """
    The ways the declared distributions break their layering.
    """

    DEPENDENCY_ON_A_HIGHER_LAYER = "depends on a distribution in a higher layer"
    """
    The first distribution lists the second, which sits in a higher layer.
    """

    DEPENDENCY_CYCLE = "depend on each other in a cycle"
    """
    The distributions, in order, each list the next and the last lists the first.
    """

    UNDECLARED_DISTRIBUTION = "has no declaration"
    """
    The distribution is listed as a dependency, but nothing declares it.
    """

    MODULE_CLAIMED_TWICE = "both claim the same module"
    """
    Two distributions name the same module or subpackage.
    """


@dataclass
class InconsistentPackageMap(DataclassException, ValueError):
    """
    The declared distributions are not layered and acyclic.
    """

    inconsistency: PackageMapInconsistency
    """
    How the declarations break the layering.
    """

    distributions: tuple[str, ...]
    """
    The package names of the distributions involved.
    """

    def error_message(self) -> str:
        return f"{', '.join(self.distributions)} {self.inconsistency}"

    def suggest_correction(self) -> str:
        return "correct the declarations in basstler.package_map.PACKAGE_MAP"


@dataclass
class UndeclaredDistribution(DataclassException, KeyError):
    """
    A declaration was looked up for a distribution the package map does not declare.
    """

    distribution: str
    """
    The package name of the distribution looked up.
    """

    def error_message(self) -> str:
        return f"{self.distribution} {PackageMapInconsistency.UNDECLARED_DISTRIBUTION}"

    def suggest_correction(self) -> str:
        return (
            "declare it in basstler.package_map.PACKAGE_MAP or look up a declared one"
        )


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
