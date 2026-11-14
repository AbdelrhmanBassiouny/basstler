"""
Render one plan's page on the plan site: its waves as columns of item cards, with the
next steps its live pull-request state calls for.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from basstler.class_property import classproperty
from basstler.github.pull_request_state import LivePullRequests
from basstler.locations import SiteTemplate
from basstler.plan.dependencies import DependencyResolver, PlanDirectory
from basstler.plan.model import ItemStatus
from basstler.plan.repository_rules import RepositoryRules
from basstler.plan_site.cards import ItemCard, ModelOption, TrackSection, WaveSection
from basstler.plan_site.item_classifier import ItemClassifier
from basstler.plan.structure import Item, Plan
from basstler.plan_site.plan_overview import NextSteps, PlanOverview
from basstler.plan_site.plan_page_header import PlanPageHeader
from basstler.plan_site.plan_page_vocabulary import PlanPageVocabulary
from basstler.render_common import TemplatePage, render_markdown_to_html

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

    cards_by_identifier: Mapping[str, ItemCard]
    """
    The card the page shows for each item, by item id.
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

    live_pull_requests: LivePullRequests
    """
    What was read of every repository referenced by the plan's items.
    """

    repository_rules: RepositoryRules = field(default_factory=RepositoryRules)
    """
    The rules every plan of the repository follows.
    """

    header: PlanPageHeader = field(default_factory=PlanPageHeader)
    """
    The links and dates the top of the page shows.
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
        cards_by_identifier = ItemClassifier(
            plan=self.plan,
            live_pull_requests=self.live_pull_requests,
            dependencies=self.dependencies,
            locate_plan_page=self.locate_plan_page,
        ).classify()
        next_steps = NextSteps.of_plan(self.plan, self.dependencies)
        overview = PlanOverview.of_plan(self.plan, next_steps)
        html = self.render_template(
            stylesheet_url=self.stylesheet_url,
            script_template=SiteTemplate.PLAN_SCRIPT.name,
            live_state_script_template=SiteTemplate.LIVE_STATE_SCRIPT.name,
            recheck_script_template=SiteTemplate.PLAN_PULL_REQUEST_RECHECK_SCRIPT.name,
            vocabulary=PlanPageVocabulary(),
            plan=self.plan,
            header=self.header,
            item_statuses=list(ItemStatus),
            status_counts=overview.status_counts,
            drift_items=self.plan.drifted_items,
            ready_to_start=next_steps.ready_to_start,
            blocker_maybe_cleared=next_steps.blocker_maybe_cleared,
            ready_to_review=next_steps.ready_to_review,
            roadmap_html=render_markdown_to_html(self.roadmap_text),
            repository_rules=self.repository_rules.rules,
            waves=self._wave_sections(),
            cards_by_identifier=cards_by_identifier,
            available_models=list(ModelOption),
        )
        return RenderedPlanPage(
            html=html, overview=overview, cards_by_identifier=cards_by_identifier
        )

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
