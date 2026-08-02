"""
Contract tests for the prompt documents the live cloud Routine runs on.

``ROUTINE.md`` is read from git and executed at the start of every run; ``POINTER.md``
is the prompt registered with the Routine that resolves it. Three things are pinned.
First, the base-change rule: a pull request's base branch can only be changed through
the GitHub MCP server, since the same request issued through the session git proxy is
refused. Second, each document's shape, because the Routine locates what to execute by
the fenced block rather than by reading the whole file. Third, that the rules duplicated
into the pointer stay identical to the doctrine's.

All three are prose rather than code, so nothing else would catch an edit that undid
them. The text being asserted on is declared in ``doctrine.py`` rather than here, so
that renaming a section is one edit rather than one per assertion.
"""

from __future__ import annotations

from doctrine import (
    DOCTRINE_DOCUMENT,
    POINTER_DOCUMENT,
    DoctrineLandmark,
    GitHubMcpTool,
    PointerPlaceholder,
    PromptDirective,
    PromptDocument,
)

# %% the shape the Routine's prompt depends on


def test_doctrine_has_exactly_one_executable_prompt_block():
    """
    The Routine is told to execute the fenced block, so a second one would make that
    instruction ambiguous and none would leave it with nothing to run.
    """
    doctrine = PromptDocument.load(DOCTRINE_DOCUMENT)

    assert doctrine.occurrences(DoctrineLandmark.EXECUTABLE_PROMPT_FENCE) == 1
    assert doctrine.executable_prompt()


def test_hard_rules_stay_inside_the_executable_block():
    """
    Commentary outside the fence is not executed, so moving the hard rules out would
    silently drop them from what the Routine actually runs.
    """
    prompt = PromptDocument.load(DOCTRINE_DOCUMENT).executable_prompt()

    assert PromptDirective.HARD_RULES in prompt
    assert (
        f"{PromptDirective.NEVER} call "
        f"`{GitHubMcpTool.SUBSCRIBE_PULL_REQUEST_ACTIVITY}`" in prompt
    )


def test_setup_obtains_the_tooling_rather_than_assuming_it():
    """
    Setup must make ``stack.py`` present rather than assert that it is.

    Every later phase shells out to it, so a false assumption strands the Routine
    mid-run - and a Phase 2 failure lands after Phase 1 has already mutated pull
    requests.
    """
    doctrine = PromptDocument.load(DOCTRINE_DOCUMENT)

    step_zero = doctrine.section(
        DoctrineLandmark.SETUP, DoctrineLandmark.FORK_MAIN_UPDATE
    )

    assert "fetch" in step_zero
    assert ".claude/stack/" in step_zero


# %% the fork-specific parts stay in the pointer


def test_setup_takes_the_tooling_ref_from_the_pointer():
    """
    Naming the branch here would bake one fork's in-flight branch into the shared
    doctrine.

    The pointer already had to name a ref to resolve this document at all, so deferring
    to it keeps that name in one place and leaves the doctrine usable by any fork
    unchanged.
    """
    doctrine = PromptDocument.load(DOCTRINE_DOCUMENT)

    step_zero = doctrine.section(
        DoctrineLandmark.SETUP, DoctrineLandmark.FORK_MAIN_UPDATE
    )

    assert "pointer" in step_zero


def test_doctrine_carries_no_placeholder_a_run_would_have_to_resolve():
    """
    The doctrine is executed verbatim, so an unsubstituted placeholder would reach the
    Routine as an instruction it cannot follow.

    Everything fork-specific belongs in the pointer, which is substituted by hand at
    registration time.
    """
    doctrine = PromptDocument.load(DOCTRINE_DOCUMENT)

    unresolved = [
        placeholder
        for placeholder in PointerPlaceholder
        if placeholder.value in doctrine.text
    ]

    assert unresolved == []


def test_pointer_marks_every_fork_specific_value_as_a_placeholder():
    """
    The pointer is the one document that must name a fork and a branch, so it is also
    the one that has to be templated for anyone else to register it.
    """
    pointer = PromptDocument.load(POINTER_DOCUMENT)

    prompt = pointer.executable_prompt()

    assert PointerPlaceholder.FORK_REPOSITORY in prompt
    assert PointerPlaceholder.TOOLING_BRANCH in prompt


def test_pointer_sends_the_routine_to_the_doctrine_document():
    """
    The pointer's whole purpose is to delegate, so it must name the file to resolve;
    carrying instructions of its own is how the two drift apart.
    """
    prompt = PromptDocument.load(POINTER_DOCUMENT).executable_prompt()

    assert str(DOCTRINE_DOCUMENT.relative_to(DOCTRINE_DOCUMENT.parents[2])) in prompt


def test_pointer_hard_rules_match_the_doctrine_exactly():
    """
    The rules must bind before any file is read, so the pointer carries its own copy - the one
    duplication in this workflow, and the only place drift can reappear.
    """
    doctrine = PromptDocument.load(DOCTRINE_DOCUMENT)
    pointer = PromptDocument.load(POINTER_DOCUMENT)

    assert pointer.hard_rules() == doctrine.hard_rules()


# %% the base-change client


def test_doctrine_names_the_one_client_that_can_change_a_base():
    """
    The rule exists, is stated once, and names the tool that actually works.
    """
    doctrine = PromptDocument.load(DOCTRINE_DOCUMENT)

    assert doctrine.occurrences(DoctrineLandmark.BASE_CHANGE_RULE) == 1
    assert GitHubMcpTool.UPDATE_PULL_REQUEST in doctrine.paragraph(
        DoctrineLandmark.BASE_CHANGE_RULE
    )


def test_doctrine_records_that_the_git_proxy_refuses_a_base_change():
    """
    The refusal is recorded with its status code, so a session that hits it recognises
    it as the known, documented case rather than an unexplained failure to improvise
    around.
    """
    rule = PromptDocument.load(DOCTRINE_DOCUMENT).paragraph(
        DoctrineLandmark.BASE_CHANGE_RULE
    )

    assert "403" in rule
    assert "curl" in rule


# %% the reparent sequences


def test_native_stack_reparent_changes_the_base_rather_than_replacing_the_pull_request():
    """
    Reparenting keeps the pull request, its number and its review thread.

    Closing the orphan and opening a replacement was considered while the base change
    was believed impossible from a session; it is not, so the sequence must not drift
    back to it.
    """
    phase_one = PromptDocument.load(DOCTRINE_DOCUMENT).section(
        DoctrineLandmark.PHASE_ONE, DoctrineLandmark.PHASE_TWO
    )

    sequence = phase_one[phase_one.index(DoctrineLandmark.NATIVE_STACK_MEMBERS.text) :]

    assert GitHubMcpTool.UPDATE_PULL_REQUEST in sequence
    assert GitHubMcpTool.CREATE_PULL_REQUEST not in sequence


def test_every_reparent_instruction_points_at_the_base_change_rule():
    """
    Both reparent sites - the orphaned-child sweep and the per-merged-parent list - defer
    to the one rule, so neither can prescribe a client of its own.
    """
    phase_one = PromptDocument.load(DOCTRINE_DOCUMENT).section(
        DoctrineLandmark.PHASE_ONE, DoctrineLandmark.PHASE_TWO
    )

    orphan_sweep = phase_one[
        phase_one.index(DoctrineLandmark.ORPHANED_CHILD_SWEEP.text) : phase_one.index(
            DoctrineLandmark.NATIVE_STACK_MEMBERS.text
        )
    ]
    merged_parent_list = phase_one[
        phase_one.index(DoctrineLandmark.MERGED_PARENT_LIST.text) :
    ]

    assert GitHubMcpTool.UPDATE_PULL_REQUEST in orphan_sweep
    assert GitHubMcpTool.UPDATE_PULL_REQUEST in merged_parent_list
