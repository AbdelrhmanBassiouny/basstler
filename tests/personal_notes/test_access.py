"""
Tests for :mod:`basstler.personal_notes.access`: whether a cloud session reaches a
personal-notes repository other than its checkout's.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from http import HTTPStatus

from basstler.github.client import GitHubAttemptClient, GitHubResponse, GitHubWrite
from basstler.github.client import HttpMethod
from basstler.github.credential import CredentialProvider
from basstler.github.exceptions import GitHubRequestFailed
from basstler.personal_notes.access import NotesRepositoryAccess
from basstler.repository import Repository

from ..scratch_repository import ScratchRepository

CHECKOUT = Repository.parse("an-owner/a-project")
"""
The repository the session's checkout is a clone of.
"""

SEPARATE_NOTES = Repository.parse("an-owner/a-project-notes")
"""
A notes repository other than :data:`CHECKOUT`.
"""

RETRY = "run-it-again"
"""
The command the session is told to run once the notes repository is attached.
"""

# %% a GitHub answering from memory


@dataclass
class RepositoryReadingClient(GitHubAttemptClient):
    """
    Answers every repository read, or refuses it with :attr:`refusal`, recording what
    was read.
    """

    refusal: HTTPStatus | None = None
    """
    The status every read is refused with, ``None`` to answer it.
    """

    reads: list[str] = field(default_factory=list)
    """
    Every path read, oldest first.
    """

    def attempt_get(self, path: str) -> GitHubResponse:
        self.reads.append(path)
        if self.refusal is None:
            return GitHubResponse({})
        return GitHubResponse(
            None,
            failure=GitHubRequestFailed(
                status=self.refusal,
                detail="",
                method=HttpMethod.GET,
                path=path,
                credential_origin=CredentialProvider.CALLER,
            ),
        )

    def attempt_send(self, write: GitHubWrite) -> GitHubResponse:
        raise AssertionError(f"the access check sent a write: {write}")


# %% checking the access


def test_notes_in_the_checkout_s_own_repository_need_no_read():
    client = RepositoryReadingClient(refusal=HTTPStatus.FORBIDDEN)

    access = NotesRepositoryAccess(CHECKOUT, CHECKOUT)

    assert access.missing_access(client, RETRY) is None
    assert client.reads == []


def test_a_readable_separate_notes_repository_is_reported_as_reachable():
    client = RepositoryReadingClient()

    access = NotesRepositoryAccess(SEPARATE_NOTES, CHECKOUT)

    assert access.missing_access(client, RETRY) is None
    assert client.reads == [SEPARATE_NOTES.api_path]


def test_a_refused_separate_notes_repository_is_reported_with_how_to_attach_it():
    client = RepositoryReadingClient(refusal=HTTPStatus.FORBIDDEN)
    access = NotesRepositoryAccess(SEPARATE_NOTES, CHECKOUT)

    missing = access.missing_access(client, RETRY)

    assert missing.endswith(access.attachment(RETRY).instruction())


def test_the_refusal_is_named_in_the_report():
    client = RepositoryReadingClient(refusal=HTTPStatus.FORBIDDEN)
    access = NotesRepositoryAccess(SEPARATE_NOTES, CHECKOUT)

    missing = access.missing_access(client, RETRY)

    refusal = client.attempt_get(SEPARATE_NOTES.api_path).failure
    assert refusal.error_message() in missing


def test_the_attachment_names_the_notes_repository_and_the_retry():
    attachment = NotesRepositoryAccess(SEPARATE_NOTES, CHECKOUT).attachment(RETRY)

    assert attachment.repository == SEPARATE_NOTES
    assert attachment.retry_command == RETRY


# %% reading both repositories from the clone


def test_the_repositories_are_read_from_the_configured_urls(
    scratch_repository: ScratchRepository,
):
    """
    Both are read from the URLs the clone configures, not from git's rewrite of them to
    where it actually fetches.
    """
    scratch_repository.serve_origin_as(CHECKOUT)
    scratch_repository.serve_notes_remote_as(SEPARATE_NOTES)

    access = NotesRepositoryAccess.of_clone(scratch_repository.project_root, {})

    assert access == NotesRepositoryAccess(SEPARATE_NOTES, CHECKOUT)


def test_a_notes_remote_naming_no_repository_has_no_access_to_check(
    scratch_repository: ScratchRepository,
):
    """
    A notes remote given as a local path, as in a clone set up by hand, names no GitHub
    repository a session could attach.
    """
    scratch_repository.serve_origin_as(CHECKOUT)
    scratch_repository.resolve_notes_remote_to()

    assert NotesRepositoryAccess.of_clone(scratch_repository.project_root, {}) is None
