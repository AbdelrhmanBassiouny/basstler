"""
What about a skill's own documents is worth asserting from code.

A skill states its procedure in prose, and the parts worth stating once live in a
document beside it that it links to. Nothing resolves that link until a session follows
it, so a document renamed or moved leaves the skill pointing at nothing and every run of
it short of the part that was extracted.

Claude Code substitutes only its own variables in a skill, so a shell variable naming a
document reaches the model as the bare variable name: a document is cited by a link.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import pytest

from basstler.locations import BasstlerVariable, ClaudeCodeVariable, PluginLocation

from ..constants.paths import RepositoryLocation, SkillDirectory

LINK_TARGET = re.compile(r"\]\(([^)]+)\)")
"""
Matches the target of a markdown link, whatever it points at.
"""

# %% reading the documents


def linked_files(instructions: str) -> set[str]:
    """
    :param instructions: A skill document's own text.
    :return: Every target it links to that names a file in the repository rather than a
        URL or a heading on the page itself.
    """
    return {
        target
        for target in LINK_TARGET.findall(instructions)
        if "://" not in target and not target.startswith("#")
    }


def cited_shell_variables(document: Path) -> set[str]:
    """
    :param document: A skill document.
    :return: The name of every shell variable the document references in braces.
    """
    return set(re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*)", document.read_text()))


class SkillDocumentName(StrEnum):
    """
    The file name Claude Code loads a skill from.
    """

    SKILL = "SKILL.md"
    """
    A skill's own instructions, the only document Claude Code substitutes its
    variables in.
    """


BASH_BLOCK = re.compile(r"^( *)```bash\n(.*?)^\1```", re.MULTILINE | re.DOTALL)
"""
Matches a fenced bash block, indented or not, capturing its commands.
"""

SHELL_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
"""
Matches every word that could name a shell function.
"""


def bash_blocks(document: Path) -> list[str]:
    """
    :param document: A skill document.
    :return: The commands of every fenced bash block in it, one entry per block.
    """
    return [match.group(2) for match in BASH_BLOCK.finditer(document.read_text())]


def skill_documents() -> list[Path]:
    """
    :return: Every markdown document under the skills directory, in a stable order.
    """
    return sorted((RepositoryLocation.PLUGIN / SkillDirectory.DIRECTORY).rglob("*.md"))


def document_identifier(document: Path) -> str:
    """
    :return: The document's path within the skills directory, naming its test case.
    """
    return str(
        document.relative_to(RepositoryLocation.PLUGIN / SkillDirectory.DIRECTORY)
    )


# %% the shell configuration


@dataclass(frozen=True)
class ShellConfiguration:
    """
    The variables sourcing the plugin's shell configuration defines, which is what a
    skill document's shell variables resolve to.
    """

    variables: dict[str, str]
    """
    Each variable's value, by name.
    """

    functions: frozenset[str]
    """
    The name of every function it defines.
    """

    @classmethod
    def from_source(cls) -> ShellConfiguration:
        """
        Source this checkout's configuration and read back every variable it leaves set.

        :return: The configuration.
        """
        configuration = (
            RepositoryLocation.HOOKS
            / PluginLocation.PERSONAL_NOTES_CONFIGURATION_SCRIPT.name
        )
        result = subprocess.run(
            [
                "bash",
                "-c",
                f'source "{configuration}" >/dev/null 2>&1; '
                'for name in $(compgen -v); do printf "%s\\0%s\\0" "$name" "${!name}"; done',
            ],
            capture_output=True,
            text=True,
            check=True,
            cwd=RepositoryLocation.ROOT,
        )
        functions = subprocess.run(
            [
                "bash",
                "-c",
                f'source "{configuration}" >/dev/null 2>&1; compgen -A function',
            ],
            capture_output=True,
            text=True,
            check=True,
            cwd=RepositoryLocation.ROOT,
        )
        fields = result.stdout.split("\0")
        return cls(
            variables=dict(zip(fields[0:-1:2], fields[1::2], strict=True)),
            functions=frozenset(functions.stdout.split()),
        )

    def names_used_by(self, commands: str) -> set[str]:
        """
        :param commands: The commands of one bash block.
        :return: Every variable and function of the configuration they use, apart from
            the plugin root the session's environment sets.
        """
        variables = set(re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*)", commands))
        used = (variables & self.variables.keys()) | (
            set(SHELL_WORD.findall(commands)) & self.functions
        )
        return used - {BasstlerVariable.PLUGIN_ROOT}

    def skill_document_variables(self) -> set[str]:
        """
        :return: The names of the variables whose value is a document in the skills
            directory.
        """
        skills = (RepositoryLocation.PLUGIN / SkillDirectory.DIRECTORY).resolve()
        return {
            name
            for name, value in self.variables.items()
            if value.endswith(".md") and Path(value).resolve().is_relative_to(skills)
        }


@pytest.fixture(scope="module")
def shell_configuration() -> ShellConfiguration:
    """
    :return: This checkout's shell configuration, sourced once for the module.
    """
    return ShellConfiguration.from_source()


# %% links


@pytest.mark.parametrize("document", skill_documents(), ids=document_identifier)
def test_every_file_a_skill_document_links_to_is_there(document: Path) -> None:
    linked = linked_files(document.read_text())

    missing = {
        target for target in linked if not (document.parent / target).resolve().exists()
    }
    assert missing == set()


# %% shell variables


@pytest.mark.parametrize("document", skill_documents(), ids=document_identifier)
def test_no_skill_document_cites_a_document_through_a_shell_variable(
    document: Path, shell_configuration: ShellConfiguration
) -> None:
    cited = cited_shell_variables(document)

    assert cited & shell_configuration.skill_document_variables() == set()


@pytest.mark.parametrize("document", skill_documents(), ids=document_identifier)
def test_every_shell_variable_a_skill_document_cites_is_configured(
    document: Path, shell_configuration: ShellConfiguration
) -> None:
    """
    A variable dropped from the configuration but still cited expands to nothing in the
    documented command.
    """
    cited = cited_shell_variables(document)
    substituted = (
        {ClaudeCodeVariable.PLUGIN_ROOT}
        if document.name == SkillDocumentName.SKILL
        else set()
    )

    assert cited - shell_configuration.variables.keys() - substituted == set()


@pytest.mark.parametrize("document", skill_documents(), ids=document_identifier)
def test_every_bash_block_sources_the_configuration_it_uses(
    document: Path, shell_configuration: ShellConfiguration
) -> None:
    """
    Each Bash call is a fresh shell, so a block relying on an earlier block's sourcing
    runs with every configuration name empty.
    """
    unsourced = [
        shell_configuration.names_used_by(commands)
        for commands in bash_blocks(document)
        if PluginLocation.PERSONAL_NOTES_CONFIGURATION_SCRIPT.name not in commands
    ]

    assert [names for names in unsourced if names] == []


@pytest.mark.parametrize("document", skill_documents(), ids=document_identifier)
def test_a_command_names_the_plugin_root_as_its_document_receives_it(
    document: Path,
) -> None:
    """
    Claude Code substitutes the plugin root only into a skill's own instructions; a
    linked document reads it from the session's environment.
    """
    cited = {
        variable
        for commands in bash_blocks(document)
        for variable in re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*)", commands)
    }
    unavailable = (
        BasstlerVariable.PLUGIN_ROOT
        if document.name == SkillDocumentName.SKILL
        else ClaudeCodeVariable.PLUGIN_ROOT
    )

    assert unavailable not in cited


@pytest.mark.parametrize(
    "document",
    [
        document
        for document in skill_documents()
        if document.name == SkillDocumentName.SKILL
    ],
    ids=document_identifier,
)
def test_every_skill_links_how_to_run_commands_with_its_plugin_root(
    document: Path,
) -> None:
    """
    Each skill links the shared rules for running commands and says what plugin root
    they name.
    """
    running_commands = os.path.relpath(
        RepositoryLocation.PLUGIN / SkillDirectory.RUNNING_COMMANDS_DOCUMENT,
        document.parent,
    )
    mapping_paragraphs = [
        paragraph
        for paragraph in document.read_text().split("\n\n")
        if f"${{{BasstlerVariable.PLUGIN_ROOT}}}" in paragraph
        and f"${{{ClaudeCodeVariable.PLUGIN_ROOT}}}" in paragraph
        and f"]({running_commands})" in paragraph
    ]

    assert len(mapping_paragraphs) == 1


# %% rules scoped to a skill run


def test_the_resolve_skill_links_the_pull_request_rules() -> None:
    """
    The pull-request rules hold only while a skill linking them runs.
    """
    document = (
        RepositoryLocation.PLUGIN
        / SkillDirectory.PLAN_ITEM_RESOLVE
        / SkillDocumentName.SKILL
    )
    pull_request_rules = os.path.relpath(
        RepositoryLocation.PLUGIN / SkillDirectory.PULL_REQUEST_RULES_DOCUMENT,
        document.parent,
    )

    assert pull_request_rules in linked_files(document.read_text())


# %% the interpreter a module is run with

BARE_INTERPRETER_RUN = re.compile(r"(?<![\w/$\"{}-])python3? -m basstler\b")
"""
A module of the package run with whatever ``python``/``python3`` the path finds, which
in a session is not the package's own environment.
"""


@pytest.mark.parametrize("document", skill_documents(), ids=document_identifier)
def test_no_skill_document_runs_the_package_with_a_bare_interpreter(document: Path):
    """
    Each skill links the shared rules for running commands and says what plugin root they name.
    """
    assert BARE_INTERPRETER_RUN.findall(document.read_text()) == []


# %% where a skill writes its files

SYSTEM_TEMPORARY_PATH = re.compile(r"(?<![\w.~-])/tmp/")
"""
A path under the system's temporary directory, which the ``Artifact`` tool refuses to
publish from.
"""


@pytest.mark.parametrize("document", skill_documents(), ids=document_identifier)
def test_no_skill_document_writes_under_the_system_temporary_directory(
    document: Path,
):
    assert SYSTEM_TEMPORARY_PATH.findall(document.read_text()) == []


# %% the description claude.ai stores

SKILL_DESCRIPTION = re.compile(r"\A---\n(?:.*\n)*?description: (.*)\n", re.MULTILINE)
"""
Matches a skill's front matter up to its description, capturing the description.
"""

ANGLE_BRACKET = re.compile(r"[<>]")
"""
Matches a character claude.ai strips from a skill's description as part of an XML tag.
"""


@pytest.mark.parametrize(
    "document",
    [
        document
        for document in skill_documents()
        if document.name == SkillDocumentName.SKILL
    ],
    ids=document_identifier,
)
def test_no_skill_description_holds_an_angle_bracket(document: Path) -> None:
    """
    claude.ai warns about a description that holds an XML tag and stores it with its
    angle brackets removed, so a placeholder such as ``<plan-id>`` loses its markers.
    """
    description = SKILL_DESCRIPTION.match(document.read_text())

    assert ANGLE_BRACKET.findall(description.group(1)) == []
