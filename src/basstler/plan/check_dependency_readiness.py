#!/usr/bin/env python3
"""
Classify one item's dependencies as ready or not-ready to build on, reusing the
dashboard's own live-state classification and readiness rule.

plan-item-kickoff and plan-item-resolve both need this exact question
answered - "is it actually safe to stack new work on top of item X's
dependencies?" - and previously re-derived the rule
(:meth:`basstler.dashboard.plan.Item.is_ready_to_unblock_dependents`) in their own
SKILL.md prose instead of calling the code that already implements and tests
it. This script is that single call site.

Usage:
    python3 plan/check_dependency_readiness.py \\
        --plan /tmp/plan.yaml \\
        --pr-data /tmp/pr_data.json \\
        --item <item-id> \\
        [--plans-dir /tmp/plans]

pr_data.json shape: see :mod:`basstler.pull_request_state`, and
--plans-dir is the same directory dashboard/plan_page.py takes, so a dependency
naming <plan-id>/<item-id> resolves the way the dashboard resolves it.

Prints a one-line JSON list to stdout, one entry per entry in the item's
``depends_on``, in that order:
    [{"identifier": "<dependency reference>", "title": "<dependency title>",
      "live_state": "<LiveState value>", "is_ready": <bool>}, ...]
A dependency that doesn't resolve to a known item is reported with
``"title": null, "live_state": null, "is_ready": false`` - a broken
``depends_on`` reference is never silently treated as ready.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from basstler.dashboard.plan import Plan
from basstler.exceptions import PlanValidationError
from basstler.plan.command_arguments import PlanCommandArguments
from basstler.plan.dependencies import Dependency, DependencyResolver, PlanDirectory
from basstler.plan.validation import PlanValidator
from basstler.pull_request_state import PullRequestsByRepository
from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""


class UnknownItemError(ValueError):
    """
    Raised when the requested item id doesn't exist in the plan.
    """


class ReadinessField(StrEnum):
    """
    The keys one dependency's readiness carries once serialized.
    """

    IDENTIFIER = "identifier"
    TITLE = "title"
    LIVE_STATE = "live_state"
    IS_READY = "is_ready"


@dataclass(frozen=True)
class DependencyReadiness:
    """
    One ``depends_on`` entry, and whether it is safe to build on.
    """

    dependency: Dependency
    """
    The dependency, with its live state already classified.
    """

    def to_json(self) -> dict[str, Any]:
        """
        This readiness as the one entry the script prints for it.
        """
        live_state = self.dependency.live_state
        return {
            ReadinessField.IDENTIFIER.value: self.dependency.reference.text,
            ReadinessField.TITLE.value: self.dependency.title,
            ReadinessField.LIVE_STATE.value: live_state.value if live_state else None,
            ReadinessField.IS_READY.value: (
                self.dependency.is_ready_to_unblock_dependents()
            ),
        }

    @classmethod
    def of_item(
        cls,
        plan: Plan,
        item_identifier: str,
        pull_requests_by_repository: PullRequestsByRepository,
        plan_directory: PlanDirectory | None = None,
    ) -> list[DependencyReadiness]:
        """
        Classify every dependency of ``item_identifier`` as ready or not.

        :param plan: The already-validated plan.
        :param item_identifier: The effective identifier (``id`` or ``branch``) of the
            item whose dependencies should be checked.
        :param pull_requests_by_repository: Live pull request state for every repository
            referenced by the plan's items, and by any plan they depend on.
        :param plan_directory: The other plans a ``<plan-id>/<item-id>`` dependency
            resolves against, or ``None`` when only this plan's own items are available.
        :raises UnknownItemError: If ``item_identifier`` isn't in the plan.
        :return: One readiness per entry in the item's ``depends_on``, in that order.
        """
        item = plan.items_by_identifier.get(item_identifier)
        if item is None:
            raise UnknownItemError(f"no item {item_identifier!r} in plan {plan.id!r}")

        resolver = DependencyResolver(plan=plan, plan_directory=plan_directory)
        resolver.classify_live_states(pull_requests_by_repository)
        return [cls(dependency) for dependency in resolver.dependencies_of(item)]


def main() -> int:
    """
    Parse arguments, classify the item's dependencies, and print the result.

    See the module docstring for the CLI contract.
    """
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    PlanCommandArguments.add_to(parser)
    parser.add_argument("--item", required=True, help="The item id to check")
    arguments = parser.parse_args()
    plan_arguments = PlanCommandArguments.from_namespace(arguments)

    raw_plan = plan_arguments.read_manifest()
    try:
        PlanValidator(raw_plan, plan_arguments.plan_directory).validate()
    except PlanValidationError as error:
        logger.error(str(error))
        return 1
    plan = Plan.from_mapping(raw_plan)
    pull_requests_by_repository = plan_arguments.read_pull_requests_by_repository()

    try:
        results = DependencyReadiness.of_item(
            plan,
            arguments.item,
            pull_requests_by_repository,
            plan_arguments.plan_directory,
        )
    except UnknownItemError as error:
        logger.error(str(error))
        return 1

    logger.info(json.dumps([readiness.to_json() for readiness in results]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
