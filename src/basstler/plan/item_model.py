"""
The Claude model each plan-item skill recommends, as a committed default layered under a
personal override.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from enum import StrEnum

from basstler.class_property import classproperty
from basstler.exceptions import DataclassException
from basstler.locations import PackageLocation
from basstler.plan.item_mode import PlanItemSkill

# %% vocabulary


class ModelAlias(StrEnum):
    """
    A Claude Code model alias, which always resolves to the newest model of its family.
    """

    OPUS = "opus"
    """
    The most capable family.
    """

    SONNET = "sonnet"
    """
    The balanced family.
    """

    HAIKU = "haiku"
    """
    The fastest family.
    """

    @property
    def label(self) -> str:
        """
        The alias as a model picker shows it.
        """
        return self.value.capitalize()


# %% failures


@dataclass
class UnknownModelAliasError(DataclassException, ValueError):
    """
    Raised when a settings file names a model that is no :class:`ModelAlias`.
    """

    setting_key: str
    """
    The key the value was stored under.
    """

    value: object
    """
    The value as it was read.
    """

    def error_message(self) -> str:
        return f"{self.setting_key}: {self.value!r} is not a model alias."

    def suggest_correction(self) -> str:
        return f"Use one of: {', '.join(ModelAlias)}."


# %% layering


@dataclass(frozen=True)
class RecommendedModels:
    """
    The model every plan-item skill recommends.
    """

    by_skill: dict[PlanItemSkill, ModelAlias]
    """
    The recommended model of every skill.
    """

    @classproperty
    def committed_settings(cls) -> dict[str, object]:
        """:return: The shipped recommendations, keyed by setting key."""
        return tomllib.loads(PackageLocation.PLAN_ITEM_MODEL_DEFAULTS.value.read_text())

    @classmethod
    def layered(cls, personal_text: str | None) -> RecommendedModels:
        """
        Lay a personal override over the committed recommendations.

        :param personal_text: The content of
            :attr:`ProjectLocation.PERSONAL_PLAN_ITEM_MODELS`, or ``None`` when there is
            none.
        :raises UnknownModelAliasError: If either file names a model that is no alias.
        :return: The recommendation of every skill.
        """
        settings = cls.committed_settings
        if personal_text is not None:
            settings = settings | tomllib.loads(personal_text)
        return cls(
            by_skill={
                skill: cls.alias_of(
                    skill.model_setting_key, settings[skill.model_setting_key]
                )
                for skill in PlanItemSkill
            }
        )

    @staticmethod
    def alias_of(setting_key: str, value: object) -> ModelAlias:
        """
        :param setting_key: The key the value was stored under.
        :param value: The value as it was read.
        :raises UnknownModelAliasError: If the value names no alias.
        :return: The alias the value names.
        """
        if value not in list(ModelAlias):
            raise UnknownModelAliasError(setting_key=setting_key, value=value)
        return ModelAlias(value)

    def of_skill(self, skill: PlanItemSkill) -> ModelAlias:
        """
        :param skill: The skill to recommend for.
        :return: The model it recommends.
        """
        return self.by_skill[skill]
