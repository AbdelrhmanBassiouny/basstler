"""
The ``basstler repository-rules`` commands: showing and editing the rules every plan of
the repository follows.
"""

from __future__ import annotations

from pathlib import Path

from cyclopts import App
from cyclopts.types import ExistingFile

from basstler.exit_codes import ExitCode
from basstler.plan.repository_rules import RepositoryRule, RepositoryRules
from basstler.plan.repository_rules_store import RepositoryRulesStore
from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its commands print through.
"""


class RepositoryRulesExitCode(ExitCode):
    """
    What a ``basstler repository-rules`` command's exit status tells its caller.
    """

    SUCCESS = 0
    """
    The command did what it was asked.
    """

    UNKNOWN_RULE = 1
    """
    The rule to remove is not among the repository's rules.
    """


repository_rules_app = App(
    name="repository-rules",
    help="Show and edit the rules every plan of this repository follows.",
)
"""
The ``repository-rules`` command group.
"""


@repository_rules_app.command(name="show")
def show_rules() -> RepositoryRulesExitCode:
    """
    Print the repository's rules as the rules file holds them.
    """
    logger.info(
        RepositoryRulesStore.from_project_root(Path.cwd()).read().render().rstrip("\n")
    )
    return RepositoryRulesExitCode.SUCCESS


@repository_rules_app.command(name="set")
def set_rule(identifier: str, text: str) -> RepositoryRulesExitCode:
    """
    Add a rule, or reword the one with the same id, and push the notes branch.

    :param identifier: The rule's short name.
    :param text: What the rule says.
    """
    store = RepositoryRulesStore.from_project_root(Path.cwd())
    store.write(
        store.read().with_rule(RepositoryRule(identifier=identifier, text=text)),
        f"Set repository rule {identifier}",
    )
    return RepositoryRulesExitCode.SUCCESS


@repository_rules_app.command(name="import")
def import_rules(file: ExistingFile) -> RepositoryRulesExitCode:
    """
    Set every rule a rules file holds, as :func:`set_rule` sets one, in a single push.

    :param file: A YAML file in the rules file's own format.
    :raises pydantic.ValidationError: If the file does not hold valid rules; nothing is
        pushed.
    """
    imported = RepositoryRules.from_file(file)
    store = RepositoryRulesStore.from_project_root(Path.cwd())
    store.write(
        store.read().with_rules(imported),
        f"Set repository rules {', '.join(imported.identifiers)}",
    )
    return RepositoryRulesExitCode.SUCCESS


@repository_rules_app.command(name="remove")
def remove_rule(identifier: str) -> RepositoryRulesExitCode:
    """
    Remove a rule and push the notes branch.

    :param identifier: The id of the rule to remove.
    """
    store = RepositoryRulesStore.from_project_root(Path.cwd())
    rules = store.read()
    if identifier not in rules.identifiers:
        logger.error(f"the repository has no rule {identifier!r}")
        return RepositoryRulesExitCode.UNKNOWN_RULE
    store.write(rules.without(identifier), f"Remove repository rule {identifier}")
    return RepositoryRulesExitCode.SUCCESS
