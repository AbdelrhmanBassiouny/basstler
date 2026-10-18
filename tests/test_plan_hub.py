"""
Tests for plan_hub.py: the hub file, and gathering every registered repository's plans.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from basstler.build_hub import RepositorySummary, render_hub_page
from basstler.plan_hub import (
    HubDefault,
    HubUrlConflictError,
    PlanHub,
    gather,
    set_hub_url,
)

REGISTRY = "owner/registry"

OTHER_REPOSITORY = "owner/other"

HUB_URL = "https://claude.ai/artifact/hub"

PLAN_MANIFEST = """\
title: First plan
description: What the first plan is for.
items:
- id: a
  status: done
- id: b
  status: in_progress
"""

DASHBOARD_URLS = """\
_index: https://claude.ai/artifact/index
first-plan: https://claude.ai/artifact/first
"""


def publish_notes(remote: Path, files: dict[str, str]) -> None:
    """
    Create a bare repository at ``remote`` whose notes branch holds ``files``.

    :param remote: Where the bare repository goes.
    :param files: File contents, keyed by their path inside the plans directory.
    """
    work = remote.with_suffix(".work")
    subprocess.run(["git", "init", "--quiet", str(work)], check=True)
    for relative_path, content in files.items():
        path = work / HubDefault.PLANS_DIRECTORY.value / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    for command in (
        ["add", "--all"],
        ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "--quiet", "-m", "n"],
        ["push", "--quiet", str(remote), f"HEAD:{HubDefault.NOTES_BRANCH.value}"],
    ):
        subprocess.run(["git", "-C", str(work), *command], check=True)


@pytest.fixture
def remotes(tmp_path: Path) -> Path:
    """
    A directory standing in for GitHub, holding the registry's notes.
    """
    registry = tmp_path / f"{REGISTRY}.git"
    registry.parent.mkdir(parents=True)
    subprocess.run(["git", "init", "--quiet", "--bare", str(registry)], check=True)
    publish_notes(
        registry,
        {
            "first-plan/plan.yaml": PLAN_MANIFEST,
            "first-plan/roadmap.md": "# first\n",
            "_hub.yaml": "url: null\n",
            HubDefault.DASHBOARD_URL_CACHE.value: DASHBOARD_URLS,
        },
    )
    return tmp_path


# %% the hub file


def test_register_lists_a_repository_once():
    hub = PlanHub(registry=REGISTRY)

    assert hub.register(REGISTRY)
    assert not hub.register(REGISTRY)
    assert hub.repositories == [REGISTRY]


def test_the_hub_file_round_trips(tmp_path: Path):
    hub = PlanHub(registry=REGISTRY, repositories=[REGISTRY], url=HUB_URL)
    path = tmp_path / "hub.yaml"
    path.write_text(hub.to_text())

    assert PlanHub.load(path) == hub


def test_a_missing_hub_file_loads_as_none(tmp_path: Path):
    assert PlanHub.load(tmp_path / "hub.yaml") is None


def test_set_hub_url_records_the_first_url():
    hub = PlanHub(registry=REGISTRY)

    assert set_hub_url(hub, HUB_URL)
    assert not set_hub_url(hub, HUB_URL)
    assert hub.url == HUB_URL


def test_set_hub_url_never_replaces_a_recorded_url():
    hub = PlanHub(registry=REGISTRY, url=HUB_URL)

    with pytest.raises(HubUrlConflictError):
        set_hub_url(hub, "https://claude.ai/artifact/second")


# %% gathering


def test_gather_reads_each_repository_plans_and_index(remotes: Path):
    hub = PlanHub(registry=REGISTRY, repositories=[REGISTRY])

    (entry,) = gather(hub, f"{remotes}/{{repository}}.git")

    assert entry["repository"] == REGISTRY
    assert entry["index_url"] == "https://claude.ai/artifact/index"
    assert entry["plans"] == [
        {
            "id": "first-plan",
            "title": "First plan",
            "description": "What the first plan is for.",
            "done": 1,
            "total": 2,
            "dashboard_url": "https://claude.ai/artifact/first",
        }
    ]


def test_gather_reports_a_repository_it_cannot_fetch(remotes: Path):
    hub = PlanHub(registry=REGISTRY, repositories=[REGISTRY, OTHER_REPOSITORY])

    entries = gather(hub, f"{remotes}/{{repository}}.git")

    assert entries[1]["repository"] == OTHER_REPOSITORY
    assert entries[1]["plans"] == []
    assert entries[1]["error"]


# %% rendering


def test_the_hub_page_opens_each_repository_index_not_its_plans(remotes: Path):
    hub = PlanHub(registry=REGISTRY, repositories=[REGISTRY])
    repositories = [
        RepositorySummary.from_mapping(entry)
        for entry in gather(hub, f"{remotes}/{{repository}}.git")
    ]

    page = render_hub_page(repositories)

    assert "https://claude.ai/artifact/index" in page
    assert "https://claude.ai/artifact/first" not in page
