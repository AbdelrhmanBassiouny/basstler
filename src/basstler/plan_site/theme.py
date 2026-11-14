"""
The plan site's themes: the colours, type, frames, backdrops, chip shapes and motion a viewer
picks on the page, and the contrast every theme's text must reach before it is published.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum, StrEnum
from functools import cached_property
from typing import Annotated

import yaml
from pydantic import StringConstraints

from basstler.locations import PackageLocation, PathEnumeration, SiteFontFile
from basstler.json_model import ValidatedJSONModel
from basstler.plan_site.exceptions import NoPublishableThemeError

# %% constants

MINIMUM_TEXT_CONTRAST = 4.5
"""
The contrast ratio WCAG 2 level AA requires between normal-size text and its background.
"""

BACKDROP_INK_SHARE = 0.14
"""
The most of the text colour a backdrop's scene mixes into the background.
"""

# %% validated values

HexadecimalColor = Annotated[str, StringConstraints(pattern=r"^#[0-9A-Fa-f]{6}$")]
"""
A colour written as ``#RRGGBB``.
"""

ThemeIdentifier = Annotated[
    str, StringConstraints(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=40)
]
"""
A theme's id: lowercase words joined by hyphens.
"""

FontStack = Annotated[
    str, StringConstraints(pattern=r"^[A-Za-z0-9 ,\"'\-]+$", max_length=200)
]
"""
A CSS ``font-family`` list.
"""

CSSLength = Annotated[str, StringConstraints(pattern=r"^\d+(\.\d+)?(px|rem|em)$")]
"""
A CSS length in ``px``, ``rem`` or ``em``.
"""

CSSDuration = Annotated[str, StringConstraints(pattern=r"^\d+(ms|s)$")]
"""
A CSS duration in ``ms`` or ``s``.
"""

Ornament = Annotated[str, StringConstraints(pattern=r"^[^\"\\;{}<>\n]{0,4}$")]
"""
At most four characters shown before every page's eyebrow, or none.
"""

# %% the viewer's choices


class ColorScheme(StrEnum):
    """
    Whether a page is shown light, dark, or as the viewer's system prefers.
    """

    SYSTEM = "system"
    """
    Follow the viewer's operating system.
    """

    LIGHT = "light"
    """
    Always light.
    """

    DARK = "dark"
    """
    Always dark.
    """


class AppearanceAttribute(StrEnum):
    """
    The attributes of a page's root element its stylesheet picks the appearance by.
    """

    THEME = "data-theme"
    """
    The id of the theme shown.
    """

    SCHEME = "data-scheme"
    """
    The :class:`ColorScheme` shown.
    """


class AppearanceStorageKey(StrEnum):
    """
    The keys a viewer's choices are kept under in the browser's ``localStorage``.
    """

    THEME = "basstler-site-theme"
    """
    The id of the theme the viewer picked.
    """

    SCHEME = "basstler-site-scheme"
    """
    The :class:`ColorScheme` the viewer picked.
    """


# %% contrast


@dataclass(frozen=True)
class Color:
    """
    An sRGB colour.
    """

    hexadecimal: str
    """
    The colour as ``#RRGGBB``.
    """

    @property
    def relative_luminance(self) -> float:
        """
        The colour's relative luminance as WCAG 2 defines it, from 0 for black to 1 for
        white.
        """
        red, green, blue = (
            self.linear_channel(int(self.hexadecimal[start : start + 2], 16))
            for start in (1, 3, 5)
        )
        return 0.2126 * red + 0.7152 * green + 0.0722 * blue

    @staticmethod
    def linear_channel(value: int) -> float:
        """
        :param value: One gamma-encoded channel, from 0 to 255.
        :return: The channel's linear intensity, from 0 to 1.
        """
        encoded = value / 255
        if encoded <= 0.04045:
            return encoded / 12.92
        return ((encoded + 0.055) / 1.055) ** 2.4

    def __str__(self) -> str:
        return self.hexadecimal

    def mixed_with(self, other: Color, share: float) -> Color:
        """
        :param other: The colour mixed in.
        :param share: How much of *other* the mix holds, from 0 for none to 1 for all.
        :return: The two colours mixed channel by channel.
        """
        channels = (
            round(
                int(self.hexadecimal[start : start + 2], 16) * (1 - share)
                + int(other.hexadecimal[start : start + 2], 16) * share
            )
            for start in (1, 3, 5)
        )
        return Color("#" + "".join(f"{channel:02X}" for channel in channels))

    def lightened(self, share: float) -> Color:
        """
        :param share: How much white is mixed in, from 0 to 1.
        :return: The colour mixed with white.
        """
        return self.mixed_with(Color("#FFFFFF"), share)

    def darkened(self, share: float) -> Color:
        """
        :param share: How much black is mixed in, from 0 to 1.
        :return: The colour mixed with black.
        """
        return self.mixed_with(Color("#000000"), share)

    def contrast_with(self, other: Color) -> float:
        """
        :param other: The colour this one is shown against.
        :return: The WCAG 2 contrast ratio between the two, from 1 to 21.
        """
        lighter, darker = sorted(
            (self.relative_luminance, other.relative_luminance), reverse=True
        )
        return (lighter + 0.05) / (darker + 0.05)


@dataclass(frozen=True)
class ColorPairing:
    """
    Text of one colour shown on a background of another somewhere on the site.
    """

    description: str
    """
    Where the site shows the pairing, as a reader recognises it.
    """

    foreground: Color
    """
    The text's colour.
    """

    background: Color
    """
    The colour behind it.
    """

    @property
    def contrast(self) -> float:
        """
        The contrast ratio between the text and its background.
        """
        return self.foreground.contrast_with(self.background)

    @property
    def is_readable(self) -> bool:
        """
        Whether the contrast reaches :data:`MINIMUM_TEXT_CONTRAST`.
        """
        return self.contrast >= MINIMUM_TEXT_CONTRAST


# %% a theme as the hub file or a built-in theme file writes it


class Palette(ValidatedJSONModel):
    """
    The colours of a theme in one colour scheme.
    """

    background: HexadecimalColor
    """
    Behind the page.
    """

    surface: HexadecimalColor
    """
    Behind cards and panels.
    """

    surface_alternate: HexadecimalColor
    """
    Behind wave columns and progress bars.
    """

    text: HexadecimalColor
    """
    Body text.
    """

    text_muted: HexadecimalColor
    """
    Secondary text: descriptions, labels and dates.
    """

    border: HexadecimalColor
    """
    Card and panel borders.
    """

    accent: HexadecimalColor
    """
    The theme's signature colour: progress bars, focus rings and highlights.
    """

    accent_strong: HexadecimalColor
    """
    Links, eyebrows and accent chips' text.
    """

    accent_tint: HexadecimalColor
    """
    Behind accent chips and action buttons.
    """

    good: HexadecimalColor
    """
    Text of landed or passing chips.
    """

    good_tint: HexadecimalColor
    """
    Behind landed or passing chips.
    """

    warning: HexadecimalColor
    """
    Text of chips and notices about something not finished yet.
    """

    warning_tint: HexadecimalColor
    """
    Behind those chips and the health banner.
    """

    bad: HexadecimalColor
    """
    Text of failed, blocked or closed chips, and of errors.
    """

    bad_tint: HexadecimalColor
    """
    Behind failed, blocked or closed chips.
    """

    info: HexadecimalColor
    """
    Text of chips for work under way.
    """

    info_tint: HexadecimalColor
    """
    Behind chips for work under way.
    """

    idle: HexadecimalColor
    """
    Text of chips with nothing to report.
    """

    idle_tint: HexadecimalColor
    """
    Behind chips with nothing to report.
    """

    def scene_ink(self, depth: float) -> Color:
        """
        :param depth: How near the painted thing is, from 0 for the horizon to 1.
        :return: The background tinted towards the text colour, by at most
            :data:`BACKDROP_INK_SHARE`.
        """
        return Color(self.background).mixed_with(
            Color(self.text), depth * BACKDROP_INK_SHARE
        )

    @property
    def backdrop_pairings(self) -> list[ColorPairing]:
        """
        Every pairing of text and the darkest ink of a backdrop's scene.
        """
        return [
            ColorPairing(
                f"{description} on the backdrop", Color(foreground), self.scene_ink(1)
            )
            for description, foreground in (
                ("text", self.text),
                ("muted text", self.text_muted),
                ("links", self.accent_strong),
            )
        ]

    @property
    def text_pairings(self) -> list[ColorPairing]:
        """
        Every pairing of text and background the site's stylesheet shows.
        """
        pairings = [
            (description, foreground, background)
            for background_name, background in (
                ("background", self.background),
                ("surface", self.surface),
                ("alternate surface", self.surface_alternate),
            )
            for description, foreground in (
                (f"text on {background_name}", self.text),
                (f"muted text on {background_name}", self.text_muted),
                (f"links on {background_name}", self.accent_strong),
            )
        ]
        pairings += [
            ("errors on surface", self.bad, self.surface),
            ("warnings on surface", self.warning, self.surface),
            ("text on the health banner", self.text, self.warning_tint),
            ("good chips", self.good, self.good_tint),
            ("warning chips", self.warning, self.warning_tint),
            ("bad chips", self.bad, self.bad_tint),
            ("info chips", self.info, self.info_tint),
            ("idle chips", self.idle, self.idle_tint),
            ("accent chips and buttons", self.accent_strong, self.accent_tint),
        ]
        return [
            ColorPairing(description, Color(foreground), Color(background))
            for description, foreground, background in pairings
        ]


# %% the fonts the site serves


class FontSlant(StrEnum):
    """
    Whether a font's letters stand upright or lean, as CSS ``font-style`` names it.
    """

    UPRIGHT = "normal"
    """
    Letters that stand upright.
    """

    ITALIC = "italic"
    """
    Letters that lean.
    """


@dataclass(frozen=True)
class FontFace:
    """
    One font the site serves itself, so a viewer sees it without having it installed.
    """

    family: str
    """
    The name a theme's font list calls the font by.
    """

    file: SiteFontFile
    """
    The font's file.
    """

    slant: FontSlant = FontSlant.UPRIGHT
    """
    The slant of the letters the file draws.
    """

    @property
    def site_path(self) -> str:
        """
        Where the site serves the file, relative to its stylesheet.
        """
        return f"{self.file.parent.name}/{self.file.name}"


class BundledFont(Enum):
    """
    The fonts the site serves, which any theme's font list may name.
    """

    CINZEL = FontFace("Cinzel", SiteFontFile.CINZEL)
    """
    Capitals after Roman inscriptions.
    """

    ALMENDRA = FontFace("Almendra", SiteFontFile.ALMENDRA)
    """
    A storybook hand.
    """

    PLAYFAIR_DISPLAY = FontFace(
        "Playfair Display", SiteFontFile.PLAYFAIR_DISPLAY_ITALIC, FontSlant.ITALIC
    )
    """
    A high-contrast italic serif.
    """

    OSWALD = FontFace("Oswald", SiteFontFile.OSWALD)
    """
    A narrow gothic.
    """


# %% shape


class Frame(StrEnum):
    """
    The shape and depth of a theme's cards, panels, chips and buttons.

    .. note:: A frame never changes a fill, so text keeps the contrast checked for it.
    """

    FLAT = "flat"
    """
    A thin flat border.
    """

    RAISED = "raised"
    """
    Cushioned panels with a soft shadow that lift on hover, and glossy chips.
    """

    BEVELED = "beveled"
    """
    Chiselled edges lit from the top left with a hard cast shadow, and bevelled chips.
    """

    CARVED = "carved"
    """
    Double-ruled, sunken panels and engraved chips.
    """

    GILDED = "gilded"
    """
    Thick gilded mouldings with scrolled corners, each set with a gem.
    """

    VINE = "vine"
    """
    Carved wood twined with a leafy vine, and berries at the corners.
    """

    LACE = "lace"
    """
    A satin ribbon edged with scalloped lace, and a rose at each corner.
    """

    FORGED = "forged"
    """
    Wrought iron with a molten seam, scrolled corners and flames.
    """

    @property
    def is_drawn_from_artwork(self) -> bool:
        """
        Whether the frame is a picture, drawn in the theme's colours, instead of a border.
        """
        return self in (Frame.GILDED, Frame.VINE, Frame.LACE, Frame.FORGED)


class ChipShape(StrEnum):
    """
    The outline of a theme's chips.
    """

    PILL = "pill"
    """
    Fully rounded ends.
    """

    ROUNDED = "rounded"
    """
    The theme's small corner radius.
    """

    SQUARE = "square"
    """
    Square corners.
    """

    NOTCHED = "notched"
    """
    Corners cut off at an angle.
    """


class HeadingCase(StrEnum):
    """
    How a theme sets the letters of its headings.
    """

    AS_WRITTEN = "as-written"
    """
    The letters as the heading's text has them.
    """

    UPPERCASE = "uppercase"
    """
    Every letter a capital.
    """

    SMALL_CAPITALS = "small-capitals"
    """
    Lowercase letters drawn as small capitals.
    """


class Backdrop(StrEnum):
    """
    The scene along the foot of the page and what drifts across it.

    .. note:: A scene is painted in :meth:`Palette.scene_ink`, which text is checked on.
    """

    NONE = "none"
    """
    The plain background colour.
    """

    STARS = "stars"
    """
    A citadel on a crag under a crescent moon, with dragons, a wizard and knights.
    """

    EMBERS = "embers"
    """
    A volcano, a furnace hall, gears and smiths at the anvil, with sparks rising.
    """

    LEAVES = "leaves"
    """
    A moonlit pine forest with a great tree, an owl, stags and a fairy, with green leaves
    falling among fireflies.
    """

    PETALS = "petals"
    """
    A garden with blossom trees, a gazebo, swans and cats, with petals falling.
    """


class ThemeStyle(ValidatedJSONModel):
    """
    What a theme sets besides its colours.
    """

    body_font: FontStack = (
        '-apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, '
        "sans-serif"
    )
    """
    The font of body text.
    """

    heading_font: FontStack = (
        '-apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, '
        "sans-serif"
    )
    """
    The font of headings.
    """

    monospace_font: FontStack = (
        'ui-monospace, "SF Mono", "Cascadia Code", "JetBrains Mono", Consolas, '
        "monospace"
    )
    """
    The font of chips, ids and code.
    """

    heading_case: HeadingCase = HeadingCase.AS_WRITTEN
    """
    How the letters of headings and buttons are set.
    """

    heading_letter_spacing: CSSLength = "0em"
    """
    The space added between the letters of headings and buttons.
    """

    heading_italic: bool = False
    """
    Whether headings are set in italics.
    """

    corner_radius: CSSLength = "10px"
    """
    The corner radius of cards and panels.
    """

    small_corner_radius: CSSLength = "6px"
    """
    The corner radius of item cards, buttons and menus.
    """

    border_width: CSSLength = "1px"
    """
    The width of card and panel borders.
    """

    ornament: Ornament = ""
    """
    The characters shown before every page's eyebrow.
    """

    frame: Frame = Frame.FLAT
    """
    The shape and depth of cards, panels, chips and buttons.
    """

    chip_shape: ChipShape = ChipShape.PILL
    """
    The outline of chips.
    """

    backdrop: Backdrop = Backdrop.NONE
    """
    The scene behind the page.
    """

    animated: bool = False
    """
    Whether cards arrive, glow and shimmer and the backdrop drifts; never when the
    viewer asks for reduced motion.
    """

    transition_duration: CSSDuration = "120ms"
    """
    How long hover and focus changes take; none when the viewer asks for reduced
    motion.
    """


class SiteTheme(ValidatedJSONModel):
    """
    One theme a viewer can pick.
    """

    identifier: ThemeIdentifier
    """
    The id the page and the viewer's browser know the theme by.
    """

    title: str
    """
    The theme's name in the page's theme menu.
    """

    light: Palette
    """
    The theme's colours when shown light.
    """

    dark: Palette
    """
    The theme's colours when shown dark.
    """

    style: ThemeStyle = field(default_factory=ThemeStyle)
    """
    The theme's type, borders, ornament and motion.
    """

    def pairings_of(self, palette: Palette) -> list[ColorPairing]:
        """
        :param palette: The theme's light or dark colours.
        :return: Every pairing of text and background the theme shows in *palette*.
        """
        if self.style.backdrop is Backdrop.NONE:
            return palette.text_pairings
        return palette.text_pairings + palette.backdrop_pairings

    @property
    def unreadable_pairings(self) -> list[str]:
        """
        Each pairing in either scheme whose contrast is below
        :data:`MINIMUM_TEXT_CONTRAST`, with its scheme and ratio.
        """
        return [
            f"{pairing.description} ({scheme}, {pairing.contrast:.2f}:1)"
            for scheme, palette in (
                (ColorScheme.LIGHT, self.light),
                (ColorScheme.DARK, self.dark),
            )
            for pairing in self.pairings_of(palette)
            if not pairing.is_readable
        ]

    @property
    def contrast_report(self) -> str:
        """
        Which of the theme's pairings miss the WCAG AA text contrast.
        """
        return (
            f"text below the WCAG AA contrast of {MINIMUM_TEXT_CONTRAST}:1: "
            f"{', '.join(self.unreadable_pairings)}"
        )


# %% the built-in themes


class BuiltInTheme(PathEnumeration):
    """
    The theme files the site ships with; each file's stem is its theme's id.
    """

    CLASSIC = PackageLocation.TEMPLATES.value / "themes" / "classic.yaml"
    """
    Teal on cool grey, the site's original look.
    """

    ROSE = PackageLocation.TEMPLATES.value / "themes" / "rose.yaml"
    """
    Rose and plum with serif headings, lace frames set with roses, and falling petals.
    """

    FORGE = PackageLocation.TEMPLATES.value / "themes" / "forge.yaml"
    """
    Ember on iron, with narrow capital headings, wrought-iron frames and rising sparks.
    """

    ELDERWOOD = PackageLocation.TEMPLATES.value / "themes" / "elderwood.yaml"
    """
    Forest green and gold on parchment, with storybook headings, frames of braided branches
    and falling leaves.
    """

    CITADEL = PackageLocation.TEMPLATES.value / "themes" / "citadel.yaml"
    """
    Gold on night slate, with gilded, gem-set frames, notched chips and a starlit citadel.
    """

    @property
    def theme(self) -> SiteTheme:
        """
        The theme the file describes.
        """
        return SiteTheme.from_json(
            {"identifier": self.stem, **yaml.safe_load(self.read_text())}
        )


class AppearanceSettings(ValidatedJSONModel):
    """
    The hub file's appearance section: the site's default theme and colour scheme, and
    the themes its owner adds.
    """

    default_theme: ThemeIdentifier = BuiltInTheme.CLASSIC.stem
    """
    The id of the theme a viewer who picked none sees.
    """

    default_scheme: ColorScheme = ColorScheme.SYSTEM
    """
    The colour scheme a viewer who picked none sees.
    """

    themes: tuple[SiteTheme, ...] = ()
    """
    The owner's themes, shown after the built-in ones; one with a built-in theme's id
    replaces it.
    """

    def with_theme(self, theme: SiteTheme) -> AppearanceSettings:
        """
        :param theme: A theme of the owner's.
        :return: These settings with *theme* added, replacing an owner theme of its id.
        """
        others = tuple(
            listed for listed in self.themes if listed.identifier != theme.identifier
        )
        return replace(self, themes=(*others, theme))


# %% the themes a site is built with


@dataclass(frozen=True)
class SkippedTheme:
    """
    A theme the build left out of the site, and why.
    """

    identifier: str
    """
    The theme's id.
    """

    reason: str
    """
    Why it was left out.
    """


@dataclass(frozen=True)
class ChoiceOption:
    """
    One entry of a menu on the page.
    """

    value: str
    """
    What picking it sets the page's attribute to and keeps in the browser.
    """

    title: str
    """
    The entry's text in the menu.
    """


@dataclass(frozen=True)
class ViewerChoice:
    """
    One menu a viewer picks the page's appearance from, and where the pick is kept.
    """

    label: str
    """
    The menu's label on the page.
    """

    attribute: AppearanceAttribute
    """
    The root element's attribute a pick sets.
    """

    storage_key: AppearanceStorageKey
    """
    The ``localStorage`` key a pick is kept under.
    """

    options: list[ChoiceOption]
    """
    The entries to pick from.
    """

    default: str
    """
    The value shown before the viewer picks one.
    """


@dataclass
class SiteAppearance:
    """
    The themes a site is built with, the default its viewers start from, and every theme
    left out because its text would be hard to read.
    """

    settings: AppearanceSettings = field(default_factory=AppearanceSettings)
    """
    The hub file's appearance section.
    """

    @cached_property
    def candidate_themes(self) -> dict[str, SiteTheme]:
        """
        Every built-in and owner theme by id, an owner's replacing a built-in one.
        """
        themes = {member.stem: member.theme for member in BuiltInTheme}
        themes |= {theme.identifier: theme for theme in self.settings.themes}
        return themes

    @cached_property
    def themes(self) -> list[SiteTheme]:
        """
        The themes the site publishes: every candidate whose text is readable.
        """
        return [
            theme
            for theme in self.candidate_themes.values()
            if not theme.unreadable_pairings
        ]

    @property
    def skipped_themes(self) -> list[SkippedTheme]:
        """
        Every candidate left out for its contrast, then the configured default when
        no such theme is defined.
        """
        skipped = [
            SkippedTheme(theme.identifier, theme.contrast_report)
            for theme in self.candidate_themes.values()
            if theme.unreadable_pairings
        ]
        if self.settings.default_theme not in self.candidate_themes:
            skipped.append(
                SkippedTheme(
                    self.settings.default_theme,
                    "the hub file names it the default theme, but no theme has this id",
                )
            )
        return skipped

    @property
    def default_theme(self) -> SiteTheme:
        """
        The configured default theme when it is published, otherwise Classic, otherwise
        the first theme published.

        :raises NoPublishableThemeError: If no theme is readable.
        """
        published = {theme.identifier: theme for theme in self.themes}
        for identifier in (self.settings.default_theme, BuiltInTheme.CLASSIC.stem):
            if identifier in published:
                return published[identifier]
        if not self.themes:
            raise NoPublishableThemeError(list(self.candidate_themes))
        return self.themes[0]

    @property
    def default_scheme(self) -> ColorScheme:
        """
        The colour scheme a viewer who picked none sees.
        """
        return self.settings.default_scheme

    @property
    def viewer_choices(self) -> list[ViewerChoice]:
        """
        The colour scheme menu and the theme menu every page shows.
        """
        return [
            ViewerChoice(
                label="Scheme",
                attribute=AppearanceAttribute.SCHEME,
                storage_key=AppearanceStorageKey.SCHEME,
                options=[
                    ChoiceOption(scheme, scheme.capitalize()) for scheme in ColorScheme
                ],
                default=self.default_scheme,
            ),
            ViewerChoice(
                label="Theme",
                attribute=AppearanceAttribute.THEME,
                storage_key=AppearanceStorageKey.THEME,
                options=[
                    ChoiceOption(theme.identifier, theme.title) for theme in self.themes
                ],
                default=self.default_theme.identifier,
            ),
        ]
