#!/usr/bin/env python3
"""
Bootstrap a plan item before its implementation, rather than after it.

Everything a session knows the moment an implementation plan is approved - the branch,
the draft pull request, the item's manifest fields, its roadmap section - is derivable
without a line of the implementation, yet all of it conventionally happens at the end.
For that whole window ``plan.yaml`` says the item is ``not started`` with no branch while
a branch exists and is being worked, which every dashboard, kickoff and resolve run
downstream reads as truth.

Two operations, so each caller depends only on the surface it uses:

``record``
    Write or update the item's ``plan.yaml`` entry, set its status, add a standing
    rule to ``roadmap.md`` when the item settled one, and push both through
    ``save-plan.sh``.

``open``
    Create the branch, publish it, open the draft pull request, then write ``branch``,
    ``session`` and ``pull_request_number`` back onto the item and flip it to
    ``in progress``. A caller that has already created the pull request passes
    ``--pull-request-number`` and only the recording happens.

``open`` runs before ``record`` when both are wanted: the pull request number does not
exist until the pull request does.

Usage:
    python3 plan/item_bootstrap.py record --plan <plan-id> --item <item-id> \\
        --status <status> [--roadmap-entry <rule>] [--title <title>] [--track <track>]
    python3 plan/item_bootstrap.py open --plan <plan-id> --item <item-id> \\
        --branch <branch> --base <branch> --session <url> \\
        (--pull-request-number <number> | --pull-request-title <title> \\
         --pull-request-body <file>)

Prints a one-line JSON report led by ``status`` and ``exit_code``, so a caller acting on
the document never has to decode an integer back into a meaning.

.. note::
   Republishing the dashboard is deliberately not done here. Only a live session can
   call the ``Artifact`` tool, so both operations hand back the ``/plan-dashboard``
   command to run instead, exactly as ``save-plan.sh`` already does.

.. note::
   The manifest is edited by patching only the lines that change. A full YAML
   load-mutate-dump round trip is rejected for the reason ``plan/sync_manifest_status.py``
   records: even a format-preserving library re-flows wrapped strings, turning a
   one-field edit into an unreadable diff across the whole file. Every key, filename and
   status this module writes is named once in :class:`ManifestKey`, :class:`PlanDocument`
   and :class:`ItemStatus`, and every line is rendered by the key that owns it, so no
   caller - tests included - writes a second copy of a manifest line by hand.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from abc import ABC
from dataclasses import dataclass
from enum import Enum, StrEnum
from pathlib import Path
from typing import Any, Protocol

import yaml

from basstler.environment import GitHubCredentialVariable
from basstler.class_property import classproperty
from basstler.exceptions import DataclassException
from basstler.exit_codes import CommandFailure, ExitCode
from basstler.locations import ClaudeCodeVariable, PluginLocation, ProjectLocation
from basstler.plan.model import (
    ItemIndentation,
    ItemStatus,
    ManifestKey,
)
from basstler.repository import GitHubAddress
from basstler.shell_configuration import ShellConfigurationFunction
from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""

# %% the vocabulary a plan manifest is written in


class PlanDocument(StrEnum):
    """
    The two files a plan is kept in, beside each other on the personal-notes branch.
    """

    MANIFEST = "plan.yaml"
    """
    The structured manifest, whose schema ``plan-schema.md`` documents.
    """

    ROADMAP = "roadmap.md"
    """
    The narrative companion, a fixed sibling filename rather than a configurable one.
    """

    def path_within_notes_branch(self, plan_identifier: str) -> str:
        """
        Where this document lives for one plan.

        :param plan_identifier: The plan's id.
        :return: The path, relative to the personal-notes branch's root.
        """
        return str(ProjectLocation.PLANS / plan_identifier / self.value)


class ManifestLinePattern(Enum):
    """
    What the item-block patching looks for in a raw ``plan.yaml`` line.
    """

    ITEM_START = re.compile(rf"^\s*- {re.escape(ManifestKey.IDENTIFIER.key)}:")
    """
    Matches the first line of an item block, which is always its ``id``.

    Same anchor ``plan/sync_manifest_status.py`` uses to find item boundaries in raw text.
    """

    TOP_LEVEL_KEY = re.compile(r"^\S")
    """
    Matches a top-level ``plan.yaml`` key, which is where the last item block ends.
    """

    BLOCK_VALUE = re.compile(
        r"^\s*("
        + "|".join(
            sorted(manifest_key.key for manifest_key in ManifestKey.block_styled())
        )
        + "):"
    )
    """
    Matches a key whose value may run over the following lines, derived from
    :meth:`ManifestKey.block_styled` rather than listing those keys a second time.
    """

    def matches(self, line: str) -> bool:
        """
        :param line: One manifest line.
        :return: Whether this pattern matches at the line's start.
        """
        return self.value.match(line) is not None


class PlanItemBootstrapExitCode(ExitCode):
    """
    The process statuses this tool exits with.

    A distinct status per refusal lets a caller act on *which* failure happened without
    parsing stderr. ``argparse`` supplies 2 for a usage error.
    """

    SUCCESS = 0
    """
    The operation ran and printed its report.
    """

    UNKNOWN_PLAN = 3
    """
    No plan of that id is on the personal-notes branch.
    """

    UNKNOWN_ITEM = 4
    """
    The plan exists but tracks no item of that id, and too little was given to add one.
    """

    INCOMPLETE_NEW_ITEM = 5
    """
    Adding the item was asked for without every key a new entry must carry.
    """

    BRANCH_ALREADY_PUBLISHED = 6
    """
    The branch is already on the remote, so opening the work would adopt someone's.
    """

    PULL_REQUEST_DETAILS_MISSING = 7
    """
    Neither an existing pull request number nor the title and body to create one.
    """

    PULL_REQUEST_REFUSED = 8
    """
    GitHub rejected the creation; its own message says why.
    """


# %% failures


@dataclass
class BootstrapError(CommandFailure, DataclassException, ABC):
    """
    Base for every refusal this tool reports, each carrying its own exit status.
    """


@dataclass
class UnknownPlanError(BootstrapError):
    """
    Raised when the named plan has no manifest on the personal-notes branch.
    """

    @classproperty
    def exit_code(cls) -> PlanItemBootstrapExitCode:
        """:return: The status this kind of error ends a command with."""
        return PlanItemBootstrapExitCode.UNKNOWN_PLAN

    plan_identifier: str
    """
    The plan that could not be found.
    """

    manifest_path: str
    """
    Where its manifest was looked for.
    """

    def error_message(self) -> str:
        return (
            f"no plan {self.plan_identifier!r} on the personal-notes branch "
            f"({self.manifest_path} is not there)"
        )

    def suggest_correction(self) -> str:
        return "Run /plan-create to bootstrap it, or check the plan id for a typo."


@dataclass
class UnknownItemError(BootstrapError):
    """
    Raised when the named item is absent from an otherwise resolvable plan.
    """

    @classproperty
    def exit_code(cls) -> PlanItemBootstrapExitCode:
        """:return: The status this kind of error ends a command with."""
        return PlanItemBootstrapExitCode.UNKNOWN_ITEM

    plan_identifier: str
    """
    The plan that was searched.
    """

    item_identifier: str
    """
    The item that is not in it.
    """

    def error_message(self) -> str:
        return f"no item {self.item_identifier!r} in plan {self.plan_identifier!r}"

    def suggest_correction(self) -> str:
        return (
            "Record the item first - /add-plan-item decides where new work belongs, and "
            "this tool's record operation writes the entry."
        )


@dataclass
class IncompleteNewItemError(BootstrapError):
    """
    Raised when an item that does not exist yet is recorded without the fields needed to
    write its entry.
    """

    @classproperty
    def exit_code(cls) -> PlanItemBootstrapExitCode:
        """:return: The status this kind of error ends a command with."""
        return PlanItemBootstrapExitCode.INCOMPLETE_NEW_ITEM

    item_identifier: str
    """
    The item that would have been created.
    """

    missing_keys: tuple[ManifestKey, ...]
    """
    The keys a new entry cannot omit that were not supplied.
    """

    def error_message(self) -> str:
        missing = ", ".join(manifest_key.key for manifest_key in self.missing_keys)
        return (
            f"item {self.item_identifier!r} is not in the plan yet, so recording it "
            f"needs {missing}"
        )

    def suggest_correction(self) -> str:
        return "Pass " + " and ".join(
            f"--{manifest_key.key.replace('_', '-')}"
            for manifest_key in self.missing_keys
        )


@dataclass
class BranchAlreadyPublishedError(BootstrapError):
    """
    Raised when the branch to open already exists on the remote, which means work is
    underway and overwriting it would discard someone's commits.
    """

    @classproperty
    def exit_code(cls) -> PlanItemBootstrapExitCode:
        """:return: The status this kind of error ends a command with."""
        return PlanItemBootstrapExitCode.BRANCH_ALREADY_PUBLISHED

    branch: str
    """
    The branch that is already published.
    """

    remote: str
    """
    The remote carrying it.
    """

    def error_message(self) -> str:
        return (
            f"branch {self.branch!r} already exists on {self.remote!r} - it is already "
            "being worked, and republishing it would discard those commits"
        )

    def suggest_correction(self) -> str:
        return (
            "Pass --pull-request-number if its pull request already exists, or choose a "
            "branch name that is not taken."
        )


@dataclass
class PullRequestDetailsMissingError(BootstrapError):
    """
    Raised when opening the work must create a pull request but was given nothing to
    create it from.
    """

    @classproperty
    def exit_code(cls) -> PlanItemBootstrapExitCode:
        """:return: The status this kind of error ends a command with."""
        return PlanItemBootstrapExitCode.PULL_REQUEST_DETAILS_MISSING

    item_identifier: str
    """
    The item whose work was being opened.
    """

    def error_message(self) -> str:
        return (
            f"opening {self.item_identifier!r} has to create a pull request, but was "
            "given neither a title nor a body to create one from"
        )

    def suggest_correction(self) -> str:
        return (
            "Pass --pull-request-number for one you already created - which keeps your "
            "identity on it - or --pull-request-title and --pull-request-body."
        )


@dataclass
class PullRequestRefusedError(BootstrapError):
    """
    Raised when the remote declines to create the pull request.
    """

    @classproperty
    def exit_code(cls) -> PlanItemBootstrapExitCode:
        """:return: The status this kind of error ends a command with."""
        return PlanItemBootstrapExitCode.PULL_REQUEST_REFUSED

    detail: str
    """
    What the remote said.
    """

    def error_message(self) -> str:
        return f"the remote refused to create the pull request: {self.detail}"

    def suggest_correction(self) -> str:
        return (
            "The branch is published, so create the pull request yourself and re-run "
            "with --pull-request-number."
        )


@dataclass
class NotesBranchUnavailableError(BootstrapError):
    """
    Raised when the personal-notes branch cannot be fetched, so there is no plan data to
    read or write.
    """

    @classproperty
    def exit_code(cls) -> PlanItemBootstrapExitCode:
        """:return: The status this kind of error ends a command with."""
        return PlanItemBootstrapExitCode.UNKNOWN_PLAN

    detail: str
    """
    Why the fetch failed.
    """

    def error_message(self) -> str:
        return f"could not fetch the personal-notes branch: {self.detail}"

    def suggest_correction(self) -> str:
        return f"Run {PluginLocation.PERSONAL_NOTES_BRANCH_CREATION_SCRIPT} first."


# %% the plan on the personal-notes branch


@dataclass(frozen=True)
class ProjectCheckout:
    """
    The repository a plan item is bootstrapped in, and the git commands run within it.
    """

    project_root: Path
    """
    The repository to run within.
    """

    def run_git(self, *arguments: str) -> str:
        """
        Run git in the checkout and return its standard output.

        :param arguments: The arguments to pass to git.
        :raises subprocess.CalledProcessError: If git reports an error.
        :return: Standard output, stripped of its trailing newline.
        """
        result = subprocess.run(
            ["git", *arguments],
            cwd=self.project_root,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.rstrip("\n")

    def fetch_notes_branch(self) -> None:
        """
        Fetch the personal-notes branch, leaving ``FETCH_HEAD`` pointing at it.

        Calls the shell configuration's own fetch function, so this and the hook scripts
        never disagree about which branch a plan is on.

        :raises NotesBranchUnavailableError: If the notes branch cannot be fetched.
        """
        probe = ShellConfigurationFunction.FETCH_PERSONAL_NOTES_BRANCH.run(
            self.project_root
        )
        if probe.returncode != 0:
            raise NotesBranchUnavailableError(
                detail=probe.stderr.strip() or "no personal-notes branch found"
            )


@dataclass(frozen=True)
class PlanDocuments:
    """
    One plan's manifest and roadmap as they stand on the personal-notes branch.
    """

    plan_identifier: str
    """
    The plan's id.
    """

    manifest_text: str
    """
    The manifest's raw text, patched by line rather than re-serialized.
    """

    roadmap_text: str
    """
    The roadmap's raw markdown.
    """

    @classmethod
    def load(cls, plan_identifier: str, project_root: Path) -> PlanDocuments:
        """
        Read a plan's manifest and roadmap off the freshly fetched notes branch.

        The fetch happens here, immediately before the caller's edit, so an edit is
        never applied to a copy loaded earlier in the session.

        :param plan_identifier: The plan's id.
        :param project_root: The repository to read within.
        :raises UnknownPlanError: If the plan has no manifest on the branch.
        :return: The loaded documents.
        """
        checkout = ProjectCheckout(project_root)
        checkout.fetch_notes_branch()
        contents = {}
        for document in PlanDocument:
            path = document.path_within_notes_branch(plan_identifier)
            try:
                contents[document] = (
                    checkout.run_git("show", f"FETCH_HEAD:{path}") + "\n"
                )
            except subprocess.CalledProcessError as error:
                raise UnknownPlanError(
                    plan_identifier=plan_identifier, manifest_path=path
                ) from error
        return cls(
            plan_identifier=plan_identifier,
            manifest_text=contents[PlanDocument.MANIFEST],
            roadmap_text=contents[PlanDocument.ROADMAP],
        )

    @property
    def manifest(self) -> dict[str, Any]:
        """
        The parsed manifest, for reading fields rather than editing them.
        """
        return yaml.safe_load(self.manifest_text)

    def repository_for(self, item_identifier: str) -> str:
        """
        The ``owner/repo`` an item's pull request belongs to.

        :param item_identifier: The item's id.
        :raises UnknownItemError: If no item carries that id.
        :return: The item's own repository, or the plan's default one.
        """
        item = self.item(item_identifier)
        return (
            item.get(ManifestKey.REPOSITORY.key)
            or self.manifest[ManifestKey.DEFAULT_REPOSITORY.key]
        )

    def item(self, item_identifier: str) -> dict[str, Any]:
        """
        One item's parsed mapping.

        :param item_identifier: The item's id, or its branch when it has no id.
        :raises UnknownItemError: If no item matches.
        :return: The item's mapping.
        """
        for candidate in self.manifest.get(ManifestKey.ITEMS.key, []):
            identifier = candidate.get(ManifestKey.IDENTIFIER.key) or candidate.get(
                ManifestKey.BRANCH
            )
            if identifier == item_identifier:
                return candidate
        raise UnknownItemError(
            plan_identifier=self.plan_identifier, item_identifier=item_identifier
        )

    def has_item(self, item_identifier: str) -> bool:
        """
        Whether the plan already tracks an item under *item_identifier*.

        :param item_identifier: The item's id.
        :return: True when an entry exists.
        """
        try:
            self.item(item_identifier)
        except UnknownItemError:
            return False
        return True

    def save(self, manifest_text: str, roadmap_text: str, project_root: Path) -> None:
        """
        Push an edited manifest and roadmap through ``save-plan.sh``.

        :param manifest_text: The full manifest to write.
        :param roadmap_text: The full roadmap to write.
        :param project_root: The repository to run the script from.
        :raises subprocess.CalledProcessError: If the script reports an error.
        """
        with tempfile.TemporaryDirectory() as scratch_directory:
            scratch = Path(scratch_directory)
            written = {
                PlanDocument.MANIFEST: manifest_text,
                PlanDocument.ROADMAP: roadmap_text,
            }
            for document, content in written.items():
                (scratch / document.value).write_text(content)
            subprocess.run(
                [
                    "bash",
                    PluginLocation.PLAN_SAVING_SCRIPT,
                    self.plan_identifier,
                    "--manifest",
                    str(scratch / PlanDocument.MANIFEST.value),
                    "--roadmap",
                    str(scratch / PlanDocument.ROADMAP.value),
                ],
                cwd=project_root,
                capture_output=True,
                text=True,
                check=True,
            )


# %% patching one item's fields in the manifest text


@dataclass
class ManifestText:
    """
    A manifest's raw lines, patched by line so every untouched line survives byte for
    byte: comments, key order, string wrapping and quoting.
    """

    lines: list[str]
    """
    The manifest, split into lines.
    """

    @classmethod
    def from_text(cls, manifest_text: str) -> ManifestText:
        """
        :param manifest_text: The manifest's raw text.
        :return: The manifest, split into lines.
        """
        return cls(lines=manifest_text.split("\n"))

    @property
    def text(self) -> str:
        """
        The manifest's raw text.
        """
        return "\n".join(self.lines)

    def item_block_bounds(self) -> list[tuple[int, int]]:
        """
        :return: The half-open line range of every item block, in manifest order.
        """
        starts = [
            index
            for index, line in enumerate(self.lines)
            if ManifestLinePattern.ITEM_START.matches(line)
        ]
        if not starts:
            return []
        end_of_items = next(
            (
                index
                for index in range(starts[-1] + 1, len(self.lines))
                if ManifestLinePattern.TOP_LEVEL_KEY.matches(self.lines[index])
            ),
            len(self.lines),
        )
        return list(zip(starts, starts[1:] + [end_of_items]))

    def locate_item_block(
        self, plan_identifier: str, item_identifier: str
    ) -> tuple[int, int]:
        """
        Find one item's block.

        :param plan_identifier: The plan being edited, for the error message.
        :param item_identifier: The item's id.
        :raises UnknownItemError: If no block starts with that id.
        :return: The block's half-open line range.
        """
        opener = f"- {ManifestKey.IDENTIFIER.key}:"
        for start, end in self.item_block_bounds():
            if (
                self.lines[start].strip().removeprefix(opener).strip()
                == item_identifier
            ):
                return start, end
        raise UnknownItemError(
            plan_identifier=plan_identifier, item_identifier=item_identifier
        )

    def item_indentation(self, block: tuple[int, int] | None = None) -> ItemIndentation:
        """
        How this manifest indents its items, read off one item block so a written line
        lands beside its siblings and not under one.

        :param block: The half-open line range of the block to read, or ``None`` for
            the manifest's first item.
        :return: The block's indentation, or the default when the manifest has no item
            to read it from.
        """
        if block is None:
            bounds = self.item_block_bounds()
            if not bounds:
                return ItemIndentation()
            block = bounds[0]
        start, end = block
        opening = self.lines[start]
        marker = opening[: len(opening) - len(opening.lstrip(" "))] + "- "
        for line in self.lines[start + 1 : end]:
            if line.strip():
                return ItemIndentation(
                    marker=marker,
                    field_indent=line[: len(line) - len(line.lstrip(" "))],
                )
        return ItemIndentation(marker=marker, field_indent=" " * len(marker))

    def last_populated_line(self, start: int, end: int) -> int:
        """
        :param start: The block's first line.
        :param end: One past the block's last line.
        :return: The index of the block's last non-blank line.
        """
        return max(
            (index for index in range(start, end) if self.lines[index].strip()),
            default=start,
        )

    def with_item_fields(
        self,
        plan_identifier: str,
        item_identifier: str,
        values_by_key: dict[ManifestKey, str],
    ) -> str:
        """
        Set each of *values_by_key* on one item, patching an existing line or inserting
        a new one.

        :param plan_identifier: The plan being edited.
        :param item_identifier: The item to patch.
        :param values_by_key: The value to write to each key, in insertion order.
        :raises UnknownItemError: If the item has no block in the text.
        :return: The patched manifest text.
        """
        patched = ManifestText(lines=list(self.lines))
        lines = patched.lines
        start, end = patched.locate_item_block(plan_identifier, item_identifier)
        indentation = patched.item_indentation((start, end))
        for manifest_key, value in values_by_key.items():
            rendered = manifest_key.render(value, indentation=indentation).rstrip("\n")
            existing = next(
                (
                    index
                    for index in range(start, end)
                    if manifest_key.pattern.match(lines[index])
                ),
                None,
            )
            if existing is not None:
                lines[existing] = rendered
                continue
            insertion = next(
                (
                    index
                    for index in range(start, end)
                    if ManifestLinePattern.BLOCK_VALUE.matches(lines[index])
                ),
                patched.last_populated_line(start, end) + 1,
            )
            lines.insert(insertion, rendered)
            end += 1
        return patched.text

    def with_item(self, block: str) -> str:
        """
        Add a rendered item block after the manifest's last item.

        :param block: The block to append, as :meth:`ItemRecordRequest.render_new_item`
            renders it.
        :return: The extended manifest text.
        """
        bounds = self.item_block_bounds()
        insertion = bounds[-1][1] if bounds else len(self.lines)
        tail = "\n".join(self.lines[insertion:])
        head = "\n".join(self.lines[:insertion]).rstrip("\n")
        return f"{head}\n\n{block}{tail}"


# %% recording an item


@dataclass(frozen=True)
class ItemRecordRequest:
    """
    What recording one item needs: where it goes, what it is, and what to say about it.
    """

    plan_identifier: str
    """
    The plan the item belongs to.
    """

    item_identifier: str
    """
    The item's id, created if the plan does not track it yet.
    """

    status: ItemStatus
    """
    The status to set on the item.
    """

    title: str | None = None
    """
    The item's title, required only when the entry does not exist yet.
    """

    track: str | None = None
    """
    The track the item belongs to, required only when the entry does not exist yet.
    """

    roadmap_entry: str | None = None
    """
    A standing rule of the plan the item settled, added to its roadmap; ``None`` leaves
    the roadmap as it is.
    """

    def render_new_item(self, indentation: ItemIndentation) -> str:
        """
        Render a brand-new item block, in the field order ``plan-schema.md`` documents.

        :param indentation: How the manifest it is added to indents its items.
        :raises IncompleteNewItemError: If a field a new entry cannot omit is missing.
        :return: The block's text, newline-terminated.
        """
        required = {ManifestKey.TITLE: self.title, ManifestKey.TRACK: self.track}
        missing = tuple(
            manifest_key for manifest_key, value in required.items() if not value
        )
        if missing:
            raise IncompleteNewItemError(
                item_identifier=self.item_identifier, missing_keys=missing
            )
        body = {
            ManifestKey.TITLE: self.title,
            ManifestKey.BRANCH: "null",
            ManifestKey.TRACK: self.track,
            ManifestKey.DEPENDS_ON: "[]",
            ManifestKey.STATUS: self.status.value,
        }
        return ManifestKey.IDENTIFIER.render(
            self.item_identifier, opening_the_item=True, indentation=indentation
        ) + "".join(
            manifest_key.render(value, indentation=indentation)
            for manifest_key, value in body.items()
        )

    def roadmap_after(self, roadmap_text: str) -> str:
        """
        :param roadmap_text: The roadmap as it stands.
        :return: The roadmap with :attr:`roadmap_entry` appended as one standing rule,
            or unchanged when there is none.
        """
        if self.roadmap_entry is None:
            return roadmap_text
        return f"{roadmap_text.rstrip(chr(10))}\n- {' '.join(self.roadmap_entry.split())}\n"

    def record(self, project_root: Path) -> BootstrapReport:
        """
        Write or update the item's manifest entry, and add its roadmap entry when it has
        one, then push both.

        :param project_root: The repository to run within.
        :raises UnknownPlanError: If the plan has no manifest on the notes branch.
        :raises IncompleteNewItemError: If a new entry is missing a field it cannot omit.
        :return: What was recorded.
        """
        documents = PlanDocuments.load(self.plan_identifier, project_root)
        manifest = ManifestText.from_text(documents.manifest_text)
        created_item = not documents.has_item(self.item_identifier)
        if created_item:
            manifest_text = manifest.with_item(
                self.render_new_item(manifest.item_indentation())
            )
        else:
            manifest_text = manifest.with_item_fields(
                self.plan_identifier,
                self.item_identifier,
                {ManifestKey.STATUS: self.status.value},
            )
        documents.save(
            manifest_text, self.roadmap_after(documents.roadmap_text), project_root
        )
        return BootstrapReport(
            exit_code=PlanItemBootstrapExitCode.SUCCESS,
            plan_identifier=self.plan_identifier,
            item_identifier=self.item_identifier,
            created_item=created_item,
        )


@dataclass(frozen=True)
class BootstrapReport:
    """
    What an operation did, in the shape a caller acts on.
    """

    exit_code: PlanItemBootstrapExitCode
    """
    The status the process exits with.
    """

    plan_identifier: str
    """
    The plan that was written.
    """

    item_identifier: str
    """
    The item that was recorded or opened.
    """

    created_item: bool = False
    """
    Whether the item's manifest entry was written for the first time.
    """

    branch: str | None = None
    """
    The branch opened, when one was.
    """

    pull_request_number: int | None = None
    """
    The pull request opened, when one was.
    """

    pull_request_url: str | None = None
    """
    Where the opened pull request lives.
    """

    @property
    def dashboard_command(self) -> str:
        """
        The republish a live session still has to run, since only it can call
        ``Artifact``.
        """
        return f"/plan-dashboard {self.plan_identifier}"

    def as_document(self) -> dict[str, Any]:
        """
        Render the report as the JSON a caller reads, led by what it means.
        """
        document: dict[str, Any] = {
            "status": self.exit_code.name_for_a_caller,
            "exit_code": int(self.exit_code),
            "plan": self.plan_identifier,
            "item": self.item_identifier,
            "created_item": self.created_item,
            "dashboard_command": self.dashboard_command,
        }
        if self.branch is not None:
            document[ManifestKey.BRANCH.key] = self.branch
        if self.pull_request_number is not None:
            document[ManifestKey.PULL_REQUEST_NUMBER.key] = self.pull_request_number
            document["pull_request_url"] = self.pull_request_url
        return document


# %% opening the work


@dataclass(frozen=True)
class PullRequestRequest:
    """
    One pull request to create.
    """

    repository: str
    """
    The ``owner/repo`` to create it in.
    """

    title: str
    """
    The pull request's title.
    """

    body: str
    """
    The pull request's description.
    """

    head: str
    """
    The branch carrying the changes.
    """

    base: str
    """
    The branch to merge into.
    """

    draft: bool = True
    """
    Always a draft: this repository's convention is that a pull request stays a draft
    until its author has reviewed it themselves, and at creation time nobody has.
    """


@dataclass(frozen=True)
class CreatedPullRequest:
    """
    The pull request a remote actually created.
    """

    number: int
    """
    Its number.
    """

    html_url: str | None
    """
    Where to read it, unset when the caller supplied the number and already has it.
    """


class PullRequestOpener(Protocol):
    """
    The one call opening the work makes against a forge, kept behind a seam so the
    surrounding git work is testable without network access.
    """

    def open_pull_request(self, request: PullRequestRequest) -> CreatedPullRequest:
        """
        Create *request* and report what came back.

        :param request: The pull request to create.
        :raises PullRequestRefusedError: If the remote declines it.
        :return: The created pull request.
        """


@dataclass(frozen=True)
class GitHubPullRequestOpener:
    """
    Opens pull requests through GitHub's REST API.

    Sends a bearer token when the environment supplies one and nothing otherwise. Inside
    a Claude Code session the credential is inert - the agent proxy substitutes its own
    identity - but the same code run from a terminal or a scheduled Action has no proxy,
    and there the token is the credential. This is deliberately not a third copy of the
    prefer-``gh``-else-token rule ``github-api.sh`` and ``pr_state`` carry between them;
    it is the minimum that works from ``main`` today, for whichever item unifies them to
    absorb.
    """

    api_root: str = GitHubAddress.API
    """
    The API host, overridable for a GitHub Enterprise deployment.
    """

    def open_pull_request(self, request: PullRequestRequest) -> CreatedPullRequest:
        """
        Create *request* through ``POST /repos/{owner}/{repo}/pulls``.

        :param request: The pull request to create.
        :raises PullRequestRefusedError: If GitHub declines the creation.
        :return: The created pull request.
        """
        payload = json.dumps(
            {
                "title": request.title,
                "body": request.body,
                "head": request.head,
                "base": request.base,
                "draft": request.draft,
            }
        ).encode()
        http_request = urllib.request.Request(
            f"{self.api_root}/repos/{request.repository}/pulls",
            data=payload,
            method="POST",
            headers={
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
                **self.authorization_headers(),
            },
        )
        try:
            with urllib.request.urlopen(http_request) as response:
                created = json.loads(response.read())
        except urllib.error.HTTPError as error:
            raise PullRequestRefusedError(
                detail=f"{error.code} "
                f"{error.read().decode(errors='replace').strip()}"
            ) from error
        return CreatedPullRequest(
            number=created["number"], html_url=created["html_url"]
        )

    @staticmethod
    def authorization_headers() -> dict[str, str]:
        """
        The ``Authorization`` header, when the environment carries a token to send.

        :return: The header, or an empty mapping when there is no token.
        """
        token = GitHubCredentialVariable.first_token()
        return {"Authorization": f"Bearer {token}"} if token else {}


@dataclass(frozen=True)
class WorkOpenRequest:
    """
    What opening an item's work needs: the branch to create and the pull request to open
    on it.
    """

    plan_identifier: str
    """
    The plan the item belongs to.
    """

    item_identifier: str
    """
    The item being opened, which must already be tracked.
    """

    branch: str
    """
    The branch to create and publish.
    """

    base_branch: str
    """
    The branch to create it from and target the pull request at.
    """

    session_url: str
    """
    The session doing the work, recorded on the item.

    Required rather than derived: a session's environment cannot be asked which session
    it is, and a script that guessed would record something wrong in silence.
    """

    pull_request_title: str | None = None
    """
    The pull request's title, needed only when this module creates it.
    """

    pull_request_body: str | None = None
    """
    The pull request's description, needed only when this module creates it.
    """

    pull_request_number: int | None = None
    """
    A pull request the caller has already created, recorded instead of creating one.

    A pull request this module creates is attributed to the app the request is proxied
    through rather than to the person whose work it is, so a caller that can create one
    under its own identity should, and hand the number here. Left unset, the module
    creates it - which is what an unattended run with no session has to do.
    """


@dataclass
class WorkOpener:
    """
    The git half of opening an item's work: branch from the base, mark the start, and
    publish.
    """

    project_root: Path
    """
    The repository the branch is created in.
    """

    remote: str = "origin"
    """
    The remote the branch is published to.
    """

    def branch_is_published(self, branch: str) -> bool:
        """
        Whether *branch* already exists on the remote.

        :param branch: The branch to look for.
        :return: True when the remote already carries it.
        """
        listing = ProjectCheckout(self.project_root).run_git(
            "ls-remote", "--heads", self.remote, branch
        )
        return bool(listing.strip())

    def publish(self, request: WorkOpenRequest) -> None:
        """
        Create the branch from its base and push it, so a pull request has a head.

        The opening commit is empty by construction: the whole point of this tool is
        that the branch exists before any implementation does, and a pull request needs
        a commit its base does not have.

        :param request: The work being opened.
        """
        checkout = ProjectCheckout(self.project_root)
        checkout.run_git("checkout", "-b", request.branch, request.base_branch)
        checkout.run_git(
            "commit",
            "--allow-empty",
            "--quiet",
            "-m",
            f"Bootstrap {request.item_identifier}",
        )
        checkout.run_git("push", "-u", self.remote, request.branch)

    def open(
        self,
        request: WorkOpenRequest,
        pull_request_opener: PullRequestOpener | None = None,
    ) -> BootstrapReport:
        """
        Create the item's branch and draft pull request, then record both on the item.

        Both refusals this can raise before publishing - an untracked item, an already
        published branch - are checked first, so neither leaves anything behind. A pull
        request the remote declines is the one case that does: the branch is already
        published by then and stays, since a session cannot delete a remote branch. The
        manifest is left untouched rather than pointing at a pull request that does not
        exist, and re-running once the refusal is understood is refused by the
        already-published guard rather than silently overwriting those commits.

        :param request: The work to open.
        :param pull_request_opener: What creates the pull request, defaulting to GitHub.
        :raises UnknownItemError: If the plan does not track the item yet.
        :raises PullRequestDetailsMissingError: If it must create a pull request but was
            given nothing to create one from.
        :raises BranchAlreadyPublishedError: If the branch already exists on the remote.
        :raises PullRequestRefusedError: If the pull request could not be created.
        :return: What was opened.
        """
        opener = pull_request_opener or GitHubPullRequestOpener()
        if request.pull_request_number is None and not (
            request.pull_request_title and request.pull_request_body
        ):
            raise PullRequestDetailsMissingError(
                item_identifier=request.item_identifier
            )
        documents = PlanDocuments.load(request.plan_identifier, self.project_root)
        repository = documents.repository_for(request.item_identifier)

        if not self.branch_is_published(request.branch):
            self.publish(request)
        elif request.pull_request_number is None:
            raise BranchAlreadyPublishedError(branch=request.branch, remote=self.remote)

        created = (
            CreatedPullRequest(number=request.pull_request_number, html_url=None)
            if request.pull_request_number is not None
            else opener.open_pull_request(
                PullRequestRequest(
                    repository=repository,
                    title=request.pull_request_title,
                    body=request.pull_request_body,
                    head=request.branch,
                    base=request.base_branch,
                )
            )
        )

        manifest_text = ManifestText.from_text(
            documents.manifest_text
        ).with_item_fields(
            request.plan_identifier,
            request.item_identifier,
            {
                ManifestKey.BRANCH: request.branch,
                ManifestKey.PULL_REQUEST_NUMBER: str(created.number),
                ManifestKey.SESSION: request.session_url,
                ManifestKey.STATUS: ItemStatus.IN_PROGRESS.value,
            },
        )
        documents.save(manifest_text, documents.roadmap_text, self.project_root)
        return BootstrapReport(
            exit_code=PlanItemBootstrapExitCode.SUCCESS,
            plan_identifier=request.plan_identifier,
            item_identifier=request.item_identifier,
            branch=request.branch,
            pull_request_number=created.number,
            pull_request_url=created.html_url,
        )


# %% command line


class PlanItemBootstrapCommandLine:
    """
    This module's command line: ``record`` and ``open``.
    """

    @staticmethod
    def parser() -> argparse.ArgumentParser:
        """
        Build the argument parser for both subcommands.

        :return: The parser.
        """
        parser = argparse.ArgumentParser(
            description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
        )
        subcommands = parser.add_subparsers(dest="subcommand", required=True)

        record = subcommands.add_parser(
            "record",
            help="Write an item's manifest entry and its roadmap entry, if any",
        )
        record.add_argument("--plan", required=True)
        record.add_argument("--item", required=True)
        record.add_argument("--status", required=True, type=ItemStatus)
        record.add_argument("--roadmap-entry")
        record.add_argument("--title")
        record.add_argument("--track")

        open_command = subcommands.add_parser(
            "open", help="Create the item's branch and draft pull request"
        )
        open_command.add_argument("--plan", required=True)
        open_command.add_argument("--item", required=True)
        open_command.add_argument("--branch", required=True)
        open_command.add_argument("--base", required=True)
        open_command.add_argument("--session", required=True)
        open_command.add_argument(
            "--pull-request-title",
            help="Required unless --pull-request-number is given",
        )
        open_command.add_argument(
            "--pull-request-body",
            type=Path,
            help="Required unless --pull-request-number is given",
        )
        open_command.add_argument(
            "--pull-request-number",
            type=int,
            help="Record a pull request the caller already created, instead of creating one",
        )
        open_command.add_argument("--remote", default="origin")

        return parser


def main() -> int:
    """
    Parse arguments, run the requested operation, and print its report.

    See the module docstring for the command line contract.
    """
    arguments = PlanItemBootstrapCommandLine.parser().parse_args()
    project_root = Path(
        os.environ.get(ClaudeCodeVariable.PROJECT_DIRECTORY, Path.cwd())
    )

    try:
        if arguments.subcommand == "record":
            report = ItemRecordRequest(
                plan_identifier=arguments.plan,
                item_identifier=arguments.item,
                status=arguments.status,
                roadmap_entry=arguments.roadmap_entry,
                title=arguments.title,
                track=arguments.track,
            ).record(project_root)
        else:
            report = WorkOpener(
                project_root=project_root, remote=arguments.remote
            ).open(
                WorkOpenRequest(
                    plan_identifier=arguments.plan,
                    item_identifier=arguments.item,
                    branch=arguments.branch,
                    base_branch=arguments.base,
                    session_url=arguments.session,
                    pull_request_title=arguments.pull_request_title,
                    pull_request_body=(
                        arguments.pull_request_body.read_text()
                        if arguments.pull_request_body
                        else None
                    ),
                    pull_request_number=arguments.pull_request_number,
                )
            )
    except BootstrapError as error:
        logger.error(f"{error.exit_code.name_for_a_caller}: {error}")
        return int(error.exit_code)

    logger.info(json.dumps(report.as_document()))
    return int(report.exit_code)


if __name__ == "__main__":
    sys.exit(main())
