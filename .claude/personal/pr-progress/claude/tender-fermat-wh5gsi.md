# code-rules-light (PR #104)

## Plan
- pyproject: dev group + [tool.ruff]; fix findings; CI + pre-commit run ruff; AGENTS.md lightened
- Ruff replaces black as the formatter (owner request), docformatter kept on top

## Done
- All of the plan; merged main; ruff check + ruff format --check clean, 1791 tests pass
- SiteSection PEP 695 thread answered and resolved by the owner
- Decisions in the PR description: TYPE_CHECKING rule dropped (pydantic), pydantic not added until first boundary

## Next
- Owner review; CI on the pushed merge + reformat
