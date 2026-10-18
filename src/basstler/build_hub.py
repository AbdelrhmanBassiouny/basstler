"""
Render the plan hub: one card per registered repository, opening its own index.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from basstler.build_index import PlanSummary
from basstler.render_common import create_template_environment


@dataclass
class RepositorySummary:
    """
    One repository's card on the hub.
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

    @property
    def done(self) -> int:
        """
        How many items are done, across every plan.
        """
        return sum(plan.done for plan in self.plans)

    @property
    def total(self) -> int:
        """
        How many items there are, across every plan.
        """
        return sum(plan.total for plan in self.plans)

    @property
    def progress_label(self) -> str:
        """
        How many plans the repository has, and how many of their items are done.
        """
        return f"{len(self.plans)} plans · {self.done} / {self.total} items done"

    @property
    def completion_percentage_label(self) -> str:
        """
        The share of items done, ready for the progress bar's ``width`` style.
        """
        share = self.done / self.total * 100 if self.total else 0.0
        return f"{share:.1f}%"

    @property
    def css_class(self) -> str:
        """
        The repository card's CSS class list.
        """
        return "plan-card"


def render_hub_page(repositories: list[RepositorySummary]) -> str:
    """
    :param repositories: Every repository to list, in the order they should appear.
    :return: The rendered HTML page.
    """
    template = create_template_environment().get_template("hub.html")
    return template.render(repositories=repositories)
