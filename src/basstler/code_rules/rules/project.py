"""
The rules for this repository only.
"""

from __future__ import annotations

from typing import override

from basstler import environment, locations, package_map
from basstler.bash import Bash
from basstler.class_property import classproperty
from basstler.code_rules import rules
from basstler.code_rules.bash_by_name import BashByNameChecker
from basstler.code_rules.checker import CodeRuleChecker
from basstler.code_rules.commands import CodeRulesCommand
from basstler.code_rules.locale_encoding import LocaleEncodingChecker
from basstler.code_rules.package_boundaries import PackageBoundaryChecker
from basstler.code_rules.rule import CodeReference, Section
from basstler.code_rules.tree_removal import TreeRemovalChecker
from basstler.directory_tree import DirectoryTree


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

    IMPORT_ONLY_LISTED_PACKAGES = (
        "A package imports only the basstler packages its pyproject lists: every "
        "module belongs to a distribution declared in "
        f"{CodeReference(package_map).path}, and imports only from that distribution "
        "and the ones it lists",
        (),
        PackageBoundaryChecker(),
    )


class PortabilityRules(Section):
    """
    The rules that keep the package and its suite working on Windows as on Linux.
    """

    @classproperty
    @override
    def parent(cls) -> type[Section]:
        return ProjectRules

    START_BASH_THROUGH_ITS_LOCATOR = (
        f"Start bash through {CodeReference(Bash).path}, never by its name: Windows "
        "resolves a bare `bash` to WSL's launcher instead of Git Bash",
        (),
        BashByNameChecker(),
    )

    READ_AND_WRITE_TEXT_AS_UTF_8 = (
        'Read and write text as UTF-8: pass `encoding="utf-8"` to every '
        "`read_text`, `write_text`, text-mode `open` and `subprocess` call that "
        "decodes its output, never `text=True`. Windows falls back to a code page "
        "that cannot encode most of Unicode",
        (),
        LocaleEncodingChecker(),
    )

    REMOVE_TREES_THROUGH_DIRECTORY_TREE = (
        f"Remove a directory through {CodeReference(DirectoryTree).path}, never with "
        "`shutil.rmtree`: Windows refuses to delete the read-only object files git "
        "leaves in a clone",
        (),
        TreeRemovalChecker(),
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
