## Plan
- Merge workflow starts the site build on merge: default branch directly; `basstler/plan-site-merge` + user step when refused; skipped for forks.

## Done
- `MergeWorkflow` on `pull_request_target`; fallback branch and step; fork skip via GitHub's `fork` flag.
- Actions budget: `pull_request_target`, repository pin as fork guard.
- New plan item `page-merge-recheck` (forks' merges from the browser); #62 comment.

## Next
- Review on #122.
