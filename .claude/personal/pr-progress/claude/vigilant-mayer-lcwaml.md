## Plan
- Plans stay true to GitHub on their own: one branch per item, merged items recorded at merge time.

## Done
- Validation refuses a branch two items name (same plan or another); index no longer warns on same-plan repeats.
- `merged_items every-plan` records and prunes every plan, pushes with retries; reusable workflow plan-merged-items.yml; merge workflow calls it on merge.
- Data cleaned: 17 stale merged items in 10 plans across both notes repositories; tracy_icra shared by three CRAM items fixed.

## Next
- Full suite, commit, push, draft PR (release:minor).
- After release: re-run /setup-personal-notes in each notes repository so its merge workflow gains the record job.
