"""
Filling GitHub's new fine-grained token form in from its address.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from basstler.github.token_form import (
    FineGrainedTokenForm,
    PermissionLevel,
    RepositoryPermission,
    TokenFormParameter,
)

FORM = FineGrainedTokenForm(
    "a token",
    "what it is for",
    "an-owner",
    {RepositoryPermission.PULL_REQUESTS: PermissionLevel.WRITE},
)
"""
A form with every field and one permission filled in.
"""


def test_every_field_and_permission_is_filled_in():
    fields = parse_qs(urlsplit(FORM.url).query)
    assert fields == {
        TokenFormParameter.NAME: [FORM.name],
        TokenFormParameter.DESCRIPTION: [FORM.description],
        TokenFormParameter.RESOURCE_OWNER: [FORM.resource_owner],
        RepositoryPermission.PULL_REQUESTS: [PermissionLevel.WRITE],
    }
