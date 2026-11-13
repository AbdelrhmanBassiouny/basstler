### Plan
- Theme model (ValidatedJSONModel) + built-in themes as YAML: Classic, Rosé, Forge, high-fantasy
- Hub file: default_theme and owner themes
- Render per-theme CSS tokens; site.css keeps layout
- WCAG AA contrast check; failing theme -> health banner, not published
- Header menu: light/dark/system + theme, localStorage, applied before first paint
- /site-theme-create skill and docs/themes.md

### Done
- Gathered context; branch, draft PR #212, item recorded in progress

### Next
- Tests for the theme model and contrast check, then the model
