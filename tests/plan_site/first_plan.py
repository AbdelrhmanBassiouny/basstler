"""
The dataset's first plan and the pull requests its items name, which the site's tests
look up.
"""

from __future__ import annotations

from basstler.plan_site.__main__ import PlanSource
from basstler.plan_site.plan import Plan
from basstler.repository import PullRequestReference, Repository

from ..constants.site import SitePlan

# %% the first plan and its pull requests

FIRST_PLAN = Plan.from_mapping(
    PlanSource.from_directory(SitePlan.FIRST.directory).manifest
)
"""
The dataset's first plan, whose items' pull requests and tracking issue the tests look
up.
"""

PLAN_REPOSITORY = Repository.parse(FIRST_PLAN.default_repository)
"""
The repository the first plan's items are opened on unless they name another.
"""

MERGED_PULL_REQUEST, OPEN_PULL_REQUEST, ELSEWHERE_PULL_REQUEST = (
    PullRequestReference(
        Repository.parse(item.repository or FIRST_PLAN.default_repository),
        item.pull_request_number,
    )
    for item in FIRST_PLAN.items
)
"""
The first plan's pull requests, in item order: a merged one, an open one, and one on a
repository other than the plan's default.
"""
