"""
Render the plan site's hub and repository pages, the stylesheet every page links, and
the record of what a build left out.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from urllib.parse import urlencode

from basstler.class_property import classproperty
from basstler.locations import SiteTemplate
from basstler.maintenance.github import ListingParameter, PullRequestListState
from basstler.github.client import PageParameter
from basstler.plan.model import ItemStatus
from basstler.plan_site.plan import Item, ProgressStage
from basstler.plan_site.site_vocabulary import LiveStateVocabulary
from basstler.pull_request_state import LiveState
from basstler.render_common import ScriptData, TemplatePage
from basstler.repository import GitHubAddress

MAXIMUM_PULL_REQUESTS_PER_PAGE = 100
"""
The most pull requests one page of GitHub's pull request listing holds.
"""

# %% what a card's script reads


class ProgressCardAttribute(StrEnum):
    """
    The attributes that mark what a progress card's script recounts and rewrites.
    """

    COUNTED_ITEMS = "data-counted-items"
    """
    The :class:`CountedItem` entries a card counts.
    """

    PROGRESS = "data-progress-label"
    """
    The card's progress label.
    """

    STAGE_LABEL = "data-stage-label"
    """
    One stage's share label, naming the :class:`ProgressStage`.
    """

    STAGE_BAR = "data-stage-bar"
    """
    One stage's bar segment, naming the :class:`ProgressStage`.
    """

    LABEL_FORMAT = "data-label-format"
    """
    The label a count or share is written into, with a :class:`LabelPlaceholder`.
    """

    WIDTH_FORMAT = "data-width-format"
    """
    The CSS width a bar segment's share is written into, with a
    :class:`LabelPlaceholder`.
    """

    FINISHED = "data-live-progress-finished"
    """
    Set on the page once every card is recounted.
    """


class LabelPlaceholder(StrEnum):
    """
    The placeholders a label format holds for the numbers a card counts.
    """

    DONE = "{done}"
    """
    How many items are done.
    """

    PERCENTAGE = "{percentage}"
    """
    A stage's share of the items, as a percentage.
    """


@dataclass(frozen=True)
class CountedItem(ScriptData):
    """
    One item a card counts, as its script recounts it live.
    """

    status: ItemStatus
    """
    The item's status as built.
    """

    live_state: LiveState
    """
    The live state of the item's pull request as built.
    """

    listing_url: str | None
    """
    The first page of every pull request of the repository the item's pull request is
    in, or ``None`` without a pull request.
    """

    number: int | None
    """
    The item's pull request number, or ``None`` without a pull request.
    """

    @classmethod
    def of_item(cls, item: Item) -> CountedItem:
        """
        :param item: A classified item.
        :return: What a card counts of it.
        """
        reference = item.pull_request_reference
        if reference is None:
            return cls(
                status=item.status,
                live_state=item.live_state,
                listing_url=None,
                number=None,
            )
        query = urlencode(
            {
                ListingParameter.STATE: PullRequestListState.ALL.query,
                ListingParameter.PAGE_SIZE: MAXIMUM_PULL_REQUESTS_PER_PAGE,
            }
        )
        return cls(
            status=item.status,
            live_state=item.live_state,
            listing_url=(
                f"{GitHubAddress.API}/{reference.repository.pull_requests_path}?{query}"
            ),
            number=reference.number,
        )


# %% the cards a page lists


@dataclass(frozen=True)
class StageShare:
    """
    The share of a card's items that reached one :class:`ProgressStage`.
    """

    stage: ProgressStage
    """
    The stage measured.
    """

    percentage: float
    """
    The share of items that reached :attr:`stage`, from 0 to 100.
    """

    @classproperty
    def label_decimal_places(cls) -> int:
        """
        How many decimal places :attr:`label` writes the percentage with.
        """
        return 0

    @classproperty
    def width_decimal_places(cls) -> int:
        """
        How many decimal places :attr:`width` writes the percentage with.
        """
        return 1

    @property
    def label_format(self) -> str:
        """
        :attr:`label` with :attr:`LabelPlaceholder.PERCENTAGE` for the percentage.
        """
        return f"{LabelPlaceholder.PERCENTAGE}% {self.stage}"

    @property
    def label(self) -> str:
        """
        The share as text, such as ``40% started``.
        """
        return self.label_format.replace(
            LabelPlaceholder.PERCENTAGE,
            f"{self.percentage:.{self.label_decimal_places}f}",
        )

    @classproperty
    def width_format(cls) -> str:
        """
        :attr:`width` with :attr:`LabelPlaceholder.PERCENTAGE` for the percentage.
        """
        return f"{LabelPlaceholder.PERCENTAGE}%"

    @property
    def width(self) -> str:
        """
        The share as the CSS width of its bar segment.
        """
        return self.width_format.replace(
            LabelPlaceholder.PERCENTAGE,
            f"{self.percentage:.{self.width_decimal_places}f}",
        )


@dataclass(kw_only=True)
class ProgressCard(ABC):
    """
    One card on a site page: a heading, a progress label and a bar showing how many
    items are started, reviewed and done.

    The plan cards on a repository's index and the repository cards on the hub are drawn
    by the same markup, so what the bar and the card's class are worked out from is
    shared here.
    """

    done: int
    """
    How many items are done.
    """

    total: int
    """
    How many items there are.
    """

    started: int = 0
    """
    How many items have begun: see :attr:`Item.is_started`.
    """

    reviewed: int = 0
    """
    How many items' pull requests are past their author's review: see
    :attr:`Item.is_reviewed`.
    """

    counted_items: list[CountedItem] = field(default_factory=list)
    """
    The items the counts are taken over, which the page's script recounts live.
    """

    @staticmethod
    def counts_over(
        cards: Sequence[ProgressCard],
    ) -> dict[str, int | list[CountedItem]]:
        """
        :param cards: The cards a larger card stands for.
        :return: Every count and counted item a card carries, combined over *cards*, by
            field name - ready to pass to the larger card's constructor.
        """
        return {
            "done": sum(card.done for card in cards),
            "total": sum(card.total for card in cards),
            "started": sum(card.started for card in cards),
            "reviewed": sum(card.reviewed for card in cards),
            "counted_items": [item for card in cards for item in card.counted_items],
        }

    @classproperty
    def card_css_class(cls) -> str:
        """
        The CSS class every card carries.
        """
        return "plan-card"

    @classproperty
    def complete_css_class(cls) -> str:
        """
        The CSS class a card adds once every item is done.
        """
        return "complete"

    @classproperty
    def stage_label_separator(cls) -> str:
        """
        What separates the stage share labels.
        """
        return " · "

    @property
    @abstractmethod
    def progress_label_format(self) -> str:
        """
        :attr:`progress_label` with :attr:`LabelPlaceholder.DONE` for the done count.
        """

    @property
    def progress_label(self) -> str:
        """
        The human-readable progress shown on the card.
        """
        return self.progress_label_format.replace(LabelPlaceholder.DONE, str(self.done))

    @property
    def is_complete(self) -> bool:
        """
        Whether every item is done.
        """
        return self.total > 0 and self.done == self.total

    def percentage_of(self, count: int) -> float:
        """
        :param count: How many of the card's items to express as a share.
        :return: *count*'s share of :attr:`total`, from 0 to 100.
        """
        return (count / self.total * 100) if self.total else 0.0

    @property
    def stage_shares(self) -> list[StageShare]:
        """
        The share of items that reached each :class:`ProgressStage`, earliest stage
        first.
        """
        counts = {
            ProgressStage.STARTED: self.started,
            ProgressStage.REVIEWED: self.reviewed,
            ProgressStage.DONE: self.done,
        }
        return [
            StageShare(stage=stage, percentage=self.percentage_of(counts[stage]))
            for stage in ProgressStage
        ]

    @property
    def labelled_stage_shares(self) -> list[StageShare]:
        """
        The started and reviewed :attr:`stage_shares`, none when there are no items; the
        done share is left to :attr:`progress_label`.
        """
        if not self.total:
            return []
        return [
            share
            for share in self.stage_shares
            if share.stage is not ProgressStage.DONE
        ]

    @property
    def stage_shares_label(self) -> str | None:
        """
        The :attr:`labelled_stage_shares` as text, or ``None`` when there are none.
        """
        if not self.labelled_stage_shares:
            return None
        return self.stage_label_separator.join(
            share.label for share in self.labelled_stage_shares
        )

    @property
    def css_class(self) -> str:
        """
        The card's CSS class list: :attr:`card_css_class`, plus
        :attr:`complete_css_class` once every item is done.
        """
        if self.is_complete:
            return f"{self.card_css_class} {self.complete_css_class}"
        return self.card_css_class


@dataclass(kw_only=True)
class PlanSummary(ProgressCard):
    """
    One plan's card on its repository's index.
    """

    id: str
    """The plan's stable identifier: a short kebab-case slug (e.g.
    ``rdr-refactor``), not a UUID - it is chosen by whoever bootstraps the
    plan, doubles as its directory name, and is what a person types as the
    ``<plan-id>`` argument to ``/plan-create``, so it
    needs to stay human-readable and human-typable."""

    title: str
    """
    The plan's display title.
    """

    description: str
    """
    A one-line description shown under the title.
    """

    page_url: str | None = None
    """
    The address of the plan's page on the site, or ``None`` when it has none.
    """

    @property
    def progress_label_format(self) -> str:
        if not self.total:
            return "no items yet"
        return f"{LabelPlaceholder.DONE} / {self.total} done"


# %% the pages


@dataclass(frozen=True)
class SkippedPage:
    """
    A part of the site the build left out, and why.
    """

    site_path: str
    """
    Where it would have been published below the site's address: ``owner/repo`` for a
    repository, ``owner/repo/plan-id`` for a plan.
    """

    reason: str
    """
    Why it was left out.
    """


@dataclass(kw_only=True)
class RepositorySummary(ProgressCard):
    """
    One repository's card on the hub, counting the items of every one of its plans.
    """

    name: str
    """
    The repository, as ``owner/repo``.
    """

    index_url: str | None
    """
    The repository's own index page, or ``None`` when its notes could not be read.
    """

    plans: list[PlanSummary] = field(default_factory=list)
    """
    The repository's plans.
    """

    skipped_plans: list[SkippedPage] = field(default_factory=list)
    """
    The repository's plans the build left out.
    """

    error: str | None = None
    """
    Why the repository's notes could not be read, if they could not.
    """

    @classmethod
    def over_plans(
        cls,
        name: str,
        index_url: str,
        plans: list[PlanSummary],
        skipped_plans: list[SkippedPage],
    ) -> RepositorySummary:
        """
        :param name: The repository, as ``owner/repo``.
        :param index_url: The repository's own index page.
        :param plans: The repository's published plans.
        :param skipped_plans: The repository's plans the build left out.
        :return: The repository's card, counting every published plan's items.
        """
        return cls(
            name=name,
            index_url=index_url,
            plans=plans,
            skipped_plans=skipped_plans,
            **cls.counts_over(plans),
        )

    @classmethod
    def unreadable(cls, name: str, error: str) -> RepositorySummary:
        """
        :param name: The repository, as ``owner/repo``.
        :param error: Why its notes could not be read.
        :return: The repository's card, with no plans and no index to open.
        """
        return cls(name=name, index_url=None, error=error, done=0, total=0)

    @property
    def progress_label_format(self) -> str:
        return f"{len(self.plans)} plans · {LabelPlaceholder.DONE} / {self.total} items done"

    @property
    def skipped_pages(self) -> list[SkippedPage]:
        """
        Every part of this repository the build left out: its plans that failed
        validation, or the whole repository when its notes could not be read.
        """
        if self.error is None:
            return self.skipped_plans
        return [SkippedPage(site_path=self.name, reason=self.error)]


@dataclass(kw_only=True)
class SiteSummary(ProgressCard):
    """
    The whole site at a glance: every repository's card, counting all their items.
    """

    repositories: list[RepositorySummary]
    """
    Every repository on the site, in the hub file's order.
    """

    @classmethod
    def over_repositories(cls, repositories: list[RepositorySummary]) -> SiteSummary:
        """
        :param repositories: Every repository on the site.
        :return: The site's summary, counting every repository's items.
        """
        return cls(repositories=repositories, **cls.counts_over(repositories))

    @property
    def plan_count(self) -> int:
        """
        How many plans the site publishes, across every repository.
        """
        return sum(len(repository.plans) for repository in self.repositories)

    @property
    def skipped_pages(self) -> list[SkippedPage]:
        """
        Every plan and repository the build left out, in the hub file's order.
        """
        return [
            page
            for repository in self.repositories
            for page in repository.skipped_pages
        ]

    @property
    def progress_label_format(self) -> str:
        return (
            f"{len(self.repositories)} repositories · {self.plan_count} plans · "
            f"{LabelPlaceholder.DONE} / {self.total} items done"
        )


# %% the pages


@dataclass
class SiteStylesheet(TemplatePage):
    """
    The one stylesheet every page of the site links.
    """

    @classproperty
    def template(cls) -> str:
        return SiteTemplate.STYLESHEET.name

    def render(self) -> str:
        """
        :return: The stylesheet's text.
        """
        return self.render_template()


@dataclass(frozen=True)
class HubPageVocabulary(LiveStateVocabulary):
    """
    The names the hub's and repository indexes' templates and scripts share.
    """

    progress_card_attribute: type[ProgressCardAttribute] = field(
        default=ProgressCardAttribute, init=False
    )
    """
    The attributes that mark what the script recounts and rewrites.
    """

    label_placeholder: type[LabelPlaceholder] = field(
        default=LabelPlaceholder, init=False
    )
    """
    The placeholders the script writes counts into.
    """

    progress_stage: type[ProgressStage] = field(default=ProgressStage, init=False)
    """
    The stages a card counts.
    """

    progress_card: type[ProgressCard] = field(default=ProgressCard, init=False)
    """
    The class whose CSS classes a card carries.
    """

    stage_share: type[StageShare] = field(default=StageShare, init=False)
    """
    The class whose decimal places a share is written with.
    """

    counted_item: type[CountedItem] = field(default=CountedItem, init=False)
    """
    The class whose fields the script reads each counted item by.
    """

    page_parameter: type[PageParameter] = field(default=PageParameter, init=False)
    """
    The query parameter a listing's page is asked for by.
    """

    pull_requests_per_page: int = field(
        default=MAXIMUM_PULL_REQUESTS_PER_PAGE, init=False
    )
    """
    How many pull requests a full page of a listing holds.
    """


@dataclass
class LiveProgressPage(TemplatePage, ABC):
    """
    A site page whose progress cards its script recounts from GitHub's live pull
    request states.
    """

    def render_template(self, **context: Any) -> str:
        """
        :meth:`TemplatePage.render_template`, also passing the recounting scripts and
        the :class:`HubPageVocabulary` they are written with.
        """
        return super().render_template(
            vocabulary=HubPageVocabulary(),
            live_state_script_template=SiteTemplate.LIVE_STATE_SCRIPT.name,
            live_progress_script_template=SiteTemplate.LIVE_PROGRESS_SCRIPT.name,
            **context,
        )


@dataclass
class HubPage(LiveProgressPage):
    """
    The hub page: a card per registered repository.
    """

    site: SiteSummary
    """
    The whole site, whose repositories are listed in the order they should appear.
    """

    stylesheet_url: str
    """
    The address of the site's :class:`SiteStylesheet`.
    """

    @classproperty
    def template(cls) -> str:
        return SiteTemplate.HUB.name

    def render(self) -> str:
        """
        :return: The rendered HTML page.
        """
        return self.render_template(
            site=self.site,
            repositories=self.site.repositories,
            stylesheet_url=self.stylesheet_url,
        )


@dataclass
class RepositoryIndexPage(LiveProgressPage):
    """
    One repository's index on the site: a card per published plan, and a banner naming
    every plan the build left out.
    """

    repository: RepositorySummary
    """
    The repository whose plans the page lists.
    """

    hub_url: str
    """
    The hub's address, linked back up to.
    """

    stylesheet_url: str
    """
    The address of the site's :class:`SiteStylesheet`.
    """

    @classproperty
    def template(cls) -> str:
        return SiteTemplate.REPOSITORY_INDEX.name

    def render(self) -> str:
        """
        :return: The rendered HTML page.
        """
        return self.render_template(
            repository=self.repository,
            hub_url=self.hub_url,
            stylesheet_url=self.stylesheet_url,
        )
