"""
Tests for plan-site-build.yml, the reusable workflow that builds the plan site and
deploys it to the calling repository's Pages when a rendered page changed.
"""

from __future__ import annotations

from typing import Any

import pytest
import yaml

from basstler.build_site import SiteFile
from basstler.locations import PackageLocation, ProjectLocation

# %% reading the workflow


@pytest.fixture
def build_workflow() -> dict[Any, Any]:
    """
    The parsed reusable build workflow.
    """
    return yaml.safe_load(
        (
            PackageLocation.SOURCE_TREE / ProjectLocation.PLAN_SITE_BUILD_WORKFLOW
        ).read_text()
    )


def step_using(job: dict[str, Any], action: str) -> dict[str, Any]:
    """
    :param job: A parsed workflow job.
    :param action: The action a step of the job uses, without its version.
    :return: That step.
    """
    (step,) = (
        step
        for step in job["steps"]
        if step.get("uses", "").partition("@")[0] == action
    )
    return step


# %% the build


def test_the_build_is_a_reusable_workflow(build_workflow: dict[Any, Any]):
    # YAML 1.1 reads the ``on`` key as ``True``.
    assert "workflow_call" in build_workflow[True]


def test_the_build_compares_the_built_site_s_digest_with_the_published_one(
    build_workflow: dict[Any, Any],
):
    build = build_workflow["jobs"]["build"]
    (site_changed,) = build["outputs"].values()
    step_identifier = site_changed.split(".")[1]
    (compare,) = (step for step in build["steps"] if step.get("id") == step_identifier)
    assert SiteFile.DIGEST in compare["run"]


def test_the_build_uploads_and_deploys_only_a_changed_site(
    build_workflow: dict[Any, Any],
):
    jobs = build_workflow["jobs"]
    ((output_name, site_changed),) = jobs["build"]["outputs"].items()
    changed = site_changed.removeprefix("${{").removesuffix("}}").strip()
    upload = step_using(jobs["build"], "actions/upload-pages-artifact")
    assert upload["if"] == f"{changed} == 'true'"
    assert jobs["deploy"]["if"] == f"needs.build.outputs.{output_name} == 'true'"
