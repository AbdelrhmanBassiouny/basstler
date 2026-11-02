"""
Fill in what each item of a plan shows on its page, from live pull request data.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from basstler.plan.dependencies import DependencyResolver
from basstler.plan.model import ItemStatus
from basstler.plan_site.cards import ItemAction, ResolveAction, StartNowAction
from basstler.plan_site.plan import Item, Plan
from basstler.pull_request_state import (
    LiveState,
    PullRequestRecord,
    PullRequestsByRepository,
)
from basstler.repository import GitHubAddress

# %% the classifier


@dataclass
class ItemClassifier:
    """
    Fills in every item's live state, pull request, drift, dependency chips and action,
    and shows an item whose pull request merged as done.
    """

    plan: Plan
    """
    The plan whose items are classified.
    """

    pull_requests_by_repository: PullRequestsByRepository
    """
    Live pull request state for every repository the plan's items name.
    """

    dependencies: DependencyResolver
    """
    The resolver of the plan's dependencies.
    """

    locate_plan_page: Callable[[str], str] | None = None
    """
    Where another plan's page is published, given its id, or ``None`` when plan pages
    have no known address.
    """

    def classify(self) -> None:
        """
        Fill in every item of :attr:`plan` in place.
        """
        self.dependencies.classify_live_states(self.pull_requests_by_repository)
        for item in self.plan.items:
            self._classify_pull_request(item)
        for item in self.plan.items:
            item.dependency_chips = [
                dependency.chip(self.locate_plan_page)
                for dependency in self.dependencies.dependencies_of(item)
            ]
            item.action = self._action_for(item)
            item.pending_start_action = self._pending_start_action_for(item)

    def _classify_pull_request(self, item: Item) -> None:
        """
        Fill in what one item's own pull request decides about it.
        """
        if item.live_state is LiveState.MERGED:
            item.status = ItemStatus.DONE
        item.pull_request_record = self._pull_request_record_of(item)
        if item.pull_request_number is not None:
            item.pull_request_url = f"{GitHubAddress.WEB}/{self._repository_of(item)}/pull/{item.pull_request_number}"
        if item.pull_request_record is not None:
            item.upstream_pull_request_url = item.pull_request_record.upstream_link
        item.drift_description = self._drift_description_of(item)
        item.needs_review = (
            item.live_state is LiveState.OPEN_DRAFT
            and item.status is not ItemStatus.DEFERRED
        )

    def _repository_of(self, item: Item) -> str:
        """
        The repository one item's pull request is in.
        """
        return item.repository or self.plan.default_repository

    def _pull_request_record_of(self, item: Item) -> PullRequestRecord | None:
        """
        One item's live pull request, or ``None`` if it has none or GitHub returned
        none.
        """
        if item.pull_request_number is None:
            return None
        repository_pull_requests = self.pull_requests_by_repository.get(
            self._repository_of(item), {}
        )
        return repository_pull_requests.get(str(item.pull_request_number))

    def _action_for(self, item: Item) -> ItemAction | None:
        """
        One item's action button: none for a done item, or for a not-started item until
        its dependencies are ready to build on.
        """
        match item.status:
            case ItemStatus.DONE:
                return None
            case ItemStatus.NOT_STARTED:
                if not self.dependencies.dependencies_are_ready(item):
                    return None
                return self._start_action_for(item)
            case ItemStatus.BLOCKED:
                label = "Resolve"
            case ItemStatus.IN_PROGRESS:
                label = "Resume"
            case ItemStatus.DEFERRED:
                label = "Reconsider"
        return ResolveAction(
            label=label, plan_id=self.plan.id, item_identifier=item.identifier
        )

    def _start_action_for(self, item: Item) -> StartNowAction:
        """
        Build the action that starts one not-started item.
        """
        return StartNowAction(
            label="Start now",
            plan_id=self.plan.id,
            item_identifier=item.identifier,
        )

    def _pending_start_action_for(self, item: Item) -> StartNowAction | None:
        """
        Build the start action of a not-started item that only open draft dependencies
        hold back, or ``None`` for any other item.

        Reads :attr:`Item.action` and :attr:`Item.dependency_chips`, so runs after both
        are filled in.
        """
        if item.status is not ItemStatus.NOT_STARTED or item.action is not None:
            return None
        if not all(
            chip.dependency.is_ready_to_unblock_dependents()
            or chip.draft_pull_request is not None
            for chip in item.dependency_chips
        ):
            return None
        return self._start_action_for(item)

    @staticmethod
    def _drift_description_of(item: Item) -> str | None:
        """
        Why one item's status disagrees with its live state, or ``None`` if it agrees.
        """
        match item.live_state, item.status:
            case LiveState.NOT_FOUND, _:
                return f"pull request #{item.pull_request_number} not found on GitHub"
            case ((LiveState.OPEN_DRAFT | LiveState.OPEN_READY), ItemStatus.DONE):
                return f"marked done, but pull request #{item.pull_request_number} is still open"
            case LiveState.CLOSED_UNMERGED, (
                ItemStatus.IN_PROGRESS | ItemStatus.BLOCKED
            ):
                return f"marked {item.status.value}, but pull request #{item.pull_request_number} is closed unmerged"
            case LiveState.CLOSED_UNMERGED, ItemStatus.DONE:
                return f"marked done, but pull request #{item.pull_request_number} was closed without merging"
            case _:
                return None
