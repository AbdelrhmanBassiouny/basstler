"""
Tests for what each fix for a failed read of the site repository tells the session.
"""

from __future__ import annotations

from datetime import timedelta
from http import HTTPStatus

import pytest

from basstler.github.client import HttpMethod
from basstler.github.credential import CredentialProvider
from basstler.github.exceptions import GitHubCredentialRejected
from basstler.github.repository import GitHubAddress, Repository
from basstler.plan_site.build_start import SiteAccess
from basstler.plan_site.exceptions import SiteRepositoryUnreachableError
from basstler.plan_site.site_read import (
    CredentialAccessFix,
    GitHubOutageFix,
    RefusalCorrectionFix,
    RepositoryAttachmentFix,
)
from basstler.plan_site.site_repository import SiteRepository

# %% the site repository and a refusal of it

SITE = SiteRepository(Repository.parse("an-owner/plans"))
"""
The site repository that could not be read.
"""

RETRY_COMMAND = "python -m publish.again"
"""
The command each fix ends with.
"""

ACCESS = SiteAccess(SITE, RETRY_COMMAND)
"""
How the session reaches :data:`SITE`.
"""

REJECTED = GitHubCredentialRejected(
    status=HTTPStatus.UNAUTHORIZED,
    detail="",
    method=HttpMethod.GET,
    path=SITE.repository.api_path,
    credential_origin=CredentialProvider.CALLER,
)
"""
GitHub rejecting the credential the read used.
"""

# %% what each fix says


def test_an_unattached_repository_is_fixed_by_attaching_it():
    """
    The fix ends with how a cloud session attaches the repository.
    """
    fix = RepositoryAttachmentFix(ACCESS)

    assert fix.describe().endswith(ACCESS.remedy(in_cloud_session=True))


@pytest.mark.parametrize("in_cloud_session", [True, False])
def test_a_refused_credential_is_fixed_by_gaining_access(in_cloud_session):
    """
    The fix ends with how this kind of session gets access.
    """
    fix = CredentialAccessFix(ACCESS, in_cloud_session)

    assert fix.describe().endswith(ACCESS.remedy(in_cloud_session))


def test_an_outage_is_reported_with_github_s_status_page():
    """
    Whether GitHub has an incident is on its status page, which the fix names.
    """
    fix = GitHubOutageFix((timedelta(seconds=2),), RETRY_COMMAND)

    assert GitHubAddress.STATUS in fix.describe()


def test_an_outage_is_fixed_by_running_the_command_again():
    """
    The fix ends by naming the command to run once GitHub recovers.
    """
    fix = GitHubOutageFix((), RETRY_COMMAND)

    assert RETRY_COMMAND in fix.describe()


def test_a_refusal_naming_its_own_fix_is_fixed_as_it_says():
    """
    The fix starts with the refusal's own correction.
    """
    fix = RefusalCorrectionFix(REJECTED, RETRY_COMMAND)

    assert fix.describe().startswith(REJECTED.suggest_correction())


def test_a_refusal_naming_its_own_fix_is_followed_by_running_the_command_again():
    """
    The fix ends by naming the command to run once the refusal is fixed.
    """
    fix = RefusalCorrectionFix(REJECTED, RETRY_COMMAND)

    assert RETRY_COMMAND in fix.describe()


# %% the error


def test_the_error_s_correction_ends_with_its_fix():
    """
    The error's correction is its fix, after warning not to create the repository.
    """
    fix = GitHubOutageFix((), RETRY_COMMAND)
    error = SiteRepositoryUnreachableError(SITE.repository, REJECTED, fix)

    assert error.suggest_correction().endswith(fix.describe())
