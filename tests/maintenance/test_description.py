"""
Tests for what a pass reads out of a fork pull request's description and writes into it.
"""

from __future__ import annotations

from basstler.maintenance.constants import MaintenanceText
from basstler.maintenance.description import PullRequestDescription

from .fork import A_SESSION_LINK, PromotionSampleText

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
