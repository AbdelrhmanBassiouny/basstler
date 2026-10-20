"""
Tests for the workflows the ``/upstream-reviews`` skill dispatches.

The reusable workflow does the read; the dispatch-only workflow in this repository is
what lets a project that commits no workflow of its own still have the read run, by
naming its upstream and fork owner as inputs instead. Both are read as YAML rather than
run, since a runner is the one place these tests cannot reach.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

import yaml

from .constants.paths import RepositoryLocation


class UpstreamReviewsWorkflow(StrEnum):
    """
    The two workflow files, by name.
    """

    REUSABLE = "upstream-reviews.yml"
    """
    The workflow that installs the package and reads the upstream pull request.
    """

    DISPATCH = "upstream-reviews-dispatch.yml"
    """
    The dispatch-only caller in this repository, taking the upstream as an input.
    """

    def read(self) -> dict[str, Any]:
        """
        :return: The workflow, parsed.
        """
        return yaml.safe_load((RepositoryLocation.WORKFLOWS / self).read_text())

    def triggers(self) -> dict[str, Any]:
        """
        YAML 1.1 reads a bare ``on`` key as ``True``, so the trigger block is looked up
        under either spelling.

        :return: The workflow's ``on`` block.
        """
        workflow = self.read()
        return workflow.get("on", workflow.get(True))


class TargetInput(StrEnum):
    """
    The inputs naming which repositories a read is about.
    """

    UPSTREAM = "upstream"
    """
    The repository the pull request is reviewed on.
    """

    FORK_OWNER = "fork_owner"
    """
    The owner whose branches the read claims.
    """


REUSABLE_ONLY_INPUT = "basstler_ref"
"""
The reusable workflow's input its dispatch caller supplies itself rather than taking.
"""


def reusable_inputs() -> dict[str, Any]:
    """
    :return: Every input the reusable workflow declares, by name.
    """
    return UpstreamReviewsWorkflow.REUSABLE.triggers()["workflow_call"]["inputs"]


def dispatch_inputs() -> dict[str, Any]:
    """
    :return: Every input the dispatch workflow takes, by name.
    """
    return UpstreamReviewsWorkflow.DISPATCH.triggers()["workflow_dispatch"]["inputs"]


def dispatch_job() -> dict[str, Any]:
    """
    :return: The dispatch workflow's only job.
    """
    (job,) = UpstreamReviewsWorkflow.DISPATCH.read()["jobs"].values()
    return job


def reusable_run_script() -> str:
    """
    :return: Every ``run`` script of the reusable workflow's steps, joined.
    """
    (job,) = UpstreamReviewsWorkflow.REUSABLE.read()["jobs"].values()
    return "\n".join(step.get("run", "") for step in job["steps"])


def test_the_reusable_workflow_takes_the_upstream_and_fork_owner_as_optional_inputs():
    """
    A project caller still names neither, reading its committed configuration instead.
    """
    inputs = reusable_inputs()

    assert [inputs[name].get("required", False) for name in TargetInput] == [
        False,
        False,
    ]


def test_the_reusable_workflow_hands_each_target_input_to_the_reader():
    script = reusable_run_script()

    for name in TargetInput:
        assert f"inputs.{name}" in script
    assert "--upstream" in script
    assert "--fork-owner" in script


def test_the_dispatch_workflow_takes_every_input_its_caller_does_not_supply():
    assert set(dispatch_inputs()) == set(reusable_inputs()) - {REUSABLE_ONLY_INPUT}


def test_the_dispatch_workflow_requires_the_repositories_it_cannot_infer():
    """
    It runs in this repository, so neither the project's committed upstream nor the
    runner's own owner says anything about the fork being read.
    """
    inputs = dispatch_inputs()

    assert all(inputs[name]["required"] for name in TargetInput)


def test_the_dispatch_workflow_calls_the_reusable_workflow_in_this_repository():
    assert dispatch_job()["uses"] == (
        f"./{RepositoryLocation.WORKFLOWS.value.relative_to(RepositoryLocation.ROOT.value)}"
        f"/{UpstreamReviewsWorkflow.REUSABLE}"
    )


def test_the_dispatch_workflow_hands_every_reusable_input_on():
    assert set(dispatch_job()["with"]) == set(reusable_inputs())


def test_the_dispatch_workflow_grants_no_more_than_the_reusable_workflow_needs():
    assert UpstreamReviewsWorkflow.DISPATCH.read()["permissions"] == (
        UpstreamReviewsWorkflow.REUSABLE.read()["permissions"]
    )


def test_the_skill_dispatches_the_workflow_this_repository_holds():
    skill = (
        RepositoryLocation.PLUGIN / "skills" / "upstream-reviews" / "SKILL.md"
    ).read_text()

    assert UpstreamReviewsWorkflow.DISPATCH in skill
    assert (RepositoryLocation.WORKFLOWS / UpstreamReviewsWorkflow.DISPATCH).is_file()
