"""
Tests for the models that validate GitHub's objects as they read them.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from basstler.upstream_reviews.review_models import Author, PageInfo, ReviewThread
from basstler.upstream_reviews.rest_models import RestReview
from basstler.upstream_reviews.vocabulary import ReviewState

from .replay import RecordedResponse

# %% reading an object


def test_a_deleted_account_reads_as_the_unknown_author():
    """
    GitHub reports a deleted account as null, which reads as the unknown author.
    """
    assert Author.from_json(None) == Author(Author.unknown_login)


def test_an_object_missing_a_field_is_rejected():
    """
    An object without the fields a model reads is refused as it is read.
    """
    with pytest.raises(ValidationError):
        PageInfo.from_json({})


def test_a_connection_reads_the_same_entries_as_the_listed_ones():
    """
    Entries read out of a connection's nodes equal the same entries given as a list.
    """
    thread = RecordedResponse.PULL_REQUEST_PAGE_ONE.recorded().pull_request.review_threads.threads[
        0
    ]

    listed = ReviewThread(
        thread.identifier,
        thread.is_resolved,
        thread.is_outdated,
        thread.path,
        thread.line,
        list(thread.comments),
    )

    assert listed == thread


# %% values named as GitHub spells them


@pytest.mark.parametrize("member", list(ReviewState))
def test_a_value_is_read_by_its_github_name_in_any_case(member: ReviewState):
    """
    GitHub's spelling of a value names its member whatever its letter case.
    """
    assert ReviewState.from_github_name(member.name.lower()) is member


def test_a_member_reads_as_itself():
    """
    A value already read stays the member it is.
    """
    assert ReviewState.from_github_name(ReviewState.APPROVED) is ReviewState.APPROVED


# %% the keys a model reads


def test_the_keys_a_model_reads_include_its_nested_models_keys():
    """
    A model's keys include every key the models nested in it read.
    """
    assert Author.read_keys <= RestReview.read_keys
