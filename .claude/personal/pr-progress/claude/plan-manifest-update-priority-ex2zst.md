### Plan
1. Merge `main` into the branch: port its 19 commits from the pre-`src/` layout onto
   `main`'s subpackages (`basstler.plan.item_bootstrap`, `basstler.maintenance.*`,
   `tests/plan`, `tests/maintenance`), reusing what `main` already has
   (`basstler.exceptions.DataclassException`, `ExitCode`, `CommandFailure`, the item-indent fix).
2. Run the full test suite and the format hook, then push.
3. Update the PR description, `plan.yaml` notes, and the dashboard; PR stays draft.

### Done
- Resolve found the stall: `mergeable_state: dirty`, no CI, no review threads.

### Next
- Step 1.
