#!/usr/bin/env python3
"""
Build the plan site: the hub, each repository's plans, and each plan's dashboard.

Reads the hub file, fetches every repository it lists, and renders that repository's
plans with the live state of every pull request they reference. Nothing here needs a
Claude session or belongs to an account, so the site is the same for everyone:

    <site>/                          the hub, one card per repository
    <site>/<owner>/<repo>/           that repository's plans
    <site>/<owner>/<repo>/<plan>/    a plan's dashboard

Usage:
    python3 -m basstler.build_site --registry <owner/repo> --output _site \\
        [--site-url <url>] [--remote-url-template <template>]

The hub file is read off the registry's notes branch. A plan whose manifest fails
validation, or a repository whose notes cannot be fetched, is reported and left out;
everything else is still published.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from http import HTTPStatus
from pathlib import Path
from typing import Any

import yaml

from basstler.build_dashboard import (
    DashboardRenderer,
    Plan,
    PlanValidationError,
    PullRequestRecord,
    PullRequestsByRepository,
    validate_plan,
)
from basstler.build_hub import RepositorySummary, render_hub_page
from basstler.build_index import PlanSummary, render_index_page
from basstler.environment import GitHubCredentialVariable
from basstler.maintenance_github import (
    GitHubCredentialUnavailableError,
    GitHubRepository,
    GitHubRequestFailed,
)
from basstler.plan_hub import HubDefault, NotesBranch, PlanHub
from basstler.plan_model import ItemStatus
from basstler.repository import Repository
from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""


class SiteFile(StrEnum):
    """
    The file and directory names the site and its source are laid out with.
    """

    PAGE = "index.html"
    """
    The page a directory serves, for the hub, every index and every plan alike.
    """

    NO_JEKYLL = ".nojekyll"
    """
    The marker that stops GitHub Pages from running Jekyll over already-rendered HTML.
    """

    MANIFEST = "plan.yaml"
    """
    A plan's manifest on the notes branch.
    """

    ROADMAP = "roadmap.md"
    """
    A plan's narrative on the notes branch.
    """


# %% a plan as the notes branch stores it


@dataclass
class PlanSource:
    """
    One plan's manifest and roadmap, as read from its directory on the notes branch.
    """

    directory_name: str
    """
    The plan's directory name, which is also the path its page is published under.
    """

    manifest: dict[str, Any]
    """
    The parsed ``plan.yaml``, not yet validated.
    """

    roadmap_text: str
    """
    The plan's ``roadmap.md``, or an empty string if it has none.
    """

    @classmethod
    def from_directory(cls, directory: Path) -> PlanSource:
        """
        Read one plan's directory.

        :param directory: The directory holding the plan's manifest.
        :return: The plan's source.
        """
        roadmap = directory / SiteFile.ROADMAP
        return cls(
            directory_name=directory.name,
            manifest=yaml.safe_load((directory / SiteFile.MANIFEST).read_text()),
            roadmap_text=roadmap.read_text() if roadmap.exists() else "",
        )

    @classmethod
    def every_plan_in(cls, plans_directory: Path) -> list[PlanSource]:
        """
        Read every plan under a ``plans`` directory, in directory-name order.

        :param plans_directory: The directory holding one subdirectory per plan.
        :return: Each subdirectory that carries a manifest.
        """
        return [
            cls.from_directory(manifest.parent)
            for manifest in sorted(plans_directory.glob(f"*/{SiteFile.MANIFEST}"))
        ]


# %% live pull request state


@dataclass(frozen=True)
class PullRequestReference:
    """
    One pull request a plan item names.
    """

    repository: str
    """
    The ``owner/repo`` the pull request is opened on.
    """

    number: int
    """
    The pull request's number.
    """


class PullRequestSource(ABC):
    """
    Where the live state of the pull requests a site shows comes from.
    """

    @abstractmethod
    def pull_request(self, reference: PullRequestReference) -> PullRequestRecord | None:
        """
        :param reference: The pull request to look up.
        :return: Its live state, or ``None`` if the repository has no such pull request.
        """

    @abstractmethod
    def issue_url(self, repository: str, number: int) -> str | None:
        """
        :param repository: The ``owner/repo`` the issue or pull request is opened on.
        :param number: Its number.
        :return: Its web page, or ``None`` if the repository has no such number.
        """


def pull_request_record_from_api(api_record: Mapping[str, Any]) -> PullRequestRecord:
    """
    Read the fields a dashboard classifies by out of one REST pull request object.

    :param api_record: The pull request, as the pulls API describes it.
    :return: The record a dashboard renders from.
    """
    return PullRequestRecord.from_mapping(
        {
            "state": api_record["state"],
            "draft": api_record["draft"],
            "merged_at": api_record["merged_at"],
            "labels": [label["name"] for label in api_record["labels"]],
        }
    )


@dataclass
class GitHubPullRequestSource(PullRequestSource):
    """
    Pull request state read from the GitHub REST API, once per repository.

    A repository's pull requests are listed in bulk on first use and kept, so a site
    covering many plans costs a handful of requests rather than one per item. A number
    the listing missed is read on its own.
    """

    token: str
    """
    The credential the requests authenticate with.
    """

    listed_pull_requests: dict[str, dict[int, PullRequestRecord]] = field(
        default_factory=dict
    )
    """
    Every repository listed so far, mapped to its pull requests by number.
    """

    def client_for(self, repository: str) -> GitHubRepository:
        """
        :param repository: The ``owner/repo`` to call.
        :return: A client for it.
        """
        return GitHubRepository(Repository.parse(repository), self.token)

    def pull_request(self, reference: PullRequestReference) -> PullRequestRecord | None:
        listed = self.pull_requests_of(reference.repository)
        if reference.number in listed:
            return listed[reference.number]
        api_record = self.read_if_present(
            lambda client: client.pull_request(reference.number), reference.repository
        )
        return None if api_record is None else pull_request_record_from_api(api_record)

    def issue_url(self, repository: str, number: int) -> str | None:
        api_record = self.read_if_present(
            lambda client: client.issue(number), repository
        )
        return None if api_record is None else str(api_record["html_url"])

    def pull_requests_of(self, repository: str) -> dict[int, PullRequestRecord]:
        """
        :param repository: The ``owner/repo`` to list.
        :return: Every pull request on it, by number, listed on first use.
        """
        if repository not in self.listed_pull_requests:
            self.listed_pull_requests[repository] = {
                api_record["number"]: pull_request_record_from_api(api_record)
                for api_record in self.client_for(repository).all_pull_requests()
            }
        return self.listed_pull_requests[repository]

    def read_if_present(
        self,
        read: Callable[[GitHubRepository], Mapping[str, Any]],
        repository: str,
    ) -> Mapping[str, Any] | None:
        """
        Make one read, treating an absent number as an answer rather than a failure.

        :param read: The call to make, given the repository's client.
        :param repository: The ``owner/repo`` to call.
        :return: The response, or ``None`` if the API answered that it does not exist.
        :raises GitHubRequestFailed: If the API refused the read for any other reason.
        """
        try:
            return read(self.client_for(repository))
        except GitHubRequestFailed as refused:
            if refused.status != HTTPStatus.NOT_FOUND:
                raise
            return None


# %% the site


@dataclass
class PublishedPlan:
    """
    One plan rendered to its page, with the entry the index lists it under.
    """

    page: str
    """
    The plan's rendered dashboard.
    """

    summary: PlanSummary
    """
    The plan's entry in the index.
    """


@dataclass
class PlanSite:
    """
    One repository's plans: their dashboards plus the index linking them.
    """

    repository: str
    """
    The ``owner/repo`` whose notes the plans come from.
    """

    plans_directory: Path
    """
    That repository's ``plans`` directory, holding one subdirectory per plan.
    """

    site_url: str
    """
    The address the whole site is served from, which every link is built on.
    """

    pull_request_source: PullRequestSource
    """
    Where the live pull request state comes from.
    """

    @property
    def hub_url(self) -> str:
        """
        The hub's address, which every page links back up to.
        """
        return f"{self.site_url.rstrip('/')}/"

    @property
    def index_url(self) -> str:
        """
        The address this repository's index is served from.
        """
        return f"{self.hub_url}{self.repository}/"

    def plan_url(self, directory_name: str) -> str:
        """
        :param directory_name: The plan's directory name.
        :return: The address its page is served from.
        """
        return f"{self.index_url}{directory_name}/"

    def build(self, output: Path) -> RepositorySummary:
        """
        Render this repository's index and plans into the site.

        :param output: The site's root directory.
        :return: The repository's card on the hub.
        """
        published = {
            source.directory_name: self.publish(source)
            for source in PlanSource.every_plan_in(self.plans_directory)
            if self.is_publishable(source)
        }
        repository_directory = output / self.repository
        for directory_name, plan in published.items():
            page = repository_directory / directory_name / SiteFile.PAGE
            page.parent.mkdir(parents=True, exist_ok=True)
            page.write_text(plan.page)

        summaries = [plan.summary for plan in published.values()]
        repository_directory.mkdir(parents=True, exist_ok=True)
        (repository_directory / SiteFile.PAGE).write_text(
            render_index_page(summaries, self.repository, self.hub_url)
        )
        return RepositorySummary(self.repository, self.index_url, summaries)

    @staticmethod
    def is_publishable(source: PlanSource) -> bool:
        """
        :param source: The plan to check.
        :return: Whether its manifest passes validation, logging why if it does not.
        """
        try:
            validate_plan(source.manifest)
        except PlanValidationError as error:
            logger.warning(f"{source.directory_name} is not published: {error}")
            return False
        return True

    def publish(self, source: PlanSource) -> PublishedPlan:
        """
        Render one valid plan.

        :param source: The plan to render.
        :return: Its page and its index entry.
        """
        plan = Plan.from_mapping(source.manifest)
        renderer = DashboardRenderer(
            plan=plan,
            roadmap_text=source.roadmap_text,
            pull_requests_by_repository=self.pull_requests_of(plan),
            tracking_url=self.tracking_url_of(plan),
            hub_url=self.hub_url,
            index_url=self.index_url,
        )
        page, dashboard_summary = renderer.render()
        summary = PlanSummary(
            id=plan.id,
            title=plan.title,
            description=plan.description,
            done=dashboard_summary.status_counts.get(ItemStatus.DONE, 0),
            total=len(plan.items),
            dashboard_url=self.plan_url(source.directory_name),
        )
        return PublishedPlan(page=page, summary=summary)

    def pull_requests_of(self, plan: Plan) -> PullRequestsByRepository:
        """
        :param plan: The plan whose items to look up.
        :return: The live state of every pull request its items name, in the shape the
            dashboard renders from; a number the repository does not have is left out.
        """
        pull_requests: PullRequestsByRepository = {}
        for item in plan.items:
            if item.pull_request_number is None:
                continue
            reference = PullRequestReference(
                repository=item.repository or plan.default_repository,
                number=item.pull_request_number,
            )
            record = self.pull_request_source.pull_request(reference)
            if record is not None:
                pull_requests.setdefault(reference.repository, {})[
                    str(reference.number)
                ] = record
        return pull_requests

    def tracking_url_of(self, plan: Plan) -> str | None:
        """
        :param plan: The plan whose tracking issue to link.
        :return: The tracking issue's page, or ``None`` if the plan has none.
        """
        if plan.tracking_issue is None:
            return None
        return self.pull_request_source.issue_url(
            plan.default_repository, plan.tracking_issue
        )


@dataclass
class HubSite:
    """
    The whole site: the hub page over every repository the hub file lists.
    """

    hub: PlanHub
    """
    The hub file, naming the repositories to publish.
    """

    site_url: str
    """
    The address the site is served from.
    """

    pull_request_source: PullRequestSource
    """
    Where the live pull request state comes from.
    """

    remote_url_template: str = HubDefault.REMOTE_URL_TEMPLATE.value
    """
    How a listed repository's name becomes a URL git can fetch.
    """

    def build(self, output: Path) -> list[RepositorySummary]:
        """
        Render every repository, then the hub linking them.

        :param output: The directory to write the site into.
        :return: Every repository's card, in the hub file's order.
        """
        output.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as scratch:
            repositories = [
                self.build_repository(repository, Path(scratch) / str(position), output)
                for position, repository in enumerate(self.hub.repositories)
            ]
        (output / SiteFile.PAGE).write_text(render_hub_page(repositories))
        (output / SiteFile.NO_JEKYLL).touch()
        return repositories

    def build_repository(
        self, repository: str, scratch: Path, output: Path
    ) -> RepositorySummary:
        """
        :param repository: The ``owner/repo`` to publish.
        :param scratch: A directory of its own to fetch the notes into.
        :param output: The site's root directory.
        :return: The repository's card, with an error when its notes cannot be read.
        """
        notes = NotesBranch.fetch(
            repository,
            self.hub.notes_branch,
            self.remote_url_template,
            scratch / "notes.git",
        )
        if notes is None:
            return RepositorySummary(
                repository, None, error=f"cannot fetch {self.hub.notes_branch}"
            )
        site = PlanSite(
            repository=repository,
            plans_directory=notes.export_plans(scratch / "checkout"),
            site_url=self.site_url,
            pull_request_source=self.pull_request_source,
        )
        return site.build(output)


def load_hub(registry: str, remote_url_template: str) -> PlanHub | None:
    """
    :param registry: The ``owner/repo`` whose notes hold the hub file.
    :param remote_url_template: How that name becomes a URL git can fetch.
    :return: The hub file, or ``None`` when the registry has none.
    """
    with tempfile.TemporaryDirectory() as scratch:
        notes = NotesBranch.fetch(
            registry,
            HubDefault.NOTES_BRANCH.value,
            remote_url_template,
            Path(scratch) / "notes.git",
        )
        text = None if notes is None else notes.read(HubDefault.HUB_FILE.value)
    return None if not text else PlanHub.from_mapping(yaml.safe_load(text))


def main() -> int:
    """
    Parse arguments and build the site. See the module docstring for the CLI contract.
    """
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--registry", required=True, help="The repository whose notes hold the hub file"
    )
    parser.add_argument(
        "--output", required=True, type=Path, help="The directory to write the site to"
    )
    parser.add_argument(
        "--site-url", default=None, help="The site's address, if not the hub file's"
    )
    parser.add_argument(
        "--remote-url-template", default=HubDefault.REMOTE_URL_TEMPLATE.value
    )
    arguments = parser.parse_args()

    hub = load_hub(arguments.registry, arguments.remote_url_template)
    if hub is None:
        logger.error(f"{arguments.registry} has no hub file on its notes branch.")
        return 1
    site_url = arguments.site_url or hub.site_url
    if not site_url:
        logger.error("The hub file names no site_url; pass --site-url.")
        return 1
    token = GitHubCredentialVariable.first_token()
    if not token:
        raise GitHubCredentialUnavailableError(tuple(GitHubCredentialVariable))
    site = HubSite(
        hub=hub,
        site_url=site_url,
        pull_request_source=GitHubPullRequestSource(token=token),
        remote_url_template=arguments.remote_url_template,
    )
    repositories = site.build(arguments.output)
    logger.info(
        f"published {sum(len(r.plans) for r in repositories)} plans from "
        f"{len(repositories)} repositories to {arguments.output}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
