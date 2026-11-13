"""
Tests for :mod:`basstler.plan.item_model`: which Claude model each plan-item skill
recommends, the committed default layered under a personal override.
"""

from __future__ import annotations

import tomllib

import pytest

from basstler.locations import PackageLocation
from basstler.plan.item_model import (
    ModelAlias,
    RecommendedModels,
    UnknownModelAliasError,
)
from basstler.plan.item_mode import PlanItemSkill

# %% fixtures


@pytest.fixture
def committed_models() -> dict[str, str]:
    """
    The recommendations as the committed file spells them, keyed by setting key.
    """
    return tomllib.loads(PackageLocation.PLAN_ITEM_MODEL_DEFAULTS.value.read_text())


# %% the aliases


def test_the_aliases_are_the_ones_claude_code_resolves_to_the_newest_model():
    assert [alias.value for alias in ModelAlias] == ["opus", "sonnet", "haiku"]


# %% layering


@pytest.mark.parametrize("skill", list(PlanItemSkill))
def test_without_a_personal_file_every_skill_recommends_its_committed_alias(
    skill: PlanItemSkill, committed_models: dict[str, str]
):
    recommended = RecommendedModels.layered(personal_text=None)
    assert recommended.of_skill(skill) == ModelAlias(
        committed_models[skill.model_setting_key]
    )


def test_a_personal_file_overrides_only_the_skills_it_names(
    committed_models: dict[str, str],
):
    personal_text = (
        f'{PlanItemSkill.KICKOFF.model_setting_key} = "{ModelAlias.HAIKU}"\n'
    )
    recommended = RecommendedModels.layered(personal_text=personal_text)
    assert recommended.of_skill(PlanItemSkill.KICKOFF) == ModelAlias.HAIKU
    assert recommended.of_skill(PlanItemSkill.RESOLVE) == ModelAlias(
        committed_models[PlanItemSkill.RESOLVE.model_setting_key]
    )


def test_a_personal_file_naming_no_alias_is_refused():
    personal_text = f'{PlanItemSkill.KICKOFF.model_setting_key} = "claude-opus-5"\n'
    with pytest.raises(UnknownModelAliasError):
        RecommendedModels.layered(personal_text=personal_text)
