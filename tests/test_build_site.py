"""
Tests for build_site.py's static plan site: the hub, each repository's index, and each
plan's dashboard.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from http import HTTPStatus
from pathlib import Path
from typing import Any

import pytest

from basstler.build_dashboard import Plan, PullRequestRecord, PullRequestState
from basstler.build_site import (
    GitHubPullRequestSource,
    HubSite,
    PlanSource,
    PullRequestSource,
    RepositorySite,
    SiteFile,
)
from basstler.github_labels import GitHubLabel
from basstler.maintenance_board import PullRequestField
from basstler.maintenance_github import (
    GitHubRepository,
    GitHubRequestFailed,
    PullRequestListState,
)
from basstler.plan_hub import PlanHub
from basstler.plan_item_bootstrap import PlanDocument
from basstler.plan_model import ItemStatus
from basstler.repository import PullRequestReference, Repository

from .constants import DatasetLocation, SitePlan, SiteRepository, SiteSampleText
from .test_plan_hub import publish_notes

NOTES_REPOSITORY = SiteRepository.NOTES.value
"""
The repository whose notes the dataset's plans stand in for.
"""

REPOSITORY_URL = f"{SiteSampleText.SITE_URL}{NOTES_REPOSITORY}/"
"""
Where that repository's index is served from.
"""

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

PUBLISHED_PLANS = (SitePlan.FIRST, SitePlan.SECOND)
"""
The dataset's plans whose manifests pass validation.
"""


def link_to(url: str) -> str:
    """
    :param url: The address a page links to.
    :return: The attribute a rendered link to it carries.
    """
    return f'href="{url}"'


# %% recorded pull request state


@dataclass
class RecordedPullRequestSource(PullRequestSource):
    """
    Pull request state answered from a fixed record, noting every lookup made.
    """

    records: dict[PullRequestReference, PullRequestRecord] = field(default_factory=dict)
    """
    The pull requests that exist, by reference.
    """

    issue_urls: dict[PullRequestReference, str] = field(default_factory=dict)
    """
    The issue pages that exist, by repository and number.
    """

    looked_up: list[PullRequestReference] = field(default_factory=list)
    """
    Every pull request asked for, in order.
    """

    def pull_request(self, reference: PullRequestReference) -> PullRequestRecord | None:
        self.looked_up.append(reference)
        return self.records.get(reference)

    def issue_url(self, repository: Repository, number: int) -> str | None:
        return self.issue_urls.get(PullRequestReference(repository, number))


@pytest.fixture
def pull_request_source() -> RecordedPullRequestSource:
    """
    The live state of the first plan's pull requests, all but one of which exist.
    """
    return RecordedPullRequestSource(
        records={
            MERGED_PULL_REQUEST: PullRequestRecord(
                state=PullRequestState.CLOSED, labels=[GitHubLabel.MERGED.value]
            ),
            OPEN_PULL_REQUEST: PullRequestRecord(
                state=PullRequestState.OPEN, draft=True
            ),
        },
        issue_urls={
            PullRequestReference(
                PLAN_REPOSITORY, FIRST_PLAN.tracking_issue
            ): PLAN_REPOSITORY.issue_url(FIRST_PLAN.tracking_issue)
        },
    )


@pytest.fixture
def site(pull_request_source: RecordedPullRequestSource) -> RepositorySite:
    """
    A site over the dataset's plans directory.
    """
    return RepositorySite(
        site_url=SiteSampleText.SITE_URL,
        pull_request_source=pull_request_source,
        repository=NOTES_REPOSITORY,
        plans_directory=DatasetLocation.SITE_PLANS.value,
    )


def page_of(output: Path, plan: SitePlan | None = None) -> str:
    """
    :param output: The site's root directory.
    :param plan: The plan whose dashboard to read, or ``None`` for the index.
    :return: The page the notes repository serves there.
    """
    directory = output / str(NOTES_REPOSITORY)
    if plan is not None:
        directory /= plan
    return (directory / SiteFile.PAGE).read_text()


# %% the plans the notes branch carries


def test_every_plan_in_reads_only_directories_that_carry_a_manifest():
    sources = PlanSource.every_plan_in(DatasetLocation.SITE_PLANS.value)
    assert [source.directory_name for source in sources] == sorted(SitePlan)


def test_from_directory_reads_the_roadmap():
    source = PlanSource.from_directory(SitePlan.FIRST.directory)
    assert source.roadmap_text == (
        (SitePlan.FIRST.directory / PlanDocument.ROADMAP).read_text()
    )


def test_from_directory_without_a_roadmap_reads_it_as_empty(tmp_path: Path):
    manifest = SitePlan.SECOND.directory / PlanDocument.MANIFEST
    (tmp_path / PlanDocument.MANIFEST).write_text(manifest.read_text())
    assert PlanSource.from_directory(tmp_path).roadmap_text == ""


# %% building the site


def test_build_writes_the_index_and_a_page_per_valid_plan(
    site: RepositorySite, tmp_path: Path
):
    site.build(tmp_path)
    written = sorted(path for path in tmp_path.rglob("*") if path.is_file())
    repository_directory = tmp_path / str(NOTES_REPOSITORY)
    assert written == sorted(
        [repository_directory / SiteFile.PAGE]
        + [repository_directory / plan / SiteFile.PAGE for plan in PUBLISHED_PLANS]
    )


def test_build_leaves_out_a_plan_whose_manifest_fails_validation(
    site: RepositorySite, tmp_path: Path
):
    repository = site.build(tmp_path)
    assert [summary.id for summary in repository.plans] == list(PUBLISHED_PLANS)


def test_build_links_each_plan_to_its_page_on_the_site(
    site: RepositorySite, tmp_path: Path
):
    repository = site.build(tmp_path)
    index = page_of(tmp_path)
    for summary in repository.plans:
        assert summary.dashboard_url == site.plan_url(summary.id)
        assert link_to(summary.dashboard_url) in index


def test_every_page_links_back_up_to_the_hub_and_its_index(
    site: RepositorySite, tmp_path: Path
):
    site.build(tmp_path)
    dashboard = page_of(tmp_path, SitePlan.FIRST)
    assert link_to(SiteSampleText.SITE_URL) in page_of(tmp_path)
    assert link_to(SiteSampleText.SITE_URL) in dashboard
    assert link_to(REPOSITORY_URL) in dashboard


def test_plan_url_joins_the_site_address_whether_or_not_it_ends_in_a_slash(
    pull_request_source: RecordedPullRequestSource,
):
    with_slash, without_slash = (
        RepositorySite(site_url, pull_request_source, NOTES_REPOSITORY, Path())
        for site_url in (SiteSampleText.SITE_URL, SiteSampleText.SITE_URL.rstrip("/"))
    )
    assert with_slash.plan_url(SitePlan.FIRST) == without_slash.plan_url(SitePlan.FIRST)
    assert with_slash.plan_url(SitePlan.FIRST) == f"{REPOSITORY_URL}{SitePlan.FIRST}/"


def test_build_counts_done_items_from_the_manifest(
    site: RepositorySite, tmp_path: Path
):
    first_plan = next(
        summary
        for summary in site.build(tmp_path).plans
        if summary.id == SitePlan.FIRST
    )
    statuses = [item.status for item in FIRST_PLAN.items]
    assert first_plan.done == statuses.count(ItemStatus.DONE)
    assert first_plan.total == len(statuses)


def test_the_repository_card_counts_every_plan(site: RepositorySite, tmp_path: Path):
    repository = site.build(tmp_path)
    assert repository.done == sum(plan.done for plan in repository.plans)
    assert repository.total == sum(plan.total for plan in repository.plans)


def test_build_looks_up_every_referenced_pull_request_in_its_own_repository(
    site: RepositorySite, pull_request_source: RecordedPullRequestSource, tmp_path: Path
):
    site.build(tmp_path)
    assert pull_request_source.looked_up == [
        MERGED_PULL_REQUEST,
        OPEN_PULL_REQUEST,
        ELSEWHERE_PULL_REQUEST,
    ]


def test_pull_requests_of_leaves_out_a_number_the_repository_does_not_have(
    site: RepositorySite, pull_request_source: RecordedPullRequestSource
):
    assert site.pull_requests_of(FIRST_PLAN) == {
        str(PLAN_REPOSITORY): {
            str(reference.number): pull_request_source.records[reference]
            for reference in (MERGED_PULL_REQUEST, OPEN_PULL_REQUEST)
        }
    }


def test_build_links_the_tracking_issue_on_the_plan_page(
    site: RepositorySite, tmp_path: Path
):
    site.build(tmp_path)
    tracking_url = PLAN_REPOSITORY.issue_url(FIRST_PLAN.tracking_issue)
    assert tracking_url in page_of(tmp_path, SitePlan.FIRST)


# %% the whole site


def test_the_hub_links_every_repository_and_reports_one_it_cannot_fetch(
    pull_request_source: RecordedPullRequestSource, tmp_path: Path
):
    remotes = tmp_path / "remotes"
    publish_notes(
        remotes,
        NOTES_REPOSITORY,
        {
            path.relative_to(DatasetLocation.SITE_PLANS.value): path.read_text()
            for path in DatasetLocation.SITE_PLANS.value.rglob("*")
            if path.is_file()
        },
    )
    listed = (SiteRepository.NOTES.value, SiteRepository.MISSING.value)
    hub = PlanHub(
        registry=str(NOTES_REPOSITORY),
        repositories=[str(repository) for repository in listed],
    )
    site = HubSite(
        site_url=SiteSampleText.SITE_URL,
        pull_request_source=pull_request_source,
        hub=hub,
        remote_root=str(remotes),
    )

    repositories = site.build(tmp_path / "site")

    hub_page = (tmp_path / "site" / SiteFile.PAGE).read_text()
    assert link_to(REPOSITORY_URL) in hub_page
    assert [len(repository.plans) for repository in repositories] == [
        len(PUBLISHED_PLANS),
        0,
    ]
    assert repositories[1].error
    assert (tmp_path / "site" / SiteFile.NO_JEKYLL).exists()


# %% reading pull requests from the GitHub API


def api_pull_request(
    reference: PullRequestReference,
    overrides: Mapping[PullRequestField, Any] | None = None,
) -> dict[str, Any]:
    """
    Build one pull request object shaped like the pulls API's.

    :param reference: The pull request to describe.
    :param overrides: Fields to replace.
    """
    record = {
        PullRequestField.NUMBER: reference.number,
        PullRequestField.STATE: PullRequestState.OPEN.value,
        PullRequestField.DRAFT: False,
        PullRequestField.MERGED_AT: None,
        PullRequestField.LABELS: [],
        PullRequestField.HTML_URL: reference.url,
    }
    record.update(overrides or {})
    return {
        pull_request_field.key: value for pull_request_field, value in record.items()
    }


def test_from_api_reads_label_names():
    labels = [GitHubLabel.BUG.value, GitHubLabel.MERGED.value]
    record = PullRequestRecord.from_api(
        api_pull_request(
            MERGED_PULL_REQUEST,
            {PullRequestField.LABELS: [{"name": label} for label in labels]},
        )
    )
    assert record.labels == labels


def test_from_api_reads_a_merge():
    merged_at = "2026-10-01T12:00:00+00:00"
    record = PullRequestRecord.from_api(
        api_pull_request(
            MERGED_PULL_REQUEST,
            {
                PullRequestField.STATE: PullRequestState.CLOSED.value,
                PullRequestField.MERGED_AT: merged_at,
            },
        )
    )
    assert record.was_merged
    assert record.merged_at.isoformat() == merged_at


@dataclass(frozen=True)
class RecordedRepository(GitHubRepository):
    """
    A repository client answering from recorded responses, keyed by request path.
    """

    responses: Mapping[str, Any] = field(default_factory=dict)
    """
    The decoded response to each ``GET`` path; any other path answers not found.
    """

    def _call(
        self, method: str, path: str, payload: Mapping[str, Any] | None = None
    ) -> Any:
        if path not in self.responses:
            raise GitHubRequestFailed(
                status=HTTPStatus.NOT_FOUND, detail="", method=method, path=path
            )
        return self.responses[path]


@dataclass
class RecordedGitHubPullRequestSource(GitHubPullRequestSource):
    """
    The GitHub source, with its client answering from recorded responses.
    """

    responses: Mapping[str, Any] = field(default_factory=dict)
    """
    What every repository's client answers, by request path.
    """

    def client_for(self, repository: Repository) -> GitHubRepository:
        return RecordedRepository(repository, self.token, responses=self.responses)


def listing_path() -> str:
    """
    :return: The path the first page of every pull request is listed from.
    """
    return (
        f"/pulls?state={PullRequestListState.ALL}"
        f"&per_page={GitHubRepository.page_size}&page=1"
    )


def pull_request_path(reference: PullRequestReference) -> str:
    """
    :param reference: The pull request to read.
    :return: The path it is read from on its own.
    """
    return f"/pulls/{reference.number}"


def test_github_source_answers_a_listed_pull_request_from_the_listing():
    listed = api_pull_request(OPEN_PULL_REQUEST, {PullRequestField.DRAFT: True})
    source = RecordedGitHubPullRequestSource(
        token=SiteSampleText.TOKEN, responses={listing_path(): [listed]}
    )
    record = source.pull_request(OPEN_PULL_REQUEST)
    assert record == PullRequestRecord.from_api(listed)


def test_github_source_reads_an_unlisted_pull_request_on_its_own():
    unlisted = api_pull_request(OPEN_PULL_REQUEST, {PullRequestField.DRAFT: True})
    source = RecordedGitHubPullRequestSource(
        token=SiteSampleText.TOKEN,
        responses={listing_path(): [], pull_request_path(OPEN_PULL_REQUEST): unlisted},
    )
    record = source.pull_request(OPEN_PULL_REQUEST)
    assert record == PullRequestRecord.from_api(unlisted)


def test_github_source_answers_none_for_a_pull_request_that_does_not_exist():
    source = RecordedGitHubPullRequestSource(
        token=SiteSampleText.TOKEN, responses={listing_path(): []}
    )
    assert source.pull_request(ELSEWHERE_PULL_REQUEST) is None


def test_github_source_reads_an_issue_url():
    issue_url = PLAN_REPOSITORY.issue_url(FIRST_PLAN.tracking_issue)
    source = RecordedGitHubPullRequestSource(
        token=SiteSampleText.TOKEN,
        responses={
            f"/issues/{FIRST_PLAN.tracking_issue}": {
                PullRequestField.HTML_URL.key: issue_url
            }
        },
    )
    assert source.issue_url(PLAN_REPOSITORY, FIRST_PLAN.tracking_issue) == issue_url


@dataclass(frozen=True)
class RefusingRepository(GitHubRepository):
    """
    A repository client whose every call is refused as forbidden.
    """

    def _call(
        self, method: str, path: str, payload: Mapping[str, Any] | None = None
    ) -> Any:
        raise GitHubRequestFailed(
            status=HTTPStatus.FORBIDDEN, detail="", method=method, path=path
        )


@dataclass
class RefusingGitHubPullRequestSource(GitHubPullRequestSource):
    """
    The GitHub source, with every call refused.
    """

    def client_for(self, repository: Repository) -> GitHubRepository:
        return RefusingRepository(repository, self.token)


def test_github_source_reraises_a_refusal_other_than_not_found():
    with pytest.raises(GitHubRequestFailed) as refused:
        RefusingGitHubPullRequestSource(token=SiteSampleText.TOKEN).issue_url(
            PLAN_REPOSITORY, FIRST_PLAN.tracking_issue
        )
    assert refused.value.status == HTTPStatus.FORBIDDEN
