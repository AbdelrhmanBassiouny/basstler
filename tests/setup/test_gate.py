"""
Tests for :mod:`basstler.setup.gate`'s command line: a skill is named as a session
invokes it.
"""

from __future__ import annotations

import pytest

from basstler.setup.gate import GateOption, GatedSkill, gate_app

# %% naming the skill


@pytest.mark.parametrize("skill", list(GatedSkill))
def test_a_skill_is_named_as_a_session_invokes_it(skill: GatedSkill):
    """
    The command takes a skill by the name its document runs the gate with.
    """
    _, bound, _ = gate_app.parse_args([GateOption.SKILL, skill.value])

    assert bound.arguments["skill"] is skill
