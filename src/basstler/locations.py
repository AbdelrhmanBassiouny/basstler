"""
Every file and directory this package names, each written once.

..note:: Imports nothing outside the standard library, since :mod:`basstler.setup.dependencies`
    reads its declaration's location from here before anything is installed.
"""

from __future__ import annotations

import os
from enum import ReprEnum
from pathlib import Path

from basstler.environment import EnvironmentVariable


class PathEnumeration(Path, ReprEnum):
    """
    An enumeration whose members are paths.

    A member is the path it names - joined onto another with ``/``, opened, passed to a
    subprocess, formatted as its text - and every path derived from one is a plain
    :class:`~pathlib.Path`.

    ..warning:: ``Path.name`` shadows the enumeration's own ``name``: ``member.name`` is
        the path's last component, and the member's name is ``member._name_``.
    """

    def __hash__(self) -> int:
        """
        Hash as the path does, so a member and its path are one key; the enumeration's own
        hash would tell them apart.
        """
        return hash(self.value)

    def __eq__(self, value: object, /) -> bool:
        """
        The value of the Enum should be equal to an equivalent Path instance.

        :param value: A Path instance to compare.
        :return: True if the value is equal to an equivalent Path instance, False otherwise.
        """
        return self.value == value

    def with_segments(self, *path_segments: str | os.PathLike[str]) -> Path:
        """
        :param path_segments: The segments of a path derived from this one.
        :return: That path, as a plain path rather than a lookup of a member by value.
        """
        return Path(*path_segments)


class PackageLocation(PathEnumeration):
    """
    The package's own directory and the files shipped in it, as absolute paths.
    """

    DIRECTORY = Path(__file__).parent
    """
    This package's own directory.
    """

    SOURCE_TREE = DIRECTORY.parent.parent
    """
    The directory holding the package's ``pyproject.toml``, ``README.md`` and ``src`` when
    the package is imported from a source checkout - through an editable install or
    ``PYTHONPATH``. Meaningless for a package installed as a copy.
    """

    STACK_CONFIGURATION = DIRECTORY / "stack" / "stack.toml"
    """
    The shipped stack configuration every run starts from, before a project's and a
    user's overrides.
    """

    DEPENDENCY_DECLARATION = SOURCE_TREE / "pyproject.toml"
    """
    The package metadata of a source checkout, whose ``[project] dependencies`` this
    package installs.
    """

    LICENSE = SOURCE_TREE / "LICENSE"
    """
    The licence text of a source checkout.
    """

    TEMPLATES = DIRECTORY / "templates"
    """
    The templates the plan site's pages are rendered from.
    """

    SITE_FONTS = TEMPLATES / "fonts"
    """
    The font files the plan site serves, each beside its licence. The site serves them
    from a directory of the same name.
    """

    PACKAGE_MAP = DIRECTORY / "package_map.py"
    """
    The module declaring which distribution ships each of the package's modules.
    """

    QUERIES = DIRECTORY / "github" / "queries"
    """
    The GraphQL documents the upstream review reader sends.
    """

    PLAN_ITEM_MODE_DEFAULTS = DIRECTORY / "plan" / "plan-item-modes.toml"
    """
    The shipped plan-item execution modes.
    """


class RepositoryStateLocation(PathEnumeration):
    """
    Scratch state kept per repository, relative to its common git directory, which every
    worktree of the repository shares and no checkout or install of the package holds.
    """

    DIRECTORY = Path("basstler")
    """
    Everything this package keeps there.
    """

    BOARD = DIRECTORY / "board.json"
    """
    The exported snapshot of the fork's open pull requests.
    """

    MAINTENANCE_REPORT = DIRECTORY / "maintenance-report.json"
    """
    Everything the last maintenance pass did, in full.
    """

    PLAN_STATE_SYNC_STAMP = DIRECTORY / "plan-state-sync-sha"
    """
    The personal-notes commit this clone last read plan state at. The shell
    configuration's ``PLAN_STATE_SYNC_STAMP`` spells the same name.
    """

    PERSONAL_SETTINGS_SYNC_STAMP = DIRECTORY / "personal-settings-sync-hash"
    """
    The hash of the personal settings last synced into, or saved out of, this clone's
    local settings. The shell configuration's ``PERSONAL_SETTINGS_SYNC_STAMP`` spells
    the same name.
    """


class CommitScratchFile(PathEnumeration):
    """
    The files a commit built outside the working tree is staged through, relative to a
    scratch directory of its own.
    """

    INDEX = Path("index")
    """
    The index the commit's tree is staged in, leaving the clone's own untouched.
    """

    BLOB = Path("blob")
    """
    One file's content, written out to be stored as a blob.
    """


class SiteFontFile(PathEnumeration):
    """
    The font files the plan site serves, each the Latin letters of one open-licence face.
    """

    CINZEL = PackageLocation.SITE_FONTS.value / "cinzel-latin-700-normal.woff2"
    """
    Cinzel Bold: capitals after Roman inscriptions.
    """

    ALMENDRA = PackageLocation.SITE_FONTS.value / "almendra-latin-700-normal.woff2"
    """
    Almendra Bold: a storybook hand.
    """

    PLAYFAIR_DISPLAY_ITALIC = (
        PackageLocation.SITE_FONTS.value / "playfair-display-latin-600-italic.woff2"
    )
    """
    Playfair Display SemiBold Italic: a high-contrast serif.
    """

    OSWALD = PackageLocation.SITE_FONTS.value / "oswald-latin-600-normal.woff2"
    """
    Oswald SemiBold: a narrow gothic.
    """


class SiteTemplate(PathEnumeration):
    """
    The templates the plan site's pages and stylesheet are rendered from.
    """

    STYLESHEET = PackageLocation.TEMPLATES.value / "site.css"
    """
    The one stylesheet every page of the site links.
    """

    LAYOUT = PackageLocation.TEMPLATES.value / "site_layout.html"
    """
    The document every page of the site fills in.
    """

    PARTS = PackageLocation.TEMPLATES.value / "site_parts.html"
    """
    The markup the site's pages share: progress cards, the health banner, dependency
    chips and action buttons.
    """

    HUB = PackageLocation.TEMPLATES.value / "hub.html"
    """
    The hub: a card per repository.
    """

    REPOSITORY_INDEX = PackageLocation.TEMPLATES.value / "site_index.html"
    """
    One repository's index: a card per plan.
    """

    PLAN = PackageLocation.TEMPLATES.value / "site_plan.html"
    """
    One plan's page: a column per wave, a card per item.
    """

    PLAN_SCRIPT = PackageLocation.TEMPLATES.value / "site_plan.js"
    """
    A plan page's behaviour: copying commands, choosing a model, revealing an item.
    """

    LIVE_STATE_SCRIPT = PackageLocation.TEMPLATES.value / "site_live_state.js"
    """
    The script every site page reads a pull request's live state from GitHub's answer
    with, and re-checks with when the tab is shown again.
    """

    LIVE_PROGRESS_SCRIPT = PackageLocation.TEMPLATES.value / "site_live_progress.js"
    """
    The hub's and repository indexes' script that recounts every progress card from
    each repository's pull request listing.
    """

    PLAN_PULL_REQUEST_RECHECK_SCRIPT = (
        PackageLocation.TEMPLATES.value / "site_plan_pull_request_recheck.js"
    )
    """
    The plan page's script that reads every pull request's state from GitHub in the
    browser, and shows when the page was last refreshed.
    """

    APPEARANCE_SCRIPT = PackageLocation.TEMPLATES.value / "site_appearance.js"
    """
    The script every site page applies the viewer's theme and colour scheme with
    before it is drawn, and keeps a new pick with.
    """


class BasstlerVariable(EnvironmentVariable):
    """
    The environment variables this package's own shell configuration sets.
    """

    PLUGIN_ROOT = "BASSTLER_PLUGIN_ROOT"
    """
    The root of the Claude Code plugin whose hooks and skills run this package.
    """

    PYTHON = "BASSTLER_PYTHON"
    """
    The interpreter whose environment holds this package, for running its modules.
    """

    ENVIRONMENT_DIRECTORY = "BASSTLER_ENVIRONMENT_DIRECTORY"
    """
    The package's environment of the session's project, which every command of the
    session runs, whichever repository it runs in.
    """


class InstructionsTemplate(PathEnumeration):
    """
    The templates the agent instruction files are rendered from.
    """

    AGENTS = PackageLocation.TEMPLATES.value / "agents.md.jinja"
    """
    The content of ``AGENTS.md``: rules under the headings of their sections.
    """


class PluginLocation(PathEnumeration):
    """
    The plugin's files this package runs, relative to the plugin's root.
    """

    HOOKS = Path("hooks")
    """
    The shell entry points that read and write personal-notes data.
    """

    PERSONAL_NOTES_CONFIGURATION_SCRIPT = HOOKS / "resolve-personal-notes-config.sh"
    """
    The shell configuration that resolves the personal-notes remote and branch, and
    fetches it.
    """

    PERSONAL_NOTES_WRITER_SCRIPT = HOOKS / "write-personal-notes-file.sh"
    """
    The helper that commits one file to the personal-notes branch and pushes it.
    """

    PERSONAL_NOTES_BRANCH_CREATION_SCRIPT = HOOKS / "create-personal-notes-branch.sh"
    """
    The helper that creates the personal-notes branch where it does not exist yet.
    """

    ENTRY_POINT_SCRIPT = HOOKS / "basstler.sh"
    """
    Runs one module of the package once the package is ready to run, saying in one
    line why when it cannot be.
    """

    SESSION_START_SCRIPT = HOOKS / "session-start.sh"
    """
    The session-start hook: sets up the package's environment and loads the personal
    notes.
    """

    SESSION_START_MESSAGES_SCRIPT = HOOKS / "session-start-messages.sh"
    """
    The messages the session-start hook prints, sourced by it.
    """

    SESSION_RULES = HOOKS / "session-rules.md"
    """
    The rules every session using basstler's skills follows, which the session-start
    hook loads into the project's local instructions.
    """

    PERSONAL_NOTES_SAVING_SCRIPT = HOOKS / "save-personal-notes.sh"
    """
    Saves the personal notes in the project's local instructions back to the
    personal-notes branch.
    """

    SETUP_CHECK_SCRIPT = HOOKS / "check-setup.sh"
    """
    Reports, one row per prerequisite, what the personal-notes setup still lacks.
    """

    PLAN_SAVING_SCRIPT = HOOKS / "save-plan.sh"
    """
    Pushes an edited plan manifest and roadmap to the personal-notes branch.
    """

    PULL_REQUEST_PROGRESS_SAVING_SCRIPT = HOOKS / "save-pr-progress.sh"
    """
    Saves a branch's pull-request progress notes to the personal-notes branch.
    """

    PLAN_UPDATES_SINCE_SCRIPT = HOOKS / "plan-updates-since.sh"
    """
    Reports what changed in the plans since this clone last read them.
    """

    GIT_IDENTITY_SAVING_SCRIPT = HOOKS / "save-git-identity.sh"
    """
    Saves the user's git identity to the personal-notes branch.
    """

    PERSONAL_SETTINGS_SAVING_SCRIPT = HOOKS / "save-personal-settings.sh"
    """
    Saves the user's personal settings to the personal-notes branch.
    """

    @property
    def path_under_exported_root(self) -> str:
        """
        This file as bash spells it under :attr:`BasstlerVariable.PLUGIN_ROOT`, for a
        message that names it without knowing the root.
        """
        return f"${BasstlerVariable.PLUGIN_ROOT}/{self}"


class BasstlerRepositoryLocation(PathEnumeration):
    """
    The directories of basstler's own repository a release reads, relative to its root.
    """

    PLUGIN = Path("plugin")
    """
    The Claude Code plugin.
    """

    PLUGIN_MANIFEST = PLUGIN / ".claude-plugin" / "plugin.json"
    """
    The plugin's manifest: its name, description and, once released, version.
    """

    @property
    def path_in_plugin(self) -> Path:
        """
        :return: This file's path from the plugin's root, as the released plugin holds it.
        """
        return self.relative_to(BasstlerRepositoryLocation.PLUGIN)


class PluginSkillLocation(PathEnumeration):
    """
    The files of the plugin's skills this package reads, relative to the plugin's root.
    """

    SKILLS = Path("skills")
    """
    The directory holding one directory per skill.
    """

    STARTER_NOTES = SKILLS / "setup-personal-notes" / "starter-notes.md"
    """
    The conventions a new personal-notes file can be seeded with.
    """


class ProjectLocation(PathEnumeration):
    """
    The files this package reads, runs or writes in a project, relative to its root.

    Those on the personal-notes branch are relative to that branch's root, which is the
    same tree.
    """

    CLAUDE_CODE_DIRECTORY = Path(".claude")
    """
    The directory Claude Code reads a project's settings from.
    """

    PERSONAL_NOTES = CLAUDE_CODE_DIRECTORY / "personal"
    """
    Where the personal-notes branch keeps everything it holds.
    """

    PROJECT_STACK_CONFIGURATION = CLAUDE_CODE_DIRECTORY / "basstler" / "stack.toml"
    """
    The stack settings a project commits, naming its own upstream - layered over
    :attr:`PackageLocation.STACK_CONFIGURATION`.
    """

    PERSONAL_NOTES_DOCUMENT = PERSONAL_NOTES / "notes.md"
    """
    The notes file itself, unless a clone's settings put it elsewhere.
    """

    PLANS = PERSONAL_NOTES / "plans"
    """
    Where plans live on the personal-notes branch.

    Mirrors ``PLANS_DIR`` in ``resolve-personal-notes-config.sh``, which is the shell
    half of the same tooling; a test holds the two equal so the mirror cannot drift.
    """

    PLAN_HUB = PLANS / "_hub.yaml"
    """
    The plan hub file: the site's address and every repository it publishes.

    Mirrors ``PLAN_HUB_PATH`` in ``resolve-personal-notes-config.sh``.
    """

    PLAN_BRANCH_INDEX = PLANS / "_generated" / "branch-index.tsv"
    """
    The generated index naming the plan each item branch belongs to.

    Mirrors ``PLAN_BRANCH_INDEX_PATH`` in ``resolve-personal-notes-config.sh``.
    """

    PLAN_RULES = PLANS / "_rules.yaml"
    """
    The rules every plan of the repository follows, one entry per rule.
    """

    PERSONAL_STACK_CONFIGURATION = PERSONAL_NOTES / "stack.toml"
    """
    The per-user override of :attr:`PROJECT_STACK_CONFIGURATION`.
    """

    WORKFLOWS = Path(".github") / "workflows"
    """
    Where GitHub reads a repository's workflows from - the top level only.
    """

    ACTIONS_BUDGET = Path(".github") / "actions_budget.py"
    """
    The repository's Actions budget: the limits basstler holds every workflow to.
    """

    PERSONAL_PLAN_ITEM_MODES = PERSONAL_NOTES / "plan-item-modes.toml"
    """
    The per-user override of :attr:`PackageLocation.PLAN_ITEM_MODE_DEFAULTS`.
    """

    AGENTS_INSTRUCTIONS = Path("AGENTS.md")
    """
    The instructions agents read, generated from :mod:`basstler.code_rules.rules`.
    """


class WorkflowLocation(PathEnumeration):
    """
    The GitHub Actions workflows the plan site runs on, relative to the root of the
    branch that holds each.
    """

    DIRECTORY = Path(".github") / "workflows"
    """
    Where GitHub reads a branch's workflows from.
    """

    PLAN_SITE_BUILD = DIRECTORY / "plan-site-build.yml"
    """
    basstler's reusable workflow that builds and deploys the plan site.
    """

    PLAN_SITE = DIRECTORY / "plan-site.yml"
    """
    The workflow on the user's site repository that calls :attr:`PLAN_SITE_BUILD`.
    """

    PLAN_SITE_DISPATCH = DIRECTORY / "plan-site-dispatch.yml"
    """
    The workflow on a notes branch that starts :attr:`PLAN_SITE` on every push to it.
    """

    PLAN_SITE_MERGE = DIRECTORY / "plan-site-merge.yml"
    """
    The workflow on a notes repository's default branch that starts :attr:`PLAN_SITE`
    whenever a pull request merges.
    """


class ClaudeCodeVariable(EnvironmentVariable):
    """
    The environment variables Claude Code sets for the commands it runs.
    """

    PROJECT_DIRECTORY = "CLAUDE_PROJECT_DIR"
    """
    The root of the project the session runs in.
    """

    PLUGIN_ROOT = "CLAUDE_PLUGIN_ROOT"
    """
    The plugin's installation directory, which Claude Code also substitutes into a
    plugin skill's own instructions when it loads them.
    """

    REMOTE = "CLAUDE_CODE_REMOTE"
    """
    :attr:`~basstler.environment.EnvironmentFlag.TRUE` in a Claude Code cloud session, whose proxy answers GitHub's REST API but
    not its GraphQL API.
    """

    SESSION_IDENTIFIER = "CLAUDE_CODE_SESSION_ID"
    """
    The session's own identifier, which names its transcript file.
    """

    CONFIGURATION_DIRECTORY = "CLAUDE_CONFIG_DIR"
    """
    Where Claude Code keeps its state, transcripts included, when not ``~/.claude``.
    """

    GIT_BASH_PATH = "CLAUDE_CODE_GIT_BASH_PATH"
    """
    The bash Claude Code runs its commands in on Windows, when set.
    """
