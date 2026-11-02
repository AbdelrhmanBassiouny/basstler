"""
Tests for :mod:`basstler.plan_site.plan_page`: how an item card's chips are coloured.
"""

from __future__ import annotations

import pytest

from basstler.plan.model import ItemStatus
from basstler.plan_site.plan_page import ChipTone
from basstler.pull_request_state import LiveState
from basstler.upstream_reviews.vocabulary import RollupState

# %% chip tones


@pytest.mark.parametrize("check_state", [RollupState.FAILURE, RollupState.ERROR])
def test_a_failed_check_is_bad(check_state: RollupState):
    assert ChipTone.of_check_state(check_state) is ChipTone.BAD


def test_passing_checks_are_good():
    assert ChipTone.of_check_state(RollupState.SUCCESS) is ChipTone.GOOD


@pytest.mark.parametrize("check_state", [RollupState.PENDING, RollupState.EXPECTED])
def test_unfinished_checks_are_a_warning(check_state: RollupState):
    assert ChipTone.of_check_state(check_state) is ChipTone.WARNING


def test_checks_nothing_reported_are_idle():
    assert ChipTone.of_check_state(RollupState.NOT_REPORTED) is ChipTone.IDLE


def test_every_status_and_live_state_has_a_tone():
    assert {ChipTone.of_status(status) for status in ItemStatus} <= set(ChipTone)
    assert {ChipTone.of_live_state(state) for state in LiveState} <= set(ChipTone)


def test_a_merged_pull_request_is_good():
    assert ChipTone.of_live_state(LiveState.MERGED) is ChipTone.GOOD


def test_a_blocked_item_is_bad():
    assert ChipTone.of_status(ItemStatus.BLOCKED) is ChipTone.BAD
