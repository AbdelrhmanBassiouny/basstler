"""
Tests for plan_site_workflows.py: the notes branch's trigger starting the plan site's
build, the default branch's workflow running that build, and installing the trigger.
"""

from __future__ import annotations

import shlex
from pathlib import PurePosixPath
from typing import Any

import yaml

from basstler.locations import PackageLocation, ProjectLocation
from basstler.personal_notes_branch import NotesWriteOutcome
from basstler.plan_site_workflows import PlanSiteTrigger

from .constants.notes import ScratchBranch

# %% reading workflows


def workflow_events(workflow: dict[Any, Any]) -> dict[str, Any]:
    """
    :param workflow: A parsed workflow file.
    :return: The events it runs on; YAML 1.1 reads the ``on`` key as ``True``.
    """
    return workflow[True]


def repository_workflow(path: ProjectLocation) -> dict[Any, Any]:
    """
    :param path: A workflow of this repository.
    :return: The parsed workflow.
    """
    return yaml.safe_load((PackageLocation.SOURCE_TREE / path).read_text())


# %% the trigger


def test_the_trigger_runs_only_on_plan_pushes_to_its_notes_branch():
    workflow = yaml.safe_load(PlanSiteTrigger(ScratchBranch.PERSONAL_NOTES).workflow)
    assert workflow_events(workflow) == {
        "push": {
            "branches": [ScratchBranch.PERSONAL_NOTES],
            "paths": [f"{ProjectLocation.PLANS.as_posix()}/**"],
        }
    }


def test_the_trigger_starts_the_workflow_publishing_the_site():
    workflow = yaml.safe_load(PlanSiteTrigger(ScratchBranch.PERSONAL_NOTES).workflow)
    (step,) = workflow["jobs"]["dispatch"]["steps"]
    command = shlex.split(step["run"])
    assert command[:4] == [
        "gh",
        "workflow",
        "run",
        ProjectLocation.PLAN_SITE_WORKFLOW.name,
    ]


# %% the site workflow


def test_the_site_workflow_runs_the_reusable_build():
    workflow = repository_workflow(ProjectLocation.PLAN_SITE_WORKFLOW)
    (job,) = workflow["jobs"].values()
    assert job["uses"] == f"./{ProjectLocation.PLAN_SITE_BUILD_WORKFLOW.as_posix()}"


def test_the_build_is_a_reusable_workflow():
    workflow = repository_workflow(ProjectLocation.PLAN_SITE_BUILD_WORKFLOW)
    assert "workflow_call" in workflow_events(workflow)


# %% installing


def test_installing_pushes_the_trigger_to_the_notes_branch(notes_repository):
    trigger = PlanSiteTrigger(ScratchBranch.PERSONAL_NOTES)
    outcome = trigger.install(notes_repository.personal_notes_branch())
    published = notes_repository.published_notes_file(
        PurePosixPath(ProjectLocation.PLAN_SITE_TRIGGER_WORKFLOW.as_posix())
    )
    assert outcome is NotesWriteOutcome.PUSHED
    assert published == f"{trigger.workflow}\n"


def test_installing_an_installed_trigger_pushes_nothing(notes_repository):
    trigger = PlanSiteTrigger(ScratchBranch.PERSONAL_NOTES)
    trigger.install(notes_repository.personal_notes_branch())
    assert (
        trigger.install(notes_repository.personal_notes_branch())
        is NotesWriteOutcome.UNCHANGED
    )
