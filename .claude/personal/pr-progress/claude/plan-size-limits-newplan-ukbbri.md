## Plan
- #18 (new-plan-when-full) is stacked on #11 and routes new work by #11's Measure.ITEM_COUNT, not by CRAM #207's budget.

## Done
- Merged #11 into the branch and changed the PR base to claude/happy-wozniak-nizfnv.
- plan_size_check counts unlanded items against Measure.ITEM_COUNT; a plan is full once it reaches the limit. Takes only --manifest (a StrEnum option).
- Deleted plan_size_budget.py, plan-size-report.sh and their tests/wiring; nothing else used them.
- 900 tests pass. Plan item updated (depends_on #11, no blockers).

## Next
- #11 has a merge conflict with main; #18 inherits it until #11 fixes it.
- When #11 renames plan_model.ManifestField to ManifestKey, update test_plan_size_check.py to match.
- After #11 lands, change #18's base back to main.
