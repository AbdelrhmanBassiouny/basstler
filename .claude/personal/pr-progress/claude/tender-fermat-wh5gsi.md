# code-rules-light (PR #104)

## Plan
- pyproject: dev group + [tool.ruff]; fix findings; CI + pre-commit run ruff; AGENTS.md lightened
- Ruff replaces black as the formatter (owner request), docformatter kept on top

## Done
- All of the plan; main merged again (2026-11-01, conflict in test_save_plan.py), its 2 new ruff findings fixed
- ruff check + ruff format --check clean, 1860 tests pass; no open review threads
- Decisions in the PR description: TYPE_CHECKING rule dropped (pydantic), pydantic not added until first boundary

## Next
- CI red only from main's own break (#110 test vs #109 read_at); fixed in bug PR #112 - once it merges, merge main here, check ruff, push
- Owner review
