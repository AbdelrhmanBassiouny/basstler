"""
Contract tests for the prose a stacked-PR maintenance pass runs on.

``.claude/skills/stacked-pr-maintenance/SKILL.md`` is the doctrine a run executes, and
``POINTER.md`` is the prompt registered with the cloud Routine that resolves it. Four
things are pinned. First, the base-change rule: a pull request's base branch can only be
changed through the GitHub MCP server, since the same request issued through the session
git proxy is refused. Second, the pointer's shape, because what gets registered is the
fenced block rather than the whole file. Third, that the rules duplicated into the
pointer stay identical to the skill's. Fourth, that context resolution prefers what it
was told over what it can infer, since inference is the half that can fail.

All of it is prose rather than code, so nothing else would catch an edit that undid
them. The text being asserted on is declared in ``prompt_model.py`` rather than here, so
that renaming a section is one edit rather than one per assertion.
"""

from __future__ import annotations

from prompt_model import (
    MAINTENANCE_SKILL_DOCUMENT,
    MAINTENANCE_SKILL_PATH,
    POINTER_DOCUMENT,
    GitHubMcpTool,
    PointerPlaceholder,
    PromptDirective,
    PromptDocument,
    PromptLandmark,
    PromptRule,
)
from stack import CONFIGURATION_COMMAND, ExitCode, load_configuration

# %% the shape each document depends on


def test_the_pointer_has_exactly_one_registered_block():
    """
    The block between the fences is what gets pasted into the Routine, so a second one
    would make it ambiguous and none would leave nothing to register.
    """
    pointer = PromptDocument.load(POINTER_DOCUMENT)

    assert pointer.occurrences(PromptLandmark.EXECUTABLE_PROMPT_FENCE) == 1
    assert pointer.executable_prompt()


def test_the_pointer_carries_the_hard_rules_inside_the_registered_block():
    """
    Commentary outside the fence is not registered, so rules that must bind before any
    file is read have to sit inside it.
    """
    prompt = PromptDocument.load(POINTER_DOCUMENT).executable_prompt()

    assert PromptDirective.HARD_RULES in prompt
    assert (
        f"{PromptDirective.NEVER} call "
        f"`{GitHubMcpTool.SUBSCRIBE_PULL_REQUEST_ACTIVITY}`" in prompt
    )


def test_the_skill_states_the_whole_job_rather_than_delegating_it():
    """
    Until the skill is on the default branch it cannot be invoked by name, so the pointer
    reads the file instead - which only works while the file carries the rules and every
    phase itself.
    """
    skill = PromptDocument.load(MAINTENANCE_SKILL_DOCUMENT)

    assert PromptDirective.HARD_RULES in skill.text
    for phase in (PromptLandmark.PHASE_ONE, PromptLandmark.PHASE_TWO):
        assert skill.occurrences(phase) == 1


# %% resolving which repositories a run operates on


def step_zero() -> str:
    """
    :return: The skill's context-resolution step, up to the first step that acts.
    """
    return PromptDocument.load(MAINTENANCE_SKILL_DOCUMENT).section(
        PromptLandmark.CONTEXT_RESOLUTION, PromptLandmark.FORK_MAIN_UPDATE
    )


def test_step_zero_obtains_the_tooling_rather_than_assuming_it():
    """
    Every phase shells out to ``stack.py``, so a false assumption strands a run mid-way
    - and a phase 2 failure lands after phase 1 has already mutated pull requests.
    """
    assert "fetch" in step_zero()
    assert ".claude/stack/" in step_zero()


def test_step_zero_takes_the_tooling_ref_from_the_pointer():
    """
    Naming the branch here would bake one fork's in-flight branch into the shared
    doctrine.

    The pointer already had to name a ref to resolve this document at all.
    """
    assert "you were told to resolve this document from" in step_zero()


def test_step_zero_asks_the_tool_which_remote_is_which():
    """
    A checkout may call the fork anything, so names decide nothing.

    The document asks the tooling rather than writing remote names into git commands,
    which is what keeps a run from pointing pushes at the review repository.
    """
    skill = PromptDocument.load(MAINTENANCE_SKILL_DOCUMENT)
    configuration = load_configuration()

    assert CONFIGURATION_COMMAND in step_zero()
    assert f"{configuration.fork_remote}/" not in skill.text
    assert f"{configuration.upstream_remote}/" not in skill.text


def test_step_zero_prefers_what_it_was_told_over_what_it_can_infer():
    """
    Inference is the half that can fail, so an answer already in hand must be used
    before it is ever reached.
    """
    resolution = step_zero()

    given = resolution.index("**What you were given.**")
    inferred = resolution.index("**What the checkout knows.**")

    assert given < inferred


def test_step_zero_names_the_status_that_means_the_fork_is_unknown():
    """
    That status is the one failure a run can act on by asking, so it has to be
    recognisable as itself rather than as any non-zero exit.
    """
    assert f"status {ExitCode.REMOTES_UNRESOLVED.value}" in step_zero()


def test_a_run_that_cannot_ask_stops_rather_than_guessing():
    """
    A scheduled run has nobody to answer it, and its hard rules forbid opening a
    discussion - so the unresolved case must end the run, never pick a repository.
    """
    resolution = step_zero()

    non_interactive = resolution[resolution.index("If you were invoked with") :]

    assert "stop and report" in non_interactive


# %% the fork-specific parts stay in the pointer


def test_the_skill_carries_no_placeholder_a_run_would_have_to_resolve():
    """
    The doctrine is executed as written, so an unsubstituted placeholder would reach a
    run as an instruction it cannot follow.

    Everything fork-specific belongs in the pointer, which is substituted by hand at
    registration time.
    """
    skill = PromptDocument.load(MAINTENANCE_SKILL_DOCUMENT)

    unresolved = [
        placeholder
        for placeholder in PointerPlaceholder
        if placeholder.value in skill.text
    ]

    assert unresolved == []


def test_the_skill_names_no_fork_of_its_own():
    """
    The fork is configuration, so the doctrine has to read it rather than spell it out:
    it runs on whichever fork registered it, so an owner named here is an instruction to
    operate on somebody else's repository.
    """
    skill = PromptDocument.load(MAINTENANCE_SKILL_DOCUMENT)

    fork = load_configuration().fork_repository

    assert fork.owner not in skill.text
    assert str(fork) not in skill.text


def test_the_pointer_marks_every_fork_specific_value_as_a_placeholder():
    """
    The pointer is the one document that must name repositories and a branch, so it is
    also the one that has to be templated for anyone else to register it.
    """
    prompt = PromptDocument.load(POINTER_DOCUMENT).executable_prompt()

    for placeholder in PointerPlaceholder:
        assert placeholder in prompt


def test_the_pointer_hands_over_both_repositories_so_nothing_is_inferred():
    """
    The pointer knows both, and passing them is what lets a scheduled run resolve its
    context without a question it has nobody to ask.
    """
    prompt = PromptDocument.load(POINTER_DOCUMENT).executable_prompt()

    assert f"fork={PointerPlaceholder.FORK_REPOSITORY}" in prompt
    assert f"upstream={PointerPlaceholder.UPSTREAM_REPOSITORY}" in prompt
    assert "--non-interactive" in prompt


def test_the_pointer_sends_the_run_to_the_maintenance_skill():
    """
    The pointer's whole purpose is to delegate, so it must name the file to resolve;
    carrying instructions of its own is how the two drift apart.
    """
    prompt = PromptDocument.load(POINTER_DOCUMENT).executable_prompt()

    assert str(MAINTENANCE_SKILL_PATH) in prompt


def test_the_pointer_hard_rules_match_the_skill_exactly():
    """
    The rules must bind before any file is read, so the pointer carries its own copy - the
    one duplication in this workflow, and the only place drift can reappear.
    """
    skill = PromptDocument.load(MAINTENANCE_SKILL_DOCUMENT)
    pointer = PromptDocument.load(POINTER_DOCUMENT)

    assert pointer.hard_rules() == skill.hard_rules()


# %% the base-change client


def test_the_skill_names_the_one_client_that_can_change_a_base():
    """
    The rule exists, is stated once, and names the tool that actually works.
    """
    skill = PromptDocument.load(MAINTENANCE_SKILL_DOCUMENT)

    assert skill.occurrences(PromptRule.BASE_CHANGE) == 1
    assert GitHubMcpTool.UPDATE_PULL_REQUEST in skill.paragraph(PromptRule.BASE_CHANGE)


def test_the_skill_records_that_the_git_proxy_refuses_a_base_change():
    """
    The refusal is recorded with its status code and the client that earns it, so a run
    that hits it recognises the known, documented case rather than an unexplained
    failure to improvise around.
    """
    rule = PromptDocument.load(MAINTENANCE_SKILL_DOCUMENT).paragraph(
        PromptRule.BASE_CHANGE
    )

    assert PromptRule.BASE_CHANGE.refusal_status_code in rule
    assert PromptRule.BASE_CHANGE.refused_client in rule


# %% the reparent sequences


def test_native_stack_reparent_changes_the_base_rather_than_replacing_the_pull_request():
    """
    Reparenting keeps the pull request, its number and its review thread.

    Closing the orphan and opening a replacement was considered while the base change
    was believed impossible from a session; it is not, so the sequence must not drift
    back to it.
    """
    phase_one = PromptDocument.load(MAINTENANCE_SKILL_DOCUMENT).section(
        PromptLandmark.PHASE_ONE, PromptLandmark.PHASE_TWO
    )

    sequence = phase_one[phase_one.index(PromptLandmark.NATIVE_STACK_MEMBERS.text) :]

    assert GitHubMcpTool.UPDATE_PULL_REQUEST in sequence
    assert GitHubMcpTool.CREATE_PULL_REQUEST not in sequence


def test_both_reparent_sites_are_reached_from_the_one_base_change_rule():
    """
    The rule is stated once, before both sites, so neither can prescribe a client of its
    own.
    """
    phase_one = PromptDocument.load(MAINTENANCE_SKILL_DOCUMENT).section(
        PromptLandmark.PHASE_ONE, PromptLandmark.PHASE_TWO
    )

    rule = phase_one.index(PromptRule.BASE_CHANGE.text)
    orphan_sweep = phase_one.index(PromptLandmark.ORPHANED_CHILD_SWEEP.text)
    landed_branch_list = phase_one.index(PromptLandmark.MERGED_PARENT_LIST.text)

    assert rule < orphan_sweep < landed_branch_list
    assert (
        GitHubMcpTool.UPDATE_PULL_REQUEST
        in phase_one[
            orphan_sweep : phase_one.index(PromptLandmark.NATIVE_STACK_MEMBERS.text)
        ]
    )
