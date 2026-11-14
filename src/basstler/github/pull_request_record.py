"""
A pull request as GitHub's REST API answers it, read field by field.

A fetch that drops a field is not partially correct, so every field is declared with
how to read it and whether it may be absent, and a record omitting a required one is
rejected rather than defaulted.
"""

from __future__ import annotations

import dataclasses
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum, StrEnum
from typing import Any

from basstler.class_property import classproperty
from basstler.exit_codes import CommandFailure, StackExitCode
from basstler.github.states import CombinedCheckState

PullRequestRecord = Mapping[str, Any]
"""
One pull request as the REST API answers it, before any field is read.
"""

# %% the fields a pull request is read from


class PullRequestHeadKey(StrEnum):
    """
    The keys of the object a pull request's head arrives as.
    """

    REFERENCE = "ref"
    """
    The head branch's name.
    """

    HEAD_REPOSITORY = "repo"
    """
    The repository the head branch lives in, ``null`` once that repository is deleted.
    """

    FULL_NAME = "full_name"
    """
    A repository's ``owner/name``, under :attr:`HEAD_REPOSITORY`.
    """

    COMMIT = "sha"
    """
    The commit the head branch points at.
    """


class AccountField(StrEnum):
    """
    The fields of an account the API describes.
    """

    LOGIN = "login"
    """
    The account's login.
    """


class PullRequestFieldShape(StrEnum):
    """
    How one pull-request field's value has to be read.

    The API answers some fields with a nested object where a plain value would do, so
    reading is per-field rather than uniform.
    """

    VALUE = "value"
    """
    Taken as it comes.
    """

    BRANCH_REFERENCE = "branch-reference"
    """
    A branch, given either plainly or as an object carrying a ``ref``.
    """

    LABEL_NAMES = "label-names"
    """
    A list of labels, each given either plainly or as an object carrying a ``name``.
    """

    ACCOUNT_LOGINS = "account-logins"
    """
    A list of accounts, each an object carrying a ``login``.
    """


@dataclass(frozen=True)
class PullRequestFieldSpecification:
    """
    What one pull-request field is called, how to read it, and whether it may be absent.
    """

    key: str
    """
    The key the API answers under.
    """

    shape: PullRequestFieldShape = PullRequestFieldShape.VALUE
    """
    How its value has to be read.
    """

    required: bool = False
    """
    Whether a record omitting it is rejected rather than read.
    """


class PullRequestField(PullRequestFieldSpecification, Enum):
    """
    Every pull-request field this executor reads, and how to read it.

    Each member *is* a specification, so nothing outside this enum knows that ``head``
    arrives nested while ``draft`` does not, or which fields a board cannot be derived
    without.

    A member is written as the specification it carries, and :meth:`__init__` unpacks it
    onto the member itself - so ``PullRequestField.HEAD.key`` reads directly and the
    member is a :class:`PullRequestFieldSpecification` in its own right.
    """

    def __init__(self, specification: PullRequestFieldSpecification) -> None:
        """
        Carry the specification's values on the member itself.

        Without this the mixin would receive the whole specification as its first
        argument - silently, landing the instance in :attr:`key` - since an enum passes
        a member's value straight to the type it mixes in.

        :param specification: What this field is called and how to read it.
        """
        for field in dataclasses.fields(PullRequestFieldSpecification):
            object.__setattr__(self, field.name, getattr(specification, field.name))

    NUMBER = PullRequestFieldSpecification(key="number", required=True)
    """
    The pull request's number.
    """
    HEAD = PullRequestFieldSpecification(
        key="head", shape=PullRequestFieldShape.BRANCH_REFERENCE, required=True
    )
    """The branch the pull request would merge - the stack node it names."""
    BASE = PullRequestFieldSpecification(
        key="base", shape=PullRequestFieldShape.BRANCH_REFERENCE, required=True
    )
    """The branch it would merge into - its parent in the stack."""
    DRAFT = PullRequestFieldSpecification(key="draft", required=True)
    """
    Whether its author has yet reviewed it themselves.
    """
    LABELS = PullRequestFieldSpecification(
        key="labels", shape=PullRequestFieldShape.LABEL_NAMES, required=True
    )
    """
    The labels it carries, which the workflow reads as state.
    """
    BODY = PullRequestFieldSpecification(key="body")
    """
    Its description, read for the session link and the promotion prefill.
    """
    TITLE = PullRequestFieldSpecification(key="title")
    """
    Its title, which prefills the upstream pull request.
    """
    MERGEABLE_STATE = PullRequestFieldSpecification(key="mergeable_state")
    """
    GitHub's own verdict on whether it currently conflicts with its base.
    """
    STATE = PullRequestFieldSpecification(key="state")
    """
    Whether it is open or closed, a merged one included among the closed.
    """
    MERGED_AT = PullRequestFieldSpecification(key="merged_at")
    """
    When GitHub merged it, absent for one never merged through GitHub.
    """
    HTML_URL = PullRequestFieldSpecification(key="html_url")
    """
    Its page on GitHub, which the issues API answers under the same key.
    """
    ASSIGNEES = PullRequestFieldSpecification(
        key="assignees", shape=PullRequestFieldShape.ACCOUNT_LOGINS
    )
    """
    The logins of the accounts it is assigned to.
    """

    def read(self, record: PullRequestRecord, number: int | None = None) -> Any:
        """
        Read this field out of a fetched pull request.

        :param record: The fetched pull request.
        :param number: The pull request being read, named in any rejection.
        :return: The field's value, read according to its shape.
        :raises MissingPullRequestFieldError: If a required field is absent, or its
            value carries no name where its shape says one belongs.
        """
        value = record.get(self.key)
        if value is None:
            if self.required:
                raise MissingPullRequestFieldError(self, number)
            return None
        match self.shape:
            case PullRequestFieldShape.BRANCH_REFERENCE:
                return self._branch_reference(value, number)
            case PullRequestFieldShape.LABEL_NAMES:
                return [
                    label if isinstance(label, str) else str(label["name"])
                    for label in value
                ]
            case PullRequestFieldShape.ACCOUNT_LOGINS:
                return [str(account[AccountField.LOGIN]) for account in value]
            case _:
                return value

    def _branch_reference(self, value: Any, number: int | None) -> str:
        """:param value: The field's value, plain or nested.
        :param number: The pull request being read, named in any rejection.
        :return: The branch it names.
        :raises MissingPullRequestFieldError: If it names none."""
        if isinstance(value, str):
            return value
        if isinstance(value, Mapping) and value.get(PullRequestHeadKey.REFERENCE):
            return str(value[PullRequestHeadKey.REFERENCE])
        raise MissingPullRequestFieldError(self, number)


@dataclass
class MissingPullRequestFieldError(CommandFailure, ValueError):
    """
    Raised when a fetched pull request omits a field the board is derived from.

    A fetch that drops a field is not partially correct: absent and legitimately empty
    are different facts, and defaulting one to the other is what makes bad board data
    indistinguishable from good.
    """

    @classproperty
    def exit_code(cls) -> StackExitCode:
        """:return: The status this kind of error ends a command with."""
        return StackExitCode.USAGE

    field_name: PullRequestField
    """
    The field that was absent.
    """

    pull_request_number: int | None
    """
    The pull request it was absent from, or ``None`` when the number itself is.
    """

    def __str__(self) -> str:
        """:return: Which field is missing, and from where."""
        subject = (
            f"pull request {self.pull_request_number}"
            if self.pull_request_number is not None
            else "a fetched pull request"
        )
        return (
            f"{subject} has no '{self.field_name}'; the board cannot be derived from a "
            f"fetch that omits it"
        )


# %% the pull request's head


@dataclass(frozen=True)
class PullRequestHead:
    """
    The branch a pull request would merge, where it lives, and the commit it is at.
    """

    branch: str
    """
    The head branch's name.
    """

    repository: str | None
    """
    The ``owner/name`` of the repository the head branch lives in, ``None`` once that
    repository is deleted.
    """

    commit: str
    """
    The commit the head branch points at.
    """

    @staticmethod
    def commit_in(record: PullRequestRecord) -> str | None:
        """
        :param record: The fetched pull request.
        :return: The commit its head points at, or ``None`` when the record carries no
            head object naming one.
        """
        head = record.get(PullRequestField.HEAD.key)
        if not isinstance(head, Mapping):
            return None
        return head.get(PullRequestHeadKey.COMMIT)

    @classmethod
    def from_record(cls, record: PullRequestRecord, number: int) -> PullRequestHead:
        """
        :param record: The fetched pull request.
        :param number: The pull request being read, named in any rejection.
        :return: Its head.
        :raises MissingPullRequestFieldError: If the head does not say where it lives or
            which commit it is at.
        """
        head = record.get(PullRequestField.HEAD.key)
        if (
            not isinstance(head, Mapping)
            or PullRequestHeadKey.HEAD_REPOSITORY not in head
            or not head.get(PullRequestHeadKey.COMMIT)
        ):
            raise MissingPullRequestFieldError(PullRequestField.HEAD, number)
        repository = head[PullRequestHeadKey.HEAD_REPOSITORY]
        return cls(
            branch=PullRequestField.HEAD.read(record, number),
            repository=(
                None
                if repository is None
                else str(repository[PullRequestHeadKey.FULL_NAME])
            ),
            commit=str(head[PullRequestHeadKey.COMMIT]),
        )


# %% the checks on a pull request's head


class CommitChecks(ABC):
    """
    Reading the verdict over the checks reported on one commit.
    """

    @abstractmethod
    def check_state(self, commit: str) -> CombinedCheckState:
        """:param commit: The commit the checks ran on.
        :return: The verdict over every check run and commit status reported on it."""
