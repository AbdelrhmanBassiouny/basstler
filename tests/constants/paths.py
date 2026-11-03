"""
Paths more than one suite reads: the repository, the dataset, skills and notes.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from basstler.locations import PackageLocation, PathEnumeration, ProjectLocation


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

    PLUGIN_PROBE = ROOT / "plugin-probe"
    """
    The throwaway plugin that reports what a plugin receives in a cloud session.
    """

    PLUGIN_PROBE_SERVER = PLUGIN_PROBE / "scripts" / "probe-server.sh"
    """
    The probe's MCP server.
    """

    WORKFLOWS = ROOT / ".github" / "workflows"
    """
    The repository's Actions workflows.
    """

    RELEASE_WORKFLOW = WORKFLOWS / "release.yml"
    """
    The workflow that tags a merge commit as a release.
    """

    PLAN_SITE_BUILD_WORKFLOW = WORKFLOWS / "plan-site-build.yml"
    """
    The reusable workflow that builds the plan site and deploys a changed one.
    """


class DatasetLocation(PathEnumeration):
    """
    This suite's own test data, next to the tests that read it.
    """

    DIRECTORY = Path(__file__).parents[1] / "dataset"
    """
    The dataset directory itself.
    """

    BOOTSTRAP_PLAN = DIRECTORY / "bootstrap-plan.yaml"
    """
    The item-bootstrap fixture plan: two items, a folded note, blank lines between
    items.
    """

    FLUSH_SEQUENCES_PLAN = DIRECTORY / "flush-sequences-plan.yaml"
    """
    :attr:`BOOTSTRAP_PLAN` with every sequence written flush with its key instead of
    indented under it.
    """

    BOOTSTRAP_ROADMAP = DIRECTORY / "bootstrap-roadmap.md"
    """
    The item-bootstrap fixture plan's roadmap.
    """

    MERGE_NEW_ITEM = DIRECTORY / "merge-new-item.yaml"
    """
    One item block, indented like :attr:`BOOTSTRAP_PLAN`'s items, that one writer adds.
    """

    ROADMAP_WITH_SESSION_RULE = DIRECTORY / "bootstrap-roadmap-session-rule.md"
    """
    :attr:`BOOTSTRAP_ROADMAP` with a rule the saving session added.
    """

    ROADMAP_WITH_CONCURRENT_RULE = DIRECTORY / "bootstrap-roadmap-concurrent-rule.md"
    """
    :attr:`BOOTSTRAP_ROADMAP` with a different rule another writer added meanwhile.
    """

    CONCURRENT_WRITER_HOOK = DIRECTORY / "concurrent-writer-pre-push.sh"
    """
    A pre-push hook that pushes another writer's commit to the notes branch ahead of
    the push it runs for.
    """

    PROTECTED_MAIN_HOOK = DIRECTORY / "refuse-main-pre-receive.sh"
    """
    A pre-receive hook that refuses every push updating ``main``, as a protected default
    branch does.
    """

    PULL_REQUEST_DATA_KEYED_BY_NUMBER = DIRECTORY / "pr-data-keyed-by-number.json"
    """
    A ``pr_data.json`` missing its repository level: one pull request keyed by its
    number alone.
    """

    ACTION_RESULT_WITHOUT_REQUEST_IDENTIFIER = (
        DIRECTORY / "action-result-without-request-identifier.json"
    )
    """
    A result an Action release from before results named their request committed.
    """

    PLAN_SITE_RUNS_SUCCEEDED = DIRECTORY / "plan-site-runs-succeeded.json"
    """
    A site repository's run listing whose latest plan-site run succeeded.
    """

    PLAN_SITE_DISPATCH_RUNS_SUCCEEDED = (
        DIRECTORY / "plan-site-dispatch-runs-succeeded.json"
    )
    """
    A notes repository's run listing whose latest dispatch run succeeded.
    """

    PLAN_SITE_DISPATCH_RUNS_FAILED = DIRECTORY / "plan-site-dispatch-runs-failed.json"
    """
    A notes repository's run listing whose latest dispatch run failed after an earlier
    one succeeded.
    """

    PLAN_SITE_DISPATCH_RUNS_NEVER_SUCCEEDED = (
        DIRECTORY / "plan-site-dispatch-runs-never-succeeded.json"
    )
    """
    A notes repository's run listing in which no dispatch run succeeded.
    """

    PLAN_SITE_TOKEN_STORED_BEFORE_FAILURE = (
        DIRECTORY / "plan-site-token-stored-before-failure.json"
    )
    """
    A notes repository's token secret, set before its recorded failed dispatch run.
    """

    PLAN_SITE_TOKEN_STORED_AFTER_FAILURE = (
        DIRECTORY / "plan-site-token-stored-after-failure.json"
    )
    """
    A notes repository's token secret, set after its recorded failed dispatch run.
    """

    WORKFLOW_RUNS_NONE = DIRECTORY / "workflow-runs-none.json"
    """
    A run listing with no runs at all.
    """

    REPOSITORY_FORK = DIRECTORY / "repository-fork.json"
    """
    A repository's REST response for a fork.
    """

    REPOSITORY_NOT_FORK = DIRECTORY / "repository-not-fork.json"
    """
    A repository's REST response for a repository that is not a fork.
    """

    MERGE_WORKFLOW_PULL_REQUEST = DIRECTORY / "merge-workflow-pull-request.json"
    """
    The REST response for the pull request proposing the plan site's merge workflow.
    """

    PULL_REQUEST_REFUSED = DIRECTORY / "pull-request-refused.json"
    """
    GitHub's answer refusing to open a pull request for a token without the right.
    """

    PROMOTION_SUMMARIES = DIRECTORY / "promotion-summaries.json"
    """
    What a session writes for the upstream pull requests of the two-branch stack: points
    and a title for the parent, nothing for the child.
    """

    DESCRIPTION_WITH_PROMOTION_PROSE = DIRECTORY / "description-with-promotion-prose.md"
    """
    A fork pull request description whose own prose has a heading starting like the
    promotion heading, followed by a sentence and a code fence.
    """

    PLAN_WITH_LANDED_ITEMS = DIRECTORY / "plan-with-landed-items.yaml"
    """
    A plan with a tracking issue and three items: one landed, one in progress that
    depends on it, and one not started that depends on both.
    """

    PLAN_ALL_LANDED = DIRECTORY / "plan-all-landed.yaml"
    """
    A plan every item of which has landed.
    """

    ROADMAP_OF_STANDING_RULES = DIRECTORY / "roadmap-of-standing-rules.md"
    """
    A roadmap in the shape the limits accept, whose last entry wraps onto a second line.
    """

    ROADMAP_WITH_DATED_SECTION = DIRECTORY / "roadmap-with-dated-section.md"
    """
    A roadmap a session appended a dated section to.
    """

    PULL_REQUESTS_BY_BRANCH = DIRECTORY / "pull-requests-by-branch.json"
    """
    A recorded pull request listing, one pull request for each
    :class:`ProgressBranch` that has one.
    """

    PLANS = DIRECTORY / "plans"
    """
    A plans directory the cross-plan reference tests resolve against: one subdirectory
    per fixture plan.
    """

    STUBS = DIRECTORY / "stubs"
    """
    Executables copied onto a scratch ``PATH`` to stand in for a real ``gh``, ``curl`` or
    hook script.
    """

    DISPATCH_CHECK_NEEDS_SETUP_STUB = STUBS / "dispatch_check_needs_setup.py"
    """
    A module standing in for :mod:`basstler.plan_site.dispatch_check`, reporting a
    dispatch that needs setup.
    """

    UPSTREAM_REVIEW_RESPONSES = DIRECTORY / "upstream-review-responses"
    """
    The recorded GraphQL responses the upstream review reader is replayed against.
    """

    BRIEF_PLAN = DIRECTORY / "brief-plan.yaml"
    """
    A plan whose one item depends on a merged item, a draft item and an item of
    another plan.
    """

    BRIEF_ROADMAP = DIRECTORY / "brief-roadmap.md"
    """
    The standing rules of :attr:`BRIEF_PLAN`, one of them wrapped across two lines.
    """

    SITE_PLANS = DIRECTORY / "site-plans"
    """
    A ``plans`` directory as the notes branch carries it: two valid plans, one whose
    manifest fails validation, and the generated directory that holds no plan.
    """

    ACTIONS_BUDGET = DIRECTORY / "actions-budget"
    """
    A budget manifest and one small workflow per rule it holds a workflow to.
    """

    ACTIONS_BUDGET_WORKFLOWS = ACTIONS_BUDGET / "workflows"
    """
    The workflows the dataset's manifest declares, each breaking the rule its name says.
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
    A minimal plan the plan site builds.
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


class RecordedCommitChecks(PathEnumeration):
    """
    The check-run listings and combined statuses the API answers for one commit, as
    recorded.
    """

    DIRECTORY = DatasetLocation.DIRECTORY / "commit-checks"
    """
    The directory holding them.
    """

    ONE_CHECK_RUN_FAILING = DIRECTORY / "check-runs-one-failing.json"
    """
    Three check runs: ``pytest`` failed, ``lint`` passed, ``docs`` is still running.
    """

    ONE_CHECK_RUN_RUNNING = DIRECTORY / "check-runs-one-running.json"
    """
    Two check runs: ``pytest`` is queued and ``lint`` passed.
    """

    EVERY_CHECK_RUN_FINISHED = DIRECTORY / "check-runs-all-finished.json"
    """
    Three finished check runs, ending in success, skipped and neutral.
    """

    NO_CHECK_RUNS = DIRECTORY / "check-runs-none.json"
    """
    A listing with no check runs in it.
    """

    NO_STATUSES = DIRECTORY / "status-none.json"
    """
    A combined status no integration reported to.
    """

    ONE_STATUS_ERRORING = DIRECTORY / "status-one-erroring.json"
    """
    Two statuses: ``legacy-ci`` errored and ``coverage`` succeeded.
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

    STACKED_PULL_REQUEST_MAINTENANCE = DIRECTORY / "stacked-pr-maintenance"
    """
    The maintenance pass's own instructions.
    """

    PLAN_CREATE = DIRECTORY / "plan-create"
    """
    The skill that creates a plan, beside the schema reference and the worked example.
    """

    PLAN_ITEM_KICKOFF = DIRECTORY / "plan-item-kickoff"
    """
    The instructions a kickoff run follows.
    """

    PLAN_ITEM_RESOLVE = DIRECTORY / "plan-item-resolve"
    """
    The instructions a resolve run follows.
    """

    UPSTREAM_REVIEWS = DIRECTORY / "upstream-reviews"
    """
    The instructions for reading a branch's upstream review threads.
    """

    RUNNING_COMMANDS_DOCUMENT = DIRECTORY / "running-commands.md"
    """
    How every skill runs its commands, which each skill's instructions link.
    """

    MANIFEST_STALENESS_DOCUMENT = PLAN_CREATE / "manifest-staleness.md"
    """
    The rule every skill that writes plan data cites: when to write the manifest.
    """

    @classmethod
    def skills(cls) -> tuple[SkillDirectory, ...]:
        """
        :return: Every member that is a skill's own directory.
        """
        return tuple(
            member
            for member in cls
            if member.parent == cls.DIRECTORY.value and not member.suffix
        )


class SkillFile(StrEnum):
    """
    The files every skill directory carries.
    """

    INSTRUCTIONS = "SKILL.md"
    """
    The instructions Claude Code loads the skill from.
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

    PULL_REQUEST_PROGRESS = ProjectLocation.PERSONAL_NOTES / "pr-progress"
    """
    The directory holding each pull request branch's progress notes, by branch name.
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


class ProseSnippet(PathEnumeration):
    """
    Python sources the prose length check measures.
    """

    DIRECTORY = DatasetLocation.DIRECTORY / "prose-length"
    """
    The directory holding them.
    """

    OVERLONG_MODULE_DOCSTRING = DIRECTORY / "overlong-module-docstring.py"
    """
    A module docstring of five prose lines.
    """

    FIELDS_AND_LITERAL_BLOCKS = DIRECTORY / "fields-and-literal-blocks.py"
    """
    A function docstring of two prose lines, a literal block and a field list.
    """

    OVERLONG_ATTRIBUTE_DOCSTRING = DIRECTORY / "overlong-attribute-docstring.py"
    """
    A class whose attribute docstring holds five prose lines.
    """

    COMMENT_BLOCKS = DIRECTORY / "comment-blocks.py"
    """
    A section header above a three-line comment block, a trailing comment, and a
    four-line comment block.
    """


class DocstringSnippet(PathEnumeration):
    """
    Python sources the missing docstring check reads.
    """

    DIRECTORY = DatasetLocation.DIRECTORY / "missing-docstrings"
    """
    The directory holding them.
    """

    UNDOCUMENTED_DEFINITIONS = DIRECTORY / "undocumented-definitions.py"
    """
    A documented module whose class leaves a field, an override of an implemented
    method and a new method undocumented, and implements an abstract method without a
    docstring.
    """

    UNIMPORTABLE_DEFINITIONS = DIRECTORY / "unimportable-definitions.py"
    """
    A documented module that raises on import, leaving a method and a function
    undocumented.
    """

    NO_MODULE_DOCSTRING = DIRECTORY / "no-module-docstring.py"
    """
    A module without a docstring holding one documented function.
    """

    DOCUMENTED_MODULE = DIRECTORY / "documented-module.py"
    """
    A module breaking no rule a checker enforces.
    """


class RuleSectionsFile(PathEnumeration):
    """
    The sections the ``AGENTS.md`` generation tests render, and what they render to.
    """

    DIRECTORY = DatasetLocation.DIRECTORY / "code_rules"
    """
    The directory holding them.
    """

    EXPECTED_TEXT = DIRECTORY / "rule-sections.md"
    """
    The text of the sections in ``rule_sections.py``, with placeholders for the module's
    path and the commands' invocations.
    """
