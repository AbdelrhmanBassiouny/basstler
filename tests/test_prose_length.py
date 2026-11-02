"""
Tests for prose_length.py: reporting docstrings and comment blocks longer than a limit.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from basstler.maintenance.git_commands import GitCommandRunner
from basstler.prose_length import (
    ProseKind,
    ProseLengthCheck,
    ProseLengthOption,
    ProseLimits,
    SourceProse,
    StagedLines,
    main,
)

from .constants.paths import ProseSnippet

# %% measuring


def overlong(snippet: ProseSnippet) -> list[tuple[ProseKind, int, int]]:
    """:return: Each overlong block of *snippet*, as its kind, first line and prose
    lines."""
    return [
        (finding.block.kind, finding.block.first_line, finding.block.prose_lines)
        for finding in ProseLengthCheck().findings([snippet])
    ]


def test_a_docstring_over_its_limit_is_reported():
    assert overlong(ProseSnippet.OVERLONG_MODULE_DOCSTRING) == [
        (ProseKind.DOCSTRING, 1, 5)
    ]


def test_field_lists_and_literal_blocks_are_not_prose():
    (block,) = SourceProse(ProseSnippet.FIELDS_AND_LITERAL_BLOCKS.read_text()).blocks

    assert block.prose_lines == 2


def test_an_attribute_docstring_is_measured():
    assert overlong(ProseSnippet.OVERLONG_ATTRIBUTE_DOCSTRING) == [
        (ProseKind.DOCSTRING, 10, 5)
    ]


def test_a_comment_block_over_its_limit_is_reported_and_section_headers_are_not_prose():
    assert overlong(ProseSnippet.COMMENT_BLOCKS) == [(ProseKind.COMMENT, 10, 4)]


def test_a_raised_limit_lets_the_block_through():
    check = ProseLengthCheck(ProseLimits(docstring_lines=5))

    assert check.findings([ProseSnippet.OVERLONG_MODULE_DOCSTRING]) == []


# %% the staged change


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    """:return: A git repository whose one commit holds an overlong module docstring."""
    for arguments in (
        ["init", "--quiet"],
        ["config", "user.name", "Tester"],
        ["config", "user.email", "tester@example.com"],
    ):
        subprocess.run(["git", *arguments], cwd=tmp_path, check=True)
    shutil.copy(ProseSnippet.OVERLONG_MODULE_DOCSTRING, tmp_path / "module.py")
    subprocess.run(["git", "add", "module.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "--quiet", "-m", "Add"], cwd=tmp_path, check=True)
    return tmp_path


def test_only_blocks_the_staged_change_touches_are_reported(repository):
    path = repository / "module.py"
    committed_lines = len(path.read_text().splitlines())
    with path.open("a") as source:
        source.write(f"\n{ProseSnippet.OVERLONG_ATTRIBUTE_DOCSTRING.read_text()}")
    subprocess.run(["git", "add", "module.py"], cwd=repository, check=True)
    check = ProseLengthCheck(staged=StagedLines(GitCommandRunner(repository)))

    findings = check.findings([path])

    assert [finding.block.first_line > committed_lines for finding in findings] == [
        True
    ]


# %% command line


def test_the_command_fails_when_a_block_is_overlong():
    assert main([ProseLengthOption.ALL, str(ProseSnippet.COMMENT_BLOCKS)]) == 1


def test_the_command_passes_when_nothing_is_overlong():
    assert (
        main([ProseLengthOption.ALL, str(ProseSnippet.FIELDS_AND_LITERAL_BLOCKS)]) == 0
    )
