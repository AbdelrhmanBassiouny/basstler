PR #173 - install the package at the plugin's own release (bug, patch).

Plan
- Keep the PR to the release-pinning fix; split of session-start tests/source is follow-up work.

Done
- Pinned the package to plugin.json's version; `release:` line and `mismatched` status (a5241ccb).
- Review: a plugin naming no release now installs nothing and every hook stops (fd0cf854); thread resolved.

Next
- Propose the split (test module, then hook source) via /add-plan-item once #173 lands; then resolve the split thread.
- Ask whether the plugin-content digest can go, now that the source changes with every release.
