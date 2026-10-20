"""
A GitHub repository, identified the way GitHub itself writes it, and read out of the
references and git remote URLs the tooling is handed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class GitHubAddress(StrEnum):
    """
    The base URLs every GitHub address this package builds is built on.
    """

    WEB = "https://github.com"
    """
    The root of every web and clone URL.
    """

    API = "https://api.github.com"
    """
    The root of every REST call.
    """


@dataclass
class MalformedRepositoryError(ValueError):
    """
    Raised when a repository reference is not in ``owner/name`` form.
    """

    text: str
    """
    The value that could not be parsed.
    """

    def __str__(self) -> str:
        """:return: What was expected and what arrived instead."""
        return f"expected a repository as 'owner/name', got {self.text!r}"


@dataclass(frozen=True)
class Repository:
    """
    A GitHub repository, identified the way GitHub itself writes it.
    """

    owner: str
    """
    The user or organization the repository belongs to.
    """

    name: str
    """
    The repository's own name.
    """

    @classmethod
    def parse(cls, text: str) -> Repository:
        """
        Parse an ``owner/name`` repository reference.

        :param text: The reference to parse.
        :return: The parsed repository.
        :raises MalformedRepositoryError: If *text* is not ``owner/name``.
        """
        owner, separator, name = text.partition("/")
        if not (owner and separator and name):
            raise MalformedRepositoryError(text)
        return cls(owner, name)

    @staticmethod
    def _remote_url_segments(url: str) -> list[str]:
        """
        Split a remote URL into its path segments, discarding scheme and host.

        :param url: The remote URL to split.
        :return: The path segments, which name a repository when there are two or more.
        """
        reference = url.removesuffix(".git").rstrip("/")
        if "://" in reference:
            _, _, host_and_path = reference.partition("://")
            _, _, path = host_and_path.partition("/")
        elif ":" in reference:
            _, _, path = reference.rpartition(":")
        else:
            return []
        return [segment for segment in path.split("/") if segment]

    @classmethod
    def names_a_repository(cls, url: str) -> bool:
        """
        Test whether a remote URL points at a repository at all.

        :param url: The remote URL to test.
        :return: Whether it names an ``owner/name`` pair.
        """
        return len(cls._remote_url_segments(url)) >= 2

    @classmethod
    def from_remote_url(cls, url: str) -> Repository:
        """
        Read the repository a git remote URL points at.

        Accepts every form a fork remote takes - HTTPS, SSH, and the local proxy a cloud
        session is given - by discarding the host and taking the last two path segments.

        :param url: The remote URL to read.
        :return: The repository it names.
        :raises MalformedRepositoryError: If *url* names no ``owner/name`` pair.
        """
        segments = cls._remote_url_segments(url)
        if len(segments) < 2:
            raise MalformedRepositoryError(url)
        return cls.parse("/".join(segments[-2:]))

    @property
    def full_name(self) -> str:
        """
        The ``owner/name`` form GitHub's own interface and the ``gh`` CLI use.
        """
        return f"{self.owner}/{self.name}"

    @property
    def url(self) -> str:
        """
        The repository's page on GitHub, which is also the base of every page within it.
        """
        return f"{GitHubAddress.WEB}/{self.full_name}"

    @property
    def clone_url(self) -> str:
        """
        The HTTPS URL git clones and fetches the repository from.
        """
        return self.clone_url_under()

    def clone_url_under(self, root: str = GitHubAddress.WEB) -> str:
        """
        :param root: Where repositories are kept as ``<root>/owner/name.git``: GitHub
            itself, or a directory of bare repositories standing in for it.
        :return: The URL git clones and fetches this repository from there.
        """
        return f"{root}/{self.full_name}.git"

    def pull_request_url(self, number: int) -> str:
        """
        :param number: The pull request's number.
        :return: The pull request's page on GitHub.
        """
        return f"{self.url}/pull/{number}"

    def issue_url(self, number: int) -> str:
        """
        :param number: The issue's number.
        :return: The issue's page on GitHub.
        """
        return f"{self.url}/issues/{number}"

    @property
    def api_path(self) -> str:
        """
        The repository's REST path, relative to :attr:`GitHubAddress.API`, which is also
        the base of every REST path within it and what ``gh api`` takes.
        """
        return f"repos/{self.full_name}"

    def job_log_path(self, job: int) -> str:
        """
        :param job: The Actions job's own number.
        :return: The REST path of that job's whole recorded log.
        """
        return f"{self.api_path}/actions/jobs/{job}/logs"

    def git_requirement(self, distribution: str, reference: str) -> str:
        """
        A pip requirement installing a distribution straight from this repository.

        :param distribution: The distribution the repository builds.
        :param reference: The tag, branch or commit to install it at.
        :return: The requirement, as ``pip install`` takes it.
        """
        return f"{distribution} @ git+{self.url}@{reference}"

    def __str__(self) -> str:
        """:return: :attr:`full_name`."""
        return self.full_name


PACKAGE_REPOSITORY = Repository("AbdelrhmanBassiouny", "basstler")
"""
The repository this package is developed and released from, which also holds the
dispatch-only workflow that reads a project's upstream pull request for it.
"""


@dataclass(frozen=True)
class PullRequestReference:
    """
    One pull request, named by the repository it is opened on and its number.

    Identity only: what a pull request currently *is* - open, merged, labelled - is read
    into a record of its own by whichever caller needs it.
    """

    repository: Repository
    """
    The repository the pull request is opened on.
    """

    number: int
    """
    The pull request's number.
    """

    @property
    def url(self) -> str:
        """
        The pull request's page on GitHub.
        """
        return self.repository.pull_request_url(self.number)
