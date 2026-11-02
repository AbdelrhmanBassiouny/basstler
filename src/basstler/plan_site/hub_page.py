"""
Render the plan site's hub and repository pages, the stylesheet every page links, and
the record of what a build left out.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from basstler.dashboard.index_page import PlanSummary, ProgressCard
from basstler.class_property import classproperty
from basstler.locations import SiteTemplate
from basstler.render_common import TemplatePage


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
