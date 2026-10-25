Plan
- Bug fix on #69: item_bootstrap reports why save-plan refused an edit instead of a bare CalledProcessError.

Done
- PlanSaveRefusedError carries save-plan's stderr; new exit status plan_save_refused (9); 4 tests; 1263 pass.

Next
- Await review.
