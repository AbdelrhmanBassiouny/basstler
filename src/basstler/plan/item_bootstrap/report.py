"""
What an item-bootstrap operation answers with.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from basstler.plan.item_bootstrap.vocabulary import PlanItemBootstrapExitCode, ReportKey
from basstler.plan.model import (
    ManifestKey,
)

# %% reports


class OperationReport(ABC):
    """
    What any operation answers with: the status the process exits with, and the JSON a
    caller reads.
    """

    @property
    @abstractmethod
    def exit_code(self) -> PlanItemBootstrapExitCode:
        """
        The status the process exits with.
        """

    @abstractmethod
    def to_json(self) -> dict[str, Any]:
        """
        Render the report as the JSON a caller reads, led by what it means.
        """


@dataclass(frozen=True)
class BootstrapReport(OperationReport):
    """
    What an operation on one item did, in the shape a caller acts on.
    """

    plan_identifier: str
    """
    The plan that was written.
    """

    item_identifier: str
    """
    The item that was recorded, opened or updated.
    """

    created_item: bool = False
    """
    Whether the item's manifest entry was written for the first time.
    """

    branch: str | None = None
    """
    The branch opened, when one was.
    """

    pull_request_number: int | None = None
    """
    The pull request opened, when one was.
    """

    pull_request_url: str | None = None
    """
    Where the opened pull request lives.
    """

    note_paragraphs: int | None = None
    """
    How many paragraphs the written note reads as, when one was written.
    """

    @property
    def exit_code(self) -> PlanItemBootstrapExitCode:
        return PlanItemBootstrapExitCode.SUCCESS

    def to_json(self) -> dict[str, Any]:
        document: dict[str, Any] = {
            ReportKey.STATUS: self.exit_code.name_for_a_caller,
            ReportKey.EXIT_CODE: int(self.exit_code),
            ReportKey.PLAN: self.plan_identifier,
            ReportKey.ITEM: self.item_identifier,
            ReportKey.CREATED_ITEM: self.created_item,
        }
        if self.branch is not None:
            document[ManifestKey.BRANCH.key] = self.branch
        if self.pull_request_number is not None:
            document[ManifestKey.PULL_REQUEST_NUMBER.key] = self.pull_request_number
            document[ReportKey.PULL_REQUEST_URL] = self.pull_request_url
        if self.note_paragraphs is not None:
            document[ReportKey.NOTE_PARAGRAPHS] = self.note_paragraphs
        return document
