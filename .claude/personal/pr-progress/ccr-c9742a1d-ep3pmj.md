## Plan
- `MergeWorkflow` on the notes repository's default branch, started by a merged pull request; same token and step as the dispatch workflow.

## Done
- `MergeWorkflow`, `WorkflowLocation.PLAN_SITE_MERGE`, merge template extending the dispatch template (dispatch output unchanged).
- Publication writes it onto the default branch (`default_branch_of`).
- Tests (6 new), setup skill step 8, PR description, `release:minor`.

## Next
- Owner's call: `pull_request_target` to cover fork pull requests; a user step when the default branch refuses direct pushes.
- After merge: re-run setup in each published repository.
