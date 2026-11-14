# Plan site themes

Every page of the plan site has a menu at its top: **Scheme** (system, light or dark)
and **Theme**. A viewer's pick is kept in their own browser and applied before the page
is drawn, so it carries across pages and visits. A viewer who picked nothing sees the
site's defaults.

## Built-in themes

| Theme | Look |
|---|---|
| `classic` | Teal on cool grey, flat cards and pill chips, the site's original look; the default |
| `rose` | Rose and plum, serif headings, cushioned raised cards that lift on hover, glossy pill chips |
| `forge` | Ember on iron, monospace headings, chiselled bevelled frames with a hard shadow, square chips |
| `elderwood` | Forest green and gold on parchment, book-face headings, carved double-ruled panels, engraved rounded chips |
| `citadel` | Gold on night slate, carved capitals, riveted polished-metal frames, embossed notched chips |

## Setting the defaults and adding themes

The site's owner sets both in the `appearance` section of the hub file
(`.claude/personal/plans/_hub.yaml` on the registry's notes branch):

```yaml
appearance:
  default_theme: harbour     # a built-in or an added theme's identifier
  default_scheme: system     # system, light or dark
  themes:
    - identifier: harbour
      title: Harbour
      light: { ... }
      dark: { ... }
      style: { ... }
```

An added theme with a built-in theme's identifier replaces it. The
`/site-theme-create` skill drafts a theme with you, checks it and saves it; by hand,
`basstler.sh plan_site.hub add-theme --hub <hub.yaml> --theme <theme.yaml> [--default]
--output <hub.yaml>` does the same check and edit.

## What a theme sets

- **`light` and `dark`**: one palette each, every colour written `#RRGGBB`.
  - `background`, `surface`, `surface_alternate`: behind the page, cards, and wave
    columns.
  - `text`, `text_muted`, `border`.
  - `accent` (bars, focus, highlights), `accent_strong` (links, eyebrows, accent chip
    text), `accent_tint` (behind accent chips and buttons).
  - The chip tones, each a text colour and a `_tint` behind it: `good` (landed,
    passing), `warning` (waiting), `bad` (failed, blocked, closed), `info` (under way),
    `idle` (nothing to report).
- **`style`** (optional; each key defaults to Classic's):
  - `body_font`, `heading_font`, `monospace_font`: CSS font lists.
  - `corner_radius`, `small_corner_radius`, `border_width`: lengths in `px`, `rem` or
    `em`.
  - `frame`: the shape and depth of cards, panels, chips and buttons:
    - `flat`: a thin flat border.
    - `raised`: cushioned, softly shadowed panels that lift on hover; glossy chips.
    - `beveled`: chiselled edges lit from the top left with a hard cast shadow;
      bevelled chips.
    - `carved`: double-ruled, sunken panels; engraved chips. Needs a `border_width` of
      at least `3px` to show both rules.
    - `metal`: riveted frames of polished metal in the theme's `accent` colour, with
      square corners whatever the radii say; embossed chips. The rivets are as wide as
      twice the `border_width`, so `5px` to `6px` suits it.
  - `chip_shape`: `pill`, `rounded` (the small corner radius), `square` or `notched`
    (corners cut at an angle).
  - `ornament`: up to four characters shown before each page's eyebrow.
  - `transition_duration`: how long hover and focus changes take, in `ms` or `s`;
    viewers who ask their system for reduced motion get none.

## The contrast check

Every build checks each theme's text against WCAG 2 level AA: a contrast of at least
4.5:1 for body, muted and link text on every background, for errors and warnings, for
the health banner and for every chip tone, in both schemes. A theme that misses it is
not published: the hub's health banner names it with each failing pairing, its scheme
and its ratio, and a default that fails falls back to Classic. Frames and chip shapes
only add borders, shading and outlines around the palette's fills, so they never change
what the check measured.
