"""
Tests for :mod:`basstler.plan_site.plan_page`: dependencies on items of another plan,
and their chips.
"""

from __future__ import annotations

from basstler.github.pull_request_state import (
    LiveState,
    PullRequestRecord,
    PullRequestState,
)
from basstler.plan.model import ItemStatus

from ..fixture_plans import (
    FixturePlanId,
    ForeignItemId,
    foreign_reference,
)
from .plan_page_builders import (
    FOREIGN_PULL_REQUESTS,
    item,
    make_renderer,
    make_renderer_over_plan_directory,
    renderer_with_cards,
    site_plan_url,
)

# %% resolving a dependency in another plan


def test_item_is_ready_to_start_once_a_foreign_dependency_is_out_of_draft():
    renderer = make_renderer_over_plan_directory(
        [
            item(
                "a",
                ItemStatus.NOT_STARTED,
                depends_on=[foreign_reference(ForeignItemId.READY)],
            )
        ],
        FOREIGN_PULL_REQUESTS,
    )
    summary = renderer.render().overview
    assert summary.ready_to_start == ["a"]


def test_item_is_not_ready_to_start_while_a_foreign_dependency_is_a_draft():
    """
    An item waits while a dependency in another plan is still a draft.
    """
    renderer = make_renderer_over_plan_directory(
        [
            item(
                "a",
                ItemStatus.NOT_STARTED,
                depends_on=[foreign_reference(ForeignItemId.DRAFT)],
            )
        ],
        FOREIGN_PULL_REQUESTS,
    )
    page = renderer.render()
    summary = page.overview
    assert summary.ready_to_start == []
    assert page.cards_by_identifier["a"].action is None


def test_item_is_ready_to_start_once_a_foreign_dependency_has_landed():
    renderer = make_renderer_over_plan_directory(
        [
            item(
                "a",
                ItemStatus.NOT_STARTED,
                depends_on=[foreign_reference(ForeignItemId.DONE)],
            )
        ]
    )
    summary = renderer.render().overview
    assert summary.ready_to_start == ["a"]


def test_foreign_dependency_live_state_comes_from_its_own_plans_repository():
    # The number 91 exists only under other-plan's repository; read against
    # the rendered plan's own, it would classify as not_found.
    renderer = make_renderer_over_plan_directory(
        [
            item(
                "a",
                ItemStatus.NOT_STARTED,
                depends_on=[foreign_reference(ForeignItemId.READY)],
            )
        ],
        FOREIGN_PULL_REQUESTS,
    )
    renderer.render()
    resolved = renderer.dependencies.resolve(foreign_reference(ForeignItemId.READY))
    assert resolved.live_state is LiveState.OPEN_READY


def test_item_is_not_ready_to_start_when_a_dependency_cannot_be_resolved():
    """
    An item whose dependency resolves to nothing is not ready to start.
    """
    # The latent fault this fixes: an unresolvable entry used to be skipped,
    # so a mistyped dependency counted as ready.
    renderer = make_renderer_over_plan_directory(
        [item("a", ItemStatus.NOT_STARTED, depends_on=["ghost"])]
    )
    page = renderer.render()
    summary = page.overview
    assert summary.ready_to_start == []
    assert page.cards_by_identifier["a"].action is None


def test_item_is_ready_to_review_once_a_foreign_dependency_has_a_pull_request():
    renderer = make_renderer_over_plan_directory(
        [
            item(
                "a",
                ItemStatus.IN_PROGRESS,
                pull_request_number=1,
                depends_on=[foreign_reference(ForeignItemId.DRAFT)],
            )
        ],
        {
            **FOREIGN_PULL_REQUESTS,
            "owner/repo": {
                "1": PullRequestRecord(state=PullRequestState.OPEN, draft=True)
            },
        },
    )
    summary = renderer.render().overview
    assert summary.ready_to_review == ["a"]


def test_item_is_not_ready_to_review_while_a_foreign_dependency_has_no_pull_request():
    renderer = make_renderer_over_plan_directory(
        [
            item(
                "a",
                ItemStatus.IN_PROGRESS,
                pull_request_number=1,
                depends_on=[foreign_reference(ForeignItemId.NOT_STARTED)],
            )
        ],
        {
            "owner/repo": {
                "1": PullRequestRecord(state=PullRequestState.OPEN, draft=True)
            }
        },
    )
    summary = renderer.render().overview
    assert summary.ready_to_review == []


# %% the chip of a dependency in another plan


def test_chip_for_a_foreign_dependency_reads_the_qualified_reference():
    """
    A dependency in another plan is chipped under its plan-qualified reference.
    """
    reference = foreign_reference(ForeignItemId.READY)
    renderer = make_renderer_over_plan_directory(
        [item("a", ItemStatus.NOT_STARTED, depends_on=[reference])],
        FOREIGN_PULL_REQUESTS,
    )
    page = renderer.render()
    chip = page.cards_by_identifier["a"].dependency_chips[0]
    assert chip.dependency.reference.text == reference
    assert chip.dependency.is_ready_to_unblock_dependents() is True


def test_chip_tooltip_carries_the_foreign_items_title_plan_and_live_state():
    """
    A foreign dependency's tooltip names its title, its plan and its live state.
    """
    renderer = make_renderer_over_plan_directory(
        [
            item(
                "a",
                ItemStatus.NOT_STARTED,
                depends_on=[foreign_reference(ForeignItemId.DRAFT)],
            )
        ],
        FOREIGN_PULL_REQUESTS,
    )
    page = renderer.render()
    chip = page.cards_by_identifier["a"].dependency_chips[0]
    foreign = renderer.dependencies.resolve(foreign_reference(ForeignItemId.DRAFT))
    assert foreign.title in chip.tooltip
    assert foreign.plan.title in chip.tooltip
    assert LiveState.OPEN_DRAFT.display_label in chip.tooltip


def test_chip_links_to_the_foreign_items_card_on_its_plans_page():
    """
    A foreign dependency's chip links to its card on its own plan's page.
    """
    reference = foreign_reference(ForeignItemId.DONE)
    renderer = make_renderer_over_plan_directory(
        [item("a", ItemStatus.NOT_STARTED, depends_on=[reference])],
        locate_plan_page=site_plan_url,
    )
    page = renderer.render()
    chip = page.cards_by_identifier["a"].dependency_chips[0]
    foreign = renderer.dependencies.resolve(reference)
    assert (
        chip.card_url == f"{site_plan_url(FixturePlanId.OTHER)}#{foreign.item.anchor}"
    )
    assert chip.dependency.is_in_another_plan is True


def test_chip_has_no_link_to_a_foreign_item_when_plan_pages_have_no_address():
    """
    Without plan page addresses, a foreign dependency's chip links nowhere.
    """
    renderer = make_renderer_over_plan_directory(
        [
            item(
                "a",
                ItemStatus.NOT_STARTED,
                depends_on=[foreign_reference(ForeignItemId.DONE)],
            )
        ]
    )
    page = renderer.render()
    assert page.cards_by_identifier["a"].dependency_chips[0].card_url is None


def test_chip_for_a_same_plan_dependency_links_to_its_card_on_this_page():
    """
    A same-plan dependency's chip links to its card's anchor on this page.
    """
    renderer = make_renderer_over_plan_directory(
        [
            item("a", ItemStatus.DONE),
            item("b", ItemStatus.NOT_STARTED, depends_on=["a"]),
        ]
    )
    page = renderer.render()
    chip = page.cards_by_identifier["b"].dependency_chips[0]
    assert chip.card_url == f"#{renderer.plan.items_by_identifier['a'].anchor}"
    assert chip.dependency.is_in_another_plan is False


def test_chip_for_an_unresolved_dependency_has_no_link():
    """
    An unresolved dependency's chip links nowhere.
    """
    renderer = make_renderer(
        [item("a", ItemStatus.NOT_STARTED, depends_on=["missing"])]
    )
    page = renderer.render()
    assert page.cards_by_identifier["a"].dependency_chips[0].card_url is None


def test_render_gives_each_item_card_its_anchor():
    renderer = renderer_with_cards([item("a", ItemStatus.NOT_STARTED)])
    output = renderer.render().html
    assert f'id="{renderer.plan.items_by_identifier["a"].anchor}"' in output


def test_render_opens_a_foreign_dependency_chip_in_a_new_tab():
    """
    A foreign dependency's chip opens its plan's page in a new tab.
    """
    reference = foreign_reference(ForeignItemId.DONE)
    renderer = renderer_with_cards(
        [item("a", ItemStatus.NOT_STARTED, depends_on=[reference])],
        locate_plan_page=site_plan_url,
    )
    page = renderer.render()
    output = page.html
    chip = page.cards_by_identifier["a"].dependency_chips[0]
    assert f'href="{chip.card_url}" target="_blank"' in output


def test_render_highlights_a_same_plan_dependency_chips_card_on_click():
    """
    A same-plan dependency's chip highlights that card when clicked.
    """
    renderer = renderer_with_cards(
        [
            item("a", ItemStatus.DONE),
            item("b", ItemStatus.NOT_STARTED, depends_on=["a"]),
        ]
    )
    page = renderer.render()
    output = page.html
    chip = page.cards_by_identifier["b"].dependency_chips[0]
    assert (
        f'href="{chip.card_url}" data-item-identifier="{chip.dependency.reference.text}" '
        'onclick="planPageHighlightItem(event, this)"' in output
    )
