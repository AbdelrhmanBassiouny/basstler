Plan:
- Draft PR #32 (bug): PRs name their own version; release.yml only tags the merged commit and publishes a GitHub release, so the claude.ai plugin sync gets the version from the merge

Done:
- GitHub release step; bump-in-PR check (next patch/minor/major), idempotent `bump` (default patch), tag-only release step; tests, README; this PR bumps to 0.1.2

Next:
- Owner reviews/merges #32
- After merge: confirm a new session's synced plugin.json says 0.1.2 and installs @v0.1.2
- Optional: hand-create releases for v0.1.0 / v0.1.1
