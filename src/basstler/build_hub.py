#!/usr/bin/env python3
"""
Render the plan hub: one card per registered repository, opening its own index.

Usage:
    python3 build_hub.py --repositories /tmp/repositories.json --output /tmp/hub.html

repositories.json is what ``python -m basstler.plan_hub gather`` writes: a JSON list of
``{"repository": ..., "index_url": ..., "plans": [<build_index.py plan summary>, ...]}``,
with an ``error`` on a repository whose notes could not be read.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from basstler.build_index import PlanSummary
from basstler.render_common import create_template_environment, sanitize_http_url


@dataclass
class RepositorySummary:
    """
    One repository's section of the hub.
    """

    name: str
    """
    The repository, as ``owner/repo``.
    """

    index_url: str | None
    """
    The repository's own index page, or ``None`` if it was never published.
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
    def from_mapping(cls, data: dict[str, Any]) -> RepositorySummary:
        """
        Build a summary from one entry of ``repositories.json``.
        """
        return cls(
            name=data["repository"],
            index_url=sanitize_http_url(data.get("index_url")),
            plans=[PlanSummary.from_mapping(plan) for plan in data.get("plans", [])],
            error=data.get("error"),
        )

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


def main() -> int:
    """
    Parse arguments, render the hub page, and write it out.
    """
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--repositories", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()

    repositories = [
        RepositorySummary.from_mapping(entry)
        for entry in json.loads(arguments.repositories.read_text())
    ]
    arguments.output.write_text(render_hub_page(repositories))
    return 0


if __name__ == "__main__":
    sys.exit(main())
