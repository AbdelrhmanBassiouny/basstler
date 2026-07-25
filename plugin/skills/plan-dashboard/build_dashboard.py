#!/usr/bin/env python3
"""Render a single plan's dashboard HTML from its manifest + live GitHub data.

Generic, plan-agnostic: every plan-specific value (title, items, tracking
link, ...) comes from the inputs below, never hardcoded here. This is the
deterministic half of /plan-dashboard - the skill (SKILL.md) is responsible
for gathering the inputs (git show on the personal-notes branch, GitHub API
calls) and for the one step this script cannot do itself: calling the
Artifact tool to publish the HTML this script produces.

Usage:
    python3 build_dashboard.py \\
        --plan /tmp/plan.yaml \\
        --roadmap /tmp/roadmap.md \\
        --pr-data /tmp/pr_data.json \\
        --output /tmp/dashboard.html \\
        [--tracking-url "https://github.com/<owner>/<repo>/issues/<n>"]

pr_data.json shape: {"<owner>/<repo>": {"<pr_number>": {"state": "open"|
"closed", "draft": bool, "merged_at": str|null}}} - one entry per PR number
referenced by any item, gathered by the skill via
mcp__github__list_pull_requests (bulk, paginated) before falling back to
mcp__github__pull_request_read for anything outside that page window.

Prints a one-line JSON summary to stdout (status counts, drift count,
ready-to-start/blocker-maybe-cleared item titles) so the calling skill can
report back without re-parsing the HTML it just wrote.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

from render_common import escape_html, render_markdown_to_html

MAXIMUM_DEPENDENCY_STACK_LEVEL = 4
"""Same-track dependency chains deeper than this wrap back to indent level 0."""


class ItemStatus(StrEnum):
    """The thin, manually-maintained status a plan.yaml item carries.

    Deliberately thin: everything about a PR's actual GitHub state
    (open/draft/merged/CI/review) is never stored here - it is always
    live-fetched and represented separately by :class:`LiveState`.
    """

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DEFERRED = "deferred"
    DONE = "done"

    @property
    def display_label(self) -> str:
        """The human-readable label shown in the dashboard UI for this status."""
        match self:
            case ItemStatus.NOT_STARTED:
                return "Not started"
            case ItemStatus.IN_PROGRESS:
                return "In progress"
            case ItemStatus.BLOCKED:
                return "Blocked"
            case ItemStatus.DEFERRED:
                return "Deferred"
            case ItemStatus.DONE:
                return "Done"


class LiveState(StrEnum):
    """An item's live GitHub PR state, classified fresh on every run."""

    MERGED = "merged"
    OPEN_DRAFT = "open_draft"
    OPEN_READY = "open_ready"
    CLOSED_UNMERGED = "closed_unmerged"
    NOT_FOUND = "not_found"

    @property
    def display_label(self) -> str:
        """The human-readable label shown in the dashboard UI for this state."""
        match self:
            case LiveState.MERGED:
                return "Merged"
            case LiveState.OPEN_DRAFT:
                return "Open · Draft"
            case LiveState.OPEN_READY:
                return "Open · Ready"
            case LiveState.CLOSED_UNMERGED:
                return "Closed (unmerged)"
            case LiveState.NOT_FOUND:
                return "Not found on GitHub"


def live_state_display_label(live_state: LiveState | None) -> str:
    """The human-readable label for an item's live state, including "no PR yet".

    :param live_state: The item's classified live state, or ``None`` if the
        item has no ``pr`` set at all (as opposed to :attr:`LiveState.NOT_FOUND`,
        which means a ``pr`` was set but GitHub has no matching PR).
    :return: The label to show in the dashboard UI.
    """
    return live_state.display_label if live_state is not None else "No PR yet"


class ValidationProblemKind(StrEnum):
    """The category of a single plan.yaml validation problem."""

    INVALID_SCHEMA_VERSION = "invalid_schema_version"
    DUPLICATE_ITEM_ID = "duplicate_item_id"
    UNKNOWN_TRACK = "unknown_track"
    UNKNOWN_WAVE = "unknown_wave"
    INVALID_DEPENDS_ON = "invalid_depends_on"
    UNKNOWN_DEPENDENCY = "unknown_dependency"
    UNKNOWN_STATUS = "unknown_status"


@dataclass
class ValidationProblem:
    """A single, human-readable problem found while validating a plan.yaml."""

    kind: ValidationProblemKind
    """Which validation rule this problem violates."""

    message: str
    """The human-readable description shown to the user."""


class PlanValidationError(Exception):
    """Raised when a plan.yaml fails schema validation - see plans/README.md."""

    def __init__(self, problems: list[ValidationProblem]) -> None:
        self.problems = problems
        """Every problem found - collected rather than stopping at the first
        one, since a broken manifest is itself something the user needs the
        full picture of, not a single symptom."""
        super().__init__("; ".join(problem.message for problem in problems))


def validate_plan(plan: dict[str, Any]) -> None:
    """Check the same schema rules plan-create is required to produce
    manifests that pass.

    :param plan: The raw, freshly-``yaml.safe_load``-ed plan.yaml content.
    :raises PlanValidationError: If any rule is violated, carrying every
        problem found.
    """
    problems: list[ValidationProblem] = []

    if plan.get("schema_version") != 1:
        problems.append(
            ValidationProblem(
                ValidationProblemKind.INVALID_SCHEMA_VERSION,
                f"schema_version must be 1, got {plan.get('schema_version')!r}",
            )
        )

    item_identifiers = [
        item.get("id") or item.get("branch") for item in plan.get("items", [])
    ]
    if len(item_identifiers) != len(set(item_identifiers)):
        seen: set[str] = set()
        duplicate_identifiers = {
            identifier
            for identifier in item_identifiers
            if identifier in seen or seen.add(identifier)
        }
        problems.append(
            ValidationProblem(
                ValidationProblemKind.DUPLICATE_ITEM_ID,
                f"duplicate item id(s): {sorted(duplicate_identifiers)}",
            )
        )

    track_identifiers = {track["id"] for track in plan.get("tracks", [])}
    wave_identifiers = {wave["id"] for wave in plan.get("waves", [])}
    item_identifier_set = set(item_identifiers)

    for item in plan.get("items", []):
        item_identifier = item.get("id") or item.get("branch")
        if item.get("track") not in track_identifiers:
            problems.append(
                ValidationProblem(
                    ValidationProblemKind.UNKNOWN_TRACK,
                    f"item {item_identifier!r} has unknown track {item.get('track')!r}",
                )
            )
        if item.get("status") not in {status.value for status in ItemStatus}:
            problems.append(
                ValidationProblem(
                    ValidationProblemKind.UNKNOWN_STATUS,
                    f"item {item_identifier!r} has unknown status {item.get('status')!r}",
                )
            )
        depends_on = item.get("depends_on")
        if depends_on is not None and not isinstance(depends_on, list):
            problems.append(
                ValidationProblem(
                    ValidationProblemKind.INVALID_DEPENDS_ON,
                    f"item {item_identifier!r} depends_on must be a list, got {type(depends_on).__name__}",
                )
            )
        else:
            for dependency_identifier in depends_on or []:
                if dependency_identifier not in item_identifier_set:
                    problems.append(
                        ValidationProblem(
                            ValidationProblemKind.UNKNOWN_DEPENDENCY,
                            f"item {item_identifier!r} depends_on unknown id {dependency_identifier!r}",
                        )
                    )

    for track in plan.get("tracks", []):
        if track.get("wave") not in wave_identifiers:
            problems.append(
                ValidationProblem(
                    ValidationProblemKind.UNKNOWN_WAVE,
                    f"track {track['id']!r} has unknown wave {track.get('wave')!r}",
                )
            )

    if problems:
        raise PlanValidationError(problems)


@dataclass
class PullRequestRecord:
    """The live GitHub state of one pull request, as gathered by the skill."""

    state: str
    """GitHub's own PR state string: ``"open"`` or ``"closed"``."""

    draft: bool = False
    """Whether the PR is currently a draft."""

    merged_at: str | None = None
    """The PR's merge timestamp, or ``None`` if it was never merged."""

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> PullRequestRecord:
        """Build a record from one entry of ``pr_data.json``."""
        return cls(
            state=data["state"],
            draft=data.get("draft", False),
            merged_at=data.get("merged_at"),
        )


PullRequestsByRepository = dict[str, dict[str, PullRequestRecord]]


@dataclass
class Wave:
    """A sequential phase of the initiative - wave 2 generally starts once
    wave 1 has landed."""

    id: str
    """The wave's stable identifier, referenced by :attr:`Track.wave`."""

    name: str
    """The wave's display name."""


@dataclass
class Track:
    """A parallel line of work within a wave - its items can proceed
    independently of other tracks in the same wave."""

    id: str
    """The track's stable identifier, referenced by :attr:`Item.track`."""

    name: str
    """The track's display name."""

    wave: str
    """The :attr:`Wave.id` this track belongs to."""

    description: str | None = None
    """Shown in place of an item list when the track has no items yet."""


@dataclass
class Item:
    """One tracked unit of work (typically one branch/PR) within a plan."""

    title: str
    """The item's display title."""

    branch: str
    """The git branch this item is implemented on."""

    track: str
    """The :attr:`Track.id` this item belongs to."""

    status: ItemStatus
    """The manually-maintained status - see :class:`ItemStatus`."""

    id: str | None = None
    """The item's stable identifier, defaulting to :attr:`branch` if unset."""

    pr: int | None = None
    """The PR number tracking this item, if one exists yet."""

    repo: str | None = None
    """Overrides the plan's ``default_repo`` for this item, if set."""

    session: str | None = None
    """A link to the session that produced this item, if any."""

    notes: str | None = None
    """Free-text notes shown on the item's card."""

    depends_on: list[str] = field(default_factory=list)
    """The identifiers of items that must complete before this one can start."""

    blockers: list[str] = field(default_factory=list)
    """Free-text descriptions of what's currently blocking this item."""

    live_state: LiveState | None = field(default=None, init=False)
    """This item's live GitHub state, filled in by :meth:`DashboardRenderer.render`."""

    drift_description: str | None = field(default=None, init=False)
    """Why :attr:`status` disagrees with :attr:`live_state`, if it does."""

    @property
    def identifier(self) -> str:
        """The item's effective identifier: :attr:`id`, or :attr:`branch` if unset."""
        return self.id or self.branch

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> Item:
        """Build an item from one entry of plan.yaml's ``items[]`` - only
        called after :func:`validate_plan` has already confirmed the data
        is well-formed."""
        return cls(
            title=data["title"],
            branch=data["branch"],
            track=data["track"],
            status=ItemStatus(data["status"]),
            id=data.get("id"),
            pr=data.get("pr"),
            repo=data.get("repo"),
            session=data.get("session"),
            notes=data.get("notes"),
            depends_on=list(data.get("depends_on") or []),
            blockers=list(data.get("blockers") or []),
        )

    def is_effectively_done(self) -> bool:
        """Whether this item can unblock a dependent, by manifest status or live state."""
        return self.status is ItemStatus.DONE or self.live_state is LiveState.MERGED


@dataclass
class Plan:
    """A full multi-PR/multi-session initiative, as read from plan.yaml."""

    id: str
    """The plan's stable identifier - the directory name under ``plans/``."""

    title: str
    """The plan's display title."""

    description: str
    """A one-line description shown under the title."""

    default_repo: str
    """The ``"owner/repo"`` items resolve PRs against unless they override it."""

    waves: list[Wave]
    """The plan's sequential phases, in order."""

    tracks: list[Track]
    """The plan's parallel lines of work, each tagged with a wave."""

    items: list[Item]
    """The plan's tracked units of work, each tagged with a track."""

    tracking_issue: int | None = None
    """The coordination-mailbox issue/PR number for structural changes, if any."""

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> Plan:
        """Build a plan from a freshly-loaded plan.yaml - only called after
        :func:`validate_plan` has already confirmed the data is well-formed."""
        return cls(
            id=data["id"],
            title=data["title"],
            description=data["description"],
            default_repo=data["default_repo"],
            waves=[Wave(**wave) for wave in data.get("waves", [])],
            tracks=[Track(**track) for track in data.get("tracks", [])],
            items=[Item.from_mapping(item) for item in data.get("items", [])],
            tracking_issue=data.get("tracking_issue"),
        )


@dataclass
class DashboardSummary:
    """The one-line JSON summary this script prints to stdout on success."""

    status_counts: dict[ItemStatus, int]
    """How many items carry each :class:`ItemStatus`."""

    drift_items: list[str]
    """Titles of items whose manifest status disagrees with live GitHub state."""

    ready_to_start: list[str]
    """Titles of not-started/blocked items whose dependencies are all done."""

    blocker_maybe_cleared: list[str]
    """Titles of blocked items with some (not all) dependencies done."""

    def to_json_dict(self) -> dict[str, Any]:
        """Render to the plain-dict shape the calling skill expects."""
        return {
            "counts": {
                status.value: count for status, count in self.status_counts.items()
            },
            "drift_count": len(self.drift_items),
            "drift_items": self.drift_items,
            "ready_to_start": self.ready_to_start,
            "blocker_maybe_cleared": self.blocker_maybe_cleared,
        }


@dataclass
class DashboardRenderer:
    """Renders one :class:`Plan` (plus its live PR data and roadmap text)
    into the dashboard's HTML.

    A dataclass rather than a bag of closures over shared state: each
    rendering concern (an item card, a dependency chip, a track's stacked
    items, ...) is an independently named, independently testable method
    instead of a nested function capturing outer variables.
    """

    plan: Plan
    """The plan being rendered."""

    roadmap_text: str
    """The plan's ``roadmap.md`` narrative content."""

    pr_data: PullRequestsByRepository
    """Live PR state for every repository referenced by the plan's items."""

    tracking_url: str | None
    """The tracking issue/PR's ``html_url``, if the plan has one."""

    items_by_identifier: dict[str, Item] = field(init=False)
    """Every item, keyed by :attr:`Item.identifier`."""

    def __post_init__(self) -> None:
        self.items_by_identifier = {item.identifier: item for item in self.plan.items}

    def render(self) -> tuple[str, DashboardSummary]:
        """Classify live state/drift for every item, then render the full page.

        :return: The rendered HTML, and the summary to print on stdout.
        """
        self._classify_items()
        drift_items = [item for item in self.plan.items if item.drift_description]
        ready_to_start, blocker_maybe_cleared = self._compute_next_steps()

        template = (Path(__file__).parent / "dashboard_template.html").read_text()
        output = (
            template.replace("{{TITLE}}", escape_html(self.plan.title))
            .replace("{{DESCRIPTION}}", escape_html(self.plan.description))
            .replace("{{REPO}}", escape_html(self.plan.default_repo))
            .replace("{{TOTAL}}", str(len(self.plan.items)))
            .replace("{{TRACKING_PR_LINK}}", self._render_tracking_link())
            .replace("{{SUMMARY_PILLS}}", self._render_summary_pills())
            .replace("{{ALERT_HTML}}", self._render_alert_banner(drift_items))
            .replace(
                "{{NEXT_HTML}}",
                self._render_next_steps(
                    drift_items, ready_to_start, blocker_maybe_cleared
                ),
            )
            .replace("{{ROADMAP_HTML}}", render_markdown_to_html(self.roadmap_text))
            .replace("{{WAVES_HTML}}", self._render_waves())
        )

        summary = DashboardSummary(
            status_counts=self._status_counts(),
            drift_items=[item.title for item in drift_items],
            ready_to_start=[item.title for item in ready_to_start],
            blocker_maybe_cleared=[item.title for item in blocker_maybe_cleared],
        )
        return output, summary

    def _classify_items(self) -> None:
        for item in self.plan.items:
            item.live_state = self._live_state_of(item)
            item.drift_description = self._drift_description_of(item)

    def _live_state_of(self, item: Item) -> LiveState | None:
        if item.pr is None:
            return None
        repository_pull_requests = self.pr_data.get(
            item.repo or self.plan.default_repo, {}
        )
        pull_request = repository_pull_requests.get(str(item.pr))
        if pull_request is None:
            return LiveState.NOT_FOUND
        if pull_request.merged_at:
            return LiveState.MERGED
        if pull_request.state == "closed":
            return LiveState.CLOSED_UNMERGED
        if pull_request.draft:
            return LiveState.OPEN_DRAFT
        return LiveState.OPEN_READY

    @staticmethod
    def _drift_description_of(item: Item) -> str | None:
        live_state = item.live_state
        match live_state, item.status:
            case LiveState.NOT_FOUND, _:
                return f"PR #{item.pr} not found on GitHub"
            case (LiveState.OPEN_DRAFT | LiveState.OPEN_READY), ItemStatus.DONE:
                return f"marked done, but PR #{item.pr} is still open"
            case LiveState.MERGED, (
                ItemStatus.NOT_STARTED | ItemStatus.BLOCKED | ItemStatus.DEFERRED
            ):
                return (
                    f"marked {item.status.value}, but PR #{item.pr} is already merged"
                )
            case (LiveState.MERGED | LiveState.CLOSED_UNMERGED), (
                ItemStatus.IN_PROGRESS | ItemStatus.BLOCKED
            ):
                return f"marked {item.status.value}, but PR #{item.pr} is {live_state.value.replace('_', ' ')}"
            case _:
                return None

    def _compute_next_steps(self) -> tuple[list[Item], list[Item]]:
        ready_to_start: list[Item] = []
        blocker_maybe_cleared: list[Item] = []
        for item in self.plan.items:
            dependencies = [
                self.items_by_identifier[identifier]
                for identifier in item.depends_on
                if identifier in self.items_by_identifier
            ]
            if not dependencies or item.status not in (
                ItemStatus.NOT_STARTED,
                ItemStatus.BLOCKED,
            ):
                continue
            done_count = sum(
                dependency.is_effectively_done() for dependency in dependencies
            )
            if done_count == len(dependencies):
                ready_to_start.append(item)
            elif item.status is ItemStatus.BLOCKED and done_count > 0:
                blocker_maybe_cleared.append(item)
        return ready_to_start, blocker_maybe_cleared

    def _status_counts(self) -> dict[ItemStatus, int]:
        counts = {status: 0 for status in ItemStatus}
        for item in self.plan.items:
            counts[item.status] += 1
        return counts

    def _render_dependency_chip(self, dependency_identifier: str) -> str:
        dependency = self.items_by_identifier.get(dependency_identifier)
        label = dependency.title if dependency else dependency_identifier
        short_label = dependency.identifier if dependency else dependency_identifier
        return f'<span class="chip" title="{escape_html(label)}">{escape_html(short_label)}</span>'

    def _render_pull_request_link(self, item: Item) -> str:
        if item.pr is None:
            return '<span class="muted">no PR yet</span>'
        item_repo = item.repo or self.plan.default_repo
        return f'<a class="pr-link" href="https://github.com/{item_repo}/pull/{item.pr}" target="_blank" rel="noopener">#{item.pr}</a>'

    def _render_item_card(
        self, item: Item, indent_level: int, wrap_parent_identifier: str | None
    ) -> str:
        live_class = f"live-{item.live_state.value}" if item.live_state else "live-none"
        drift_html = (
            f'<div class="drift">⚠ {escape_html(item.drift_description)}</div>'
            if item.drift_description
            else ""
        )
        session_html = ""
        if item.session:
            session_html = f'<a class="session-link" href="{escape_html(item.session)}" target="_blank" rel="noopener">session ↗</a>'
        dependencies_html = ""
        if item.depends_on:
            chips = " ".join(
                self._render_dependency_chip(dependency)
                for dependency in item.depends_on
            )
            dependencies_html = (
                f'<div class="deps"><span class="deps-label">needs</span> {chips}</div>'
            )
        blockers_html = ""
        if item.blockers:
            blockers_html = (
                '<div class="blockers">'
                + "".join(
                    f'<div class="blocker">▸ {escape_html(blocker)}</div>'
                    for blocker in item.blockers
                )
                + "</div>"
            )
        notes_html = (
            f'<div class="notes">{escape_html(item.notes).strip()}</div>'
            if item.notes
            else ""
        )
        wrap_html = ""
        if wrap_parent_identifier:
            parent = self.items_by_identifier.get(wrap_parent_identifier)
            parent_label = parent.title if parent else wrap_parent_identifier
            wrap_html = (
                f'<div class="wrap-arrow">◄ continues from <span class="mono">{escape_html(wrap_parent_identifier)}</span> '
                f'<span class="wrap-parent-title">({escape_html(parent_label)})</span></div>'
            )

        return f"""
    <article class="item status-{item.status.value} {'has-drift' if item.drift_description else ''}" style="margin-left: {indent_level * 1.75}rem;">
      {wrap_html}
      <div class="item-row">
        <div class="item-spine"></div>
        <div class="item-body">
          <div class="item-head">
            <h4 class="item-title">{escape_html(item.title)}</h4>
            <div class="item-badges">
              <span class="badge status-badge status-{item.status.value}">{item.status.display_label}</span>
              <span class="badge live-badge {live_class}">{live_state_display_label(item.live_state)}</span>
            </div>
          </div>
          <div class="item-meta">
            <span class="mono id">{escape_html(item.identifier)}</span>
            <span class="mono branch">{escape_html(item.branch)}</span>
            {self._render_pull_request_link(item)}
            {session_html}
          </div>
          {drift_html}
          {notes_html}
          {dependencies_html}
          {blockers_html}
        </div>
      </div>
    </article>"""

    def _render_track_stack(self, track_items: list[Item]) -> str:
        """Order a track's items into a dependency stack (same-track
        depends_on only), assign an indent level per item capped at
        :data:`MAXIMUM_DEPENDENCY_STACK_LEVEL`, wrapping back to level 0
        (with a left-edge arrow back to the real parent) past the cap."""
        identifiers_in_track = {item.identifier for item in track_items}
        children_by_parent: dict[str, list[Item]] = {}
        roots: list[Item] = []
        for item in track_items:
            same_track_dependencies = [
                dependency
                for dependency in item.depends_on
                if dependency in identifiers_in_track
            ]
            if same_track_dependencies:
                children_by_parent.setdefault(same_track_dependencies[0], []).append(
                    item
                )
            else:
                roots.append(item)

        rendered_cards: list[str] = []

        def walk(item: Item, level: int, wrap_parent_identifier: str | None) -> None:
            next_level = level + 1
            wrap_for_children = None
            if next_level > MAXIMUM_DEPENDENCY_STACK_LEVEL:
                next_level = 0
                wrap_for_children = item.identifier
            rendered_cards.append(
                self._render_item_card(item, level, wrap_parent_identifier)
            )
            for child in children_by_parent.get(item.identifier, []):
                walk(child, next_level, wrap_for_children)

        for root in roots:
            walk(root, 0, None)

        return "".join(rendered_cards)

    def _render_waves(self) -> str:
        tracks_by_wave: dict[str, list[Track]] = {}
        for track in self.plan.tracks:
            tracks_by_wave.setdefault(track.wave, []).append(track)

        items_by_track: dict[str, list[Item]] = {}
        for item in self.plan.items:
            items_by_track.setdefault(item.track, []).append(item)

        waves_html: list[str] = []
        for wave in self.plan.waves:
            tracks_html: list[str] = []
            for track in tracks_by_wave.get(wave.id, []):
                track_items = items_by_track.get(track.id, [])
                if not track_items:
                    tracks_html.append(f"""
            <section class="track">
              <h3 class="track-title">{escape_html(track.name)}</h3>
              <p class="track-empty">{escape_html(track.description or 'No tracked items.')}</p>
            </section>""")
                    continue
                items_html = self._render_track_stack(track_items)
                tracks_html.append(f"""
        <section class="track">
          <h3 class="track-title">{escape_html(track.name)}</h3>
          <div class="item-list">{items_html}</div>
        </section>""")
            waves_html.append(f"""
    <section class="wave" id="wave-{escape_html(wave.id)}">
      <div class="wave-eyebrow">{escape_html(wave.name)}</div>
      {''.join(tracks_html)}
    </section>""")
        return "".join(waves_html)

    def _render_summary_pills(self) -> str:
        counts = self._status_counts()
        return "".join(
            f'<div class="stat"><span class="stat-num">{counts[status]}</span><span class="stat-label">{status.display_label}</span></div>'
            for status in ItemStatus
        )

    @staticmethod
    def _render_next_steps(
        drift_items: list[Item],
        ready_to_start: list[Item],
        blocker_maybe_cleared: list[Item],
    ) -> str:
        sections: list[str] = []
        if drift_items:
            rows = "".join(
                f'<li><strong>{escape_html(item.title)}</strong><br><span class="next-reason">{escape_html(item.drift_description)}</span></li>'
                for item in drift_items
            )
            sections.append(
                f'<div class="next-group next-drift"><h4>Fix the manifest ({len(drift_items)})</h4><ul>{rows}</ul></div>'
            )
        if ready_to_start:
            rows = "".join(
                f'<li><strong>{escape_html(item.title)}</strong><br><span class="next-reason">all dependencies done — nothing structurally blocking it</span></li>'
                for item in ready_to_start
            )
            sections.append(
                f'<div class="next-group next-ready"><h4>Ready to start ({len(ready_to_start)})</h4><ul>{rows}</ul></div>'
            )
        if blocker_maybe_cleared:
            rows = "".join(
                f'<li><strong>{escape_html(item.title)}</strong><br><span class="next-reason">some (not all) dependencies are done — worth re-checking the blocker</span></li>'
                for item in blocker_maybe_cleared
            )
            sections.append(
                f'<div class="next-group next-recheck"><h4>Blocker may be cleared ({len(blocker_maybe_cleared)})</h4><ul>{rows}</ul></div>'
            )
        if not sections:
            sections.append(
                '<p class="next-empty">Nothing actionable right now — every item is either in progress, fully blocked, or done.</p>'
            )
        return "".join(sections)

    @staticmethod
    def _render_alert_banner(drift_items: list[Item]) -> str:
        if not drift_items:
            return '<div class="alert-banner clean-banner">No drift — every item\'s manual status agrees with live GitHub state.</div>'
        rows = "".join(
            f"<li>{escape_html(item.title)} — {escape_html(item.drift_description)}</li>"
            for item in drift_items
        )
        return f'<div class="alert-banner drift-banner"><strong>{len(drift_items)} drift flag(s)</strong><ul>{rows}</ul></div>'

    def _render_tracking_link(self) -> str:
        if not self.tracking_url:
            return ""
        return f' <a class="tracking-link" href="{escape_html(self.tracking_url)}" target="_blank" rel="noopener">Propose a structural change →</a>'


def _load_pull_requests_by_repository(
    pr_data_json: dict[str, Any],
) -> PullRequestsByRepository:
    return {
        repository: {
            pull_request_number: PullRequestRecord.from_mapping(record)
            for pull_request_number, record in pull_requests.items()
        }
        for repository, pull_requests in pr_data_json.items()
    }


def main() -> int:
    """Parse arguments, validate the manifest, render the dashboard, and
    print its summary. See the module docstring for the CLI contract."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--plan", required=True, help="Path to plan.yaml")
    parser.add_argument("--roadmap", required=True, help="Path to roadmap.md")
    parser.add_argument(
        "--pr-data",
        required=True,
        help='Path to a JSON file: {"owner/repo": {"pr_number": {...}}}',
    )
    parser.add_argument(
        "--output", required=True, help="Path to write the dashboard HTML to"
    )
    parser.add_argument(
        "--tracking-url",
        default=None,
        help="The plan's tracking_issue html_url, if it has one",
    )
    arguments = parser.parse_args()

    raw_plan = yaml.safe_load(Path(arguments.plan).read_text())
    roadmap_text = Path(arguments.roadmap).read_text()
    pr_data_json = json.loads(Path(arguments.pr_data).read_text())

    try:
        validate_plan(raw_plan)
    except PlanValidationError as error:
        print(f"plan.yaml failed validation: {error}", file=sys.stderr)
        return 1

    plan = Plan.from_mapping(raw_plan)
    pr_data = _load_pull_requests_by_repository(pr_data_json)
    renderer = DashboardRenderer(
        plan=plan,
        roadmap_text=roadmap_text,
        pr_data=pr_data,
        tracking_url=arguments.tracking_url,
    )
    output, summary = renderer.render()

    Path(arguments.output).write_text(output)
    print(json.dumps(summary.to_json_dict()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
