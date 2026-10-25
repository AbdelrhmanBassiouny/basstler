"""
Tests for the manifest vocabulary and exit statuses the item-bootstrap commands share.
"""

from __future__ import annotations

import subprocess

import pytest
import yaml

from basstler.locations import PluginLocation, ProjectLocation
from basstler.plan.item_bootstrap.exceptions import (
    BranchAlreadyPublishedError,
    IncompleteNewItemError,
    PlanNotWrittenError,
    PlanSaveRefusedError,
    PullRequestDetailsMissingError,
    PullRequestRefusedError,
    UnknownItemError,
    UnknownPlanError,
)
from basstler.plan.item_bootstrap.manifest_text import ManifestText
from basstler.plan.item_bootstrap.record import ItemRecordRequest
from basstler.plan.item_bootstrap.vocabulary import PlanItemBootstrapExitCode
from basstler.plan.model import (
    ItemStatus,
    KeySpecification,
    ManifestKey,
    PlanDocument,
    Prose,
    ValueStyle,
)

from ...constants.paths import DatasetLocation
from ...scratch_repository import ScratchRepository
from .bootstrap_scenario import (
    EXISTING_ITEM,
    NEW_ITEM,
    PLAN_IDENTIFIER,
    PLAN_MANIFEST,
    manifest_line,
)

# %% the vocabulary the manifest is written in


def test_a_rendered_field_line_matches_how_a_real_manifest_writes_it():
    """
    The renderer's indentation and spacing have to match a manifest written by hand,
    since every other test compares the two.
    """
    assert (
        manifest_line(ManifestKey.STATUS, ItemStatus.NOT_STARTED.value) in PLAN_MANIFEST
    )
    assert manifest_line(ManifestKey.TRACK, "a-track") in PLAN_MANIFEST


NARROWLY_INDENTED_MANIFEST = (
    DatasetLocation.DIRECTORY / "narrowly-indented-plan.yaml"
).read_text()
"""
A manifest predating this module's own formatting convention: its items list has no
indent before the ``-`` and its fields sit two spaces in, not the four
``ItemLayout.FIELD_INDENT`` assumes.

``icra-mechanism/plan.yaml`` on the personal-notes branch is written exactly this way.
"""


def test_patching_a_field_matches_the_items_own_indentation_rather_than_a_fixed_one():
    """
    A fixed indentation nests a patched field under whichever key happens to precede it.

    instead of beside it, the moment a manifest's own indentation differs from the
    module's assumed one - which stops the result parsing as YAML at all.
    """
    patched = ManifestText.from_text(NARROWLY_INDENTED_MANIFEST).with_item_fields(
        "narrow-plan",
        "an-item",
        {ManifestKey.STATUS: ItemStatus.IN_PROGRESS.value},
    )

    item = yaml.safe_load(patched)[ManifestKey.ITEMS.key][0]
    assert item[ManifestKey.STATUS.key] == ItemStatus.IN_PROGRESS.value
    assert item[ManifestKey.TITLE.key] == "An item indented two spaces, not four"


def test_a_new_item_matches_the_existing_items_indentation_rather_than_a_fixed_one():
    """
    A new item rendered at a fixed indentation lands inside the previous item instead of
    beside it whenever the manifest's own items sit flush with ``items:``, and the
    result stops parsing as YAML at all.
    """
    request = ItemRecordRequest(
        plan_identifier="narrow-plan",
        item_identifier=NEW_ITEM,
        status=ItemStatus.NOT_STARTED,
        title="A brand new item",
        track="a-track",
    )
    manifest = ManifestText.from_text(NARROWLY_INDENTED_MANIFEST)

    extended = manifest.with_item(request.render_new_item(manifest.item_indentation()))

    items = yaml.safe_load(extended)[ManifestKey.ITEMS.key]
    assert [item[ManifestKey.IDENTIFIER.key] for item in items] == ["an-item", NEW_ITEM]
    assert items[1][ManifestKey.TRACK.key] == "a-track"


def test_a_key_quotes_its_own_value_when_its_style_says_to():
    """
    Quoting is the key's to decide, so no caller has to know that a title is prose and a
    track is a bare identifier.
    """
    assert ManifestKey.TITLE.render("A brand new item").endswith(
        ': "A brand new item"\n'
    )
    assert ManifestKey.TRACK.render("a-track").endswith(": a-track\n")
    assert ManifestKey.TITLE.style is ValueStyle.DOUBLE_QUOTED
    assert ManifestKey.TRACK.style is ValueStyle.PLAIN


def test_every_key_is_a_specification_in_its_own_right():
    """
    Mixing the specification into the enum is what lets a key carry its style without a
    lookup beside it, so the relationship is asserted rather than assumed.
    """
    assert issubclass(ManifestKey, KeySpecification)
    assert all(
        isinstance(manifest_key, KeySpecification) for manifest_key in ManifestKey
    )


def test_every_key_was_declared_as_specification_arguments():
    """
    A member declared as a built ``KeySpecification`` rather than as its argument tuple
    is accepted silently by the enum machinery and lands the whole instance in ``key``.

    This is what catches that.
    """
    assert all(isinstance(manifest_key.key, str) for manifest_key in ManifestKey)
    assert all(
        isinstance(manifest_key.style, ValueStyle) for manifest_key in ManifestKey
    )


def test_a_key_indexes_a_parsed_manifest_by_the_string_it_names():
    """
    A key reads parsed YAML through its own ``key``, which is the manifest's own
    spelling of it.
    """
    item = yaml.safe_load(PLAN_MANIFEST)[ManifestKey.ITEMS.key][0]
    assert item[ManifestKey.IDENTIFIER.key] == EXISTING_ITEM
    assert item[ManifestKey.STATUS.key] == ItemStatus.NOT_STARTED


def test_the_plans_directory_matches_the_shell_configuration_that_owns_it(
    bootstrap_repository: ScratchRepository,
):
    """
    ``ProjectLocation.PLANS`` mirrors ``PLANS_DIR`` in the shell configuration, and
    ``ProjectLocation.PLAN_HUB`` mirrors ``PLAN_HUB_PATH``; this is what stops the
    mirrors drifting, since each pair is edited in different files.
    """
    resolved = subprocess.run(
        [
            "bash",
            "-c",
            f'source "{PluginLocation.PERSONAL_NOTES_CONFIGURATION_SCRIPT}" && '
            'printf "%s\\n%s\\n%s\\n" "${PLANS_DIR}" "$(plan_manifest_path "$1")" '
            '"${PLAN_HUB_PATH}"',
            "test",
            PLAN_IDENTIFIER,
        ],
        cwd=bootstrap_repository.project_root,
        capture_output=True,
        text=True,
        check=True,
    )
    plans_directory, manifest_path, hub_path = resolved.stdout.strip().split("\n")
    assert plans_directory == str(ProjectLocation.PLANS)
    assert hub_path == str(ProjectLocation.PLAN_HUB)
    assert manifest_path == PlanDocument.MANIFEST.path_within_notes_branch(
        PLAN_IDENTIFIER
    )


SCALAR_STYLED_KEYS = tuple(
    manifest_key for manifest_key in ManifestKey if not manifest_key.is_block_styled
)
"""
The keys whose value is written on the key's own line, derived from the styles rather
than listed a second time.
"""

VALUES_YAML_READS_BACK_DIFFERENTLY = (
    "opened on #76",
    'a value carrying a "quoted" phrase',
    r"a path like C:\temp",
    "a value ending in a colon:",
)
"""
Values a manifest can legitimately carry that YAML does not read back as written unless
the writer quotes and escapes them.
"""


@pytest.mark.parametrize("hostile_value", VALUES_YAML_READS_BACK_DIFFERENTLY)
@pytest.mark.parametrize("manifest_key", SCALAR_STYLED_KEYS)
def test_a_rendered_scalar_reads_back_as_the_value_it_was_given(
    manifest_key: ManifestKey, hostile_value: str
):
    written = yaml.safe_load(manifest_key.render(hostile_value))

    assert written[manifest_key.key] == hostile_value


def test_a_word_wrapped_at_its_hyphen_is_written_whole():
    """
    A hyphen at the end of a hard-wrapped line is where the author broke a word they
    wrote whole.
    """
    written = Prose("the paragraphs have to be blank-\nline separated").folded("")

    assert written == "the paragraphs have to be blank-line separated\n"


def test_a_suspended_hyphen_typed_on_one_line_keeps_its_space():
    written = Prose("all network- and credential-free tests").folded("")

    assert written == "all network- and credential-free tests\n"


def test_a_paragraph_break_still_separates_paragraphs_after_a_hyphen():
    assert Prose("ends in a-\n\nnew paragraph").paragraphs == [
        "ends in a-",
        "new paragraph",
    ]


def test_only_the_keys_whose_values_run_over_lines_are_block_styled():
    assert ManifestKey.block_styled() == {
        ManifestKey.NOTES,
        ManifestKey.BLOCKERS,
        ManifestKey.DEPENDS_ON,
    }


# %% exit statuses


def test_every_exit_code_names_itself_from_its_own_member():
    for exit_code in PlanItemBootstrapExitCode:
        assert exit_code.name_for_a_caller == exit_code.name.lower()


def test_each_refusal_carries_its_own_exit_code():
    codes = {
        UnknownPlanError: PlanItemBootstrapExitCode.UNKNOWN_PLAN,
        UnknownItemError: PlanItemBootstrapExitCode.UNKNOWN_ITEM,
        IncompleteNewItemError: PlanItemBootstrapExitCode.INCOMPLETE_NEW_ITEM,
        BranchAlreadyPublishedError: (
            PlanItemBootstrapExitCode.BRANCH_ALREADY_PUBLISHED
        ),
        PullRequestDetailsMissingError: (
            PlanItemBootstrapExitCode.PULL_REQUEST_DETAILS_MISSING
        ),
        PullRequestRefusedError: PlanItemBootstrapExitCode.PULL_REQUEST_REFUSED,
        PlanSaveRefusedError: PlanItemBootstrapExitCode.PLAN_SAVE_REFUSED,
        PlanNotWrittenError: PlanItemBootstrapExitCode.PLAN_NOT_WRITTEN,
    }
    assert {error: error.exit_code for error in codes} == codes


def test_a_refusal_composes_its_message_from_its_own_fields():
    refusal = UnknownItemError(
        plan_identifier=PLAN_IDENTIFIER, item_identifier="no-such-item"
    )
    assert refusal.error_message() in str(refusal)
    assert refusal.suggest_correction() in str(refusal)
