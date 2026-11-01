"""
Tests for plan_site/hub.py: the hub file, and reading a listed repository's notes
branch.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from basstler.locations import ProjectLocation
from basstler.maintenance.git_commands import GitCommandRunner
from basstler.plan_site.exceptions import RegistryUnreadableError
from basstler.dashboard.plan import Item
from basstler.plan_site.hub import HubCommand, NotesBranch, PlanHub, SiteAddress, main
from basstler.plan.model import PlanDocument
from basstler.repository import Repository
from basstler.setup.steps import PersonalNotesSetting

from ..constants.site import SitePlan, SiteRepository, SiteSampleText
from ..fixture_plans import ForeignItemId

REGISTRY = SiteRepository.NOTES.value
"""
The repository whose notes hold the hub file under test.
"""

PLAN_MANIFEST = SitePlan.FIRST.directory / PlanDocument.MANIFEST
"""
The manifest a published notes branch carries.
"""


def publish_notes(remote_root: Path, repository: Repository, files: dict[Path, str]):
    """
    Create a bare repository standing in for one on GitHub, whose notes branch holds
    ``files``.

    :param remote_root: The directory standing in for GitHub, as
        :meth:`Repository.clone_url_under` takes it.
    :param repository: The repository to create under it.
    :param files: File contents, keyed by their path inside the plans directory.
    """
    remote = Path(repository.clone_url_under(str(remote_root)))
    work = remote.with_suffix(".work")
    for directory in (remote, work):
        directory.mkdir(parents=True)
        GitCommandRunner(directory).run("init", "--quiet")
    GitCommandRunner(remote).run("config", "core.bare", "true")
    for relative_path, content in files.items():
        path = work / ProjectLocation.PLANS / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    git = GitCommandRunner(work)
    git.run("add", "--all")
    git.run(
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@t",
        "commit",
        "--quiet",
        "--allow-empty",
        "-m",
        "n",
    )
    git.run(
        "push", "--quiet", str(remote), f"HEAD:{PersonalNotesSetting.BRANCH.default}"
    )


# %% the hub file


def test_register_lists_a_repository_once():
    hub = PlanHub(registry=str(REGISTRY))

    assert hub.register(str(REGISTRY))
    assert not hub.register(str(REGISTRY))
    assert hub.repositories == [str(REGISTRY)]


def test_the_hub_file_round_trips(tmp_path: Path):
    hub = PlanHub(
        registry=str(REGISTRY),
        repositories=[str(REGISTRY)],
        site_url=SiteSampleText.SITE_URL.value,
    )
    path = tmp_path / ProjectLocation.PLAN_HUB.name
    path.write_text(hub.to_text())

    assert PlanHub.load(path) == hub


def test_a_missing_hub_file_loads_as_none(tmp_path: Path):
    assert PlanHub.load(tmp_path / ProjectLocation.PLAN_HUB.name) is None


def test_the_hub_file_is_read_off_the_registry_notes_branch(tmp_path: Path):
    hub = PlanHub(registry=str(REGISTRY), repositories=[str(REGISTRY)])
    publish_notes(
        tmp_path, REGISTRY, {Path(ProjectLocation.PLAN_HUB.name): hub.to_text()}
    )

    assert PlanHub.from_registry(REGISTRY, str(tmp_path)) == hub


def test_a_registry_without_a_hub_file_reads_as_none(tmp_path: Path):
    publish_notes(tmp_path, REGISTRY, {})

    assert PlanHub.from_registry(REGISTRY, str(tmp_path)) is None


def test_a_registry_whose_notes_cannot_be_fetched_is_refused(tmp_path: Path):
    with pytest.raises(RegistryUnreadableError) as refused:
        PlanHub.from_registry(SiteRepository.MISSING.value, str(tmp_path))
    assert refused.value.registry == SiteRepository.MISSING.value


# %% a listed repository's notes


def test_a_fetched_notes_branch_reads_and_checks_out_its_plans(tmp_path: Path):
    manifest_path = Path(SitePlan.FIRST) / PlanDocument.MANIFEST
    publish_notes(tmp_path, REGISTRY, {manifest_path: PLAN_MANIFEST.read_text()})

    notes = NotesBranch.fetch(
        REGISTRY,
        PersonalNotesSetting.BRANCH.default,
        str(tmp_path),
        tmp_path / "scratch",
    )
    plans_directory = notes.check_out_plans()

    assert notes.read(ProjectLocation.PLANS / manifest_path) == (
        PLAN_MANIFEST.read_text().strip()
    )
    assert (plans_directory / manifest_path).read_text() == PLAN_MANIFEST.read_text()


def test_a_repository_that_cannot_be_fetched_reads_as_none(tmp_path: Path):
    notes = NotesBranch.fetch(
        SiteRepository.MISSING.value,
        PersonalNotesSetting.BRANCH.default,
        str(tmp_path),
        tmp_path / "scratch",
    )

    assert notes is None


# %% the address of every page on the site

SITE = SiteAddress(SiteSampleText.SITE_URL.value)
"""
The site under test's address.
"""


def test_every_page_address_joins_the_site_address_whether_or_not_it_ends_in_a_slash():
    without_slash = SiteAddress(SiteSampleText.SITE_URL.rstrip("/"))

    assert without_slash.plan_url(REGISTRY, SitePlan.FIRST) == SITE.plan_url(
        REGISTRY, SitePlan.FIRST
    )
    assert SITE.plan_url(REGISTRY, SitePlan.FIRST) == (
        f"{SiteSampleText.SITE_URL}{REGISTRY}/{SitePlan.FIRST}/"
    )


def test_a_plan_page_sits_under_its_repository_page():
    assert SITE.plan_url(REGISTRY, SitePlan.FIRST) == (
        f"{SITE.repository_url(REGISTRY)}{SitePlan.FIRST}/"
    )


def test_an_item_address_names_its_card_on_the_plan_page():
    assert SITE.item_url(REGISTRY, SitePlan.FIRST, ForeignItemId.READY) == (
        f"{SITE.plan_url(REGISTRY, SitePlan.FIRST)}#{Item.anchor_of(ForeignItemId.READY)}"
    )


def write_hub(directory: Path, site_url: str | None) -> Path:
    """
    :param directory: Where to write the hub file.
    :param site_url: The site address it names.
    :return: The written hub file.
    """
    path = directory / ProjectLocation.PLAN_HUB.name
    path.write_text(PlanHub(registry=str(REGISTRY), site_url=site_url).to_text())
    return path


def run_page_url(
    monkeypatch: pytest.MonkeyPatch, hub_path: Path, *arguments: str
) -> int:
    """
    Run the hub command's page address subcommand in process.

    :param hub_path: The hub file it reads.
    :param arguments: The page's arguments after the hub file and repository.
    :return: The command's exit status.
    """
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "hub",
            HubCommand.PAGE_URL,
            f"--hub={hub_path}",
            f"--repository={REGISTRY}",
            *arguments,
        ],
    )
    return main()


def test_the_page_url_command_prints_a_plan_page_address(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    hub_path = write_hub(tmp_path, SiteSampleText.SITE_URL.value)

    status = run_page_url(monkeypatch, hub_path, f"--plan={SitePlan.FIRST}")

    assert status == 0
    assert capsys.readouterr().out.strip() == SITE.plan_url(REGISTRY, SitePlan.FIRST)


def test_the_page_url_command_prints_an_item_address(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    hub_path = write_hub(tmp_path, SiteSampleText.SITE_URL.value)

    run_page_url(
        monkeypatch,
        hub_path,
        f"--plan={SitePlan.FIRST}",
        f"--item={ForeignItemId.READY}",
    )

    assert capsys.readouterr().out.strip() == SITE.item_url(
        REGISTRY, SitePlan.FIRST, ForeignItemId.READY
    )


def test_the_page_url_command_prints_the_repository_page_without_a_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    hub_path = write_hub(tmp_path, SiteSampleText.SITE_URL.value)

    run_page_url(monkeypatch, hub_path)

    assert capsys.readouterr().out.strip() == SITE.repository_url(REGISTRY)


def test_the_page_url_command_fails_when_the_hub_names_no_site(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    hub_path = write_hub(tmp_path, None)

    status = run_page_url(monkeypatch, hub_path, f"--plan={SitePlan.FIRST}")

    assert status != 0
    assert capsys.readouterr().out == ""
