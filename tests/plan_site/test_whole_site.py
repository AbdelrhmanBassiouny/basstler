"""
Tests that build the whole plan site from the test dataset, the way the site build
workflow does: the hub file read off the registry, every listed repository fetched.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from basstler.plan_site.__main__ import HubSite, SiteFile, main
from basstler.plan_site.exceptions import RegistryUnreadableError
from basstler.plan_site.hub import PlanHub, SiteAddress
from basstler.locations import ProjectLocation

from ..constants.paths import DatasetLocation
from ..constants.site import SitePlan, SiteRepository, SiteSampleText
from ..recorded_pull_requests import RecordedPullRequestSource
from .test_build_site import PUBLISHED_PLANS
from .test_hub import publish_notes

# %% the whole site from the dataset


@pytest.fixture
def remotes(tmp_path: Path) -> Path:
    """
    A directory standing in for GitHub: the notes repository carries the dataset's plans
    and a hub file listing it and a repository that does not exist.
    """
    remote_root = tmp_path / "remotes"
    hub = PlanHub(
        registry=str(SiteRepository.NOTES.value),
        repositories=[str(repository.value) for repository in SiteRepository],
        site_url=SiteSampleText.SITE_URL.value,
    )
    plans = {
        path.relative_to(DatasetLocation.SITE_PLANS.value): path.read_text()
        for path in DatasetLocation.SITE_PLANS.value.rglob("*")
        if path.is_file()
    }
    hub_path = ProjectLocation.PLAN_HUB.relative_to(ProjectLocation.PLANS)
    publish_notes(
        remote_root, SiteRepository.NOTES.value, {**plans, hub_path: hub.to_text()}
    )
    return remote_root


@pytest.fixture
def built_site(remotes: Path, tmp_path: Path) -> Path:
    """
    The site built from the hub file the registry's notes carry.
    """
    hub = PlanHub.from_registry(SiteRepository.NOTES.value, str(remotes))
    output = tmp_path / "site"
    HubSite(
        address=SiteAddress(hub.site_url),
        pull_request_source=RecordedPullRequestSource(),
        hub=hub,
        remote_root=str(remotes),
    ).build(output)
    return output


def test_the_site_publishes_the_hub_every_index_and_every_valid_plan(built_site: Path):
    repository = Path(str(SiteRepository.NOTES.value))
    pages = {
        Path(SiteFile.PAGE),
        repository / SiteFile.PAGE,
        *(repository / plan / SiteFile.PAGE for plan in PUBLISHED_PLANS),
    }
    written = {
        path.relative_to(built_site) for path in built_site.rglob("*") if path.is_file()
    }
    assert written == {
        *pages,
        Path(SiteFile.STYLESHEET),
        Path(SiteFile.NO_JEKYLL),
        Path(SiteFile.DIGEST),
    }


def test_the_hub_names_the_plan_and_the_repository_the_build_left_out(
    built_site: Path,
):
    hub_page = (built_site / SiteFile.PAGE).read_text()
    assert f"{SiteRepository.NOTES.value}/{SitePlan.BROKEN}" in hub_page
    assert str(SiteRepository.MISSING.value) in hub_page


# %% a registry that cannot be read


def test_the_build_fails_when_the_registry_cannot_be_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    arguments = [
        "plan_site",
        f"--registry={SiteRepository.MISSING.value}",
        f"--output={tmp_path / 'site'}",
        f"--remote-root={tmp_path}",
    ]
    monkeypatch.setattr(sys, "argv", arguments)
    with pytest.raises(RegistryUnreadableError):
        main()
