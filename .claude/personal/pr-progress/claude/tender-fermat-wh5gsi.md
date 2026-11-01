# code-rules-light (PR #104)

## Plan
- pyproject: dev group + [tool.ruff]; fix findings; CI + pre-commit run ruff; AGENTS.md lightened

## Done
- All of the plan; ruff clean, 1749 tests pass
- Decisions in the PR description: TYPE_CHECKING rule dropped (pydantic), pydantic not added until first boundary, black kept
- Answered the SiteSection PEP 695 thread (krrood compatibility, importing SectionCard, SubclassSafeGeneric not needed); no code change, thread left open

## Next
- Owner reply on that thread; CI result on the new ruff job
