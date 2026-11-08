"""
The steps of publishing that only the user can take, and the lines and browser steps that take them.
"""

from __future__ import annotations

import sys
import textwrap
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlencode

from basstler.plan_site import token_storage
from basstler.github.run_listing import ListedRun
from basstler.plan_site.site_repository import SiteRepository
from basstler.plan_site.workflows import (
    PlanSiteSecret,
)
from basstler.repository import GitHubAddress, Repository
from basstler.standard_streams import StandardStreamHandler
from basstler.github.pull_request import NewPullRequest
from basstler.github.client import (
    GitHubClient,
)
from basstler.upstream_reviews.rest_models import RestPullRequestSummary

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""

# %% what is left to the user


class UserStep(StrEnum):
    """
    The steps of publishing that only the user can take.
    """

    CREATE_SITE_REPOSITORY = "create the site repository"
    """
    The site repository does not exist, or cannot be reached.
    """

    TURN_ON_PAGES = "turn on GitHub Pages for the site repository"
    """
    No build in the site repository has succeeded yet.
    """

    CREATE_TOKEN = "create, or regenerate, the token that starts the build"
    """
    No dispatch from the notes branch has succeeded yet, so the token it needs may not
    exist.
    """

    STORE_TOKEN = "store the token as a secret in every notes repository"
    """
    No dispatch from the notes branch has succeeded yet. Actions secrets belong to one
    repository, so each repository the site publishes needs its own copy.
    """

    ADD_MERGE_WORKFLOW = "merge the workflow that starts the build on every merge"
    """
    The merge workflow waits on a branch of its own until its pull request merges into the
    notes repository's default branch.
    """


@dataclass(frozen=True)
class PendingStep:
    """
    One step left to the user, with the command line and the browser steps that take it.
    """

    step: UserStep
    """
    The step.
    """

    line: str | None
    """
    The one copyable line that takes it, ``None`` when GitHub offers no command for it.
    """

    browser_steps: tuple[str, ...]
    """
    The same step taken on github.com, one click or entry each, in order.
    """

    latest_run: ListedRun | None = None
    """
    The latest run of the workflow whose failure to succeed makes the step necessary,
    ``None`` when it has not run.
    """

    failure: str | None = None
    """
    Why publishing could not take the step itself, ``None`` when it does not try.
    """

    def render(self) -> str:
        """:return: The step as it is printed."""
        numbered = "\n".join(
            f"    {number}. {text}"
            for number, text in enumerate(self.browser_steps, start=1)
        )
        lines = [f"- {self.step}:"]
        if self.failure:
            lines.append(
                textwrap.indent(
                    f"Could not be done automatically: {self.failure}", "    "
                )
            )
        if self.latest_run is not None:
            lines.append(
                f"  Latest run, {self.latest_run.outcome}: {self.latest_run.page_url}"
            )
        if self.line is None:
            lines.append("  GitHub offers no command for this; in the browser:")
        else:
            lines.extend([f"    {self.line}", "  Or in the browser:"])
        lines.append(numbered)
        return "\n".join(lines)


@dataclass(frozen=True)
class UserSteps:
    """
    The command line and the browser steps for each step left to the user.
    """

    notes_repository: Repository
    """
    The repository whose notes branch starts the build.
    """

    site: SiteRepository
    """
    The site repository.
    """

    registered: Sequence[str]
    """
    Every ``owner/name`` the site publishes, which the token has to read.
    """

    def pending(
        self, step: UserStep, latest_run: ListedRun | None = None
    ) -> PendingStep:
        """
        :param step: The step.
        :param latest_run: The latest run of the workflow that makes the step
            necessary, ``None`` when it has not run.
        :return: The step with its line and its browser steps.
        """
        site = self.site.repository
        steps = {
            UserStep.CREATE_SITE_REPOSITORY: PendingStep(
                step,
                f"gh repo create {site.full_name} --public",
                (
                    f"Open {GitHubAddress.WEB}/new.",
                    f"Set the owner to {site.owner} and the repository name to "
                    f"{site.name}.",
                    "Choose Public, then click Create repository.",
                ),
            ),
            UserStep.TURN_ON_PAGES: PendingStep(
                step,
                f"gh api -X POST {site.api_path}/pages -f build_type=workflow",
                (
                    f"Open {site.url}/settings/pages.",
                    "Under Build and deployment, set Source to GitHub Actions.",
                ),
                latest_run,
            ),
            UserStep.CREATE_TOKEN: PendingStep(
                step,
                None,
                (
                    f"Open {self.site.token_form_url()} - its name, owner "
                    "and Actions write access are filled in. To reuse the token you "
                    "already have for the plan site, open it instead and click "
                    "Regenerate token.",
                    "Under Repository access, choose Only select repositories and "
                    f"select {site.full_name} alone.",
                    "Click Generate token and copy the token now; GitHub shows it "
                    "once.",
                ),
                latest_run,
            ),
            UserStep.STORE_TOKEN: PendingStep(
                step,
                f"{sys.executable} -m {token_storage.__name__}",
                tuple(
                    f"Open {GitHubAddress.WEB}/{repository}/settings/secrets/actions/new, "
                    f"set the name to {PlanSiteSecret.TOKEN}, paste the token as the "
                    "secret, then click Add secret."
                    for repository in self.registered
                ),
                latest_run,
            ),
        }
        return steps[step]


@dataclass(frozen=True)
class MergeWorkflowProposal:
    """
    The merge workflow waiting on a branch of its own, for the user to merge into the
    notes repository's default branch.
    """

    repository: Repository
    """
    The notes repository.
    """

    base: str
    """
    Its default branch, which refused the workflow.
    """

    head: str
    """
    The branch holding the workflow.
    """

    title: str = "Start the plan site build on every merge"
    """
    The title of the pull request proposing it.
    """

    @property
    def opening(self) -> NewPullRequest:
        """:return: The pull request proposing the workflow, opened ready to merge."""
        return NewPullRequest(
            self.repository, self.title, self.head, self.base, draft=False
        )

    @property
    def open_pull_requests_path(self) -> str:
        """:return: The listing of the open pull requests from :attr:`head` into
        :attr:`base`."""
        query = urlencode(
            {
                "head": f"{self.repository.owner}:{self.head}",
                "base": self.base,
                "state": "open",
            },
            safe=":",
        )
        return f"{self.repository.pull_requests_path}?{query}"

    def pending(self, github: GitHubClient) -> PendingStep:
        """
        :param github: What reads and opens pull requests.
        :return: The step merging the pull request proposing the workflow, opened unless
            one already is, or, when it cannot be opened, the step opening and
            merging it, with why it could not be opened.
        """
        listed = github.get(self.open_pull_requests_path)
        if listed:
            return self.merging(RestPullRequestSummary.from_json(listed[0]))
        opened = github.attempt_send(self.opening)
        if opened.failure is not None:
            return PendingStep(
                UserStep.ADD_MERGE_WORKFLOW,
                f"gh pr create --repo {self.repository.full_name} --base {self.base} "
                f"--head {self.head} --fill, then merge it",
                (
                    f"Open {self.repository.url}/compare/{self.base}...{self.head}"
                    "?expand=1.",
                    "Click Create pull request.",
                    "Merge the pull request.",
                ),
                failure=str(opened.failure),
            )
        return self.merging(RestPullRequestSummary.from_json(opened.body))

    @staticmethod
    def merging(pull_request: RestPullRequestSummary) -> PendingStep:
        """
        :param pull_request: The pull request proposing the workflow.
        :return: The step that merges it.
        """
        return PendingStep(
            UserStep.ADD_MERGE_WORKFLOW,
            f"gh pr merge {pull_request.page_url} --merge",
            (f"Open {pull_request.page_url}.", "Click Merge pull request."),
        )
