"""
Tests for the item-bootstrap command line.
"""

from __future__ import annotations

import json
import subprocess

from basstler.plan.item_bootstrap.commands import BootstrapCommand
from basstler.plan.item_bootstrap.vocabulary import PlanItemBootstrapExitCode, ReportKey
from basstler.plan.model import (
    ItemStatus,
    ManifestKey,
)

from ...scratch_repository import ScratchRepository
from ...script_runner import PythonModuleRunner
from .bootstrap_scenario import (
    BOOTSTRAP_MODULE,
    CONFLICT_REASON,
    EXISTING_ITEM,
    NEW_BRANCH,
    NO_PLANS_BRANCH,
    OWNER,
    PLAN_IDENTIFIER,
    SECOND_ITEM,
    an_entry_over_the_length_limit,
    publish_the_branch_index,
    published_items,
    second_item_branch,
    the_length_violation_of,
    update_request,
)

# %% the command line


def run_bootstrap(
    repository: ScratchRepository, *arguments: str
) -> subprocess.CompletedProcess[str]:
    """
    Run the scratch layout's copy of this module with *arguments*.

    :param repository: A fixture-built scratch repository.
    :param arguments: CLI arguments to pass.
    :return: The finished subprocess.
    """
    return PythonModuleRunner(
        project_root=repository.project_root, module_name=BOOTSTRAP_MODULE
    ).run(*arguments)


def record_arguments(plan: str = PLAN_IDENTIFIER, *extra: str) -> list[str]:
    """
    The command line for recording the existing item.

    :param plan: The plan to record against.
    :param extra: Further arguments, appended as given.
    :return: The arguments.
    """
    return [
        "record",
        "--plan",
        plan,
        "--item",
        EXISTING_ITEM,
        "--status",
        ItemStatus.IN_PROGRESS.value,
        *extra,
    ]


def test_the_record_subcommand_reports_status_and_exit_code_first(
    bootstrap_repository: ScratchRepository,
):

    result = run_bootstrap(bootstrap_repository, *record_arguments())

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert list(report)[:2] == [ReportKey.STATUS, ReportKey.EXIT_CODE]
    assert (
        report[ReportKey.STATUS] == PlanItemBootstrapExitCode.SUCCESS.name_for_a_caller
    )
    assert report[ReportKey.EXIT_CODE] == PlanItemBootstrapExitCode.SUCCESS


def test_the_command_line_names_the_status_it_failed_with(
    bootstrap_repository: ScratchRepository,
):

    result = run_bootstrap(bootstrap_repository, *record_arguments(plan="no-such-plan"))

    assert result.returncode == PlanItemBootstrapExitCode.UNKNOWN_PLAN
    assert PlanItemBootstrapExitCode.UNKNOWN_PLAN.name_for_a_caller in result.stderr


def test_the_command_line_prints_why_the_plan_save_refused(
    bootstrap_repository: ScratchRepository,
):
    entry = an_entry_over_the_length_limit()

    result = run_bootstrap(
        bootstrap_repository,
        *record_arguments(PLAN_IDENTIFIER, "--roadmap-entry", entry),
    )

    assert result.returncode == PlanItemBootstrapExitCode.PLAN_SAVE_REFUSED
    assert str(the_length_violation_of(entry)) in result.stderr


def test_the_dashboard_republish_is_handed_back_rather_than_attempted(
    bootstrap_repository: ScratchRepository,
):

    result = run_bootstrap(bootstrap_repository, *record_arguments())

    report = json.loads(result.stdout)
    assert report[ReportKey.DASHBOARD_COMMAND] == f"/plan-dashboard {PLAN_IDENTIFIER}"


def test_the_update_subcommand_writes_a_note_from_a_file(
    bootstrap_repository: ScratchRepository,
):
    note = bootstrap_repository.write("note.md", "What the run found.\n")

    result = run_bootstrap(
        bootstrap_repository,
        "update",
        "--plan",
        PLAN_IDENTIFIER,
        "--item",
        EXISTING_ITEM,
        "--status",
        ItemStatus.BLOCKED.value,
        "--notes",
        str(note),
    )

    assert result.returncode == PlanItemBootstrapExitCode.SUCCESS, result.stderr
    item = published_items(bootstrap_repository)[EXISTING_ITEM]
    assert item[ManifestKey.NOTES.key] == "What the run found.\n"
    assert item[ManifestKey.STATUS.key] == ItemStatus.BLOCKED


def test_replacing_a_note_and_extending_it_cannot_be_asked_for_at_once(
    bootstrap_repository: ScratchRepository,
):
    note = bootstrap_repository.write("note.md", "Replaces it.\n")
    addition = bootstrap_repository.write("addition.md", "Extends it.\n")

    result = run_bootstrap(
        bootstrap_repository,
        "update",
        "--plan",
        PLAN_IDENTIFIER,
        "--item",
        EXISTING_ITEM,
        "--notes",
        str(note),
        "--append-notes",
        str(addition),
    )

    assert result.returncode == PlanItemBootstrapExitCode.USAGE
    assert "--append-notes" in result.stderr


def test_the_check_subcommand_exits_stale_and_names_the_field(
    bootstrap_repository: ScratchRepository,
):
    update_request(values_by_key={ManifestKey.BRANCH: NEW_BRANCH}).update(
        bootstrap_repository.project_root
    )

    result = run_bootstrap(
        bootstrap_repository,
        "check",
        "--plan",
        PLAN_IDENTIFIER,
        "--item",
        EXISTING_ITEM,
    )

    assert result.returncode == PlanItemBootstrapExitCode.MANIFEST_IS_STALE
    report = json.loads(result.stdout)
    assert list(report)[:2] == [ReportKey.STATUS, ReportKey.EXIT_CODE]
    assert [finding[ReportKey.FIELD] for finding in report[ReportKey.FINDINGS]] == [
        ManifestKey.BRANCH.key
    ]


def test_the_resolve_subcommand_names_the_plan_and_items_a_branch_carries(
    bootstrap_repository: ScratchRepository,
):
    publish_the_branch_index(bootstrap_repository)

    result = run_bootstrap(
        bootstrap_repository, "resolve", "--branch", second_item_branch()
    )

    assert result.returncode == PlanItemBootstrapExitCode.SUCCESS
    report = json.loads(result.stdout)
    assert report[ReportKey.PLAN] == PLAN_IDENTIFIER
    assert [item[ReportKey.ITEM] for item in report[ReportKey.ITEMS]] == [SECOND_ITEM]


def test_the_block_subcommand_exits_on_a_branch_that_belongs_to_no_plan(
    bootstrap_repository: ScratchRepository,
):
    publish_the_branch_index(bootstrap_repository)
    reason = bootstrap_repository.write("reasons/conflict.md", CONFLICT_REASON)

    result = run_bootstrap(
        bootstrap_repository,
        "block",
        "--branch",
        NO_PLANS_BRANCH,
        "--owner",
        OWNER,
        "--reason",
        str(reason),
    )

    assert result.returncode == PlanItemBootstrapExitCode.BRANCH_TRACKS_NO_ITEM
    assert json.loads(result.stdout)[ReportKey.PLAN] is None


def test_every_command_answers_to_a_word_of_its_own():
    commands = BootstrapCommand.every_command()

    assert {type(command) for command in commands} == set(
        BootstrapCommand.__subclasses__()
    )
    assert len({command.invoked_as for command in commands}) == len(commands)


def test_the_parser_takes_each_command_s_word(
    bootstrap_repository: ScratchRepository,
):
    """
    The parser is built from the commands themselves, so a word a command answers to is
    a word the command line accepts.
    """
    words = [command.invoked_as for command in BootstrapCommand.every_command()]

    refusals = {
        word: run_bootstrap(bootstrap_repository, word, "--help").returncode
        for word in words
    }

    assert refusals == {word: PlanItemBootstrapExitCode.SUCCESS for word in words}
