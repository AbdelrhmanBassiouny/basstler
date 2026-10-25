### Plan
1. Merge `main`, porting the branch onto `basstler.plan` / `main`'s classes (done: `5940e8f`).
2. Full suite (1451 passed) and format hook, push (done).
3. PR description, `release:minor`, `plan.yaml` notes, dashboard (done).

### Done
- Dropped the branch's git runner/exceptions/stack refactor: `main` already unified them.
- Shared `basstler.command_line.Command` now backs `MaintenanceCommand` and the bootstrap's commands.

### Next
- CI on `5940e8f` had not reported when this session ended.
- The plugin's installed basstler (v2.2.0) lacks `update`/`check`/`block` until this lands and releases.
