"""
Tests for :mod:`basstler.plan_site.build_start`: starting the plan site's build with the
session's own credential.
"""

from __future__ import annotations

from http import HTTPStatus

import pytest

import basstler.plan_site.build_start

from basstler.github.repository_details import RepositoryDetails
from basstler.github.workflow_run import WorkflowDispatch
from basstler.locations import WorkflowLocation
from basstler.plan_site.build_start import (
    BUILD_START_COMMAND,
    BuildStart,
    CodeFence,
    GitHubCommand,
    SessionTool,
    SiteAccess,
)
from basstler.plan_site.site_repository import SiteRepository
from basstler.repository import Repository

from .site_answering_client import SITE_DETAILS, SiteAnsweringClient

SITE = SiteRepository(Repository.parse("an-owner/plans"))
"""
The site repository whose build is started.
"""

# %% starting the build


def test_the_build_is_dispatched_on_the_site_s_default_branch():
    """
    The dispatch runs the build on the branch GitHub reports as the default.
    """
    client = SiteAnsweringClient()

    attempt = BuildStart.attempt(SITE, client)

    assert attempt.started
    assert client.writes == [
        WorkflowDispatch(
            SITE.repository,
            WorkflowLocation.PLAN_SITE,
            RepositoryDetails.from_json(SITE_DETAILS).default_branch,
        )
    ]


def test_a_refused_site_repository_dispatches_nothing():
    """
    When reading the site repository is refused, no dispatch is sent.
    """
    client = SiteAnsweringClient(refusal=HTTPStatus.FORBIDDEN)

    attempt = BuildStart.attempt(SITE, client)

    assert not attempt.started
    assert client.writes == []


def test_a_cloud_session_is_told_to_attach_the_site_repository_and_ask_if_refused():
    """
    A cloud session is told to attach the site repository, and to ask the user if that
    is refused.
    """
    client = SiteAnsweringClient(refusal=HTTPStatus.FORBIDDEN)

    description = BuildStart.attempt(SITE, client).describe(in_cloud_session=True)

    assert SessionTool.ATTACH_REPOSITORY in description
    assert SessionTool.ASK_USER in description
    assert SITE.repository.name in description


def test_a_local_session_is_not_told_to_attach_a_repository():
    """
    A local session is told to log ``gh`` in, not to attach a repository.
    """
    client = SiteAnsweringClient(refusal=HTTPStatus.FORBIDDEN)

    description = BuildStart.attempt(SITE, client).describe(in_cloud_session=False)

    assert SessionTool.ATTACH_REPOSITORY not in description
    assert GitHubCommand.LOG_IN in description


def test_a_refused_site_repository_is_reported():
    """
    The refusal that stopped the build is in what is printed.
    """
    client = SiteAnsweringClient(refusal=HTTPStatus.FORBIDDEN)

    attempt = BuildStart.attempt(SITE, client)

    assert attempt.response.failure.error_message() in attempt.describe(
        in_cloud_session=False
    )


def test_a_local_session_is_shown_the_command_in_a_bash_block_of_its_own():
    """
    The command to run is on its own line inside a fenced bash block.
    """
    client = SiteAnsweringClient(refusal=HTTPStatus.FORBIDDEN)

    description = BuildStart.attempt(SITE, client).describe(in_cloud_session=False)

    assert description.endswith(
        "\n".join(["", CodeFence.BASH, GitHubCommand.LOG_IN, CodeFence.CLOSE])
    )


@pytest.mark.parametrize("in_cloud_session", [True, False])
def test_a_build_that_did_not_start_names_the_command_that_starts_it_again(
    in_cloud_session: bool,
):
    """
    Saving the plan again changes nothing and so starts no build: the retry has to be
    this command itself.
    """
    client = SiteAnsweringClient(refusal=HTTPStatus.FORBIDDEN)

    description = BuildStart.attempt(SITE, client).describe(in_cloud_session)

    assert BUILD_START_COMMAND in description


def test_the_retry_command_runs_this_module():
    assert BUILD_START_COMMAND.endswith(f"-m {basstler.plan_site.build_start.__name__}")


# %% checking the access before any save


def test_a_session_that_can_read_the_site_repository_is_told_nothing():
    assert SiteAccess(SITE).missing_access(SiteAnsweringClient(), True) is None


def test_a_cloud_session_that_cannot_read_the_site_repository_is_told_to_attach_it():
    client = SiteAnsweringClient(refusal=HTTPStatus.FORBIDDEN)

    missing = SiteAccess(SITE).missing_access(client, in_cloud_session=True)

    assert missing.endswith(SiteAccess(SITE).remedy(in_cloud_session=True))
