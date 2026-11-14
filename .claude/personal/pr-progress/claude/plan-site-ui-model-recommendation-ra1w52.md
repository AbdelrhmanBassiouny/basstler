## Plan
- ModelAlias enum (opus, sonnet, haiku) replaces ModelOption
- plan-item-models.toml plus personal override, layered like plan-item-modes.toml
- ItemAction declares its skill; the template preselects the recommended alias

## Done
- Draft PR #209: tests, implementation, build wiring
- Merged main (conflicts in plan_site/__main__.py and cards.py, imports only); plan, plan_site, stack suites, ruff, code-rules pass

## Next
- Review; confirm the default aliases (both sonnet, an assumption)
