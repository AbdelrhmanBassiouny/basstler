"""
The paths and names more than one suite in this directory needs.

Anything :mod:`basstler` already names - a module, or a location in
:mod:`basstler.locations` - is not written down here: a suite imports it, so a rename
moves with the code instead of leaving a literal behind. What remains has no import to
derive it from: this directory's own dataset, the skill directories, the notes-branch
paths only the shell hooks name, and the names a scratch repository is built with.
"""

from __future__ import annotations

from enum import Enum, IntEnum, StrEnum
from pathlib import Path
from typing import Any

from basstler.locations import PackageLocation, PathEnumeration, ProjectLocation
from basstler.repository import Repository
from basstler.setup_steps import PersonalNotesSetting


class RepositoryLocation(PathEnumeration):
    """
    This repository's own parts the suites read: the plugin the hooks and skills ship
    in, and the workflows.

    Found from the package's source tree rather than through
    :class:`basstler.locations.PluginLocation`, so a plugin root set in the environment
    running the suite cannot point the tests at another copy.
    """

    ROOT = PackageLocation.SOURCE_TREE.value
    """
    The repository root.
    """

    PLUGIN = ROOT / "plugin"
    """
    The Claude Code plugin: its manifest, hooks and skills.
    """

    PLUGIN_MANIFEST = PLUGIN / ".claude-plugin" / "plugin.json"
    """
    The plugin's manifest, the one place the release's version is written.
    """

    HOOKS = PLUGIN / "hooks"
    """
    The shell entry points under test.
    """

    WORKFLOWS = ROOT / ".github" / "workflows"
    """
    The repository's Actions workflows.
    """


class DatasetLocation(PathEnumeration):
    """
    This suite's own test data, next to the tests that read it.
    """

    DIRECTORY = Path(__file__).parent / "dataset"
    """
    The dataset directory itself.
    """

    STUBS = DIRECTORY / "stubs"
    """
    Executables copied onto a scratch ``PATH`` to stand in for a real ``gh``, ``curl`` or
    hook script.
    """

    UPSTREAM_REVIEW_RESPONSES = DIRECTORY / "upstream-review-responses"
    """
    The recorded GraphQL responses the upstream review reader is replayed against.
    """

    INSTALLED_DISTRIBUTIONS = DIRECTORY / "installed-distributions"
    """
    A directory that reads as installed distributions once it is on ``sys.path``, holding one
    whose name is spelled with every separator a distribution name may use.
    """

    UNINSTALLED_PROJECT = DIRECTORY / "uninstalled-project" / "pyproject.toml"
    """
    The metadata of a project no environment has installed, declaring no dependencies.
    """

    PARTLY_INSTALLED_PROJECT = DIRECTORY / "partly-installed-project" / "pyproject.toml"
    """
    A project declaring one dependency that is installed, then one that cannot be.
    """

    PLAN = DIRECTORY / "plan.yaml"
    """
    A minimal plan the dashboard builds.
    """

    ROADMAP = DIRECTORY / "roadmap.md"
    """
    The roadmap saved beside :attr:`PLAN`.
    """

    PLAN_WITH_UNKNOWN_STATUS = DIRECTORY / "plan-with-unknown-status.yaml"
    """
    The same plan, its item's status one the schema does not define.
    """

    STACK_CONFIGURATION = DIRECTORY / "stack-configuration"
    """
    Shipped defaults and a project's own stack settings, for layering one over the other.
    """

    SCRATCH_FORK_STACK_CONFIGURATION = STACK_CONFIGURATION / "scratch-fork.toml"
    """
    The stack settings a scratch fork checkout commits, naming the upstream its tests
    stand up.
    """

    COMMITTED_DEFAULT_STACK_CONFIGURATION = (
        STACK_CONFIGURATION / "committed-default.toml"
    )
    """
    A project's committed settings naming every default, beneath a personal-notes
    override.
    """

    SET_UP_CHECKOUT = DIRECTORY / "set-up-checkout"
    """
    A committed tree of everything ``check-setup.sh`` requires of the basstler checkout a
    plugin runs from, copied over a scratch checkout rather than written out file by file.

    Its plugin files stand in for the real ones: the ``tooling_files`` check tests only that
    each path exists, so nothing there is ever run.
    """

    SET_UP_PROJECT = DIRECTORY / "set-up-project"
    """
    A committed tree of everything ``check-setup.sh`` requires of a set-up project, copied
    over a scratch project root.
    """


class DatasetPlan(StrEnum):
    """
    What the dataset's plans are known by.
    """

    IDENTIFIER = "test-plan"
    """
    The ``id`` :attr:`DatasetLocation.PLAN` carries, and so the plan id it is saved
    under.
    """


class SavePlanOption(StrEnum):
    """
    The options ``save-plan.sh`` reads its plan from files with.
    """

    MANIFEST = "--manifest"
    """
    The plan.yaml to save.
    """

    ROADMAP = "--roadmap"
    """
    The roadmap.md to save beside it.
    """


class StackBranch(StrEnum):
    """
    The branches a stack under test is built from, named once for every suite that
    builds one.

    A suite names several of them per test, in a board entry, a git command and an
    assertion at once, so a spelling that differs anywhere is a test quietly about a
    branch its stack does not contain.
    """

    PARENT = "a-parent"
    """
    The bottom of the chain, cut from the base.
    """

    CHILD = "a-child"
    """
    Stacked directly on the parent.
    """

    BASE = "main"
    """
    The upstream base every stack in the suites ultimately targets.
    """

    ENGINE = "engine"
    """
    The bottom of a three-deep stack, cut from the base.
    """

    ENGINE_UI = "engine-ui"
    """
    Stacked on :attr:`ENGINE`.
    """

    ENGINE_DOCS = "engine-docs"
    """
    Stacked on :attr:`ENGINE_UI`, the top of the three-deep stack.
    """

    PARSER = "parser"
    """
    A single branch cut from the base, beside the three-deep stack.
    """

    FEATURE = "feature"
    """
    The one branch of a stack that needs no other.
    """

    FIRST_ROOT = "first-root"
    """
    One of two branches cut from the base.
    """

    SECOND_ROOT = "second-root"
    """
    The other of two branches cut from the base.
    """

    CHILD_OF_FIRST_ROOT = "child-of-first-root"
    """
    Stacked on :attr:`FIRST_ROOT`.
    """

    LANDED = "landed"
    """
    A branch already in the upstream base.
    """

    LANDED_ELSEWHERE = "landed-elsewhere"
    """
    A parent in the upstream base that no open pull request describes.
    """

    UNLANDED_ELSEWHERE = "unlanded-elsewhere"
    """
    A parent no open pull request describes and that is not in the upstream base.
    """

    OFF_BOARD_PARENT = "off-board-parent"
    """
    A parent other than the base that the board carries no pull request for.
    """

    UNDER_REVIEW = "under-review"
    """
    A branch in the upstream review queue.
    """

    WORK_IN_PROGRESS = "work-in-progress"
    """
    A drafted branch, still being worked on.
    """

    STUCK = "stuck"
    """
    A branch withheld for conflict resolution.
    """

    FINE = "fine"
    """
    A branch beside :attr:`STUCK` that nothing holds back.
    """


class StackLabel(StrEnum):
    """
    The labels the workflow under test reads and writes, named once for every suite that
    puts one on a pull request.

    A label is written into a board entry, handed to a command and read back in an
    assertion, so a suite that spells it is holding the code to a name nothing else in
    the suite has to agree with.
    """

    IN_REVIEW = "in-review"
    """
    Carried by a branch that has reached the upstream review queue.
    """

    REBASE = "rebase"
    """
    Authorises rewriting a branch's published history rather than merging into it.
    """

    NEEDS_RESOLUTION = "needs-resolution"
    """
    Put on a branch whose owner has been asked to resolve a conflict.
    """

    BUG = "bug"
    """
    Carried by a fix, and never acted on by this tooling - a label it reads past.
    """

    SOMEBODY_ELSES = "a-label-somebody-else-put-here"
    """
    Stands for whatever else a pull request happens to carry - the labels a write must
    preserve precisely because this tool knows nothing about them.
    """


class StackPullRequestNumber(IntEnum):
    """
    The numbers of the fork pull requests the two-branch stack under test is made of.

    A number is written into a board entry, keyed into a recorded write and read back in
    an assertion, so it is named once rather than spelled at each of those places.
    """

    PARENT = 40
    """
    The pull request of :attr:`StackBranch.PARENT`.
    """

    CHILD = 41
    """
    The pull request of :attr:`StackBranch.CHILD`, based on the parent's.
    """


class PromotionSampleText(StrEnum):
    """
    The text a promotion test puts into a fork pull request and finds again in what the
    routine writes back.
    """

    TITLE = "A parent branch"
    """
    The parent pull request's title.
    """

    SUMMARY = "What this branch does."
    """
    The first paragraph of the parent pull request's description.
    """

    DETAIL = "More detail."
    """
    The paragraph after it.
    """

    PROSE = "Prose."
    """
    A description's text before its Promote section.
    """

    FIRST_LINK = "https://example.invalid/first"
    """
    The create-link a first promotion writes.
    """

    SECOND_LINK = "https://example.invalid/second"
    """
    The create-link a second promotion writes in its place.
    """

    COMMENT_LINK_PREFIX = "https://example.invalid/comment/"
    """
    What a recorded comment's stand-in URL starts with, before the comment's position.
    """


class SkillDirectory(PathEnumeration):
    """
    The skills the suites read, relative to the plugin root.

    Claude Code finds a skill by its path, so the path *is* the interface, and the package
    does not name it.
    """

    DIRECTORY = Path("skills")
    """
    The directory holding every skill.
    """

    PLAN_DASHBOARD = DIRECTORY / "plan-dashboard"
    """
    The dashboard skill: its instructions, its worked example and its shell entry point.
    """

    STACKED_PULL_REQUEST_MAINTENANCE = DIRECTORY / "stacked-pr-maintenance"
    """
    The maintenance pass's own instructions.
    """

    DASHBOARD_REFRESH_SCRIPT = PLAN_DASHBOARD / "refresh_dashboard.sh"
    """
    The dashboard skill's shell entry point.
    """


class ScratchBranch(StrEnum):
    """
    The branches a scratch repository is given besides a stack's own.
    """

    PERSONAL_NOTES = PersonalNotesSetting.BRANCH.default
    """
    The personal-notes branch name the hooks resolve to by default.
    """

    WORK = "some-work-branch"
    """
    The throwaway branch a scratch repository is left checked out on.
    """


class PersonalNotesPath(PathEnumeration):
    """
    The files the shell hooks read from the personal-notes branch or write into a clone,
    relative to the project root, that the package itself does not name.
    """

    LOCAL_INSTRUCTIONS = Path("CLAUDE.local.md")
    """
    The clone's private instructions, which the session start writes and save-plan.sh
    reads a plan out of.
    """

    GIT_IDENTITY = ProjectLocation.PERSONAL_NOTES / "git-identity"
    """
    The recorded git identity a clone with none of its own is given.
    """

    SETTINGS_ON_NOTES_BRANCH = ProjectLocation.PERSONAL_NOTES / "settings.local.json"
    """
    The Claude Code settings the branch carries.
    """

    LOCAL_SETTINGS = ProjectLocation.CLAUDE_CODE_DIRECTORY / "settings.local.json"
    """
    Where those settings are synced to in the clone - the file Claude Code itself reads,
    and writes its own permission grants into.
    """

    BRANCH_INDEX = ProjectLocation.PLANS / "_generated" / "branch-index.tsv"
    """
    The generated reverse index mapping an item's branch to the plan tracking it.
    """


class ScrubbedEnvironmentPrefix(StrEnum):
    """
    Variables a scratch run must not inherit, by the prefix of their name.

    The session running this suite legitimately has all of them set, and every one of them
    changes what a hook resolves - so a test asserting the default resolution has to be run
    without them rather than around them.
    """

    PERSONAL_NOTES = "CLAUDE_PERSONAL_NOTES_"
    """
    The personal-notes remote, branch and path overrides.
    """

    PROJECT_DIRECTORY = "CLAUDE_PROJECT_DIR"
    """
    The project Claude Code names, which the hooks resolve their project from first.
    """

    ENVIRONMENT_FILE = "CLAUDE_ENV_FILE"
    """
    The file a SessionStart hook exports variables to the session through.
    """

    BASSTLER = "BASSTLER_"
    """
    The plugin root, the package's home and anything else the configuration exports.
    """

    GIT_AUTHOR = "GIT_AUTHOR_"
    """
    The commit author git would otherwise take from the configuration.
    """

    GIT_COMMITTER = "GIT_COMMITTER_"
    """
    The committer git would otherwise take from the configuration.
    """


class ProjectTableKey(StrEnum):
    """
    The ``[project]`` keys the suites read that :class:`basstler.dependencies.PyprojectKey`
    does not name, since the package itself never reads them.
    """

    REQUIRES_PYTHON = "requires-python"
    """
    The version specifier an interpreter has to satisfy.
    """

    DYNAMIC = "dynamic"
    """
    The keys the build backend resolves rather than the table stating them.
    """


class ConfigurationVariable(StrEnum):
    """
    The variables of the shell configuration the tests read back, named once.
    """

    ENVIRONMENT_DIRECTORY = "BASSTLER_ENVIRONMENT_DIRECTORY"
    """
    The package's own environment.
    """

    ENVIRONMENT_INTERPRETER = "BASSTLER_ENVIRONMENT_INTERPRETER"
    """
    The interpreter of the package's own environment.
    """

    INSTALLED_SOURCE_FILE = "BASSTLER_INSTALLED_SOURCE_FILE"
    """
    The file recording what the environment's package was installed from.
    """

    PYTHON_REQUIREMENT = "BASSTLER_PYTHON_REQUIREMENT"
    """
    The interpreters the package supports.
    """

    INTERPRETER_CANDIDATES = "BASSTLER_INTERPRETER_CANDIDATES"
    """
    The supported interpreters looked for by name, separated by spaces.
    """

    HOME = "BASSTLER_HOME"
    """
    Where the package's environment and its installed ``uv`` live.
    """

    REPOSITORY_URL = "BASSTLER_REPOSITORY_URL"
    """
    The repository an installed plugin's package is installed from.
    """

    UV_DIRECTORY = "BASSTLER_UV_DIRECTORY"
    """
    Where a session start installs ``uv`` when it finds neither ``uv`` nor a supported
    interpreter.
    """


class RemoteName(StrEnum):
    """
    The git remote names the scratch checkouts are built with: the fork and upstream
    names the shipped ``stack.toml`` defaults to.
    """

    ORIGIN = "origin"
    """
    The name git gives the remote a checkout was cloned from.
    """

    UPSTREAM = "upstream"
    """
    The conventional name of the remote a fork was forked from.
    """

    MINE = "mine"
    """
    A remote pointing at the user's own fork, under a name no default matches.
    """

    THEIRS = "theirs"
    """
    A remote pointing at somebody else's fork, beside :attr:`MINE`.
    """

    BACKUP = "backup"
    """
    A remote at a local path, which names no repository.
    """

    UNEXPECTED = "a-name-nobody-expects"
    """
    A fork remote under a name no default or setting mentions.
    """

    PERSONAL_UPSTREAM = "my-own-upstream-name"
    """
    The upstream remote name a personal-notes override picks.
    """

    PREFERRED_UPSTREAM = "an-upstream-remote"
    """
    The name a missing upstream remote is to be added under.
    """


class StackRepository(Enum):
    """
    The repositories the stack suites' checkouts and configurations name.
    """

    FORK = Repository("a-fork-owner", "a-fork")
    """
    The fork a scratch checkout's remote points at.
    """

    SOMEBODY_ELSES_FORK = Repository("someone-else", "their-fork")
    """
    A fork other than the one the configuration names.
    """

    SAME_NAMED_FORK = Repository("a-fork-owner", "a-project")
    """
    A fork named like the upstream it was forked from.
    """

    ANOTHER_OWNERS_FORK = Repository("another-owner", "a-project")
    """
    A second fork of the upstream, beside :attr:`SAME_NAMED_FORK`.
    """

    UPSTREAM = Repository("an-upstream-owner", "a-project")
    """
    The upstream every fork here is forked from.
    """

    DIFFERENT_UPSTREAM = Repository("a-different-upstream", "a-project")
    """
    An upstream named on the command line in place of the committed one.
    """


class StackSampleText(StrEnum):
    """
    The text the stack suites feed in where only its shape matters.
    """

    CHECK_CONCLUSION = "failure"
    """
    A pull request's CI conclusion, carried through untouched.
    """

    SESSION_LINK = "https://claude.ai/code/session_x"
    """
    The session a pull request was opened from.
    """

    TITLE = "A title"
    """
    A promotion link's title.
    """

    BODY = "A body"
    """
    A promotion link's description.
    """

    SHORT_BODY = "short"
    """
    A description well within the link's length limit.
    """

    TITLE_WITH_SEPARATORS = "Fix A & B"
    """
    A title holding a character that would end a query parameter unencoded.
    """

    BODY_WITH_FRAGMENT = "see #106"
    """
    A description holding a character that would start a URL fragment unencoded.
    """

    FILLER = "x"
    """
    One character, repeated to make a text too long for a link.
    """

    LOCAL_PATH_REMOTE = "/srv/git/mirror"
    """
    A remote URL that is a local path rather than a repository.
    """

    UNRELATED_FILE = "README.md"
    """
    A notes-branch file that is not the stack configuration.
    """

    UNRELATED_CONTENT = "unrelated\n"
    """
    Its content.
    """

    UNKNOWN_COMMAND = "not-a-command"
    """
    A command the tool does not answer.
    """

    NOT_A_REPOSITORY = "not-a-repository"
    """
    A repository reference missing its ``owner/`` part.
    """


class HatchVersionKey(StrEnum):
    """
    The path through ``pyproject.toml`` to the build's version source, and that source's
    keys.
    """

    TOOL = "tool"
    """
    The table every tool's settings sit under.
    """

    HATCH = "hatch"
    """
    The build backend's own table.
    """

    VERSION = "version"
    """
    Where the backend is told to read the version from, and the name it requires of the
    pattern's group that captures the version.
    """

    PATH = "path"
    """
    The file the version is read out of, relative to the repository root.
    """

    PATTERN = "pattern"
    """
    The regular expression whose ``version`` group is the version.
    """

    @classmethod
    def version_table(cls, pyproject: dict[str, Any]) -> dict[str, str]:
        """
        :param pyproject: A parsed ``pyproject.toml``.
        :return: Its ``[tool.hatch.version]`` table.
        """
        return pyproject[cls.TOOL][cls.HATCH][cls.VERSION]


class PluginManifestKey(StrEnum):
    """
    The keys of a Claude Code plugin's ``plugin.json`` the suites read.
    """

    NAME = "name"
    """
    The plugin's name, which is also its package's distribution name.
    """

    VERSION = "version"
    """
    The plugin's release, which its package is installed at.
    """


class EnvironmentVariable(StrEnum):
    """
    The standard environment variables a test sets or reads for a subprocess.
    """

    EXECUTABLE_SEARCH_PATH = "PATH"
    """
    The directories a shell searches for a command.
    """

    IMPORT_PATH = "PYTHONPATH"
    """
    The directories an interpreter searches for imports ahead of its installed packages.
    """


class StubVariable(StrEnum):
    """
    The environment variables the stubs under ``dataset/stubs`` read.
    """

    PIP_CALL_LOG = "STUB_PIP_CALL_LOG"
    """
    The file the ``pip`` stub appends each invocation to.
    """

    PIP_STATUS = "STUB_PIP_STATUS"
    """
    The exit status the ``pip`` stub reports.
    """

    PIP_INSTALLED_UV = "STUB_PIP_INSTALLED_UV"
    """
    The script a ``uv`` installed by the ``pip`` stub runs.
    """

    UV_CALL_LOG = "STUB_UV_CALL_LOG"
    """
    The file the ``uv`` stub appends each invocation to.
    """

    UV_STATUS = "STUB_UV_STATUS"
    """
    The exit status the ``uv`` stub reports.
    """

    UV_PYTHON = "STUB_UV_PYTHON"
    """
    The interpreter an environment the ``uv`` stub creates runs.
    """


class PackageManager(StrEnum):
    """
    The executables the session start installs packages with, each named as it is on
    ``PATH`` and as its stub is under ``dataset/stubs``.
    """

    PIP = "pip"
    """
    The package installer every interpreter ships, used where there is no ``uv``.
    """

    UV = "uv"
    """
    The package manager that also creates environments and fetches interpreters.
    """


class FileMode(IntEnum):
    """
    The permission bits a test gives a file it writes.
    """

    EXECUTABLE = 0o755
    """
    Readable and runnable by everyone, writable by its owner.
    """


class ReleaseSampleVersion(StrEnum):
    """
    The versions a scratch checkout's plugin manifest names in the release-version tests.
    """

    RELEASED = "1.0.0"
    """
    The version the scratch checkout is tagged at.
    """

    NEXT_PATCH = "1.0.1"
    """
    :attr:`RELEASED` with its patch part bumped, not tagged yet.
    """

    NEXT_MINOR = "1.1.0"
    """
    :attr:`RELEASED` with its minor part bumped.
    """

    NEXT_MAJOR = "2.0.0"
    """
    :attr:`RELEASED` with its major part bumped.
    """

    CHOSEN = "3.4.5"
    """
    A version given explicitly rather than incremented.
    """


class ReleaseSampleFile(PathEnumeration):
    """
    The files of a scratch checkout the release-version tests change, relative to its
    root.
    """

    PACKAGE_MODULE = Path("src") / "sample" / "__init__.py"
    """
    A module of the scratch checkout's package.
    """

    SKILL = Path("plugin") / "skills" / "sample" / "SKILL.md"
    """
    A skill of the scratch checkout's plugin.
    """

    DOCUMENTATION = Path("docs") / "guide.md"
    """
    Documentation, which no install runs but which still makes a new release.
    """


class ReleaseSampleText(StrEnum):
    """
    File contents the release-version tests write.
    """

    MANIFEST = '{{\n  "name": "basstler",\n  "version": "{version}"\n}}\n'
    """
    A plugin manifest, formatted with its ``version``.
    """

    EXAMPLE_CALLER = (
        "    uses: owner/basstler/.github/workflows/upstream-reviews.yml@v{version}\n"
        "    with:\n"
        "      basstler_ref: v{version}\n"
    )
    """
    The example caller's two references to the release, formatted with its ``version``.
    """

    CHANGE = "changed = True\n"
    """
    What a test writes to change a file.
    """
