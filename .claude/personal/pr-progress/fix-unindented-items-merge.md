## Plan
- Fix: a sequence entry flush with its key (`- id:` at column 0) no longer counts as a top-level key in plan-save merges.

## Done
- Failing tests with a flush-sequence fixture; `TOP_LEVEL_KEY` = `^[^\s-]`; draft PR #124 (`bug`).
- Used the patched checkout once to save the team-basstler split.

## Next
- Review; after release, the installed save works on flush-sequence plans.
