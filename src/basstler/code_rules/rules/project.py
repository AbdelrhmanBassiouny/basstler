"""
The rules for this repository only.
"""

from __future__ import annotations

from typing import override

from basstler import environment, locations
from basstler.class_property import classproperty
from basstler.code_rules import rules
from basstler.code_rules.checker import CodeRuleChecker
from basstler.code_rules.commands import CodeRulesCommand
from basstler.code_rules.rule import CodeReference, Section


class ProjectRules(Section):
    """
    The rules for this repository only.
    """


class PackageAndPluginRules(Section):
    """
    The rules on the package and the plugin.
    """

    @classproperty
    @override
    def parent(cls) -> type[Section]:
        return ProjectRules

    MODULES_IN_THE_PACKAGE = (
        "Every Python module lives in the `basstler` package under `src/`; the "
        "plugin under `plugin/` carries only its `SKILL.md` files, manifest and "
        "bash entry points, which call the installed package with `python -m "
        "basstler.<module>`"
    )

    NAME_FILES_AND_VARIABLES_ONCE = (
        f"Name every file and directory once, in {CodeReference(locations).path}; "
        f"every environment variable once, in {CodeReference(environment).path}"
    )

    ONLY_DECLARED_DEPENDENCIES = (
        "The package depends only on the libraries `pyproject.toml` lists. Code "
        "that comes from `krrood` is copied, never imported; until krrood's light "
        "core is released, a copied module says so and cites krrood with "
        "`` :cite:`krrood` ``, whose entry is in `docs/references.bib`"
    )


class AgentInstructionsRules(Section):
    """
    The rules on this repository's ``AGENTS.md``.
    """

    @classproperty
    @override
    def parent(cls) -> type[Section]:
        return ProjectRules

    GENERATE_THE_AGENTS_FILE = (
        "`AGENTS.md` is generated from the sections in "
        f"{CodeReference(rules).path}; change a rule there and run "
        f"`{CodeRulesCommand.AGENTS_MD.invocation}`, never edit the file"
    )

    LINK_EVERY_CHECKER_TO_ITS_RULE = (
        "A script that finds code breaking a rule is a "
        f"{CodeReference(CodeRuleChecker).path}, set as that rule's "
        "`checker`, so the rule and its check are declared together"
    )


class ReleasesRules(Section):
    """
    The rules on releases.
    """

    @classproperty
    @override
    def parent(cls) -> type[Section]:
        return ProjectRules

    VERSION_FROM_THE_TAG = (
        "No file carries the version: the release workflow tags the merge commit, "
        "and `hatch-vcs` reads the version from that tag"
    )

    DECIDE_EVERY_RELEASE = (
        "Every pull request decides its release: label it `release:minor` for a new"
        " feature or capability, `release:major` for a breaking change (removed or "
        "renamed commands, flags, files or settings a user relies on), and leave it"
        " unlabelled for a patch. Say which and why in the description"
    )
