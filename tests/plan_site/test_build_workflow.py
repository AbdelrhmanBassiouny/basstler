"""
Tests for plan-site-build.yml, the reusable workflow that builds the plan site and
deploys it to the calling repository's Pages when a rendered page changed.
"""

from __future__ import annotations

from enum import StrEnum

import pytest

from basstler.plan_site.__main__ import SiteFile

from ..constants.paths import RepositoryLocation
from ..workflow_definition import Workflow, WorkflowTrigger

# %% reading the workflow


class PlanSiteBuildJob(StrEnum):
    """
    The build workflow's jobs.
    """

    BUILD = "build"
    DEPLOY = "deploy"


class PagesAction(StrEnum):
    """
    The Pages actions the build workflow uses.
    """

    UPLOAD = "actions/upload-pages-artifact"


@pytest.fixture
def build_workflow() -> Workflow:
    """
    The parsed reusable build workflow.
    """
    return Workflow.read(RepositoryLocation.PLAN_SITE_BUILD_WORKFLOW)


# %% the build


def test_the_build_is_a_reusable_workflow(build_workflow: Workflow):
    assert WorkflowTrigger.WORKFLOW_CALL in build_workflow.triggers


def test_the_build_compares_the_built_site_s_digest_with_the_published_one(
    build_workflow: Workflow,
):
    build = build_workflow.jobs[PlanSiteBuildJob.BUILD]
    (site_changed,) = build.outputs.values()
    compare = build.step_identified_as(site_changed.step_identifier)
    assert SiteFile.DIGEST in compare.command


def test_the_build_uploads_and_deploys_only_a_changed_site(build_workflow: Workflow):
    build = build_workflow.jobs[PlanSiteBuildJob.BUILD]
    ((output_name, site_changed),) = build.outputs.items()
    assert build.step_using(PagesAction.UPLOAD).condition == site_changed.true_condition
    assert (
        build_workflow.jobs[PlanSiteBuildJob.DEPLOY].condition
        == build.output(output_name).true_condition
    )


def test_a_build_waits_for_the_running_one_instead_of_cancelling_it(
    build_workflow: Workflow,
):
    assert build_workflow.concurrency.cancel_in_progress is False
