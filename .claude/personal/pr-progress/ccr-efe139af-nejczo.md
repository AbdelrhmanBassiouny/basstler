**Plan**
- Ceilings `runs_per_day` / `jobs_per_day` on `WorkflowLimits` (unset by default)
- `basstler.actions_usage`: 24-hour counts per workflow, levels at 80% / 100%
- Surfaces: session-start line, `tests.yml` first job + `budget-override` gate, report command
- Tests first, mocked client

**Done**
- Context gathered; plan written down

**Next**
- Bootstrap, then limits + exceptions + measurement tests
