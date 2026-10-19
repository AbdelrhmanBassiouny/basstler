## Plan
- #18 (new-plan-when-full) is stacked on #11 and routes new work by #11's Measure.ITEM_COUNT, not by CRAM #207's budget.

## Done
- #18 retargeted onto #11: plan_size_check counts unlanded items against Measure.ITEM_COUNT; the #207 budget module and report hook are deleted.
- #11 has main merged in, and both review rounds (9 + 3 threads) are addressed and resolved; it now has a shared basstler.exceptions.DataclassException.
- #11 is re-merged into #18 (c615582); 968 tests pass on #18 and 961 on #11.

## Next
- After #11 lands, change #18's base back to main.
