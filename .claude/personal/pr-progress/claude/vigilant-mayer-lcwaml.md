## Plan
- PR #187 (draft, release:minor), reshaped after owner review 2026-11-11:
  - session start records merged items of every plan (`merged_items every-plan`), replacing the one-plan recording;
  - drop the merge-time workflow (reusable workflow, merge-template `record` job, their enums);
  - one item per branch: validation refuses a branch named twice, within or across plans;
  - answer the 4 inline threads and clarify that code.

## Done
- Owner decisions taken in chat (session start over workflow; one item per branch).
- Branch restacked onto main 53375b5 at d857175 by the maintenance pass.

## Next
- Tests first, then the changes above; update PR description; reply to threads.
