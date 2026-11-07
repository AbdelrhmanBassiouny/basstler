"""
Render one plan's page on the plan site: its waves as columns of item cards, with the
next steps its live pull-request state calls for.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from basstler.class_property import classproperty
from basstler.locations import SiteTemplate
from basstler.plan.dependencies import DependencyResolver, PlanDirectory
from basstler.plan.model import ItemStatus
from basstler.maintenance.board import PullRequestField
from basstler.github_labels import GitHubLabel
from basstler.plan_site.cards import (
    DraftRecheckAttribute,
    LiveStateAttribute,
    ModelOption,
    PlanTimeAttribute,
    RefreshSource,
    TrackSection,
    WaveSection,
)
from basstler.plan_site.chip_tone import ChipTone
from basstler.plan_site.item_classifier import ItemClassifier
from basstler.plan_site.hub import PlanHistory
from basstler.plan_site.plan import Item, Plan
from basstler.plan_site.plan_overview import NextSteps, PlanOverview
from basstler.pull_request_state import (
    LiveState,
    PullRequestsByRepository,
    PullRequestState,
)
from basstler.render_common import (
    TemplatePage,
    render_markdown_to_html,
    sanitize_http_url,
)

# %% the rendered page


@dataclass
class RenderedPlanPage:
    """
    What rendering one plan's page produces.
    """

    html: str
    """
    The page.
    """

    overview: PlanOverview
    """
    The plan's state the page was rendered from.
    """


# %% the plan page


@dataclass(kw_only=True)
class PlanPage(TemplatePage):
    """
    A plan's page on the site: one column per wave, each item a card with its status,
    pull request, CI, assignee and dependency chips, plus the plan's next steps.

    In the browser, the page reads every pull request's state from GitHub, shows it
    live, and shows the items no draft holds back any longer as startable.
    """

    stylesheet_url: str
    """
    The address of the site's stylesheet.
    """

    plan: Plan
    """
    The plan being rendered.
    """

    roadmap_text: str
    """
    The plan's ``roadmap.md`` narrative content.
    """

    pull_requests_by_repository: PullRequestsByRepository
    """
    Live pull request state for every repository referenced by the plan's items.
    """

    tracking_url: str | None = None
    """
    The tracking issue's or pull request's ``html_url``, if the plan has one.
    """

    hub_url: str | None = None
    """
    The plan hub's URL, the first link of the page's breadcrumb.
    """

    index_url: str | None = None
    """
    The repository's own index page, the breadcrumb's second link.
    """

    plan_directory: PlanDirectory | None = None
    """
    The other plans this plan's ``depends_on`` entries may name, if any were loaded.
    """

    locate_plan_page: Callable[[str], str] | None = None
    """
    Where another plan's page is published, given its id, or ``None`` when plan pages
    have no known address.
    """

    history: PlanHistory | None = None
    """
    When the plan was created and last changed, ``None`` when its history is unknown.
    """

    built_at: datetime | None = None
    """
    When the site was built, which the page shows as its refresh time until the browser
    reads GitHub itself; ``None`` to leave it out.
    """

    dependencies: DependencyResolver = field(init=False)
    """
    The resolver every reader of the plan's ``depends_on`` entries goes through.
    """

    @classproperty
    def template(cls) -> str:
        return SiteTemplate.PLAN.name

    def __post_init__(self) -> None:
        self.dependencies = DependencyResolver(
            plan=self.plan, plan_directory=self.plan_directory
        )

    def render(self) -> RenderedPlanPage:
        """
        :return: The rendered page, and the plan's state it shows.
        """
        ItemClassifier(
            plan=self.plan,
            pull_requests_by_repository=self.pull_requests_by_repository,
            dependencies=self.dependencies,
            locate_plan_page=self.locate_plan_page,
        ).classify()
        next_steps = NextSteps.of_plan(self.plan, self.dependencies)
        overview = PlanOverview.of_plan(self.plan, next_steps)
        html = self.render_template(
            stylesheet_url=self.stylesheet_url,
            chip_tone=ChipTone,
            script_template=SiteTemplate.PLAN_SCRIPT.name,
            recheck_script_template=SiteTemplate.PLAN_PULL_REQUEST_RECHECK_SCRIPT.name,
            draft_recheck_attribute=DraftRecheckAttribute,
            live_state_attribute=LiveStateAttribute,
            plan_time_attribute=PlanTimeAttribute,
            refresh_source=RefreshSource,
            live_state=LiveState,
            chip_tones=[tone.value for tone in ChipTone],
            live_states={
                state.name: {
                    "label": state.display_label,
                    "tone": ChipTone.of_live_state(state).value,
                }
                for state in LiveState
            },
            merged_label=GitHubLabel.MERGED.value,
            done_status={
                "status": ItemStatus.DONE.value,
                "label": ItemStatus.DONE.value.capitalize(),
                "tone": ChipTone.of_status(ItemStatus.DONE).value,
                "css_class": Item.status_css_class(ItemStatus.DONE),
            },
            history=self.history,
            built_at=self.built_at,
            pull_request_field=PullRequestField,
            pull_request_state=PullRequestState,
            title=self.plan.title,
            description=self.plan.description,
            repository=self.plan.default_repository,
            repository_url=self.plan.repository_url,
            total_items=len(self.plan.items),
            tracking_url=self.tracking_url,
            hub_url=sanitize_http_url(self.hub_url),
            index_url=sanitize_http_url(self.index_url),
            item_statuses=list(ItemStatus),
            status_counts=overview.status_counts,
            drift_items=self.plan.drifted_items,
            ready_to_start=next_steps.ready_to_start,
            blocker_maybe_cleared=next_steps.blocker_maybe_cleared,
            ready_to_review=next_steps.ready_to_review,
            roadmap_html=render_markdown_to_html(self.roadmap_text),
            waves=self._wave_sections(),
            available_models=list(ModelOption),
        )
        return RenderedPlanPage(html=html, overview=overview)

    def _wave_sections(self) -> list[WaveSection]:
        """
        :return: One section per wave, each holding its tracks and their items.
        """
        items_by_track: dict[str, list[Item]] = {}
        for item in self.plan.items:
            items_by_track.setdefault(item.track, []).append(item)
        return [
            WaveSection(
                wave=wave,
                tracks=[
                    TrackSection.of_track(track, items_by_track.get(track.id, []))
                    for track in self.plan.tracks
                    if track.wave == wave.id
                ],
            )
            for wave in self.plan.waves
        ]
