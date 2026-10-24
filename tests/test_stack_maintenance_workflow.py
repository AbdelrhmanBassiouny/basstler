"""
The stack-maintenance workflow and the example caller a project copies to run it.
"""

from __future__ import annotations

import basstler.maintenance
from basstler.maintenance_commands import BoardCommand, UnattendedRunCommand

from .constants.paths import ExampleCaller, RepositoryLocation
from .workflow_document import PullRequestActivity, WorkflowDocument, WorkflowEvent

# %% the reusable workflow


def test_the_board_is_exported_before_the_report_is_run():
    """
    ``run-unattended`` derives its stack from ``board.json`` and consumes it, so the
    export that produces that file has to run first in the same job.
    """
    workflow = WorkflowDocument.read(RepositoryLocation.STACK_MAINTENANCE_WORKFLOW)
    script = workflow.only_job.script_of("Run the maintenance pass")

    module = basstler.maintenance.__name__
    board_export = script.index(f"{module} {BoardCommand.invoked_as} --write")
    unattended_run = script.index(f"{module} {UnattendedRunCommand.invoked_as}")

    assert board_export < unattended_run


# %% the example caller


def test_the_example_caller_runs_on_events_only():
    """
    The Actions budget allows no ``schedule``, so a pass starts on the pull request
    events that can change the stack, or by dispatch.
    """
    caller = WorkflowDocument.read(ExampleCaller.STACK_MAINTENANCE)

    assert caller.triggers == {
        WorkflowEvent.PULL_REQUEST: (
            PullRequestActivity.OPENED,
            PullRequestActivity.READY_FOR_REVIEW,
            PullRequestActivity.CLOSED,
        ),
        WorkflowEvent.WORKFLOW_DISPATCH: (),
    }


def test_the_example_caller_calls_this_workflow():
    call = WorkflowDocument.read(ExampleCaller.STACK_MAINTENANCE).only_job.call

    assert call.workflow.endswith(
        str(
            RepositoryLocation.STACK_MAINTENANCE_WORKFLOW.relative_to(
                RepositoryLocation.ROOT
            )
        )
    )
