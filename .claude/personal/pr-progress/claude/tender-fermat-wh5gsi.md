# code-rules-light (PR #104)

## Plan
- pyproject: `dev` dependency group (ruff, pytest, pytest-xdist) and `[tool.ruff]` for the mechanical rules
- Fix ruff's findings on existing code
- CI and pre-commit run `ruff check`
- AGENTS.md: drop prose ruff enforces; add the approved lighter rules

## Done
- Branch, draft PR, manifest recorded

## Next
- ruff configuration and fixes
