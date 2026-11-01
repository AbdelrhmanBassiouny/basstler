# code-rules-light (PR #104)

## Plan
- pyproject: dev group + [tool.ruff]; fix findings; CI + pre-commit run ruff; AGENTS.md lightened

## Done
- All of the plan; ruff clean, 1749 tests pass
- Decisions in the PR description: TYPE_CHECKING rule dropped (pydantic), pydantic not added until first boundary, black kept

## Next
- Owner review; CI result on the new ruff job
