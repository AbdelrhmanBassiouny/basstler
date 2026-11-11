"""
A plan.yaml as its page on the plan site reads it: its waves, tracks and items, each
item carrying the live state the renderer fills in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
from typing import TYPE_CHECKING, Any

from basstler.plan.model import ItemStatus, ManifestKey
from basstler.plan_site.progress_stage import ProgressStage
from basstler.pull_request_state import LiveState, PullRequestRecord
from basstler.render_common import sanitize_http_url
from basstler.repository import GitHubAddress, PullRequestReference

if TYPE_CHECKING:
    from basstler.plan_site.cards import DependencyChip, ItemAction, StartNowAction


# %% waves and tracks


@dataclass
class Wave:
    """A sequential phase of the initiative - wave 2 generally starts once
    wave 1 has landed."""

    id: str
    """The wave's stable identifier, referenced by :attr:`Track.wave`."""

    name: str
    """
    The wave's display name.
    """

    description: str | None = None
    """
    An optional one-line note about the wave, shown in the plan page's header.
    """

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> Wave:
        """Build a wave from one entry of plan.yaml's ``waves[]`` - only
        called after :meth:`PlanValidator.validate` has already confirmed the data
        is well-formed."""
        return cls(
            id=data[ManifestKey.IDENTIFIER.key],
            name=data[ManifestKey.NAME.key],
            description=data.get(ManifestKey.DESCRIPTION.key),
        )


@dataclass
class Track:
    """A parallel line of work within a wave - its items can proceed
    independently of other tracks in the same wave."""

    id: str
    """
    The track's stable identifier, referenced by :attr:`Item.track`.
    """

    name: str
    """
    The track's display name.
    """

    wave: str
    """
    The :attr:`Wave.id` this track belongs to.
    """

    description: str | None = None
    """
    Shown in place of an item list when the track has no items yet.
    """

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> Track:
        """Build a track from one entry of plan.yaml's ``tracks[]`` - only
        called after :meth:`PlanValidator.validate` has already confirmed the data
        is well-formed."""
        return cls(
            id=data[ManifestKey.IDENTIFIER.key],
            name=data[ManifestKey.NAME.key],
            wave=data[ManifestKey.WAVE.key],
            description=data.get(ManifestKey.DESCRIPTION.key),
        )


# %% items


@dataclass
class Item:
    """
    One tracked unit of work (typically one branch/pull request) within a plan.
    """

    title: str
    """
    The item's display title.
    """

    branch: str | None
    """
    The git branch this item is implemented on, or ``None`` before one exists.
    """

    track: str
    """
    The :attr:`Track.id` this item belongs to.
    """

    status: ItemStatus
    """
    The manifest's status, shown as done once the item's pull request has merged.
    """

    id: str | None = None
    """
    The item's stable identifier, defaulting to :attr:`branch` if unset.
    """

    pull_request_number: int | None = None
    """
    The pull request number tracking this item, if one exists yet.
    """

    repository: str | None = None
    """
    Overrides the plan's ``default_repository`` for this item, if set.
    """

    session: str | None = None
    """
    A link to the session that produced this item, if any.
    """

    notes: str | None = None
    """
    Free-text notes shown on the item's card.
    """

    depends_on: list[str] = field(default_factory=list)
    """
    The identifiers of items that must complete before this one can start.
    """

    blockers: list[str] = field(default_factory=list)
    """
    Free-text descriptions of what's currently blocking this item.
    """

    live_state: LiveState = field(default=LiveState.NO_PULL_REQUEST, init=False)
    """
    This item's live GitHub state.
    """

    drift_description: str | None = field(default=None, init=False)
    """
    Why :attr:`status` disagrees with :attr:`live_state`, if it does.
    """

    access_warning: str | None = field(default=None, init=False)
    """
    Why the build could not read this item's pull request, and how to let it, if it
    could not.
    """

    pull_request_url: str | None = field(default=None, init=False)
    """
    This item's pull request on GitHub, if it has one.
    """

    pull_request_reference: PullRequestReference | None = field(
        default=None, init=False
    )
    """
    This item's pull request, if it has one.
    """

    pull_request_api_url: str | None = field(default=None, init=False)
    """
    The same pull request's address in GitHub's REST pulls API, which the page re-reads
    in the browser.
    """

    pull_request_record: PullRequestRecord | None = field(default=None, init=False)
    """
    This item's live pull request, if GitHub has one by its number.
    """

    upstream_pull_request_url: str | None = field(default=None, init=False)
    """
    The upstream pull request its pull request's description links, if any.
    """

    dependency_chips: list[DependencyChip] = field(default_factory=list, init=False)
    """
    One chip per entry of :attr:`depends_on`.
    """

    action: ItemAction | None = field(default=None, init=False)
    """
    This item's action button; ``None`` for a done item, and for a not-started item
    until its dependencies are ready to build on.
    """

    pending_start_action: StartNowAction | None = field(default=None, init=False)
    """
    The start action of a not-started item that only open draft dependencies hold back;
    ``None`` for any other item.
    """

    needs_review: bool = field(default=False, init=False)
    """
    Whether this item has an open draft pull request and is not deferred: every pull
    request stays a draft until its author has reviewed it.
    """

    @property
    def has_open_pull_request(self) -> bool:
        """
        Whether this item currently has an open (draft or ready) pull request.
        """
        return self.live_state in (LiveState.OPEN_DRAFT, LiveState.OPEN_READY)

    @property
    def is_started(self) -> bool:
        """
        Whether work on this item has begun: it has a pull request, or its status is
        past not started and it is not set aside.
        """
        return self.live_state is not LiveState.NO_PULL_REQUEST or self.status in (
            ItemStatus.IN_PROGRESS,
            ItemStatus.BLOCKED,
            ItemStatus.DONE,
        )

    @property
    def is_reviewed(self) -> bool:
        """
        Whether this item's pull request is past its author's review: out of draft, or
        merged.
        """
        return self.live_state in (LiveState.OPEN_READY, LiveState.MERGED)

    @property
    def reached_stages(self) -> list[ProgressStage]:
        """
        The progress stages this item has reached, earliest first.
        """
        reached = {
            ProgressStage.STARTED: self.is_started,
            ProgressStage.REVIEWED: self.is_reviewed,
            ProgressStage.DONE: self.is_effectively_done(),
        }
        return [stage for stage in ProgressStage if reached[stage]]

    @property
    def identifier(self) -> str:
        """
        The item's effective identifier: :attr:`id`, or :attr:`branch` if unset.
        """
        return self.id or self.branch

    @property
    def anchor(self) -> str:
        """
        The ``id`` of this item's card on its plan's page, which a link names after
        ``#`` to reach that card.
        """
        return self.anchor_of(self.identifier)

    @staticmethod
    def anchor_of(identifier: str) -> str:
        """
        :param identifier: An item's :attr:`identifier`.
        :return: The :attr:`anchor` of that item's card.
        """
        return f"item-{identifier}"

    @property
    def status_and_drift_css_class(self) -> str:
        """
        The item card's dynamic CSS class suffix: ``status-<member name>``, plus ``has-
        drift`` once :attr:`drift_description` is set.
        """
        drift_suffix = " has-drift" if self.drift_description else ""
        return f"{self.status_css_class(self.status)}{drift_suffix}"

    @staticmethod
    def status_css_class(status: ItemStatus) -> str:
        """
        :param status: An item status.
        :return: The CSS class a card with that status carries.
        """
        return f"status-{status.name.lower()}"

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> Item:
        """Build an item from one entry of plan.yaml's ``items[]`` - only
        called after :meth:`PlanValidator.validate` has already confirmed the data
        is well-formed."""
        notes = data.get(ManifestKey.NOTES.key)
        return cls(
            title=data[ManifestKey.TITLE.key],
            branch=data.get(ManifestKey.BRANCH.key),
            track=data[ManifestKey.TRACK.key],
            status=ItemStatus(data[ManifestKey.STATUS.key]),
            id=data.get(ManifestKey.IDENTIFIER.key),
            pull_request_number=data.get(ManifestKey.PULL_REQUEST_NUMBER.key),
            repository=data.get(ManifestKey.REPOSITORY.key),
            session=sanitize_http_url(data.get(ManifestKey.SESSION.key)),
            notes=notes.strip() if notes else None,
            depends_on=list(data.get(ManifestKey.DEPENDS_ON.key) or []),
            blockers=list(data.get(ManifestKey.BLOCKERS.key) or []),
        )

    def is_effectively_done(self) -> bool:
        """
        Whether this item can unblock a dependent, by manifest status or live state.
        """
        return self.status is ItemStatus.DONE or self.live_state is LiveState.MERGED

    def is_ready_to_unblock_dependents(self) -> bool:
        """Whether a dependent item can safely start stacking its own branch
        on this one: done, merged, or its pull request is open and out of draft (ready
        for review). Stacking on a same-track dependency is this repo's
        normal workflow well before that dependency merges - a still-open
        draft is the one state that isn't safe to build on top of, since it
        can still see heavy rework."""
        return self.is_effectively_done() or self.live_state is LiveState.OPEN_READY

    def is_ready_for_dependent_review(self) -> bool:
        """
        Whether a dependent's pull request is worth reviewing yet: this item's own pull
        request exists and has reached review, whether it is still open or has already
        landed. Having no pull request at all is the one state that makes a dependent
        premature to review.

        ..note:: Deliberately weaker than :meth:`is_ready_to_unblock_dependents`,
            which additionally requires being out of draft: building a branch on
            a dependency that can still see heavy rework is unsafe, while merely
            reviewing the branch above it is not.
        """
        return self.has_open_pull_request or self.is_effectively_done()


# %% the plan


@dataclass
class Plan:
    """
    A full initiative spanning multiple pull requests and sessions, as read from
    plan.yaml.
    """

    id: str
    """The plan's stable identifier - the directory name under ``plans/``."""

    title: str
    """
    The plan's display title.
    """

    description: str
    """
    A one-line description shown under the title.
    """

    default_repository: str
    """
    The ``"owner/repo"`` items resolve pull requests against unless they override it.
    """

    waves: list[Wave]
    """
    The plan's sequential phases, in order.
    """

    tracks: list[Track]
    """
    The plan's parallel lines of work, each tagged with a wave.
    """

    items: list[Item]
    """
    The plan's tracked units of work, each tagged with a track.
    """

    tracking_issue: int | None = None
    """
    The coordination-mailbox issue or pull request number for structural changes, if
    any.
    """

    @cached_property
    def items_by_identifier(self) -> dict[str, Item]:
        """
        Each of :attr:`items`, by its effective id.
        """
        return {item.identifier: item for item in self.items}

    @property
    def drifted_items(self) -> list[Item]:
        """
        The items whose :attr:`Item.drift_description` is set.
        """
        return [item for item in self.items if item.drift_description]

    @property
    def repository_url(self) -> str:
        """
        :attr:`default_repository`'s GitHub URL, ready for the masthead link.
        """
        return f"{GitHubAddress.WEB}/{self.default_repository}"

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> Plan:
        """Build a plan from a freshly-loaded plan.yaml - only called after
        :meth:`PlanValidator.validate` has already confirmed the data is well-formed."""
        return cls(
            id=data[ManifestKey.IDENTIFIER.key],
            title=data[ManifestKey.TITLE.key],
            description=data[ManifestKey.DESCRIPTION.key],
            default_repository=data[ManifestKey.DEFAULT_REPOSITORY.key],
            waves=[
                Wave.from_mapping(wave) for wave in data.get(ManifestKey.WAVES.key, [])
            ],
            tracks=[
                Track.from_mapping(track)
                for track in data.get(ManifestKey.TRACKS.key, [])
            ],
            items=[
                Item.from_mapping(item) for item in data.get(ManifestKey.ITEMS.key, [])
            ],
            tracking_issue=data.get(ManifestKey.TRACKING_ISSUE.key),
        )
