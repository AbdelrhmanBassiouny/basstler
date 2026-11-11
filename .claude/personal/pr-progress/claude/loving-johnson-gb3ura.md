## Plan
- Failing test: the merge workflow's pull request opens as a draft
- Drop `draft=False` from `MergeWorkflowProposal.opening`
- Merge step marks a draft ready first (`draft` on `RestPullRequestSummary`, recordings gain `draft`)
- Update `/setup-personal-notes` step description

## Done
- Branch, draft PR #196, item recorded in progress

## Next
- Write the failing tests
