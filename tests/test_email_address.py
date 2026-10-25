"""
Tests for email_address.py: reading an email address out of the text a user types.
"""

import pytest

from basstler.email_address import EmailAddress
from basstler.exceptions import MalformedEmailAddressError

ADDRESS = EmailAddress("ada", "example.com")
"""
The address every well-formed text in these tests names.
"""

# %% parsing


def test_email_address_splits_text_into_local_part_and_domain():
    assert EmailAddress.parse(f"{ADDRESS.local_part}@{ADDRESS.domain}") == ADDRESS


def test_email_address_round_trips_through_its_text():
    assert EmailAddress.parse(str(ADDRESS)) == ADDRESS


def test_email_address_keeps_an_at_sign_quoted_in_the_local_part():
    quoted = EmailAddress('"ada@home"', ADDRESS.domain)
    assert EmailAddress.parse(str(quoted)) == quoted


@pytest.mark.parametrize("malformed", ["no-separator", "@no-local-part", "no-domain@"])
def test_email_address_rejects_text_that_is_not_local_part_at_domain(malformed: str):
    with pytest.raises(MalformedEmailAddressError):
        EmailAddress.parse(malformed)
