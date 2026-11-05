"""
The size limits every plan and every pull request's progress notes are held to on save.
"""

from __future__ import annotations

import re
import shutil
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, StrEnum
from pathlib import Path
from typing import Annotated

from cyclopts import App, Parameter

from basstler.class_property import classproperty
from basstler.exit_codes import CommandFailure, ExitCode, SizeLimitExitCode
from basstler.plan.dependencies import DependencyReference
from basstler.plan.model import PlanDocument, PlanItem, PlanManifest
from basstler.standard_streams import StandardStreamHandler

logger = StandardStreamHandler.logger_for(__name__)
"""
This module's logger, which is also what its command prints through.
"""

# %% the limits


@dataclass(frozen=True)
class SizeLimit:
    """
    The most of one quantity a document may hold.
    """

    description: str
    """
    What is counted, as a phrase following the count.
    """

    maximum: int
    """
    The most a document may hold.
    """


class Measure(SizeLimit, Enum):
    """
    One quantity a document is measured by, with the most of it a document may hold.
    """

    ITEM_COUNT = ("items in the plan", 15)
    """
    A plan larger than this is two plans.
    """

    DESCRIPTION_LENGTH = ("characters in the plan's description", 600)
    """
    What the plan is for, in a paragraph.
    """

    NOTE_LENGTH = ("characters in an item's notes", 600)
    """
    What the item's next session needs: its scope and the decisions that bind it.
    """

    BLOCKER_COUNT = ("blockers on an item", 2)
    """
    The things an item currently waits on.
    """

    BLOCKER_LENGTH = ("characters in one blocker", 300)
    """
    One sentence naming what is awaited and from whom.
    """

    ROADMAP_ENTRY_COUNT = ("entries in the roadmap", 12)
    """
    The plan's standing rules, one entry each.
    """

    ROADMAP_ENTRY_LENGTH = ("characters in one roadmap entry", 400)
    """
    One standing rule and the reason it exists.
    """

    PROGRESS_LENGTH = ("characters in the progress notes", 2000)
    """
    A pull request's plan, what is done and what is next.
    """

    def violations(
        self, location: DocumentLocation, measured: int
    ) -> list[SizeViolation]:
        """
        :param location: Where the quantity was counted.
        :param measured: How much was counted.
        :return: The violation, when *measured* is over the limit; otherwise nothing.
        """
        if measured <= self.maximum:
            return []
        return [SizeViolation(measure=self, location=location, measured=measured)]

    def has_room(self, measured: int) -> bool:
        """
        :param measured: How much is already counted.
        :return: Whether one more would still fit within the limit.
        """
        return measured < self.maximum


# %% violations


class DocumentPart(StrEnum):
    """
    A part of a document a quantity is counted in.
    """

    PLAN = "plan"
    """
    The plan as a whole.
    """

    PLAN_DESCRIPTION = "plan description"
    """
    The plan's description.
    """

    ITEM = "item"
    """
    One of the plan's items.
    """

    ROADMAP = "roadmap"
    """
    The roadmap as a whole.
    """

    ROADMAP_ENTRY = "roadmap entry"
    """
    One of the roadmap's entries.
    """

    PROGRESS_NOTES = "progress notes"
    """
    A pull request's progress notes.
    """


class DocumentLocation(ABC):
    """
    Where in a document a quantity was counted.
    """

    @abstractmethod
    def __str__(self) -> str:
        """
        :return: The location, as a refusal names it.
        """


@dataclass(frozen=True)
class WholePartLocation(DocumentLocation):
    """
    A part of a document there is only one of.
    """

    part: DocumentPart
    """
    The part of the document.
    """

    def __str__(self) -> str:
        return self.part


@dataclass(frozen=True)
class ItemLocation(DocumentLocation):
    """
    One of the plan's items.
    """

    item_identifier: str
    """
    The item's id.
    """

    def __str__(self) -> str:
        return f"{DocumentPart.ITEM} {self.item_identifier!r}"


@dataclass(frozen=True)
class RoadmapEntryLocation(DocumentLocation):
    """
    One of the roadmap's entries.
    """

    entry_number: int
    """
    The entry's number, counted from one.
    """

    def __str__(self) -> str:
        return f"{DocumentPart.ROADMAP_ENTRY} {self.entry_number}"


@dataclass
class Violation(Exception, ABC):
    """
    Anything that makes a document refused.
    """

    @abstractmethod
    def __str__(self) -> str:
        """
        :return: What is wrong and where, as one line.
        """


@dataclass
class SizeViolation(Violation):
    """
    One measure a document holds more of than its limit allows.
    """

    measure: Measure
    """
    What was counted.
    """

    location: DocumentLocation
    """
    Where in the document it was counted.
    """

    measured: int
    """
    How much the document holds.
    """

    def __str__(self) -> str:
        return (
            f"{self.location}: {self.measured} {self.measure.description}, "
            f"over the limit of {self.measure.maximum}"
        )


@dataclass
class RoadmapFormatViolation(Violation):
    """
    A roadmap line that is neither the title, an entry, nor an entry's continuation.
    """

    line_number: int
    """
    The line's number, counted from one.
    """

    line: str
    """
    The line as written.
    """

    def __str__(self) -> str:
        return (
            f"roadmap line {self.line_number} is not a '- ' entry or its indented "
            f"continuation: {self.line[:80]!r}"
        )


@dataclass(frozen=True)
class DocumentSummary:
    """
    How a refusal names a document, and what it tells the author to keep.
    """

    description: str
    """
    The document, as a phrase.
    """

    content_to_keep: str
    """
    What the document is for, which is all it should hold.
    """


class LimitedDocument(DocumentSummary, Enum):
    """
    A document the limits are enforced on, with what to keep when it is refused.
    """

    PLAN = ("the plan", "the next step, what blocks it and the plan's standing rules")
    """
    A plan's manifest and roadmap.
    """

    PROGRESS_NOTES = ("the progress notes", "the plan, what is done and what is next")
    """
    A pull request's progress notes.
    """


@dataclass
class DocumentOverLimitError(CommandFailure):
    """
    Raised when a document breaks one of its limits.
    """

    @classproperty
    def exit_code(cls) -> SizeLimitExitCode:
        """:return: The status this kind of error ends a command with."""
        return SizeLimitExitCode.OVER_LIMIT

    document: LimitedDocument
    """
    The document that was refused.
    """

    violations: list[Violation]
    """
    Every limit the document breaks.
    """

    def __str__(self) -> str:
        """
        :return: One line per violation, then what the document should hold instead.
        """
        return "\n".join(
            [f"Refusing to save {self.document.description}:"]
            + [f"  {violation}" for violation in self.violations]
            + [
                f"Keep only {self.document.content_to_keep}; history belongs in git "
                "and on the pull requests."
            ]
        )


# %% the documents


class MeasuredDocument(ABC):
    """
    A document held to the limits.
    """

    @property
    @abstractmethod
    def limited_document(self) -> LimitedDocument:
        """
        :return: Which document this is, as a refusal names it.
        """

    @abstractmethod
    def violations(self) -> list[Violation]:
        """
        :return: Every limit the document breaks that it is refused for.
        """

    def warnings(self) -> list[Violation]:
        """
        :return: Every limit the document breaks that it is not refused for.
        """
        return []

    def check(self) -> None:
        """
        :raises DocumentOverLimitError: If the document breaks a limit.
        """
        violations = self.violations()
        if violations:
            raise DocumentOverLimitError(self.limited_document, violations)


class RoadmapLine(StrEnum):
    """
    The shapes a roadmap line may take, as the pattern each one matches.
    """

    TITLE = r"^# \S"
    """
    The roadmap's one heading, its first line.
    """

    ENTRY = r"^- \S"
    """
    The first line of an entry.
    """

    CONTINUATION = r"^  \S"
    """
    A further line of the entry above it.
    """


@dataclass(frozen=True)
class Roadmap:
    """
    A plan's ``roadmap.md``: a title, then the plan's standing rules as a list of
    entries.
    """

    entries: list[str]
    """
    Each entry with its line wrapping undone.
    """

    format_violations: list[RoadmapFormatViolation]
    """
    The lines that fit none of the roadmap's shapes.
    """

    @classmethod
    def from_text(cls, text: str) -> Roadmap:
        """
        :param text: The roadmap as written.
        :return: Its entries, and every line that is not part of one.
        """
        entries: list[str] = []
        format_violations: list[RoadmapFormatViolation] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            if line_number == 1 and re.match(RoadmapLine.TITLE, line):
                continue
            if re.match(RoadmapLine.ENTRY, line):
                entries.append(line[2:].strip())
            elif re.match(RoadmapLine.CONTINUATION, line) and entries:
                entries[-1] = f"{entries[-1]} {line.strip()}"
            else:
                format_violations.append(RoadmapFormatViolation(line_number, line))
        return cls(entries=entries, format_violations=format_violations)

    def violations(self) -> list[Violation]:
        """
        :return: Every limit the roadmap breaks.
        """
        violations: list[Violation] = list(self.format_violations)
        violations += Measure.ROADMAP_ENTRY_COUNT.violations(
            WholePartLocation(DocumentPart.ROADMAP), len(self.entries)
        )
        for number, entry in enumerate(self.entries, start=1):
            violations += Measure.ROADMAP_ENTRY_LENGTH.violations(
                RoadmapEntryLocation(number), len(entry)
            )
        return violations


@dataclass(frozen=True)
class Plan(MeasuredDocument):
    """
    A plan's manifest and roadmap, measured together.
    """

    manifest: PlanManifest
    """
    The plan's items and their state.
    """

    roadmap: Roadmap
    """
    The plan's standing rules.
    """

    stored_manifest: PlanManifest | None = None
    """
    The manifest this plan replaces, when one is already saved. An item identical to
    its stored entry is not being changed by the save.
    """

    @property
    def limited_document(self) -> LimitedDocument:
        return LimitedDocument.PLAN

    def item_is_changed(self, item: PlanItem) -> bool:
        """
        :param item: One of this plan's items.
        :return: Whether the save changes it: it is new, or differs from its stored entry.
        """
        if self.stored_manifest is None:
            return True
        return item not in self.stored_manifest.items

    def item_violations(self, item: PlanItem) -> list[Violation]:
        """
        :param item: One of this plan's items.
        :return: Every limit the item breaks.
        """
        location = ItemLocation(item.identifier)
        violations: list[Violation] = []
        violations += Measure.NOTE_LENGTH.violations(location, len(item.notes))
        violations += Measure.BLOCKER_COUNT.violations(location, len(item.blockers))
        for blocker in item.blockers:
            violations += Measure.BLOCKER_LENGTH.violations(location, len(blocker))
        return violations

    def manifest_violations(self) -> list[Violation]:
        """
        :return: Every limit the manifest breaks, except in an item the save leaves
            unchanged.
        """
        manifest = self.manifest
        violations: list[Violation] = []
        violations += Measure.ITEM_COUNT.violations(
            WholePartLocation(DocumentPart.PLAN), len(manifest.items)
        )
        violations += Measure.DESCRIPTION_LENGTH.violations(
            WholePartLocation(DocumentPart.PLAN_DESCRIPTION), len(manifest.description)
        )
        for item in manifest.items:
            if self.item_is_changed(item):
                violations += self.item_violations(item)
        return violations

    def violations(self) -> list[Violation]:
        return self.manifest_violations() + self.roadmap.violations()

    def warnings(self) -> list[Violation]:
        """
        :return: Every limit broken by an item the save leaves unchanged, which stays
            as it was saved.
        """
        return [
            violation
            for item in self.manifest.items
            if not self.item_is_changed(item)
            for violation in self.item_violations(item)
        ]


@dataclass(frozen=True)
class ProgressNotes(MeasuredDocument):
    """
    A pull request's progress notes.
    """

    text: str
    """
    The notes as written.
    """

    @classmethod
    def from_file(cls, path: Path) -> ProgressNotes:
        """
        :param path: A file holding a pull request's progress notes.
        :return: The notes it holds.
        """
        return cls(path.read_text())

    @property
    def limited_document(self) -> LimitedDocument:
        return LimitedDocument.PROGRESS_NOTES

    def violations(self) -> list[Violation]:
        return Measure.PROGRESS_LENGTH.violations(
            WholePartLocation(DocumentPart.PROGRESS_NOTES), len(self.text.strip())
        )


# %% staging a plan


class StagedPlan(StrEnum):
    """
    What staging a plan's files left at their destination.
    """

    SAVED = "saved"
    """
    The pruned manifest and the roadmap were written.
    """

    REMOVED = "removed"
    """
    Every item had landed, so the plan's directory was deleted.
    """


@dataclass(frozen=True)
class PlanFiles:
    """
    A plan's manifest and roadmap.
    """

    manifest: Path
    """
    The plan's ``plan.yaml``.
    """

    roadmap: Path
    """
    The plan's ``roadmap.md``.
    """

    def stage(self, destination: PlanFiles) -> StagedPlan:
        """
        Write the plan, without its landed items, to *destination*; a plan with no
        items left is finished, and its directory is deleted instead. A manifest with
        nothing landed is copied unchanged. An item the save leaves as it is already
        saved at *destination* is not refused for breaking a limit; it is warned about.

        :param destination: Where the plan is saved; both files share one directory.
        :raises DocumentOverLimitError: If the pruned plan breaks a limit, other than
            in an unchanged item.
        :return: Which of the two happened.
        """
        original = PlanManifest.from_file(self.manifest)
        manifest = original.without_landed_items()
        if not manifest.items:
            shutil.rmtree(destination.manifest.parent, ignore_errors=True)
            self.release_dependents(original, destination)
            return StagedPlan.REMOVED
        stored = (
            PlanManifest.from_file(destination.manifest)
            if destination.manifest.exists()
            else None
        )
        plan = Plan(manifest, Roadmap.from_text(self.roadmap.read_text()), stored)
        plan.check()
        for warning in plan.warnings():
            logger.warning(
                f"Saving anyway, as this save leaves it as it was: {warning}"
            )
        destination.manifest.parent.mkdir(parents=True, exist_ok=True)
        if original.landed_identifiers:
            manifest.write(destination.manifest)
        else:
            shutil.copyfile(self.manifest, destination.manifest)
        shutil.copyfile(self.roadmap, destination.roadmap)
        self.release_dependents(original, destination)
        return StagedPlan.SAVED

    def release_dependents(self, plan: PlanManifest, destination: PlanFiles) -> None:
        """
        Stop every other plan beside *destination* depending on an item of *plan* that
        has landed, since a landed item is removed from its plan and the entry would
        no longer resolve.

        :param plan: The plan being saved, with its landed items still in it.
        :param destination: Where the plan is saved; its directory's siblings hold the
            other plans.
        """
        landed_references = {
            DependencyReference(
                item_identifier=identifier, plan_id=plan.identifier
            ).text
            for identifier in plan.landed_identifiers
        }
        plans_directory = destination.manifest.parent.parent
        for manifest_path in sorted(plans_directory.glob(f"*/{PlanDocument.MANIFEST}")):
            if manifest_path == destination.manifest:
                continue
            dependent = PlanManifest.from_file(manifest_path)
            released = dependent.without_dependencies(landed_references)
            if released != dependent:
                released.write(manifest_path)


# %% command line


class SizeLimitCommand(StrEnum):
    """
    The subcommands this module's command line runs.
    """

    STAGE = "stage"
    """
    Write a plan without its landed items, or delete it once all have landed.
    """

    CHECK_PROGRESS = "check-progress"
    """
    Refuse progress notes over their limit.
    """


class SizeLimitOption(StrEnum):
    """
    The options this module's command line takes.
    """

    MANIFEST_DESTINATION = "--manifest-destination"
    """
    Where :attr:`SizeLimitCommand.STAGE` writes the manifest.
    """

    ROADMAP_DESTINATION = "--roadmap-destination"
    """
    Where :attr:`SizeLimitCommand.STAGE` writes the roadmap.
    """


size_limits_app = App(
    name="basstler.plan.size_limits",
    help="Hold plans and progress notes to their size limits on save.",
)
"""
This module's command line: one command per :class:`SizeLimitCommand`.
"""


@size_limits_app.command(name=SizeLimitCommand.STAGE)
def stage(
    manifest_path: Path,
    roadmap_path: Path,
    /,
    *,
    manifest_destination: Annotated[
        Path, Parameter(name=SizeLimitOption.MANIFEST_DESTINATION)
    ],
    roadmap_destination: Annotated[
        Path, Parameter(name=SizeLimitOption.ROADMAP_DESTINATION)
    ],
) -> SizeLimitExitCode:
    """
    Write a plan without its landed items, or delete it once all have landed, and print
    what was left at the destination.

    :param manifest_path: The manifest to stage.
    :param roadmap_path: The roadmap to stage.
    :param manifest_destination: Where to write the manifest.
    :param roadmap_destination: Where to write the roadmap.
    """
    source = PlanFiles(manifest_path, roadmap_path)
    logger.info(source.stage(PlanFiles(manifest_destination, roadmap_destination)))
    return SizeLimitExitCode.SUCCESS


@size_limits_app.command(name=SizeLimitCommand.CHECK_PROGRESS)
def check_progress(progress_path: Path, /) -> SizeLimitExitCode:
    """
    Refuse progress notes over their limit.

    :param progress_path: The progress notes to check.
    """
    ProgressNotes.from_file(progress_path).check()
    return SizeLimitExitCode.SUCCESS


def main() -> ExitCode:
    """
    Run the invoked command, ending with the status a refusal carries.

    :return: The process exit code.
    """
    try:
        return size_limits_app(sys.argv[1:], result_action="return_value")
    except CommandFailure as error:
        logger.error(f"{error}")
        return error.exit_code


if __name__ == "__main__":
    sys.exit(main())
