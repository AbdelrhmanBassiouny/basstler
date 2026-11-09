"""
Tests for :mod:`basstler.plan_site.token_storage`: proving the plan site's token by
starting the site's build with it, then storing it in every repository.
"""

from __future__ import annotations

import io
from collections.abc import Mapping
from dataclasses import dataclass, field
from http import HTTPStatus

import pytest

from basstler.plan_site.build_start import BuildStart
from basstler.plan_site.exceptions import PlanSiteTokenNotEnteredError
from basstler.plan_site.site_repository import SiteRepository
from basstler.plan_site.token_storage import (
    GitHubCommandLineSecretStore,
    SecretStore,
    StorageReport,
    StorageResult,
    TokenStorage,
)
from basstler.plan_site.workflows import PlanSiteSecret
from basstler.repository import Repository

from .site_answering_client import SiteAnsweringClient

SITE = SiteRepository(Repository("an-owner", "plans"))
"""
The site repository whose build the token starts.
"""

FIRST = Repository("an-owner", "a-repository")
"""
The first repository the token is stored in.
"""

SECOND = Repository("an-owner", "another-repository")
"""
The second repository the token is stored in.
"""

TOKEN = "a-token"
"""
The token stored.
"""

# %% mimics


@dataclass
class RecordingSecretStore(SecretStore):
    """
    Records every secret it is given, refusing the repositories in :attr:`refusals`.
    """

    refusals: Mapping[Repository, str] = field(default_factory=dict)
    """
    Why each refused repository refuses, by repository.
    """

    stored: list[tuple[Repository, PlanSiteSecret, str]] = field(default_factory=list)
    """
    Every secret stored, oldest first.
    """

    def store(self, repository: Repository, secret: PlanSiteSecret, value: str) -> str:
        refusal = self.refusals.get(repository, "")
        if not refusal:
            self.stored.append((repository, secret, value))
        return refusal


@dataclass
class TerminalInput(io.StringIO):
    """
    Standard input that reports whether a terminal is attached.
    """

    attached: bool = True
    """
    Whether a terminal is attached.
    """

    def __post_init__(self) -> None:
        """
        Start with nothing to read.
        """
        super().__init__()

    def isatty(self) -> bool:
        """
        Unlike :meth:`io.StringIO.isatty`, report :attr:`attached`.
        """
        return self.attached


# %% proving


def test_the_token_is_proven_by_starting_the_site_s_build_with_it():
    """
    The build start the token proves itself with is the one a dispatch workflow makes.
    """
    client = SiteAnsweringClient()

    report = TokenStorage(TOKEN, SITE, RecordingSecretStore()).store([FIRST], client)

    reference_client = SiteAnsweringClient()
    expected = BuildStart.attempt(SITE, reference_client)
    assert (report.build_start, client.writes) == (expected, reference_client.writes)
    assert report.build_start.started


def test_a_token_that_cannot_start_the_build_is_stored_nowhere():
    """
    A token GitHub refuses to start the build with is stored in no repository.
    """
    secrets = RecordingSecretStore()

    report = TokenStorage(TOKEN, SITE, secrets).store(
        [FIRST, SECOND], SiteAnsweringClient(refusal=HTTPStatus.FORBIDDEN)
    )

    assert (secrets.stored, report.results, report.succeeded) == ([], [], False)


def test_a_token_that_cannot_start_the_build_links_the_token_form():
    """
    A refused token's report links the form that creates it again.
    """
    report = TokenStorage(TOKEN, SITE, RecordingSecretStore()).store(
        [FIRST], SiteAnsweringClient(refusal=HTTPStatus.FORBIDDEN)
    )

    (line,) = report.describe()
    assert SITE.token_form_url() in line


# %% storing


def test_a_proven_token_is_stored_in_every_repository_given():
    """
    A proven token is stored, as its secret, in every repository in order.
    """
    secrets = RecordingSecretStore()

    TokenStorage(TOKEN, SITE, secrets).store([FIRST, SECOND], SiteAnsweringClient())

    assert secrets.stored == [
        (FIRST, PlanSiteSecret.TOKEN, TOKEN),
        (SECOND, PlanSiteSecret.TOKEN, TOKEN),
    ]


def test_a_refused_store_is_reported_and_fails_the_report():
    """
    A repository refusing the secret is reported, and the others are still stored.
    """
    refusal = "HTTP 403"

    report = TokenStorage(TOKEN, SITE, RecordingSecretStore({FIRST: refusal})).store(
        [FIRST, SECOND], SiteAnsweringClient()
    )

    assert (report.results, report.succeeded) == (
        [StorageResult(FIRST, refusal), StorageResult(SECOND)],
        False,
    )


def test_a_proven_token_stored_everywhere_succeeds():
    """
    A proven token every repository stores makes the report succeed.
    """
    report = TokenStorage(TOKEN, SITE, RecordingSecretStore()).store(
        [FIRST], SiteAnsweringClient()
    )

    assert report == StorageReport(report.build_start, [StorageResult(FIRST)])
    assert report.succeeded


def test_the_token_is_kept_out_of_the_storage_s_representation():
    """
    The token never shows in a traceback or log line that prints the storage.
    """
    assert TOKEN not in repr(TokenStorage(TOKEN, SITE, RecordingSecretStore()))


def test_a_missing_command_line_client_is_reported_as_the_refusal():
    """
    Without ``gh`` installed, the store refuses and names the missing executable.
    """
    executable = "no-such-github-command-line"

    refusal = GitHubCommandLineSecretStore(executable).store(
        FIRST, PlanSiteSecret.TOKEN, TOKEN
    )

    assert refusal == f"{executable} is not installed"


# %% reading the token


def test_the_token_is_not_read_without_a_terminal(monkeypatch):
    """
    Without a terminal the token would have to come through a pipe or a chat, so it is
    refused instead.
    """
    monkeypatch.setattr("sys.stdin", TerminalInput(attached=False))

    with pytest.raises(PlanSiteTokenNotEnteredError) as raised:
        PlanSiteSecret.TOKEN.read_value()

    assert raised.value == PlanSiteTokenNotEnteredError(
        PlanSiteSecret.TOKEN, terminal=False
    )


def test_an_empty_token_is_refused(monkeypatch):
    """
    An empty answer at the command's hidden terminal prompt is refused as no token
    entered.
    """
    monkeypatch.setattr("sys.stdin", TerminalInput())
    monkeypatch.setattr("getpass.getpass", lambda prompt: "\n")

    with pytest.raises(PlanSiteTokenNotEnteredError) as raised:
        PlanSiteSecret.TOKEN.read_value()

    assert raised.value == PlanSiteTokenNotEnteredError(
        PlanSiteSecret.TOKEN, terminal=True
    )


def test_a_pasted_token_is_read_without_surrounding_whitespace(monkeypatch):
    """
    A token pasted at the command's hidden terminal prompt is read without the spaces or
    newline a paste can carry around it.
    """
    monkeypatch.setattr("sys.stdin", TerminalInput())
    monkeypatch.setattr("getpass.getpass", lambda prompt: f" {TOKEN}\n")

    assert PlanSiteSecret.TOKEN.read_value() == TOKEN
