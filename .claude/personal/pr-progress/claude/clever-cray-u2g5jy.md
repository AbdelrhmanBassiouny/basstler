## Plan
- `GitHubAddress.SSH` and `clone_root_for(remote_url)`; `RemoteBranch.url`
- Publication command derives `remote_root` from the notes remote
- `PublicationPushRefusedError` with `PushRefusal`, naming `gh auth setup-git`, `gh auth refresh -s workflow` or SSH

## Done
- Implemented all three, test-first (4d77ebd); `GitHubCommand` moved to `github/credential.py` to avoid an import cycle
- Full suite: only the 38 environmental failures `main` also has; ruff, format and code-rules pass
- Overlaps probed: #141, #144, #154 and #172 share files that merge cleanly

## Next
- Read CI on 4d77ebd; owner review of the draft
