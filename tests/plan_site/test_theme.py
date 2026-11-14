"""
Tests for plan_site/theme.py: the site's themes, their contrast, and the appearance a
site is built with.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path
from urllib.parse import quote

import pydantic
import pytest
import yaml

from basstler.plan_site.hub import HubCommand, PlanHub, main
from basstler.plan_site.hub_page import HubPage, SiteStylesheet, SiteSummary
from basstler.plan_site.theme import (
    AppearanceAttribute,
    AppearanceSettings,
    AppearanceStorageKey,
    Backdrop,
    BuiltInTheme,
    BundledFont,
    ChipShape,
    Color,
    ColorScheme,
    Frame,
    HeadingCase,
    SiteAppearance,
    SiteTheme,
    SkippedTheme,
    ThemeStyle,
)

from ..constants.paths import DatasetLocation
from ..constants.site import SiteRepository, SiteSampleText

# %% fixtures


def theme_from(path: Path) -> SiteTheme:
    """
    :param path: A theme file of the test dataset.
    :return: The theme it describes.
    """
    return SiteTheme.from_json(yaml.safe_load(path.read_text()))


@pytest.fixture
def readable_theme() -> SiteTheme:
    """
    An owner's theme whose text is readable in both colour schemes.
    """
    return theme_from(DatasetLocation.READABLE_THEME)


@pytest.fixture
def faint_theme() -> SiteTheme:
    """
    An owner's theme whose muted text is too faint when shown light.
    """
    return theme_from(DatasetLocation.FAINT_THEME)


# %% contrast


def test_two_colours_mix_channel_by_channel():
    assert Color("#000000").mixed_with(Color("#FFFFFF"), 0.2) == Color("#333333")


def test_a_colour_fully_lightened_is_white_and_fully_darkened_is_black():
    colour = Color("#3A7CA5")

    assert (colour.lightened(1), colour.darkened(1)) == (
        Color("#FFFFFF"),
        Color("#000000"),
    )


def test_black_on_white_has_the_highest_contrast_wcag_defines():
    assert Color("#000000").contrast_with(Color("#FFFFFF")) == pytest.approx(21)


def test_a_colour_on_itself_has_no_contrast():
    assert Color("#0E7C86").contrast_with(Color("#0E7C86")) == pytest.approx(1)


@pytest.mark.parametrize("member", list(BuiltInTheme))
def test_every_built_in_theme_is_readable_in_both_schemes(member: BuiltInTheme):
    assert member.theme.unreadable_pairings == []


@pytest.mark.parametrize("member", list(BuiltInTheme))
def test_a_built_in_theme_is_known_by_its_file_stem(member: BuiltInTheme):
    assert member.theme.identifier == member.stem


def test_a_faint_theme_names_the_pairing_it_fails(faint_theme: SiteTheme):
    assert len(faint_theme.unreadable_pairings) >= 1
    assert all(
        f"({ColorScheme.LIGHT}," in pairing
        for pairing in faint_theme.unreadable_pairings
    )


# %% validating what the owner writes


def test_a_colour_that_is_not_hexadecimal_is_refused(readable_theme: SiteTheme):
    data = readable_theme.to_json()
    data["light"]["text"] = "red"
    with pytest.raises(pydantic.ValidationError):
        SiteTheme.from_json(data)


def test_an_ornament_that_could_end_a_css_rule_is_refused():
    with pytest.raises(pydantic.ValidationError):
        ThemeStyle.from_json({"ornament": "}"})


def test_a_font_list_that_could_end_a_css_declaration_is_refused():
    with pytest.raises(pydantic.ValidationError):
        ThemeStyle.from_json({"body_font": "serif; color: red"})


def test_a_frame_the_site_does_not_draw_is_refused():
    with pytest.raises(pydantic.ValidationError):
        ThemeStyle.from_json({"frame": "glass"})


def test_a_backdrop_the_site_does_not_draw_is_refused():
    with pytest.raises(pydantic.ValidationError):
        ThemeStyle.from_json({"backdrop": "aurora"})


def test_a_theme_file_names_its_frame_backdrop_and_chip_shape(
    readable_theme: SiteTheme,
):
    style = readable_theme.style

    assert (style.frame, style.backdrop, style.chip_shape, style.animated) == (
        Frame.GILDED,
        Backdrop.STARS,
        ChipShape.NOTCHED,
        True,
    )


# %% the appearance a site is built with


def test_a_faint_theme_is_left_out_and_reported(faint_theme: SiteTheme):
    appearance = SiteAppearance(AppearanceSettings(themes=(faint_theme,)))

    assert faint_theme.identifier not in [
        theme.identifier for theme in appearance.themes
    ]
    assert appearance.skipped_themes == [
        SkippedTheme(faint_theme.identifier, faint_theme.contrast_report)
    ]


def test_an_owner_theme_is_published_after_the_built_in_ones(readable_theme: SiteTheme):
    appearance = SiteAppearance(AppearanceSettings(themes=(readable_theme,)))

    assert [theme.identifier for theme in appearance.themes] == [
        *(member.stem for member in BuiltInTheme),
        readable_theme.identifier,
    ]


def test_an_owner_theme_replaces_the_built_in_theme_of_its_id(
    readable_theme: SiteTheme,
):
    replacement = replace(readable_theme, identifier=BuiltInTheme.CLASSIC.stem)
    appearance = SiteAppearance(AppearanceSettings(themes=(replacement,)))

    assert appearance.candidate_themes[BuiltInTheme.CLASSIC.stem] == replacement


def test_the_owner_picks_the_default_theme(readable_theme: SiteTheme):
    settings = AppearanceSettings(
        default_theme=readable_theme.identifier, themes=(readable_theme,)
    )

    assert SiteAppearance(settings).default_theme == readable_theme


def test_an_unknown_default_falls_back_to_classic_and_is_reported():
    settings = AppearanceSettings(default_theme="nowhere")
    appearance = SiteAppearance(settings)

    assert appearance.default_theme == BuiltInTheme.CLASSIC.theme
    assert [skipped.identifier for skipped in appearance.skipped_themes] == [
        settings.default_theme
    ]


def test_a_faint_default_falls_back_to_classic(faint_theme: SiteTheme):
    settings = AppearanceSettings(
        default_theme=faint_theme.identifier, themes=(faint_theme,)
    )

    assert SiteAppearance(settings).default_theme == BuiltInTheme.CLASSIC.theme


def test_the_viewer_starts_from_the_owner_default_scheme():
    settings = AppearanceSettings(default_scheme=ColorScheme.DARK)
    choices = {
        choice.attribute: choice.default
        for choice in SiteAppearance(settings).viewer_choices
    }

    assert choices[AppearanceAttribute.SCHEME] == ColorScheme.DARK


# %% the stylesheet and the pages


def test_the_stylesheet_declares_every_published_theme_and_no_faint_one(
    faint_theme: SiteTheme,
):
    appearance = SiteAppearance(AppearanceSettings(themes=(faint_theme,)))
    stylesheet = SiteStylesheet(appearance).render()

    for theme in appearance.themes:
        assert f'{AppearanceAttribute.THEME}="{theme.identifier}"' in stylesheet
    assert f'{AppearanceAttribute.THEME}="{faint_theme.identifier}"' not in stylesheet


def test_the_stylesheet_writes_a_theme_s_colours(readable_theme: SiteTheme):
    appearance = SiteAppearance(AppearanceSettings(themes=(readable_theme,)))
    stylesheet = SiteStylesheet(appearance).render()

    assert f'"{readable_theme.style.ornament}"' in stylesheet
    assert readable_theme.dark.text_muted in stylesheet


def theme_declaration(theme: SiteTheme) -> str:
    """
    :param theme: A readable theme.
    :return: The stylesheet's rule that declares the theme's style and light colours.
    """
    stylesheet = SiteStylesheet(
        SiteAppearance(AppearanceSettings(themes=(theme,)))
    ).render()
    opening = f'[{AppearanceAttribute.THEME}="{theme.identifier}"] {{'
    return stylesheet.split(opening, 1)[1].split("}", 1)[0]


def test_every_frame_draws_its_own_shape(readable_theme: SiteTheme):
    declarations = {
        theme_declaration(
            replace(readable_theme, style=replace(readable_theme.style, frame=frame))
        )
        for frame in Frame
    }

    assert len(declarations) == len(Frame)


def test_a_frame_drawn_from_artwork_is_painted_in_the_theme_s_accent(
    readable_theme: SiteTheme,
):
    assert readable_theme.style.frame.is_drawn_from_artwork
    assert quote(readable_theme.light.accent) in theme_declaration(readable_theme)


def test_every_backdrop_draws_its_own_scene(readable_theme: SiteTheme):
    declarations = {
        theme_declaration(
            replace(
                readable_theme, style=replace(readable_theme.style, backdrop=backdrop)
            )
        )
        for backdrop in Backdrop
    }

    assert len(declarations) == len(Backdrop)


def test_a_scene_is_painted_in_the_ink_text_is_checked_on(readable_theme: SiteTheme):
    ink = readable_theme.light.scene_ink(1)

    assert quote(f'fill="{ink}"') in theme_declaration(readable_theme)
    assert ink in {
        pairing.background for pairing in readable_theme.light.backdrop_pairings
    }


def test_a_theme_with_a_backdrop_is_checked_against_its_scene(
    readable_theme: SiteTheme,
):
    plain = replace(
        readable_theme, style=replace(readable_theme.style, backdrop=Backdrop.NONE)
    )

    assert plain.pairings_of(plain.light) == plain.light.text_pairings
    assert readable_theme.pairings_of(readable_theme.light) == (
        readable_theme.light.text_pairings + readable_theme.light.backdrop_pairings
    )


@pytest.mark.parametrize("font", BundledFont)
def test_the_stylesheet_loads_every_font_the_site_serves(font: BundledFont):
    face = font.value
    stylesheet = SiteStylesheet().render()
    assert f'font-family: "{face.family}"; font-style: {face.slant};' in stylesheet
    assert f'url("{face.site_path}")' in stylesheet


@pytest.mark.parametrize("font", BundledFont)
def test_a_font_the_site_serves_is_shipped_with_the_package(font: BundledFont):
    assert font.value.file.is_file()


def test_every_heading_case_sets_its_own_letters(readable_theme: SiteTheme):
    declarations = {
        theme_declaration(
            replace(
                readable_theme, style=replace(readable_theme.style, heading_case=case)
            )
        )
        for case in HeadingCase
    }

    assert len(declarations) == len(HeadingCase)


def test_only_an_animated_theme_moves(readable_theme: SiteTheme):
    still = replace(readable_theme, style=replace(readable_theme.style, animated=False))

    assert theme_declaration(still) != theme_declaration(readable_theme)


def test_every_chip_shape_draws_its_own_outline(readable_theme: SiteTheme):
    declarations = {
        theme_declaration(
            replace(
                readable_theme, style=replace(readable_theme.style, chip_shape=shape)
            )
        )
        for shape in ChipShape
    }

    assert len(declarations) == len(ChipShape)


@pytest.fixture
def hub_page_html(readable_theme: SiteTheme) -> str:
    """
    An empty hub page whose owner made :func:`readable_theme` the default, shown dark.
    """
    settings = AppearanceSettings(
        default_theme=readable_theme.identifier,
        default_scheme=ColorScheme.DARK,
        themes=(readable_theme,),
    )
    page = HubPage(
        SiteSummary.over_repositories([], []),
        stylesheet_url=SiteSampleText.SITE_URL,
        appearance=SiteAppearance(settings),
    )
    return page.render()


def test_a_page_is_drawn_in_the_default_theme_and_scheme_before_any_script(
    hub_page_html: str, readable_theme: SiteTheme
):
    assert (
        f'<html lang="en" {AppearanceAttribute.SCHEME}="{ColorScheme.DARK}" '
        f'{AppearanceAttribute.THEME}="{readable_theme.identifier}">'
    ) in hub_page_html


def test_a_page_offers_every_published_theme_and_scheme(hub_page_html: str):
    for theme in SiteAppearance().themes:
        assert f'<option value="{theme.identifier}"' in hub_page_html
    for scheme in ColorScheme:
        assert f'<option value="{scheme}"' in hub_page_html


def test_a_page_applies_the_stored_choice_in_its_head(hub_page_html: str):
    head = hub_page_html[: hub_page_html.index("</head>")]
    for key in AppearanceStorageKey:
        assert key in head
    assert head.index("<script>") < head.index('<link rel="stylesheet"')


def test_the_hub_names_a_theme_left_out(faint_theme: SiteTheme):
    appearance = SiteAppearance(AppearanceSettings(themes=(faint_theme,)))
    page = HubPage(
        SiteSummary.over_repositories([], appearance.skipped_themes),
        stylesheet_url=SiteSampleText.SITE_URL,
        appearance=appearance,
    )

    assert f"Theme <code>{faint_theme.identifier}</code>" in page.render()


# %% the hub file


def test_the_hub_file_keeps_its_appearance(readable_theme: SiteTheme):
    hub = PlanHub(
        registry=str(SiteRepository.NOTES.value),
        appearance=AppearanceSettings(
            default_theme=readable_theme.identifier, themes=(readable_theme,)
        ),
    )

    assert PlanHub.from_yaml(hub.to_text()) == hub


def run_add_theme(
    monkeypatch: pytest.MonkeyPatch, hub_path: Path, theme: Path, *flags: str
) -> int:
    """
    Run the hub command's ``add-theme`` subcommand in process, writing over the hub
    file.

    :param hub_path: The hub file it reads and writes.
    :param theme: The theme file to add.
    :param flags: Further arguments.
    :return: The command's exit status.
    """
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "hub",
            HubCommand.ADD_THEME,
            f"--hub={hub_path}",
            f"--theme={theme}",
            f"--output={hub_path}",
            *flags,
        ],
    )
    return main()


@pytest.fixture
def hub_path(tmp_path: Path) -> Path:
    """
    A hub file with no appearance section.
    """
    path = tmp_path / "hub.yaml"
    path.write_text(PlanHub(registry=str(SiteRepository.NOTES.value)).to_text())
    return path


def test_add_theme_adds_a_readable_theme_as_the_default(
    monkeypatch: pytest.MonkeyPatch, hub_path: Path, readable_theme: SiteTheme
):
    status = run_add_theme(
        monkeypatch, hub_path, DatasetLocation.READABLE_THEME, "--default"
    )

    appearance = PlanHub.load(hub_path).appearance
    assert status == 0
    assert appearance.themes == (readable_theme,)
    assert appearance.default_theme == readable_theme.identifier


def test_add_theme_refuses_a_faint_theme(
    monkeypatch: pytest.MonkeyPatch, hub_path: Path
):
    before = hub_path.read_text()

    status = run_add_theme(monkeypatch, hub_path, DatasetLocation.FAINT_THEME)

    assert status == 1
    assert hub_path.read_text() == before
