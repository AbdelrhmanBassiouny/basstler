## Plan
- Record items done whose pull requests GitHub reports merged, in save-plan.sh and at session start; a failed read changes nothing.

## Done
- `basstler.plan.merged_items` with unit tests; save-plan.sh records before staging; session-start.sh records and saves the loaded plan, with a `merged items` summary line.
- Tests written first; full suite green apart from 4 local Playwright browser errors. Pushed; PR #172 is a draft labelled `bug`.

## Next
- Wait for CI and review on #172.
