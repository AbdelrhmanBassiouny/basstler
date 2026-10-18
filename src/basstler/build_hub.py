"""
Render the plan hub: one card per registered repository, opening its own index.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from basstler.build_index import PlanSummary, ProgressCard
from basstler.class_property import classproperty
from basstler.render_common import PageTemplate, TemplatePage


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

    error: str | None = None
    """
    Why the repository's notes could not be read, if they could not.
    """

    @classmethod
    def over_plans(
        cls, name: str, index_url: str, plans: list[PlanSummary]
    ) -> RepositorySummary:
        """
        :param name: The repository, as ``owner/repo``.
        :param index_url: The repository's own index page.
        :param plans: The repository's plans.
        :return: The repository's card, counting every plan's items.
        """
        return cls(
            name=name,
            index_url=index_url,
            plans=plans,
            done=sum(plan.done for plan in plans),
            total=sum(plan.total for plan in plans),
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


@dataclass
class HubPage(TemplatePage):
    """
    The hub page: a card per registered repository.
    """

    repositories: list[RepositorySummary]
    """
    Every repository to list, in the order they should appear.
    """

    @classproperty
    def template(cls) -> PageTemplate:
        return PageTemplate.HUB

    def render(self) -> str:
        """
        :return: The rendered HTML page.
        """
        return self.render_template(repositories=self.repositories)
