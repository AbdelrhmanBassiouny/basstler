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

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from basstler.locations import PluginLocation

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
        fields = result.stdout.split("\0")
        return cls(variables=dict(zip(fields[0:-1:2], fields[1::2])))

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

    assert cited - shell_configuration.variables.keys() == set()
