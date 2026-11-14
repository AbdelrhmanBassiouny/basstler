"""
The plan site's token steps when its token also marks files viewed.
"""

from __future__ import annotations

from basstler.github.token_form import (
    PermissionLevel,
    RepositoryPermission,
    SharedToken,
    TokenUse,
)
from basstler.plan_site.site_repository import SiteRepository
from basstler.plan_site.user_steps import UserStep, UserSteps
from basstler.repository import Repository

# %% the repositories

NOTES = Repository("an-owner", "notes")
"""
The repository whose notes the site publishes and whose pull requests are marked.
"""

SITE = SiteRepository(Repository("an-owner", "plans"))
"""
The site repository, of the same owner.
"""


def viewer_use(owner: str) -> TokenUse:
    """
    :param owner: The owner of the repository whose pull requests are marked.
    :return: The job marking files viewed there.
    """
    return TokenUse(
        "marks files viewed",
        (Repository(owner, "notes"),),
        {RepositoryPermission.PULL_REQUESTS: PermissionLevel.WRITE},
        "VIEWER_TOKEN",
        (NOTES,),
    )


def steps(owner: str) -> UserSteps:
    """
    :param owner: The owner of the repository whose pull requests are marked.
    :return: The steps of a site publishing :data:`NOTES`, sharing its token.
    """
    return UserSteps(NOTES, SITE, [NOTES.full_name], shared_uses=(viewer_use(owner),))


# %% the steps


def test_a_job_on_the_site_owner_s_repositories_is_stored_with_the_build_s_token():
    shared = steps(SITE.repository.owner)
    expected = SharedToken.joining(
        "basstler", SITE.token_use([NOTES]), (viewer_use(SITE.repository.owner),)
    )
    assert shared.pending(UserStep.STORE_TOKEN).line == expected.store_command


def test_the_shared_token_s_form_asks_for_both_jobs_permissions():
    form_step = steps(SITE.repository.owner).pending(UserStep.CREATE_TOKEN)
    assert [
        f"{permission}={PermissionLevel.WRITE}" in form_step.browser_steps[0]
        for permission in (
            RepositoryPermission.ACTIONS,
            RepositoryPermission.PULL_REQUESTS,
        )
    ] == [True, True]


def test_a_job_on_another_owner_s_repositories_leaves_the_build_s_token_alone():
    alone = UserSteps(NOTES, SITE, [NOTES.full_name])
    assert steps("someone-else").pending(UserStep.CREATE_TOKEN) == alone.pending(
        UserStep.CREATE_TOKEN
    )
