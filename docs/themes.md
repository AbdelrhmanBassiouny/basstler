# Plan site themes

Every page of the plan site has a menu at its top: **Scheme** (system, light or dark)
and **Theme**. A viewer's pick is kept in their own browser and applied before the page
is drawn, so it carries across pages and visits. A viewer who picked nothing sees the
site's defaults.

## Built-in themes

| Theme | Look |
|---|---|
| `classic` | Teal on cool grey, flat cards and pill chips, the site's original look; the default |
| `rose` | Rose and plum, italic Didot-style headings, satin-and-lace frames and buttons with a rose at each corner; a garden with blossom trees, a gazebo, swans and cats, and falling petals |
| `forge` | Ember on iron, spaced capital monospace headings, wrought-iron frames with a molten seam and flames, riveted buttons; a volcano, a furnace hall, gears and smiths at the anvil, and rising sparks |
| `elderwood` | Forest green and gold on parchment, storybook headings, wooden frames and buttons twined with a berried vine; a moonlit pine forest with a great tree, an owl, stags and a fairy, and fireflies |
| `citadel` | Gold on night slate, small-capital inscription headings, gilded scrollwork frames set with gems, studded gold buttons; a citadel on a crag with dragons, a wizard and knights under twinkling stars |

Every theme but Classic is animated: cards arrive one after another, work under way
glows, progress bars shimmer and the backdrop drifts. A viewer whose system asks for
reduced motion sees all of it still.

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
  - `heading_case`: `as-written`, `uppercase` or `small-capitals`, for headings and
    buttons; `heading_letter_spacing`: a length added between their letters;
    `heading_italic`: `true` or `false`.
  - `corner_radius`, `small_corner_radius`, `border_width`: lengths in `px`, `rem` or
    `em`.
  - `frame`: the shape and depth of cards, panels, chips and buttons:
    - `flat`: a thin flat border.
    - `raised`: cushioned, softly shadowed panels that lift on hover; glossy chips.
    - `beveled`: chiselled edges lit from the top left with a hard cast shadow;
      bevelled chips.
    - `carved`: double-ruled, sunken panels; engraved chips. Needs a `border_width` of
      at least `3px` to show both rules.
    - `gilded`, `vine`, `lace`, `forged`: thick frames drawn as pictures in the
      theme's own colours, with ornate corners that reach past the card: gilded
      scrollwork set with gems (`accent`, gems in `bad`), wood twined with a berried
      vine (`accent` leaves), satin and lace with roses (`accent`, leaves in `good`),
      and wrought iron with a molten seam and flames (`accent`). They ignore the
      radii and `border_width`, draw buttons and menus to match, set buttons in the
      heading font and enlarge the page's title.
  - `backdrop`: a scene along the foot of the page and what drifts behind it: `none`,
    `stars` (a citadel, dragons, a wizard and knights), `embers` (a volcano, a
    furnace hall and smiths), `fireflies` (a forest, a great tree, an owl and stags)
    or `petals` (a garden, a gazebo, swans and cats).
  - `animated`: `true` makes cards arrive, work under way glow, progress bars shimmer
    and the backdrop drift; `false`, the default, keeps everything still.
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
what the check measured. A backdrop's scene is painted in the
background tinted at most 14% towards the text colour, and a theme with a backdrop is
also checked for body, muted and link text on that darkest tint. What drifts across
the scene is small, and text lying straight on the page carries a halo of the
background colour.
