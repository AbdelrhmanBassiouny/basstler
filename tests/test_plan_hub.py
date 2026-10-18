"""
Tests for plan_hub.py: the hub file, and reading a listed repository's notes branch.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from basstler.plan_hub import HubDefault, NotesBranch, PlanHub

REGISTRY = "owner/registry"

SITE_URL = "https://owner.github.io/site/"

PLAN_MANIFEST = "title: First plan\nitems: []\n"


def publish_notes(remote: Path, files: dict[str, str]) -> None:
    """
    Create a bare repository at ``remote`` whose notes branch holds ``files``.

    :param remote: Where the bare repository goes.
    :param files: File contents, keyed by their path inside the plans directory.
    """
    work = remote.with_suffix(".work")
    subprocess.run(["git", "init", "--quiet", str(work)], check=True)
    subprocess.run(["git", "init", "--quiet", "--bare", str(remote)], check=True)
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


# %% the hub file


def test_register_lists_a_repository_once():
    hub = PlanHub(registry=REGISTRY)

    assert hub.register(REGISTRY)
    assert not hub.register(REGISTRY)
    assert hub.repositories == [REGISTRY]


def test_the_hub_file_round_trips(tmp_path: Path):
    hub = PlanHub(registry=REGISTRY, repositories=[REGISTRY], site_url=SITE_URL)
    path = tmp_path / "hub.yaml"
    path.write_text(hub.to_text())

    assert PlanHub.load(path) == hub


def test_a_missing_hub_file_loads_as_none(tmp_path: Path):
    assert PlanHub.load(tmp_path / "hub.yaml") is None


# %% a listed repository's notes


def test_a_fetched_notes_branch_reads_and_exports_its_plans(tmp_path: Path):
    publish_notes(tmp_path / f"{REGISTRY}.git", {"first-plan/plan.yaml": PLAN_MANIFEST})

    notes = NotesBranch.fetch(
        REGISTRY,
        HubDefault.NOTES_BRANCH.value,
        f"{tmp_path}/{{repository}}.git",
        tmp_path / "scratch",
    )
    plans_directory = notes.export_plans(tmp_path / "checkout")

    assert notes.read("first-plan/plan.yaml") == PLAN_MANIFEST
    assert (plans_directory / "first-plan" / "plan.yaml").read_text() == PLAN_MANIFEST


def test_a_repository_that_cannot_be_fetched_reads_as_none(tmp_path: Path):
    notes = NotesBranch.fetch(
        "owner/missing",
        HubDefault.NOTES_BRANCH.value,
        f"{tmp_path}/{{repository}}.git",
        tmp_path / "scratch",
    )

    assert notes is None
