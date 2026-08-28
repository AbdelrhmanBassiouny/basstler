#!/usr/bin/env python3
"""
Prints the setup steps that live outside this clone, filled in for the fork the
clone actually points at.

check-setup.sh reports on everything a shell can inspect - the notes branch, the
recorded git identity, the dashboard dependencies. What it cannot reach is
everything held by a service rather than a file: labels in a GitHub repository,
Claude's access to that repository, and the variables a fresh-clone environment
has to carry. Those are the steps a first-time user is left holding, so they are
printed here as a short list with the values already substituted, rather than
described in prose the reader has to translate.

Usage:
    python3 .claude/hooks/setup_steps.py
"""

from __future__ import annotations

import os
import subprocess
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
"""
The repository this script describes, resolved from the script's own location so the
answer does not depend on the caller's working directory.
"""

CONNECTOR_SETTINGS_URL = "https://claude.ai/customize/connectors"
"""
Where a user grants Claude access to their own GitHub repositories.
"""

ORGANIZATION_SETTINGS_URL = "https://claude.ai/admin-settings/claude-tag"
"""
Where an organization owner grants Claude access to the organization's repositories.
"""

WEB_ENVIRONMENT_DOCUMENTATION_URL = (
    "https://code.claude.com/docs/en/claude-code-on-the-web"
)
"""
Where the environment-level variable list for cloud sessions is documented.
"""


# %% the settings whose values the printed steps depend on


@dataclass(frozen=True)
class PersonalNotesSetting:
    """
    One of the three settings that decide where personal notes live.

    resolve-personal-notes-config.sh is the definition of both the precedence and the
    defaults; this mirrors them because the shell file exports nothing a child process
    could read them from.
    """

    git_config_key: str
    """
    The git config key that takes precedence over everything else.
    """

    environment_variable: str
    """
    The environment variable read when no git config value is set.
    """

    default: str
    """
    The value in force when neither of the two above is set.
    """

    def resolve(self, project_root: Path, environment: Mapping[str, str]) -> str:
        """
        Read this setting's value as the hooks themselves would.

        :param project_root: The clone whose git config to read.
        :param environment: The environment to read the variable from.
        :return: The value in force.
        """
        configured = subprocess.run(
            ["git", "config", "--get", self.git_config_key],
            cwd=project_root,
            capture_output=True,
            text=True,
        )
        if configured.returncode == 0 and configured.stdout.strip():
            return configured.stdout.strip()
        return environment.get(self.environment_variable) or self.default


NOTES_REMOTE_SETTING = PersonalNotesSetting(
    git_config_key="claude.personalNotesRemote",
    environment_variable="CLAUDE_PERSONAL_NOTES_REMOTE",
    default="origin",
)
"""
The remote, or raw URL, the notes branch lives on.
"""

NOTES_BRANCH_SETTING = PersonalNotesSetting(
    git_config_key="claude.personalNotesBranch",
    environment_variable="CLAUDE_PERSONAL_NOTES_BRANCH",
    default="claude/personal-notes",
)
"""
The branch the notes are stored on.
"""

NOTES_PATH_SETTING = PersonalNotesSetting(
    git_config_key="claude.personalNotesPath",
    environment_variable="CLAUDE_PERSONAL_NOTES_PATH",
    default=".claude/personal/cram-notes.md",
)
"""
Where on that branch the notes file sits.
"""

PERSONAL_NOTES_SETTINGS = (
    NOTES_REMOTE_SETTING,
    NOTES_BRANCH_SETTING,
    NOTES_PATH_SETTING,
)
"""
Every personal-notes setting, in the order the printed variable list uses.
"""


# %% the repository the steps are about


@dataclass(frozen=True)
class Repository:
    """
    A GitHub repository, named the way its URLs and the ``gh`` CLI name it.
    """

    owner: str
    """
    The user or organization that owns it.
    """

    name: str
    """
    The repository's own name.
    """

    @classmethod
    def from_remote_url(cls, url: str) -> Repository | None:
        """
        Read a repository out of a git remote URL, in either the HTTPS or the SSH form.

        :param url: The remote URL.
        :return: The repository, or ``None`` if the URL names no GitHub repository.
        """
        if "github.com" not in url:
            return None
        path = url.split("github.com", 1)[1].lstrip(":/").removesuffix(".git")
        segments = [segment for segment in path.split("/") if segment]
        if len(segments) != 2:
            return None
        return cls(owner=segments[0], name=segments[1])

    @property
    def full_name(self) -> str:
        """
        The ``owner/name`` form the ``gh`` CLI and GitHub's own interface use.
        """
        return f"{self.owner}/{self.name}"

    @property
    def labels_url(self) -> str:
        """
        The page where labels are created by hand.
        """
        return f"https://github.com/{self.full_name}/labels"


def resolve_repository(project_root: Path, notes_remote: str) -> Repository | None:
    """
    Find the repository a user's pull requests and notes go to.

    :param project_root: The clone to read remotes from.
    :param notes_remote: The resolved notes remote, either a remote name or a URL.
    :return: The repository, or ``None`` when no remote resolves to a GitHub URL.
    """
    candidates = [notes_remote]
    remote_url = subprocess.run(
        ["git", "remote", "get-url", notes_remote],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    if remote_url.returncode == 0:
        candidates.insert(0, remote_url.stdout.strip())
    for candidate in candidates:
        repository = Repository.from_remote_url(candidate)
        if repository is not None:
            return repository
    return None


# %% the labels a fork has to carry


class LabelPurpose(StrEnum):
    """
    What each label this tooling relies on is for, as its ``gh`` description.
    """

    MERGED = "The changes landed even though GitHub never recorded a merge"
    """
    Read by the dashboard, which treats the label exactly like a real merge.
    """

    BUG = "A bug fix"
    """
    Applied by a session opening a bug-fix pull request, and shown as a dashboard chip.
    """

    IN_REVIEW = "Under review"
    """
    Recognized so it does not read as an unknown label; no script acts on it yet.
    """


@dataclass(frozen=True)
class RepositoryLabel:
    """
    One label this tooling reads or applies, and therefore one a fork must carry.
    """

    name: str
    """
    The label's name, as GitHub stores it.
    """

    purpose: LabelPurpose
    """
    What it means, used as the description when the label is created.
    """

    def creation_command(self, repository: Repository) -> str:
        """
        The ``gh`` command that creates this label.

        :param repository: The repository to create it in.
        :return: The command, ready to paste.
        """
        return (
            f"gh label create {self.name} --repo {repository.full_name} "
            f'--description "{self.purpose.value}"'
        )


REQUIRED_LABELS = (
    RepositoryLabel(name="merged", purpose=LabelPurpose.MERGED),
    RepositoryLabel(name="bug", purpose=LabelPurpose.BUG),
    RepositoryLabel(name="in-review", purpose=LabelPurpose.IN_REVIEW),
)
"""
Every label the tooling reads or applies.

The same set build_dashboard.py's ``PullRequestLabel`` enumerates - kept as its own
tuple because that module needs the dashboard's dependencies installed, which is one
of the things this script exists to run before.
"""


# %% the steps themselves


@dataclass(frozen=True)
class SetupStep(ABC):
    """
    One setup step that no script can perform or verify, because it changes a setting
    held by GitHub or by Claude rather than a file in this clone.
    """

    @property
    @abstractmethod
    def title(self) -> str:
        """
        What the step changes, in a few words.
        """

    @property
    @abstractmethod
    def reason(self) -> str:
        """
        What stops working until it is done.
        """

    @abstractmethod
    def instructions(self) -> list[str]:
        """
        What to do, one line per action.

        :return: The lines, printed under the title.
        """

    def render(self, number: int) -> str:
        """
        Render this step as the numbered block the reader sees.

        :param number: The step's position in the printed list.
        :return: The block, without a trailing newline.
        """
        lines = [f"{number}. {self.title}", f"   {self.reason}", ""]
        lines.extend(f"   {instruction}" for instruction in self.instructions())
        return "\n".join(lines)


@dataclass(frozen=True)
class ForkLabels(SetupStep):
    """
    Creating the labels this tooling reads and applies, in the user's fork.
    """

    repository: Repository
    """
    The fork the labels belong in.
    """

    @property
    def title(self) -> str:
        """See :attr:`SetupStep.title`."""
        return f"Add three labels to {self.repository.full_name}"

    @property
    def reason(self) -> str:
        """See :attr:`SetupStep.reason`."""
        return (
            "A fresh fork has none of them: dashboards misread landed work, and "
            "applying a label a repository lacks fails mid-pull-request."
        )

    def instructions(self) -> list[str]:
        """See :meth:`SetupStep.instructions`."""
        commands = [
            label.creation_command(self.repository) for label in REQUIRED_LABELS
        ]
        return [*commands, f"Or create them by hand: {self.repository.labels_url}"]


@dataclass(frozen=True)
class RepositoryAccess(SetupStep):
    """
    Giving Claude access to the repository sessions read and open pull requests
    against.
    """

    repository: Repository
    """
    The repository the access has to cover.
    """

    @property
    def title(self) -> str:
        """See :attr:`SetupStep.title`."""
        return f"Give Claude access to {self.repository.full_name}"

    @property
    def reason(self) -> str:
        """See :attr:`SetupStep.reason`."""
        return (
            "A session that cannot reach the repository cannot read pull requests, "
            "open them, or build a dashboard from their state."
        )

    def instructions(self) -> list[str]:
        """See :meth:`SetupStep.instructions`."""
        return [
            f"Your own fork: {CONNECTOR_SETTINGS_URL}",
            f"An organization's fork, granted by an owner: {ORGANIZATION_SETTINGS_URL}",
        ]


@dataclass(frozen=True)
class PersistentVariables(SetupStep):
    """
    Carrying the personal-notes settings into environments that clone fresh every
    session.
    """

    variable_lines: tuple[str, ...]
    """
    The ``NAME=value`` lines to paste, empty when every setting is still its default.
    """

    @classmethod
    def resolve(
        cls, project_root: Path, environment: Mapping[str, str]
    ) -> PersistentVariables:
        """
        Work out which settings this clone has moved off their defaults.

        :param project_root: The clone to read settings from.
        :param environment: The environment to read them from.
        :return: The step, carrying only the lines that differ from the defaults.
        """
        lines = []
        for setting in PERSONAL_NOTES_SETTINGS:
            value = setting.resolve(project_root, environment)
            if value != setting.default:
                lines.append(f"{setting.environment_variable}={value}")
        return cls(variable_lines=tuple(lines))

    @property
    def title(self) -> str:
        """See :attr:`SetupStep.title`."""
        return "Carry your settings into environments that clone fresh"

    @property
    def reason(self) -> str:
        """See :attr:`SetupStep.reason`."""
        return (
            "Claude Code on the web starts from a new clone every session, so git "
            "config set inside one is gone by the next."
        )

    def instructions(self) -> list[str]:
        """See :meth:`SetupStep.instructions`."""
        if not self.variable_lines:
            return ["Nothing to paste: every setting is still its default."]
        return [
            "Paste these into your environment's variable list "
            f"({WEB_ENVIRONMENT_DOCUMENTATION_URL}):",
            *self.variable_lines,
        ]


# %% the checklist they add up to


HEADING = "These steps are yours - no script can do them:"
"""
The line introducing the printed list.
"""


@dataclass(frozen=True)
class SetupChecklist:
    """
    The steps one clone leaves to its user, in the order they should be done.
    """

    steps: tuple[SetupStep, ...]
    """
    The steps that apply to this clone.
    """

    @classmethod
    def for_clone(
        cls, project_root: Path, environment: Mapping[str, str]
    ) -> SetupChecklist:
        """
        Work out which steps a clone leaves to its user, and fill them in from it.

        The repository-specific steps are omitted when no GitHub repository can be
        resolved from the clone's remotes, since neither can be acted on without one.

        :param project_root: The clone the steps are about.
        :param environment: The environment its settings resolve from.
        :return: The checklist.
        """
        notes_remote = NOTES_REMOTE_SETTING.resolve(project_root, environment)
        repository = resolve_repository(project_root, notes_remote)
        steps: list[SetupStep] = []
        if repository is not None:
            steps.extend([ForkLabels(repository), RepositoryAccess(repository)])
        steps.append(PersistentVariables.resolve(project_root, environment))
        return cls(steps=tuple(steps))

    def render(self) -> str:
        """
        Render the whole checklist as it is printed.

        :return: The full output.
        """
        blocks = [
            step.render(number) for number, step in enumerate(self.steps, start=1)
        ]
        return "\n\n".join([HEADING, *blocks])


def main() -> None:
    """
    Print the checklist for this clone.
    """
    print(SetupChecklist.for_clone(PROJECT_ROOT, os.environ).render())


if __name__ == "__main__":
    main()
