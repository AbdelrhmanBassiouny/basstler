**Plan**
- Ceilings `runs_per_day` / `jobs_per_day` on `WorkflowLimits` (unset by default)
- `basstler.actions_usage`: 24-hour counts per workflow, levels at 80% / 100%
- Surfaces: session-start line, `tests.yml` first job + `budget-override` gate, report command
- Tests first, mocked client

**Done**
- Ceilings, `actions_usage` module and report command, with mocked-client tests
- Session-start "Actions usage" line (silent when no ceilings are set) and its tests
- `tests.yml`: `usage` job first; `test` matrix skipped over a ceiling unless `budget-override`

**Next**
- Owner: set the ceilings' numbers in `.github/actions_budget.py` (none exist yet) and create the `budget-override` label
- Review the draft
