"""
The fixed values GitHub reports reviews, pull requests and checks in.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Self

from pydantic import GetCoreSchemaHandler
from pydantic_core import core_schema

from basstler.json_model import RawValueReader

# %% values named as GitHub spells them


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


# %% checks


class Conclusion(RawValueReader):
    """
    Reads the conclusion GitHub gives a check run or workflow run, null while it runs,
    as its :class:`CheckOutcome`.
    """

    def read(self, value: str | None) -> CheckOutcome:
        return CheckOutcome.from_conclusion(value)


class CheckOutcome(NamedAsGitHub):
    """
    Where one check stands, over both shapes a rollup can hold.

    A check run that has not finished reports no conclusion at all, which reads here as
    :attr:`PENDING` so an unfinished check is never mistaken for a passing one.
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
