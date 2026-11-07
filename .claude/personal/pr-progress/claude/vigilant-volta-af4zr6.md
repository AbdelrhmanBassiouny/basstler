PR: https://github.com/AbdelrhmanBassiouny/basstler/pull/155 (draft, bug, patch)

Plan
- Release only tested commits; serve the plugin from the release; setup never pushes to main.

Done
- release.yml follows Tests, tags the tested commit, atomically moves `release` (created at v3.8.1).
- marketplace.json serves the plugin from `release` via git-subdir.
- Merge workflow always proposed by PR; contract test counts real invocations.
- Review thread on plugin syncing answered and resolved.

Next
- CI-failure issue design: open thread, awaiting user's choice.
- stack_upstream for non-forks: own PR after #155; likely folds into
  basstler-v2-fixes/restack-without-upstream - confirm with user.
