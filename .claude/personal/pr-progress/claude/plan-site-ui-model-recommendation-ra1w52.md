## Plan
- ModelAlias enum (opus, sonnet, haiku) replaces ModelOption
- plan-item-models.toml plus personal override, layered like plan-item-modes.toml
- ItemAction declares its skill; the template preselects the recommended alias

## Done
- Bootstrap, draft PR #209
- Tests, implementation, build wiring; full plan and plan_site suites, ruff and code-rules pass

## Next
- Review; confirm the default aliases (both sonnet, an assumption)
