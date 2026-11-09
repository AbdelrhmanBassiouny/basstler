## Plan
- Failing tests first: unit test of recording merged items; save-plan.sh test that a merged item is dropped; session-start test.
- `basstler.plan.merged_items`: mark each item whose pull request GitHub reports merged as done; a failed read changes nothing and exits with its own status.
- save-plan.sh records merged items on the merged manifest before staging; a failed read is reported and the save goes on.
- session-start.sh records them for the loaded plan and saves it when any changed.

## Done
- Branch, draft PR #172, item recorded in progress.

## Next
- Write the failing tests.
