"""
Which libraries of CI's matrix a change needs tested: the libraries whose package or
test directory it touches, and every library depending on them.

The tests read a small workspace in the dataset, standing in for a project that runs its
libraries' tests as one CI matrix.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from basstler.changed_libraries import (
    CommandLineFlag,
    LibraryMatrix,
    SelectedTests,
    SelectionOutput,
    ChangedPathKind,
    main,
)
from basstler.exceptions import MissingMatrixAxis
from basstler.locations import ProjectLocation

from .constants import DatasetLocation

# %% the dataset's workspace


@pytest.fixture
def tooling_directory() -> Path:
    """
    :return: A tooling directory the dataset's project names besides ``.claude``.
    """
    return Path("tools")


@pytest.fixture
def matrix(tooling_directory: Path) -> LibraryMatrix:
    """
    :return: The library matrix of the dataset's CI workflow.
    """
    return LibraryMatrix.read(
        project_root=DatasetLocation.CHANGED_LIBRARIES,
        workflow=DatasetLocation.CHANGED_LIBRARIES_WORKFLOW,
        job="test_each_lib",
        axis="lib",
        tooling_directories=(
            ProjectLocation.CLAUDE_CODE_DIRECTORY.value,
            tooling_directory,
        ),
    )


def test_the_libraries_are_read_off_the_matrix_axis_in_order(matrix: LibraryMatrix):
    assert [library.name for library in matrix.libraries] == [
        "core",
        "middle_library",
        "leaf",
        "lonely",
        "cycle_first",
        "cycle_second",
        "meta_package",
        "checks",
    ]


def test_a_job_without_the_axis_is_reported():
    with pytest.raises(MissingMatrixAxis):
        LibraryMatrix.read(
            project_root=DatasetLocation.CHANGED_LIBRARIES,
            workflow=DatasetLocation.CHANGED_LIBRARIES_WORKFLOW,
            job="test_each_lib",
            axis="python",
        )


def test_a_job_the_workflow_does_not_have_is_reported():
    with pytest.raises(MissingMatrixAxis):
        LibraryMatrix.read(
            project_root=DatasetLocation.CHANGED_LIBRARIES,
            workflow=DatasetLocation.CHANGED_LIBRARIES_WORKFLOW,
            job="test_everything",
            axis="lib",
        )


# %% selecting from a change


def test_a_changed_library_is_tested_with_every_library_depending_on_it(
    matrix: LibraryMatrix,
):
    """
    ``middle_library`` and ``leaf`` depend on ``core`` directly and through each other;
    the meta-package's declaration names every library, and ``checks`` has no package,
    so it depends on all of them.
    """
    selection = matrix.selection_for([Path("core/src/core/geometry.py")])

    assert selection.libraries == frozenset(
        {"core", "middle_library", "leaf", "meta_package", "checks"}
    )


def test_a_changed_test_directory_selects_its_library(matrix: LibraryMatrix):
    assert matrix.selection_for(
        [Path("test/leaf_test/test_leaf.py")]
    ) == matrix.selection_for([Path("leaf/src/leaf/leaf.py")])


def test_dependency_names_match_whatever_separators_case_and_extras_they_use(
    matrix: LibraryMatrix,
):
    """
    ``middle_library`` declares ``Core>=1.0`` and ``leaf`` declares
    ``middle_library[plotting]`` against the distribution ``middle-library``.
    """
    selection = matrix.selection_for([Path("core/pyproject.toml")])

    assert {"middle_library", "leaf"} <= selection.libraries


def test_libraries_depending_on_each_other_are_both_selected(matrix: LibraryMatrix):
    selection = matrix.selection_for([Path("cycle_first/cycle_first.py")])

    assert selection.libraries == frozenset(
        {"cycle_first", "cycle_second", "meta_package", "checks"}
    )


def test_a_library_change_does_not_test_the_tooling(matrix: LibraryMatrix):
    assert matrix.selection_for([Path("lonely/lonely.py")]).tests_tooling is False


def test_a_change_only_to_the_tooling_tests_the_tooling_alone(
    matrix: LibraryMatrix, tooling_directory: Path
):
    selection = matrix.selection_for(
        [
            ProjectLocation.CLAUDE_CODE_DIRECTORY / "settings.json",
            tooling_directory / "release.py",
        ]
    )

    assert selection == SelectedTests(libraries=frozenset(), tests_tooling=True)


def test_a_change_only_to_documentation_tests_nothing(matrix: LibraryMatrix):
    selection = matrix.selection_for(
        [Path("README.md"), Path("core/doc/index.rst"), Path("doc/conf.py")]
    )

    assert selection == SelectedTests(libraries=frozenset(), tests_tooling=False)


def test_a_change_outside_every_library_and_the_tooling_tests_everything(
    matrix: LibraryMatrix,
):
    """
    A path no library or the tooling owns - here the workspace declaration - could
    affect any of them.
    """
    selection = matrix.selection_for([Path("lonely/lonely.py"), Path("pyproject.toml")])

    assert selection == matrix.everything


def test_everything_tests_every_library_and_the_tooling(matrix: LibraryMatrix):
    assert matrix.everything == SelectedTests(
        libraries=frozenset(library.name for library in matrix.libraries),
        tests_tooling=True,
    )


@pytest.mark.parametrize(
    ("path", "kind"),
    [
        (Path("core/core.py"), ChangedPathKind.LIBRARY),
        (Path("test/core_test/test_core.py"), ChangedPathKind.LIBRARY),
        (
            ProjectLocation.CLAUDE_CODE_DIRECTORY / "settings.json",
            ChangedPathKind.TOOLING,
        ),
        (Path("core/doc/index.md"), ChangedPathKind.DOCUMENTATION),
        (Path("uv.lock"), ChangedPathKind.WORKSPACE),
    ],
)
def test_each_path_is_attributed_to_what_it_belongs_to(
    matrix: LibraryMatrix, path: Path, kind: ChangedPathKind
):
    assert matrix.kind_of(path) is kind


# %% what the workflow reads back


def test_the_unselected_libraries_are_excluded_from_the_matrix(matrix: LibraryMatrix):
    selection = matrix.selection_for([Path("lonely/lonely.py")])

    assert matrix.exclusions_for(selection) == [
        {"lib": name}
        for name in ("core", "middle_library", "leaf", "cycle_first", "cycle_second")
    ]


def test_the_step_outputs_name_the_exclusions_and_what_runs(
    matrix: LibraryMatrix, tooling_directory: Path
):
    selection = matrix.selection_for([tooling_directory / "release.py"])

    assert matrix.step_outputs_for(selection) == {
        SelectionOutput.EXCLUDED: json.dumps(matrix.exclusions_for(selection)),
        SelectionOutput.TESTS_LIBRARIES: "false",
        SelectionOutput.TESTS_TOOLING: "true",
    }


# %% command line


@pytest.fixture
def command_line(tooling_directory: Path) -> list[str]:
    """
    :return: The command line selecting from the dataset's matrix.
    """
    return [
        CommandLineFlag.PROJECT_ROOT,
        str(DatasetLocation.CHANGED_LIBRARIES),
        CommandLineFlag.WORKFLOW,
        DatasetLocation.CHANGED_LIBRARIES_WORKFLOW.name,
        CommandLineFlag.JOB,
        "test_each_lib",
        CommandLineFlag.AXIS,
        "lib",
        CommandLineFlag.TOOLING,
        str(tooling_directory),
    ]


def test_the_command_prints_the_step_outputs_of_the_changed_paths_it_reads(
    matrix: LibraryMatrix,
    command_line: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    changed = [Path("leaf/leaf.py"), Path("tools/release.py")]
    monkeypatch.setattr(
        "sys.stdin", io.StringIO("".join(f"{path}\n" for path in changed))
    )

    main(command_line)

    outputs = matrix.step_outputs_for(matrix.selection_for(changed))
    assert capsys.readouterr().out.splitlines() == [
        f"{output}={value}" for output, value in outputs.items()
    ]


def test_the_command_counts_the_claude_code_directory_as_tooling_unasked(
    command_line: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    without_tooling = command_line[: command_line.index(CommandLineFlag.TOOLING)]
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(f"{ProjectLocation.CLAUDE_CODE_DIRECTORY / 'settings.json'}\n"),
    )

    main(without_tooling)

    assert (
        f"{SelectionOutput.TESTS_TOOLING}=true" in capsys.readouterr().out.splitlines()
    )
