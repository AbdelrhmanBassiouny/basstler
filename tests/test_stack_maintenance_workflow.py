"""
The one thing about the stack-maintenance workflow worth asserting from code.

The pass reads ``board.json`` and deletes it once it concludes - see
``RunReportCommand.perform``'s own docstring - so a caller who invokes it without first
exporting a board fails with :class:`stack.BoardUnavailable` every time, never only on a
second run. That ordering lives in a YAML string a reviewer has to read carefully to
verify; this test reads it back the same way the shell would, so a future edit that
drops or reorders the export step fails here instead of in the next scheduled run.
"""

from __future__ import annotations

import yaml

import basstler.maintenance
from basstler.locations import CheckoutLocation
from basstler.maintenance_commands import BoardCommand, UnattendedRunCommand

from .constants import (
    RepositoryLocation,
    StackMaintenancePullRequestType,
    StackMaintenanceTrigger,
)

STACK_MAINTENANCE_WORKFLOW = RepositoryLocation.WORKFLOWS / "stack-maintenance.yml"
"""
The workflow document that runs the maintenance pass unattended.
"""


def _maintenance_pass_run_script() -> str:
    """:return: The shell script of the step that runs the maintenance pass."""
    document = yaml.safe_load(STACK_MAINTENANCE_WORKFLOW.read_text())
    steps = document["jobs"]["maintain"]["steps"]
    step = next(
        step for step in steps if step.get("name") == "Run the maintenance pass"
    )
    return step["run"]


def test_the_board_is_exported_before_the_report_is_run():
    """
    ``run-report`` derives its stack from ``board.json`` and consumes it, so the export
    that produces that file has to run first in the same job.
    """
    script = _maintenance_pass_run_script()

    module = basstler.maintenance.__name__
    board_export = script.index(f"{module} {BoardCommand.invoked_as} --write")
    unattended_run = script.index(f"{module} {UnattendedRunCommand.invoked_as}")

    assert board_export < unattended_run


def _example_caller_triggers() -> dict:
    """:return: The example caller's ``on`` table, which YAML 1.1 reads as ``True``."""
    document = yaml.safe_load(
        (
            RepositoryLocation.ROOT / CheckoutLocation.STACK_MAINTENANCE_CALLER
        ).read_text()
    )
    return document[True]


def test_the_example_caller_runs_on_events_only():
    """
    The Actions budget allows no ``schedule``, so a pass starts on the pull request
    events that can change the stack, or by dispatch.
    """
    triggers = _example_caller_triggers()

    assert set(triggers) == set(StackMaintenanceTrigger)
    assert set(triggers[StackMaintenanceTrigger.PULL_REQUEST]["types"]) == set(
        StackMaintenancePullRequestType
    )


def test_the_example_caller_calls_this_workflow():
    caller = (
        RepositoryLocation.ROOT / CheckoutLocation.STACK_MAINTENANCE_CALLER
    ).read_text()

    assert f"/.github/workflows/{STACK_MAINTENANCE_WORKFLOW.name}@" in caller
