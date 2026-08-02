"""
Contract tests for ``ROUTINE.md``, which the live cloud Routine reads and executes.

Two things are pinned here. First, the base-change rule: a pull request's base branch
can only be changed through the GitHub MCP server, since the same request issued through
the session git proxy is refused. Second, the document's shape, because the Routine's
prompt locates what to execute by the fenced block rather than by reading the whole
file.

Both are prose rather than code, so nothing else would catch an edit that undid them.
"""

from __future__ import annotations

from pathlib import Path

ROUTINE_DOCUMENT = Path(__file__).parent.parent / "ROUTINE.md"

EXECUTABLE_PROMPT_FENCE = "```text"
"""
Opening fence of the block the Routine executes; the surrounding prose is commentary.
"""

BASE_CHANGE_RULE_HEADING = "BASE CHANGES GO THROUGH THE GITHUB MCP SERVER."
"""
Opening words of the doctrine paragraph that names the one client able to retarget a
base.
"""

MCP_BASE_CHANGE_TOOL = "update_pull_request"
"""
The MCP tool that performs the retarget.
"""


def read_routine() -> str:
    """
    Read the doctrine document.

    :return: The full text of ``ROUTINE.md``.
    """
    return ROUTINE_DOCUMENT.read_text()


def phase_one() -> str:
    """
    Extract the Phase 1 section, which owns every reparent instruction.

    :return: The text from the Phase 1 heading up to the Phase 2 heading.
    """
    routine = read_routine()
    start = routine.index("PHASE 1 - LANDED PARENTS")
    return routine[start : routine.index("PHASE 2 - RESTACK", start)]


def executable_prompt() -> str:
    """
    Extract the block the Routine executes, the way the Routine's own prompt does.

    :return: The text between the opening and closing fences.
    """
    routine = read_routine()
    start = routine.index(EXECUTABLE_PROMPT_FENCE) + len(EXECUTABLE_PROMPT_FENCE)
    return routine[start : routine.index("\n```", start)]


# %% the shape the Routine's prompt depends on


def test_document_has_exactly_one_executable_prompt_block():
    """
    The Routine is told to execute the fenced block, so a second one would make that
    instruction ambiguous and none would leave it with nothing to run.
    """
    routine = read_routine()

    assert routine.count(EXECUTABLE_PROMPT_FENCE) == 1
    assert "\n```" in routine[routine.index(EXECUTABLE_PROMPT_FENCE) :]


def test_hard_rules_stay_inside_the_executable_block():
    """
    Commentary outside the fence is not executed, so moving the hard rules out would
    silently drop them from what the Routine actually runs.
    """
    prompt = executable_prompt()

    assert "HARD RULES" in prompt
    assert "NEVER call `subscribe_pr_activity`" in prompt


def test_setup_obtains_the_tooling_rather_than_assuming_it():
    """
    Setup must make ``stack.py`` present rather than assert that it is.

    Every later phase shells out to it, so a false assumption strands the Routine
    mid-run - and a Phase 2 failure lands after Phase 1 has already mutated pull
    requests.
    """
    setup = executable_prompt()
    setup = setup[setup.index("SETUP") : setup.index("1. UPDATE FORK MAIN FIRST")]

    assert "git fetch" in setup
    assert ".claude/stack/" in setup


# %% the base-change client


def test_doctrine_names_the_one_client_that_can_change_a_base():
    """
    The rule exists, is stated once, and names the tool that actually works.
    """
    routine = read_routine()

    assert routine.count(BASE_CHANGE_RULE_HEADING) == 1
    rule = routine[routine.index(BASE_CHANGE_RULE_HEADING) :]
    assert MCP_BASE_CHANGE_TOOL in rule[: rule.index("\n\n")]


def test_doctrine_records_that_the_git_proxy_refuses_a_base_change():
    """
    The refusal is recorded with its status code, so a session that hits it recognises
    it as the known, documented case rather than an unexplained failure to improvise
    around.
    """
    rule = read_routine()
    rule = rule[rule.index(BASE_CHANGE_RULE_HEADING) :]
    rule = rule[: rule.index("\n\n")]

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
    sequence = phase_one()
    sequence = sequence[sequence.index("NATIVE-STACK MEMBERS.") :]

    assert MCP_BASE_CHANGE_TOOL in sequence
    assert "create_pull_request" not in sequence


def test_every_reparent_instruction_points_at_the_base_change_rule():
    """
    Both reparent sites - the orphaned-child sweep and the per-merged-parent list - defer
    to the one rule, so neither can prescribe a client of its own.
    """
    section = phase_one()

    orphan_sweep = section[
        section.index("REPARENT EVERY ORPHANED CHILD") : section.index(
            "NATIVE-STACK MEMBERS."
        )
    ]
    merged_parent_list = section[
        section.index("For each OPEN fork PR (head branch B)") :
    ]

    assert MCP_BASE_CHANGE_TOOL in orphan_sweep
    assert MCP_BASE_CHANGE_TOOL in merged_parent_list
