#!/usr/bin/env python3
"""
Keep a plan item's recorded state current, from before its implementation onward.

Everything a session knows the moment an implementation plan is approved - the branch,
the draft pull request, the item's manifest fields - is derivable without a line of the
implementation, yet all of it conventionally happens at the end. For that whole window
``plan.yaml`` says the item is ``not started`` with no branch while a branch exists and
is being worked, which every dashboard, kickoff and resolve run downstream reads as
truth. The same holds for every later transition - a blocker appearing, a status
changing, a conclusion that changes what the item means - which is the rule
``manifest-staleness.md``, beside the plan-dashboard skill, states.

Seven operations, so each caller depends only on the surface it uses:

``record``
    Write or update the item's ``plan.yaml`` entry, set its status, add a standing
    rule to ``roadmap.md`` when the item settled one, and push both through
    ``save-plan.sh``.

``open``
    Create the branch, publish it, open the draft pull request, then write ``branch``,
    ``session`` and ``pull_request_number`` back onto the item and flip it to
    ``in progress``. A caller that has already created the pull request passes
    ``--pull-request-number`` and only the recording happens.

``update``
    Set any of the item's recorded fields, ``notes`` and ``blockers`` included.
    ``--append-notes`` extends the recorded note rather than replacing it.

``check``
    Report which recorded fields local git contradicts, exiting non-zero when any do.

``resolve``
    Name the plan and the items a branch belongs to, for a caller that holds a branch
    rather than an item id.

``block`` / ``unblock``
    Record or withdraw one owner's blocker on every item a branch carries, deriving the
    status from what is left blocking it. A blocker carries its owner, so a pass
    replaces and clears its own entries and never a person's.

``open`` runs before ``record`` when both are wanted: the pull request number does not
exist until the pull request does.

Usage:
    python -m basstler.plan.item_bootstrap record --plan <plan-id> --item <item-id> \\
        --status <status> [--roadmap-entry <rule>] [--title <title>] [--track <track>]
    python -m basstler.plan.item_bootstrap open --plan <plan-id> --item <item-id> \\
        --branch <branch> --base <branch> --session <url> \\
        (--pull-request-number <number> | --pull-request-title <title> \\
         --pull-request-body <file>)
    python -m basstler.plan.item_bootstrap update --plan <plan-id> --item <item-id> \\
        [--status <status>] [--branch <branch>] [--pull-request-number <number>] \\
        [--session <url>] [--notes <file> | --append-notes <file>] \\
        [--blockers <file> ...]
    python -m basstler.plan.item_bootstrap check --plan <plan-id> --item <item-id> \\
        [--remote <remote>]
    python -m basstler.plan.item_bootstrap resolve --branch <branch>
    python -m basstler.plan.item_bootstrap block --branch <branch> --owner <name> \\
        --reason <file>
    python -m basstler.plan.item_bootstrap unblock --branch <branch> --owner <name>

Prints a one-line JSON report led by ``status`` and ``exit_code``, so a caller acting on
the document never has to decode an integer back into a meaning.

.. note::
   Republishing the dashboard is deliberately not done here. Only a live session can
   call the ``Artifact`` tool, so every operation hands back the ``/plan-dashboard``
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
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, StrEnum
from pathlib import Path
from typing import Any, Protocol

import yaml

from basstler.environment import GitHubCredentialVariable
from basstler.class_property import classproperty
from basstler.command_line import Command
from basstler.exceptions import DataclassException
from basstler.exit_codes import CommandFailure, ExitCode
from basstler.locations import ClaudeCodeVariable, PluginLocation, ProjectLocation
from basstler.plan.model import (
    ItemIndentation,
    ItemStatus,
    ManifestKey,
    Prose,
    ValueStyle,
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

    SEQUENCE_ENTRY = re.compile(r"^\s*-\s")
    """
    Matches one entry of a block sequence, which YAML lets sit either indented under its
    key or flush with it.
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
    parsing stderr.
    """

    SUCCESS = 0
    """
    The operation ran and printed its report.
    """

    USAGE = 2
    """
    No such command, or the wrong arguments; ``argparse``'s own status for a usage error.
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

    PLAN_SAVE_REFUSED = 9
    """
    The plan save rejected the edited manifest or roadmap; its own message says why.
    """

    MANIFEST_IS_STALE = 10
    """
    The check found recorded fields that local git contradicts.
    """

    BRANCH_TRACKS_NO_ITEM = 11
    """
    No plan claims the branch, so there was nothing to resolve or to write.

    A finding rather than a failure: every pull request is supposed to belong to a plan,
    so a caller acting on the status alone reports it instead of guessing.
    """

    PLAN_NOT_WRITTEN = 12
    """
    The save reported success, but the notes branch does not carry the edit.
    """


class ReportKey(StrEnum):
    """
    The keys of the JSON documents these operations print that this module invents.

    A key naming a manifest field - ``branch``, ``blockers``, an item's own ``status`` -
    is read from :class:`ManifestKey` instead.
    """

    STATUS = "status"
    """
    What the run means, as :attr:`ExitCode.name_for_a_caller` puts it.

    Distinct from an item's own ``status``, which names a point in its lifecycle; the
    two share a spelling and nothing else.
    """

    EXIT_CODE = "exit_code"
    """
    The status the process exits with.
    """

    PLAN = "plan"
    """
    The plan the operation acted on.
    """

    ITEM = "item"
    """
    The item the operation acted on.
    """

    ITEMS = "items"
    """
    Every item a branch carries, for an operation keyed on a branch.
    """

    CREATED_ITEM = "created_item"
    """
    Whether the item's manifest entry was written for the first time.
    """

    DASHBOARD_COMMAND = "dashboard_command"
    """
    The dashboard republish the caller still has to run.
    """

    PULL_REQUEST_URL = "pull_request_url"
    """
    Where an opened pull request lives.
    """

    NOTE_PARAGRAPHS = "note_paragraphs"
    """
    How many paragraphs the item's note reads as once written.
    """

    FINDINGS = "findings"
    """
    Every recorded field local git contradicts.
    """

    FIELD = "field"
    """
    The manifest field one finding is about.
    """

    RECORDED = "recorded"
    """
    What the manifest says for that field.
    """

    OBSERVED = "observed"
    """
    What git shows for it instead.
    """

    PREVIOUS_STATUS = "previous_status"
    """
    The status an item carried before a write.
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
class PlanSaveRefusedError(BootstrapError):
    """
    Raised when the plan save rejects the edited documents, so nothing was published.
    """

    @classproperty
    def exit_code(cls) -> PlanItemBootstrapExitCode:
        """:return: The status this kind of error ends a command with."""
        return PlanItemBootstrapExitCode.PLAN_SAVE_REFUSED

    detail: str
    """
    What the plan save printed on its error stream.
    """

    def error_message(self) -> str:
        return f"the plan save refused the edit: {self.detail}"

    def suggest_correction(self) -> str:
        return (
            "Fix what the plan save names and run the command again; after opening, "
            "pass --pull-request-number for the pull request it already created."
        )


@dataclass
class PlanNotWrittenError(BootstrapError):
    """
    Raised when a save that reported success left the notes branch without the edit.
    """

    @classproperty
    def exit_code(cls) -> PlanItemBootstrapExitCode:
        """:return: The status this kind of error ends a command with."""
        return PlanItemBootstrapExitCode.PLAN_NOT_WRITTEN

    plan_identifier: str
    """
    The plan that was meant to be written.
    """

    documents: tuple[PlanDocument, ...]
    """
    The documents the notes branch does not carry the edit to.
    """

    def error_message(self) -> str:
        missing = ", ".join(document.value for document in self.documents)
        return (
            f"the plan save reported success, but plan {self.plan_identifier!r} on the "
            f"personal-notes branch does not carry the edit to {missing}"
        )

    def suggest_correction(self) -> str:
        return (
            "Read the plan off the notes branch before editing it again - another write "
            "may have landed in between."
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

    def branch_is_published(self, branch: str, remote: str) -> bool:
        """
        :param branch: The branch to look for.
        :param remote: The remote to ask.
        :return: Whether *remote* already carries *branch*.
        """
        return bool(self.run_git("ls-remote", "--heads", remote, branch).strip())

    def plan_tracking(self, branch: str) -> str | None:
        """
        The plan that tracks *branch*, per the branch index on the freshly fetched notes
        branch.

        :param branch: The branch to look up.
        :raises NotesBranchUnavailableError: If the notes branch cannot be fetched.
        :return: The plan's id, or ``None`` when no plan claims the branch.
        """
        self.fetch_notes_branch()
        lookup = ShellConfigurationFunction.PLAN_ID_FOR_BRANCH.run(
            self.project_root, branch
        )
        return lookup.stdout.strip() or None


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
        Push an edited manifest and roadmap through ``save-plan.sh``, then read the
        notes branch back to confirm they landed.

        :param manifest_text: The full manifest to write.
        :param roadmap_text: The full roadmap to write.
        :param project_root: The repository to run the script from.
        :raises PlanSaveRefusedError: If the script refuses the documents.
        :raises PlanNotWrittenError: If the branch does not carry the edit afterwards.
        """
        with tempfile.TemporaryDirectory() as scratch_directory:
            scratch = Path(scratch_directory)
            written = {
                PlanDocument.MANIFEST: manifest_text,
                PlanDocument.ROADMAP: roadmap_text,
            }
            for document, content in written.items():
                (scratch / document.value).write_text(content)
            saved = subprocess.run(
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
            )
        if saved.returncode != 0:
            raise PlanSaveRefusedError(detail=saved.stderr.strip())
        self.confirm_written(written, project_root)

    def confirm_written(
        self, written: dict[PlanDocument, str], project_root: Path
    ) -> None:
        """
        Check that the notes branch carries what was just saved.

        :param written: The content each document was saved with.
        :param project_root: The repository to read within.
        :raises PlanNotWrittenError: If a document on the branch differs from what was
            saved.
        """
        landed = PlanDocuments.load(self.plan_identifier, project_root)
        on_the_branch = {
            PlanDocument.MANIFEST: landed.manifest_text,
            PlanDocument.ROADMAP: landed.roadmap_text,
        }
        unwritten = tuple(
            document
            for document, content in written.items()
            if on_the_branch[document].strip() != content.strip()
        )
        if unwritten:
            raise PlanNotWrittenError(
                plan_identifier=self.plan_identifier, documents=unwritten
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
        values_by_key: dict[ManifestKey, Any],
    ) -> str:
        """
        Set each of *values_by_key* on one item, replacing every line an existing value
        occupies or inserting a new one.

        :param plan_identifier: The plan being edited.
        :param item_identifier: The item to patch.
        :param values_by_key: The value to write to each key, in insertion order, each
            in the form :meth:`ManifestKey.render` takes.
        :raises UnknownItemError: If the item has no block in the text.
        :return: The patched manifest text.
        """
        patched = ManifestText(lines=list(self.lines))
        lines = patched.lines
        start, end = patched.locate_item_block(plan_identifier, item_identifier)
        indentation = patched.item_indentation((start, end))
        for manifest_key, value in values_by_key.items():
            rendered = (
                manifest_key.render(value, indentation=indentation)
                .rstrip("\n")
                .split("\n")
            )
            existing = next(
                (
                    index
                    for index in range(start, end)
                    if manifest_key.pattern.match(lines[index])
                ),
                None,
            )
            if existing is not None:
                replaced = patched.value_end(existing, end, manifest_key)
                lines[existing:replaced] = rendered
                end += len(rendered) - (replaced - existing)
                continue
            insertion = next(
                (
                    index
                    for index in range(start, end)
                    if ManifestLinePattern.BLOCK_VALUE.matches(lines[index])
                ),
                patched.last_populated_line(start, end) + 1,
            )
            lines[insertion:insertion] = rendered
            end += len(rendered)
        return patched.text

    def value_end(self, key_line: int, end: int, manifest_key: ManifestKey) -> int:
        """
        One past the last line a key's value occupies.

        A value written beneath its key owns every following line indented past the key.
        A block sequence also owns the entries at the key's own depth, since YAML lets
        them sit flush with their key.

        :param key_line: The line the key sits on.
        :param end: One past the item block's last line.
        :param manifest_key: The key whose value is being measured.
        :return: One past the value's last line.
        """
        if not manifest_key.is_block_styled:
            return key_line + 1
        key_indent = self.indentation_width(self.lines[key_line])
        entries_sit_flush = manifest_key.style is ValueStyle.SEQUENCE
        last_value_line = key_line
        for index in range(key_line + 1, end):
            line = self.lines[index]
            if not line.strip():
                continue
            indent = self.indentation_width(line)
            if indent > key_indent:
                last_value_line = index
                continue
            if (
                indent < key_indent
                or not entries_sit_flush
                or not ManifestLinePattern.SEQUENCE_ENTRY.matches(line)
            ):
                break
            last_value_line = index
        return last_value_line + 1

    @staticmethod
    def indentation_width(line: str) -> int:
        """
        :param line: The line to measure.
        :return: How many columns its leading whitespace takes.
        """
        return len(line) - len(line.lstrip())

    def block_scalar_style(
        self, plan_identifier: str, item_identifier: str, manifest_key: ManifestKey
    ) -> BlockScalarStyle:
        """
        The style one item's key is written in, which parsing the manifest discards.

        :param plan_identifier: The plan being edited, for the error message.
        :param item_identifier: The item whose key to read.
        :param manifest_key: The key to read.
        :raises UnknownItemError: If the item has no block in the text.
        :return: :attr:`BlockScalarStyle.LITERAL` for a value opened with ``|``,
            otherwise :attr:`BlockScalarStyle.FOLDED`, which is also how a value written
            on the key's own line reads.
        """
        start, end = self.locate_item_block(plan_identifier, item_identifier)
        key_line = next(
            (
                line
                for line in self.lines[start:end]
                if manifest_key.pattern.match(line)
            ),
            None,
        )
        if key_line is None:
            return BlockScalarStyle.FOLDED
        indicator = key_line.split(":", 1)[1].strip()
        if indicator.startswith(BlockScalarStyle.LITERAL.value):
            return BlockScalarStyle.LITERAL
        return BlockScalarStyle.FOLDED

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
            ManifestKey.BRANCH: None,
            ManifestKey.TRACK: self.track,
            ManifestKey.DEPENDS_ON: (),
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
            plan_identifier=self.plan_identifier,
            item_identifier=self.item_identifier,
            created_item=created_item,
        )


class OperationReport(ABC):
    """
    What any operation answers with: the status the process exits with, and the JSON a
    caller reads.
    """

    @property
    @abstractmethod
    def exit_code(self) -> PlanItemBootstrapExitCode:
        """
        The status the process exits with.
        """

    @abstractmethod
    def as_document(self) -> dict[str, Any]:
        """
        Render the report as the JSON a caller reads, led by what it means.
        """

    @staticmethod
    def dashboard_command_for(plan_identifier: str) -> str:
        """
        :param plan_identifier: The plan that was written.
        :return: The republish a live session still has to run, since only it can call
            ``Artifact``.
        """
        return f"/plan-dashboard {plan_identifier}"


@dataclass(frozen=True)
class BootstrapReport(OperationReport):
    """
    What an operation on one item did, in the shape a caller acts on.
    """

    plan_identifier: str
    """
    The plan that was written.
    """

    item_identifier: str
    """
    The item that was recorded, opened or updated.
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

    note_paragraphs: int | None = None
    """
    How many paragraphs the written note reads as, when one was written.
    """

    @property
    def exit_code(self) -> PlanItemBootstrapExitCode:
        return PlanItemBootstrapExitCode.SUCCESS

    @property
    def dashboard_command(self) -> str:
        """
        The republish a live session still has to run, since only it can call
        ``Artifact``.
        """
        return OperationReport.dashboard_command_for(self.plan_identifier)

    def as_document(self) -> dict[str, Any]:
        document: dict[str, Any] = {
            ReportKey.STATUS: self.exit_code.name_for_a_caller,
            ReportKey.EXIT_CODE: int(self.exit_code),
            ReportKey.PLAN: self.plan_identifier,
            ReportKey.ITEM: self.item_identifier,
            ReportKey.CREATED_ITEM: self.created_item,
            ReportKey.DASHBOARD_COMMAND: self.dashboard_command,
        }
        if self.branch is not None:
            document[ManifestKey.BRANCH.key] = self.branch
        if self.pull_request_number is not None:
            document[ManifestKey.PULL_REQUEST_NUMBER.key] = self.pull_request_number
            document[ReportKey.PULL_REQUEST_URL] = self.pull_request_url
        if self.note_paragraphs is not None:
            document[ReportKey.NOTE_PARAGRAPHS] = self.note_paragraphs
        return document


# %% updating an item


class BlockScalarStyle(StrEnum):
    """
    How a block scalar YAML has already read back separates its paragraphs, named by the
    indicator that opens it.
    """

    LITERAL = "|"
    """
    Every line break is kept, so a single newline is a hard-wrapped line and a blank line
    separates paragraphs.
    """

    FOLDED = ">"
    """
    Line breaks fold into spaces and a blank line reads back as one newline, so a single
    newline separates paragraphs.
    """

    @property
    def paragraph_separator(self) -> re.Pattern[str]:
        """
        What separates two paragraphs in a value of this style once it has been read.
        """
        if self is BlockScalarStyle.LITERAL:
            return re.compile(r"\n\s*\n")
        return re.compile(r"\n+")


@dataclass(frozen=True)
class RecordedNote:
    """
    The note an item's manifest entry carries, as YAML read it back.
    """

    text: str | None
    """
    The note's text, or ``None`` where the item carries none.
    """

    style: BlockScalarStyle
    """
    How the note is written in the manifest, which decides how its paragraphs read back.
    """

    def extended_by(self, addition: str) -> str:
        """
        The note with *addition* as a further paragraph, its paragraphs separated by blank
        lines as :class:`basstler.plan.model.Prose` reads them.

        :param addition: The text to add, as its author wrote it.
        :return: The whole note.
        """
        paragraphs = [
            paragraph
            for paragraph in self.style.paragraph_separator.split(
                (self.text or "").strip()
            )
            if paragraph
        ]
        paragraphs.append(addition.strip())
        return "\n\n".join(paragraphs)


@dataclass(frozen=True)
class ItemUpdateRequest:
    """
    What updating one item needs: which item, and which fields to set on it.
    """

    plan_identifier: str
    """
    The plan the item belongs to.
    """

    item_identifier: str
    """
    The item being updated, which must already be tracked.
    """

    values_by_key: dict[ManifestKey, Any]
    """
    The value to write to each key, in the order they are applied.
    """

    notes_to_append: str | None = None
    """
    A further paragraph for the item's recorded note, rather than a replacement for it.
    """

    def update(self, project_root: Path) -> BootstrapReport:
        """
        Set the item's fields and push the manifest, leaving the roadmap alone.

        :param project_root: The repository to run within.
        :raises UnknownPlanError: If the plan has no manifest on the notes branch.
        :raises UnknownItemError: If the plan tracks no item of that id.
        :return: What was written.
        """
        documents = PlanDocuments.load(self.plan_identifier, project_root)
        manifest = ManifestText.from_text(documents.manifest_text)
        values_by_key = dict(self.values_by_key)
        if self.notes_to_append is not None:
            recorded = RecordedNote(
                text=documents.item(self.item_identifier).get(ManifestKey.NOTES.key),
                style=manifest.block_scalar_style(
                    self.plan_identifier, self.item_identifier, ManifestKey.NOTES
                ),
            )
            values_by_key[ManifestKey.NOTES] = recorded.extended_by(
                self.notes_to_append
            )
        manifest_text = manifest.with_item_fields(
            self.plan_identifier, self.item_identifier, values_by_key
        )
        documents.save(manifest_text, documents.roadmap_text, project_root)
        written_note = values_by_key.get(ManifestKey.NOTES)
        return BootstrapReport(
            plan_identifier=self.plan_identifier,
            item_identifier=self.item_identifier,
            note_paragraphs=(
                len(Prose(written_note).paragraphs)
                if written_note is not None
                else None
            ),
        )


# %% checking what the manifest claims against local git


@dataclass(frozen=True)
class StalenessFinding:
    """
    One recorded field that local git contradicts.
    """

    manifest_key: ManifestKey
    """
    The field whose recorded value is stale.
    """

    recorded: str | None
    """
    What the manifest says, or ``None`` where it says nothing.
    """

    observed: str
    """
    What git shows instead, in the terms a reader acts on.
    """

    def as_document(self) -> dict[str, Any]:
        """
        Render the finding as the JSON a caller reads.
        """
        return {
            ReportKey.FIELD: self.manifest_key.key,
            ReportKey.RECORDED: self.recorded,
            ReportKey.OBSERVED: self.observed,
        }


@dataclass(frozen=True)
class StalenessReport(OperationReport):
    """
    Which of an item's recorded fields local git contradicts, if any.
    """

    plan_identifier: str
    """
    The plan the item belongs to.
    """

    item_identifier: str
    """
    The item that was checked.
    """

    findings: tuple[StalenessFinding, ...]
    """
    Every stale field, in the order the fields are checked.
    """

    @property
    def exit_code(self) -> PlanItemBootstrapExitCode:
        if self.findings:
            return PlanItemBootstrapExitCode.MANIFEST_IS_STALE
        return PlanItemBootstrapExitCode.SUCCESS

    def as_document(self) -> dict[str, Any]:
        return {
            ReportKey.STATUS: self.exit_code.name_for_a_caller,
            ReportKey.EXIT_CODE: int(self.exit_code),
            ReportKey.PLAN: self.plan_identifier,
            ReportKey.ITEM: self.item_identifier,
            ReportKey.FINDINGS: [finding.as_document() for finding in self.findings],
            ReportKey.DASHBOARD_COMMAND: self.dashboard_command_for(
                self.plan_identifier
            ),
        }


@dataclass(frozen=True)
class ItemCheckRequest:
    """
    Which item to compare against local git, and the remote its branch is published to.

    Local git only: the dashboard compares the manifest against GitHub on every refresh,
    so what is left is the window before a push.
    """

    plan_identifier: str
    """
    The plan the item belongs to.
    """

    item_identifier: str
    """
    The item to check.
    """

    remote: str = "origin"
    """
    The remote the item's branch would be published to.
    """

    def check(self, project_root: Path) -> StalenessReport:
        """
        Compare the item's recorded fields against what local git shows.

        :param project_root: The repository to run within.
        :raises UnknownPlanError: If the plan has no manifest on the notes branch.
        :raises UnknownItemError: If the plan tracks no item of that id.
        :return: What is stale, if anything.
        """
        item = PlanDocuments.load(self.plan_identifier, project_root).item(
            self.item_identifier
        )
        recorded_branch = item.get(ManifestKey.BRANCH.key)
        if not recorded_branch:
            findings: tuple[StalenessFinding, ...] = ()
        elif not ProjectCheckout(project_root).branch_is_published(
            recorded_branch, self.remote
        ):
            findings = (
                StalenessFinding(
                    manifest_key=ManifestKey.BRANCH,
                    recorded=recorded_branch,
                    observed=f"no branch of that name on {self.remote}",
                ),
            )
        else:
            findings = self.fields_a_published_branch_requires(item, recorded_branch)
        return StalenessReport(
            plan_identifier=self.plan_identifier,
            item_identifier=self.item_identifier,
            findings=findings,
        )

    @staticmethod
    def fields_a_published_branch_requires(
        item: dict[str, Any], branch: str
    ) -> tuple[StalenessFinding, ...]:
        """
        :param item: The item's parsed manifest mapping.
        :param branch: The published branch it records.
        :return: One finding per field an item whose branch is published still leaves
            unset or contradicts.
        """
        observed = f"{branch} is published"
        recorded_status = item.get(ManifestKey.STATUS.key)
        status_findings = (
            (
                StalenessFinding(
                    manifest_key=ManifestKey.STATUS,
                    recorded=recorded_status,
                    observed=observed,
                ),
            )
            if recorded_status is not None
            and ItemStatus(recorded_status) is ItemStatus.NOT_STARTED
            else ()
        )
        return status_findings + tuple(
            StalenessFinding(
                manifest_key=manifest_key, recorded=None, observed=observed
            )
            for manifest_key in (ManifestKey.SESSION, ManifestKey.PULL_REQUEST_NUMBER)
            if item.get(manifest_key.key) is None
        )


# %% the items a branch carries, and the blockers one owner writes on them


@dataclass(frozen=True)
class TrackedItem:
    """
    One item a branch carries, as the manifest records it right now.
    """

    item_identifier: str
    """
    The item's id.
    """

    status: ItemStatus
    """
    The status the manifest records for it.
    """

    blockers: tuple[str, ...]
    """
    What the manifest records as blocking it.
    """

    def as_document(self) -> dict[str, Any]:
        """
        Render the item as the JSON a caller reads.
        """
        return {
            ReportKey.ITEM: self.item_identifier,
            ManifestKey.STATUS.key: self.status.value,
            ManifestKey.BLOCKERS.key: list(self.blockers),
        }


@dataclass(frozen=True)
class ItemWrite(TrackedItem):
    """
    One item's recorded state after a write, and the status it carried before it.
    """

    previous_status: ItemStatus
    """
    The status the manifest recorded before the write.
    """

    def as_document(self) -> dict[str, Any]:
        return {
            **super().as_document(),
            ReportKey.PREVIOUS_STATUS: self.previous_status.value,
        }


@dataclass(frozen=True)
class BranchReport(OperationReport):
    """
    Every item a branch carries, as an operation keyed on that branch found or left it.
    """

    branch: str
    """
    The branch that was looked up.
    """

    plan_identifier: str | None
    """
    The plan tracking it, or ``None`` when no plan claims the branch.
    """

    items: tuple[TrackedItem, ...]
    """
    Every item recording that branch, in manifest order.
    """

    @classmethod
    def of_branch(cls, branch: str, project_root: Path) -> BranchReport:
        """
        Find the plan and every item a branch belongs to.

        :param branch: The branch to resolve.
        :param project_root: The repository to run within.
        :raises UnknownPlanError: If the index names a plan with no manifest.
        :return: What the branch belongs to.
        """
        plan_identifier = ProjectCheckout(project_root).plan_tracking(branch)
        if plan_identifier is None:
            return cls(branch=branch, plan_identifier=None, items=())
        manifest = PlanDocuments.load(plan_identifier, project_root).manifest
        items = tuple(
            TrackedItem(
                item_identifier=item[ManifestKey.IDENTIFIER.key],
                status=ItemStatus(item[ManifestKey.STATUS.key]),
                blockers=tuple(item.get(ManifestKey.BLOCKERS.key) or ()),
            )
            for item in manifest[ManifestKey.ITEMS.key]
            if item.get(ManifestKey.BRANCH.key) == branch
        )
        return cls(branch=branch, plan_identifier=plan_identifier, items=items)

    @property
    def exit_code(self) -> PlanItemBootstrapExitCode:
        if self.items:
            return PlanItemBootstrapExitCode.SUCCESS
        return PlanItemBootstrapExitCode.BRANCH_TRACKS_NO_ITEM

    def as_document(self) -> dict[str, Any]:
        document: dict[str, Any] = {
            ReportKey.STATUS: self.exit_code.name_for_a_caller,
            ReportKey.EXIT_CODE: int(self.exit_code),
            ManifestKey.BRANCH.key: self.branch,
            ReportKey.PLAN: self.plan_identifier,
            ReportKey.ITEMS: [item.as_document() for item in self.items],
        }
        if self.plan_identifier is not None:
            document[ReportKey.DASHBOARD_COMMAND] = self.dashboard_command_for(
                self.plan_identifier
            )
        return document


@dataclass(frozen=True)
class OwnedBlocker:
    """
    One owner's blocker on every item a branch carries, set or withdrawn.

    Written as ``<owner>: <reason>``, so the owner replaces and withdraws only its own
    entries and never one a person wrote.
    """

    branch: str
    """
    The branch whose items are written.
    """

    owner: str
    """
    Who the blocker belongs to.
    """

    reason: str | None = None
    """
    Why the branch is blocked, or ``None`` to withdraw the owner's blocker.
    """

    @classproperty
    def owner_separator(cls) -> str:
        """
        What separates a written blocker's owner from its reason.
        """
        return ": "

    def write(self, project_root: Path) -> BranchReport:
        """
        Rewrite every item on the branch with the owner's blocker set or withdrawn, then
        derive each item's status from what is left blocking it.

        Only fields that change are written, so withdrawing a blocker an item never
        carried leaves it untouched.

        :param project_root: The repository to run within.
        :return: What was written.
        """
        resolution = BranchReport.of_branch(self.branch, project_root)
        writes = tuple(
            self.write_item(item, resolution, project_root) for item in resolution.items
        )
        return BranchReport(
            branch=self.branch, plan_identifier=resolution.plan_identifier, items=writes
        )

    def write_item(
        self, item: TrackedItem, resolution: BranchReport, project_root: Path
    ) -> ItemWrite:
        """
        :param item: One item the branch carries.
        :param resolution: The plan and items the branch resolved to.
        :param project_root: The repository to run within.
        :return: The item as written.
        """
        prefix = f"{self.owner}{self.owner_separator}"
        blockers = tuple(
            blocker for blocker in item.blockers if not blocker.startswith(prefix)
        )
        if self.reason is not None:
            blockers += (f"{prefix}{self.reason}",)
        status = self.status_beside(blockers, item.status)
        changed = {
            manifest_key: value
            for manifest_key, value, recorded in (
                (ManifestKey.STATUS, status, item.status),
                (ManifestKey.BLOCKERS, blockers, item.blockers),
            )
            if value != recorded
        }
        if changed:
            ItemUpdateRequest(
                plan_identifier=resolution.plan_identifier,
                item_identifier=item.item_identifier,
                values_by_key=changed,
            ).update(project_root)
        return ItemWrite(
            item_identifier=item.item_identifier,
            status=status,
            blockers=blockers,
            previous_status=item.status,
        )

    @staticmethod
    def status_beside(blockers: tuple[str, ...], previous: ItemStatus) -> ItemStatus:
        """
        The status an item carries given what is now blocking it.

        An item nothing blocks keeps what it recorded, unless that was
        :attr:`ItemStatus.BLOCKED`, which the blockers it no longer has were the reason
        for.

        :param blockers: What blocks the item now.
        :param previous: The status it recorded before.
        :return: The status to record.
        """
        if blockers:
            return ItemStatus.BLOCKED
        if previous is ItemStatus.BLOCKED:
            return ItemStatus.IN_PROGRESS
        return previous


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

        if not ProjectCheckout(self.project_root).branch_is_published(
            request.branch, self.remote
        ):
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
                ManifestKey.PULL_REQUEST_NUMBER: created.number,
                ManifestKey.SESSION: request.session_url,
                ManifestKey.STATUS: ItemStatus.IN_PROGRESS.value,
            },
        )
        documents.save(manifest_text, documents.roadmap_text, self.project_root)
        return BootstrapReport(
            plan_identifier=request.plan_identifier,
            item_identifier=request.item_identifier,
            branch=request.branch,
            pull_request_number=created.number,
            pull_request_url=created.html_url,
        )


# %% command line


@dataclass(frozen=True)
class BootstrapCommand(Command):
    """
    One operation this module's command line offers.
    """

    @abstractmethod
    def run(self, arguments: argparse.Namespace, project_root: Path) -> OperationReport:
        """
        Do the work the parsed command line asks for.

        :param arguments: The parsed command line.
        :param project_root: The repository to run within.
        :return: What the operation found or wrote.
        """

    @staticmethod
    def parser() -> argparse.ArgumentParser:
        """
        :return: The argument parser, built from every command.
        """
        parser = argparse.ArgumentParser(
            description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
        )
        subcommands = parser.add_subparsers(dest="subcommand", required=True)
        for command in BootstrapCommand.every_command():
            command.declare_arguments(
                subcommands.add_parser(command.invoked_as, help=command.description)
            )
        return parser


@dataclass(frozen=True)
class RecordCommand(BootstrapCommand):
    """
    Writes an item's manifest entry, and a standing rule it settled.
    """

    @classproperty
    def invoked_as(cls) -> str:
        return "record"

    @classproperty
    def description(cls) -> str:
        return "Write an item's manifest entry and its roadmap entry, if any"

    def declare_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--plan", required=True)
        parser.add_argument("--item", required=True)
        parser.add_argument("--status", required=True, type=ItemStatus)
        parser.add_argument("--roadmap-entry")
        parser.add_argument("--title")
        parser.add_argument("--track")

    def run(self, arguments: argparse.Namespace, project_root: Path) -> BootstrapReport:
        return ItemRecordRequest(
            plan_identifier=arguments.plan,
            item_identifier=arguments.item,
            status=arguments.status,
            roadmap_entry=arguments.roadmap_entry,
            title=arguments.title,
            track=arguments.track,
        ).record(project_root)


@dataclass(frozen=True)
class OpenCommand(BootstrapCommand):
    """
    Creates the item's branch and draft pull request, and records them.
    """

    @classproperty
    def invoked_as(cls) -> str:
        return "open"

    @classproperty
    def description(cls) -> str:
        return "Create the item's branch and draft pull request"

    def declare_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--plan", required=True)
        parser.add_argument("--item", required=True)
        parser.add_argument("--branch", required=True)
        parser.add_argument("--base", required=True)
        parser.add_argument("--session", required=True)
        parser.add_argument(
            "--pull-request-title",
            help="Required unless --pull-request-number is given",
        )
        parser.add_argument(
            "--pull-request-body",
            type=Path,
            help="Required unless --pull-request-number is given",
        )
        parser.add_argument(
            "--pull-request-number",
            type=int,
            help="Record a pull request the caller already created, instead of creating one",
        )
        parser.add_argument("--remote", default="origin")

    def run(self, arguments: argparse.Namespace, project_root: Path) -> BootstrapReport:
        return WorkOpener(project_root=project_root, remote=arguments.remote).open(
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


@dataclass(frozen=True)
class UpdateCommand(BootstrapCommand):
    """
    Sets an item's recorded fields, reading prose from files.
    """

    @classproperty
    def invoked_as(cls) -> str:
        return "update"

    @classproperty
    def description(cls) -> str:
        return "Set an item's recorded fields"

    def declare_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--plan", required=True)
        parser.add_argument("--item", required=True)
        parser.add_argument("--status", type=ItemStatus)
        parser.add_argument("--branch")
        parser.add_argument("--pull-request-number", type=int)
        parser.add_argument("--session")
        notes = parser.add_mutually_exclusive_group()
        notes.add_argument(
            "--notes", type=Path, help="A file whose text becomes the item's notes"
        )
        notes.add_argument(
            "--append-notes",
            type=Path,
            help="A file whose text is added to the item's notes as a new paragraph",
        )
        parser.add_argument(
            "--blockers",
            type=Path,
            action="append",
            help="A file whose text becomes one blocker; repeat for each",
        )

    def run(self, arguments: argparse.Namespace, project_root: Path) -> BootstrapReport:
        values_by_key: dict[ManifestKey, Any] = {
            manifest_key: value
            for manifest_key, value in (
                (ManifestKey.STATUS, arguments.status),
                (ManifestKey.BRANCH, arguments.branch),
                (ManifestKey.PULL_REQUEST_NUMBER, arguments.pull_request_number),
                (ManifestKey.SESSION, arguments.session),
            )
            if value is not None
        }
        if arguments.notes:
            values_by_key[ManifestKey.NOTES] = arguments.notes.read_text()
        if arguments.blockers:
            values_by_key[ManifestKey.BLOCKERS] = [
                blocker.read_text().strip() for blocker in arguments.blockers
            ]
        return ItemUpdateRequest(
            plan_identifier=arguments.plan,
            item_identifier=arguments.item,
            values_by_key=values_by_key,
            notes_to_append=(
                arguments.append_notes.read_text() if arguments.append_notes else None
            ),
        ).update(project_root)


@dataclass(frozen=True)
class CheckCommand(BootstrapCommand):
    """
    Reports which of an item's recorded fields local git contradicts.
    """

    @classproperty
    def invoked_as(cls) -> str:
        return "check"

    @classproperty
    def description(cls) -> str:
        return "Report which recorded fields local git contradicts"

    def declare_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--plan", required=True)
        parser.add_argument("--item", required=True)
        parser.add_argument("--remote", default="origin")

    def run(self, arguments: argparse.Namespace, project_root: Path) -> StalenessReport:
        return ItemCheckRequest(
            plan_identifier=arguments.plan,
            item_identifier=arguments.item,
            remote=arguments.remote,
        ).check(project_root)


@dataclass(frozen=True)
class ResolveCommand(BootstrapCommand):
    """
    Names the plan and the items a branch belongs to.
    """

    @classproperty
    def invoked_as(cls) -> str:
        return "resolve"

    @classproperty
    def description(cls) -> str:
        return "Name the plan and items a branch belongs to"

    def declare_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--branch", required=True)

    def run(self, arguments: argparse.Namespace, project_root: Path) -> BranchReport:
        return BranchReport.of_branch(arguments.branch, project_root)


@dataclass(frozen=True)
class BlockCommand(BootstrapCommand):
    """
    Records an owner's blocker on every item a branch carries.
    """

    @classproperty
    def invoked_as(cls) -> str:
        return "block"

    @classproperty
    def description(cls) -> str:
        return "Record your own blocker on every item a branch carries"

    def declare_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--branch", required=True)
        parser.add_argument("--owner", required=True)
        parser.add_argument(
            "--reason",
            required=True,
            type=Path,
            help="A file whose text is the blocker",
        )

    def run(self, arguments: argparse.Namespace, project_root: Path) -> BranchReport:
        return OwnedBlocker(
            branch=arguments.branch,
            owner=arguments.owner,
            reason=arguments.reason.read_text().strip(),
        ).write(project_root)


@dataclass(frozen=True)
class UnblockCommand(BootstrapCommand):
    """
    Withdraws an owner's blocker from every item a branch carries.
    """

    @classproperty
    def invoked_as(cls) -> str:
        return "unblock"

    @classproperty
    def description(cls) -> str:
        return "Clear your own blocker from every item a branch carries"

    def declare_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--branch", required=True)
        parser.add_argument("--owner", required=True)

    def run(self, arguments: argparse.Namespace, project_root: Path) -> BranchReport:
        return OwnedBlocker(branch=arguments.branch, owner=arguments.owner).write(
            project_root
        )


def main() -> int:
    """
    Parse arguments, run the requested operation, and print its report.

    See the module docstring for the command line contract.
    """
    arguments = BootstrapCommand.parser().parse_args()
    project_root = Path(
        os.environ.get(ClaudeCodeVariable.PROJECT_DIRECTORY, Path.cwd())
    )

    command = next(
        command
        for command in BootstrapCommand.every_command()
        if command.invoked_as == arguments.subcommand
    )
    try:
        report = command.run(arguments, project_root)
    except BootstrapError as error:
        logger.error(f"{error.exit_code.name_for_a_caller}: {error}")
        return int(error.exit_code)

    logger.info(json.dumps(report.as_document()))
    return int(report.exit_code)


if __name__ == "__main__":
    sys.exit(main())
