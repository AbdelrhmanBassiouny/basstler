"""
A few sections standing in for the repository's own.
"""

from __future__ import annotations

from typing import override

from basstler.class_property import classproperty
from basstler.code_rules.prose_length import ProseLengthChecker
from basstler.code_rules.rule import Section

# %% sections


class DesignPrinciplesRules(Section):
    """
    A section listing rules and holding a subsection.
    """

    KEEP_DESIGNS_SIMPLE = "A rule about design"


class ErrorsRules(Section):
    """
    A subsection whose first rule is spelled out by details.
    """

    @classproperty
    @override
    def parent(cls) -> type[Section]:
        return DesignPrinciplesRules

    RAISE_ERRORS = "A rule about errors", ("A first detail", "A second detail")

    NAME_ERRORS = "Another rule about errors"


class VerificationRules(Section):
    """
    A section listing rules only in its subsection.
    """


class AssertionsRules(Section):
    """
    The subsection of a section without rules of its own, with a checked rule.
    """

    @classproperty
    @override
    def parent(cls) -> type[Section]:
        return VerificationRules

    ASSERT_EXACTLY = "A rule about assertions"

    KEEP_ASSERTIONS_SHORT = "A rule a checker enforces", (), ProseLengthChecker()


class ReleasesThroughCIRules(Section):
    """
    A section whose name ends in an acronym.
    """
