## Plan
- `GitHubAddress.SSH` and `clone_root_for(remote_url)`; `RemoteBranch.url`
- Publication command derives `remote_root` from the notes remote
- `PublicationPushRefusedError` with `PushRefusal`, naming `gh auth login`, `gh auth refresh -s workflow` or SSH
- Review: git is lent `gh`'s login (`GitHubLoginLendingRunner`) instead of telling the user to run `gh auth setup-git`

## Done
- All of the above, test-first (4d77ebd, 11a5d67); CI green on 4d77ebd; merge probe CLEAN against main 48ca1ab
- Review threads: rename resolved; "do it deterministically" answered, left open for the workflow-scope question

## Next
- CI on 11a5d67; owner's answer on whether the workflow scope should be checked before the first push
