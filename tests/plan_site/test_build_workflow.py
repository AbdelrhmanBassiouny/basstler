"""
Tests for plan-site-build.yml, the reusable workflow that builds the plan site and
deploys it to the calling repository's Pages when a rendered page changed.
"""

from __future__ import annotations

from enum import StrEnum

import pytest

from basstler.environment import GitHubCredentialVariable
from basstler.plan_site.__main__ import SiteFile
from basstler.plan_site.workflows import BuildSecret

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


class BuildStep(StrEnum):
    """
    The identifiers of the build job's steps the tests read.
    """

    BUILD = "build"


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


# %% reading private notes


def test_the_build_accepts_an_optional_notes_token(build_workflow: Workflow):
    """
    A caller may pass the token, and one that does not still builds.
    """
    assert build_workflow.called_secrets == {BuildSecret.NOTES_TOKEN: False}


def test_the_build_reads_the_notes_with_the_notes_token_when_one_is_passed(
    build_workflow: Workflow,
):
    """
    The build reads with the passed token, else with the site repository's own.
    """
    build = build_workflow.jobs[PlanSiteBuildJob.BUILD].step_identified_as(
        BuildStep.BUILD
    )

    assert build.environment == {
        GitHubCredentialVariable.GH_TOKEN: (
            f"${{{{ secrets.{BuildSecret.NOTES_TOKEN} || github.token }}}}"
        )
    }


def test_git_fetches_the_notes_with_the_build_s_credential(build_workflow: Workflow):
    """
    Git authenticates through ``gh`` before the build fetches any notes branch.
    """
    build = build_workflow.jobs[PlanSiteBuildJob.BUILD].step_identified_as(
        BuildStep.BUILD
    )

    assert build.command.splitlines()[0] == "gh auth setup-git"
