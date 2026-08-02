#!/usr/bin/env python3
"""
Machine-readable landmarks of the prompt documents the cloud Routine runs on.

``ROUTINE.md`` is the doctrine the Routine executes and ``POINTER.md`` is the short
prompt registered at claude.ai/code/routines that resolves it. Both are prose, so
nothing in them can be imported and asserted against directly. This module declares the
landmarks they are required to contain and owns the extraction their contract tests
need, so renaming a section is one edit here rather than one per assertion.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, StrEnum
from pathlib import Path

# %% documents

DOCTRINE_DOCUMENT = Path(__file__).with_name("ROUTINE.md")
"""
The doctrine the Routine reads from git and executes each run.
"""

POINTER_DOCUMENT = Path(__file__).with_name("POINTER.md")
"""
The pointer prompt registered with the cloud Routine, which resolves the doctrine.
"""

PARAGRAPH_BREAK = "\n\n"
"""
Separator ending the paragraph :meth:`PromptDocument.paragraph` returns.
"""

# %% vocabulary the documents are required to use


class GitHubMcpTool(StrEnum):
    """
    GitHub MCP server tools the documents prescribe or forbid by name.
    """

    UPDATE_PULL_REQUEST = "update_pull_request"
    CREATE_PULL_REQUEST = "create_pull_request"
    SUBSCRIBE_PULL_REQUEST_ACTIVITY = "subscribe_pr_activity"


class PromptDirective(StrEnum):
    """
    Words an executable prompt uses to mark an instruction as non-negotiable.
    """

    HARD_RULES = "HARD RULES"
    NEVER = "NEVER"


class PointerPlaceholder(StrEnum):
    """
    Tokens in the pointer prompt a fork owner substitutes before registering it.
    """

    FORK_REPOSITORY = "<FORK_REPOSITORY>"
    TOOLING_BRANCH = "<TOOLING_BRANCH>"


@dataclass(frozen=True, eq=False)
class LandmarkSpecification:
    """
    One piece of literal text a prompt document is required to contain.
    """

    text: str
    """
    The literal text, exactly as it appears in the document.
    """

    purpose: str
    """
    What the document's contract depends on this landmark for.
    """


class DoctrineLandmark(LandmarkSpecification, Enum):
    """
    The structural landmarks the prompt documents are located by.

    Section extraction slices between these, so each text must occur exactly where the
    section it opens begins, and must not occur earlier in the document.
    """

    EXECUTABLE_PROMPT_FENCE = (
        "```text",
        "Opens the block the Routine executes; surrounding prose is commentary.",
    )
    CLOSING_FENCE = (
        "\n```",
        "Closes the executable block.",
    )
    HARD_RULES = (
        f"{PromptDirective.HARD_RULES} so you never drift into review work:",
        "Heads the rules that must bind before any file is read.",
    )
    PRE_FLIGHT = (
        "PRE-FLIGHT",
        "Heads the checks that precede every push, and so ends the hard rules.",
    )
    SETUP = (
        "\nSETUP\n",
        "Heads the steps that make the run's preconditions true.",
    )
    FORK_MAIN_UPDATE = (
        "1. UPDATE FORK MAIN FIRST",
        "First numbered setup step, and so ends step 0.",
    )
    PHASE_ONE = (
        "PHASE 1 - LANDED PARENTS",
        "Heads the phase owning every reparent instruction.",
    )
    PHASE_TWO = (
        "PHASE 2 - RESTACK",
        "Heads the restack phase, and so ends Phase 1.",
    )
    BASE_CHANGE_RULE = (
        "BASE CHANGES GO THROUGH THE GITHUB MCP SERVER.",
        "Opens the rule naming the one client able to retarget a base.",
    )
    ORPHANED_CHILD_SWEEP = (
        "REPARENT EVERY ORPHANED CHILD",
        "Opens the first of the two reparent sites.",
    )
    NATIVE_STACK_MEMBERS = (
        "NATIVE-STACK MEMBERS.",
        "Opens the sequence for children the plain retarget cannot move.",
    )
    MERGED_PARENT_LIST = (
        "For each OPEN fork PR (head branch B)",
        "Opens the second of the two reparent sites.",
    )


class LandmarkNotFoundError(LookupError):
    """
    Raised when a prompt document no longer contains a landmark it is required to
    contain.
    """

    def __init__(self, landmark: DoctrineLandmark, document: Path) -> None:
        super().__init__(
            f"{document.name} no longer contains {landmark.name}: {landmark.text!r} "
            f"({landmark.purpose})"
        )
        self.landmark = landmark
        """
        The landmark that could not be located.
        """
        self.document = document
        """
        The document that was searched.
        """


# %% the documents themselves


@dataclass(frozen=True)
class PromptDocument:
    """
    A markdown document carrying an executable prompt, and the parts of it callers
    assert on.
    """

    text: str
    """
    The document's full text.
    """

    path: Path
    """
    Where the text was read from.
    """

    @classmethod
    def load(cls, path: Path = DOCTRINE_DOCUMENT) -> PromptDocument:
        """
        Read a prompt document from disk.

        :param path: The document to read.
        :return: The loaded document.
        """
        return cls(path.read_text(), path)

    def position(self, landmark: DoctrineLandmark, start: int = 0) -> int:
        """
        Locate a landmark.

        :param landmark: The landmark to find.
        :param start: Index to search from.
        :return: Index at which the landmark's text begins.
        :raises LandmarkNotFoundError: If the document does not contain it.
        """
        index = self.text.find(landmark.text, start)
        if index < 0:
            raise LandmarkNotFoundError(landmark, self.path)
        return index

    def occurrences(self, landmark: DoctrineLandmark) -> int:
        """
        Count how often a landmark appears.

        :param landmark: The landmark to count.
        :return: Number of occurrences.
        """
        return self.text.count(landmark.text)

    def section(
        self, start: DoctrineLandmark, end: DoctrineLandmark | None = None
    ) -> str:
        """
        Extract the text between two landmarks.

        :param start: Landmark opening the section.
        :param end: Landmark opening the next section; omit to run to the document's
            end.
        :return: The section's text, including *start*'s own text.
        :raises LandmarkNotFoundError: If either landmark is missing.
        """
        begin = self.position(start)
        if end is None:
            return self.text[begin:]
        return self.text[begin : self.position(end, begin)]

    def paragraph(self, landmark: DoctrineLandmark) -> str:
        """
        Extract the single paragraph a landmark opens.

        :param landmark: Landmark opening the paragraph.
        :return: The text from the landmark up to the next blank line.
        :raises LandmarkNotFoundError: If the landmark is missing.
        """
        begin = self.position(landmark)
        return self.text[begin : self.text.index(PARAGRAPH_BREAK, begin)]

    def executable_prompt(self) -> str:
        """
        Extract the fenced block, the way the Routine's own prompt does.

        :return: The text between the opening and closing fences.
        :raises LandmarkNotFoundError: If either fence is missing.
        """
        fence = DoctrineLandmark.EXECUTABLE_PROMPT_FENCE
        begin = self.position(fence) + len(fence.text)
        return self.text[begin : self.position(DoctrineLandmark.CLOSING_FENCE, begin)]

    def hard_rules(self) -> str:
        """
        Extract the hard-rules block: its heading and every bullet beneath it.

        Parsing to the end of the bullets rather than to a following landmark lets the
        block be compared across documents that continue differently after it.

        :return: The heading line and its bullets.
        :raises LandmarkNotFoundError: If the block is missing.
        """
        lines = self.section(DoctrineLandmark.HARD_RULES).splitlines()
        block = [lines[0]]
        for line in lines[1:]:
            if not line.startswith(("- ", "  ")):
                break
            block.append(line)
        return "\n".join(block)
