## Plan
- Merge workflow starts the site build on merge; placement under discussion: always on `basstler/plan-site-merge` with setup opening its PR, skipped for forks.

## Done
- `MergeWorkflow` on `pull_request_target` closed+merged; written to the default branch (for now).
- Actions budget: reads `pull_request_target`; a repository pin counts as a fork guard; dispatch and merge workflows both pass.

## Next
- Owner decides placement; then replace the direct default-branch write (parked direct-push fallback patch is superseded if accepted).
