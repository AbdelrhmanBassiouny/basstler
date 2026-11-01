"""
Classify one item's dependencies as ready or not-ready to build on, reusing the
dashboard's own live-state classification and readiness rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from basstler.dashboard.plan import Plan
from basstler.plan.dependencies import Dependency, DependencyResolver, PlanDirectory
from basstler.pull_request_state import PullRequestsByRepository


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
        This readiness as the one entry the item brief serializes for it.
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
