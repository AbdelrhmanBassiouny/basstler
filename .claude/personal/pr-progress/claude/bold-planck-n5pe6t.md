**Plan**
- Failing test first, then `-c core.hooksPath=/dev/null` on the one notes commit

**Done**
- Draft PR #177; test (rejecting pre-commit hook) failed, now passes
- Fix in `NotesBranchWriter.write`; ruff and format clean; no new suite failures (38 environment failures exist on main too)

**Next**
- Review; patch release (no label)
