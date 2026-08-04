#!/usr/bin/env python3
"""
Bootstrap a plan item before its implementation, rather than after it.

Everything a session knows the moment an implementation plan is approved - the branch,
the draft pull request, the item's manifest fields, its roadmap section - is derivable
without a line of the implementation, yet all of it conventionally happens at the end.
For that whole window ``plan.yaml`` says the item is ``not_started`` with no branch while
a branch exists and is being worked, which every dashboard, kickoff and resolve run
downstream reads as truth.

Two operations, so each caller depends only on the surface it uses:

``record``
    Write or update the item's ``plan.yaml`` entry and append its ``roadmap.md``
    section, set its status, and push both through ``save-plan.sh``.

``open``
    Create the branch, publish it, open the draft pull request, then write ``branch``,
    ``session`` and ``pull_request_number`` back onto the item and flip it to
    ``in_progress``. A caller that has already created the pull request passes
    ``--pull-request-number`` and only the recording happens.

``open`` runs before ``record`` when both are wanted: the pull request number does not
exist until the pull request does.

Usage:
    python3 plan_item_bootstrap.py record --plan <plan-id> --item <item-id> \\
        --status <status> --roadmap-section <file> [--title <title>] [--track <track>]
    python3 plan_item_bootstrap.py open --plan <plan-id> --item <item-id> \\
        --branch <branch> --base <branch> --session <url> \\
        --pull-request-title <title> --pull-request-body <file>

Prints a one-line JSON report led by ``status`` and ``exit_code``, so a caller acting on
the document never has to decode an integer back into a meaning.

.. note::
   Republishing the dashboard is deliberately not done here. Only a live session can
   call the ``Artifact`` tool, so both operations hand back the ``/plan-dashboard``
   command to run instead, exactly as ``save-plan.sh`` already does.

.. note::
   The manifest is edited by patching only the lines that change. A full YAML
   load-mutate-dump round trip is rejected for the reason ``sync_manifest_status.py``
   records: even a format-preserving library re-flows wrapped strings, turning a
   one-field edit into an unreadable diff across the whole file.
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
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from pathlib import Path
from typing import Any, Protocol

import yaml

GITHUB_API_ROOT = "https://api.github.com"
"""
Where pull requests are created, overridable for a GitHub Enterprise host.
"""

CONFIGURATION_SCRIPT = ".claude/hooks/resolve-personal-notes-config.sh"
"""
The shell script that owns personal-notes remote/branch resolution, sourced rather than
reimplemented so the two can never disagree.
"""

SAVE_PLAN_SCRIPT = ".claude/hooks/save-plan.sh"
"""
The script that pushes an edited manifest and roadmap to the personal-notes branch.
"""

ITEM_START_PATTERN = re.compile(r"^\s*- id:")
"""
Matches the first line of an item block in ``plan.yaml``.

Same anchor ``sync_manifest_status.py`` uses to find item boundaries in raw text.
"""

TOP_LEVEL_KEY_PATTERN = re.compile(r"^\S")
"""
Matches a top-level ``plan.yaml`` key, which is where the last item block ends.
"""

FOLDED_FIELD_PATTERN = re.compile(r"^\s*(notes|blockers):")
"""
Matches an item field whose value may run over several following lines, so a new field
is inserted before it rather than after.
"""

ITEM_FIELD_INDENT = "    "
"""
The indentation ``plan.yaml`` item fields carry, one level inside the list marker.
"""


class ItemStatus(StrEnum):
    """
    The statuses ``plan.yaml``'s ``status`` field accepts.

    Mirrors ``build_dashboard.py``'s own enum, which lives in the plan-dashboard skill
    directory and is not importable from here until ``development_tooling`` gives both a
    shared home.
    """

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DEFERRED = "deferred"
    DONE = "done"


class ExitCode(IntEnum):
    """
    The process statuses this tool exits with.

    Values are distinct rather than aligned with ``stack.py``'s own ``ExitCode``, which
    is not reachable from ``main``; aligning the two belongs with whichever item brings
    them into one package.
    """

    SUCCESS = 0
    UNKNOWN_PLAN = 3
    UNKNOWN_ITEM = 4
    INCOMPLETE_NEW_ITEM = 5
    BRANCH_ALREADY_PUBLISHED = 6
    PULL_REQUEST_DETAILS_MISSING = 7
    PULL_REQUEST_REFUSED = 8

    @property
    def name_for_a_caller(self) -> str:
        """
        The status's own name, for a report a person or a script has to act on.

        Derived from the member rather than a table beside it, so a status can never
        carry a name belonging to a different one.
        """
        return self.name.lower()


# %% failures


class BootstrapError(Exception):
    """
    Base for every refusal this tool reports, each carrying its own exit status.
    """

    exit_code = ExitCode.SUCCESS
    """
    The process status this refusal exits with.
    """


class UnknownPlanError(BootstrapError):
    """
    Raised when the named plan has no manifest on the personal-notes branch.
    """

    exit_code = ExitCode.UNKNOWN_PLAN


class UnknownItemError(BootstrapError):
    """
    Raised when the named item is absent from an otherwise resolvable plan.
    """

    exit_code = ExitCode.UNKNOWN_ITEM


class IncompleteNewItemError(BootstrapError):
    """
    Raised when an item that does not exist yet is recorded without the fields needed to
    write its entry.
    """

    exit_code = ExitCode.INCOMPLETE_NEW_ITEM


class BranchAlreadyPublishedError(BootstrapError):
    """
    Raised when the branch to open already exists on the remote, which means work is
    underway and overwriting it would discard someone's commits.
    """

    exit_code = ExitCode.BRANCH_ALREADY_PUBLISHED


class PullRequestDetailsMissingError(BootstrapError):
    """
    Raised when opening the work must create a pull request but was given neither a
    title nor a body to create it from.
    """

    exit_code = ExitCode.PULL_REQUEST_DETAILS_MISSING


class PullRequestRefusedError(BootstrapError):
    """
    Raised when the remote declines to create the pull request.
    """

    exit_code = ExitCode.PULL_REQUEST_REFUSED


class NotesBranchUnavailableError(BootstrapError):
    """
    Raised when the personal-notes branch cannot be fetched, so there is no plan data to
    read or write.
    """

    exit_code = ExitCode.UNKNOWN_PLAN


# %% the plan on the personal-notes branch


def run_git(*arguments: str, project_root: Path) -> str:
    """
    Run git in *project_root* and return its standard output.

    :param arguments: The arguments to pass to git.
    :param project_root: The repository to run within.
    :raises subprocess.CalledProcessError: If git reports an error.
    :return: Standard output, stripped of its trailing newline.
    """
    result = subprocess.run(
        ["git", *arguments],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.rstrip("\n")


@dataclass(frozen=True)
class PlanLocation:
    """
    Where one plan's manifest and roadmap live, as the shell configuration resolves it.
    """

    manifest_path: str
    """
    The manifest's path within the personal-notes branch.
    """

    roadmap_path: str
    """
    The roadmap's path within the personal-notes branch.
    """

    @classmethod
    def resolve(cls, plan_identifier: str, project_root: Path) -> PlanLocation:
        """
        Fetch the personal-notes branch and resolve *plan_identifier*'s paths within it.

        Sources the shell configuration and calls its own fetch function rather than
        re-deriving the remote/branch precedence, so this and the hook scripts can never
        disagree about which branch a plan is on.

        :param plan_identifier: The plan's id.
        :param project_root: The repository to resolve within.
        :raises NotesBranchUnavailableError: If the notes branch cannot be fetched.
        :return: The resolved location, with ``FETCH_HEAD`` left pointing at the branch.
        """
        probe = subprocess.run(
            [
                "bash",
                "-c",
                f'source "{CONFIGURATION_SCRIPT}" && fetch_personal_notes_branch && '
                'printf "%s\\n%s\\n" '
                '"$(plan_manifest_path "$1")" "$(plan_roadmap_path "$1")"',
                "plan_item_bootstrap",
                plan_identifier,
            ],
            cwd=project_root,
            capture_output=True,
            text=True,
        )
        if probe.returncode != 0:
            raise NotesBranchUnavailableError(
                "could not fetch the personal-notes branch: "
                f"{probe.stderr.strip() or 'no personal-notes branch found'}"
            )
        manifest_path, roadmap_path = probe.stdout.strip().split("\n")
        return cls(manifest_path=manifest_path, roadmap_path=roadmap_path)


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
        location = PlanLocation.resolve(plan_identifier, project_root)
        try:
            manifest_text = run_git(
                "show",
                f"FETCH_HEAD:{location.manifest_path}",
                project_root=project_root,
            )
            roadmap_text = run_git(
                "show", f"FETCH_HEAD:{location.roadmap_path}", project_root=project_root
            )
        except subprocess.CalledProcessError as error:
            raise UnknownPlanError(
                f"no plan {plan_identifier!r} on the personal-notes branch "
                f"({location.manifest_path} is not there)"
            ) from error
        return cls(
            plan_identifier=plan_identifier,
            manifest_text=manifest_text + "\n",
            roadmap_text=roadmap_text + "\n",
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
        :return: The item's own ``repository``, or the plan's ``default_repository``.
        """
        item = self.item(item_identifier)
        return item.get("repository") or self.manifest["default_repository"]

    def item(self, item_identifier: str) -> dict[str, Any]:
        """
        One item's parsed mapping.

        :param item_identifier: The item's id, or its branch when it has no id.
        :raises UnknownItemError: If no item matches.
        :return: The item's mapping.
        """
        for candidate in self.manifest.get("items", []):
            if (candidate.get("id") or candidate.get("branch")) == item_identifier:
                return candidate
        raise UnknownItemError(
            f"no item {item_identifier!r} in plan {self.plan_identifier!r}"
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
            manifest_file = scratch / "plan.yaml"
            roadmap_file = scratch / "roadmap.md"
            manifest_file.write_text(manifest_text)
            roadmap_file.write_text(roadmap_text)
            subprocess.run(
                [
                    "bash",
                    SAVE_PLAN_SCRIPT,
                    self.plan_identifier,
                    "--manifest",
                    str(manifest_file),
                    "--roadmap",
                    str(roadmap_file),
                ],
                cwd=project_root,
                capture_output=True,
                text=True,
                check=True,
            )


# %% patching one item's fields in the manifest text


def item_block_bounds(manifest_lines: list[str]) -> list[tuple[int, int]]:
    """
    The half-open line range of every item block in the manifest.

    :param manifest_lines: The manifest, split into lines.
    :return: One ``(start, end)`` pair per item, in manifest order.
    """
    starts = [
        index
        for index, line in enumerate(manifest_lines)
        if ITEM_START_PATTERN.match(line)
    ]
    if not starts:
        return []
    end_of_items = next(
        (
            index
            for index in range(starts[-1] + 1, len(manifest_lines))
            if TOP_LEVEL_KEY_PATTERN.match(manifest_lines[index])
        ),
        len(manifest_lines),
    )
    boundaries = starts[1:] + [end_of_items]
    return list(zip(starts, boundaries))


def locate_item_block(
    manifest_lines: list[str], item_identifier: str
) -> tuple[int, int]:
    """
    Find one item's block within the manifest text.

    :param manifest_lines: The manifest, split into lines.
    :param item_identifier: The item's id.
    :raises UnknownItemError: If no block starts with that id.
    :return: The block's half-open line range.
    """
    for start, end in item_block_bounds(manifest_lines):
        if manifest_lines[start].strip().removeprefix("- id:").strip() == (
            item_identifier
        ):
            return start, end
    raise UnknownItemError(
        f"no item block for {item_identifier!r} in the manifest text"
    )


def apply_item_fields(
    manifest_text: str, item_identifier: str, fields: dict[str, str]
) -> str:
    """
    Set each of *fields* on one item, patching an existing line or inserting a new one.

    Every other line is left byte-for-byte untouched, so comments, key order, string
    wrapping and quoting all survive.

    :param manifest_text: The manifest's raw text.
    :param item_identifier: The item to patch.
    :param fields: Field names mapped to their rendered YAML values.
    :raises UnknownItemError: If the item has no block in the text.
    :return: The patched manifest text.
    """
    lines = manifest_text.split("\n")
    start, end = locate_item_block(lines, item_identifier)
    for field_name, value in fields.items():
        field_pattern = re.compile(rf"^(\s*{re.escape(field_name)}:\s*).*$")
        existing = next(
            (index for index in range(start, end) if field_pattern.match(lines[index])),
            None,
        )
        if existing is not None:
            lines[existing] = f"{ITEM_FIELD_INDENT}{field_name}: {value}"
            continue
        insertion = next(
            (
                index
                for index in range(start, end)
                if FOLDED_FIELD_PATTERN.match(lines[index])
            ),
            last_populated_line(lines, start, end) + 1,
        )
        lines.insert(insertion, f"{ITEM_FIELD_INDENT}{field_name}: {value}")
        end += 1
    return "\n".join(lines)


def last_populated_line(manifest_lines: list[str], start: int, end: int) -> int:
    """
    The last non-blank line of a block, so an appended field lands inside it.

    :param manifest_lines: The manifest, split into lines.
    :param start: The block's first line.
    :param end: One past the block's last line.
    :return: The index of the block's last non-blank line.
    """
    return max(
        (index for index in range(start, end) if manifest_lines[index].strip()),
        default=start,
    )


def render_new_item(request: ItemRecordRequest) -> str:
    """
    Render a brand-new item block, in the field order ``plan-schema.md`` documents.

    :param request: The item to record.
    :raises IncompleteNewItemError: If a field a new entry cannot omit is missing.
    :return: The block's text, newline-terminated.
    """
    if not request.title or not request.track:
        raise IncompleteNewItemError(
            f"item {request.item_identifier!r} is not in the plan yet, so recording it "
            "needs --title and --track"
        )
    return (
        f"  - id: {request.item_identifier}\n"
        f'{ITEM_FIELD_INDENT}title: "{request.title}"\n'
        f"{ITEM_FIELD_INDENT}branch: null\n"
        f"{ITEM_FIELD_INDENT}track: {request.track}\n"
        f"{ITEM_FIELD_INDENT}depends_on: []\n"
        f"{ITEM_FIELD_INDENT}status: {request.status.value}\n"
    )


def append_item(manifest_text: str, block: str) -> str:
    """
    Add a rendered item block after the manifest's last item.

    :param manifest_text: The manifest's raw text.
    :param block: The block to append, as :func:`render_new_item` renders it.
    :return: The extended manifest text.
    """
    lines = manifest_text.split("\n")
    bounds = item_block_bounds(lines)
    insertion = bounds[-1][1] if bounds else len(lines)
    tail = "\n".join(lines[insertion:])
    head = "\n".join(lines[:insertion]).rstrip("\n")
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

    roadmap_section_path: Path
    """
    A file whose markdown is appended to the plan's roadmap.
    """

    title: str | None = None
    """
    The item's title, required only when the entry does not exist yet.
    """

    track: str | None = None
    """
    The track the item belongs to, required only when the entry does not exist yet.
    """


@dataclass(frozen=True)
class BootstrapReport:
    """
    What an operation did, in the shape a caller acts on.
    """

    exit_code: ExitCode
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
            document["branch"] = self.branch
        if self.pull_request_number is not None:
            document["pull_request_number"] = self.pull_request_number
            document["pull_request_url"] = self.pull_request_url
        return document


def record_item(request: ItemRecordRequest, project_root: Path) -> BootstrapReport:
    """
    Write or update one item's manifest entry and roadmap section, then push both.

    :param request: The item to record.
    :param project_root: The repository to run within.
    :raises UnknownPlanError: If the plan has no manifest on the notes branch.
    :raises IncompleteNewItemError: If a new entry is missing a field it cannot omit.
    :return: What was recorded.
    """
    documents = PlanDocuments.load(request.plan_identifier, project_root)
    created_item = not documents.has_item(request.item_identifier)

    if created_item:
        manifest_text = append_item(documents.manifest_text, render_new_item(request))
    else:
        manifest_text = apply_item_fields(
            documents.manifest_text,
            request.item_identifier,
            {"status": request.status.value},
        )

    roadmap_text = append_roadmap_section(
        documents.roadmap_text, request.roadmap_section_path.read_text()
    )
    documents.save(manifest_text, roadmap_text, project_root)
    return BootstrapReport(
        exit_code=ExitCode.SUCCESS,
        plan_identifier=request.plan_identifier,
        item_identifier=request.item_identifier,
        created_item=created_item,
    )


def append_roadmap_section(roadmap_text: str, section: str) -> str:
    """
    Add one section to the end of a roadmap, separated by a blank line.

    :param roadmap_text: The roadmap as it stands.
    :param section: The markdown to append.
    :return: The extended roadmap.
    """
    return f"{roadmap_text.rstrip(chr(10))}\n\n{section.lstrip(chr(10))}"


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

    api_root: str = GITHUB_API_ROOT
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
                f"GitHub refused to create the pull request ({error.code}): "
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
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        return {"Authorization": f"Bearer {token}"} if token else {}


@dataclass(frozen=True)
class WorkOpenRequest:
    """
    What opening an item's work needs: the branch to create and the pull request to
    open on it.
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
    through rather than to the person running it, so a caller that can create one under
    its own identity should, and hand the number here. Left unset, the module creates it
    - which is what an unattended run with no session has to do.
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
        listing = run_git(
            "ls-remote", "--heads", self.remote, branch, project_root=self.project_root
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
        run_git(
            "checkout",
            "-b",
            request.branch,
            request.base_branch,
            project_root=self.project_root,
        )
        run_git(
            "commit",
            "--allow-empty",
            "--quiet",
            "-m",
            f"Bootstrap {request.item_identifier}",
            project_root=self.project_root,
        )
        run_git(
            "push",
            "-u",
            self.remote,
            request.branch,
            project_root=self.project_root,
        )


def open_work(
    request: WorkOpenRequest,
    project_root: Path,
    pull_request_opener: PullRequestOpener | None = None,
    remote: str = "origin",
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
    :param project_root: The repository to run within.
    :param pull_request_opener: What creates the pull request, defaulting to GitHub.
    :param remote: The remote to publish the branch to.
    :raises UnknownItemError: If the plan does not track the item yet.
    :raises BranchAlreadyPublishedError: If the branch already exists on the remote.
    :raises PullRequestRefusedError: If the pull request could not be created.
    :return: What was opened.
    """
    opener = pull_request_opener or GitHubPullRequestOpener()
    if request.pull_request_number is None and not (
        request.pull_request_title and request.pull_request_body
    ):
        raise PullRequestDetailsMissingError(
            "opening the work has to create the pull request, so it needs a title and "
            "a body - or a --pull-request-number for one already created"
        )
    documents = PlanDocuments.load(request.plan_identifier, project_root)
    repository = documents.repository_for(request.item_identifier)

    work = WorkOpener(project_root=project_root, remote=remote)
    if not work.branch_is_published(request.branch):
        work.publish(request)
    elif request.pull_request_number is None:
        raise BranchAlreadyPublishedError(
            f"branch {request.branch!r} already exists on {remote!r} - it is already "
            "being worked, and republishing it would discard those commits"
        )

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

    manifest_text = apply_item_fields(
        documents.manifest_text,
        request.item_identifier,
        {
            "branch": request.branch,
            "pull_request_number": str(created.number),
            "session": request.session_url,
            "status": ItemStatus.IN_PROGRESS.value,
        },
    )
    documents.save(manifest_text, documents.roadmap_text, project_root)
    return BootstrapReport(
        exit_code=ExitCode.SUCCESS,
        plan_identifier=request.plan_identifier,
        item_identifier=request.item_identifier,
        branch=request.branch,
        pull_request_number=created.number,
        pull_request_url=created.html_url,
    )


# %% command line


def build_parser() -> argparse.ArgumentParser:
    """
    Build the argument parser for both subcommands.

    :return: The parser.
    """
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subcommands = parser.add_subparsers(dest="subcommand", required=True)

    record = subcommands.add_parser(
        "record", help="Write an item's manifest entry and roadmap section"
    )
    record.add_argument("--plan", required=True)
    record.add_argument("--item", required=True)
    record.add_argument("--status", required=True, type=ItemStatus)
    record.add_argument("--roadmap-section", required=True, type=Path)
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
        "--pull-request-title", help="Required unless --pull-request-number is given"
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
    arguments = build_parser().parse_args()
    project_root = Path(os.environ.get("CLAUDE_PROJECT_DIR", Path.cwd()))

    try:
        if arguments.subcommand == "record":
            report = record_item(
                ItemRecordRequest(
                    plan_identifier=arguments.plan,
                    item_identifier=arguments.item,
                    status=arguments.status,
                    roadmap_section_path=arguments.roadmap_section,
                    title=arguments.title,
                    track=arguments.track,
                ),
                project_root=project_root,
            )
        else:
            report = open_work(
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
                ),
                project_root=project_root,
                remote=arguments.remote,
            )
    except BootstrapError as error:
        print(f"{error.exit_code.name_for_a_caller}: {error}", file=sys.stderr)
        return int(error.exit_code)

    print(json.dumps(report.as_document()))
    return int(report.exit_code)


if __name__ == "__main__":
    sys.exit(main())
