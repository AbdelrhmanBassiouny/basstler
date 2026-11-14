"""
Tests for basstler.plan_site's static plan site: the hub, each repository's index, and
each plan's page.
"""

from __future__ import annotations

import dataclasses
import html
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path

import pytest

from basstler.exceptions import PlanValidationError
from basstler.github.exceptions import GitHubRequestFailed
from basstler.github.pull_request_record import (
    PullRequestField,
)
from basstler.github.pull_request_source import GitHubPullRequestSource
from basstler.github.pull_request_state import PullRequestRecord, PullRequestState
from basstler.github.states import CombinedCheckState
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
from basstler.plan_site.cards import LiveStateAttribute, PlanTimeAttribute
from basstler.plan_site.chip_tone import ChipTone
from basstler.plan_site.hub import NotesBranch, PlanHub, SiteAddress
from basstler.plan_site.hub_page import PlanSummary, SiteStylesheet, SkippedPage
from basstler.plan_site.item_classifier import ItemClassifier
from basstler.plan_site.plan import Plan
from basstler.plan_site.theme import AppearanceSettings, BundledFont, SiteAppearance

from ..constants.paths import DatasetLocation
from ..constants.site import SitePlan, SiteRepository, SiteSampleText
from ..github.pull_request_api import api_pull_request, details_of, listing_path
from ..github.recorded_client import RecordedGitHubClient
from ..recorded_pull_requests import RecordedPullRequestSource
from .first_plan import (
    ELSEWHERE_PULL_REQUEST,
    FIRST_PLAN,
    MERGED_PULL_REQUEST,
    OPEN_PULL_REQUEST,
    PLAN_REPOSITORY,
)
from .test_theme import theme_from

NOTES_REPOSITORY = SiteRepository.NOTES.value
"""
The repository whose notes the dataset's plans stand in for.
"""

REPOSITORY_URL = f"{SiteSampleText.SITE_URL}{NOTES_REPOSITORY}/"
"""
Where that repository's index is served from.
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


def test_live_pull_requests_leave_out_a_number_the_repository_does_not_have(
    pull_request_source: RecordedPullRequestSource,
):
    live_pull_requests = pull_request_source.live_pull_requests_of(
        DependencyResolver(FIRST_PLAN)
    )
    assert live_pull_requests.pull_requests_by_repository == {
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


@pytest.mark.parametrize("font", BundledFont)
def test_the_site_build_writes_every_font_its_stylesheet_names(
    hub_site: HubSite, tmp_path: Path, font: BundledFont
):
    output = tmp_path / "site"
    hub_site.build(output)
    assert (output / font.value.site_path).read_bytes() == font.value.file.read_bytes()


def test_the_site_build_draws_every_page_in_the_hub_file_s_themes(
    hub_site: HubSite, tmp_path: Path
):
    faint_theme = theme_from(DatasetLocation.FAINT_THEME)
    settings = AppearanceSettings(themes=(faint_theme,))
    site = dataclasses.replace(
        hub_site, hub=dataclasses.replace(hub_site.hub, appearance=settings)
    )
    output = tmp_path / "site"

    site.build(output)

    assert (output / SiteFile.STYLESHEET).read_text() == SiteStylesheet(
        SiteAppearance(settings)
    ).render()
    assert (
        f"Theme <code>{faint_theme.identifier}</code>"
        in (output / SiteFile.PAGE).read_text()
    )


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


# %% a repository the build cannot read


def unreadable_elsewhere_site(
    dataset_notes: NotesBranch, refusal: HTTPStatus = HTTPStatus.NOT_FOUND
) -> RepositorySite:
    """
    :param dataset_notes: The dataset's notes branch.
    :param refusal: The status the read of the other repository is refused with.
    :return: A site over it whose pull request source reads the first plan's default
        repository, its pull requests and its tracking issue, and is refused the other
        repository.
    """
    return RepositorySite(
        address=SiteAddress(SiteSampleText.SITE_URL),
        pull_request_source=GitHubPullRequestSource(
            RecordedGitHubClient(
                responses={
                    **details_of(PLAN_REPOSITORY),
                    f"/{PLAN_REPOSITORY.issue_path(FIRST_PLAN.tracking_issue)}": {
                        PullRequestField.HTML_URL.key: PLAN_REPOSITORY.issue_url(
                            FIRST_PLAN.tracking_issue
                        )
                    },
                },
                pages={
                    listing_path(PLAN_REPOSITORY): [
                        [
                            api_pull_request(reference)
                            for reference in (MERGED_PULL_REQUEST, OPEN_PULL_REQUEST)
                        ]
                    ]
                },
                refusal=refusal,
            )
        ),
        notes=dataset_notes,
    )


def test_build_publishes_a_plan_whose_item_is_on_a_repository_it_cannot_read(
    dataset_notes: NotesBranch, tmp_path: Path
):
    unreadable_elsewhere_site(dataset_notes).build(tmp_path)
    assert (tmp_path / str(NOTES_REPOSITORY) / SitePlan.FIRST / SiteFile.PAGE).exists()


def test_build_fails_when_a_repository_s_read_fails_other_than_by_refused_access(
    dataset_notes: NotesBranch, tmp_path: Path
):
    with pytest.raises(GitHubRequestFailed) as failed:
        unreadable_elsewhere_site(dataset_notes, HTTPStatus.UNAUTHORIZED).build(
            tmp_path
        )
    assert failed.value.path == f"/{ELSEWHERE_PULL_REQUEST.repository.api_path}"


def access_warning_on(site: RepositorySite) -> str:
    """
    :param site: A site built by :func:`unreadable_elsewhere_site`.
    :return: The warning an item on the repository it was refused shows.
    """
    repository = ELSEWHERE_PULL_REQUEST.repository
    return ItemClassifier.access_warning_of(
        repository, site.pull_request_source.read_failure_of(repository)
    )


def test_an_item_on_a_repository_the_build_cannot_read_shows_how_to_let_it(
    dataset_notes: NotesBranch, tmp_path: Path
):
    site = unreadable_elsewhere_site(dataset_notes)
    site.build(tmp_path)
    assert html.escape(access_warning_on(site)) in page_of(tmp_path, SitePlan.FIRST)


def test_build_reports_a_repository_it_cannot_read(
    dataset_notes: NotesBranch, tmp_path: Path, capsys: pytest.CaptureFixture
):
    site = unreadable_elsewhere_site(dataset_notes)
    site.build(tmp_path)
    assert (
        f"{NOTES_REPOSITORY}/{SitePlan.FIRST}: {access_warning_on(site)}"
        in capsys.readouterr().err
    )


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
