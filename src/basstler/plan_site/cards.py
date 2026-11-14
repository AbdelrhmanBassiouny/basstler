"""
What an item card and its sections show beyond the item itself: its dependency chips, its
action button and model dropdown, and the track and wave sections it sits in.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from basstler.class_property import classproperty
from basstler.plan.model_alias import ModelAlias

if TYPE_CHECKING:
    from basstler.github.repository import PullRequestReference
    from basstler.plan.dependencies import (
        Dependency,
        ResolvedDependency,
        UnresolvedDependency,
    )
    from basstler.plan_site.plan import Item, Track, Wave


# %% dependency chips


class DraftRecheckAttribute(StrEnum):
    """
    The data attributes a plan page's script re-checks blocking draft pull requests by.
    """

    PULL_REQUEST = "data-draft-pull-request"
    """
    On a dependency chip: the REST API address of the draft pull request it waits on.
    """

    READY_TITLE = "data-ready-title"
    """
    On a dependency chip: its hover title once that pull request no longer blocks.
    """

    START_ACTION = "data-start-action"
    """
    On a hidden action button: the start action its item gets once no draft holds it
    back.
    """

    FINISHED = "data-draft-recheck-finished"
    """
    On the page: every re-check has had its answer.
    """


class LiveStateAttribute(StrEnum):
    """
    The data attributes a plan page's script shows each pull request's live state by.
    """

    PULL_REQUEST = "data-live-pull-request"
    """
    On an item's pull request chip: that pull request's REST API address.
    """

    ITEM_STATUS = "data-item-status"
    """
    On an item's card: its status, as the page counts it.
    """

    STATUS_CHIP = "data-status-chip"
    """
    On an item's status chip.
    """

    STATUS_COUNT = "data-status-count"
    """
    On the page's count of one status: the status counted.
    """


class PlanTimeAttribute(StrEnum):
    """
    The data attributes of the times a plan page shows.
    """

    RELATIVE = "data-relative-time"
    """
    On a time the page's script shows relative to now.
    """

    REFRESHED = "data-refreshed-at"
    """
    On the time the page's states were last read from GitHub.
    """

    REFRESH_SOURCE = "data-refresh-source"
    """
    On the text saying where :attr:`REFRESHED` came from.
    """


class RefreshSource(StrEnum):
    """
    Where the states a plan page shows were last read from, as the page words it.
    """

    BUILD = "from the site build"
    """
    The build read them; the browser has not, or found nothing to read.
    """

    LIVE = "live from GitHub"
    """
    The browser read every pull request from GitHub.
    """

    REFUSED = "from the site build; GitHub refused the live check"
    """
    The browser asked GitHub, which refused or did not answer, as when the viewer's
    hourly limit is spent.
    """


@dataclass
class DependencyChip:
    """One ready-to-render ``needs`` chip on an item's card - see
    :attr:`Item.dependency_chips`."""

    dependency: Dependency
    """The dependency the chip stands for."""

    tooltip: str
    """The chip's hover title: the dependency's title, plus the plan holding
    it and its live state when that plan isn't this one, or the raw entry if
    it doesn't resolve at all."""

    card_url: str | None = None
    """Where the dependency's own card is shown: an anchor on this page for an
    item of this plan, or that card on its own plan's page - ``None`` when
    the entry resolves to nothing, or that page has no known address."""

    draft_pull_request: PullRequestReference | None = None
    """
    The open draft pull request that alone keeps the dependency from being ready, or
    ``None`` when no draft does.
    """

    @classproperty
    def tooltip_separator(cls) -> str:
        """Joins the parts of a cross-plan chip's hover title."""
        return " · "

    @classmethod
    def unresolved(cls, dependency: UnresolvedDependency) -> DependencyChip:
        """Build the chip for a ``depends_on`` entry nothing resolves.

        :param dependency: The dependency this chip stands for.
        """
        return cls(dependency=dependency, tooltip=dependency.reference.text)

    @classmethod
    def of_dependency(
        cls,
        dependency: ResolvedDependency,
        locate_plan_page: Callable[[str], str] | None,
    ) -> DependencyChip:
        """Build the chip for a resolved dependency.

        :param dependency: The dependency this chip stands for.
        :param locate_plan_page: Where another plan's page is published,
            given its id, or ``None`` when plan pages have no known address.
        """
        if not dependency.is_in_another_plan:
            return cls(
                dependency=dependency,
                tooltip=dependency.item.title,
                card_url=f"#{dependency.item.anchor}",
                draft_pull_request=dependency.draft_pull_request,
            )
        card_url = (
            f"{locate_plan_page(dependency.plan.id)}#{dependency.item.anchor}"
            if locate_plan_page is not None
            else None
        )
        return cls(
            dependency=dependency,
            tooltip=cls.tooltip_separator.join(
                [
                    dependency.item.title,
                    dependency.plan.title,
                    dependency.item.live_state.display_label,
                ]
            ),
            card_url=card_url,
            draft_pull_request=dependency.draft_pull_request,
        )


# %% action buttons


@dataclass(frozen=True)
class ItemAction(ABC):
    """One not-done item's actionable button - see
    :attr:`Item.action`. The label matches what the status actually calls
    for (starting fresh work reads differently from resolving a blocker),
    but every non-``done`` status gets one: there's always something
    actionable to do next besides waiting.

    Not a plain enum: each action carries the plan/item it targets, so its
    members can't be fixed singletons - one subclass per ``/plan-item-...``
    skill instead. Not instantiated directly - see :class:`StartNowAction`/
    :class:`ResolveAction`."""

    label: str
    """The button's text, e.g. ``"Start now"`` or ``"Resolve"``."""

    plan_id: str
    """The plan this action's command targets."""

    item_identifier: str
    """The item this action's command targets."""

    recommended_model: ModelAlias | None = None
    """The model the button's picker preselects, or ``None`` to preselect none."""

    @classproperty
    @abstractmethod
    def skill_command_name(cls) -> str:
        """The ``/plan-item-...`` skill this action invokes - fixed per
        subclass, since which skill an action routes to never varies per
        instance (only :attr:`label` does, e.g. ``"Resolve"`` vs. ``"Resume"``
        for the same :class:`ResolveAction`)."""

    @property
    def command(self) -> str:
        """The full command copied to the clipboard when the button is
        clicked."""
        return f"{self.skill_command_name} {self.plan_id} {self.item_identifier}"


@dataclass(frozen=True)
class StartNowAction(ItemAction):
    """Routes a not-started item, once every dependency is ready, to
    ``plan-item-kickoff``."""

    @classproperty
    def skill_command_name(cls) -> str:
        """:return: The ``plan-item-kickoff`` skill."""
        return "/plan-item-kickoff"


@dataclass(frozen=True)
class ResolveAction(ItemAction):
    """Routes a blocked, in-progress, or deferred item to
    ``plan-item-resolve`` - :attr:`ItemAction.label` is worded to match
    which of those three it actually is."""

    @classproperty
    def skill_command_name(cls) -> str:
        """:return: The ``plan-item-resolve`` skill."""
        return "/plan-item-resolve"


# %% track and wave sections


@dataclass
class TrackSection:
    """
    One track's rendering context: its declared info plus its items.
    """

    track: Track
    """
    The track itself.
    """

    items: list[Item]
    """
    The track's items, each after the same-track item it depends on - empty if the
    track has none yet.
    """

    @property
    def empty_state_message(self) -> str:
        """
        What to show in place of an item list when the track has none yet: the track's
        own :attr:`Track.description`, or a generic fallback.
        """
        return self.track.description or "No tracked items."

    @classmethod
    def of_track(cls, track: Track, track_items: list[Item]) -> TrackSection:
        """
        :param track: The track.
        :param track_items: The track's items, in manifest order.
        :return: The track's section, with its items ordered depth-first by their first
            same-track dependency.
        """
        identifiers = {item.identifier for item in track_items}
        dependents: dict[str | None, list[Item]] = {}
        for item in track_items:
            parent = next(
                (entry for entry in item.depends_on if entry in identifiers),
                None,
            )
            dependents.setdefault(parent, []).append(item)
        ordered_items: list[Item] = []
        pending = list(reversed(dependents.get(None, [])))
        while pending:
            item = pending.pop()
            ordered_items.append(item)
            pending.extend(reversed(dependents.get(item.identifier, [])))
        return cls(track=track, items=ordered_items)


@dataclass
class WaveSection:
    """One wave's rendering context: its declared info plus its tracks, in order."""

    wave: Wave
    """The wave itself."""

    tracks: list[TrackSection]
    """The wave's tracks, in declaration order."""
