"""
Writing one file of a repository, directly or proposed for its default branch through a
pull request.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Annotated
from urllib.parse import quote, urlencode

from pydantic import Field

from basstler.class_property import classproperty
from basstler.github.client import (
    GitHubAttemptClient,
    GitHubResponse,
    HttpMethod,
    RepositoryWrite,
)
from basstler.github.pull_request import NewPullRequest
from basstler.github.web_page import WebPage
from basstler.json_model import ValidatedJSONModel
from basstler.repository import Repository

# %% the contents API


class FileWrite(RepositoryWrite):
    """
    Creates one file on a branch of a repository, as one commit.
    """

    file: Annotated[str, Field(exclude=True)]
    """
    The file's path from the repository's root.
    """

    message: str
    """
    The commit's message.
    """

    content: str
    """
    The file's content, base64-encoded as the API takes it.
    """

    branch: str
    """
    The branch the commit is made on.
    """

    @classproperty
    def method(cls) -> HttpMethod:
        return HttpMethod.PUT

    @property
    def path(self) -> str:
        return f"{self.repository.api_path}/contents/{self.file}"


class FileUpdate(FileWrite):
    """
    Replaces one file on a branch of a repository, as one commit.
    """

    sha: str
    """
    The blob the file holds now, which the API requires to replace it.
    """


class RepositoryFile(ValidatedJSONModel):
    """
    One file of a repository, as the contents API returns it.
    """

    sha: str
    """
    The blob the file holds.
    """

    content: str
    """
    The file's content, base64-encoded with line breaks.
    """

    @property
    def text(self) -> str:
        """
        The file's content, decoded.
        """
        return base64.b64decode(self.content).decode()


# %% branches and pull requests


class ReferenceTarget(ValidatedJSONModel):
    """
    The commit a branch points at.
    """

    sha: str
    """
    The commit's hash.
    """


class BranchReference(ValidatedJSONModel):
    """
    One branch, as the git references API returns it.
    """

    target: Annotated[ReferenceTarget, Field(alias="object")]
    """
    The commit the branch points at.
    """


class NewBranch(RepositoryWrite):
    """
    A branch that does not exist yet, starting at one commit.
    """

    ref: str
    """
    The branch's full reference, ``refs/heads/<name>``.
    """

    sha: str
    """
    The commit it starts at.
    """

    @classproperty
    def method(cls) -> HttpMethod:
        return HttpMethod.POST

    @property
    def path(self) -> str:
        return f"{self.repository.api_path}/git/refs"


class OpenPullRequest(WebPage):
    """
    A pull request that is open.
    """

    number: int
    """
    Its number on the repository.
    """


# %% proposing the file


@dataclass(frozen=True)
class ProposalOutcome:
    """
    What proposing a file came to.
    """

    pull_request: OpenPullRequest | None = None
    """
    The pull request proposing the file, ``None`` when none could be opened.
    """

    opened_now: bool = False
    """
    Whether this proposal opened it, rather than finding it open.
    """

    failure: str = ""
    """
    Why no pull request could be opened, empty otherwise.
    """


@dataclass(frozen=True)
class FileProposal:
    """
    One file proposed for a repository's default branch, on a branch of its own and
    through a pull request a reviewer merges.
    """

    repository: Repository
    """
    The repository the file is proposed for.
    """

    base: str
    """
    The default branch the file is proposed for.
    """

    branch: str
    """
    The branch carrying the file.
    """

    file: str
    """
    The file's path from the repository's root.
    """

    text: str
    """
    The file's whole content.
    """

    title: str
    """
    The pull request's title, which is also the commit's message.
    """

    body: str
    """
    The pull request's description, in Markdown.
    """

    def propose(self, client: GitHubAttemptClient) -> ProposalOutcome:
        """
        Put the file on :attr:`branch` and open a pull request for it, unless one is
        open already.

        :param client: Reads and writes the repository.
        :return: The pull request, or why none could be opened.
        """
        listed = client.attempt_get(
            f"{self.repository.pull_requests_path}?state=open"
            f"&head={self.repository.owner}:{self.branch}"
        )
        failed = (
            (listed if listed.failure is not None else None)
            or self.create_branch(client)
            or self.write_file(client)
        )
        if failed is not None:
            return ProposalOutcome(failure=failed.failure.error_message())
        already_open = [OpenPullRequest.from_json(entry) for entry in listed.body]
        if already_open:
            return ProposalOutcome(already_open[0])
        opened = client.attempt_send(
            NewPullRequest(
                self.repository,
                title=self.title,
                head=self.branch,
                base=self.base,
                body=self.body,
                draft=False,
            )
        )
        if opened.failure is not None:
            return ProposalOutcome(failure=opened.failure.error_message())
        return ProposalOutcome(OpenPullRequest.from_json(opened.body), opened_now=True)

    def create_branch(self, client: GitHubAttemptClient) -> GitHubResponse | None:
        """
        Start :attr:`branch` at :attr:`base`'s head when it does not exist.

        :param client: Reads and writes the repository.
        :return: The answer that failed, ``None`` when the branch exists now.
        """
        existing = client.attempt_get(self.reference_path(self.branch))
        if existing.failure is None:
            return None
        if not existing.is_not_found:
            return existing
        base = client.attempt_get(self.reference_path(self.base))
        if base.failure is not None:
            return base
        created = client.attempt_send(
            NewBranch(
                self.repository,
                ref=f"refs/heads/{self.branch}",
                sha=BranchReference.from_json(base.body).target.sha,
            )
        )
        return created if created.failure is not None else None

    def write_file(self, client: GitHubAttemptClient) -> GitHubResponse | None:
        """
        Commit the file to :attr:`branch` unless it holds this content already.

        :param client: Reads and writes the repository.
        :return: The answer that failed, ``None`` when the branch holds the file now.
        """
        existing = client.attempt_get(self.contents_path(self.branch))
        if existing.failure is not None and not existing.is_not_found:
            return existing
        current = (
            None
            if existing.failure is not None
            else RepositoryFile.from_json(existing.body)
        )
        if current is not None and current.text == self.text:
            return None
        commit = {
            "repository": self.repository,
            "file": self.file,
            "message": self.title,
            "content": base64.b64encode(self.text.encode()).decode(),
            "branch": self.branch,
        }
        written = client.attempt_send(
            FileWrite(**commit)
            if current is None
            else FileUpdate(**commit, sha=current.sha)
        )
        return written if written.failure is not None else None

    def reference_path(self, branch: str) -> str:
        """
        :param branch: A branch of the repository.
        :return: The REST path of its git reference.
        """
        return f"{self.repository.api_path}/git/ref/heads/{branch}"

    def contents_path(self, branch: str) -> str:
        """
        :param branch: A branch of the repository.
        :return: The REST path of the file on that branch.
        """
        return f"{self.repository.api_path}/contents/{self.file}?ref={branch}"

    @property
    def new_file_page(self) -> str:
        """
        GitHub's page adding the file to :attr:`base`, with its path and content
        filled in.
        """
        query = urlencode({"filename": self.file, "value": self.text}, quote_via=quote)
        return f"{self.repository.url}/new/{self.base}?{query}"
