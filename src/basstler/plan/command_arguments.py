"""
The command line every command reading one plan and its live pull request state shares.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

from basstler.plan.dependencies import PlanDirectory
from basstler.pull_request_state import PullRequestRecord, PullRequestsByRepository

# %% options


class PlanCommandOption(StrEnum):
    """The options every command reading one plan and its live pull request
    state takes."""

    PLAN = "--plan"
    """The plan's own plan.yaml."""

    PULL_REQUEST_DATA = "--pr-data"
    """The JSON file holding live pull request state - see
    :mod:`basstler.pull_request_state` for its shape."""

    PLANS_DIRECTORY = "--plans-dir"
    """The directory holding every plan as ``<plan-id>/plan.yaml``, required
    only by a manifest whose ``depends_on`` names another plan."""


@dataclass
class PlanCommandArguments:
    """The arguments every command reading one plan and its live pull request
    state takes, once parsed."""

    plan_path: Path
    """The plan's own plan.yaml."""

    pull_request_data_path: Path
    """The JSON file holding live pull request state."""

    plan_directory: PlanDirectory | None
    """The plans a ``<plan-id>/<item-id>`` entry resolves against, or
    ``None`` when none was given."""

    @classmethod
    def add_to(cls, parser: argparse.ArgumentParser) -> None:
        """Declare these arguments on one command's parser.

        :param parser: The command's parser.
        """
        parser.add_argument(
            PlanCommandOption.PLAN,
            dest="plan_path",
            type=Path,
            required=True,
            help="Path to plan.yaml",
        )
        parser.add_argument(
            PlanCommandOption.PULL_REQUEST_DATA,
            dest="pull_request_data_path",
            type=Path,
            required=True,
            help='Path to a JSON file: {"owner/repo": {"pr_number": {...}}}',
        )
        parser.add_argument(
            PlanCommandOption.PLANS_DIRECTORY,
            dest="plans_directory",
            type=Path,
            default=None,
            help=(
                "Path to the directory holding every plan (<plan-id>/plan.yaml), "
                "required only by a manifest whose depends_on names another plan"
            ),
        )

    @classmethod
    def from_namespace(cls, arguments: argparse.Namespace) -> PlanCommandArguments:
        """Read these arguments back from a parsed command line.

        :param arguments: The command line, parsed by a parser
            :meth:`add_to` declared them on.
        """
        return cls(
            plan_path=arguments.plan_path,
            pull_request_data_path=arguments.pull_request_data_path,
            plan_directory=(
                PlanDirectory(arguments.plans_directory)
                if arguments.plans_directory
                else None
            ),
        )

    def read_manifest(self) -> Any:
        """The plan.yaml content, as ``yaml.safe_load`` returns it."""
        return yaml.safe_load(self.plan_path.read_text())

    def read_pull_requests_by_repository(self) -> PullRequestsByRepository:
        """The live pull request state, parsed.

        :raises MalformedPullRequestDataError: If any entry can't be parsed.
        """
        return PullRequestRecord.parse_by_repository(
            json.loads(self.pull_request_data_path.read_text())
        )
