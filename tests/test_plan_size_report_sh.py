"""
Integration tests for plan-size-report.sh.

Runs against a local ``git init --bare`` fixture rather than a real remote, so no test
needs network access or a real personal-notes branch.
"""

import subprocess
from pathlib import Path

import pytest
import yaml

from basstler.locations import PluginLocation, ProjectLocation
from basstler.plan_item_bootstrap import PlanDocument
from basstler.plan_size_budget import PlanSize, SizeBudget, SizeReport

from .project_declaration import ProjectDeclaration
from .scratch_repository import PackageSourceFile, ScratchRepository

UNINSTALLABLE_REQUIREMENT = "basstler-no-such-distribution>=1"
"""
A distribution nothing can have installed, so a declaration naming it is always reported
as missing.
"""


def declaration_file(repository: ScratchRepository) -> Path:
    """
    :param repository: A fixture-built scratch repository.
    :return: Where its scratch checkout declares the package's requirements.
    """
    return repository.checkout_root / PackageSourceFile.METADATA


def plan_files(plan_id: str, item_count: int = 0, roadmap_line_count: int = 0) -> dict:
    """
    Build one plan's two notes-branch files.

    :param plan_id: The plan's id, used as its directory name and its ``id`` field.
    :param item_count: How many items its manifest declares.
    :param roadmap_line_count: How many lines its roadmap holds.
    :return: File contents, keyed by path relative to the notes branch's root.
    """
    plan_directory = f"{ProjectLocation.PLANS}/{plan_id}"
    manifest = {
        "id": plan_id,
        "items": [{"id": f"item-{number}"} for number in range(item_count)],
    }
    return {
        f"{plan_directory}/{PlanDocument.MANIFEST}": yaml.safe_dump(manifest),
        f"{plan_directory}/{PlanDocument.ROADMAP}": "".join(
            f"roadmap line {number}\n" for number in range(roadmap_line_count)
        ),
    }


@pytest.fixture
def report_repository(scratch_repository: ScratchRepository) -> ScratchRepository:
    """
    A scratch repository carrying the real plan-size-report.sh and everything it runs,
    with no notes branch published yet - each test publishes the plans it is about.

    :param scratch_repository: The initialized scratch repository and notes remote.
    :return: The same repository, ready to publish plans and run the report against.
    """
    scratch_repository.install_hook_scripts(
        PluginLocation.PERSONAL_NOTES_CONFIGURATION_SCRIPT.name,
        PluginLocation.PLAN_SIZE_REPORT_SCRIPT.name,
    )
    scratch_repository.install_package()
    scratch_repository.write("README.md", "scratch repo\n")
    scratch_repository.commit_everything("initial commit")
    scratch_repository.resolve_notes_remote_to()
    return scratch_repository


def run_report(repository: ScratchRepository) -> subprocess.CompletedProcess[str]:
    """
    Run the scratch layout's plan-size-report.sh.

    :param repository: A fixture-built scratch repository.
    :return: The finished subprocess.
    """
    return repository.run_hook_script(PluginLocation.PLAN_SIZE_REPORT_SCRIPT.name)


def report_line_for(report: str, plan_id: str) -> str:
    """
    Pick one plan's row out of a printed report.

    :param report: The report the script printed.
    :param plan_id: The plan whose row to return.
    :return: That row, with its trailing padding stripped.
    """
    rows = [line for line in report.splitlines() if line.startswith(f"{plan_id} ")]
    assert len(rows) == 1, f"expected exactly one row for {plan_id!r} in:\n{report}"
    return rows[0].rstrip()


# %% what the report covers


def test_reports_every_plan_on_the_notes_branch(report_repository: ScratchRepository):
    report_repository.publish_notes_branch(
        {**plan_files("plan-a", item_count=1), **plan_files("plan-b", item_count=2)}
    )
    result = run_report(report_repository)
    assert result.returncode == 0, result.stderr
    assert report_line_for(result.stdout, "plan-a").split()[1] == "1"
    assert report_line_for(result.stdout, "plan-b").split()[1] == "2"


def test_counts_the_manifest_and_roadmap_lines_together(
    report_repository: ScratchRepository,
):
    files = plan_files("plan-a", item_count=1, roadmap_line_count=4)
    report_repository.publish_notes_branch(files)
    manifest_line_count = len(
        files[f"{ProjectLocation.PLANS}/plan-a/{PlanDocument.MANIFEST}"].splitlines()
    )
    result = run_report(report_repository)
    assert report_line_for(result.stdout, "plan-a").split()[2:5] == [
        str(manifest_line_count),
        "4",
        str(manifest_line_count + 4),
    ]


def test_a_plan_within_the_budget_is_reported_as_within_it(
    report_repository: ScratchRepository,
):
    report_repository.publish_notes_branch(plan_files("plan-a", item_count=1))
    result = run_report(report_repository)
    assert report_line_for(result.stdout, "plan-a").endswith(SizeReport.WITHIN_BUDGET)


def test_a_plan_over_the_budget_is_reported_as_over_it(
    report_repository: ScratchRepository,
):
    item_count = SizeBudget().maximum_items + 1
    report_repository.publish_notes_branch(plan_files("plan-a", item_count=item_count))
    (overrun,) = SizeBudget().overruns(
        PlanSize(
            plan_id="plan-a",
            item_count=item_count,
            manifest_line_count=0,
            roadmap_line_count=0,
        )
    )
    result = run_report(report_repository)
    assert report_line_for(result.stdout, "plan-a").endswith(str(overrun))


def test_generated_data_beside_the_plans_is_not_reported_as_a_plan(
    report_repository: ScratchRepository,
):
    report_repository.publish_notes_branch(
        {
            **plan_files("plan-a", item_count=1),
            f"{ProjectLocation.PLANS}/_generated/branch-index.tsv": "a-branch\tplan-a\n",
        }
    )
    result = run_report(report_repository)
    assert not [
        line for line in result.stdout.splitlines() if line.startswith("_generated")
    ]


# %% refusals


def test_rejects_an_unexpected_argument(report_repository: ScratchRepository):
    report_repository.publish_notes_branch(plan_files("plan-a"))
    result = report_repository.run_hook_script(
        PluginLocation.PLAN_SIZE_REPORT_SCRIPT.name, "plan-a"
    )
    assert result.returncode == 1
    assert result.stderr.startswith("Unexpected argument: plan-a\n")


def test_fails_when_the_notes_branch_does_not_exist(
    report_repository: ScratchRepository,
):
    result = run_report(report_repository)
    assert result.returncode == 1
    assert "doesn't exist yet" in result.stderr


def test_reports_whichever_dependency_is_missing(
    report_repository: ScratchRepository,
):
    declaration_file(report_repository).write_text(
        ProjectDeclaration(
            name=ProjectDeclaration.of_this_package().name,
            dependencies=(UNINSTALLABLE_REQUIREMENT,),
        ).as_toml(),
    )
    report_repository.publish_notes_branch(plan_files("plan-a"))

    result = run_report(report_repository)

    assert result.returncode == 1
    assert UNINSTALLABLE_REQUIREMENT in result.stderr


def test_runs_when_every_dependency_is_installed(
    report_repository: ScratchRepository,
):
    report_repository.publish_notes_branch(plan_files("plan-a"))

    result = run_report(report_repository)

    assert result.returncode == 0, result.stderr
    assert UNINSTALLABLE_REQUIREMENT not in result.stderr
