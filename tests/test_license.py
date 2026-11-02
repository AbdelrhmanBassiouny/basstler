"""
The licence file is the official licence text, unaltered.
"""

from __future__ import annotations

import hashlib
from enum import StrEnum

from basstler.locations import PackageLocation


# %% official licence text


class OfficialLicenseDigest(StrEnum):
    """
    SHA-256 digests of official licence texts, as published by their stewards.
    """

    APACHE_2_0 = "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"
    """
    The digest of https://www.apache.org/licenses/LICENSE-2.0.txt.
    """


def test_license_is_the_official_apache_2_0_text() -> None:
    """
    The licence file is byte for byte the Apache License 2.0 that apache.org publishes.
    """
    license_digest = hashlib.sha256(
        PackageLocation.LICENSE.value.read_bytes()
    ).hexdigest()

    assert license_digest == OfficialLicenseDigest.APACHE_2_0
