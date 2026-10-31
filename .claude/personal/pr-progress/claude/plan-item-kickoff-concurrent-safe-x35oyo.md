# concurrent-safe-save (#98)

## Plan
- basstler.plan.manifest_merge: three-way merge (read / session / latest) per top-level key and per item; roadmap as one document; refuse an item both sides changed.
- save-plan.sh --read-at <commit> --attempts <n>: fetch, merge onto the fresh tip, validate, stage, commit, push; retry from the fetch on a rejected push.
- item_bootstrap: PlanDocuments records the commit it read and passes --read-at.
- Docs telling a session to edit and save pass --read-at.

## Done
- Branch, draft PR #98, item recorded in progress.

## Next
- Failing tests for the merge, then the merge module.
- Failing save-plan.sh tests (second writer pushes from a pre-push hook), then the retry loop.
