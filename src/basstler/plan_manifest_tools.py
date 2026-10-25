#!/usr/bin/env python3
"""
Small plan.yaml manifest utilities used by save-plan.sh.

Kept as a real, testable script rather than inline ``python3 -c`` snippets
in the shell script, so this logic can be read, changed, and (if it grows
non-trivial branches later) tested like any other code.

Usage:
    python3 plan_manifest_tools.py read-id <manifest-file>
    python3 plan_manifest_tools.py validate <manifest-file>
    python3 plan_manifest_tools.py regenerate-branch-index \\
        --scratch-dir <dir> --plans-dir <relative-dir> \\
        --manifest-filename <name> --output <relative-path>
    python3 plan_manifest_tools.py item <manifest-file> (--id <item-id> | --branch <branch>)
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from enum import StrEnum
from functools import cached_property
from pathlib import Path
from typing import Any

import yaml

from basstler.exceptions import PlanValidationError
from basstler.plan_validation import PlanValidator
from basstler import plan_model
from basstler.exit_codes import ExitCode
from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""


class ManifestToolsCommand(StrEnum):
    """
    The subcommands this tool answers.
    """

    READ_ID = "read-id"
    """
    Print a manifest's ``id`` field.
    """

    VALIDATE = "validate"
    """
    Check a manifest against the rules a dashboard is built under.
    """

    REGENERATE_BRANCH_INDEX = "regenerate-branch-index"
    """
    Rebuild the branch to plan-id index.
    """

    ITEM = "item"
    """
    Print the plan's header and one item's entry.
    """


class ManifestToolsOption(StrEnum):
    """
    The options the subcommands take.
    """

    SCRATCH_DIRECTORY = "--scratch-dir"
    """
    The checkout of the personal-notes branch the index is built from.
    """

    PLANS_DIRECTORY = "--plans-dir"
    """
    The plans directory, relative to the scratch directory.
    """

    MANIFEST_FILENAME = "--manifest-filename"
    """
    The filename every plan's manifest has.
    """

    OUTPUT = "--output"
    """
    Where the regenerated index is written.
    """

    ITEM_IDENTIFIER = "--id"
    """
    The id of the item to print.
    """

    BRANCH = "--branch"
    """
    The branch whose item to print.
    """


class ManifestToolsExitCode(ExitCode):
    """
    How the command ended, as its caller reads it.
    """

    SUCCESS = 0
    """
    The subcommand did what it was asked.
    """

    INVALID_MANIFEST = 1
    """
    The manifest breaks a rule the dashboard validates; the problems are on stderr.
    """


class YamlBooleanCoercionError(ValueError):
    """
    Raised when a plan.yaml field that must be a string was parsed as a ``bool``
    instead. PyYAML's YAML 1.1 resolver treats bare tokens like.

    ``no``/``yes``/``on``/``off`` as booleans, silently discarding the
    original text - quoting the value in plan.yaml (e.g. ``id: "no"``)
    avoids this.
    """


@dataclass
class PlanManifest:
    """
    One plan.yaml manifest on disk, read once.
    """

    path: Path
    """
    Where the manifest is.
    """

    @cached_property
    def content(self) -> dict[str, Any]:
        """
        :return: The manifest, parsed.
        """
        with self.path.open() as manifest_file:
            return yaml.safe_load(manifest_file)

    @property
    def identifier(self) -> str:
        """
        :raises YamlBooleanCoercionError: If ``id`` was parsed as a boolean.
        :return: The manifest's ``id`` field, or an empty string if it has none.
        """
        return self.string_field(self.content.get("id", ""), "id")

    @property
    def item_branches(self) -> list[str]:
        """
        :raises YamlBooleanCoercionError: If an item's ``branch`` was parsed as a
            boolean.
        :return: Every item's branch, in the manifest's order, leaving out the items that
            name none.
        """
        branches = []
        for item in self.content.get("items", []):
            raw_branch = item.get("branch")
            if raw_branch is None:
                continue
            branch = self.string_field(raw_branch, "branch")
            if branch:
                branches.append(branch)
        return branches

    def validate(self) -> None:
        """
        Check the manifest against the same rules a dashboard is built under, so nothing
        is saved that no dashboard could then be built from.

        :raises PlanValidationError: If it breaks any rule, carrying every problem
            found.
        """
        PlanValidator(self.content).validate()

    def string_field(self, value: object, field_name: str) -> str:
        """
        Guard against PyYAML's YAML 1.1 boolean coercion silently corrupting a
        plan/branch identifier that happens to read as a bare ``no``/``yes``/
        ``on``/``off`` token.

        :param value: The field's already-parsed value.
        :param field_name: The field's name, for the error message.
        :raises YamlBooleanCoercionError: If *value* was coerced to ``bool``.
        :return: *value* as a ``str``.
        """
        if isinstance(value, bool):
            raise YamlBooleanCoercionError(
                f"{self.path}: field {field_name!r} was parsed as the boolean "
                f"{value!r} instead of a string - quote its value in plan.yaml "
                f'(e.g. {field_name}: "no") to avoid PyYAML\'s YAML 1.1 bare-token '
                "coercion."
            )
        return str(value)


@dataclass
class BranchIndex:
    """
    The branch -> plan-id reverse index, rebuilt from every plan.yaml in a checkout of
    the personal-notes branch.

    See ``resolve-personal-notes-config.sh``'s ``plan_id_for_branch`` for why the format
    is TSV, not YAML.
    """

    scratch_directory: Path
    """
    The scratch worktree root to scan within.
    """

    plans_directory: Path
    """
    The plans directory, relative to :attr:`scratch_directory` (e.g.
    ``.claude/personal/plans``).
    """

    manifest_filename: str
    """
    The manifest's fixed filename (e.g. ``plan.yaml``).
    """

    @property
    def manifests(self) -> list[PlanManifest]:
        """
        :return: Every ``<plans_directory>/*/<manifest_filename>``, in sorted order.
        """
        plans_root = self.scratch_directory / self.plans_directory
        return [
            PlanManifest(path)
            for path in sorted(plans_root.glob(f"*/{self.manifest_filename}"))
        ]

    def render(self) -> str:
        """
        One ``"<branch>\\t<plan-id>"`` line per item branch; the first plan wins on a
        duplicate branch.

        :raises YamlBooleanCoercionError: If a plan's ``id`` or an item's ``branch`` was
            parsed as a boolean.
        :return: The regenerated index content, ready to write to disk.
        """
        lines = []
        seen_branches = set()
        for manifest in self.manifests:
            plan_id = manifest.string_field(manifest.content["id"], "id")
            for branch in manifest.item_branches:
                if branch in seen_branches:
                    logger.error(
                        f"plan_manifest_tools.py: duplicate branch {branch!r} in "
                        f"{manifest.path} - keeping the first plan it was seen "
                        "under, dropping this one."
                    )
                    continue
                seen_branches.add(branch)
                lines.append(f"{branch}\t{plan_id}")
        return "\n".join(lines) + ("\n" if lines else "")


class ManifestToolsCommandLine:
    """
    The command line save-plan.sh calls: its arguments, and the subcommand they name.
    """

    @classmethod
    def parser(cls) -> argparse.ArgumentParser:
        """
        :return: The parser for every subcommand and its arguments.
        """
        parser = argparse.ArgumentParser(
            description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
        )
        subcommands = parser.add_subparsers(dest="subcommand", required=True)

        read_id_parser = subcommands.add_parser(
            ManifestToolsCommand.READ_ID, help="Print a manifest's id field"
        )
        read_id_parser.add_argument("manifest_path", type=Path)

        validate_parser = subcommands.add_parser(
            ManifestToolsCommand.VALIDATE,
            help="Check a manifest against the rules a dashboard is built under",
        )
        validate_parser.add_argument("manifest_path", type=Path)

        regenerate_parser = subcommands.add_parser(
            ManifestToolsCommand.REGENERATE_BRANCH_INDEX,
            help="Rebuild the branch->plan-id index",
        )
        regenerate_parser.add_argument(
            ManifestToolsOption.SCRATCH_DIRECTORY, required=True, type=Path
        )
        regenerate_parser.add_argument(
            ManifestToolsOption.PLANS_DIRECTORY, required=True, type=Path
        )
        regenerate_parser.add_argument(
            ManifestToolsOption.MANIFEST_FILENAME, required=True
        )
        regenerate_parser.add_argument(
            ManifestToolsOption.OUTPUT,
            required=True,
            type=Path,
            help="Path to write the index to",
        )

        item_parser = subcommands.add_parser(
            ManifestToolsCommand.ITEM,
            help="Print the plan's header and one item's entry",
        )
        item_parser.add_argument("manifest_path", type=Path)
        item_selector = item_parser.add_mutually_exclusive_group(required=True)
        item_selector.add_argument(
            ManifestToolsOption.ITEM_IDENTIFIER, dest="item_identifier"
        )
        item_selector.add_argument(ManifestToolsOption.BRANCH)
        return parser

    @classmethod
    def run(cls, arguments: argparse.Namespace) -> ManifestToolsExitCode:
        """
        Carry out the subcommand *arguments* name.

        :param arguments: The parsed command line.
        :return: How the subcommand ended.
        """
        if arguments.subcommand == ManifestToolsCommand.READ_ID:
            logger.info(PlanManifest(arguments.manifest_path).identifier)
        elif arguments.subcommand == ManifestToolsCommand.VALIDATE:
            try:
                PlanManifest(arguments.manifest_path).validate()
            except PlanValidationError as error:
                logger.error(f"{arguments.manifest_path} failed validation: {error}")
                return ManifestToolsExitCode.INVALID_MANIFEST
        elif arguments.subcommand == ManifestToolsCommand.REGENERATE_BRANCH_INDEX:
            index = BranchIndex(
                arguments.scratch_dir, arguments.plans_dir, arguments.manifest_filename
            )
            arguments.output.write_text(index.render())
        elif arguments.subcommand == ManifestToolsCommand.ITEM:
            manifest = plan_model.PlanManifest.from_file(arguments.manifest_path)
            item = (
                manifest.item_on_branch(arguments.branch)
                if arguments.branch is not None
                else manifest.item_named(arguments.item_identifier)
            )
            logger.info(manifest.item_summary(item).rstrip("\n"))
        return ManifestToolsExitCode.SUCCESS


def main() -> ManifestToolsExitCode:
    """
    Parse arguments and dispatch to the requested subcommand.
    """
    return ManifestToolsCommandLine.run(ManifestToolsCommandLine.parser().parse_args())


if __name__ == "__main__":
    sys.exit(main())
