basstler#16 (workflow-cutover / routine-cutover), reshaped with the owner on 2026-10-24.

**Plan**
- No Action. Stack maintenance runs at the start of plan-item-kickoff/resolve (plan-item-gathering.md runs /stacked-pr-maintenance when an upstream is named).
- Reparents stay with the skill's MCP step; the pass only reports them.

**Done**
- ba02b79 dropped the workflow, example caller, run-unattended and the in-pass reparent, and added the gathering step. The MaintenanceReport class refactor stays. 1135 tests pass.
- Checked the other open PRs: #15 complements this but will conflict at the import level (stack.py split); #57 doesn't overlap.

**Next**
- Owner review (release:major: routine-prompt.md and --non-interactive removed in a7f2e00). Deleting the live Routine trigger on CRAM is the owner's step.
- An open thread asks whether to do a suite-wide sweep of retyped strings.
