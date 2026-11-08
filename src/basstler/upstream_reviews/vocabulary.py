"""
The contract every model of GitHub's data keeps, and the fixed values GitHub's
pull-request data is written in.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Self, TypeVar, get_args

from pydantic import (
    AliasChoices,
    AliasPath,
    ConfigDict,
    Field,
    GetCoreSchemaHandler,
    TypeAdapter,
)
from pydantic.dataclasses import dataclass as pydantic_dataclass
from pydantic.fields import FieldInfo
from pydantic_core import core_schema

from basstler.class_property import classproperty
from basstler.exceptions import DuplicateKeyError
from basstler.locations import PackageLocation

# %% the reading contract


class JSONModel(ABC):
    """
    A dataclass mirroring one object GitHub returns, able to read itself from it.

    Every response is parsed into these models as soon as it arrives, and every
    decision after that is made on their attributes, never on the raw object. A
    reader reads its own object's fields and hands each nested object to that
    object's own model, so no access path into a response is spelled out twice.
    """

    @classmethod
    @abstractmethod
    def from_json(cls, data: dict[str, Any]) -> JSONModel:
        """
        Read one of these out of the object GitHub returned.

        :param data: The object to read.
        :return: The parsed model.
        """


class ValidatedJSONModel(JSONModel):
    """
    A frozen pydantic dataclass by subclassing alone, whose fields are the object's keys,
    each spelled as its field name or, where GitHub names it differently, as its alias.

    Copied from krrood's ``ValidatedDataclass`` :cite:`krrood` until krrood's light core
    is released.
    """

    __pydantic_config__ = ConfigDict(validate_by_name=True, validate_by_alias=True)
    """
    The pydantic settings every subclass starts from.
    """

    def __init_subclass__(cls, config: ConfigDict | None = None, **kwargs: Any) -> None:
        """
        Make the subclass a frozen pydantic dataclass.

        :param config: Pydantic settings added to those the subclass inherits.
        :param kwargs: Passed on to the next base.
        :raises DuplicateKeyError: If two of its fields read the same key.
        """
        super().__init_subclass__(**kwargs)
        cls.__pydantic_config__ = ConfigDict(
            **cls.__pydantic_config__, **(config or {})
        )
        pydantic_dataclass(cls, frozen=True)
        readers: dict[str, str] = {}
        for name, field_info in cls.__pydantic_fields__.items():
            for key in cls.entry_keys(name, field_info):
                if key in readers:
                    raise DuplicateKeyError(cls.__name__, key, (readers[key], name))
                readers[key] = name

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Self:
        """
        :raises pydantic.ValidationError: If the object does not have the model's shape.
        """
        return TypeAdapter(cls).validate_python(data)

    def to_json(self) -> dict[str, Any]:
        """
        :return: The object, each field written under its alias where it has one.
        """
        return TypeAdapter(type(self)).dump_python(self, mode="json", by_alias=True)

    @classproperty
    def read_keys(cls) -> frozenset[str]:
        """
        Every key the model reads out of its object, at any depth.
        """
        keys: set[str] = set()
        for name, field_info in cls.__pydantic_fields__.items():
            keys |= cls.field_keys(name, field_info)
            for model in cls.nested_models(field_info.annotation):
                keys |= model.read_keys
        return frozenset(keys)

    @staticmethod
    def field_keys(name: str, field_info: FieldInfo) -> set[str]:
        """
        :param name: The field's name.
        :param field_info: The field.
        :return: Every key the field is read from, each step of a nested key path
            included.
        """
        return {
            step
            for path in ValidatedJSONModel.key_paths(name, field_info)
            for step in path
            if isinstance(step, str)
        }

    @staticmethod
    def entry_keys(name: str, field_info: FieldInfo) -> set[str]:
        """
        :param name: The field's name.
        :param field_info: The field.
        :return: The keys of the model's own object the field is read from.
        """
        return {path[0] for path in ValidatedJSONModel.key_paths(name, field_info)}

    @staticmethod
    def key_paths(name: str, field_info: FieldInfo) -> list[list[str | int]]:
        """
        :param name: The field's name.
        :param field_info: The field.
        :return: Each path of keys the field can be read from, outermost key first.
        """
        alias = field_info.validation_alias or field_info.alias or name
        choices = alias.choices if isinstance(alias, AliasChoices) else [alias]
        return [
            list(choice.path) if isinstance(choice, AliasPath) else [choice]
            for choice in choices
        ]

    @staticmethod
    def nested_models(annotation: Any) -> list[type[ValidatedJSONModel]]:
        """
        :param annotation: A field's type.
        :return: Every model the type holds, at any depth of its type arguments.
        """
        if isinstance(annotation, type) and issubclass(annotation, ValidatedJSONModel):
            return [annotation]
        return [
            model
            for argument in get_args(annotation)
            for model in ValidatedJSONModel.nested_models(argument)
        ]


class RawValueReader(ABC):
    """
    A field annotation that turns the value GitHub sent into the one the field's type
    validates.
    """

    @abstractmethod
    def read(self, value: Any) -> Any:
        """
        :param value: The value as GitHub sent it.
        :return: The value the field's type validates.
        """

    def __get_pydantic_core_schema__(
        self, source: type[Any], handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        """
        :param source: The field's type.
        :param handler: Builds pydantic's own schema for a type.
        :return: How pydantic reads the field: :meth:`read`, then the field's type.
        """
        return core_schema.no_info_before_validator_function(self.read, handler(source))


class GraphQLNodes(RawValueReader):
    """
    Reads a GraphQL connection, which holds a list-valued field's entries under
    ``nodes``, as those entries.
    """

    def read(self, value: dict[str, Any] | list[Any]) -> list[Any]:
        if isinstance(value, list):
            return value
        return value["nodes"]


class AbsentAsEmpty(RawValueReader):
    """
    Reads a text GitHub reports as null as empty text.
    """

    def read(self, value: str | None) -> str:
        return value or ""


class Conclusion(RawValueReader):
    """
    Reads the conclusion GitHub gives a check run or workflow run, null while it runs,
    as its :class:`CheckOutcome`.
    """

    def read(self, value: str | None) -> CheckOutcome:
        return CheckOutcome.from_conclusion(value)


Node = TypeVar("Node")
"""
Whatever model the entries of a connection are parsed into.
"""


GraphQLConnection = Annotated[list[Node], GraphQLNodes()]
"""
A list-valued GraphQL field, which GitHub returns as a connection.
"""


class WebPage(ValidatedJSONModel):
    """
    A REST resource that has a page of its own on github.com.
    """

    url: Annotated[str, Field(alias="html_url")]
    """
    The address of its page.
    """


# %% wire vocabulary


class NamedAsGitHub(StrEnum):
    """
    An enum whose members are named as GitHub spells its values, in any letter case,
    while each member's value is how it reads in the report.
    """

    @classmethod
    def from_github_name(cls, spelling: str) -> Self:
        """
        :param spelling: A value as GitHub spells it, or a member already.
        :return: The member it names.
        :raises KeyError: If no member has that name.
        """
        if isinstance(spelling, cls):
            return spelling
        return cls[spelling.upper()]

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source: type[Any], handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        """
        :param source: The enum.
        :param handler: Builds pydantic's own schema for a type, unused since the enum
            replaces it.
        :return: How pydantic reads a field of this enum: by :meth:`from_github_name`.
        """
        return core_schema.no_info_plain_validator_function(
            cls.from_github_name, json_schema_input_schema=core_schema.str_schema()
        )


class QueryVariable(StrEnum):
    """
    The variables the query documents declare.
    """

    OWNER = "owner"
    NAME = "name"
    HEAD_REF_NAME = "headRefName"
    NUMBER = "number"
    THREAD_CURSOR = "threadCursor"


class GraphQLDocument(StrEnum):
    """
    The query documents, stored as ``.graphql`` files beside this script.
    """

    PULL_REQUEST_FOR_BRANCH = "pull_request_for_branch"
    REVIEW_THREADS_PAGE = "review_threads_page"

    def read(self) -> str:
        """:return: The document's text."""
        return (PackageLocation.QUERIES / f"{self}.graphql").read_text()


class ReviewState(NamedAsGitHub):
    """
    The verdict a reviewer submitted with a review.

    """

    APPROVED = "approved"
    """
    The reviewer approved the changes.
    """

    CHANGES_REQUESTED = "changes requested"
    """
    The reviewer asked for changes before the pull request can merge.
    """

    COMMENTED = "commented"
    """
    The reviewer left comments without a verdict.
    """

    DISMISSED = "dismissed"
    """
    The review was dismissed and no longer counts towards the verdict.
    """

    PENDING = "pending"
    """
    The review was started but not yet submitted.
    """


class PullRequestState(StrEnum):
    """
    The lifecycle state GitHub reports for a pull request.
    """

    OPEN = "OPEN"
    CLOSED = "CLOSED"
    MERGED = "MERGED"


class CheckOutcome(NamedAsGitHub):
    """
    Where one check stands, over both shapes a rollup can hold.

    A check run that has not finished reports no conclusion at all, which reads here
    as :attr:`PENDING` so an unfinished check is never mistaken for a passing one.
    """

    SUCCESS = "success"
    """
    The check passed.
    """

    FAILURE = "failure"
    """
    The check failed.
    """

    ERROR = "error"
    """
    The commit status reported an error.
    """

    CANCELLED = "cancelled"
    """
    The check run was cancelled before it finished.
    """

    TIMED_OUT = "timed out"
    """
    The check run exceeded its time limit.
    """

    ACTION_REQUIRED = "action required"
    """
    The check run needs someone to act before it can conclude.
    """

    NEUTRAL = "neutral"
    """
    The check run finished without passing or failing.
    """

    SKIPPED = "skipped"
    """
    The check run was skipped.
    """

    STALE = "stale"
    """
    GitHub marked the check run stale after it went too long without finishing.
    """

    @classmethod
    def from_conclusion(cls, conclusion: str | None) -> CheckOutcome:
        """
        :param conclusion: A check run's or workflow run's conclusion as GitHub spells
            it, ``None`` while it runs.
        :return: The outcome it reads as.
        """
        return cls.from_github_name(conclusion) if conclusion else cls.PENDING

    STARTUP_FAILURE = "startup failure"
    """
    The check run failed before it could start.
    """

    PENDING = "pending"
    """
    The check has not finished yet.
    """

    EXPECTED = "expected"
    """
    A required commit status that has not been reported yet.
    """

    @property
    def rolls_up_to(self) -> RollupState:
        """
        :return: The verdict this outcome alone would give the whole rollup, the way
            GitHub counts it: a neutral or skipped check does not hold a pull request
            back, and everything that ended without passing fails it.
        """
        if self in {CheckOutcome.SUCCESS, CheckOutcome.NEUTRAL, CheckOutcome.SKIPPED}:
            return RollupState.SUCCESS
        if self in {CheckOutcome.ERROR, CheckOutcome.PENDING, CheckOutcome.EXPECTED}:
            return RollupState[self.name]
        return RollupState.FAILURE


ConclusionOutcome = Annotated[CheckOutcome, Conclusion()]
"""
A check's outcome, read from the conclusion GitHub gives a check run or workflow run.
"""


class RollupState(NamedAsGitHub):
    """
    The verdict GitHub itself computes over all of a pull request's checks, or that
    nothing has reported one yet.

    """

    SUCCESS = "success"
    """
    Every check passed.
    """

    FAILURE = "failure"
    """
    At least one check failed.
    """

    ERROR = "error"
    """
    At least one commit status reported an error.
    """

    PENDING = "pending"
    """
    At least one check has not finished yet.
    """

    EXPECTED = "expected"
    """
    At least one required commit status has not been reported yet.
    """

    NOT_REPORTED = "not reported"
    """
    No check run or commit status has been reported at all.
    """

    @property
    def failed(self) -> bool:
        """:return: Whether at least one check failed or reported an error."""
        return self in {RollupState.FAILURE, RollupState.ERROR}

    @classmethod
    def over(cls, outcomes: list[CheckOutcome]) -> RollupState:
        """
        Compute the verdict GitHub would over a set of checks, for a source that does
        not report one: the worst any single check would give.

        :param outcomes: Every check's outcome, at least one.
        :return: The verdict.
        """
        reached = {outcome.rolls_up_to for outcome in outcomes}
        return next(state for state in cls.severity_order() if state in reached)

    @classmethod
    def severity_order(cls) -> list[RollupState]:
        """
        :return: Every verdict a reported check can give, worst first.
        """
        return [cls.FAILURE, cls.ERROR, cls.PENDING, cls.EXPECTED, cls.SUCCESS]


class ThreadMarker(StrEnum):
    """
    The annotations a thread can carry in the report.
    """

    RESOLVED = "resolved"
    OUTDATED = "outdated"


# %% the fork's Action branch


class ActionBranch(StrEnum):
    """
    Where the Action lives in the fork.
    """

    NAME = "basstler/upstream-reviews"
    """
    The branch, outside both the fork's default branch and the ``claude/`` branches
    stack maintenance owns.
    """

    @classproperty
    def install_command(cls) -> str:
        """
        How a reader is told to install the branch or bring it up to date.
        """
        return (
            '"${BASSTLER_PYTHON}" -m basstler.setup.steps install-upstream-reviews-action '
            "--branch-or-tag <the basstler release the session runs> "
            "(/setup-personal-notes runs it)"
        )


class ActionFile(StrEnum):
    """
    Every file on the branch.
    """

    WORKFLOW = ".github/workflows/upstream-reviews.yml"
    README = "README.md"
    REQUEST = "request.json"
    RESULT = "result.json"

    @property
    def file_name(self) -> str:
        """:return: The file's own name, without its directory."""
        return Path(self.value).name


class BasstlerSource(StrEnum):
    """
    Where the reusable workflow and the package a run installs come from.
    """

    REPOSITORY = "KAOS-repositories/basstler"
    REUSABLE_WORKFLOW = ".github/workflows/upstream-reviews-action.yml"
    LATEST_RELEASE = "main"
    """
    The branch every release is tagged on, so it always holds the latest one.
    """
