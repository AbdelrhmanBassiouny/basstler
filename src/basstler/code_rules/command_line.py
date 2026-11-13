"""
The ``basstler code-rules`` commands: checking code against the rules, and generating
``AGENTS.md`` from them.
"""

from __future__ import annotations

import json
from pathlib import Path

from cyclopts import App

from basstler.code_rules import rules
from basstler.code_rules.checker import CodeRulesCheck, StagedLines
from basstler.code_rules.commands import CodeRulesCommand
from basstler.code_rules.instructions import AgentsInstructions
from basstler.code_rules.package_boundaries import (
    PackageBoundaryChecker,
    PackageCrossings,
)
from basstler.code_rules.rule_module import RuleModule
from basstler.exit_codes import ExitCode
from basstler.git.commands import GitCommandRunner
from basstler.locations import ProjectLocation
from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its commands print through.
"""


class CodeRulesExitCode(ExitCode):
    """
    What a ``basstler code-rules`` command's exit status tells pre-commit.
    """

    SUCCESS = 0
    """
    Nothing had to change.
    """

    CHANGES_NEEDED = 1
    """
    Code breaks a rule, a boundary crossing is new, or ``AGENTS.md`` was rewritten or
    is out of date.
    """


code_rules_app = App(
    name=CodeRulesCommand.GROUP,
    help="Check code against the repository's rules, and generate AGENTS.md from them.",
)
"""
The ``code-rules`` command group.
"""


@code_rules_app.command(name=CodeRulesCommand.CHECK)
def check(
    paths: list[Path] | None = None, *, all_lines: bool = False
) -> CodeRulesExitCode:
    """
    Report the code in *paths* that breaks a rule a checker enforces.

    :param paths: The Python files to check.
    :param all_lines: Check every line, not only those the staged change touches.
    """
    code_rules_check = CodeRulesCheck(
        RuleModule(rules).checkers,
        None if all_lines else StagedLines(GitCommandRunner(Path.cwd())),
    )
    violations = code_rules_check.violations(paths or [])
    for violation in violations:
        logger.error(violation.render())
    if violations:
        return CodeRulesExitCode.CHANGES_NEEDED
    return CodeRulesExitCode.SUCCESS


@code_rules_app.command(name=CodeRulesCommand.CROSSINGS)
def list_crossings(output: Path) -> CodeRulesExitCode:
    """
    Write every import of the package that crosses a distribution boundary to *output*.

    :param output: The JSON file to write the crossings to.
    """
    crossings = PackageBoundaryChecker().package_crossings()
    output.write_text(json.dumps(crossings.to_json(), indent=2) + "\n")
    logger.info("Wrote %d crossings to %s", len(crossings.crossings), output)
    return CodeRulesExitCode.SUCCESS


@code_rules_app.command(name=CodeRulesCommand.NEW_CROSSINGS)
def report_new_crossings(
    base: Path, *, base_commit: str | None = None
) -> CodeRulesExitCode:
    """
    Report each boundary crossing of the package that the base checkout does not have.

    :param base: The listing :func:`list_crossings` wrote in the base checkout.
    :param base_commit: The base checkout's commit; a module moved since keeps the
        crossings the listing holds under its old name.
    """
    checker = PackageBoundaryChecker()
    base_crossings = PackageCrossings.from_json(json.loads(base.read_text()))
    if base_commit is not None:
        renames = checker.module_renames(GitCommandRunner(Path.cwd()), base_commit)
        base_crossings = base_crossings.renamed(renames)
    added = checker.package_crossings().added_since(base_crossings)
    for crossing in added:
        logger.error(
            "basstler.%s newly imports basstler.%s across a distribution boundary; "
            "move the code or the import",
            crossing.importing_module,
            crossing.imported_module,
        )
    if added:
        return CodeRulesExitCode.CHANGES_NEEDED
    return CodeRulesExitCode.SUCCESS


@code_rules_app.command(name=CodeRulesCommand.AGENTS_MD)
def generate_agents_instructions(*, verify: bool = False) -> CodeRulesExitCode:
    """
    Write the current directory's ``AGENTS.md`` from the rules.

    :param verify: Only report whether the file is current, writing nothing.
    """
    instructions = AgentsInstructions.of_repository(Path.cwd())
    if instructions.is_current():
        return CodeRulesExitCode.SUCCESS
    if verify:
        logger.error(
            "%s is out of date; run `%s`.",
            ProjectLocation.AGENTS_INSTRUCTIONS,
            CodeRulesCommand.AGENTS_MD.invocation,
        )
        return CodeRulesExitCode.CHANGES_NEEDED
    instructions.write()
    logger.info("Wrote %s", ProjectLocation.AGENTS_INSTRUCTIONS)
    return CodeRulesExitCode.CHANGES_NEEDED
