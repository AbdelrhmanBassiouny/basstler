"""
Render one plan's page on the plan site: its waves as columns of item cards, with the
next steps its live pull-request state calls for.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from basstler.class_property import classproperty
from basstler.locations import SiteTemplate
from basstler.plan.dependencies import DependencyResolver, PlanDirectory
from basstler.plan.model import ItemStatus
from basstler.plan_site.cards import ModelOption, TrackSection, WaveSection
from basstler.plan_site.chip_tone import ChipTone
from basstler.plan_site.item_classifier import ItemClassifier
from basstler.plan_site.plan import Item, Plan
from basstler.plan_site.plan_overview import NextSteps, PlanOverview
from basstler.pull_request_state import PullRequestsByRepository
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
