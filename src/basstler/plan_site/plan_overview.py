"""
What a plan's page points to next, and the plan's state as its page shows it.
"""

from __future__ import annotations

from dataclasses import dataclass

from basstler.plan.dependencies import DependencyResolver
from basstler.plan.model import ItemStatus
from basstler.plan.structure import Item, Plan

# %% next steps


@dataclass
class NextSteps:
    """
    The items a plan's page lists as next steps.
    """

    ready_to_start: list[Item]
    """
    Not-started items whose dependencies are all ready to build on.
    """

    blocker_maybe_cleared: list[Item]
    """
    Blocked items with at least one dependency ready to build on.
    """

    ready_to_review: list[Item]
    """
    Unblocked items needing review whose dependencies all have a pull request or are
    done.
    """

    @classmethod
    def of_plan(cls, plan: Plan, dependencies: DependencyResolver) -> NextSteps:
        """
        :param plan: A plan whose items' live state is filled in.
        :param dependencies: The resolver of the plan's dependencies.
        :return: The plan's next steps.
        """
        return cls(
            ready_to_start=[
                item
                for item in plan.items
                if item.status is ItemStatus.NOT_STARTED
                and dependencies.dependencies_are_ready(item)
            ],
            blocker_maybe_cleared=[
                item
                for item in plan.items
                if item.status is ItemStatus.BLOCKED
                and any(
                    dependency.is_ready_to_unblock_dependents()
                    for dependency in dependencies.dependencies_of(item)
                )
            ],
            ready_to_review=[
                item
                for item in plan.items
                if item.needs_review
                and item.status is not ItemStatus.BLOCKED
                and all(
                    dependency.is_ready_for_dependent_review()
                    for dependency in dependencies.dependencies_of(item)
                )
            ],
        )


# %% the overview


@dataclass
class PlanOverview:
    """
    A plan's state as its page shows it: how many items stand where, and which need
    attention next.
    """

    status_counts: dict[ItemStatus, int]
    """
    How many items carry each :class:`ItemStatus`, landed items counted as done.
    """

    drift_items: list[str]
    """
    Titles of items whose manifest status disagrees with live GitHub state.
    """

    ready_to_start: list[str]
    """
    Titles of :attr:`NextSteps.ready_to_start`.
    """

    blocker_maybe_cleared: list[str]
    """
    Titles of :attr:`NextSteps.blocker_maybe_cleared`.
    """

    ready_to_review: list[str]
    """
    Titles of :attr:`NextSteps.ready_to_review`.
    """

    @classmethod
    def of_plan(cls, plan: Plan, next_steps: NextSteps) -> PlanOverview:
        """
        :param plan: A plan whose items' live state is filled in.
        :param next_steps: The plan's next steps.
        :return: The plan's overview.
        """
        status_counts = {status: 0 for status in ItemStatus}
        status_counts[ItemStatus.DONE] = plan.landed_item_count
        for item in plan.items:
            status_counts[item.status] += 1
        return cls(
            status_counts=status_counts,
            drift_items=[item.title for item in plan.drifted_items],
            ready_to_start=[item.title for item in next_steps.ready_to_start],
            blocker_maybe_cleared=[
                item.title for item in next_steps.blocker_maybe_cleared
            ],
            ready_to_review=[item.title for item in next_steps.ready_to_review],
        )
