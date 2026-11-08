#!/usr/bin/env python3
"""
The plan.yaml manifest utilities save-plan.sh calls; ``--help`` lists the commands.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import StrEnum
from functools import cached_property
from pathlib import Path
from typing import Annotated, Any

import yaml
from cyclopts import App, Parameter

from basstler.exceptions import NotesRemoteNamesNoRepository, PlanValidationError
from basstler.plan.dependencies import PlanDirectory
from basstler.plan.merge import PlanMerge, PlanVersion
from basstler.plan.validation import PlanValidator
from basstler.plan import model
from basstler.repository import Repository
from basstler.exit_codes import CommandFailure, ExitCode, ManifestToolsExitCode
from basstler.command_line import plan_item_selection
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
    Check a manifest against the rules a plan page is built under.
    """

    REGENERATE_BRANCH_INDEX = "regenerate-branch-index"
    """
    Rebuild the branch to plan-id index.
    """

    ITEM = "item"
    """
    Print the plan's header and one item's entry.
    """

    MERGE = "merge"
    """
    Merge a session's edit of a plan onto the plan as it stands now.
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
    The plans directory: relative to the scratch directory when rebuilding the index,
    and what a ``<plan-id>/<item-id>`` entry resolves against when validating.
    """

    MANIFEST_FILENAME = "--manifest-filename"
    """
    The filename every plan's manifest has.
    """

    OUTPUT = "--output"
    """
    Where the subcommand writes what it produces.
    """

    READ = "--read"
    """
    The plan directory as the session read it.
    """

    SESSION = "--session"
    """
    The plan directory as the session wrote it.
    """

    LATEST = "--latest"
    """
    The plan directory as it stands on the notes branch now.
    """

    ITEM_IDENTIFIER = "--id"
    """
    The id of the item to print.
    """

    BRANCH = "--branch"
    """
    The branch whose item to print.
    """

    NOTES_REMOTE_URL = "--notes-remote-url"
    """
    The URL of the remote whose notes branch the manifest is saved to.
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

    def validate(
        self,
        plan_directory: PlanDirectory | None = None,
        notes_repository: Repository | None = None,
    ) -> None:
        """
        Check the manifest against the same rules a plan page is built under, so nothing
        is saved that no page could then be built from, nor to another repository's
        notes than the one its work is for.

        :param plan_directory: The plans a ``<plan-id>/<item-id>`` entry resolves
            against; without one, such an entry is refused.
        :param notes_repository: The repository whose notes the manifest is saved to, or
            ``None`` when it is not known.
        :raises PlanValidationError: If it breaks any rule, carrying every problem
            found.
        """
        PlanValidator(self.content, plan_directory, notes_repository).validate()

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
                        f"plan/manifest_tools.py: duplicate branch {branch!r} in "
                        f"{manifest.path} - keeping the first plan it was seen "
                        "under, dropping this one."
                    )
                    continue
                seen_branches.add(branch)
                lines.append(f"{branch}\t{plan_id}")
        return "\n".join(lines) + ("\n" if lines else "")


# %% command line


def notes_repository(notes_remote_url: str | None) -> Repository | None:
    """
    :param notes_remote_url: The notes remote's URL, or ``None`` when no save is being
        checked.
    :return: The repository that URL names, or ``None`` for no URL.
    :raises PlanValidationError: If the URL names no repository.
    """
    if notes_remote_url is None:
        return None
    if not Repository.names_a_repository(notes_remote_url):
        raise PlanValidationError([NotesRemoteNamesNoRepository(notes_remote_url)])
    return Repository.from_remote_url(notes_remote_url)


manifest_tools_app = App(
    name="basstler.plan.manifest_tools",
    help="The plan.yaml manifest utilities save-plan.sh calls.",
)
"""
This module's command line: one command per :class:`ManifestToolsCommand`.
"""


@manifest_tools_app.command(name=ManifestToolsCommand.READ_ID)
def read_id(manifest_path: Path, /) -> ManifestToolsExitCode:
    """
    Print a manifest's ``id`` field.

    :param manifest_path: The manifest to read.
    """
    logger.info(PlanManifest(manifest_path).identifier)
    return ManifestToolsExitCode.SUCCESS


@manifest_tools_app.command(name=ManifestToolsCommand.VALIDATE)
def validate(
    manifest_path: Path,
    /,
    *,
    plans_directory: Annotated[
        Path | None, Parameter(name=ManifestToolsOption.PLANS_DIRECTORY)
    ] = None,
    notes_remote_url: Annotated[
        str | None, Parameter(name=ManifestToolsOption.NOTES_REMOTE_URL)
    ] = None,
) -> ManifestToolsExitCode:
    """
    Check a manifest against the rules a plan page is built under.

    :param manifest_path: The manifest to check.
    :param plans_directory: The plans a ``<plan-id>/<item-id>`` entry resolves against.
    :param notes_remote_url: The remote the manifest is saved to; a plan for another
        repository, or a remote naming none, is refused.
    """
    PlanManifest(manifest_path).validate(
        PlanDirectory(plans_directory) if plans_directory else None,
        notes_repository(notes_remote_url),
    )
    return ManifestToolsExitCode.SUCCESS


@manifest_tools_app.command(name=ManifestToolsCommand.REGENERATE_BRANCH_INDEX)
def regenerate_branch_index(
    *,
    scratch_directory: Annotated[
        Path, Parameter(name=ManifestToolsOption.SCRATCH_DIRECTORY)
    ],
    plans_directory: Annotated[
        Path, Parameter(name=ManifestToolsOption.PLANS_DIRECTORY)
    ],
    manifest_filename: Annotated[
        str, Parameter(name=ManifestToolsOption.MANIFEST_FILENAME)
    ],
    output: Annotated[Path, Parameter(name=ManifestToolsOption.OUTPUT)],
) -> ManifestToolsExitCode:
    """
    Rebuild the branch to plan-id index.

    :param scratch_directory: The checkout of the personal-notes branch to scan.
    :param plans_directory: The plans directory, relative to *scratch_directory*.
    :param manifest_filename: The filename every plan's manifest has.
    :param output: Where to write the index.
    """
    index = BranchIndex(scratch_directory, plans_directory, manifest_filename)
    output.write_text(index.render())
    return ManifestToolsExitCode.SUCCESS


@manifest_tools_app.command(name=ManifestToolsCommand.ITEM)
def item(
    manifest_path: Path,
    /,
    *,
    item_identifier: Annotated[
        str | None,
        Parameter(name=ManifestToolsOption.ITEM_IDENTIFIER, group=plan_item_selection),
    ] = None,
    branch: Annotated[
        str | None,
        Parameter(name=ManifestToolsOption.BRANCH, group=plan_item_selection),
    ] = None,
) -> ManifestToolsExitCode:
    """
    Print the plan's header and one item's entry.

    :param manifest_path: The manifest holding the item.
    :param item_identifier: The id of the item to print.
    :param branch: The branch whose item to print.
    """
    manifest = model.PlanManifest.from_file(manifest_path)
    selected_item = (
        manifest.item_on_branch(branch)
        if branch is not None
        else manifest.item_named(item_identifier)
    )
    logger.info(manifest.item_summary(selected_item).rstrip("\n"))
    return ManifestToolsExitCode.SUCCESS


@manifest_tools_app.command(name=ManifestToolsCommand.MERGE)
def merge(
    *,
    read: Annotated[Path, Parameter(name=ManifestToolsOption.READ)],
    session: Annotated[Path, Parameter(name=ManifestToolsOption.SESSION)],
    latest: Annotated[Path, Parameter(name=ManifestToolsOption.LATEST)],
    output: Annotated[Path, Parameter(name=ManifestToolsOption.OUTPUT)],
) -> ManifestToolsExitCode:
    """
    Merge a session's edit of a plan onto the plan as it stands now.

    :param read: The plan directory as the session read it.
    :param session: The plan directory as the session wrote it.
    :param latest: The plan directory as it stands on the notes branch now.
    :param output: Where to write the merged plan directory.
    """
    PlanMerge(
        read=PlanVersion.from_directory(read),
        session=PlanVersion.from_directory(session),
        latest=PlanVersion.from_directory(latest),
    ).merged().write(output)
    return ManifestToolsExitCode.SUCCESS


# %% entry point


def main() -> ExitCode:
    """
    Run the invoked command, ending with the status a refusal carries.

    :return: The process exit code.
    """
    try:
        return manifest_tools_app(sys.argv[1:], result_action="return_value")
    except CommandFailure as error:
        logger.error(f"{error}")
        return error.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
