"""
GitHub's form opening a pull request, with its title and description filled in from its
address.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import quote

from basstler.class_property import classproperty
from basstler.repository import Repository

# %% the form's parameters


class PullRequestFormParameter(StrEnum):
    """
    The query parameters of a compare-and-create link.
    """

    EXPAND = "expand"
    """
    Opens the pull request form rather than only the comparison.
    """

    TITLE = "title"
    """
    The title to prefill.
    """

    BODY = "body"
    """
    The description to prefill.
    """


# %% the filled-in form


@dataclass(frozen=True)
class PrefilledPullRequestLink:
    """
    A link opening the pull request form with its title and description filled in.
    """

    url: str
    """
    The compare-and-create URL, ready to open.
    """

    body_was_truncated: bool
    """
    Whether the description had to be shortened to fit the URL.
    """


@dataclass(frozen=True)
class PullRequestForm:
    """
    The pull request form for one branch, filled in from its address.

    The prefill travels in the query string, so an unencoded character truncates it and
    an oversized one is discarded whole by the server - both silently.
    """

    repository: Repository
    """
    The repository the pull request is opened on.
    """

    base: str
    """
    The branch it merges into.
    """

    head: str
    """
    The branch it proposes, as ``owner:branch`` when it is on another owner's fork.
    """

    title: str
    """
    The title to prefill.
    """

    body: str
    """
    The description to prefill, shortened if the URL would not otherwise fit.
    """

    @classproperty
    def url_character_limit(cls) -> int:
        """
        Longest URL to build, the conventional 8 KiB request-line limit servers accept.
        """
        return 8192

    @classproperty
    def truncation_marker(cls) -> str:
        """
        Appended to a body that had to be shortened, so the cut is visible in the
        prefill.
        """
        return "..."

    def url_for(self, body: str) -> str:
        """
        :param body: The description to prefill.
        :return: The form's address with :attr:`title` and *body* filled in.
        """
        return (
            f"{self.repository.url}/compare/{self.base}...{self.head}"
            f"?{PullRequestFormParameter.EXPAND}=1"
            f"&{PullRequestFormParameter.TITLE}={quote(self.title)}"
            f"&{PullRequestFormParameter.BODY}={quote(body)}"
        )

    @property
    def link(self) -> PrefilledPullRequestLink | None:
        """
        The link with :attr:`body` filled in, shortened to fit
        :attr:`url_character_limit`; ``None`` when even the title does not fit.
        """
        if len(self.url_for(self.body)) <= self.url_character_limit:
            return PrefilledPullRequestLink(
                self.url_for(self.body), body_was_truncated=False
            )
        if len(self.url_for(self.truncation_marker)) > self.url_character_limit:
            return None
        shortest, longest = 0, len(self.body)
        while shortest < longest:
            midpoint = (shortest + longest + 1) // 2
            candidate = self.url_for(self.body[:midpoint] + self.truncation_marker)
            shortest, longest = (
                (midpoint, longest)
                if len(candidate) <= self.url_character_limit
                else (shortest, midpoint - 1)
            )
        return PrefilledPullRequestLink(
            self.url_for(self.body[:shortest] + self.truncation_marker),
            body_was_truncated=True,
        )
