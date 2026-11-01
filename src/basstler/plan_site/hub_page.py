"""
Render the plan site's hub and repository pages, the stylesheet every page links, and
the record of what a build left out.
"""

from __future__ import annotations

import dataclasses
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field

from basstler.class_property import classproperty
from basstler.locations import SiteTemplate
from basstler.render_common import TemplatePage


# %% the cards a page lists


@dataclass(kw_only=True)
class ProgressCard(ABC):
    """
    One card on a site page: a heading, a progress label and a bar showing how many
    items are done.

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

    open_pull_requests: int = 0
    """
    How many of the items' pull requests are open.
    """

    reviewed_pull_requests: int = 0
    """
    How many of those open pull requests are out of draft: their author has reviewed
    them and marked them ready for review.
    """

    @staticmethod
    def counts_over(cards: Sequence[ProgressCard]) -> dict[str, int]:
        """
        :param cards: The cards a larger card stands for.
        :return: Every count a card carries, summed over *cards*, by field name - ready
            to pass to the larger card's constructor.
        """
        return {
            count.name: sum(getattr(card, count.name) for card in cards)
            for count in dataclasses.fields(ProgressCard)
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

    @property
    @abstractmethod
    def progress_label(self) -> str:
        """
        The human-readable progress shown on the card.
        """

    @property
    def is_complete(self) -> bool:
        """
        Whether every item is done.
        """
        return self.total > 0 and self.done == self.total

    @property
    def completion_percentage(self) -> float:
        """
        The share of items done, from 0 to 100.
        """
        return (self.done / self.total * 100) if self.total else 0.0

    @property
    def completion_percentage_label(self) -> str:
        """
        :attr:`completion_percentage`, formatted to one decimal place with a
        trailing ``%`` - ready to drop straight into the progress bar's
        ``width`` style without the template doing any formatting itself.
        """
        return f"{self.completion_percentage:.1f}%"

    @property
    def review_label(self) -> str | None:
        """
        How many open pull requests are out of draft, or ``None`` when none are open.
        """
        if not self.open_pull_requests:
            return None
        return (
            f"{self.reviewed_pull_requests} / {self.open_pull_requests} open pull "
            f"requests reviewed"
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
    ``<plan-id>`` argument to ``/plan-dashboard``/``/plan-create``, so it
    needs to stay human-readable and human-typable."""

    title: str
    """
    The plan's display title.
    """

    description: str
    """
    A one-line description shown under the title.
    """

    dashboard_url: str | None = None
    """
    The address of the plan's page on the site, or ``None`` when it has none.
    """

    @property
    def progress_label(self) -> str:
        return f"{self.done} / {self.total} done" if self.total else "no items yet"


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
        :return: The repository's card, counting every published plan's items and pull
            requests.
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
    def progress_label(self) -> str:
        """
        How many plans the repository has, and how many of their items are done.
        """
        return f"{len(self.plans)} plans · {self.done} / {self.total} items done"

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
        :return: The site's summary, counting every repository's items and pull
            requests.
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
    def progress_label(self) -> str:
        """
        How many repositories and plans the site has, and how many items are done.
        """
        return (
            f"{len(self.repositories)} repositories · {self.plan_count} plans · "
            f"{self.done} / {self.total} items done"
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


@dataclass
class HubPage(TemplatePage):
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
class RepositoryIndexPage(TemplatePage):
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
