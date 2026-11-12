## Plan
- PR #187 (draft, release:minor): session start records every plan's merged items; merge-time workflow removed; one item per branch.

## Done
- Pushed 7483065 (rework) and 8235a7a (dropped the two tests of two items on one branch).
- domain-models in cognitive_robot_abstract_machine notes cleaned (2e974e3).
- Replied to the review and all 4 threads; resolved the drop_landed_items and branch-index threads. BranchReport simplification queued as a follow-up task.

## Next
- Owner: push_attempts thread (keep caller-passed retries?) and the non-mapping guard thread (keep, or raise an error naming the file?).
- CI on 8235a7a: ruff and Actions usage passed; pytest was still running when last read.
