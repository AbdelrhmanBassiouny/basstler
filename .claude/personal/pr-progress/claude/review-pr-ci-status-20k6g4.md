Plan
- Resolve review thread r4316963874: parse the GraphQL responses into models, no dict walking.

Done
- Merged main (v0.1.2) in.
- 6b9d245: PageInfo, Commit, PullRequestCommit and PullRequest models, plus one result model per
  query in place of RepositoryJSON; the snapshot is assembled from a parsed PullRequest. 912 passed.
- Recorded the parse-into-models rule in notes.md and the basstler-package roadmap.

Next
- Owner review of 6b9d245. #14 (stacked) needs this branch merged in, since it edits the same module.
