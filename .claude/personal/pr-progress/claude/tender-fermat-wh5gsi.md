# code-rules-light (PR #104)

## Plan
- pyproject: dev group + [tool.ruff]; fix findings; CI + pre-commit run ruff; AGENTS.md lightened
- Ruff replaces black as the formatter (owner request), docformatter kept on top

## Done
- All of the plan; main merged with bug fix #112, new ruff findings from main fixed
- ruff check + ruff format --check clean, 1867 tests pass; no open review threads
- Decisions in the PR description: TYPE_CHECKING rule dropped (pydantic), pydantic not added until first boundary

## Next
- Owner review; CI on the latest push
