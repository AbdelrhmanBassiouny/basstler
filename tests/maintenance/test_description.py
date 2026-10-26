"""
Tests for what a pass reads out of a fork pull request's description and writes into it.
"""

from __future__ import annotations

from basstler.maintenance.constants import MaintenanceText
from basstler.maintenance.description import (
    PullRequestDescription,
    UpstreamPullRequestLink,
)

from .fork import (
    A_SESSION_LINK,
    PromotionSampleText,
    StackPullRequestNumber,
    make_configuration,
)

# %% the session link


def test_a_session_link_is_read_out_of_the_description():
    description = PullRequestDescription(f"Some prose.\n\nSession: {A_SESSION_LINK}\n")

    assert description.session_link == A_SESSION_LINK


def test_a_description_naming_no_session_yields_none():
    assert PullRequestDescription("Some prose with no link.").session_link is None


# %% the promotion section


def test_the_promotion_link_read_back_is_the_one_written():
    written = PullRequestDescription(PromotionSampleText.PROSE).with_promotion_link(
        PromotionSampleText.FIRST_LINK
    )

    assert (
        PullRequestDescription(written).promotion_link == PromotionSampleText.FIRST_LINK
    )


def test_a_description_with_no_promotion_section_yields_no_link():
    assert PullRequestDescription(PromotionSampleText.PROSE).promotion_link is None


def test_a_second_promotion_replaces_the_link_rather_than_appending_another():
    """
    Two promotion headings would leave a reader guessing which link is current.
    """
    first = PullRequestDescription(
        f"{PromotionSampleText.PROSE}\n"
    ).with_promotion_link(PromotionSampleText.FIRST_LINK)

    second = PullRequestDescription(first).with_promotion_link(
        PromotionSampleText.SECOND_LINK
    )

    assert second.count(MaintenanceText.PROMOTION_HEADING) == 1
    assert PromotionSampleText.SECOND_LINK in second
    assert PromotionSampleText.FIRST_LINK not in second
    assert second.startswith(PromotionSampleText.PROSE)


# %% the upstream pull request section


def an_upstream_link() -> UpstreamPullRequestLink:
    """
    :return: A link to the upstream pull request opened from the parent.
    """
    return UpstreamPullRequestLink(
        make_configuration().upstream_repository, StackPullRequestNumber.UPSTREAM
    )


def test_the_upstream_pull_request_read_back_is_the_one_written():
    link = an_upstream_link()
    written = PullRequestDescription(PromotionSampleText.PROSE).with_upstream_link(link)

    assert PullRequestDescription(written).upstream_link == link.url


def test_the_upstream_pull_request_is_written_as_a_hyperlink():
    link = an_upstream_link()

    written = PullRequestDescription(PromotionSampleText.PROSE).with_upstream_link(link)

    assert link.markdown in written


def test_a_description_with_no_upstream_section_yields_no_link():
    assert PullRequestDescription(PromotionSampleText.PROSE).upstream_link is None


def test_removing_the_upstream_link_drops_its_section():
    linked = PullRequestDescription(PromotionSampleText.PROSE).with_upstream_link(
        an_upstream_link()
    )

    unlinked = PullRequestDescription(linked).with_upstream_link(None)

    assert unlinked.rstrip() == PromotionSampleText.PROSE


def test_the_upstream_section_and_the_promotion_section_keep_each_other():
    promoted = PullRequestDescription(PromotionSampleText.PROSE).with_promotion_link(
        PromotionSampleText.FIRST_LINK
    )
    linked = PullRequestDescription(promoted).with_upstream_link(an_upstream_link())

    promoted_again = PullRequestDescription(
        PullRequestDescription(linked).with_promotion_link(
            PromotionSampleText.SECOND_LINK
        )
    )

    assert promoted_again.promotion_link == PromotionSampleText.SECOND_LINK
    assert promoted_again.upstream_link == an_upstream_link().url
