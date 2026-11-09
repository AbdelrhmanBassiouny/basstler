## Plan
- `GitHubAddress.SSH` and `clone_root_for(remote_url)`; `RemoteBranch.url`
- Publication command derives `remote_root` from the notes remote
- `PublicationPushRefusedError` with `PushRefusal`, naming `gh auth setup-git`, `gh auth refresh -s workflow` or SSH

## Done
- Bootstrapped the branch and draft PR #179

## Next
- Failing tests, then the fix
