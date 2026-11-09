"""
Tests for basstler.plan_site's static plan site: the hub, each repository's index, and
each plan's page.
"""

from __future__ import annotations

import dataclasses
import html
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path
from typing import Any

import pytest

from basstler.exceptions import PlanValidationError
from basstler.github_labels import GitHubLabel
from basstler.maintenance.board import (
    AccountField,
    PullRequestField,
    PullRequestHeadKey,
)
from basstler.github.exceptions import GitHubRequestFailed
from basstler.maintenance.github import (
    CommitReport,
    GitHubRepository,
    PullRequestListState,
    RepositoryPath,
)
from basstler.plan.dependencies import DependencyReference, DependencyResolver
from basstler.plan.model import ItemStatus, PlanDocument
from basstler.plan.repository_rules import RepositoryRules
from basstler.plan.validation import PlanValidator
from basstler.plan_site.__main__ import (
    HubSite,
    PlanSource,
    RepositorySite,
    SiteDigest,
    SiteFile,
)
from basstler.plan_site.chip_tone import ChipTone
from basstler.plan_site.cards import LiveStateAttribute, PlanTimeAttribute
from basstler.plan_site.hub import NotesBranch, PlanHub, SiteAddress
from basstler.plan_site.hub_page import PlanSummary, SiteStylesheet, SkippedPage
from basstler.plan_site.item_classifier import ItemClassifier
from basstler.plan_site.plan import Item, Plan
from basstler.plan_site.plan_page import PlanPage
from basstler.pull_request_source import GitHubPullRequestSource
from basstler.pull_request_state import LiveState, PullRequestRecord, PullRequestState
from basstler.repository import PullRequestReference, Repository
from basstler.github.states import CombinedCheckState

from ..constants.paths import DatasetLocation, RecordedCommitChecks
from ..constants.site import SitePlan, SiteRepository, SiteSampleText
from ..recorded_pull_requests import RecordedPullRequestSource
from ..github.recorded_client import RecordedGitHubClient

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


def page_of(output: Path, plan: SitePlan | None = None) -> str:
    """
    :param output: The site's root directory.
    :param plan: The plan whose page to read, or ``None`` for the index.
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


def test_build_reports_a_plan_whose_manifest_fails_validation(
    site: RepositorySite, tmp_path: Path
):
    broken = PlanSource.from_directory(SitePlan.BROKEN.directory)
    problems = PlanValidator(broken.manifest, site.plan_directory).problems
    repository = site.build(tmp_path)
    assert repository.skipped_plans == [
        SkippedPage(
            site_path=f"{NOTES_REPOSITORY}/{SitePlan.BROKEN}",
            reason=PlanValidationError(problems).error_message(),
        )
    ]


def test_the_index_names_every_plan_it_left_out(site: RepositorySite, tmp_path: Path):
    repository = site.build(tmp_path)
    (skipped,) = repository.skipped_plans
    assert skipped.site_path in page_of(tmp_path)


def test_build_links_each_plan_to_its_page_on_the_site(
    site: RepositorySite, tmp_path: Path
):
    repository = site.build(tmp_path)
    index = page_of(tmp_path)
    for summary in repository.plans:
        assert summary.page_url == site.plan_url(summary.id)
        assert link_to(summary.page_url) in index


def test_every_page_links_back_up_to_the_hub_and_its_index(
    site: RepositorySite, tmp_path: Path
):
    site.build(tmp_path)
    plan_page = page_of(tmp_path, SitePlan.FIRST)
    assert link_to(SiteSampleText.SITE_URL) in page_of(tmp_path)
    assert link_to(SiteSampleText.SITE_URL) in plan_page
    assert link_to(REPOSITORY_URL) in plan_page


def test_every_plan_page_shows_the_repositorys_rules(
    site: RepositorySite, tmp_path: Path
):
    site.build(tmp_path)
    rules = RepositoryRules.from_yaml(DatasetLocation.REPOSITORY_RULES.read_text())
    for plan in PUBLISHED_PLANS:
        page = page_of(tmp_path, plan)
        assert all(html.escape(rule.text) in page for rule in rules.rules)


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


def first_plan_card(site: RepositorySite, output: Path) -> PlanSummary:
    """
    :param site: The repository site to build.
    :param output: The directory to build it into.
    :return: The first plan's card on the built index.
    """
    return next(
        summary for summary in site.build(output).plans if summary.id == SitePlan.FIRST
    )


def test_a_plan_card_counts_a_pull_request_out_of_draft_as_reviewed(
    site: RepositorySite,
    pull_request_source: RecordedPullRequestSource,
    tmp_path: Path,
):
    in_draft = first_plan_card(site, tmp_path / "draft")
    pull_request_source.records[OPEN_PULL_REQUEST] = PullRequestRecord(
        state=PullRequestState.OPEN, draft=False
    )
    out_of_draft = first_plan_card(site, tmp_path / "ready")
    assert out_of_draft.reviewed == in_draft.reviewed + 1


def test_a_plan_card_counts_every_item_with_a_pull_request_as_started(
    site: RepositorySite, tmp_path: Path
):
    assert first_plan_card(site, tmp_path).started == len(FIRST_PLAN.items)


def test_the_repository_card_counts_every_plan_s_started_and_reviewed_items(
    site: RepositorySite, tmp_path: Path
):
    repository = site.build(tmp_path)
    assert repository.started == sum(plan.started for plan in repository.plans)
    assert repository.reviewed == sum(plan.reviewed for plan in repository.plans)


def test_build_looks_up_every_referenced_pull_request_in_its_own_repository(
    site: RepositorySite, pull_request_source: RecordedPullRequestSource, tmp_path: Path
):
    site.build(tmp_path)
    assert pull_request_source.looked_up == [
        MERGED_PULL_REQUEST,
        OPEN_PULL_REQUEST,
        ELSEWHERE_PULL_REQUEST,
        OPEN_PULL_REQUEST,
    ]


def test_pull_requests_of_leaves_out_a_number_the_repository_does_not_have(
    pull_request_source: RecordedPullRequestSource,
):
    assert pull_request_source.pull_requests_of(DependencyResolver(FIRST_PLAN)) == {
        str(PLAN_REPOSITORY): {
            str(reference.number): pull_request_source.records[reference]
            for reference in (MERGED_PULL_REQUEST, OPEN_PULL_REQUEST)
        }
    }


def test_a_plan_page_links_a_dependency_in_another_plan_to_its_card_there(
    site: RepositorySite, tmp_path: Path
):
    site.build(tmp_path)
    second_plan = Plan.from_mapping(
        PlanSource.from_directory(SitePlan.SECOND.directory).manifest
    )
    reference = DependencyReference.from_text(second_plan.items[0].depends_on[0])
    dependency = next(
        item
        for item in FIRST_PLAN.items
        if item.identifier == reference.item_identifier
    )
    card_url = f"{site.plan_url(reference.plan_id)}#{dependency.anchor}"
    assert link_to(card_url) in page_of(tmp_path, SitePlan.SECOND)


def test_a_plan_page_lays_out_a_column_per_wave(site: RepositorySite, tmp_path: Path):
    site.build(tmp_path)
    page = page_of(tmp_path, SitePlan.FIRST)
    for wave in FIRST_PLAN.waves:
        assert f'id="wave-{wave.id}"' in page


def test_every_page_links_the_site_stylesheet(site: RepositorySite, tmp_path: Path):
    site.build(tmp_path)
    for plan in (None, *PUBLISHED_PLANS):
        assert link_to(site.stylesheet_url) in page_of(tmp_path, plan)


def test_a_plan_page_shows_the_ci_and_assignees_of_an_open_pull_request(
    dataset_notes: NotesBranch, tmp_path: Path
):
    check_state = CombinedCheckState.FAILURE
    open_pull_request = PullRequestRecord(
        state=PullRequestState.OPEN,
        check_state=check_state,
        assignees=[SiteSampleText.ASSIGNEE.value],
    )
    site = RepositorySite(
        address=SiteAddress(SiteSampleText.SITE_URL),
        pull_request_source=RecordedPullRequestSource(
            records={OPEN_PULL_REQUEST: open_pull_request}
        ),
        notes=dataset_notes,
    )
    site.build(tmp_path)
    page = page_of(tmp_path, SitePlan.FIRST)
    assert f'class="chip {ChipTone.of_check_state(check_state)}"' in page
    assert f"@{SiteSampleText.ASSIGNEE}" in page


def test_build_links_the_tracking_issue_on_the_plan_page(
    site: RepositorySite, tmp_path: Path
):
    site.build(tmp_path)
    tracking_url = PLAN_REPOSITORY.issue_url(FIRST_PLAN.tracking_issue)
    assert tracking_url in page_of(tmp_path, SitePlan.FIRST)


# %% the whole site


@pytest.fixture
def hub_site(
    pull_request_source: RecordedPullRequestSource, dataset_remotes: Path
) -> HubSite:
    """
    A site whose hub lists the notes repository, published from the dataset's plans, and
    a repository with no notes branch.
    """
    listed = (SiteRepository.NOTES.value, SiteRepository.MISSING.value)
    hub = PlanHub(
        registry=str(NOTES_REPOSITORY),
        repositories=[str(repository) for repository in listed],
    )
    return HubSite(
        address=SiteAddress(SiteSampleText.SITE_URL),
        pull_request_source=pull_request_source,
        hub=hub,
        remote_root=str(dataset_remotes),
    )


def test_the_hub_links_every_repository_and_reports_one_it_cannot_fetch(
    hub_site: HubSite, tmp_path: Path
):
    summary = hub_site.build(tmp_path / "site")

    hub_page = (tmp_path / "site" / SiteFile.PAGE).read_text()
    assert link_to(REPOSITORY_URL) in hub_page
    repositories = summary.repositories
    assert [len(repository.plans) for repository in repositories] == [
        len(PUBLISHED_PLANS),
        0,
    ]
    assert repositories[1].error
    assert summary.done == sum(repository.done for repository in repositories)
    assert summary.total == sum(repository.total for repository in repositories)
    assert summary.started == sum(repository.started for repository in repositories)
    assert summary.reviewed == sum(repository.reviewed for repository in repositories)
    assert summary.progress_label in hub_page
    assert (tmp_path / "site" / SiteFile.NO_JEKYLL).exists()


def test_the_site_reports_every_plan_and_repository_it_left_out(
    hub_site: HubSite, tmp_path: Path
):
    summary = hub_site.build(tmp_path / "site")
    readable, unreadable = summary.repositories
    assert summary.skipped_pages == [
        *readable.skipped_plans,
        SkippedPage(site_path=unreadable.name, reason=unreadable.error),
    ]


def test_the_hub_names_every_plan_and_repository_it_left_out(
    hub_site: HubSite, tmp_path: Path
):
    summary = hub_site.build(tmp_path / "site")
    hub_page = (tmp_path / "site" / SiteFile.PAGE).read_text()
    for skipped in summary.skipped_pages:
        assert skipped.site_path in hub_page


def test_the_site_build_writes_the_stylesheet_its_pages_link(
    hub_site: HubSite, tmp_path: Path
):
    output = tmp_path / "site"
    hub_site.build(output)
    assert (output / SiteFile.STYLESHEET).read_text() == SiteStylesheet().render()
    assert link_to(hub_site.stylesheet_url) in (output / SiteFile.PAGE).read_text()


def test_the_site_build_writes_its_digest(hub_site: HubSite, tmp_path: Path):
    output = tmp_path / "site"
    hub_site.build(output)
    assert (output / SiteFile.DIGEST).read_text() == f"{SiteDigest(output).value}\n"


# %% the site's digest


def test_two_builds_of_the_same_plans_have_the_same_digest(
    site: RepositorySite, tmp_path: Path
):
    site.build(tmp_path / "first")
    site.build(tmp_path / "second")
    assert SiteDigest(tmp_path / "first").value == SiteDigest(tmp_path / "second").value


def test_the_digest_changes_when_a_page_changes(site: RepositorySite, tmp_path: Path):
    site.build(tmp_path)
    published = SiteDigest(tmp_path).value
    index = tmp_path / str(NOTES_REPOSITORY) / SiteFile.PAGE
    index.write_text(f"{index.read_text()}{SiteSampleText.SITE_URL}")
    assert SiteDigest(tmp_path).value != published


def test_the_digest_changes_when_a_page_is_removed(
    site: RepositorySite, tmp_path: Path
):
    site.build(tmp_path)
    published = SiteDigest(tmp_path).value
    (tmp_path / str(NOTES_REPOSITORY) / SitePlan.SECOND / SiteFile.PAGE).unlink()
    assert SiteDigest(tmp_path).value != published


def test_the_digest_leaves_out_its_own_file(site: RepositorySite, tmp_path: Path):
    site.build(tmp_path)
    published = SiteDigest(tmp_path).value
    SiteDigest(tmp_path).write()
    assert SiteDigest(tmp_path).value == published


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


def test_from_api_reads_the_head_commit():
    commit = SiteSampleText.HEAD_COMMIT.value
    record = PullRequestRecord.from_api(
        api_pull_request(
            OPEN_PULL_REQUEST,
            {PullRequestField.HEAD: {PullRequestHeadKey.COMMIT: commit}},
        )
    )
    assert record.head_commit == commit


def test_from_api_without_a_head_reads_no_head_commit():
    assert (
        PullRequestRecord.from_api(api_pull_request(OPEN_PULL_REQUEST)).head_commit
        is None
    )


def test_from_api_reads_the_assignee_logins():
    logins = [SiteSampleText.ASSIGNEE.value]
    record = PullRequestRecord.from_api(
        api_pull_request(
            OPEN_PULL_REQUEST,
            {
                PullRequestField.ASSIGNEES: [
                    {AccountField.LOGIN: login} for login in logins
                ]
            },
        )
    )
    assert record.assignees == logins


def listing_path(repository: Repository) -> str:
    """
    :param repository: The repository whose pull requests are listed.
    :return: The path every pull request of it is listed from.
    """
    return (
        f"/{repository.api_path}/pulls?state={PullRequestListState.ALL.query}"
        f"&per_page={GitHubRepository.page_size}"
    )


def details_of(repository: Repository) -> dict[str, Any]:
    """
    :param repository: A repository the source can read.
    :return: The recorded response to the read of its details.
    """
    return {
        f"/{repository.api_path}": json.loads(
            DatasetLocation.REPOSITORY_NOT_FORK.read_text()
        )
    }


def pull_request_path(reference: PullRequestReference) -> str:
    """
    :param reference: The pull request to read.
    :return: The path it is read from on its own.
    """
    return f"/{reference.repository.pull_request_path(reference.number)}"


def test_github_source_answers_a_listed_pull_request_from_the_listing():
    listed = api_pull_request(OPEN_PULL_REQUEST, {PullRequestField.DRAFT: True})
    source = GitHubPullRequestSource(
        RecordedGitHubClient(
            responses=details_of(OPEN_PULL_REQUEST.repository),
            pages={listing_path(OPEN_PULL_REQUEST.repository): [[listed]]},
        )
    )
    record = source.pull_request(OPEN_PULL_REQUEST)
    assert record == PullRequestRecord.from_api(listed)


def test_github_source_reads_an_unlisted_pull_request_on_its_own():
    unlisted = api_pull_request(OPEN_PULL_REQUEST, {PullRequestField.DRAFT: True})
    source = GitHubPullRequestSource(
        RecordedGitHubClient(
            responses={
                **details_of(OPEN_PULL_REQUEST.repository),
                pull_request_path(OPEN_PULL_REQUEST): unlisted,
            },
            pages={listing_path(OPEN_PULL_REQUEST.repository): [[]]},
        )
    )
    record = source.pull_request(OPEN_PULL_REQUEST)
    assert record == PullRequestRecord.from_api(unlisted)


def test_github_source_answers_none_for_a_pull_request_that_does_not_exist():
    source = GitHubPullRequestSource(
        RecordedGitHubClient(
            responses=details_of(ELSEWHERE_PULL_REQUEST.repository),
            pages={listing_path(ELSEWHERE_PULL_REQUEST.repository): [[]]},
        )
    )
    assert source.pull_request(ELSEWHERE_PULL_REQUEST) is None


# %% a repository the build cannot read


def test_github_source_answers_none_for_a_pull_request_on_a_repository_it_cannot_read():
    source = GitHubPullRequestSource(RecordedGitHubClient())
    assert source.pull_request(ELSEWHERE_PULL_REQUEST) is None


def test_github_source_finds_a_repository_whose_details_are_refused_unreadable():
    source = GitHubPullRequestSource(
        RecordedGitHubClient(responses=details_of(PLAN_REPOSITORY))
    )
    assert source.unreadable_repositories_of(DependencyResolver(FIRST_PLAN)) == {
        ELSEWHERE_PULL_REQUEST.repository
    }


def test_github_source_answers_no_issue_url_on_a_repository_it_cannot_read():
    source = GitHubPullRequestSource(RecordedGitHubClient(refusal=HTTPStatus.FORBIDDEN))
    assert source.issue_url(PLAN_REPOSITORY, FIRST_PLAN.tracking_issue) is None


def unreadable_elsewhere_site(dataset_notes: NotesBranch) -> RepositorySite:
    """
    :param dataset_notes: The dataset's notes branch.
    :return: A site over it whose pull request source reads the first plan's default
        repository, which has no pull requests, and is refused the other repository.
    """
    return RepositorySite(
        address=SiteAddress(SiteSampleText.SITE_URL),
        pull_request_source=GitHubPullRequestSource(
            RecordedGitHubClient(
                responses=details_of(PLAN_REPOSITORY),
                pages={listing_path(PLAN_REPOSITORY): [[]]},
            )
        ),
        notes=dataset_notes,
    )


def test_build_publishes_a_plan_whose_item_is_on_a_repository_it_cannot_read(
    dataset_notes: NotesBranch, tmp_path: Path
):
    unreadable_elsewhere_site(dataset_notes).build(tmp_path)
    assert (tmp_path / str(NOTES_REPOSITORY) / SitePlan.FIRST / SiteFile.PAGE).exists()


def test_an_item_on_a_repository_the_build_cannot_read_shows_how_to_let_it(
    dataset_notes: NotesBranch, tmp_path: Path
):
    unreadable_elsewhere_site(dataset_notes).build(tmp_path)
    warning = ItemClassifier.access_warning_of(str(ELSEWHERE_PULL_REQUEST.repository))
    assert html.escape(warning) in page_of(tmp_path, SitePlan.FIRST)


def test_build_reports_a_repository_it_cannot_read(
    dataset_notes: NotesBranch, tmp_path: Path, capsys: pytest.CaptureFixture
):
    unreadable_elsewhere_site(dataset_notes).build(tmp_path)
    warning = ItemClassifier.access_warning_of(str(ELSEWHERE_PULL_REQUEST.repository))
    assert f"{NOTES_REPOSITORY}/{SitePlan.FIRST}: {warning}" in capsys.readouterr().err


def item_on_an_unreadable_repository() -> Item:
    """
    :return: The first plan's item on a repository other than its default, after its
        page is rendered with that repository unreadable.
    """
    plan = Plan.from_mapping(
        PlanSource.from_directory(SitePlan.FIRST.directory).manifest
    )
    PlanPage(
        stylesheet_url=SiteSampleText.SITE_URL,
        plan=plan,
        roadmap_text="",
        pull_requests_by_repository={},
        unreadable_repositories=frozenset({ELSEWHERE_PULL_REQUEST.repository}),
    ).render()
    return next(item for item in plan.items if item.repository is not None)


def test_an_item_on_a_repository_the_build_cannot_read_is_classified_so():
    assert (
        item_on_an_unreadable_repository().live_state is LiveState.REPOSITORY_UNREADABLE
    )


def test_an_item_on_a_repository_the_build_cannot_read_is_not_reported_as_drift():
    assert item_on_an_unreadable_repository().drift_description is None


def commit_report_path(report: CommitReport) -> str:
    """
    :param report: Which listing reported against :attr:`SiteSampleText.HEAD_COMMIT`
        to read.
    :return: The path it is listed from.
    """
    return (
        f"/{OPEN_PULL_REQUEST.repository.api_path}{RepositoryPath.COMMITS}/"
        f"{SiteSampleText.HEAD_COMMIT}/{report}?per_page={GitHubRepository.page_size}"
    )


def api_pull_request_at_head(state: PullRequestState) -> dict[str, Any]:
    """
    :param state: Whether the pull request is open or closed.
    :return: The open pull request of the first plan, in that state, with its head at
        :attr:`SiteSampleText.HEAD_COMMIT`.
    """
    return api_pull_request(
        OPEN_PULL_REQUEST,
        {
            PullRequestField.STATE: state.value,
            PullRequestField.HEAD: {
                PullRequestHeadKey.COMMIT: SiteSampleText.HEAD_COMMIT.value
            },
        },
    )


def test_github_source_reads_the_checks_of_an_open_pull_request():
    source = GitHubPullRequestSource(
        RecordedGitHubClient(
            responses=details_of(OPEN_PULL_REQUEST.repository),
            pages={
                listing_path(OPEN_PULL_REQUEST.repository): [
                    [api_pull_request_at_head(PullRequestState.OPEN)]
                ],
                commit_report_path(CommitReport.CHECK_RUNS): [
                    json.loads(
                        RecordedCommitChecks.ONE_CHECK_RUN_FAILING.value.read_text()
                    )
                ],
                commit_report_path(CommitReport.STATUS): [
                    json.loads(RecordedCommitChecks.NO_STATUSES.value.read_text())
                ],
            },
        )
    )
    assert (
        source.pull_request(OPEN_PULL_REQUEST).check_state is CombinedCheckState.FAILURE
    )


def test_github_source_leaves_the_checks_of_a_closed_pull_request_unread():
    source = GitHubPullRequestSource(
        RecordedGitHubClient(
            responses=details_of(OPEN_PULL_REQUEST.repository),
            pages={
                listing_path(OPEN_PULL_REQUEST.repository): [
                    [api_pull_request_at_head(PullRequestState.CLOSED)]
                ]
            },
        )
    )
    assert source.pull_request(OPEN_PULL_REQUEST).check_state is None


def test_github_source_reads_an_issue_url():
    issue_url = PLAN_REPOSITORY.issue_url(FIRST_PLAN.tracking_issue)
    source = GitHubPullRequestSource(
        RecordedGitHubClient(
            responses={
                **details_of(PLAN_REPOSITORY),
                f"/{PLAN_REPOSITORY.api_path}/issues/{FIRST_PLAN.tracking_issue}": {
                    PullRequestField.HTML_URL.key: issue_url
                },
            }
        )
    )
    assert source.issue_url(PLAN_REPOSITORY, FIRST_PLAN.tracking_issue) == issue_url


def test_github_source_reraises_a_refusal_other_than_not_found():
    with pytest.raises(GitHubRequestFailed) as refused:
        GitHubPullRequestSource(
            RecordedGitHubClient(
                responses=details_of(PLAN_REPOSITORY), refusal=HTTPStatus.FORBIDDEN
            )
        ).issue_url(PLAN_REPOSITORY, FIRST_PLAN.tracking_issue)
    assert refused.value.status == HTTPStatus.FORBIDDEN


# %% when a plan page says its plan was created, changed and refreshed


def test_a_plan_page_shows_when_its_plan_was_created_and_last_modified(
    hub_site: HubSite, tmp_path: Path
):
    output = tmp_path / "site"
    hub_site.build(output)

    notes = NotesBranch.fetch(
        NOTES_REPOSITORY,
        hub_site.hub.notes_branch,
        hub_site.remote_root,
        tmp_path / "scratch",
    )
    history = notes.history_of(SitePlan.FIRST)
    page = page_of(output, SitePlan.FIRST)
    assert f'datetime="{history.created_at.isoformat()}"' in page
    assert f'datetime="{history.modified_at.isoformat()}"' in page


def test_a_plan_page_shows_the_build_time_as_its_last_refresh(
    site: RepositorySite, tmp_path: Path
):
    site.build(tmp_path)

    assert (
        f'{PlanTimeAttribute.REFRESHED} datetime="{site.built_at.isoformat()}"'
        in page_of(tmp_path, SitePlan.FIRST)
    )


def test_builds_at_different_times_of_the_same_plans_have_the_same_digest(
    site: RepositorySite, tmp_path: Path
):
    later = dataclasses.replace(site, built_at=datetime(2030, 1, 1, tzinfo=UTC))

    site.build(tmp_path / "first")
    later.build(tmp_path / "second")

    assert SiteDigest(tmp_path / "first").value == SiteDigest(tmp_path / "second").value


def test_an_item_s_pull_request_chip_names_its_api_address(
    site: RepositorySite, tmp_path: Path
):
    site.build(tmp_path)

    assert (
        f'{LiveStateAttribute.PULL_REQUEST}="{OPEN_PULL_REQUEST.api_url}"'
        in page_of(tmp_path, SitePlan.FIRST)
    )
