"""
An item issue's body: the item's scope, followed by the issues it depends on.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from basstler.plan_store.exceptions import MalformedDependencyError
from basstler.repository import Repository

# %% issue references


class ClosingKeyword(StrEnum):
    """
    The words with which a pull request's description closes the issue named after them.
    """

    CLOSE = "close"
    CLOSES = "closes"
    CLOSED = "closed"
    FIX = "fix"
    FIXES = "fixes"
    FIXED = "fixed"
    RESOLVE = "resolve"
    RESOLVES = "resolves"
    RESOLVED = "resolved"


REFERENCE_PATTERN = r"(?:(?P<owner>[\w.-]+)/(?P<name>[\w.-]+))?#(?P<number>\d+)"
"""
An issue reference as GitHub writes one: ``#12``, or ``owner/name#12`` for another
repository.
"""

CLOSING_REFERENCE = re.compile(
    rf"\b(?:{'|'.join(ClosingKeyword)}):?\s+{REFERENCE_PATTERN}\b", re.IGNORECASE
)
"""
A closing keyword followed by the reference of the issue it closes.
"""


@dataclass(frozen=True)
class IssueReference:
    """
    One issue, named by the repository it is opened on and its number.
    """

    repository: Repository
    """
    The repository the issue is opened on.
    """

    number: int
    """
    The issue's number.
    """

    @classmethod
    def from_match(cls, match: re.Match[str], home: Repository) -> IssueReference:
        """
        :param match: A match of :data:`REFERENCE_PATTERN`.
        :param home: The repository a reference without one names.
        :return: The issue the match names.
        """
        repository = (
            Repository(match["owner"], match["name"]) if match["owner"] else home
        )
        return cls(repository, int(match["number"]))

    @classmethod
    def closed_by(cls, text: str, home: Repository) -> set[IssueReference]:
        """
        :param text: A pull request's description.
        :param home: The repository the pull request is opened on.
        :return: Every issue the description closes.
        """
        return {
            cls.from_match(match, home) for match in CLOSING_REFERENCE.finditer(text)
        }

    def text_from(self, home: Repository) -> str:
        """
        :param home: The repository the text is written in.
        :return: The reference as GitHub writes it there.
        """
        if self.repository == home:
            return f"#{self.number}"
        return f"{self.repository.full_name}#{self.number}"


# %% the body


class ItemBodySection(StrEnum):
    """
    The headings an item issue's body is divided by after its scope.
    """

    DEPENDS_ON = "## Depends on"
    """
    Heads the list of the issues the item depends on, one ``- <reference>`` per line.
    """


DEPENDENCY_LINE = re.compile(rf"^- {REFERENCE_PATTERN}$")
"""
One entry of the dependency list.
"""


@dataclass(frozen=True)
class ItemBody:
    """
    What an item issue's body states: the item's scope and the issues it depends on.
    """

    scope: str
    """
    What the item delivers, as Markdown.
    """

    dependencies: tuple[IssueReference, ...] = ()
    """
    The issues that have to land before the item can.
    """

    @classmethod
    def parse(cls, text: str, home: Repository) -> ItemBody:
        """
        :param text: An item issue's body.
        :param home: The repository the issue is opened on.
        :return: The scope above the dependency list, and the issues the list names.
        :raises MalformedDependencyError: If a line of the list is not a reference.
        """
        scope, _, dependency_list = text.partition(ItemBodySection.DEPENDS_ON)
        dependencies = []
        for line in dependency_list.splitlines():
            if not line.strip():
                continue
            match = DEPENDENCY_LINE.match(line.strip())
            if match is None:
                raise MalformedDependencyError(line)
            dependencies.append(IssueReference.from_match(match, home))
        return cls(scope.strip(), tuple(dependencies))

    def render(self, home: Repository) -> str:
        """
        :param home: The repository the issue is opened on.
        :return: The body that :meth:`parse` reads back as this one.
        """
        if not self.dependencies:
            return self.scope
        dependency_list = "\n".join(
            f"- {dependency.text_from(home)}" for dependency in self.dependencies
        )
        return f"{self.scope}\n\n{ItemBodySection.DEPENDS_ON}\n\n{dependency_list}"
