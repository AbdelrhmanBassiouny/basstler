---
name: site-theme-create
description: "Design a theme for the plan site with the user, check its contrast, and add it to the hub file, optionally as the site's default. Invoke as \"/site-theme-create {theme-id} [what it should look like]\". Use when asked for a new site theme, palette or colour scheme, or to change the site's default theme."
allowed-tools: Bash, Read, Write, AskUserQuestion
---

# Site Theme Create

Run commands as [`running-commands.md`](../running-commands.md) says, with
`${CLAUDE_PLUGIN_ROOT}` as the `${BASSTLER_PLUGIN_ROOT}` it and every linked document name.

A theme is one YAML file, described for people in the basstler repository's
`docs/themes.md`:

```yaml
identifier: harbour            # lowercase words joined by hyphens
title: Harbour                 # its name in the page's theme menu
light: {background, surface, surface_alternate, text, text_muted, border, accent,
        accent_strong, accent_tint, good, good_tint, warning, warning_tint, bad,
        bad_tint, info, info_tint, idle, idle_tint}   # each "#RRGGBB"
dark: {the same keys}
style:                         # optional, each key optional
  body_font / heading_font / monospace_font   # CSS font lists
  heading_case                 # as-written, uppercase or small-capitals
  heading_letter_spacing       # px, rem or em
  heading_italic               # true or false
  corner_radius / small_corner_radius / border_width   # px, rem or em
  frame                        # flat, raised, beveled, carved (border_width >= 3px), or a picture frame: gilded, vine, lace, forged
  backdrop                     # none, stars, embers, fireflies or petals
  animated                     # true or false
  chip_shape                   # pill, rounded, square or notched
  ornament                     # up to 4 characters before each page's eyebrow
  transition_duration          # ms or s
```

## 1. Read the hub file

```bash
source "${CLAUDE_PLUGIN_ROOT}/hooks/resolve-personal-notes-config.sh"
fetch_personal_notes_branch >/dev/null
git show "${NOTES_REMOTE}/${NOTES_BRANCH}:${PLAN_HUB_PATH}"
```

The site reads only the hub file of the repository its `registry` key names. When that is
not this repository, say so and stop: the theme belongs in the registry's notes.

## 2. Design the theme

Draft the file in the scratchpad from what the user described. Give every key a value, both palettes included: a theme
the user only sees light is still shown dark to every viewer whose system is dark. Keep
the identifier lowercase words joined by hyphens.

## 3. Add it

```bash
source "${CLAUDE_PLUGIN_ROOT}/hooks/resolve-personal-notes-config.sh"
git show "${NOTES_REMOTE}/${NOTES_BRANCH}:${PLAN_HUB_PATH}" > <scratchpad>/hub.yaml
"${CLAUDE_PLUGIN_ROOT}/hooks/basstler.sh" plan_site.hub add-theme \
    --hub <scratchpad>/hub.yaml --theme <scratchpad>/<theme-id>.yaml \
    [--default] --output <scratchpad>/hub.yaml
```

Pass `--default` only when the user asked for the theme to be the site's default.
Exit 1 names every pairing below the WCAG AA contrast of 4.5:1, scheme and ratio
included: darken or lighten the colours it names and run it again. Never weaken the
check; the build leaves out a theme that fails it.

## 4. Save and publish

When the command prints `{"changed": true}`:

```bash
"${CLAUDE_PLUGIN_ROOT}/hooks/write-personal-notes-file.sh" --source <scratchpad>/hub.yaml \
    --destination "$(source "${CLAUDE_PLUGIN_ROOT}/hooks/resolve-personal-notes-config.sh" && echo "${PLAN_HUB_PATH}")" \
    --message "add the <theme-id> site theme"
"${CLAUDE_PLUGIN_ROOT}/hooks/basstler.sh" plan_site.build_start
```

Then tell the user the theme is in the menu at the top of every page once the build
finishes, and that each viewer's pick is kept in their own browser.
