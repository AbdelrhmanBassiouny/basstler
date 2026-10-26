"""
Tests for :mod:`basstler.dashboard.publication`: the digest of a published dashboard and
the check that decides whether it needs republishing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from basstler.dashboard.publication import (
    DashboardArtifact,
    DashboardUrlCache,
    PublicationCheck,
    PublicationField,
)
from basstler.locations import DashboardArtifactFile

from ..constants.paths import DatasetLocation

CACHE_TEXT = (DatasetLocation.DIRECTORY / "dashboard-urls.yaml").read_text()
DIGESTED_CACHE_TEXT = (
    DatasetLocation.DIRECTORY / "dashboard-urls-with-content-digests.yaml"
).read_text()

ALPHA_URL = "https://claude.ai/code/artifact/11111111-1111-4111-8111-111111111111"
BETA_URL = "https://claude.ai/code/artifact/22222222-2222-4222-8222-222222222222"
ALPHA_DIGEST = "0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c4b5a69788796a5b4c3d2e1f0"


def artifact(**contents: str) -> DashboardArtifact:
    """
    :param contents: Each file's content, by the member name of its
        :class:`DashboardArtifactFile`; a file not named is empty.
    :return: The artifact made of those files.
    """
    return DashboardArtifact(
        files={file: contents.get(file._name_, "") for file in DashboardArtifactFile}
    )


# %% the content digest


def test_identical_files_have_the_same_digest():
    assert artifact(CONTENT="a").content_digest == artifact(CONTENT="a").content_digest


@pytest.mark.parametrize("file", list(DashboardArtifactFile))
def test_a_change_to_any_file_changes_the_digest(file: DashboardArtifactFile):
    assert (
        artifact(**{file._name_: "changed"}).content_digest != artifact().content_digest
    )


def test_content_moved_between_files_changes_the_digest():
    assert (
        artifact(STYLE="ab", SCRIPT="").content_digest
        != artifact(STYLE="a", SCRIPT="b").content_digest
    )


def test_writing_puts_every_file_at_its_published_path(tmp_path: Path):
    written = artifact(PAGE="page", STYLE="style", SCRIPT="script", CONTENT="content")
    written.write_to(tmp_path)
    assert {
        file: (tmp_path / file).read_text() for file in DashboardArtifactFile
    } == written.files


# %% reading the url cache


def test_a_cache_without_digests_reads_each_url():
    cache = DashboardUrlCache.from_yaml(CACHE_TEXT)
    assert cache.urls["alpha-plan"] == ALPHA_URL


def test_a_cache_reads_the_recorded_digest():
    cache = DashboardUrlCache.from_yaml(DIGESTED_CACHE_TEXT)
    assert cache.content_digests == {"alpha-plan": ALPHA_DIGEST}


def test_the_digest_section_is_not_read_as_a_url():
    cache = DashboardUrlCache.from_yaml(DIGESTED_CACHE_TEXT)
    assert DashboardUrlCache.content_digest_section not in cache.urls


def test_an_empty_cache_holds_nothing():
    assert DashboardUrlCache.from_yaml("") == DashboardUrlCache()


# %% the publication check


def test_a_page_whose_digest_matches_the_recorded_one_is_unchanged():
    cache = DashboardUrlCache.from_yaml(DIGESTED_CACHE_TEXT)
    assert cache.check("alpha-plan", ALPHA_DIGEST) == PublicationCheck(
        url=ALPHA_URL, unchanged=True
    )


def test_a_page_whose_digest_differs_is_changed():
    cache = DashboardUrlCache.from_yaml(DIGESTED_CACHE_TEXT)
    assert cache.check("alpha-plan", "another digest") == PublicationCheck(
        url=ALPHA_URL, unchanged=False
    )


def test_a_page_with_no_recorded_digest_is_changed():
    cache = DashboardUrlCache.from_yaml(DIGESTED_CACHE_TEXT)
    assert cache.check("beta-plan", ALPHA_DIGEST) == PublicationCheck(
        url=BETA_URL, unchanged=False
    )


def test_a_page_never_published_is_changed_and_has_no_url():
    cache = DashboardUrlCache.from_yaml(
        f"{DashboardUrlCache.content_digest_section}:\n  gamma-plan: {ALPHA_DIGEST}\n"
    )
    assert cache.check("gamma-plan", ALPHA_DIGEST) == PublicationCheck(
        url=None, unchanged=False
    )


def test_the_check_renders_its_url_and_whether_it_is_unchanged():
    check = PublicationCheck(url=ALPHA_URL, unchanged=True)
    assert check.to_json() == {
        PublicationField.URL: ALPHA_URL,
        PublicationField.UNCHANGED: True,
    }
